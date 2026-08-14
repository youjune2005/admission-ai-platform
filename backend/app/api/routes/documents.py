from datetime import datetime
from pathlib import Path
import logging
import queue
import re
import shutil
import threading

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutil import now_kst
from app.db.database import SessionLocal, get_db
from app.db.models import DocumentChunk, UploadedDocument
from app.schemas.documents import DocumentListResponse, DocumentOut, IngestResult
from app.services.document_service import (
    ExtractionResult,
    extract_document,
    summarize_document,
)
from app.services.hwp_convert_service import convert_hwp_to_pdf, is_hwp_filename
from app.services.rag_service import ingest_document
from app.services.regulation_seed_service import STATUS_LABELS, seed_guideline_documents
from app.services.title_suggest_service import suggest_document_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

# OCR·임베딩은 동시에 돌리면 레이트 리밋·DB 경합이 나기 쉬워 한 건씩 처리합니다.
_DOC_JOB_QUEUE: queue.Queue[tuple[int, str | None]] = queue.Queue()
_DOC_JOB_PENDING: set[int] = set()
_DOC_JOB_LOCK = threading.Lock()
_DOC_JOB_WORKER_STARTED = False


def _doc_job_worker() -> None:
    while True:
        doc_id, old_path = _DOC_JOB_QUEUE.get()
        try:
            _process_document_job(doc_id, old_path=old_path)
        except Exception:  # noqa: BLE001
            logger.exception("문서 작업 워커에서 예외: doc_id=%s", doc_id)
        finally:
            with _DOC_JOB_LOCK:
                _DOC_JOB_PENDING.discard(doc_id)
            _DOC_JOB_QUEUE.task_done()


def _ensure_doc_job_worker() -> None:
    global _DOC_JOB_WORKER_STARTED
    with _DOC_JOB_LOCK:
        if _DOC_JOB_WORKER_STARTED:
            return
        _DOC_JOB_WORKER_STARTED = True
    thread = threading.Thread(target=_doc_job_worker, name="document-job-worker", daemon=True)
    thread.start()
    logger.info("문서 처리 워커를 시작했습니다 (순차 큐).")


def _enqueue_document_job(doc_id: int, *, old_path: str | None = None) -> None:
    """문서 추출·인덱싱 작업을 FIFO 큐에 넣습니다. 이미 대기 중이면 중복 등록하지 않습니다."""
    _ensure_doc_job_worker()
    with _DOC_JOB_LOCK:
        if doc_id in _DOC_JOB_PENDING:
            logger.info("이미 대기열에 있어 건너뜁니다: doc_id=%s", doc_id)
            return
        _DOC_JOB_PENDING.add(doc_id)
    _DOC_JOB_QUEUE.put((doc_id, old_path))
    logger.info(
        "문서 작업 대기열에 추가: doc_id=%s (대기 %s건)",
        doc_id,
        _DOC_JOB_QUEUE.qsize(),
    )

def requeue_interrupted_jobs() -> None:
    """서버가 작업 도중 재시작되면 processing 으로 남은 문서를 다시 큐에 넣습니다.

    이대로 두면 재인덱싱 요청이 409로 계속 막혀 손을 쓸 수 없게 됩니다.
    """
    db = SessionLocal()
    try:
        stuck = db.query(UploadedDocument).filter(UploadedDocument.status == "processing").all()
        for doc in stuck:
            logger.info("중단된 문서 작업을 다시 대기열에 넣습니다: doc_id=%s", doc.id)
            _enqueue_document_job(doc.id)
    except Exception:  # noqa: BLE001
        logger.exception("중단된 문서 작업 복구 실패")
    finally:
        db.close()


SUPPORTED_EXTENSIONS = (
    ".pdf",
    ".txt",
    ".md",
    ".docx",
    ".xlsx",
    ".xls",
    ".hwp",
    ".hwpx",
)
CATEGORIES = ["모집요강", "입학처 공지", "회의록", "재무현황", "예산·행정 규정", "문서 양식"]
DOC_STATUSES = ("latest", "needs_update", "upload_error", "processing")
MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".hwp": "application/x-hwp",
    ".hwpx": "application/hwp+zip",
}


