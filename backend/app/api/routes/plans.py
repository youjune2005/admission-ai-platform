import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import BriefingPlan
from app.api.routes.staff import upsert_staff_names
from app.services.archive_service import upsert_generated_document
from app.services.briefing_plan_service import generate_briefing_plan_pdf

router = APIRouter(prefix="/api/plans", tags=["plans"])


class ProgramItem(BaseModel):
    time: str = ""
    content: str = ""
    owner: str = ""


class BriefingPlanCreate(BaseModel):
    event_name: str
    target: str = ""
    attendees: str = "100"
    schedule: str = ""
    location: str = ""
    department: str = "입학팀"
    budget_limit: str = "2000000"
    budget_items: list[str] = Field(default_factory=list)
    programs: list[ProgramItem] = Field(default_factory=list)


class BriefingPlanOut(BaseModel):
    id: int
    title: str
    status: str
    pdf_url: str | None = None
    preview_url: str | None = None
    payload: dict
    archive_id: int | None = None


def _file_url(path: str | None) -> str | None:
    if not path:
        return None
    name = Path(path).name
    return f"/api/forms/files/{quote(name)}"


@router.post("/briefing", response_model=BriefingPlanOut)
def create_briefing_plan(payload: BriefingPlanCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    title = f"{payload.event_name} 운영계획서"

    plan = BriefingPlan(
        title=title,
        payload_json=json.dumps(data, ensure_ascii=False),
        status="generating",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    owner_names = [p.owner for p in payload.programs if p.owner]
    if payload.department:
        owner_names.append(payload.department)
    try:
        upsert_staff_names(db, owner_names)
    except Exception:  # noqa: BLE001
        pass

    try:
        files = generate_briefing_plan_pdf(
            data,
            filename_stem=f"운영계획서_plan{plan.id}",
        )
        plan.pdf_path = str(files.pdf_path)
        plan.preview_path = str(files.preview_path)
        plan.status = "completed"
        db.commit()
        db.refresh(plan)
    except Exception as exc:  # noqa: BLE001
        plan.status = "failed"
        db.commit()
        raise HTTPException(status_code=422, detail=f"PDF 생성 실패: {exc}") from exc

    archived = upsert_generated_document(
        db,
        title=plan.title,
        source_kind="briefing",
        source_id=plan.id,
        pdf_path=plan.pdf_path,
        preview_path=plan.preview_path,
        payload=data,
        doc_type="계획서",
        admission_category="수시",
        academic_year="2027",
        author=payload.department or "입학팀 담당자",
        status="approved",
    )

    return BriefingPlanOut(
        id=plan.id,
        title=plan.title,
        status=plan.status,
        pdf_url=_file_url(plan.pdf_path),
        preview_url=_file_url(plan.preview_path),
        payload=data,
        archive_id=archived.id,
    )


@router.get("/briefing/{plan_id}", response_model=BriefingPlanOut)
def get_briefing_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = db.get(BriefingPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다.")
    return BriefingPlanOut(
        id=plan.id,
        title=plan.title,
        status=plan.status,
        pdf_url=_file_url(plan.pdf_path),
        preview_url=_file_url(plan.preview_path),
        payload=json.loads(plan.payload_json),
    )
