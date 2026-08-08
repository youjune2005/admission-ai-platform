from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    due_date: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    due_date: datetime | None = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: str | None
    status: str
    due_date: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class NoticeDraftRequest(BaseModel):
    topic: str
    audience: str = "지원자"
    tone: str = "공식적이고 정중한"
    key_points: list[str] = []


class NoticeDraftResponse(BaseModel):
    draft: str
