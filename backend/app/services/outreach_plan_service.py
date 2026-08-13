"""고교 방문 홍보계획서 · 박람회 참가계획서 PDF 생성 (예산 없음)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pymupdf

from app.core.config import get_settings
from app.services.briefing_plan_service import (
    _PdfPen,
    _draw_table,
    _load_font,
    tighten_text,
)
from app.services.form_pdf_service import TuitionStatementFiles

PlanKind = Literal["visit", "fair"]


def _overview_rows_visit(payload: dict[str, Any]) -> list[list[str]]:
    attendees = tighten_text(payload.get("attendees") or "")
    attendee_label = attendees if str(attendees).endswith("명") else f"{attendees}명"
    return [
        ["계획명", tighten_text(payload.get("event_name") or "")],
        ["방문고교", tighten_text(payload.get("school_name") or "")],
        ["지역", tighten_text(payload.get("region") or "")],
        ["대상", tighten_text(payload.get("target") or "")],
        ["예상참석인원", tighten_text(attendee_label)],
        ["일시", tighten_text(payload.get("schedule") or "")],
        ["장소", tighten_text(payload.get("location") or "")],
        ["진행형태", tighten_text(payload.get("format") or "오프라인")],
        ["고교담당교사", tighten_text(payload.get("contact_teacher") or "")],
        ["주관부서", tighten_text(payload.get("department") or "입학팀")],
    ]


def _overview_rows_fair(payload: dict[str, Any]) -> list[list[str]]:
    attendees = tighten_text(payload.get("attendees") or "")
    attendee_label = attendees if str(attendees).endswith("명") else f"{attendees}명"
    return [
        ["박람회명", tighten_text(payload.get("event_name") or "")],
        ["주최·주관", tighten_text(payload.get("host") or "")],
        ["부스번호", tighten_text(payload.get("booth_no") or "")],
        ["대상", tighten_text(payload.get("target") or "")],
        ["예상상담인원", tighten_text(attendee_label)],
        ["일시", tighten_text(payload.get("schedule") or "")],
        ["개최장소", tighten_text(payload.get("location") or "")],
        ["배치인력", tighten_text(payload.get("staff_count") or "")],
        ["주관부서", tighten_text(payload.get("department") or "입학팀")],
    ]


def generate_outreach_plan_pdf(
    kind: PlanKind,
    payload: dict[str, Any],
    output_dir: Path | None = None,
    filename_stem: str | None = None,
) -> TuitionStatementFiles:
    settings = get_settings()
    out_dir = output_dir or (Path(settings.upload_dir) / "generated")
    out_dir.mkdir(parents=True, exist_ok=True)

    is_visit = kind == "visit"
    default_stem = "고교방문홍보계획서" if is_visit else "박람회참가계획서"
    stem = filename_stem or f"{default_stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    pdf_path = out_dir / f"{stem}.pdf"
    preview_path = out_dir / f"{stem}.png"

    event_name = tighten_text(payload.get("event_name") or ("고교 방문 홍보" if is_visit else "입시 박람회"))
    title_suffix = "홍보계획서" if is_visit else "참가계획서"
    title = tighten_text(f"{event_name} {title_suffix}")
    department = tighten_text(payload.get("department") or "입학팀")
    target = tighten_text(payload.get("target") or "")
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
    if is_visit:
        school = tighten_text(payload.get("school_name") or "방문 고교")
        purpose = (
            f"{department}에서는 {school}을(를) 방문하여 "
            f"{target or '학생·학부모·교사'}을(를) 대상으로 전형 안내와 진학 상담을 실시하고, "
            f"고교-대학 연계를 강화하고자 함."
        )
    else:
        host = tighten_text(payload.get("host") or "주최 기관")
        purpose = (
            f"{department}에서는 {host} 주최 {event_name}에 참가하여 "
            f"{target or '수험생 및 학부모'} 대상 상담·홍보를 실시하고 "
            f"우수 인재 유치 기반을 마련하고자 함."
        )
    used = pen.draw_wrapped(
        pymupdf.Rect(margin_x, y, margin_x + usable_w, y + 46),
        tighten_text(purpose),
        9.2,
    )
    y += max(used, 22) + 8

    # 2.개요
    overview = _overview_rows_visit(payload) if is_visit else _overview_rows_fair(payload)
    ensure(24 + 17 * len(overview))
    pen.draw(margin_x, y + 10, "2.개요", 10.5)
    y += 13
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["항목", "내용"],
        overview,
        col_weights=[0.26, 0.74],
        row_h=17,
        header_h=18,
    )
    y += 12

    # 3.세부일정 / 부스운영
    ensure(36 + 18 * max(len(programs), 1))
    section3 = "3.세부일정" if is_visit else "3.부스운영계획"
    pen.draw(margin_x, y + 10, section3, 10.5)
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
        ["순서", "시간", "내용", "담당자"],
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
    owners = sorted(
        {tighten_text(p.get("owner", department)) for p in programs if p.get("owner")}
    )
    if not owners:
        owners = [department]
    if is_visit:
        duty_rows = [[o, "방문 설명·상담 진행", "당일"] for o in owners]
        duty_rows.append([tighten_text(f"{department} 전체"), "자료배포·질의응답 지원", "당일"])
    else:
        duty_rows = [[o, "부스 상담·안내", "행사기간"] for o in owners]
        duty_rows.append([tighten_text(f"{department} 전체"), "홍보물 비치·동선 안내", "행사기간"])
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

    # 5.준비사항 (예산 대신)
    ensure(100)
    pen.draw(margin_x, y + 10, "5.준비사항", 10.5)
    y += 13
    if is_visit:
        prep_rows = [
            ["필요장비", tighten_text(payload.get("equipment") or "-")],
            ["홍보·배포자료", tighten_text(payload.get("materials") or "-")],
            ["요청·특이사항", tighten_text(payload.get("notes") or "-")],
        ]
    else:
        prep_rows = [
            ["홍보물·준비물", tighten_text(payload.get("materials") or "-")],
            ["상담중점내용", tighten_text(payload.get("consulting_focus") or "-")],
            ["기타사항", tighten_text(payload.get("notes") or "-")],
        ]
    y = _draw_table(
        pen,
        margin_x,
        y,
        usable_w,
        ["구분", "내용"],
        prep_rows,
        col_weights=[0.26, 0.74],
        row_h=20,
        header_h=18,
    )
    y += 12

    # 6.기대효과
    ensure(70)
    pen.draw(margin_x, y + 10, "6.기대효과", 10.5)
    y += 14
    if is_visit:
        effects = [
            "·고교 현장 방문으로 전형 정보 접근성 제고 및 오해·민원 예방",
            "·교사·학생과의 직접 소통을 통한 고교-대학 연계 강화",
            f"·{department} 홍보 활동의 우수 인재 유치 기반 확대",
        ]
    else:
        effects = [
            "·다수 수험생·학부모 대상 집중 상담으로 정보 제공 효율화",
            "·현장 질의 응대를 통한 지원 전략 안내 및 브랜드 인지도 제고",
            f"·{department} 박람회 참가 성과 축적 및 후속 홍보 연계",
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
