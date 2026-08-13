"""규정·자료 관리용 data/guidelines 시드 및 메타 동기화."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import now_kst
from app.db.models import UploadedDocument
from app.services.document_service import extract_text, summarize_document
from app.services.rag_service import ingest_document

STATUS_LABELS = {
    "latest": "최신 적용",
    "needs_update": "업데이트 필요",
    "processing": "처리 중",
}

# filename(실제 파일명) → 메타
GUIDELINE_META: list[dict] = [
    {
        "filename": "등록금 명세서_별지 제8호 서식_작성 지침.md",
        "category": "예산·행정 규정",
        "version": "V1.0",
        "status": "needs_update",
    },
    {
        "filename": "등록금 명세서_별지 제8호 서식.pdf",
        "category": "문서 양식",
        "version": "V1.0",
        "status": "latest",
    },
    {
        "filename": "수당 종류와 기준.pdf",
        "category": "예산·행정 규정",
        "version": "V1.0",
        "status": "latest",
    },
    {
        "filename": "2027학년도 숭실대학교 수시모집요강.pdf",
        "category": "모집요강",
        "version": "V1.0",
        "status": "latest",
    },
    {
        "filename": "2027학년도 숭실대학교 입학전형 시행계획(안).pdf",
        "category": "입학처 공지",
        "version": "V1.0",
        "status": "latest",
        # 이전 파일명으로 등록된 레코드 매칭
        "aliases": ["2027_plan.pdf"],
    },
]


def _doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "excel"
    if lower.endswith(".csv"):
        return "csv"
    return "text"


def _mtime_dt(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return now_kst()


def seed_guideline_documents(db: Session) -> dict[str, int]:
    """data/guidelines 파일을 DB에 등록/갱신합니다."""
    settings = get_settings()
    guidelines = Path(settings.data_dir) / "guidelines"
    if not guidelines.exists():
        return {"created": 0, "updated": 0}

    created = 0
    updated = 0

    for meta in GUIDELINE_META:
        filename = meta["filename"]
        path = guidelines / filename
        if not path.exists():
            continue

        aliases = meta.get("aliases") or []
        doc = (
            db.query(UploadedDocument)
            .filter(UploadedDocument.filename.in_([filename, *aliases]))
            .first()
        )
        if doc is None:
            doc = (
                db.query(UploadedDocument)
                .filter(UploadedDocument.stored_path.like(f"%{filename}"))
                .first()
            )
        for alias in aliases:
            if doc is None:
                doc = (
                    db.query(UploadedDocument)
                    .filter(UploadedDocument.stored_path.like(f"%{alias}"))
                    .first()
                )

        file_dt = _mtime_dt(path)

        if doc is None:
            summary = None
            try:
                text = extract_text(filename, path.read_bytes())
                summary = summarize_document(filename, text) if text.strip() else None
            except Exception:  # noqa: BLE001
                text = ""
            doc = UploadedDocument(
                filename=filename,
                stored_path=str(path.resolve()),
                doc_type=_doc_type(filename),
                summary=summary,
                source="data_folder",
                category=meta["category"],
                version=meta["version"],
                status=meta["status"],
                created_at=file_dt,
                updated_at=file_dt,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            if text.strip():
                try:
                    ingest_document(db, doc, text)
                except Exception:  # noqa: BLE001
                    pass
            created += 1
        else:
            doc.filename = filename
            doc.stored_path = str(path.resolve())
            doc.doc_type = _doc_type(filename)
            doc.source = "data_folder"
            doc.category = meta["category"]
            doc.version = meta["version"]
            doc.status = meta["status"]
            # 최종 업데이트는 기존값 유지 (없으면 파일 mtime)
            if not doc.updated_at:
                doc.updated_at = file_dt
            if not doc.created_at:
                doc.created_at = file_dt
            db.commit()
            updated += 1

    return {"created": created, "updated": updated}
