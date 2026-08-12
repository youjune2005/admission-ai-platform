"""행정문서 작성 결과 → 문서 보관함 저장/조회."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import BriefingPlan, GeneratedDocument

STATUS_LABELS = {
    "draft": "작성 중",
    "review": "직원 확인 필요",
    "approved": "승인 완료",
    "archived": "보관 완료",
}

KIND_DOC_TYPE = {
    "briefing": "계획서",
    "budget": "예산안",
    "visit": "계획서",
    "fair": "계획서",
    "interview": "안내문",
    "report": "보고서",
    "notice": "안내문",
    "faq": "FAQ",
}


def file_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/api/forms/files/{quote(Path(path).name)}"


def serialize_doc(doc: GeneratedDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_kind": doc.source_kind,
        "source_id": doc.source_id,
        "doc_type": doc.doc_type,
        "admission_category": doc.admission_category,
        "academic_year": doc.academic_year,
        "author": doc.author,
        "last_modifier": doc.last_modifier,
        "status": doc.status,
        "status_label": STATUS_LABELS.get(doc.status, doc.status),
        "version": doc.version,
        "pdf_url": file_url(doc.pdf_path),
        "preview_url": file_url(doc.preview_path),
        "approver": doc.approver,
        "approved_at": doc.approved_at.isoformat() if doc.approved_at else None,
        "archived_at": doc.archived_at.isoformat() if doc.archived_at else None,
        "archive_location": doc.archive_location,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        "payload": json.loads(doc.payload_json) if doc.payload_json else None,
    }


def upsert_generated_document(
    db: Session,
    *,
    title: str,
    source_kind: str,
    source_id: int | None = None,
    pdf_path: str | None = None,
    preview_path: str | None = None,
    payload: dict[str, Any] | None = None,
    doc_type: str | None = None,
    admission_category: str = "수시",
    academic_year: str = "2027",
    author: str = "입학팀 담당자",
    status: str = "approved",
) -> GeneratedDocument:
    """동일 source_kind+source_id가 있으면 갱신, 없으면 생성."""
    doc: GeneratedDocument | None = None
    if source_id is not None:
        doc = (
            db.query(GeneratedDocument)
            .filter(
                GeneratedDocument.source_kind == source_kind,
                GeneratedDocument.source_id == source_id,
            )
            .first()
        )

    now = datetime.utcnow()
    resolved_type = doc_type or KIND_DOC_TYPE.get(source_kind, "계획서")

    if doc is None:
        doc = GeneratedDocument(
            title=title,
            source_kind=source_kind,
            source_id=source_id,
            doc_type=resolved_type,
            admission_category=admission_category,
            academic_year=academic_year,
            author=author,
            last_modifier=author,
            status=status,
            pdf_path=pdf_path,
            preview_path=preview_path,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            approver="입학팀 팀장" if status in ("approved", "archived") else None,
            approved_at=now if status in ("approved", "archived") else None,
            archived_at=now if status == "archived" else None,
            archive_location="문서 보관함" if status == "archived" else None,
        )
        db.add(doc)
    else:
        doc.title = title
        doc.doc_type = resolved_type
        doc.admission_category = admission_category
        doc.academic_year = academic_year
        doc.last_modifier = author
        doc.pdf_path = pdf_path or doc.pdf_path
        doc.preview_path = preview_path or doc.preview_path
        doc.payload_json = json.dumps(payload or {}, ensure_ascii=False)
        if status:
            doc.status = status
            if status in ("approved", "archived") and not doc.approved_at:
                doc.approver = doc.approver or "입학팀 팀장"
                doc.approved_at = now
            if status == "archived":
                doc.archived_at = now
                doc.archive_location = doc.archive_location or "문서 보관함"
        doc.updated_at = now

    db.commit()
    db.refresh(doc)
    return doc


def backfill_from_briefing_plans(db: Session) -> int:
    """기존 BriefingPlan(완료분)을 보관함으로 이관."""
    created = 0
    plans = (
        db.query(BriefingPlan)
        .filter(BriefingPlan.status.in_(("completed", "generating")))
        .order_by(BriefingPlan.id.asc())
        .all()
    )
    for plan in plans:
        if not plan.pdf_path:
            continue
        exists = (
            db.query(GeneratedDocument)
            .filter(
                GeneratedDocument.source_kind.in_(("briefing", "budget")),
                GeneratedDocument.source_id == plan.id,
            )
            .first()
        )
        if exists:
            continue
        try:
            payload = json.loads(plan.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        kind = "budget" if payload.get("type") == "budget" else "briefing"
        upsert_generated_document(
            db,
            title=plan.title,
            source_kind=kind,
            source_id=plan.id,
            pdf_path=plan.pdf_path,
            preview_path=plan.preview_path,
            payload=payload,
            doc_type=KIND_DOC_TYPE.get(kind, "계획서"),
            status="approved" if plan.status == "completed" else "draft",
        )
        created += 1
    return created


def list_documents(
    db: Session,
    *,
    q: str | None = None,
    status: str | None = None,
    doc_type: str | None = None,
    admission_category: str | None = None,
    academic_year: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    backfill_from_briefing_plans(db)

    query = db.query(GeneratedDocument)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                GeneratedDocument.title.ilike(like),
                GeneratedDocument.author.ilike(like),
                GeneratedDocument.doc_type.ilike(like),
                GeneratedDocument.admission_category.ilike(like),
            )
        )
    if status and status != "all":
        query = query.filter(GeneratedDocument.status == status)
    if doc_type and doc_type != "all":
        query = query.filter(GeneratedDocument.doc_type == doc_type)
    if admission_category and admission_category != "all":
        query = query.filter(GeneratedDocument.admission_category == admission_category)
    if academic_year and academic_year != "all":
        query = query.filter(GeneratedDocument.academic_year == academic_year)
    if date_from:
        query = query.filter(GeneratedDocument.updated_at >= date_from)
    if date_to:
        query = query.filter(GeneratedDocument.updated_at <= date_to)

    total = query.count()
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    rows = (
        query.order_by(GeneratedDocument.updated_at.desc(), GeneratedDocument.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 전체 카운트 (필터와 무관한 탭용 — 검색어만 반영)
    base = db.query(GeneratedDocument)
    if q:
        like = f"%{q.strip()}%"
        base = base.filter(
            or_(
                GeneratedDocument.title.ilike(like),
                GeneratedDocument.author.ilike(like),
                GeneratedDocument.doc_type.ilike(like),
            )
        )
    counts = {
        "all": base.count(),
        "draft": base.filter(GeneratedDocument.status == "draft").count(),
        "review": base.filter(GeneratedDocument.status == "review").count(),
        "approved": base.filter(GeneratedDocument.status == "approved").count(),
        "archived": base.filter(GeneratedDocument.status == "archived").count(),
    }

    facets = {
        "academic_years": [
            r[0]
            for r in db.query(GeneratedDocument.academic_year)
            .distinct()
            .order_by(GeneratedDocument.academic_year.desc())
            .all()
            if r[0]
        ],
        "admission_categories": [
            r[0]
            for r in db.query(GeneratedDocument.admission_category).distinct().all()
            if r[0]
        ],
        "doc_types": [
            r[0] for r in db.query(GeneratedDocument.doc_type).distinct().all() if r[0]
        ],
    }

    return {
        "items": [serialize_doc(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts": counts,
        "facets": facets,
    }


def get_document(db: Session, doc_id: int) -> GeneratedDocument | None:
    return db.get(GeneratedDocument, doc_id)


def update_status(
    db: Session,
    doc: GeneratedDocument,
    status: str,
    *,
    modifier: str = "입학팀 담당자",
) -> GeneratedDocument:
    now = datetime.utcnow()
    doc.status = status
    doc.last_modifier = modifier
    doc.updated_at = now
    if status in ("approved", "archived") and not doc.approved_at:
        doc.approver = doc.approver or "입학팀 팀장"
        doc.approved_at = now
    if status == "archived":
        doc.archived_at = now
        doc.archive_location = doc.archive_location or "문서 보관함"
    db.commit()
    db.refresh(doc)
    return doc


def duplicate_document(db: Session, doc: GeneratedDocument) -> GeneratedDocument:
    settings = get_settings()
    out_dir = Path(settings.upload_dir) / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    new_pdf = None
    new_preview = None
    if doc.pdf_path and Path(doc.pdf_path).exists():
        new_pdf = out_dir / f"{Path(doc.pdf_path).stem}_copy_{stamp}.pdf"
        shutil.copy2(doc.pdf_path, new_pdf)
    if doc.preview_path and Path(doc.preview_path).exists():
        new_preview = out_dir / f"{Path(doc.preview_path).stem}_copy_{stamp}.png"
        shutil.copy2(doc.preview_path, new_preview)

    clone = GeneratedDocument(
        title=f"{doc.title} (복제)",
        source_kind=doc.source_kind,
        source_id=None,
        doc_type=doc.doc_type,
        admission_category=doc.admission_category,
        academic_year=doc.academic_year,
        author=doc.author,
        last_modifier=doc.author,
        status="draft",
        version="v1.0",
        pdf_path=str(new_pdf) if new_pdf else doc.pdf_path,
        preview_path=str(new_preview) if new_preview else doc.preview_path,
        payload_json=doc.payload_json,
        approver=None,
        approved_at=None,
        archived_at=None,
        archive_location=None,
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return clone


def delete_document(db: Session, doc: GeneratedDocument) -> None:
    db.delete(doc)
    db.commit()
