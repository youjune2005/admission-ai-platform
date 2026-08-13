"""보관함 저장 요청에 붙는 공통 필드. 문서 본문 JSON에는 넣지 않습니다."""

from pydantic import BaseModel

ARCHIVE_WRITE_EXCLUDE = {"archive_id", "archive_status", "regulation_summary"}


class ArchiveWriteMixin(BaseModel):
    archive_id: int | None = None
    archive_status: str | None = None
    regulation_summary: dict | None = None
