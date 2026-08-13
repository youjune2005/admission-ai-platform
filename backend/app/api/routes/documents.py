from datetime import datetime
from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import now_kst
from app.db.database import get_db
from app.db.models import DocumentChunk, UploadedDocument
from app.schemas.documents import DocumentListResponse, DocumentOut, IngestResult
from app.services.document_service import extract_text, summarize_document
from app.services.rag_service import ingest_document
from app.services.regulation_seed_service import STATUS_LABELS, seed_guideline_documents

router = APIRouter(prefix="/api/documents", tags=["documents"])

SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".docx", ".xlsx", ".xls")
CATEGORIES = ["모집요강", "입학처 공지", "FAQ", "예산·행정 규정", "문서 양식"]


def _doc_type(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".xlsx", ".xls")):
        return "excel"
    if lower.endswith(".csv"):
        return "csv"
    if lower.endswith(".docx"):
        return "docx"
    return "text"


def _chunk_count(db: Session, doc_id: int) -> int:
    return db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()


def _to_out(doc: UploadedDocument, rag_chunk_count: int = 0) -> DocumentOut:
    status = doc.status or "latest"
    return DocumentOut(
        id=doc.id,
        filename=doc.filename,
        doc_type=doc.doc_type,
        summary=doc.summary,
        source=doc.source or "upload",
        category=getattr(doc, "category", None) or "기타",
        version=getattr(doc, "version", None) or "V1.0",
        status=status,
        status_label=STATUS_LABELS.get(status, status),
        description=getattr(doc, "description", None),
        applied_date=getattr(doc, "applied_date", None),
        updated_at=getattr(doc, "updated_at", None) or doc.created_at,
        created_at=doc.created_at,
        rag_chunk_count=rag_chunk_count,
    )


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


@router.get("", response_model=DocumentListResponse)
def list_documents(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    # 시드 메타 동기화 (파일 rename 등 반영)
    seed_guideline_documents(db)

    q = db.query(UploadedDocument)
    if category:
        q = q.filter(UploadedDocument.category == category)

    total = q.count()
    rows = (
        q.order_by(UploadedDocument.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    all_docs = db.query(UploadedDocument).all()
    counts = {
        "total": len(all_docs),
        "latest": sum(1 for d in all_docs if (d.status or "latest") == "latest"),
        "needs_update": sum(1 for d in all_docs if d.status == "needs_update"),
        "processing": sum(1 for d in all_docs if d.status == "processing"),
    }

    return DocumentListResponse(
        items=[_to_out(d, _chunk_count(db, d.id)) for d in rows],
        total=total,
        page=page,
        page_size=page_size,
        counts=counts,
        categories=CATEGORIES,
    )


@router.post("/upload", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str = Form("예산·행정 규정"),
    version: str = Form("V1.0"),
    description: str | None = Form(None),
    applied_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """파일 저장 → DB 등록 → 텍스트 추출 → RAG(임베딩) 인제스트."""
    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix.lower()
    if suffix and suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 형식입니다. 허용: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    display_name = (title or "").strip() or original_name
    # 확장자 유지
    if "." not in display_name and "." in original_name:
        display_name = f"{display_name}{Path(original_name).suffix}"

    # 동일 파일명 덮어쓰기 충돌 방지
    dest_path = upload_dir / original_name
    if dest_path.exists():
        stem = Path(original_name).stem
        ext = Path(original_name).suffix
        dest_path = upload_dir / f"{stem}_{now_kst().strftime('%Y%m%d%H%M%S')}{ext}"

    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    content = dest_path.read_bytes()
    try:
        text = extract_text(original_name, content)
        summary = summarize_document(original_name, text) if text.strip() else None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"서류를 처리하는 중 오류가 발생했습니다: {exc}") from exc

    now = now_kst()
    doc = UploadedDocument(
        filename=display_name,
        stored_path=str(dest_path.resolve()),
        doc_type=_doc_type(original_name),
        summary=summary,
        source="upload",
        category=category or "기타",
        version=(version or "V1.0").strip() or "V1.0",
        status="processing",
        description=(description or "").strip() or None,
        applied_date=_parse_date(applied_date),
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    rag_chunks = 0
    if not text.strip():
        doc.status = "needs_update"
        doc.updated_at = now_kst()
        db.commit()
        db.refresh(doc)
        # DB에는 등록됐지만 RAG 불가 — 호출자에게 안내
        raise HTTPException(
            status_code=422,
            detail=(
                "파일은 등록됐으나 텍스트를 추출하지 못해 RAG 인덱싱에 실패했습니다. "
                "텍스트가 있는 PDF/DOCX/MD로 다시 업로드하거나 OCR이 가능한 파일인지 확인해 주세요."
            ),
        )

    try:
        rag_chunks = ingest_document(db, doc, text)
    except Exception as exc:  # noqa: BLE001
        doc.status = "needs_update"
        doc.updated_at = now_kst()
        db.commit()
        db.refresh(doc)
        raise HTTPException(
            status_code=500,
            detail=f"DB 등록은 됐으나 RAG 임베딩 중 오류가 발생했습니다: {exc}",
        ) from exc

    if rag_chunks <= 0:
        doc.status = "needs_update"
        doc.updated_at = now_kst()
        db.commit()
        db.refresh(doc)
        raise HTTPException(
            status_code=500,
            detail=(
                "DB 등록은 됐으나 RAG 임베딩 청크가 생성되지 않았습니다. "
                "OpenAI API 키·임베딩 설정을 확인해 주세요."
            ),
        )

    doc.status = "latest"
    doc.updated_at = now_kst()
    db.commit()
    db.refresh(doc)
    return _to_out(doc, rag_chunks)


@router.post("/ingest-data-folder", response_model=IngestResult)
def ingest_data_folder(db: Session = Depends(get_db)):
    """data/ 폴더 내 새 문서(PDF, TXT, MD)를 찾아 요약·임베딩까지 자동으로 처리합니다."""
    settings = get_settings()
    data_dir = Path(settings.data_dir).resolve()
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail=f"데이터 폴더를 찾을 수 없습니다: {data_dir}")

    # 먼저 guidelines 시드
    seed_guideline_documents(db)

    existing_paths = {doc.stored_path for doc in db.query(UploadedDocument).all()}
    existing_names = {doc.filename for doc in db.query(UploadedDocument).all()}

    ingested: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.name.upper() == "README.MD":
            continue
        if str(path) in existing_paths or path.name in existing_names:
            skipped.append(path.name)
            continue

        try:
            content = path.read_bytes()
            text = extract_text(path.name, content)
            summary = summarize_document(path.name, text) if text.strip() else None

            now = datetime.fromtimestamp(path.stat().st_mtime)
            doc = UploadedDocument(
                filename=path.name,
                stored_path=str(path.resolve()),
                doc_type=_doc_type(path.name),
                summary=summary,
                source="data_folder",
                category="기타",
                version="V1.0",
                status="processing",
                created_at=now,
                updated_at=now,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            if not text.strip():
                doc.status = "needs_update"
                db.commit()
                failed.append(path.name)
                continue

            chunks = ingest_document(db, doc, text)
            if chunks <= 0:
                doc.status = "needs_update"
                db.commit()
                failed.append(path.name)
                continue

            doc.status = "latest"
            db.commit()
            ingested.append(path.name)
        except Exception:  # noqa: BLE001
            db.rollback()
            failed.append(path.name)

    return IngestResult(ingested=ingested, skipped=skipped, failed=failed)
