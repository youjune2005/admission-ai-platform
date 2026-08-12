"""별지 제8호 서식(등록금 명세서) PDF 생성.

원본 양식 PDF를 배경으로 쓰고, 측정된 격자 좌표에 값을 세로(포트레이트) 표로 기입합니다.
채팅 미리보기용 PNG도 함께 생성합니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pymupdf

from app.core.config import get_settings

COLUMNS = [
    "구분",
    "대학, 계열",
    "과정",
    "세분",
    "학기",
    "학년(학기)",
    "학생수",
    "입학금/1인당 금액",
    "입학금/금액",
    "수업료/1인당 금액",
    "수업료/금액",
    "합계",
    "비고",
]

# 원본 [별지 제8호 서식]_pdf.pdf 에서 추출한 격자 (A4 pt)
COL_XS = [
    90.7,
    122.5,
    154.3,
    186.1,
    217.9,
    249.7,
    281.5,
    313.3,
    345.1,
    376.9,
    408.7,
    440.5,
    472.3,
    504.1,
]
HEADER_TOP = 198.5
HEADER_MID = 217.4
HEADER_BOTTOM = 252.4
TABLE_BOTTOM = 756.0

# 원본 양식의 섹션 경계 (데이터 블록 / 소계·합계·총계)
SECTION_BANDS: list[tuple[float, float, str]] = [
    (252.4, 350.4, "data"),
    (350.4, 377.9, "소계"),
    (377.9, 476.4, "data"),
    (476.4, 503.9, "소계"),
    (503.9, 602.4, "data"),
    (602.4, 630.0, "합계"),
    (630.0, 728.5, "data"),
    (728.5, 756.0, "총계"),
]

ROWS_PER_DATA_BLOCK = 3

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "별지_제8호_서식.pdf"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
]


@dataclass
class TuitionStatementFiles:
    pdf_path: Path
    preview_path: Path


def _find_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return ""


def looks_like_tuition_statement_request(text: str) -> bool:
    keywords = ("등록금", "명세서", "별지 제8호")
    return any(k in text for k in keywords)


def parse_markdown_table(markdown: str) -> list[list[str]]:
    """Markdown 표에서 데이터 행만 추출합니다 (헤더/구분선 제외)."""
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if re.match(r"^\|?\s*:?-{3,}", stripped.replace(" ", "")):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        header_like = sum(
            1 for c in cells if any(h in c for h in ("구분", "대학", "입학금", "수업료", "학생수"))
        )
        if header_like >= 3 and not rows:
            continue
        rows.append(cells)
    return rows


def _normalize_row(cells: list[str], width: int = 13) -> list[str]:
    padded = (cells + [""] * width)[:width]
    cleaned = []
    for c in padded:
        cleaned.append(
            c.replace("{입력 필요}", "")
            .replace("{{입력}}", "")
            .replace("{계산}", "")
            .replace("{입력}", "")
            .strip()
        )
    return cleaned


def _row_label(row: list[str]) -> str:
    return "".join(row[:6]).replace(" ", "")


def _is_summary_label(label: str, kind: str) -> bool:
    return kind in label


def _split_rows(
    raw_rows: list[list[str]],
) -> tuple[list[list[str]], dict[str, list[str]], list[list[str]]]:
    """일반 데이터 행과 소계/합계/총계 행을 분리합니다."""
    data_rows: list[list[str]] = []
    summaries: dict[str, list[str]] = {}
    subtotals: list[list[str]] = []
    for row in raw_rows:
        label = _row_label(row)
        if "총계" in label:
            summaries["총계"] = row
        elif "합계" in label and "소계" not in label:
            summaries["합계"] = row
        elif "소계" in label:
            subtotals.append(row)
            summaries["소계"] = row
        else:
            data_rows.append(row)
    return data_rows, summaries, subtotals


def _build_slot_plan(
    data_rows: list[list[str]],
    summaries: dict[str, list[str]],
    subtotals: list[list[str]],
) -> list[tuple[float, float, list[str] | None, str]]:
    """원본 양식 섹션에 맞춰 (y0, y1, row_or_none, kind) 슬롯을 만듭니다."""
    slots: list[tuple[float, float, list[str] | None, str]] = []
    data_idx = 0
    subtotal_idx = 0
    effective_subtotals = subtotals or (
        [summaries["소계"]] if "소계" in summaries else []
    )

    for y0, y1, kind in SECTION_BANDS:
        if kind == "data":
            height = y1 - y0
            row_h = height / ROWS_PER_DATA_BLOCK
            for i in range(ROWS_PER_DATA_BLOCK):
                sy0 = y0 + i * row_h
                sy1 = y0 + (i + 1) * row_h
                row = data_rows[data_idx] if data_idx < len(data_rows) else None
                if row is not None:
                    data_idx += 1
                slots.append((sy0, sy1, row, "data"))
        elif kind == "소계":
            if subtotal_idx < len(effective_subtotals):
                row = effective_subtotals[subtotal_idx]
                subtotal_idx += 1
            else:
                row = _normalize_row(["소계"])
            slots.append((y0, y1, row, "소계"))
        else:
            row = summaries.get(kind) or _normalize_row([kind])
            slots.append((y0, y1, row, kind))

    return slots


def _draw_centered(
    page: pymupdf.Page,
    text: str,
    rect: pymupdf.Rect,
    fontname: str,
    fontsize: float,
) -> None:
    if not text:
        return
    # 좁은 열에서도 한 줄로 유지 (세로 줄바꿈 방지)
    max_w = max(4.0, rect.width - 1.2)
    size = fontsize
    text_w = max_w
    while size >= 4.5:
        try:
            text_w = pymupdf.get_text_length(text, fontname=fontname, fontsize=size)
        except Exception:  # noqa: BLE001
            text_w = len(text) * size * 0.55
        if text_w <= max_w:
            break
        size -= 0.35

    x = rect.x0 + max(0.4, (rect.width - min(text_w, max_w)) / 2)
    y = rect.y0 + rect.height / 2 + size * 0.32
    page.insert_text(
        pymupdf.Point(x, y),
        text,
        fontname=fontname,
        fontsize=size,
    )


def _merge_span(kind: str) -> int:
    """요약 행 라벨이 가로로 병합되는 열 개수 (원본 양식 기준)."""
    if kind == "총계":
        return 6  # 구분~학년(학기)
    if kind == "합계":
        return 5  # 구분~학기
    if kind == "소계":
        return 4  # 구분~세분
    return 0


def generate_tuition_statement_pdf(
    markdown_content: str,
    output_dir: Path | None = None,
    filename_stem: str | None = None,
) -> Path:
    """하위 호환: PDF 경로만 반환합니다."""
    return generate_tuition_statement_files(
        markdown_content, output_dir=output_dir, filename_stem=filename_stem
    ).pdf_path


def generate_tuition_statement_files(
    markdown_content: str,
    output_dir: Path | None = None,
    filename_stem: str | None = None,
) -> TuitionStatementFiles:
    settings = get_settings()
    out_dir = output_dir or (Path(settings.upload_dir) / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = parse_markdown_table(markdown_content)
    normalized = [_normalize_row(r) for r in raw_rows] if raw_rows else []
    data_rows, summaries, subtotals = _split_rows(normalized)
    slots = _build_slot_plan(data_rows, summaries, subtotals)

    stem = filename_stem or f"등록금_명세서_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = out_dir / f"{stem}.pdf"
    preview_path = out_dir / f"{stem}.png"

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"원본 양식 템플릿이 없습니다: {TEMPLATE_PATH}")

    # 원본 양식을 새 문서로 복사한 뒤 값만 기입 (세로 A4 유지)
    template = pymupdf.open(TEMPLATE_PATH)
    doc = pymupdf.open()
    doc.insert_pdf(template)
    template.close()
    page = doc[0]

    font_path = _find_font()
    fontname = "korea"
    if font_path:
        page.insert_font(fontname=fontname, fontfile=font_path)
    else:
        fontname = "helv"

    # 데이터 블록 내부 가로선 (원본은 큰 칸만 있어, 입력 행 구분을 위해 얇은 선 추가)
    for y0, y1, kind in SECTION_BANDS:
        if kind != "data":
            continue
        row_h = (y1 - y0) / ROWS_PER_DATA_BLOCK
        for i in range(1, ROWS_PER_DATA_BLOCK):
            y = y0 + i * row_h
            page.draw_line(
                pymupdf.Point(COL_XS[0], y),
                pymupdf.Point(COL_XS[-1], y),
                color=(0, 0, 0),
                width=0.35,
            )

    for y0, y1, row, kind in slots:
        if not row:
            continue
        merge_to = _merge_span(kind)

        if merge_to:
            # 소계/합계/총계 라벨은 원본 양식에 이미 인쇄되어 있으므로 값만 기입
            for c_idx in range(merge_to, 13):
                cell = row[c_idx] if c_idx < len(row) else ""
                if not cell:
                    continue
                rect = pymupdf.Rect(COL_XS[c_idx], y0, COL_XS[c_idx + 1], y1)
                _draw_centered(page, cell, rect, fontname, 7.0)
        else:
            for c_idx in range(13):
                cell = row[c_idx] if c_idx < len(row) else ""
                if not cell:
                    continue
                rect = pymupdf.Rect(COL_XS[c_idx], y0, COL_XS[c_idx + 1], y1)
                _draw_centered(page, cell, rect, fontname, 6.8)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    # 미리보기 PNG (채팅용, 세로 비율 유지)
    preview_doc = pymupdf.open(output_path)
    pix = preview_doc[0].get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
    pix.save(preview_path)
    preview_doc.close()

    return TuitionStatementFiles(pdf_path=output_path, preview_path=preview_path)