class DocumentMetaUpdate(BaseModel):
    title: str | None = None
    category: str | None = None
    version: str | None = None
    description: str | None = None
    applied_date: str | None = None
    status: str | None = Field(
        default=None, description="latest|needs_update|upload_error|processing"
    )


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
    if lower.endswith((".hwp", ".hwpx")):
        return "hwp"
    return "text"


def _prepare_upload_bytes(original_name: str, content: bytes) -> tuple[str, bytes, str]:
    """저장할 파일명·바이트·doc_type을 준비합니다. HWP는 PDF로 바꿉니다."""
    if is_hwp_filename(original_name):
        try:
            pdf_bytes = convert_hwp_to_pdf(original_name, content)
        except Exception as exc:  # noqa: BLE001
            logger.exception("HWP→PDF 변환 실패: %s", original_name)
            raise HTTPException(
                status_code=422,
                detail=(
                    f"HWP 파일을 PDF로 변환하지 못했습니다: {exc}. "
                    "macOS에서는 ./scripts/setup_hancom_hwp_pdf.sh 로 한컴 자동화를 "
                    "켜거나, LibreOffice 설치 후 다시 시도하거나 HWPX/PDF로 올려 주세요."
                ),
            ) from exc
        stored_name = f"{Path(original_name).stem}.pdf"
        return stored_name, pdf_bytes, "pdf"
    return original_name, content, _doc_type(original_name)


def _chunk_count(db: Session, doc_id: int) -> int:
    return db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).count()


def _to_out(
    doc: UploadedDocument,
    rag_chunk_count: int = 0,
    *,
    replaced: bool = False,
    warning: str | None = None,
) -> DocumentOut:
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
        replaced=replaced,
        warning=warning,
    )


def _parse_date(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _get_doc(db: Session, doc_id: int) -> UploadedDocument:
    doc = db.get(UploadedDocument, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="자료를 찾을 수 없습니다.")
    return doc


def _display_name(title: str | None, original_name: str) -> str:
    display_name = (title or "").strip() or original_name
    if "." not in display_name and "." in original_name:
        display_name = f"{display_name}{Path(original_name).suffix}"
    return display_name


def _norm_stem(name: str) -> str:
    return Path(name or "").stem.strip().lower()


def _bump_version(version: str | None) -> str:
    raw = (version or "V1.0").strip() or "V1.0"
    match = re.match(r"^[Vv]?(\d+)\.(\d+)$", raw)
    if match:
        return f"V{int(match.group(1))}.{int(match.group(2)) + 1}"
    match = re.match(r"^[Vv]?(\d+)$", raw)
    if match:
        return f"V{int(match.group(1))}.1"
    return "V1.1"


def _find_same_name(
    db: Session,
    *,
    display_name: str,
    category: str,
) -> UploadedDocument | None:
    """같은 카테고리에서 자료명(확장자 무시)이 같은 기존 문서를 찾습니다."""
    target = _norm_stem(display_name)
    if not target:
        return None
    rows = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.category == category)
        .order_by(UploadedDocument.updated_at.desc(), UploadedDocument.id.desc())
        .all()
    )
    for row in rows:
        if _norm_stem(row.filename or "") == target:
            return row
    return None


def _unique_dest(upload_dir: Path, original_name: str) -> Path:
    dest_path = upload_dir / original_name
    if not dest_path.exists():
        return dest_path
    stem = Path(original_name).stem
    ext = Path(original_name).suffix
    return upload_dir / f"{stem}_{now_kst().strftime('%Y%m%d%H%M%S')}{ext}"


def _clear_chunks(db: Session, doc_id: int) -> None:
    db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
    db.commit()


