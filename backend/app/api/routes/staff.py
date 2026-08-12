from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import StaffPerson

router = APIRouter(prefix="/api/staff", tags=["staff"])


class StaffCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class StaffOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


def _normalize_name(name: str) -> str:
    return " ".join(name.split()).strip()


@router.get("", response_model=list[StaffOut])
@router.get("/", response_model=list[StaffOut], include_in_schema=False)
def list_staff(db: Session = Depends(get_db)):
    return (
        db.query(StaffPerson)
        .order_by(StaffPerson.name.asc())
        .all()
    )


@router.post("", response_model=StaffOut)
@router.post("/", response_model=StaffOut, include_in_schema=False)
def create_staff(payload: StaffCreate, db: Session = Depends(get_db)):
    name = _normalize_name(payload.name)
    if not name:
        raise HTTPException(status_code=422, detail="이름을 입력해주세요.")

    existing = db.query(StaffPerson).filter(StaffPerson.name == name).first()
    if existing:
        return existing

    person = StaffPerson(name=name)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{staff_id}", response_model=dict)
def delete_staff(staff_id: int, db: Session = Depends(get_db)):
    person = db.get(StaffPerson, staff_id)
    if not person:
        raise HTTPException(status_code=404, detail="담당자를 찾을 수 없습니다.")
    db.delete(person)
    db.commit()
    return {"ok": True, "id": staff_id}


def upsert_staff_names(db: Session, names: list[str]) -> None:
    """계획서 저장 시 담당자 이름을 이력에 반영합니다."""
    for raw in names:
        name = _normalize_name(raw)
        if not name:
            continue
        exists = db.query(StaffPerson).filter(StaffPerson.name == name).first()
        if not exists:
            db.add(StaffPerson(name=name))
    db.commit()
