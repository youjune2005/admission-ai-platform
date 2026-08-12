"""홈(대시보드) 집계 API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Inquiry, KpiDailySnapshot, UploadedDocument
from app.services.archive_service import list_documents
from app.services.inquiry_analytics_service import aggregate_inquiry_topics, classify_inquiry_topic

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

KST = timezone(timedelta(hours=9))


def _kst_day_str(offset: int = 0) -> str:
    now_kst = datetime.now(KST) + timedelta(days=offset)
    return now_kst.strftime("%Y-%m-%d")


def _day_bounds_utc(day_offset: int = 0) -> tuple[datetime, datetime]:
    """KST 기준 day_offset일(0=오늘)의 UTC naive [start, end) 구간."""
    now_kst = datetime.now(KST)
    start_kst = (now_kst + timedelta(days=day_offset)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end_kst = start_kst + timedelta(days=1)
    start_utc = start_kst.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = end_kst.astimezone(timezone.utc).replace(tzinfo=None)
    return start_utc, end_utc


def _delta_label(delta: int) -> tuple[str, str]:
    if delta > 0:
        return f"어제 대비 +{delta}건", "up"
    if delta < 0:
        return f"어제 대비 {delta}건", "down"
    return "어제 대비 ±0건", "flat"


def _current_kpi_values(db: Session) -> dict[str, int]:
    today_start, today_end = _day_bounds_utc(0)

    today_received = (
        db.query(Inquiry)
        .filter(Inquiry.created_at >= today_start, Inquiry.created_at < today_end)
        .count()
    )
    draft_completed = (
        db.query(Inquiry)
        .filter(Inquiry.status.in_(("completed", "reviewed")))
        .count()
    )
    needs_review = db.query(Inquiry).filter(Inquiry.status == "completed").count()
    regulation_review = (
        db.query(UploadedDocument).filter(UploadedDocument.status == "needs_update").count()
    )
    return {
        "today_received": today_received,
        "draft_completed": draft_completed,
        "needs_review": needs_review,
        "regulation_review": regulation_review,
    }


def _upsert_today_snapshot(db: Session, values: dict[str, int]) -> KpiDailySnapshot:
    day = _kst_day_str(0)
    row = db.query(KpiDailySnapshot).filter(KpiDailySnapshot.day == day).first()
    now = datetime.utcnow()
    if row is None:
        row = KpiDailySnapshot(day=day, created_at=now, updated_at=now)
        db.add(row)
    row.today_received = values["today_received"]
    row.draft_completed = values["draft_completed"]
    row.needs_review = values["needs_review"]
    row.regulation_review = values["regulation_review"]
    row.updated_at = now
    db.commit()
    db.refresh(row)
    return row


def _yesterday_received_count(db: Session) -> int:
    yday_start, yday_end = _day_bounds_utc(-1)
    return (
        db.query(Inquiry)
        .filter(Inquiry.created_at >= yday_start, Inquiry.created_at < yday_end)
        .count()
    )


def _get_yesterday_snapshot(db: Session) -> KpiDailySnapshot | None:
    return (
        db.query(KpiDailySnapshot)
        .filter(KpiDailySnapshot.day == _kst_day_str(-1))
        .first()
    )


def aggregate_home_kpis(db: Session) -> dict:
    """홈 KPI — 현재값 + 일별 스냅샷 로그로 어제 대비 증감."""
    values = _current_kpi_values(db)
    _upsert_today_snapshot(db, values)
    yday = _get_yesterday_snapshot(db)

    # 오늘 접수: 오늘 건수 vs 어제 건수 (실데이터)
    recv_delta = values["today_received"] - _yesterday_received_count(db)

    # 스톡성 지표: 오늘 스냅샷 vs 어제 스냅샷 (어제 로그 없으면 0 기준)
    y_draft = int(yday.draft_completed or 0) if yday else 0
    y_review = int(yday.needs_review or 0) if yday else 0
    y_reg = int(yday.regulation_review or 0) if yday else 0
    draft_delta = values["draft_completed"] - y_draft
    review_delta = values["needs_review"] - y_review
    reg_delta = values["regulation_review"] - y_reg

    items = {
        "today_received": (values["today_received"], recv_delta),
        "draft_completed": (values["draft_completed"], draft_delta),
        "needs_review": (values["needs_review"], review_delta),
        "regulation_review": (values["regulation_review"], reg_delta),
    }
    out: dict = {}
    for key, (value, delta) in items.items():
        label, trend = _delta_label(delta)
        out[key] = {
            "value": value,
            "delta": delta,
            "delta_label": label,
            "trend": trend,
        }
    return out


@router.get("/faq-topics")
def faq_topics(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """입시 문의 유형별 집계 (홈 차트)."""
    return aggregate_inquiry_topics(db, days=days, limit=limit)


@router.post("/classify-topic")
def classify_topic(payload: dict):
    """문의 문장 분류 미리보기."""
    text = str(payload.get("text") or "")
    return {"topic": classify_inquiry_topic(text), "text": text}


def _filename_with_ext(title: str, pdf_url: str | None, source_kind: str) -> str:
    name = (title or "문서").strip()
    if Path(name).suffix:
        return name
    if pdf_url or source_kind in ("briefing", "budget", "report"):
        return f"{name}.pdf"
    return name


@router.get("/home")
def home_summary(db: Session = Depends(get_db)):
    """홈 화면용: KPI + 최근 생성 문서 + 자주 들어오는 문의."""
    archive = list_documents(db, page=1, page_size=5)
    recent_docs = []
    for item in archive["items"]:
        recent_docs.append(
            {
                "id": item["id"],
                "name": _filename_with_ext(
                    item["title"], item.get("pdf_url"), item.get("source_kind") or ""
                ),
                "type": item["doc_type"],
                "updated": item.get("updated_at") or item.get("created_at"),
                "status": item.get("status_label") or item.get("status"),
                "status_key": item.get("status"),
                "pdf_url": item.get("pdf_url"),
            }
        )

    return {
        "kpis": aggregate_home_kpis(db),
        "recent_documents": recent_docs,
        "faq_topics": aggregate_inquiry_topics(db, days=7, limit=6),
    }