def _mark_processing(doc: UploadedDocument) -> None:
    """작업 시작 표시. 상단 집계가 흔들리지 않게 직전 상태를 남겨 둡니다."""
    if doc.status != "processing":
        doc.prev_status = doc.status or "latest"
    doc.status = "processing"
    doc.updated_at = now_kst()


def _effective_status(doc: UploadedDocument) -> str:
    """집계용 상태. 처리 중이면 직전 상태로 셉니다."""
    status = doc.status or "latest"
    if status == "processing":
        return doc.prev_status or "latest"
    return status


def _mark_upload_error(db: Session, doc: UploadedDocument) -> None:
    doc.status = "upload_error"
    doc.prev_status = None
    doc.updated_at = now_kst()
    db.commit()
    db.refresh(doc)


def _run_ingest(
    db: Session,
    doc: UploadedDocument,
    text: str,
    *,
    final_status: str = "latest",
) -> int:
    _clear_chunks(db, doc.id)
    if not text.strip():
        _mark_upload_error(db, doc)
        raise HTTPException(
            status_code=422,
            detail=(
                "파일은 등록됐으나 텍스트를 추출하지 못해 RAG 인덱싱에 실패했습니다. "
                "텍스트가 있는 PDF/DOCX/MD로 다시 업로드하거나 스캔본이면 AI OCR이 "
                "가능한지(OpenAI API 키) 확인해 주세요."
            ),
        )
    try:
        rag_chunks = ingest_document(db, doc, text)
    except Exception as exc:  # noqa: BLE001
        _mark_upload_error(db, doc)
        raise HTTPException(
            status_code=500,
            detail=f"DB 등록은 됐으나 RAG 임베딩 중 오류가 발생했습니다: {exc}",
        ) from exc
    if rag_chunks <= 0:
        _mark_upload_error(db, doc)
        raise HTTPException(
            status_code=500,
            detail=(
                "DB 등록은 됐으나 RAG 임베딩 청크가 생성되지 않았습니다. "
                "OpenAI API 키·임베딩 설정을 확인해 주세요."
            ),
        )
    doc.status = final_status
    doc.prev_status = None
    doc.updated_at = now_kst()
    db.commit()
    db.refresh(doc)
    return rag_chunks


def _delete_stored_file(path_str: str | None) -> None:
    if not path_str:
        return
    path = Path(path_str)
    if not path.exists() or not path.is_file():
        return
    settings = get_settings()
    upload_root = Path(settings.upload_dir).resolve()
    try:
        resolved = path.resolve()
        if upload_root in resolved.parents or resolved.parent == upload_root:
            resolved.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def _extract_and_summarize(
    original_name: str,
    content: bytes,
) -> tuple[ExtractionResult, str | None]:
    extraction = extract_document(original_name, content)
    summary = (
        summarize_document(original_name, extraction.text) if extraction.text.strip() else None
    )
    return extraction, summary


def _ingest_status(extraction: ExtractionResult) -> str:
    """OCR이 실패해 AI 정리로 넘어갔으면 담당자 확인이 필요한 상태로 둡니다."""
    return "needs_update" if extraction.degraded else "latest"


