from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.core.config import get_settings
from app.services.form_pdf_service import generate_tuition_statement_files

router = APIRouter(prefix="/api/forms", tags=["forms"])


class TuitionStatementRequest(BaseModel):
    markdown: str
    filename_stem: str | None = None


class TuitionStatementResponse(BaseModel):
    pdf_url: str
    preview_url: str
    filename: str


def _generated_file_path(filename: str) -> Path:
    settings = get_settings()
    path = Path(settings.upload_dir) / "generated" / filename
    if not path.exists() or ".." in filename:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return path


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


@router.post("/tuition-statement", response_model=TuitionStatementResponse)
def create_tuition_statement_pdf(payload: TuitionStatementRequest):
    try:
        files = generate_tuition_statement_files(
            payload.markdown,
            filename_stem=payload.filename_stem,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"PDF 생성 실패: {exc}") from exc
    return TuitionStatementResponse(
        pdf_url=f"/api/forms/files/{quote(files.pdf_path.name)}",
        preview_url=f"/api/forms/files/{quote(files.preview_path.name)}",
        filename=files.pdf_path.name,
    )


@router.get("/files/{filename}")
def download_generated_file(filename: str):
    path = _generated_file_path(filename)
    return FileResponse(
        path,
        media_type=_media_type_for(path),
        filename=filename,
    )


@router.head("/files/{filename}")
def head_generated_file(filename: str):
    path = _generated_file_path(filename)
    stat = path.stat()
    return Response(
        status_code=200,
        media_type=_media_type_for(path),
        headers={
            "content-length": str(stat.st_size),
            "accept-ranges": "bytes",
        },
    )
