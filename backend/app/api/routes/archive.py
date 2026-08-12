"""문서 보관함 API — 행정문서 작성으로 생성된 파일 관리."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import archive_service as svc

router = APIRouter(prefix="/api/archive", tags=["archive"])


class StatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(draft|review|approved|archived)$")
    modifier: str = "입학팀 담당자"


@router.get("")
def list_archive(
    q: str | None = None,
    status: str | None = Query(None, description="draft|review|approved|archived|all"),
    doc_type: str | None = None,
    admission_category: str | None = None,
    academic_year: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    def parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", ""))
        except ValueError:
            return None

    return svc.list_documents(
        db,
        q=q,
        status=status,
        doc_type=doc_type,
        admission_category=admission_category,
        academic_year=academic_year,
        date_from=parse_dt(date_from),
        date_to=parse_dt(date_to),
        page=page,
        page_size=page_size,
    )


@router.get("/{doc_id}")
def get_archive_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    return svc.serialize_doc(doc)


@router.patch("/{doc_id}/status")
def patch_status(doc_id: int, payload: StatusUpdate, db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    updated = svc.update_status(db, doc, payload.status, modifier=payload.modifier)
    return svc.serialize_doc(updated)


@router.post("/{doc_id}/duplicate")
def duplicate(doc_id: int, db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    clone = svc.duplicate_document(db, doc)
    return svc.serialize_doc(clone)


@router.delete("/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    doc = svc.get_document(db, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다.")
    svc.delete_document(db, doc)
    return {"ok": True}
