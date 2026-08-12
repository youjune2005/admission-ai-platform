"""예상 예산안 규정 검토 및 예산안 PDF 생성."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pymupdf
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import UploadedDocument
from app.services.briefing_plan_service import (
    _PdfPen,
    _load_font,
    tighten_text,
)
from app.services.form_pdf_service import TuitionStatementFiles

# 규정 키워드 → 적용 규정 표시명
REG_CATALOG = [
    ("예산집행", "예산집행지침"),
    ("집행지침", "예산집행지침"),
    ("구매", "구매규정"),
    ("조달", "구매규정"),
    ("출장", "출장 및 여비규정"),
    ("여비", "출장 및 여비규정"),
    ("수당", "수당 지급 기준"),
    ("모집요강", "모집요강"),
]

EVIDENCE_RULES = [
    ("견적서", ("견적", "홍보", "인쇄", "현수막", "제작")),
    ("비교견적서", ("견적", "구매", "외주")),
    ("규격서", ("장비", "대여", "음향", "빔")),
    ("행사 계획서", ("행사", "설명회", "다과", "장소")),
]

# 예산안 PDF 고정 양식 (열 가중치만 행 수에 따라 늘어나도 동일 유지)
BUDGET_PDF_HEADERS = ["순번", "예산항목", "산출근거", "단가(원)", "수량", "금액(원)", "비고"]
BUDGET_PDF_COL_WEIGHTS = [0.07, 0.16, 0.30, 0.14, 0.08, 0.14, 0.11]


def _docs_text_blob(docs: list[UploadedDocument]) -> str:
    parts: list[str] = []
    for d in docs:
        parts.append(d.filename or "")
        parts.append(d.summary or "")
        parts.append(d.doc_type or "")
    return " ".join(parts).lower()


def applied_regulations(docs: list[UploadedDocument]) -> list[str]:
    blob = _docs_text_blob(docs)
    found: list[str] = []
    for keyword, label in REG_CATALOG:
        if keyword.lower() in blob or keyword in blob:
            if label not in found:
                found.append(label)
    for label in ("예산집행지침", "구매규정", "출장 및 여비규정"):
        if label not in found:
            found.append(label)
    return found[:5]


def evaluate_item_status(item: dict[str, Any], docs: list[UploadedDocument]) -> str:
    """적합 | 견적서 필요 | 담당자 확인"""
    name = str(item.get("name", ""))
    basis = str(item.get("basis", ""))
    amount = int(item.get("amount") or 0)
    unit = int(item.get("unit_price") or 0)
    text = f"{name} {basis}".lower()
    blob = _docs_text_blob(docs)

    needs_quote = any(k in text for k in ("견적", "홍보", "인쇄", "현수막", "외주", "제작", "리플렛"))
    high_amount = amount >= 300_000 or unit >= 300_000
    vague = not basis.strip() or basis.strip() in ("-", "추후", "미정")

    if vague:
        return "담당자 확인"
    if needs_quote and ("견적" not in blob and "구매" not in blob):
        return "견적서 필요"
    if needs_quote and amount >= 100_000:
        return "견적서 필요"
    if high_amount and "예산" not in blob and "집행" not in blob:
        return "담당자 확인"
    return "적합"


def evidence_checklist(items: list[dict[str, Any]], docs: list[UploadedDocument]) -> list[dict[str, str]]:
    blob = _docs_text_blob(docs)
    item_text = " ".join(f"{i.get('name','')} {i.get('basis','')}" for i in items).lower()
    result: list[dict[str, str]] = []
    for label, triggers in EVIDENCE_RULES:
        relevant = any(t in item_text for t in triggers)
        if not relevant and label != "행사 계획서":
            relevant = True
        attached = any(t in blob for t in triggers) or (
            label == "행사 계획서" and ("계획" in blob or "요강" in blob)
        )
        if label == "견적서" and "견적" in blob:
            attached = True
        if label == "비교견적서" and ("비교" in blob or "견적" in blob):
            attached = True
        status = "첨부 완료" if attached else ("첨부 필요" if relevant else "해당 없음")
        if status == "해당 없음":
            status = "첨부 필요" if not attached else "첨부 완료"
        result.append({"name": label, "status": status})
    return result


def review_budget(
    db: Session,
    items: list[dict[str, Any]],
    allocated_budget: int,
) -> dict[str, Any]:
    docs = db.query(UploadedDocument).order_by(UploadedDocument.created_at.desc()).all()
    reviewed: list[dict[str, Any]] = []
    for raw in items:
        unit = int(raw.get("unit_price") or 0)
        qty = int(raw.get("quantity") or 0)
        amount = unit * qty
        row = {
            "name": str(raw.get("name") or "").strip() or "항목",
            "basis": str(raw.get("basis") or "").strip(),
            "unit_price": unit,
            "quantity": qty,
            "amount": amount,
        }
        row["status"] = evaluate_item_status(row, docs)
        reviewed.append(row)

    ok = sum(1 for r in reviewed if r["status"] == "적합")
    warn = len(reviewed) - ok
    total = sum(r["amount"] for r in reviewed)
    return {
        "items": reviewed,
        "total_budget": total,
        "allocated_budget": allocated_budget,
        "remaining_budget": allocated_budget - total,
        "summary": {"suitable": ok, "needs_check": warn},
        "applied_regulations": applied_regulations(docs),
        "evidence": evidence_checklist(reviewed, docs),
        "doc_count": len(docs),
    }


def _fmt_won(value: int) -> str:
    return f"{int(value):,}"


def _build_budget_table_rows(items: list[dict[str, Any]]) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    total = 0
    for idx, item in enumerate(items, start=1):
        name = tighten_text(str(item.get("name") or "").strip() or "항목")
        basis = tighten_text(str(item.get("basis") or "").strip())
        unit = int(item.get("unit_price") or 0)
        qty = int(item.get("quantity") or 0)
        amount = int(item.get("amount") or (unit * qty))
        note = tighten_text(str(item.get("status") or "").strip())
        total += amount
        rows.append(
            [
                str(idx),
                name,
                basis,
                _fmt_won(unit),
                str(qty),
                _fmt_won(amount),
                note,
            ]
        )
    rows.append(["", "합계", "", "", "", _fmt_won(total), ""])
    return rows, total


def _draw_budget_header_block(
    pen: _PdfPen,
    page: pymupdf.Page,
    margin_x: float,
    usable_w: float,
    y: float,
    title: str,
    allocated: int,
    total: int,
    remaining: int,
) -> float:
    title_t = tighten_text(title) or "예상 예산안"
    title_width = pen.text_width(title_t, 15)
    pen.draw(margin_x + max(0, (usable_w - title_width) / 2), y + 14, title_t, 15)
    y += 28
    page.draw_line(
        pymupdf.Point(margin_x + 90, y),
        pymupdf.Point(margin_x + usable_w - 90, y),
        color=(0.2, 0.2, 0.2),
        width=0.8,
    )
    y += 16

    pen.draw(margin_x, y + 10, "1.예산 개요", 10.5)
    y += 16

    # 개요 표: 배정 / 편성 / 잔여
    overview_h = 22
    overview_headers = ["배정 예산(원)", "편성 예산(원)", "잔여 예산(원)"]
    overview_values = [_fmt_won(allocated), _fmt_won(total), _fmt_won(remaining)]
    col_w = usable_w / 3
    for i, h in enumerate(overview_headers):
        x0 = margin_x + i * col_w
        page.draw_rect(
            pymupdf.Rect(x0, y, x0 + col_w, y + overview_h),
            color=(0, 0, 0),
            fill=(0.93, 0.93, 0.93),
            width=0.5,
        )
        pen.draw_centered(pymupdf.Rect(x0, y, x0 + col_w, y + overview_h), h, 8.2)
    y += overview_h
    for i, val in enumerate(overview_values):
        x0 = margin_x + i * col_w
        page.draw_rect(
            pymupdf.Rect(x0, y, x0 + col_w, y + overview_h),
            color=(0, 0, 0),
            width=0.5,
        )
        pen.draw_centered(pymupdf.Rect(x0, y, x0 + col_w, y + overview_h), val, 9)
    y += overview_h + 14

    pen.draw(margin_x, y + 10, "2.세부 산출내역", 10.5)
    y += 16
    return y


def _draw_budget_table_chunk(
    pen: _PdfPen,
    x0: float,
    y0: float,
    usable_w: float,
    rows: list[list[str]],
    *,
    draw_header: bool,
    row_h: float = 20,
    header_h: float = 22,
) -> float:
    """고정 양식의 예산 표 일부를 그립니다. 다음 y를 반환."""
    page = pen.page
    headers = BUDGET_PDF_HEADERS
    cols = len(headers)
    widths = [usable_w * w for w in BUDGET_PDF_COL_WEIGHTS]

    def col_x(i: int) -> float:
        return x0 + sum(widths[:i])

    y = y0
    if draw_header:
        page.draw_rect(
            pymupdf.Rect(x0, y, x0 + usable_w, y + header_h),
            color=(0, 0, 0),
            fill=(0.93, 0.93, 0.93),
            width=0.5,
        )
        for i, h in enumerate(headers):
            pen.draw_centered(
                pymupdf.Rect(col_x(i), y, col_x(i) + widths[i], y + header_h),
                h,
                8.0,
            )
        y += header_h

    table_top = y0 if draw_header else y
    for row in rows:
        is_total = (row[1] if len(row) > 1 else "") == "합계"
        fill = (0.96, 0.96, 0.96) if is_total else None
        page.draw_rect(
            pymupdf.Rect(x0, y, x0 + usable_w, y + row_h),
            color=(0, 0, 0),
            fill=fill,
            width=0.45,
        )
        for i in range(cols):
            page.draw_line(
                pymupdf.Point(col_x(i), table_top),
                pymupdf.Point(col_x(i), y + row_h),
                color=(0, 0, 0),
                width=0.4,
            )
            cell = row[i] if i < len(row) else ""
            size = 8.2 if is_total else 7.6
            # 산출근거는 왼쪽 정렬에 가깝게(가운데가 길면 잘림) — 중앙 유지하되 축소
            pen.draw_centered(
                pymupdf.Rect(col_x(i) + 1, y, col_x(i) + widths[i] - 1, y + row_h),
                cell,
                size,
            )
        y += row_h

    page.draw_rect(pymupdf.Rect(x0, table_top, x0 + usable_w, y), color=(0, 0, 0), width=0.8)
    return y


def generate_budget_statement_pdf(
    items: list[dict[str, Any]],
    title: str = "예상 예산안",
    filename_stem: str | None = None,
    allocated_budget: int = 0,
    output_dir: Path | None = None,
) -> TuitionStatementFiles:
    """행사·업무 예산안 PDF (제목 + 개요 + 세부 산출내역 표). 별지 제8호와 무관."""
    settings = get_settings()
    out_dir = output_dir or (Path(settings.upload_dir) / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = filename_stem or f"예산안_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_path = out_dir / f"{stem}.pdf"
    preview_path = out_dir / f"{stem}.png"

    table_rows, total = _build_budget_table_rows(items)
    allocated = int(allocated_budget or 0)
    remaining = allocated - total

    doc = pymupdf.open()
    page = doc.new_page(width=595.28, height=841.89)
    font, fontfile = _load_font()
    pen = _PdfPen(page, font, fontfile)

    margin_x = 40
    usable_w = page.rect.width - margin_x * 2
    bottom = page.rect.height - 48
    y = 44

    def new_page() -> None:
        nonlocal page, pen, y
        page = doc.new_page(width=595.28, height=841.89)
        pen = _PdfPen(page, font, fontfile)
        y = 44

    y = _draw_budget_header_block(
        pen, page, margin_x, usable_w, y, title, allocated, total, remaining
    )

    row_h = 20
    header_h = 22
    first_chunk = True
    # 데이터 행 + 합계 행을 페이지별로 분할
    remaining_rows = list(table_rows)
    while remaining_rows:
        available = bottom - y - 28
        if available < header_h + row_h:
            new_page()
            pen.draw(margin_x, y + 10, "2.세부 산출내역(계속)", 10.5)
            y += 16
            first_chunk = True
            available = bottom - y - 28

        capacity = max(1, int((available - (header_h if first_chunk else 0)) // row_h))
        chunk = remaining_rows[:capacity]
        remaining_rows = remaining_rows[capacity:]
        y = _draw_budget_table_chunk(
            pen,
            margin_x,
            y,
            usable_w,
            chunk,
            draw_header=first_chunk,
            row_h=row_h,
            header_h=header_h,
        )
        first_chunk = False
        y += 10

    # 하단 안내
    if y + 36 > bottom:
        new_page()
    note = tighten_text(
        "※ 산출근거는「단가(원)×수량」형식으로 기재하며, 금액 단위는 원입니다."
    )
    pen.draw(margin_x, y + 12, note, 8)
    y += 22
    pen.draw(
        margin_x,
        y + 10,
        tighten_text("※ 본 예산안은 편성안이며, 실제 집행은 관련 규정·지침에 따릅니다."),
        8,
    )

    doc.save(pdf_path)
    # 미리보기 PNG (첫 페이지)
    try:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
        pix.save(preview_path)
    except Exception:  # noqa: BLE001
        preview_path = pdf_path.with_suffix(".png")
        try:
            pix = doc[0].get_pixmap(dpi=120)
            pix.save(preview_path)
        except Exception:  # noqa: BLE001
            preview_path = Path("")
    doc.close()

    if not preview_path or not Path(preview_path).exists():
        preview_path = pdf_path

    return TuitionStatementFiles(pdf_path=pdf_path, preview_path=preview_path)
