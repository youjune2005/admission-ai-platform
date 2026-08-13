import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import BriefingPlan, GeneratedDocument
from app.api.routes.staff import upsert_staff_names
from app.services.archive_service import upsert_generated_document
from app.services.briefing_plan_service import generate_briefing_plan_pdf
from app.services.outreach_plan_service import generate_outreach_plan_pdf

router = APIRouter(prefix="/api/plans", tags=["plans"])


class ProgramItem(BaseModel):
    time: str = ""
    content: str = ""
    owner: str = ""


class BudgetLineItem(BaseModel):
    name: str
    basis: str = ""
    unit_price: int = 0
    quantity: int = 1


class BriefingPlanCreate(BaseModel):
    event_name: str
    target: str = ""
    attendees: str = "100"
    schedule: str = ""
    location: str = ""
    department: str = "입학팀"
    budget_limit: str = "2000000"
    budget_items: list[str] = Field(default_factory=list)
    budget_lines: list[BudgetLineItem] = Field(default_factory=list)
    programs: list[ProgramItem] = Field(default_factory=list)
    archive_id: int | None = None


class VisitPlanCreate(BaseModel):
    event_name: str
    school_name: str = ""
    region: str = ""
    target: str = ""
    attendees: str = "50"
    schedule: str = ""
    location: str = ""
    format: str = "오프라인"
    contact_teacher: str = ""
    department: str = "입학팀"
    equipment: str = ""
    materials: str = ""
    notes: str = ""
    programs: list[ProgramItem] = Field(default_factory=list)
    archive_id: int | None = None


class FairPlanCreate(BaseModel):
    event_name: str
    host: str = ""
    booth_no: str = ""
    target: str = ""
    attendees: str = "200"
    schedule: str = ""
    location: str = ""
    staff_count: str = ""
    department: str = "입학팀"
    materials: str = ""
    consulting_focus: str = ""
    notes: str = ""
    programs: list[ProgramItem] = Field(default_factory=list)
    archive_id: int | None = None


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


def _create_plan_record(
    db: Session,
    *,
    title: str,
    data: dict,
    owner_names: list[str],
    source_kind: str,
    filename_stem: str,
    generate,
    author: str,
    existing_id: int | None = None,
) -> BriefingPlanOut:
    if existing_id is not None:
        existing = db.get(GeneratedDocument, existing_id)
        if not existing:
            raise HTTPException(status_code=404, detail="이어서 작성할 문서를 찾을 수 없습니다.")
    plan = BriefingPlan(
        title=title,
        payload_json=json.dumps(data, ensure_ascii=False),
        status="generating",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    try:
        upsert_staff_names(db, owner_names)
    except Exception:  # noqa: BLE001
        pass

    try:
        files = generate(data, filename_stem=f"{filename_stem}_plan{plan.id}")
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
        source_kind=source_kind,
        source_id=plan.id,
        pdf_path=plan.pdf_path,
        preview_path=plan.preview_path,
        payload=data,
        doc_type="계획서",
        admission_category="수시",
        academic_year="2027",
        author=author,
        status="approved",
        existing_id=existing_id,
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


@router.post("/briefing", response_model=BriefingPlanOut)
def create_briefing_plan(payload: BriefingPlanCreate, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude={"archive_id"})
    title = f"{payload.event_name} 운영계획서"
    owners = [p.owner for p in payload.programs if p.owner]
    if payload.department:
        owners.append(payload.department)
    return _create_plan_record(
        db,
        title=title,
        data=data,
        owner_names=owners,
        source_kind="briefing",
        filename_stem="운영계획서",
        generate=generate_briefing_plan_pdf,
        author=payload.department or "입학팀 담당자",
        existing_id=payload.archive_id,
    )


@router.post("/visit", response_model=BriefingPlanOut)
def create_visit_plan(payload: VisitPlanCreate, db: Session = Depends(get_db)):
    data = {**payload.model_dump(exclude={"archive_id"}), "plan_kind": "visit"}
    title = f"{payload.event_name} 홍보계획서"
    owners = [p.owner for p in payload.programs if p.owner]
    if payload.department:
        owners.append(payload.department)
    if payload.contact_teacher:
        owners.append(payload.contact_teacher)
    return _create_plan_record(
        db,
        title=title,
        data=data,
        owner_names=owners,
        source_kind="visit",
        filename_stem="고교방문홍보계획서",
        generate=lambda d, filename_stem: generate_outreach_plan_pdf(
            "visit", d, filename_stem=filename_stem
        ),
        author=payload.department or "입학팀 담당자",
        existing_id=payload.archive_id,
    )


@router.post("/fair", response_model=BriefingPlanOut)
def create_fair_plan(payload: FairPlanCreate, db: Session = Depends(get_db)):
    data = {**payload.model_dump(exclude={"archive_id"}), "plan_kind": "fair"}
    title = f"{payload.event_name} 참가계획서"
    owners = [p.owner for p in payload.programs if p.owner]
    if payload.department:
        owners.append(payload.department)
    return _create_plan_record(
        db,
        title=title,
        data=data,
        owner_names=owners,
        source_kind="fair",
        filename_stem="박람회참가계획서",
        generate=lambda d, filename_stem: generate_outreach_plan_pdf(
            "fair", d, filename_stem=filename_stem
        ),
        author=payload.department or "입학팀 담당자",
        existing_id=payload.archive_id,
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
