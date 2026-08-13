"""행정문서 작성 중 내용 정합성·규정 RAG 검토 API."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services.document_review_service import (
    check_content_consistency,
    review_plan_regulations,
)

router = APIRouter(prefix="/api/plans/review", tags=["plan-review"])

DocKind = Literal["briefing", "visit", "fair", "budget"]


class ReviewRequest(BaseModel):
    kind: DocKind
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/consistency")
def review_consistency(body: ReviewRequest):
    return check_content_consistency(body.kind, body.payload)


@router.post("/regulations")
def review_regulations(body: ReviewRequest, db: Session = Depends(get_db)):
    return review_plan_regulations(db, body.kind, body.payload)
