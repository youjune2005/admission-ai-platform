import io

import pandas as pd

from app.schemas.analytics import AnalyticsResult, ColumnStat
from app.services.llm_service import get_llm_service


def _read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    if filename.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content))
    return pd.read_csv(io.BytesIO(content))


def analyze_file(filename: str, content: bytes, with_ai_insight: bool = True) -> AnalyticsResult:
    df = _read_dataframe(filename, content)

    columns: list[ColumnStat] = []
    for col in df.columns:
        series = df[col]
        numeric_summary = None
        top_values = None

        if pd.api.types.is_numeric_dtype(series):
            desc = series.describe()
            numeric_summary = {
                "mean": float(desc.get("mean", 0) or 0),
                "std": float(desc.get("std", 0) or 0),
                "min": float(desc.get("min", 0) or 0),
                "max": float(desc.get("max", 0) or 0),
            }
        else:
            top_values = series.astype(str).value_counts().head(5).to_dict()

        columns.append(
            ColumnStat(
                column=str(col),
                dtype=str(series.dtype),
                non_null_count=int(series.notna().sum()),
                null_count=int(series.isna().sum()),
                unique_count=int(series.nunique()),
                numeric_summary=numeric_summary,
                top_values=top_values,
            )
        )

    preview = df.head(10).fillna("").astype(object).to_dict(orient="records")

    ai_insight = None
    if with_ai_insight:
        ai_insight = _generate_insight(filename, df, columns)

    return AnalyticsResult(
        filename=filename,
        row_count=len(df),
        column_count=len(df.columns),
        columns=columns,
        preview=preview,
        ai_insight=ai_insight,
    )


def _generate_insight(filename: str, df: pd.DataFrame, columns: list[ColumnStat]) -> str:
    llm = get_llm_service()
    summary_lines = [
        f"- {c.column} ({c.dtype}): 결측 {c.null_count}건, 고유값 {c.unique_count}개"
        for c in columns[:20]
    ]
    prompt = (
        f"다음은 '{filename}' 입시 데이터 파일의 통계 요약입니다. 총 {len(df)}건, {len(df.columns)}개 컬럼.\n"
        + "\n".join(summary_lines)
        + "\n\n입시행정 담당자 관점에서 주목할 만한 특이사항, 데이터 품질 이슈, "
        "추가로 분석해보면 좋을 포인트를 3~5개의 불릿포인트로 한국어로 요약해줘."
    )
    return llm.chat([{"role": "user", "content": prompt}])
