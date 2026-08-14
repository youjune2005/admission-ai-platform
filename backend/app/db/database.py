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


def _migrate_utc_timestamps_to_kst() -> None:
    """기존 UTC naive 시각을 KST(+9h)로 한 번만 보정합니다."""
    if not settings.database_url.startswith("sqlite"):
        return

    shifts: list[tuple[str, tuple[str, ...]]] = [
        ("chat_sessions", ("created_at",)),
        ("chat_messages", ("created_at",)),
        ("workflow_tasks", ("created_at",)),
        ("uploaded_documents", ("created_at", "updated_at")),
        ("inquiries", ("created_at", "updated_at")),
        ("inquiry_activities", ("created_at",)),
        ("kpi_daily_snapshots", ("created_at", "updated_at")),
        ("briefing_plans", ("created_at", "updated_at")),
        ("staff_people", ("created_at",)),
        ("generated_documents", ("created_at", "updated_at", "approved_at", "archived_at")),
    ]

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app_meta ("
                "key VARCHAR(64) PRIMARY KEY, value TEXT)"
            )
        )
        row = conn.execute(
            text("SELECT value FROM app_meta WHERE key = 'timestamps_tz'")
        ).fetchone()
        if row and row[0] == "kst":
            return

        tables = {
            r[0]
            for r in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        for table, columns in shifts:
            if table not in tables:
                continue
            existing = {
                r[1]
                for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for col in columns:
                if col not in existing:
                    continue
                conn.execute(
                    text(
                        f"UPDATE {table} SET {col} = datetime({col}, '+9 hours') "
                        f"WHERE {col} IS NOT NULL"
                    )
                )

        conn.execute(
            text(
                "INSERT INTO app_meta(key, value) VALUES ('timestamps_tz', 'kst') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
        )


def _repair_false_upload_errors() -> None:
    """청크가 남아 있는데 upload_error로 굳어 버린 문서를 한 번만 되돌립니다.

    이전 버전은 기동할 때마다 needs_update 업로드를 upload_error로 덮어써서,
    OCR 품질만 낮았을 뿐 정상 인덱싱된 자료까지 오류로 표시됐습니다.
    """
    if not settings.database_url.startswith("sqlite"):
        return

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app_meta ("
                "key VARCHAR(64) PRIMARY KEY, value TEXT)"
            )
        )
        row = conn.execute(
            text("SELECT value FROM app_meta WHERE key = 'upload_error_repair'")
        ).fetchone()
        if row and row[0] == "done":
            return

        conn.execute(
            text(
                "UPDATE uploaded_documents SET status = 'needs_update' "
                "WHERE status = 'upload_error' AND id IN ("
                "SELECT DISTINCT document_id FROM document_chunks)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO app_meta(key, value) VALUES ('upload_error_repair', 'done') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
        )


def init_db() -> None:
    from app.db import models  # noqa: F401  (ensure models are registered)

    Base.metadata.create_all(bind=engine)

    # 기존 SQLite DB에 규정·자료 메타 컬럼 추가
    _sqlite_add_column_if_missing("uploaded_documents", "category", "category VARCHAR(50) DEFAULT '기타'")
    _sqlite_add_column_if_missing("uploaded_documents", "version", "version VARCHAR(20) DEFAULT 'V1.0'")
    _sqlite_add_column_if_missing(
        "uploaded_documents", "status", "status VARCHAR(30) DEFAULT 'latest'"
    )
    _sqlite_add_column_if_missing(
        "uploaded_documents", "prev_status", "prev_status VARCHAR(30)"
    )
    _sqlite_add_column_if_missing("uploaded_documents", "description", "description TEXT")
    _sqlite_add_column_if_missing("uploaded_documents", "applied_date", "applied_date DATETIME")
    _sqlite_add_column_if_missing("uploaded_documents", "updated_at", "updated_at DATETIME")
    _sqlite_add_column_if_missing("inquiries", "ai_draft_answer", "ai_draft_answer TEXT")
    _sqlite_add_column_if_missing(
        "inquiries", "excluded_document_ids_json", "excluded_document_ids_json TEXT"
    )
    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE inquiries SET ai_draft_answer = draft_answer "
                    "WHERE ai_draft_answer IS NULL AND draft_answer IS NOT NULL"
                )
            )
            # 규정·자료 카테고리: FAQ → 회의록
            conn.execute(
                text(
                    "UPDATE uploaded_documents SET category = '회의록' "
                    "WHERE category = 'FAQ'"
                )
            )
        _migrate_utc_timestamps_to_kst()
        _repair_false_upload_errors()

    # data/guidelines 시드
    from app.services.archive_service import dedupe_generated_documents
    from app.services.regulation_seed_service import seed_guideline_documents

    db = SessionLocal()
    try:
        seed_guideline_documents(db)
        dedupe_generated_documents(db)
    finally:
        db.close()

    if settings.database_url.startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_generated_documents_source_id "
                    "ON generated_documents(source_id) WHERE source_id IS NOT NULL"
                )
            )