def _process_document_job(doc_id: int, *, old_path: str | None = None) -> None:
    """추출·OCR·임베딩은 수 분이 걸릴 수 있어 요청과 분리해 백그라운드에서 처리합니다.

    진행 상황은 문서 status(processing → latest|needs_update|upload_error)로 확인합니다.
    """
    db = SessionLocal()
    try:
        doc = db.get(UploadedDocument, doc_id)
        if doc is None:
            return
        path = Path(doc.stored_path) if doc.stored_path else None
        if not path or not path.exists():
            _mark_upload_error(db, doc)
            return
        try:
            extraction, summary = _extract_and_summarize(path.name, path.read_bytes())
        except Exception:  # noqa: BLE001
            logger.exception("문서 추출에 실패했습니다: doc_id=%s", doc_id)
            _mark_upload_error(db, doc)
            return
        doc.summary = summary
        db.commit()
        try:
            _run_ingest(db, doc, extraction.text, final_status=_ingest_status(extraction))
        except HTTPException:
            # _run_ingest가 이미 upload_error로 표시했습니다.
            logger.warning("RAG 인덱싱에 실패했습니다: doc_id=%s", doc_id)
    except Exception:  # noqa: BLE001
        logger.exception("문서 처리 작업이 예외로 종료됐습니다: doc_id=%s", doc_id)
        try:
            doc = db.get(UploadedDocument, doc_id)
            if doc is not None and doc.status == "processing":
                _mark_upload_error(db, doc)
        except Exception:  # noqa: BLE001
            logger.exception("upload_error 표시에도 실패했습니다: doc_id=%s", doc_id)
    finally:
        if old_path:
            try:
                current = db.get(UploadedDocument, doc_id)
                if current is None or old_path != current.stored_path:
                    _delete_stored_file(old_path)
            except Exception:  # noqa: BLE001
                logger.exception("이전 파일 정리에 실패했습니다: %s", old_path)
        db.close()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
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
    # 처리 중인 문서는 직전 상태로 세서, 재인덱싱 동안 상단 숫자가 흔들리지 않게 합니다.
    effective = [_effective_status(d) for d in all_docs]
    counts = {
        "total": len(all_docs),
        "latest": sum(1 for s in effective if s == "latest"),
        "needs_update": sum(1 for s in effective if s == "needs_update"),
        "upload_error": sum(1 for s in effective if s == "upload_error"),
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


class TitleSuggestOut(BaseModel):
    title: str
    source: str = "ai"


@router.post("/suggest-title", response_model=TitleSuggestOut)
async def suggest_title(file: UploadFile = File(...)):
    """업로드 전에 자료명을 빠르게 추천합니다. OCR·인덱싱은 하지 않습니다."""
    original_name = file.filename or "upload.bin"
    suffix = Path(original_name).suffix.lower()
    if suffix and suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 형식입니다. 허용: {', '.join(SUPPORTED_EXTENSIONS)}",
        )
    raw = await file.read()
    # 제목만 뽑을 때는 용량을 제한해 응답 지연을 줄입니다(앞 8MB면 충분).
    # 단, HWP/HWPX는 OLE/ZIP 중앙 디렉터리가 파일 끝에 있어 자르면 열리지 않습니다.
    snippet_bytes = raw if is_hwp_filename(original_name) else raw[: 8 * 1024 * 1024]
    title = suggest_document_title(original_name, snippet_bytes)
    return TitleSuggestOut(title=title, source="ai")


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id)
    return _to_out(doc, _chunk_count(db, doc.id))


@router.get("/{doc_id}/file")
def get_document_file(
    doc_id: int,
    download: bool = Query(False),
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, doc_id)
    path = Path(doc.stored_path) if doc.stored_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="원본 파일을 찾을 수 없습니다.")
    suffix = path.suffix.lower()
    media = MEDIA_TYPES.get(suffix, "application/octet-stream")
    headers = {"Cache-Control": "private, max-age=120"}
    if download:
        return FileResponse(
            path,
            media_type=media,
            filename=doc.filename or path.name,
            headers=headers,
        )
    return FileResponse(
        path,
        media_type=media,
        headers={**headers, "Content-Disposition": "inline"},
    )


