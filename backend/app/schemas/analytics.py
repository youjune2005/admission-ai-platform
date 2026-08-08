from typing import Any

from pydantic import BaseModel


class ColumnStat(BaseModel):
    column: str
    dtype: str
    non_null_count: int
    null_count: int
    unique_count: int
    numeric_summary: dict[str, float] | None = None
    top_values: dict[str, int] | None = None


class AnalyticsResult(BaseModel):
    filename: str
    row_count: int
    column_count: int
    columns: list[ColumnStat]
    preview: list[dict[str, Any]]
    ai_insight: str | None = None
