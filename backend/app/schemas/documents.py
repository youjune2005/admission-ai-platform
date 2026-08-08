from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    filename: str
    doc_type: str
    summary: str | None
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IngestResult(BaseModel):
    ingested: list[str]
    skipped: list[str]
    failed: list[str]
