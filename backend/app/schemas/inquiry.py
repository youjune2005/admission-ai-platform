from datetime import datetime

from pydantic import BaseModel, Field


class InquiryCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)
    academic_year: str = "2027"
    admission_type: str = "수시모집"
    selection_type: str = ""
    asker_type: str = "학생"
    document_ids: list[int] = Field(default_factory=list)


class InquiryUpdateRequest(BaseModel):
    draft_answer: str | None = None
    status: str | None = None  # completed | reviewed


class InquiryFeedbackRequest(BaseModel):
    draft_answer: str = Field(..., min_length=1)


class InquiryFeedbackOut(BaseModel):
    feedback: str
    has_changes: bool = True


class InquiryReferenceOut(BaseModel):
    document_id: int
    filename: str
    relevance: int
    score: float = 0.0
    snippet: str = ""
    updated_at: datetime | None = None


class InquiryActivityOut(BaseModel):
    id: int
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InquiryOut(BaseModel):
    id: int
    academic_year: str
    admission_type: str
    selection_type: str
    asker_type: str
    content: str
    masked_content: str | None = None
    draft_answer: str | None = None
    ai_draft_answer: str | None = None
    status: str
    status_label: str
    selected_document_ids: list[int] = Field(default_factory=list)
    references: list[InquiryReferenceOut] = Field(default_factory=list)
    check_notes: list[str] = Field(default_factory=list)
    activities: list[InquiryActivityOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class InquiryListResponse(BaseModel):
    items: list[InquiryOut]
    total: int
    page: int
    page_size: int


class ReferenceDocOut(BaseModel):
    id: int
    filename: str
    category: str
    updated_at: datetime | None = None
    created_at: datetime | None = None