@router.post("/upload", response_model=DocumentOut, status_code=202)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str = Form("예산·행정 규정"),
    version: str = Form("V1.0"),
    description: str | None = Form(None),
    applied_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """파일 저장 → DB 등록까지 처리하고 즉시 응답합니다.

    텍스트 추출·요약·RAG 인덱싱은 백그라운드에서 이어지며, 진행 상황은 status로 확인합니다.
    같은 카테고리에 동일 자료명이 있으면 파일을 덮어쓰고 버전을 V1.1, V1.2…로 올립니다.
    """
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

    raw = await file.read()
    stored_name, payload, doc_type = _prepare_upload_bytes(original_name, raw)

    display_name = _display_name(title, original_name)
    # HWP는 PDF로 저장하지만 자료명 확장자는 사용자가 준 제목(또는 원본 stem)을 유지합니다.
    if is_hwp_filename(original_name) and display_name.lower().endswith((".hwp", ".hwpx")):
        display_name = f"{Path(display_name).stem}.pdf"
    category_value = category or "기타"
    existing = _find_same_name(db, display_name=display_name, category=category_value)

    dest_path = _unique_dest(upload_dir, stored_name)
    dest_path.write_bytes(payload)

    now = now_kst()
    if existing:
        old_path = existing.stored_path
        existing.filename = display_name
        existing.stored_path = str(dest_path.resolve())
        existing.doc_type = doc_type
        existing.source = "upload"
        existing.version = _bump_version(existing.version)
        _mark_processing(existing)
        if description is not None:
            existing.description = description.strip() or None
        parsed_date = _parse_date(applied_date)
        if parsed_date is not None:
            existing.applied_date = parsed_date
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        background.add_task(_enqueue_document_job, existing.id, old_path=old_path)
        return _to_out(existing, _chunk_count(db, existing.id), replaced=True)

    doc = UploadedDocument(
        filename=display_name,
        stored_path=str(dest_path.resolve()),
        doc_type=doc_type,
        summary=None,
        source="upload",
        category=category_value,
        version=(version or "V1.0").strip() or "V1.0",
        status="processing",
        prev_status="latest",
        description=(description or "").strip() or None,
        applied_date=_parse_date(applied_date),
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(_enqueue_document_job, doc.id)
    return _to_out(doc, 0)


@router.patch("/{doc_id}", response_model=DocumentOut)
def update_document_meta(
    doc_id: int,
    payload: DocumentMetaUpdate,
    db: Session = Depends(get_db),
):
    doc = _get_doc(db, doc_id)
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="자료명을 입력하세요.")
        doc.filename = _display_name(title, doc.filename)
    if payload.category is not None:
        doc.category = payload.category.strip() or doc.category
    if payload.version is not None:
        doc.version = payload.version.strip() or doc.version
    if payload.description is not None:
        doc.description = payload.description.strip() or None
    if payload.applied_date is not None:
        doc.applied_date = _parse_date(payload.applied_date)
    if payload.status is not None:
        if payload.status not in DOC_STATUSES:
            raise HTTPException(status_code=422, detail="유효하지 않은 상태입니다.")
        if doc.status == "processing" and payload.status != "processing":
            # 처리 중인 문서의 상태를 직접 바꾸면 기억해 둔 직전 상태는 의미가 없습니다.
            doc.prev_status = None
        doc.status = payload.status
    doc.updated_at = now_kst()
    db.commit()
    db.refresh(doc)
    return _to_out(doc, _chunk_count(db, doc.id))


