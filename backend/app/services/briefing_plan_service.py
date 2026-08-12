"""입시설명회 운영계획서 PDF 생성 (입력 폼 기반)."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf

from app.core.config import get_settings
from app.services.form_pdf_service import TuitionStatementFiles

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
]

BUDGET_ITEM_LABELS = {
    "다과": ("다과비", 8000),
    "홍보물": ("홍보물 제작비", 1500),
    "현수막": ("현수막", 1),
    "장소 장비": ("장소·장비 사용료", 1),
    "교통비": ("교통비", 1),
}


def _find_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return ""


def tighten_text(value: str) -> str:
    """숫자·괄호·문장 부호 주변의 불필요한 공백을 줄입니다."""
    if not value:
        return ""
    text = str(value)
    # 숫자 사이 공백 제거: "2 0 2 7" -> "2027", "1 4:0 0" -> "14:00"
    text = re.sub(r"(?<=\d)\s+(?=\d)", "", text)
    # 괄호 안/바로 뒤 앞 공백 정리: "( 를 )" -> "(를)", ") 을" 유지하되 "(를) " 과잉만 축소
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\)\s+(?=\S)", ")", text)
    # 번호 앞 공백 제거, "1. 목적" -> "1.목적"
    text = re.sub(r"^\s*(\d+)\.\s*", r"\1.", text)
    text = re.sub(r"(?<=\s)(\d+)\.\s+", r"\1.", text)
    # 기호 주변 공백 축소
    text = re.sub(r"\s*~\s*", "~", text)
    text = re.sub(r"\s*×\s*", "×", text)
    text = re.sub(r"\s*,\s*", ",", text)
    text = re.sub(r"\s*:\s*", ":", text)
    # 연속 공백을 한 칸으로
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _load_font() -> tuple[pymupdf.Font | None, str]:
    path = _find_font()
    if not path:
        return None, "helv"
    try:
        return pymupdf.Font(fontfile=path), path
    except Exception:  # noqa: BLE001
        return None, path


class _PdfPen:
    def __init__(self, page: pymupdf.Page, font: pymupdf.Font | None, fontfile: str):
        self.page = page
        self.font = font
        self.fontfile = fontfile
        self.fontname = "korea"
        if fontfile and Path(fontfile).exists():
            try:
                page.insert_font(fontname=self.fontname, fontfile=fontfile)
            except Exception:  # noqa: BLE001
                self.fontname = "helv"
        else:
            self.fontname = "helv"

    def text_width(self, text: str, fontsize: float) -> float:
        text = tighten_text(text)
        if self.font is not None:
            return self.font.text_length(text, fontsize=fontsize)
        return pymupdf.get_text_length(text, fontname=self.fontname, fontsize=fontsize)

    def draw(self, x: float, y: float, text: str, fontsize: float) -> None:
        text = tighten_text(text)
        if not text:
            return
        if self.font is not None:
            tw = pymupdf.TextWriter(self.page.rect)
            tw.append(pymupdf.Point(x, y), text, font=self.font, fontsize=fontsize)
            tw.write_text(self.page)
        else:
            self.page.insert_text(
                pymupdf.Point(x, y),
                text,
                fontname=self.fontname,
                fontsize=fontsize,
            )

    def draw_centered(self, rect: pymupdf.Rect, text: str, fontsize: float) -> None:
        text = tighten_text(text)
        if not text:
            return
        width = self.text_width(text, fontsize)
        # 너무 길면 글자 크기만 소폭 축소
        size = fontsize
        while width > rect.width - 2 and size > 6:
            size -= 0.4
            width = self.text_width(text, size)
        x = rect.x0 + max(1.0, (rect.width - width) / 2)
        y = rect.y0 + rect.height / 2 + size * 0.32
        self.draw(x, y, text, size)

    def draw_wrapped(self, rect: pymupdf.Rect, text: str, fontsize: float) -> float:
        """왼쪽 정렬 줄바꿈. 사용한 높이를 반환."""
        text = tighten_text(text)
        if not text:
            return 0
        words = list(text)
        # 글자 단위로 폭에 맞춰 줄 분할 (한글/숫자 공백 이슈 방지)
        lines: list[str] = []
        current = ""
        for ch in words:
            trial = current + ch
            if self.text_width(trial, fontsize) <= rect.width or not current:
                current = trial
            else:
                lines.append(current)
                current = ch
        if current:
            lines.append(current)

        y = rect.y0 + fontsize
        for line in lines:
            if y > rect.y1:
                break
            self.draw(rect.x0, y, line, fontsize)
            y += fontsize * 1.25
        return y - rect.y0


def _draw_table(
    pen: _PdfPen,
    x0: float,
    y0: float,
    usable_w: float,
    headers: list[str],
    rows: list[list[str]],
    col_weights: list[float] | None = None,
    row_h: float = 18,
    header_h: float = 20,
) -> float:
    page = pen.page
    cols = len(headers)
    weights = col_weights or [1 / cols] * cols
    widths = [usable_w * w for w in weights]

    def col_x(i: int) -> float:
        return x0 + sum(widths[:i])

    page.draw_rect(
        pymupdf.Rect(x0, y0, x0 + usable_w, y0 + header_h),
        color=(0, 0, 0),
        fill=(0.93, 0.93, 0.93),
        width=0.5,
    )
    for i, h in enumerate(headers):
        pen.draw_centered(
            pymupdf.Rect(col_x(i), y0, col_x(i) + widths[i], y0 + header_h),
            h,
            8.2,
        )

    y = y0 + header_h
    for row in rows:
        page.draw_rect(
            pymupdf.Rect(x0, y, x0 + usable_w, y + row_h),
            color=(0, 0, 0),
            width=0.45,
        )
        for i in range(cols):
            page.draw_line(
                pymupdf.Point(col_x(i), y0),
                pymupdf.Point(col_x(i), y + row_h),
                color=(0, 0, 0),
                width=0.4,
            )
            cell = row[i] if i < len(row) else ""
            pen.draw_centered(
                pymupdf.Rect(col_x(i), y, col_x(i) + widths[i], y + row_h),
                cell,
                7.8,
            )
        y += row_h
    page.draw_rect(pymupdf.Rect(x0, y0, x0 + usable_w, y), color=(0, 0, 0), width=0.8)
    return y


def build_budget_rows(payload: dict[str, Any]) -> list[list[str]]:
    attendees = int(str(payload.get("attendees", "100")).replace("명", "").replace(",", "").strip() or "100")
    limit = int(str(payload.get("budget_limit", "2000000")).replace(",", "").replace("원", "").strip() or "2000000")
    items: list[str] = payload.get("budget_items") or []
    rows: list[list[str]] = []
    total = 0
    for label in items:
        name, unit_hint = BUDGET_ITEM_LABELS.get(label, (label, 1))
        if label == "다과":
            unit, qty, basis = 8000, attendees, f"{attendees}명×{8000:,}원"
        elif label == "홍보물":
            unit, qty, basis = 1500, attendees, f"리플렛{attendees}부×{1500:,}원"
        elif label == "현수막":
            unit, qty, basis = 120000, 1, "현수막1식"
        elif label == "장소 장비":
            unit, qty, basis = 300000, 1, "음향·빔등1식"
        elif label == "교통비":
            qty = max(1, attendees // 50)
            unit, basis = 50000, f"차량{qty}대×{50000:,}원"
        else:
            unit, qty, basis = unit_hint, 1, "1식"
        amount = unit * qty
        total += amount
        rows.append([name, basis, f"{unit:,}", str(qty), f"{amount:,}"])

    if total > limit and total > 0:
        ratio = limit / total
        scaled: list[list[str]] = []
        new_total = 0
        for name, basis, unit_s, qty_s, _ in rows:
            amount = int(int(unit_s.replace(",", "")) * int(qty_s) * ratio)
            new_total += amount
            scaled.append([name, basis, unit_s, qty_s, f"{amount:,}"])
        rows = scaled
        total = new_total

    rows.append(["합계", "", "", "", f"{total:,}"])
    return [[tighten_text(c) for c in row] for row in rows]


def generate_briefing_plan_pdf(
    payload: dict[str, Any],
    output_dir: Path | None = None,
    filename_stem: str | None = None,
) -> TuitionStatementFiles:
    settings = get_settings()
    out_dir = output_dir or (Path(settings.upload_dir) / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = filename_stem or f"운영계획서_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_path = out_dir / f"{stem}.pdf"
    preview_path = out_dir / f"{stem}.png"

    event_name = tighten_text(payload.get("event_name") or "입시설명회")
    title = tighten_text(f"{event_name} 운영계획서")
    target = tighten_text(payload.get("target") or "")
    attendees = tighten_text(payload.get("attendees") or "")
    schedule = tighten_text(payload.get("schedule") or "")
    location = tighten_text(payload.get("location") or "")
    department = tighten_text(payload.get("department") or "입학팀")
    programs: list[dict[str, str]] = payload.get("programs") or []

    doc = pymupdf.open()
    page = doc.new_page(width=595.28, height=841.89)
    font, fontfile = _load_font()
    pen = _PdfPen(page, font, fontfile)

    margin_x = 46
    usable_w = page.rect.width - margin_x * 2
    y = 44

    def new_page() -> None:
        nonlocal page, pen, y
        page = doc.new_page(width=595.28, height=841.89)
        pen = _PdfPen(page, font, fontfile)
        y = 44

    def ensure(need: float) -> None:
        nonlocal y
        if y + need > page.rect.height - 44:
            new_page()

    # title
    title_width = pen.text_width(title, 15)
    pen.draw(margin_x + max(0, (usable_w - title_width) / 2), y + 14, title, 15)
    y += 28
    page.draw_line(
        pymupdf.Point(margin_x + 90, y),
        pymupdf.Point(margin_x + usable_w - 90, y),
        color=(0.2, 0.2, 0.2),
        width=0.8,
    )
    y += 14

    # 1.목적
    ensure(55)
    pen.draw(margin_x, y + 10, "1.목적", 10.5)
    y += 14
    purpose = tighten_text(
        f"{department}에서는 {target or '고등학생 및 학부모'}을(를) 대상으로 "
        f"{event_name}을(를) 개최하여 전형 안내와 상담을 제공하고자 함."
    )
    used = pen.draw_wrapped(
        pymupdf.Rect(margin_x, y, margin_x + usable_w, y + 46),
        purpose,
        9.2,
    )
    y += max(used, 22) + 8

    # 2.행사개요
    ensure(110)
    pen.draw(margin_x, y + 10, "2.행사개요", 10.5)
    y += 13
    attendee_label = attendees if str(attendees).endswith("명") else f"{attendees}명"
    overview_rows = [
        ["행사명", event_name],
        ["대상", target],
        ["참석예정인원", tighten_text(attendee_label)],
        ["일시", schedule],
        ["장소", location],
        ["주관부서", department],
    ]
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["항목", "내용"],
        overview_rows,
        col_weights=[0.26, 0.74],
        row_h=17,
        header_h=18,
    )
    y += 12

    # 3.세부일정
    ensure(36 + 18 * max(len(programs), 1))
    pen.draw(margin_x, y + 10, "3.세부일정", 10.5)
    y += 13
    program_rows = [
        [
            str(i + 1),
            tighten_text(p.get("time", "")),
            tighten_text(p.get("content", "")),
            tighten_text(p.get("owner", "")),
        ]
        for i, p in enumerate(programs)
    ] or [["1", "-", "-", "-"]]
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["순서", "시간", "프로그램내용", "담당자"],
        program_rows,
        col_weights=[0.1, 0.22, 0.42, 0.26],
        row_h=17,
        header_h=18,
    )
    y += 12

    # 4.업무분장
    ensure(90)
    pen.draw(margin_x, y + 10, "4.업무분장", 10.5)
    y += 13
    owners = sorted({tighten_text(p.get("owner", department)) for p in programs if p.get("owner")})
    if not owners:
        owners = [department]
    duty_rows = [[o, "프로그램 진행 및 현장 응대", "당일"] for o in owners]
    duty_rows.append([tighten_text(f"{department} 전체"), "접수·안내·질의응답 지원", "당일"])
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["담당", "주요업무", "시기"],
        duty_rows,
        col_weights=[0.28, 0.5, 0.22],
        row_h=17,
        header_h=18,
    )
    y += 12

    # 5.예산
    ensure(120)
    pen.draw(margin_x, y + 10, "5.예산", 10.5)
    y += 13
    budget_rows = build_budget_rows(payload)
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["예산항목", "산출근거", "단가", "수량", "금액(원)"],
        budget_rows,
        col_weights=[0.2, 0.34, 0.16, 0.12, 0.18],
        row_h=17,
        header_h=18,
    )
    y += 12

    # 6.기대효과
    ensure(70)
    pen.draw(margin_x, y + 10, "6.기대효과", 10.5)
    y += 14
    effects = [
        "·수시전형에 대한 정확한 정보제공으로 지원자·학부모 이해도 제고",
        "·현장상담을 통한 문의응대 효율화 및 민원 사전예방",
        f"·{department} 홍보역량 강화 및 우수인재 유치 기반 마련",
    ]
    for line in effects:
        ensure(16)
        pen.draw(margin_x, y + 9, tighten_text(line), 9.0)
        y += 14

    doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()

    preview = pymupdf.open(pdf_path)
    pix = preview[0].get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False)
    pix.save(preview_path)
    preview.close()

    return TuitionStatementFiles(pdf_path=pdf_path, preview_path=preview_path)
