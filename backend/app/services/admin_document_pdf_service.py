"""행정문서(운영계획서 등) Markdown → PDF/PNG 미리보기 생성."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pymupdf

from app.core.config import get_settings
from app.services.form_pdf_service import TuitionStatementFiles, parse_markdown_table

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/Library/Fonts/AppleGothic.ttf",
]

ADMIN_DOC_KEYWORDS = (
    "운영계획서",
    "행정문서",
    "홍보계획서",
    "참가계획서",
    "결과보고서",
    "예산안",
    "보조문서",
)


def looks_like_admin_document_request(text: str) -> bool:
    return any(k in text for k in ADMIN_DOC_KEYWORDS)


def _find_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return ""


def _extract_title(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
        if "운영계획서" in stripped and len(stripped) < 80:
            return stripped.strip("* ").strip()
    return fallback


def _plain_blocks(markdown: str) -> list[tuple[str, str]]:
    """(kind, text) — heading|paragraph|bullet|table_marker."""
    blocks: list[tuple[str, str]] = []
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("|"):
            table_lines = [stripped]
            i += 1
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            blocks.append(("table", "\n".join(table_lines)))
            continue
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            blocks.append((f"h{min(level, 3)}", stripped.lstrip("#").strip()))
            i += 1
            continue
        if re.match(r"^(\d+\.|[-*•])\s+", stripped):
            blocks.append(("bullet", re.sub(r"^(\d+\.|[-*•])\s+", "", stripped)))
            i += 1
            continue
        # bold-ish section titles like **1. 목적**
        if stripped.startswith("**") and stripped.endswith("**"):
            blocks.append(("h2", stripped.strip("*").strip()))
            i += 1
            continue
        blocks.append(("p", stripped.replace("**", "")))
        i += 1
    return blocks


def generate_admin_document_files(
    markdown_content: str,
    title_hint: str = "행정문서",
    output_dir: Path | None = None,
    filename_stem: str | None = None,
) -> TuitionStatementFiles:
    settings = get_settings()
    out_dir = output_dir or (Path(settings.upload_dir) / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = filename_stem or f"행정문서_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_path = out_dir / f"{stem}.pdf"
    preview_path = out_dir / f"{stem}.png"

    content = markdown_content.strip()
    if content.startswith("[AI 응답 실패]"):
        raise ValueError("AI 응답 실패 내용은 PDF로 만들지 않습니다.")

    title = _extract_title(content, title_hint)
    blocks = _plain_blocks(content)

    doc = pymupdf.open()
    page = doc.new_page(width=595.28, height=841.89)
    font_path = _find_font()
    fontname = "korea"
    if font_path:
        page.insert_font(fontname=fontname, fontfile=font_path)
    else:
        fontname = "helv"

    margin_x = 48
    margin_top = 52
    margin_bottom = 48
    usable_w = page.rect.width - margin_x * 2
    y = margin_top

    def new_page() -> pymupdf.Page:
        nonlocal page, y
        page = doc.new_page(width=595.28, height=841.89)
        if font_path:
            page.insert_font(fontname=fontname, fontfile=font_path)
        y = margin_top
        return page

    def ensure_space(need: float) -> None:
        nonlocal y
        if y + need > page.rect.height - margin_bottom:
            new_page()

    # Title
    ensure_space(40)
    page.insert_textbox(
        pymupdf.Rect(margin_x, y, margin_x + usable_w, y + 36),
        title,
        fontname=fontname,
        fontsize=16,
        align=pymupdf.TEXT_ALIGN_CENTER,
    )
    y += 42
    page.draw_line(
        pymupdf.Point(margin_x + usable_w * 0.25, y),
        pymupdf.Point(margin_x + usable_w * 0.75, y),
        color=(0.15, 0.15, 0.15),
        width=0.8,
    )
    y += 18

    for kind, text in blocks:
        if kind == "table":
            rows = parse_markdown_table(text)
            # include header from first markdown header line
            header_cells: list[str] = []
            for line in text.splitlines():
                if re.match(r"^\|?\s*:?-{3,}", line.replace(" ", "")):
                    continue
                if line.strip().startswith("|") and not header_cells:
                    header_cells = [c.strip() for c in line.strip().strip("|").split("|")]
                    break
            table_rows = ([header_cells] if header_cells else []) + rows
            if not table_rows:
                continue
            cols = max(len(r) for r in table_rows)
            col_w = usable_w / cols
            row_h = 18
            ensure_space(row_h * len(table_rows) + 12)
            top = y
            for r_idx, row in enumerate(table_rows):
                padded = (row + [""] * cols)[:cols]
                for c_idx, cell in enumerate(padded):
                    x0 = margin_x + c_idx * col_w
                    rect = pymupdf.Rect(x0, top + r_idx * row_h, x0 + col_w, top + (r_idx + 1) * row_h)
                    if r_idx == 0:
                        page.draw_rect(rect, color=(0, 0, 0), fill=(0.93, 0.93, 0.93), width=0.4)
                    else:
                        page.draw_rect(rect, color=(0, 0, 0), width=0.4)
                    page.insert_textbox(
                        pymupdf.Rect(rect.x0 + 2, rect.y0 + 2, rect.x1 - 2, rect.y1 - 1),
                        cell[:40],
                        fontname=fontname,
                        fontsize=7.5,
                        align=pymupdf.TEXT_ALIGN_CENTER,
                    )
            y = top + row_h * len(table_rows) + 14
            continue

        if kind.startswith("h"):
            size = 13 if kind == "h1" else 11.5 if kind == "h2" else 10.5
            ensure_space(size + 14)
            page.insert_text(
                pymupdf.Point(margin_x, y + size),
                text,
                fontname=fontname,
                fontsize=size,
            )
            y += size + 12
            continue

        if kind == "bullet":
            ensure_space(20)
            wrote = page.insert_textbox(
                pymupdf.Rect(margin_x + 8, y, margin_x + usable_w, y + 48),
                f"• {text}",
                fontname=fontname,
                fontsize=9.5,
                align=pymupdf.TEXT_ALIGN_LEFT,
            )
            # insert_textbox returns unused height leftover (negative if overflow)
            y += 18 if wrote >= 0 else 36
            continue

        # paragraph
        ensure_space(24)
        rect = pymupdf.Rect(margin_x, y, margin_x + usable_w, y + 90)
        leftover = page.insert_textbox(
            rect,
            text,
            fontname=fontname,
            fontsize=9.5,
            align=pymupdf.TEXT_ALIGN_LEFT,
        )
        used = 90 - max(leftover, 0) if leftover >= 0 else 90
        y += max(used, 16) + 8

    doc.save(pdf_path, garbage=4, deflate=True)
    doc.close()

    preview_doc = pymupdf.open(pdf_path)
    pix = preview_doc[0].get_pixmap(matrix=pymupdf.Matrix(1.7, 1.7), alpha=False)
    pix.save(preview_path)
    preview_doc.close()

    return TuitionStatementFiles(pdf_path=pdf_path, preview_path=preview_path)
