import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.db.database import get_db
from app.db.models import Inquiry, UploadedDocument
from app.schemas.inquiry import (
    InquiryCreateRequest,
    InquiryFeedbackOut,
    InquiryFeedbackRequest,
    InquiryListResponse,
    InquiryOut,
    InquiryUpdateRequest,
    ReferenceDocOut,
)
from app.services.inquiry_service import (
    add_activity,
    generate_draft_feedback,
    generate_inquiry_draft,
    inquiry_to_dict,
    mask_pii,
)

router = APIRouter(prefix="/api/inquiry", tags=["inquiry"])


def _out(inquiry: Inquiry) -> InquiryOut:
    return InquiryOut(**inquiry_to_dict(inquiry))


@router.get("/references", response_model=list[ReferenceDocOut])
def list_reference_docs(db: Session = Depends(get_db)):
    """답변 생성 전 확인용 규정·자료 목록."""
    rows = (
        db.query(UploadedDocument)
        .order_by(UploadedDocument.updated_at.desc(), UploadedDocument.created_at.desc())
        .all()
    )
    return [
        ReferenceDocOut(
            id=d.id,
            filename=d.filename,
            category=getattr(d, "category", None) or "기타",
            updated_at=getattr(d, "updated_at", None) or d.created_at,
            created_at=d.created_at,
        )
        for d in rows
    ]


@router.get("", response_model=InquiryListResponse)
def list_inquiries(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    q = db.query(Inquiry)
    total = q.count()
    rows = (
        q.options(joinedload(Inquiry.activities))
        .order_by(Inquiry.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return InquiryListResponse(
        items=[_out(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{inquiry_id}", response_model=InquiryOut)
def get_inquiry(inquiry_id: int, db: Session = Depends(get_db)):
    inquiry = (
        db.query(Inquiry)
        .options(joinedload(Inquiry.activities))
        .filter(Inquiry.id == inquiry_id)
        .first()
    )
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    return _out(inquiry)


@router.post("/generate", response_model=InquiryOut)
def generate_inquiry(payload: InquiryCreateRequest, db: Session = Depends(get_db)):
    """문의 저장 + RAG/LLM 초안 생성."""
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="문의 내용을 입력하세요.")

    masked = mask_pii(content)
    inquiry = Inquiry(
        academic_year=payload.academic_year.replace("학년도", "").strip() or "2027",
        admission_type=payload.admission_type or "수시모집",
        selection_type=payload.selection_type or "",
        asker_type=payload.asker_type if payload.asker_type in ("학생", "학부모") else "학생",
        content=content,
        masked_content=masked,
        status="pending",
        selected_document_ids_json=json.dumps(payload.document_ids or [], ensure_ascii=False),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    add_activity(db, inquiry, "문의 접수")
    db.commit()

    try:
        inquiry = generate_inquiry_draft(db, inquiry, document_ids=payload.document_ids or None)
    except Exception as exc:  # noqa: BLE001
        inquiry.status = "pending"
        add_activity(db, inquiry, f"답변 생성 실패: {exc}")
        db.commit()
        raise HTTPException(status_code=500, detail=f"답변 생성 중 오류: {exc}") from exc

    inquiry = (
        db.query(Inquiry)
        .options(joinedload(Inquiry.activities))
        .filter(Inquiry.id == inquiry.id)
        .first()
    )
    return _out(inquiry)


@router.post("/{inquiry_id}/regenerate", response_model=InquiryOut)
def regenerate_inquiry(inquiry_id: int, db: Session = Depends(get_db)):
    inquiry = db.get(Inquiry, inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    try:
        inquiry = generate_inquiry_draft(db, inquiry)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"다시 생성 중 오류: {exc}") from exc
    inquiry = (
        db.query(Inquiry)
        .options(joinedload(Inquiry.activities))
        .filter(Inquiry.id == inquiry_id)
        .first()
    )
    return _out(inquiry)


@router.post("/{inquiry_id}/feedback", response_model=InquiryFeedbackOut)
def feedback_inquiry(
    inquiry_id: int,
    payload: InquiryFeedbackRequest,
    db: Session = Depends(get_db),
):
    """담당자가 수정한 초안에 대해, 변경된 부분만 AI 피드백."""
    inquiry = db.get(Inquiry, inquiry_id)
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    original = (getattr(inquiry, "ai_draft_answer", None) or inquiry.draft_answer or "").strip()
    modified = (payload.draft_answer or "").strip()
    if not original:
        raise HTTPException(status_code=400, detail="비교할 AI 원본 초안이 없습니다.")
    if original == modified:
        raise HTTPException(status_code=400, detail="수정된 내용이 없습니다. 초안을 수정한 뒤 다시 시도해 주세요.")

    try:
        feedback = generate_draft_feedback(
            question=inquiry.content,
            original_draft=original,
            modified_draft=modified,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"피드백 생성 중 오류: {exc}") from exc

    add_activity(db, inquiry, "AI 피드백 요청")
    db.commit()

    return InquiryFeedbackOut(feedback=feedback, has_changes=True)


@router.patch("/{inquiry_id}", response_model=InquiryOut)
def update_inquiry(inquiry_id: int, payload: InquiryUpdateRequest, db: Session = Depends(get_db)):
    inquiry = (
        db.query(Inquiry)
        .options(joinedload(Inquiry.activities))
        .filter(Inquiry.id == inquiry_id)
        .first()
    )
    if not inquiry:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")

    if payload.draft_answer is not None:
        inquiry.draft_answer = payload.draft_answer
        add_activity(db, inquiry, "답변 초안 수정·임시 저장")
    if payload.status is not None:
        if payload.status not in ("completed", "reviewed", "pending", "generating"):
            raise HTTPException(status_code=400, detail="잘못된 상태입니다.")
        inquiry.status = payload.status
        if payload.status == "reviewed":
            add_activity(db, inquiry, "검토 완료")
    inquiry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(inquiry)
    return _out(inquiry)
