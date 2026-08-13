"""행정문서 작성 결과 → 문서 보관함 저장/조회."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import now_kst
from app.db.models import BriefingPlan, GeneratedDocument

STATUS_LABELS = {
    "draft": "작성 중",
    "issue": "문제 있음",
    "review": "검토 필요",
    "approved": "승인 완료",
    "archived": "보관 완료",
}

ARCHIVE_STATUSES = ("draft", "issue", "review", "approved", "archived")


def status_from_regulation_summary(summary: dict[str, Any] | None) -> str:
    if not summary:
        return "approved"
    try:
        violations = int(summary.get("violations") or 0)
    except (TypeError, ValueError):
        violations = 0
    try:
        checks = int(summary.get("needs_check") or 0)
    except (TypeError, ValueError):
        checks = 0
    if violations > 0:
        return "issue"
    if checks > 0:
        return "review"
    return "approved"


def resolve_archive_status(
    *,
    archive_status: str | None = None,
    regulation_summary: dict[str, Any] | None = None,
    default: str = "approved",
) -> str:
    if archive_status in ARCHIVE_STATUSES:
        return archive_status
    if regulation_summary:
        return status_from_regulation_summary(regulation_summary)
    return default if default in ARCHIVE_STATUSES else "approved"


def _apply_status_timestamps(doc: GeneratedDocument, status: str, now: datetime) -> None:
    if status in ("approved", "archived"):
        if not doc.approved_at:
            doc.approver = doc.approver or "입학팀 팀장"
            doc.approved_at = now
        if status == "archived":
            doc.archived_at = now
            doc.archive_location = doc.archive_location or "문서 보관함"
        return
    doc.approver = None
    doc.approved_at = None
    if status != "archived":
        doc.archived_at = None


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
    existing_id: int | None = None,
    touch_updated_at: bool = True,
) -> GeneratedDocument:
    """같은 문서(종류+제목+학년도)가 있으면 갱신, 없으면 생성.

    existing_id가 있으면 해당 작성 중/복제 문서를 우선 갱신합니다.
    이미 보관 완료된 건은 덮지 않고 새 문서로 둡니다.
    touch_updated_at=False면 백필처럼 조회 시 수정일을 건드리지 않습니다.
    """
    doc: GeneratedDocument | None = None
    if existing_id is not None:
        doc = db.get(GeneratedDocument, existing_id)
    if doc is None and source_id is not None:
        doc = (
            db.query(GeneratedDocument)
            .filter(GeneratedDocument.source_id == source_id)
            .first()
        )
    if doc is None and existing_id is None:
        doc = (
            db.query(GeneratedDocument)
            .filter(
                GeneratedDocument.source_kind == source_kind,
                GeneratedDocument.title == title,
                GeneratedDocument.academic_year == academic_year,
                GeneratedDocument.status.notin_(("archived", "draft")),
            )
            .order_by(GeneratedDocument.id.desc())
            .first()
        )

    now = now_kst()
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
            approver=None,
            approved_at=None,
            archived_at=None,
            archive_location=None,
        )
        _apply_status_timestamps(doc, status, now)
        db.add(doc)
    else:
        next_payload = json.dumps(payload or {}, ensure_ascii=False)
        next_pdf = pdf_path or doc.pdf_path
        next_preview = preview_path or doc.preview_path
        next_source_id = source_id if source_id is not None else doc.source_id
        content_changed = (
            doc.title != title
            or doc.source_kind != source_kind
            or doc.source_id != next_source_id
            or doc.doc_type != resolved_type
            or doc.admission_category != admission_category
            or doc.academic_year != academic_year
            or doc.pdf_path != next_pdf
            or doc.preview_path != next_preview
            or (doc.payload_json or "") != next_payload
            or (status and doc.status != status)
        )
        doc.title = title
        doc.source_kind = source_kind
        if source_id is not None:
            doc.source_id = source_id
        doc.doc_type = resolved_type
        doc.admission_category = admission_category
        doc.academic_year = academic_year
        doc.pdf_path = next_pdf
        doc.preview_path = next_preview
        doc.payload_json = next_payload
        if status:
            doc.status = status
            _apply_status_timestamps(doc, status, now)
        if content_changed:
            doc.last_modifier = author
            if touch_updated_at:
                doc.updated_at = now

    db.commit()
    db.refresh(doc)
    return doc


def _infer_plan_kind(payload: dict[str, Any]) -> str:
    kind = str(payload.get("plan_kind") or payload.get("type") or "").strip().lower()
    if kind in KIND_DOC_TYPE:
        return kind
    return "briefing"


def dedupe_generated_documents(db: Session) -> int:
    """같은 원본 계획(source_id)이 여러 건이면 한 건만 남깁니다."""
    rows = (
        db.query(GeneratedDocument)
        .filter(GeneratedDocument.source_id.isnot(None))
        .order_by(GeneratedDocument.id.asc())
        .all()
    )
    by_source: dict[int, list[GeneratedDocument]] = {}
    for row in rows:
        if row.source_id is None:
            continue
        by_source.setdefault(row.source_id, []).append(row)

    # visit/fair/budget가 briefing 복제본보다 원본에 가깝다
    rank = {"visit": 0, "fair": 0, "budget": 0, "briefing": 1}
    removed = 0
    for group in by_source.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda d: (rank.get(d.source_kind, 9), d.id))
        for extra in group[1:]:
            db.delete(extra)
            removed += 1
    if removed:
        db.commit()

    # 작성 중이 아닌 같은 제목·종류·학년도는 1건만 유지
    all_rows = db.query(GeneratedDocument).order_by(GeneratedDocument.id.asc()).all()
    by_identity: dict[tuple[str, str, str], list[GeneratedDocument]] = {}
    for row in all_rows:
        if row.status == "draft":
            continue
        key = (
            row.source_kind or "",
            (row.title or "").strip(),
            row.academic_year or "",
        )
        by_identity.setdefault(key, []).append(row)
    for group in by_identity.values():
        if len(group) < 2:
            continue
        group.sort(
            key=lambda d: (
                0 if d.status == "archived" else 1 if d.status == "approved" else 2,
                0 if d.pdf_path else 1,
                -(d.id or 0),
            )
        )
        for extra in group[1:]:
            db.delete(extra)
            removed += 1
    if removed:
        db.commit()
    return removed


def backfill_from_briefing_plans(db: Session) -> int:
    """기존 BriefingPlan(완료분)을 보관함으로 이관."""
    dedupe_generated_documents(db)

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
            .filter(GeneratedDocument.source_id == plan.id)
            .first()
        )
        if exists:
            continue
        try:
            payload = json.loads(plan.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        kind = _infer_plan_kind(payload)
        twin = (
            db.query(GeneratedDocument)
            .filter(
                GeneratedDocument.source_kind == kind,
                GeneratedDocument.title == plan.title,
                GeneratedDocument.status != "draft",
            )
            .order_by(GeneratedDocument.id.desc())
            .first()
        )
        if twin:
            if twin.source_id is None:
                twin.source_id = plan.id
                db.commit()
            continue
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
            touch_updated_at=False,
        )
        created += 1
    return created


SORTABLE_COLUMNS = {
    "title": GeneratedDocument.title,
    "updated_at": GeneratedDocument.updated_at,
}


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
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
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
    sort_col = SORTABLE_COLUMNS.get(sort_by, GeneratedDocument.updated_at)
    descending = (sort_dir or "desc").lower() != "asc"
    primary = desc(sort_col) if descending else asc(sort_col)
    secondary = desc(GeneratedDocument.id) if descending else asc(GeneratedDocument.id)
    rows = (
        query.order_by(primary, secondary)
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
        "issue": base.filter(GeneratedDocument.status == "issue").count(),
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
    now = now_kst()
    doc.status = status
    doc.last_modifier = modifier
    doc.updated_at = now
    _apply_status_timestamps(doc, status, now)
    db.commit()
    db.refresh(doc)
    return doc


def _unique_copy_title(db: Session, base_title: str) -> str:
    root = base_title.strip() or "문서"
    title = f"{root} (복제)"
    n = 2
    while (
        db.query(GeneratedDocument)
        .filter(GeneratedDocument.title == title)
        .first()
        is not None
    ):
        title = f"{root} (복제 {n})"
        n += 1
    return title


def preview_image_path(doc: GeneratedDocument, *, full: bool = False) -> Path | None:
    """미리보기 PNG. full=True면 PDF 1페이지를 원본 비율로 더 크게 렌더합니다."""
    settings = get_settings()
    out_dir = Path(settings.upload_dir) / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdf = Path(doc.pdf_path) if doc.pdf_path else None
    existing = Path(doc.preview_path) if doc.preview_path else None

    if full and pdf and pdf.exists():
        dest = out_dir / f"{pdf.stem}_preview_full.png"
        if dest.exists() and dest.stat().st_mtime >= pdf.stat().st_mtime:
            return dest
        try:
            import pymupdf

            rendered = pymupdf.open(pdf)
            pix = rendered[0].get_pixmap(matrix=pymupdf.Matrix(2.4, 2.4), alpha=False)
            pix.save(dest)
            rendered.close()
            return dest
        except Exception:  # noqa: BLE001
            if existing and existing.exists():
                return existing
            return None

    if existing and existing.exists():
        return existing
    if pdf and pdf.exists():
        dest = out_dir / f"{pdf.stem}.png"
        if dest.exists():
            return dest
        try:
            import pymupdf

            rendered = pymupdf.open(pdf)
            pix = rendered[0].get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
            pix.save(dest)
            rendered.close()
            return dest
        except Exception:  # noqa: BLE001
            return None
    return None


def duplicate_document(db: Session, doc: GeneratedDocument) -> GeneratedDocument:
    clone = GeneratedDocument(
        title=_unique_copy_title(db, doc.title),
        source_kind=doc.source_kind,
        source_id=None,
        doc_type=doc.doc_type,
        admission_category=doc.admission_category,
        academic_year=doc.academic_year,
        author=doc.author,
        last_modifier=doc.author,
        status="draft",
        version="v1.0",
        pdf_path=None,
        preview_path=None,
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
