"""입시 문의 → 유형 분류 및 대시보드(자주 들어오는 문의) 집계.

홈 차트는 입시 문의 답변(`/api/inquiry`)에 등록된 Inquiry만 집계합니다.
구 챗봇 ChatMessage는 포함하지 않습니다.
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.timeutil import now_kst
from app.db.models import Inquiry

# 핵심 키워드 → 유형 (우선순위 높은 순)
TOPIC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("수능최저학력기준", ("수능최저", "최저학력", "최저 기준", "수능 최저", "등급합")),
    ("학생부 반영방법", ("학생부 반영", "교과 반영", "내신 반영", "환산", "비교과", "생기부")),
    (
        "전형별 지원자격",
        (
            "지원자격",
            "지원 자격",
            "자격 요건",
            "해당자",
            "대상자",
            "동시지원",
            "동시 지원",
            "중복지원",
            "중복 지원",
            "복수지원",
            "복수 지원",
            "학생부종합",
            "학생부교과",
        ),
    ),
    ("제출서류 안내", ("제출서류", "서류 제출", "서류제출", "업로드", "자기소개서", "대체서식")),
    ("면접고사 안내", ("면접", "면접고사", "면접 일정", "면접 방식")),
    ("등록금 및 장학", ("등록금", "장학", "장학금", "수업료", "입학금")),
    ("논술고사 안내", ("논술", "논술고사", "모의논술", "샤프")),
    ("전형일정", ("원서접수", "접수 기간", "일정", "마감", "발표")),
]


def _normalize(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def classify_inquiry_topic(text: str) -> str:
    """문의 문장에서 핵심 유형 1개를 반환합니다."""
    raw = (text or "").strip()
    if not raw:
        return "기타"
    normalized = _normalize(raw)
    for label, keywords in TOPIC_RULES:
        for kw in keywords:
            nkw = _normalize(kw)
            if nkw and (nkw in normalized or kw in raw):
                return label
    return "기타"


def aggregate_inquiry_topics(
    db: Session,
    *,
    days: int = 7,
    limit: int = 6,
) -> dict[str, Any]:
    """최근 N일 입시 문의(Inquiry)를 유형별로 집계합니다."""
    days = max(1, min(days, 90))
    since = now_kst() - timedelta(days=days)

    inquiry_rows = (
        db.query(Inquiry)
        .filter(Inquiry.created_at >= since)
        .order_by(Inquiry.created_at.desc())
        .all()
    )

    counter: Counter[str] = Counter()
    samples: dict[str, list[str]] = {}
    for row in inquiry_rows:
        content = row.content or ""
        topic = classify_inquiry_topic(content)
        counter[topic] += 1
        bucket = samples.setdefault(topic, [])
        if len(bucket) < 3:
            snippet = content.strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            if snippet:
                bucket.append(snippet)

    ordered = counter.most_common(limit)
    if not ordered:
        placeholder = [
            "수능최저학력기준",
            "학생부 반영방법",
            "전형별 지원자격",
            "제출서류 안내",
            "면접고사 안내",
            "등록금 및 장학",
        ]
        items = [{"label": label, "count": 0, "samples": []} for label in placeholder]
        total = 0
    else:
        items = [
            {"label": label, "count": count, "samples": samples.get(label, [])}
            for label, count in ordered
        ]
        total = sum(counter.values())

    return {
        "days": days,
        "total": total,
        "items": items,
        "updated_at": now_kst().isoformat(),
        "source": "inquiries",
    }
