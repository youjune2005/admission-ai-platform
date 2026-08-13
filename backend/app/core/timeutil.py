"""대한민국(Asia/Seoul) 기준 시각 유틸.

DB·로그·API에 넣는 시각은 naive KST(타임존 정보 없음, 벽시계=한국시간)로 통일합니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    """현재 시각을 KST naive datetime으로 반환합니다."""
    return datetime.now(KST).replace(tzinfo=None)
