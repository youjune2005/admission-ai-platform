from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import WorkflowTask
from app.schemas.workflow import (
    NoticeDraftRequest,
    NoticeDraftResponse,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)
from app.services.workflow_service import generate_notice_draft

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(db: Session = Depends(get_db)):
    return db.query(WorkflowTask).order_by(WorkflowTask.created_at.desc()).all()


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)):
    task = WorkflowTask(**payload.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskUpdate, db: Session = Depends(get_db)):
    task = db.get(WorkflowTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = db.get(WorkflowTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    db.delete(task)
    db.commit()
    return {"ok": True}


@router.post("/notice-draft", response_model=NoticeDraftResponse)
def create_notice_draft(payload: NoticeDraftRequest):
    draft = generate_notice_draft(payload)
    return NoticeDraftResponse(draft=draft)