@router.post("/{doc_id}/replace", response_model=DocumentOut, status_code=202)
async def replace_document_file(
    doc_id: int,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    version: str | None = Form(None),
    description: str | None = Form(None),
    applied_date: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """기존 자료의 파일을 교체합니다. RAG 재인덱싱은 백그라운드에서 이어집니다."""
    doc = _get_doc(db, doc_id)
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

    raw = await file.read()
    stored_name, payload, doc_type = _prepare_upload_bytes(original_name, raw)

    dest_path = _unique_dest(upload_dir, stored_name)
    dest_path.write_bytes(payload)

    old_path = doc.stored_path
    doc.stored_path = str(dest_path.resolve())
    doc.doc_type = doc_type
    _mark_processing(doc)
    if title is not None and title.strip():
        display = _display_name(title, original_name)
        if is_hwp_filename(original_name) and display.lower().endswith((".hwp", ".hwpx")):
            display = f"{Path(display).stem}.pdf"
        doc.filename = display
    if version is not None and version.strip():
        doc.version = version.strip()
    else:
        doc.version = _bump_version(doc.version)
    if description is not None:
        doc.description = description.strip() or None
    if applied_date is not None:
        doc.applied_date = _parse_date(applied_date)
    doc.updated_at = now_kst()
    db.commit()
    db.refresh(doc)

    background.add_task(_enqueue_document_job, doc.id, old_path=old_path)
    return _to_out(doc, _chunk_count(db, doc.id))


@router.post("/{doc_id}/reindex", response_model=DocumentOut, status_code=202)
def reindex_document(
    doc_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """재인덱싱을 대기열에 넣고 즉시 응답합니다. 작업은 서버에서 순차 처리됩니다."""
    doc = _get_doc(db, doc_id)
    path = Path(doc.stored_path) if doc.stored_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="원본 파일을 찾을 수 없습니다.")
    if doc.status == "processing":
        raise HTTPException(status_code=409, detail="이미 재인덱싱이 진행 중이거나 대기열에 있습니다.")

    _mark_processing(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(_enqueue_document_job, doc_id)
    return _to_out(doc, _chunk_count(db, doc.id))


@router.delete("/{doc_id}")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = _get_doc(db, doc_id)
    path = doc.stored_path
    db.delete(doc)
    db.commit()
    _delete_stored_file(path)
    return {"ok": True}


@router.post("/ingest-data-folder", response_model=IngestResult)
def ingest_data_folder(db: Session = Depends(get_db)):
    """data/ 폴더 내 새 문서를 찾아 변환·요약·임베딩까지 자동으로 처리합니다."""
    settings = get_settings()
    data_dir = Path(settings.data_dir).resolve()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    if not data_dir.exists():
        raise HTTPException(status_code=404, detail=f"데이터 폴더를 찾을 수 없습니다: {data_dir}")

    seed_guideline_documents(db)

    existing_paths = {doc.stored_path for doc in db.query(UploadedDocument).all()}
    existing_names = {doc.filename for doc in db.query(UploadedDocument).all()}
    existing_stems = {_norm_stem(doc.filename) for doc in db.query(UploadedDocument).all()}

    ingested: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for path in sorted(data_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.name.upper() == "README.MD":
            continue
        if (
            str(path) in existing_paths
            or path.name in existing_names
            or _norm_stem(path.name) in existing_stems
        ):
            skipped.append(path.name)
            continue

        try:
            content = path.read_bytes()
            stored_name, payload, doc_type = _prepare_upload_bytes(path.name, content)
            stored_path = path.resolve()
            display_name = path.name
            # HWP/HWPX도 사용자 업로드와 동일하게 PDF를 저장하고 이후 파이프라인은
            # 오직 PDF만 다루게 합니다. 원본 data 파일은 그대로 보존합니다.
            if is_hwp_filename(path.name):
                converted_path = _unique_dest(upload_dir, stored_name)
                converted_path.write_bytes(payload)
                stored_path = converted_path.resolve()
                display_name = stored_name

            extraction, summary = _extract_and_summarize(stored_name, payload)
            text = extraction.text

            now = datetime.fromtimestamp(path.stat().st_mtime)
            doc = UploadedDocument(
                filename=display_name,
                stored_path=str(stored_path),
                doc_type=doc_type,
                summary=summary,
                source="data_folder",
                category="기타",
                version="V1.0",
                status="processing",
                prev_status="latest",
                created_at=now,
                updated_at=now,
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)

            if not text.strip():
                doc.status = "upload_error"
                db.commit()
                failed.append(path.name)
                continue

            chunks = ingest_document(db, doc, text)
            if chunks <= 0:
                doc.status = "upload_error"
                db.commit()
                failed.append(path.name)
                continue

            doc.status = _ingest_status(extraction)
            db.commit()
            ingested.append(display_name)
        except Exception:  # noqa: BLE001
            db.rollback()
            failed.append(path.name)

    return IngestResult(ingested=ingested, skipped=skipped, failed=failed)
