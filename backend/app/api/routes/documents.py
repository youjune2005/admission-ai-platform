import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import UploadedDocument
from app.schemas.documents import DocumentOut, IngestResult
from app.services.document_service import extract_text, summarize_document
from app.services.rag_service import ingest_document

router = APIRouter(prefix="/api/documents", tags=["documents"])

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md")


def _doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "excel"
    if lower.endswith(".csv"):
        return "csv"
    return "text"


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(UploadedDocument).order_by(UploadedDocument.created_at.desc()).all()


@router.post("/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    dest_path = upload_dir / file.filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    content = dest_path.read_bytes()
    try:
        text = extract_text(file.filename, content)
        summary = summarize_document(file.filename, text) if text.strip() else None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"서류를 처리하는 중 오류가 발생했습니다: {exc}") from exc

    doc = UploadedDocument(
        filename=file.filename,
        stored_path=str(dest_path),
        doc_type=_doc_type(file.filename),
        summary=summary,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    if text.strip():
        ingest_document(db, doc, text)

    return doc


@router.post("/ingest-data-folder", response_model=IngestResult)
def ingest_data_folder(db: Session = Depends(get_db)):
    """data/ 폴더 내 새 문서(PDF, TXT, MD)를 찾아 요약·임베딩까지 자동으로 처리합니다."""
    settings = get_settings()
    data_dir = Path(settings.data_dir).resolve()
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail=f"데이터 폴더를 찾을 수 없습니다: {data_dir}")

    existing_paths = {doc.stored_path for doc in db.query(UploadedDocument).all()}

    ingested: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.name.upper() == "README.MD":
            continue
        if str(path) in existing_paths:
            skipped.append(path.name)
            continue

        try:
            content = path.read_bytes()
            text = extract_text(path.name, content)
            summary = summarize_document(path.name, text) if text.strip() else None

            doc = UploadedDocument(
                filename=path.name,
                stored_path=str(path),
                doc_type=_doc_type(path.name),
                summary=summary,
                source="data_folder",
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            if text.strip():
                ingest_document(db, doc, text)

            ingested.append(path.name)
        except Exception:  # noqa: BLE001
            db.rollback()
            failed.append(path.name)

    return IngestResult(ingested=ingested, skipped=skipped, failed=failed)
