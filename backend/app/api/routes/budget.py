import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import BriefingPlan, GeneratedDocument
from app.services.archive_service import upsert_generated_document
from app.services.budget_plan_service import generate_budget_statement_pdf, review_budget

router = APIRouter(prefix="/api/budget", tags=["budget"])


class BudgetItemIn(BaseModel):
    name: str = ""
    basis: str = ""
    unit_price: int = 0
    quantity: int = 0
    amount: int | None = None
    status: str | None = None


class BudgetReviewRequest(BaseModel):
    title: str = "예상 예산안"
    allocated_budget: int = 0
    items: list[BudgetItemIn] = Field(default_factory=list)


class BudgetFinalizeRequest(BaseModel):
    title: str = "예상 예산안"
    allocated_budget: int = 0
    items: list[BudgetItemIn] = Field(default_factory=list)
    archive_id: int | None = None


def _normalize_items(items: list[BudgetItemIn]) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        unit = int(item.unit_price or 0)
        qty = int(item.quantity or 0)
        amount = int(item.amount if item.amount is not None else unit * qty)
        rows.append(
            {
                "name": item.name,
                "basis": item.basis,
                "unit_price": unit,
                "quantity": qty,
                "amount": amount,
                "status": item.status,
            }
        )
    return rows


def _file_url(path: str | None) -> str | None:
    if not path:
        return None
    return f"/api/forms/files/{quote(Path(path).name)}"


@router.post("/review")
def review_budget_plan(payload: BudgetReviewRequest, db: Session = Depends(get_db)):
    items = _normalize_items(payload.items)
    if not items:
        raise HTTPException(status_code=422, detail="예산 항목을 1개 이상 입력해주세요.")
    result = review_budget(db, items, int(payload.allocated_budget or 0))
    result["title"] = payload.title
    return result


@router.post("/finalize")
def finalize_budget_plan(payload: BudgetFinalizeRequest, db: Session = Depends(get_db)):
    items = _normalize_items(payload.items)
    if not items:
        raise HTTPException(status_code=422, detail="예산 항목을 1개 이상 입력해주세요.")

    # 저장 레코드 (BriefingPlan 테이블 재사용: type을 payload에 기록)
    if payload.archive_id is not None:
        existing = db.get(GeneratedDocument, payload.archive_id)
        if not existing:
            raise HTTPException(status_code=404, detail="이어서 작성할 문서를 찾을 수 없습니다.")

    record_payload = {
        "type": "budget",
        "title": payload.title,
        "allocated_budget": payload.allocated_budget,
        "items": items,
    }
    plan = BriefingPlan(
        title=payload.title or "예상 예산안",
        payload_json=json.dumps(record_payload, ensure_ascii=False),
        status="generating",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    try:
        files = generate_budget_statement_pdf(
            items,
            title=payload.title or "예상 예산안",
            filename_stem=f"예산안_plan{plan.id}",
            allocated_budget=int(payload.allocated_budget or 0),
        )
        plan.pdf_path = str(files.pdf_path)
        plan.preview_path = str(files.preview_path)
        plan.status = "completed"
        db.commit()
        db.refresh(plan)
    except Exception as exc:  # noqa: BLE001
        plan.status = "failed"
        db.commit()
        raise HTTPException(status_code=422, detail=f"예산안 PDF 생성 실패: {exc}") from exc

    archived = upsert_generated_document(
        db,
        title=plan.title,
        source_kind="budget",
        source_id=plan.id,
        pdf_path=plan.pdf_path,
        preview_path=plan.preview_path,
        payload=record_payload,
        doc_type="예산안",
        admission_category="수시",
        academic_year="2027",
        author="입학팀 담당자",
        status="approved",
        existing_id=payload.archive_id,
    )

    review = review_budget(db, items, int(payload.allocated_budget or 0))
    return {
        "id": plan.id,
        "title": plan.title,
        "status": plan.status,
        "pdf_url": _file_url(plan.pdf_path),
        "preview_url": _file_url(plan.preview_path),
        "archive_id": archived.id,
        "review": review,
    }
