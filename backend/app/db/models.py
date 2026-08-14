from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now_kst
from app.db.database import Base


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    done = "done"


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), default="새 상담")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("chat_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class WorkflowTask(Base):
    __tablename__ = "workflow_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TaskStatus.todo.value)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)


class UploadedDocument(Base):
    __tablename__ = "uploaded_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    doc_type: Mapped[str] = mapped_column(String(50))  # "csv" | "excel" | "pdf" | "text"
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="upload")  # "upload" | "data_folder"
    # 규정·자료 관리 메타
    category: Mapped[str] = mapped_column(String(50), default="기타")
    version: Mapped[str] = mapped_column(String(20), default="V1.0")
    # latest | needs_update | upload_error | processing
    status: Mapped[str] = mapped_column(String(30), default="latest")
    # processing 중일 때 상단 집계에 쓸 직전 상태. 작업이 끝나면 비웁니다.
    prev_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    applied_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("uploaded_documents.id"))
    chunk_index: Mapped[int] = mapped_column()
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[str] = mapped_column(Text)  # JSON-encoded list[float]

    document: Mapped[UploadedDocument] = relationship(back_populates="chunks")


class Inquiry(Base):
    """입시 문의 답변 (1건 = 문의 + AI 초안)."""

    __tablename__ = "inquiries"

    id: Mapped[int] = mapped_column(primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(20), default="2027")
    admission_type: Mapped[str] = mapped_column(String(40), default="수시모집")
    selection_type: Mapped[str] = mapped_column(String(50), default="")
    asker_type: Mapped[str] = mapped_column(String(20), default="학생")  # 학생 | 학부모
    content: Mapped[str] = mapped_column(Text)
    masked_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # AI가 처음/다시 생성한 원본 초안 (담당자 수정분과 비교용)
    ai_draft_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | generating | completed | reviewed
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    selected_document_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 근거에서 뺄 문서 id. 자료가 많아질수록 포함 목록보다 제외 목록이 관리하기 쉽습니다.
    excluded_document_ids_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    references_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    check_notes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_kst, onupdate=now_kst
    )

    activities: Mapped[list["InquiryActivity"]] = relationship(
        back_populates="inquiry",
        cascade="all, delete-orphan",
        order_by="desc(InquiryActivity.created_at), desc(InquiryActivity.id)",
    )


class InquiryActivity(Base):
    __tablename__ = "inquiry_activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    inquiry_id: Mapped[int] = mapped_column(ForeignKey("inquiries.id"), index=True)
    message: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)

    inquiry: Mapped["Inquiry"] = relationship(back_populates="activities")


class KpiDailySnapshot(Base):
    """홈 KPI 일별 스냅샷 — 어제 대비 증감 계산용 로그."""

    __tablename__ = "kpi_daily_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    # KST 기준 YYYY-MM-DD
    day: Mapped[str] = mapped_column(String(10), unique=True, index=True)
    today_received: Mapped[int] = mapped_column(default=0)
    draft_completed: Mapped[int] = mapped_column(default=0)
    needs_review: Mapped[int] = mapped_column(default=0)
    regulation_review: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_kst, onupdate=now_kst
    )


class BriefingPlan(Base):
    """입시설명회 운영계획서 작성 입력값 및 생성 결과."""

    __tablename__ = "briefing_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    payload_json: Mapped[str] = mapped_column(Text)  # JSON
    status: Mapped[str] = mapped_column(String(30), default="draft")
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_kst, onupdate=now_kst
    )


class StaffPerson(Base):
    """운영계획서 등에서 사용한 담당자 이름 이력."""

    __tablename__ = "staff_people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)


class GeneratedDocument(Base):
    """행정문서 작성으로 생성된 문서 보관함 레코드."""

    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    # briefing | budget | visit | fair | interview | report | other
    source_kind: Mapped[str] = mapped_column(String(40), default="other", index=True)
    source_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    # 계획서 | 예산안 | 안내문 | FAQ | 보고서 등
    doc_type: Mapped[str] = mapped_column(String(50), default="계획서")
    # 수시 | 정시 | 기타
    admission_category: Mapped[str] = mapped_column(String(40), default="수시")
    academic_year: Mapped[str] = mapped_column(String(20), default="2027")
    author: Mapped[str] = mapped_column(String(100), default="입학팀 담당자")
    last_modifier: Mapped[str] = mapped_column(String(100), default="입학팀 담당자")
    # draft | review | approved | archived
    status: Mapped[str] = mapped_column(String(30), default="approved", index=True)
    version: Mapped[str] = mapped_column(String(20), default="v1.0")
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    preview_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archive_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_kst)
