from datetime import datetime

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    id: int
    filename: str
    doc_type: str
    summary: str | None
    source: str
    category: str = "기타"
    version: str = "V1.0"
    status: str = "latest"
    status_label: str = "최신 적용"
    description: str | None = None
    applied_date: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime
    rag_chunk_count: int = 0
    replaced: bool = False
    warning: str | None = None

    model_config = {"from_attributes": True}


class IngestResult(BaseModel):
    ingested: list[str]
    skipped: list[str]
    failed: list[str]


class DocumentUploadMeta(BaseModel):
    title: str | None = None
    category: str = "예산·행정 규정"
    version: str = "V1.0"
    description: str | None = None
    applied_date: str | None = None  # YYYY-MM-DD


class DocumentListResponse(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int
    counts: dict[str, int] = Field(default_factory=dict)
    categories: list[str] = Field(default_factory=list)
