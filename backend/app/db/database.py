from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_add_column_if_missing(table: str, column: str, ddl: str) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        existing = {r[1] for r in rows}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def init_db() -> None:
    from app.db import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)

    # 기존 SQLite DB에 규정·자료 메타 컬럼 추가
    _sqlite_add_column_if_missing("uploaded_documents", "category", "category VARCHAR(50) DEFAULT '기타'")
    _sqlite_add_column_if_missing("uploaded_documents", "version", "version VARCHAR(20) DEFAULT 'V1.0'")
    _sqlite_add_column_if_missing(
        "uploaded_documents", "status", "status VARCHAR(30) DEFAULT 'latest'"
    )
    _sqlite_add_column_if_missing("uploaded_documents", "description", "description TEXT")
    _sqlite_add_column_if_missing("uploaded_documents", "applied_date", "applied_date DATETIME")
    _sqlite_add_column_if_missing("uploaded_documents", "updated_at", "updated_at DATETIME")
    _sqlite_add_column_if_missing("inquiries", "ai_draft_answer", "ai_draft_answer TEXT")
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE inquiries SET ai_draft_answer = draft_answer "
                    "WHERE ai_draft_answer IS NULL AND draft_answer IS NOT NULL"
                )
            )

    # data/guidelines 시드
    from app.services.regulation_seed_service import seed_guideline_documents

    db = SessionLocal()
    try:
        seed_guideline_documents(db)
    finally:
        db.close()
