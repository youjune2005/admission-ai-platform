"""행정문서 작성: 내용 정합성 점검 + 규정 RAG 검토."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.llm_service import get_llm_service
from app.services.rag_service import (
    aggregate_document_references,
    retrieve_relevant_chunks,
)

logger = logging.getLogger(__name__)

_NUM = re.compile(r"\d[\d,]*")
# 수량×단가 산출식. 반드시 '원'이 붙어야 하며, 크기 표기(3m×1m)와 구분합니다.
_BASIS_RE = re.compile(
    r"(?P<qty>\d[\d,]*)\s*(?P<unit>명|개|부|대|식|장|건|매|본)?\s*[×xX*]\s*(?P<price>\d[\d,]*)\s*원"
)
# 숫자와 × 사이에 끼면 산출식이 아닌 길이 단위로 봅니다.
_LENGTH_UNIT = r"(?:mm|cm|m|㎜|㎝|ｍ|미터|센티|센티미터)"
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[~\-–]\s*(\d{1,2}):(\d{2})")

CONTENT_SYSTEM_PROMPT = (
    "당신은 대학 입학처 행정문서를 검토하는 담당자입니다. "
    "제공된 문서 JSON 안에서만 모순을 찾으세요. "
    "인터넷·일반 시세·관행·외부 지식은 절대 사용하지 마세요. "
    "같은 불일치는 한 건만 보고하고, 어느 쪽 값을 고칠지 선택지(options)로 나누세요. "
    "예: 수량 4 vs 산출근거 2대 → 옵션1 수량 4→2, 옵션2 근거 2대→4대. "
    "예산 항목에서 볼 것은 단가·수량·산출 근거 세 가지의 불일치뿐입니다. "
    "금액·합계·총 예산액·배정 예산·잔액은 시스템이 자동으로 계산하므로 "
    "검산하거나 서로 비교하지 말고, 그에 대한 지적은 절대 만들지 마세요. "
    "산출 근거에 'N개 × M원'처럼 수량과 단가가 적힌 식이 있을 때만 대조하세요. "
    "'견적 기준', '시중가', '협의', '업체 견적'처럼 식이 없는 메모나 "
    "'3m × 1m' 같은 크기·규격 메모는 수량·단가와 비교하지 마세요. "
    "문서에 없는 항목을 추가하거나 가격이 적절한지 평가하지 마세요. "
    "문제가 없으면 빈 배열을 반환하세요. "
    "반드시 JSON만 출력하세요: "
    '{"issues":[{"id":"문자열","severity":"error"|"warn","location":"위치",'
    '"field":"json경로","problem":"한 줄 문제 설명","guideline":"선택 가이드",'
    '"options":[{"id":"opt1","label":"수량을 4 → 2로 변경","before":"수량 4",'
    '"after":"수량 2","patches":[{"path":"budget_lines.0.quantity","value":2}]}]}]}'
)

REGULATION_SYSTEM_PROMPT = (
    "당신은 대학 입학처에서 행정문서와 내부 규정을 한 문장씩 대조하는 담당자입니다. "
    "반드시 아래에 제공된 내부 규정·자료 RAG 결과의 원문만 근거로 삼으세요. "
    "인터넷 검색·일반론·추측으로 대충 넘기지 마세요. "
    "각 건은 문서에서 문제 되는 구절과 규정 원문 문장을 그대로 따오세요. "
    "\n"
    "【위반(violation) — 매우 엄격】 "
    "금액·인원·절차·첨부 의무 등이 규정 문장과 숫자·의무가 명백히 충돌할 때만 쓰세요. "
    "애매하면 violation으로 올리지 말고 check로 두세요. "
    "\n"
    "【검토 필요(check) — 넓게】 "
    "위반으로 단정하기 어렵더라도, 관련 규정이 있고 문서 기재와 맞춰 볼 여지가 있으면 "
    "대부분 check로 올리세요. "
    "예산 한도·견적·첨부·여비·수당·구매·홍보비·다과비·인원·장소·일정 등 "
    "담당자 확인이 필요할 만한 항목은 check로 잡으세요. "
    "reason에는 왜 대조가 필요한지 한 문장으로 적으세요. "
    "관련 규정 청크가 있으면 findings가 거의 비지 않게 하세요. "
    "\n"
    "제공된 근거 목록에 없는 문서를 인용하지 마세요. "
    "모집요강·전형요강은 예산 항목(다과비·홍보물·리플렛 등) 검토 근거로 쓰지 마세요. "
    "반드시 JSON만 출력하세요: "
    '{"findings":[{"status":"violation"|"check","location":"예산 > 다과비",'
    '"document_excerpt":"문서에 적힌 문제 구절 그대로",'
    '"regulation_excerpt":"규정 원문 문장 그대로",'
    '"regulation_title":"규정 파일명","citation_n":1,'
    '"reason":"검토가 필요한 구체적 이유 한 문장",'
    '"mismatch_note":"이 문서의 「…」 부분이 규정 「…」에 맞지 않음"}]}'
)


def _to_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"[^\d]", "", value)
        if digits:
            return int(digits)
    return default


def _won(n: int) -> str:
    return f"{int(n):,}원"


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_json_payload(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}


def _minutes(h: int, m: int) -> int:
    return h * 60 + m


def _parse_time_range(text: str) -> tuple[int, int] | None:
    match = _TIME_RE.search(text or "")
    if not match:
        return None
    start = _minutes(int(match.group(1)), int(match.group(2)))
    end = _minutes(int(match.group(3)), int(match.group(4)))
    if end <= start:
        end += 24 * 60
    return start, end


def _rewrite_basis(basis: str, *, qty: int | None = None, price: int | None = None) -> str:
    text = basis or ""
    match = _BASIS_RE.search(text)
    if not match:
        return text
    new_qty = qty if qty is not None else _to_int(match.group("qty"))
    new_price = price if price is not None else _to_int(match.group("price"))
    unit = match.group("unit") or ""
    replacement = f"{new_qty}{unit} × {new_price:,}원"
    return f"{text[: match.start()]}{replacement}{text[match.end() :]}"


def _parse_qty_price_basis(basis: str) -> re.Match[str] | None:
    """수량×단가(원) 산출식만 반환합니다. 크기 표기·견적 메모는 제외합니다."""
    text = basis or ""
    match = _BASIS_RE.search(text)
    if not match:
        return None
    # '3m × 50,000원'처럼 숫자와 × 사이에 길이 단위가 끼면 산출식이 아닙니다.
    between = text[match.start("qty") + len(match.group("qty")) : match.start("price")]
    if re.search(_LENGTH_UNIT, between, re.I):
        return None
    return match


def _option(
    *,
    oid: str,
    label: str,
    before: str,
    after: str,
    patches: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": oid,
        "label": label,
        "before": before,
        "after": after,
        "patches": patches,
    }


def _issue(
    *,
    iid: str,
    location: str,
    field: str,
    problem: str,
    guideline: str,
    options: list[dict[str, Any]] | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    opts = options or []
    first = opts[0] if opts else {}
    return {
        "id": iid,
        "severity": severity,
        "location": location,
        "field": field,
        "problem": problem,
        "guideline": guideline,
        "before": str(first.get("before") or ""),
        "after": str(first.get("after") or ""),
        "patch": (first.get("patches") or [None])[0] if first.get("patches") else None,
        "options": opts,
    }


def _check_budget_lines(
    lines: list[Any],
    *,
    attendees: int | None,
    limit: int | None,
    prefix: str,
    path_prefix: str,
    verified: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    total = 0
    for idx, raw in enumerate(lines):
        row = _as_dict(raw)
        name = str(row.get("name") or f"항목 {idx + 1}")
        basis = str(row.get("basis") or "")
        unit_price = _to_int(row.get("unit_price"))
        quantity = _to_int(row.get("quantity"), 1)
        total += unit_price * quantity
        loc = f"{prefix} > {name}"

        # 금액은 단가×수량으로 자동 계산되는 값이라 모순 대상이 아닙니다.
        # 아래 수정안에서 함께 갱신만 해 줍니다.
        has_amount = row.get("amount") is not None

        match = _parse_qty_price_basis(basis)
        basis_qty = _to_int(match.group("qty")) if match else 0
        basis_price = _to_int(match.group("price")) if match else 0
        unit = (match.group("unit") if match else "") or ""
        unit_label = unit or "개"
        qty_conflict = bool(match and basis_qty and quantity != basis_qty)
        price_conflict = bool(match and basis_price and unit_price != basis_price)

        # 예산 항목의 산술 대조는 결정적 검사가 전담합니다.
        # '견적 기준'·크기 메모처럼 산출식이 없어도 LLM이 지어낸 모순을 막기 위해
        # 항목 자체를 판정 완료로 표시합니다.
        if verified is not None:
            verified.append((f"{path_prefix}.{idx}", name))

        if qty_conflict and price_conflict:
            to_basis_patches: list[dict[str, Any]] = [
                {"path": f"{path_prefix}.{idx}.quantity", "value": basis_qty},
                {"path": f"{path_prefix}.{idx}.unit_price", "value": basis_price},
            ]
            if has_amount:
                to_basis_patches.append(
                    {"path": f"{path_prefix}.{idx}.amount", "value": basis_price * basis_qty}
                )
            new_basis = _rewrite_basis(basis, qty=quantity, price=unit_price)
            issues.append(
                _issue(
                    iid=f"{path_prefix}-{idx}-basis",
                    location=loc,
                    field=f"{path_prefix}.{idx}",
                    problem=(
                        f"수량이 {quantity}{unit_label}·단가 {_won(unit_price)}인데 "
                        f"산출 근거는 {basis_qty}{unit_label} × {_won(basis_price)}입니다."
                    ),
                    guideline="입력값과 산출 근거 중 맞는 쪽 하나를 선택하세요.",
                    options=[
                        _option(
                            oid="fields-to-basis",
                            label=f"수량 {quantity}→{basis_qty}, 단가 {_won(unit_price)}→{_won(basis_price)}로 변경",
                            before=f"수량 {quantity}{unit_label} · 단가 {_won(unit_price)}",
                            after=f"수량 {basis_qty}{unit_label} · 단가 {_won(basis_price)}",
                            patches=to_basis_patches,
                        ),
                        _option(
                            oid="basis-to-fields",
                            label=f"산출 근거를 {quantity}{unit_label} × {_won(unit_price)}로 변경",
                            before=basis,
                            after=new_basis,
                            patches=[{"path": f"{path_prefix}.{idx}.basis", "value": new_basis}],
                        ),
                    ],
                )
            )
        elif qty_conflict:
            qty_patches = [{"path": f"{path_prefix}.{idx}.quantity", "value": basis_qty}]
            if has_amount:
                qty_patches.append(
                    {"path": f"{path_prefix}.{idx}.amount", "value": unit_price * basis_qty}
                )
            new_basis = _rewrite_basis(basis, qty=quantity)
            issues.append(
                _issue(
                    iid=f"{path_prefix}-{idx}-qty",
                    location=loc,
                    field=f"{path_prefix}.{idx}.quantity",
                    problem=(
                        f"수량이 {quantity}{unit_label}인데 산출 근거는 "
                        f"{basis_qty}{unit_label}로 되어 있습니다."
                    ),
                    guideline="수량과 산출 근거 중 맞는 쪽을 선택하세요.",
                    options=[
                        _option(
                            oid="qty-to-basis",
                            label=f"수량을 {quantity} → {basis_qty}로 변경",
                            before=f"수량 {quantity}{unit_label}",
                            after=f"수량 {basis_qty}{unit_label}",
                            patches=qty_patches,
                        ),
                        _option(
                            oid="basis-to-qty",
                            label=f"산출 근거를 {basis_qty}{unit_label} → {quantity}{unit_label}로 변경",
                            before=basis,
                            after=new_basis,
                            patches=[{"path": f"{path_prefix}.{idx}.basis", "value": new_basis}],
                        ),
                    ],
                )
            )
        elif price_conflict:
            price_patches = [{"path": f"{path_prefix}.{idx}.unit_price", "value": basis_price}]
            if has_amount:
                price_patches.append(
                    {"path": f"{path_prefix}.{idx}.amount", "value": basis_price * quantity}
                )
            new_basis = _rewrite_basis(basis, price=unit_price)
            issues.append(
                _issue(
                    iid=f"{path_prefix}-{idx}-price",
                    location=loc,
                    field=f"{path_prefix}.{idx}.unit_price",
                    problem=(
                        f"단가가 {_won(unit_price)}인데 산출 근거는 {_won(basis_price)}로 되어 있습니다."
                    ),
                    guideline="단가와 산출 근거 중 맞는 쪽을 선택하세요.",
                    options=[
                        _option(
                            oid="price-to-basis",
                            label=f"단가를 {_won(unit_price)} → {_won(basis_price)}로 변경",
                            before=f"단가 {_won(unit_price)}",
                            after=f"단가 {_won(basis_price)}",
                            patches=price_patches,
                        ),
                        _option(
                            oid="basis-to-price",
                            label=f"산출 근거 단가를 {_won(basis_price)} → {_won(unit_price)}로 변경",
                            before=basis,
                            after=new_basis,
                            patches=[{"path": f"{path_prefix}.{idx}.basis", "value": new_basis}],
                        ),
                    ],
                )
            )

        if (
            not qty_conflict
            and attendees
            and quantity
            and attendees != quantity
            and any(token in name for token in ("다과", "음료", "간식", "리플렛", "홍보물"))
        ):
            issues.append(
                _issue(
                    iid=f"{path_prefix}-{idx}-attendees",
                    location=loc,
                    field=f"{path_prefix}.{idx}.quantity",
                    severity="warn",
                    problem=f"예상 참석 인원이 {attendees}명인데 {name} 수량은 {quantity}입니다.",
                    guideline="참석 인원과 수량 중 실제 기준에 맞는 쪽을 선택하세요.",
                    options=[
                        _option(
                            oid="qty-to-attendees",
                            label=f"수량을 {quantity} → {attendees}로 변경",
                            before=f"수량 {quantity}",
                            after=f"수량 {attendees}",
                            patches=[{"path": f"{path_prefix}.{idx}.quantity", "value": attendees}],
                        ),
                        _option(
                            oid="attendees-to-qty",
                            label=f"참석 인원을 {attendees}명 → {quantity}명으로 변경",
                            before=f"참석 인원 {attendees}명",
                            after=f"참석 인원 {quantity}명",
                            patches=[{"path": "attendees", "value": str(quantity)}],
                        ),
                    ],
                )
            )

    if limit and total > limit:
        issues.append(
            _issue(
                iid=f"{path_prefix}-over-limit",
                location=prefix,
                field="budget_limit" if path_prefix == "budget_lines" else "allocated_budget",
                severity="warn",
                problem=f"예산 합계 {_won(total)}이 한도 {_won(limit)}를 초과합니다.",
                guideline="한도를 올리거나, 항목 금액을 줄인 뒤 다시 생성하세요. 자동으로 한쪽만 맞출 수 없는 경우입니다.",
                options=[],
            )
        )
    return issues


def _check_programs(programs: list[Any], schedule: str) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    parsed: list[tuple[int, int, int, str]] = []
    for idx, raw in enumerate(programs):
        row = _as_dict(raw)
        time_text = str(row.get("time") or "")
        content = str(row.get("content") or f"일정 {idx + 1}")
        span = _parse_time_range(time_text)
        if span:
            parsed.append((span[0], span[1], idx, content))

    window = _parse_time_range(schedule)
    if window:
        ws, we = window
        for start, end, idx, content in parsed:
            if start < ws or end > we:
                issues.append(
                    _issue(
                        iid=f"programs-{idx}-window",
                        location=f"세부일정 > {content}",
                        field=f"programs.{idx}.time",
                        severity="warn",
                        problem=f"세부일정 시간({_as_dict(programs[idx]).get('time') or ''})이 전체 행사 일시와 어긋납니다.",
                        guideline="세부일정은 행사 시작·종료 시각 안에 들어가도록 맞추세요.",
                        options=[],
                    )
                )

    parsed.sort()
    for i in range(1, len(parsed)):
        prev_s, prev_e, prev_i, prev_c = parsed[i - 1]
        cur_s, cur_e, cur_i, cur_c = parsed[i]
        if cur_s < prev_e:
            issues.append(
                _issue(
                    iid=f"programs-overlap-{prev_i}-{cur_i}",
                    location="세부일정",
                    field=f"programs.{cur_i}.time",
                    problem=f"「{prev_c}」와 「{cur_c}」 시간이 겹칩니다.",
                    guideline="앞 일정이 끝난 뒤에 다음 일정이 시작되도록 시각을 조정하세요.",
                    options=[],
                )
            )
    return issues


def _deterministic_issues(
    kind: str,
    payload: dict[str, Any],
    verified: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    attendees = _to_int(payload.get("attendees")) or None
    schedule = str(payload.get("schedule") or "")

    if kind in ("briefing", "budget"):
        if kind == "briefing":
            lines = _as_list(payload.get("budget_lines"))
            limit = _to_int(payload.get("budget_limit")) or None
            issues.extend(
                _check_budget_lines(
                    lines,
                    attendees=attendees,
                    limit=limit,
                    prefix="예산",
                    path_prefix="budget_lines",
                    verified=verified,
                )
            )
        else:
            lines = _as_list(payload.get("items"))
            limit = _to_int(payload.get("allocated_budget")) or None
            issues.extend(
                _check_budget_lines(
                    lines,
                    attendees=None,
                    limit=limit,
                    prefix="예산안",
                    path_prefix="items",
                    verified=verified,
                )
            )

    if kind in ("briefing", "visit", "fair"):
        issues.extend(_check_programs(_as_list(payload.get("programs")), schedule))

    return issues


def _normalize_options(item: dict[str, Any]) -> list[dict[str, Any]]:
    raw_opts = item.get("options")
    options: list[dict[str, Any]] = []
    if isinstance(raw_opts, list):
        for idx, raw in enumerate(raw_opts):
            opt = _as_dict(raw)
            patches_raw = opt.get("patches")
            patches: list[dict[str, Any]] = []
            if isinstance(patches_raw, list):
                patches = [p for p in (_as_dict(x) for x in patches_raw) if p.get("path")]
            elif isinstance(opt.get("patch"), dict) and opt["patch"].get("path"):
                patches = [opt["patch"]]
            label = str(opt.get("label") or opt.get("after") or f"수정안 {idx + 1}").strip()
            if not label:
                continue
            options.append(
                _option(
                    oid=str(opt.get("id") or f"opt-{idx}"),
                    label=label,
                    before=str(opt.get("before") or ""),
                    after=str(opt.get("after") or ""),
                    patches=patches,
                )
            )
    if options:
        return options
    patch = item.get("patch") if isinstance(item.get("patch"), dict) else None
    if patch and patch.get("path"):
        return [
            _option(
                oid="suggested",
                label=str(item.get("after") or "제안대로 수정"),
                before=str(item.get("before") or ""),
                after=str(item.get("after") or ""),
                patches=[patch],
            )
        ]
    return []


# 자동 계산 값. 모델이 검산하다 없는 모순을 만들어 내지 않도록 숨깁니다.
_DERIVED_LINE_FIELDS = ("amount", "total", "sum")
_DERIVED_TOP_FIELDS = ("allocated_budget", "budget_limit", "total", "total_amount", "remaining")


def _strip_derived(payload: dict[str, Any]) -> dict[str, Any]:
    """LLM에 보낼 사본에서 자동 계산 필드를 걷어냅니다."""
    clean = {
        key: value for key, value in payload.items() if key not in _DERIVED_TOP_FIELDS
    }
    for key in ("items", "budget_lines"):
        rows = clean.get(key)
        if not isinstance(rows, list):
            continue
        clean[key] = [
            {k: v for k, v in _as_dict(row).items() if k not in _DERIVED_LINE_FIELDS}
            for row in rows
        ]
    return clean


def _targets_derived_value(field: str, problem: str) -> bool:
    """자동 계산 값을 두고 시비를 거는 지적인지 판단합니다."""
    leaf = _normalize_field_path(field).rsplit(".", 1)[-1]
    if leaf in _DERIVED_LINE_FIELDS or leaf in _DERIVED_TOP_FIELDS:
        return True
    if field:
        return False
    # field 없이 문장만 온 경우엔 문구로 거릅니다.
    return any(
        token in problem
        for token in ("총액", "합계", "총 예산", "총예산", "배정 예산", "배정예산", "잔액", "잔여")
    )


_BRACKET_INDEX_RE = re.compile(r"\[(\d+)\]")


def _normalize_field_path(field: str) -> str:
    """모델이 items[0].quantity처럼 돌려줘도 items.0.quantity로 맞춥니다."""
    return _BRACKET_INDEX_RE.sub(r".\1", field.strip()).replace("..", ".")


def _reopens_settled_line(
    field: str,
    location: str,
    problem: str,
    settled: list[tuple[str, str]],
) -> bool:
    """산술 판정이 끝난 예산 항목을 LLM이 다시 문제 삼는지 봅니다."""
    field = _normalize_field_path(field)
    for path, name in settled:
        if field == path or field.startswith(f"{path}."):
            return True
        # 항목명이 보이면 산술·근거 관련 재지적은 모두 버립니다.
        if name and (name in location or name in problem):
            return True
    return False


def _llm_content_issues(
    kind: str,
    payload: dict[str, Any],
    existing: list[dict[str, Any]],
    settled: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    llm = get_llm_service()
    if llm.provider == "mock":
        return []
    seen_ids = {str(item["id"]) for item in existing}
    seen_keys = {
        (str(item.get("location") or ""), str(item.get("field") or "").rsplit(".", 1)[0])
        for item in existing
    }
    user = (
        f"문서 종류: {kind}\n"
        f"이미 보고한 위치: {[item.get('location') for item in existing] or '없음'}\n"
        f"단가·수량·산출 근거 판정을 이미 마친 항목: "
        f"{[name for _, name in settled] or '없음'}\n"
        "아래 문서 JSON에서 아직 없는 추가 내부 모순만 찾아 JSON으로 답하세요. "
        "위에 적힌 항목의 단가·수량·산출 근거는 다시 계산하거나 지적하지 마세요. "
        "산출 근거에 수량×단가(원) 식이 없으면 비교하지 마세요. "
        "'견적 기준'·크기 규격 같은 메모는 모순이 아닙니다. "
        "금액·합계 같은 자동 계산 값은 JSON에 없으니 만들어 내지 마세요.\n\n"
        f"{json.dumps(_strip_derived(payload), ensure_ascii=False, indent=2)[:8000]}"
    )
    raw = llm.chat([{"role": "user", "content": user}], system=CONTENT_SYSTEM_PROMPT)
    data = _parse_json_payload(raw)
    rows = data.get("issues")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        item = _as_dict(row)
        iid = str(item.get("id") or f"llm-{idx}")
        location = str(item.get("location") or "문서")
        field = str(item.get("field") or "")
        key = (location, field.rsplit(".", 1)[0] if field else location)
        if iid in seen_ids or key in seen_keys:
            continue
        problem = str(item.get("problem") or "").strip()
        if not problem:
            continue
        if _targets_derived_value(field, problem):
            continue
        if _reopens_settled_line(field, location, problem, settled):
            continue
        seen_ids.add(iid)
        seen_keys.add(key)
        out.append(
            _issue(
                iid=iid,
                location=location,
                field=field,
                problem=problem,
                guideline=str(item.get("guideline") or "어느 쪽 값이 맞는지 선택하세요."),
                options=_normalize_options(item),
                severity=item.get("severity") if item.get("severity") in ("error", "warn") else "warn",
            )
        )
    return out


def check_content_consistency(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    # 결정적 검사가 산출 근거까지 대조한 예산 항목. LLM 재검토 대상에서 뺍니다.
    settled: list[tuple[str, str]] = []
    issues = _deterministic_issues(kind, payload, settled)
    issues.extend(_llm_content_issues(kind, payload, issues, settled))
    errors = sum(1 for item in issues if item.get("severity") == "error")
    warns = sum(1 for item in issues if item.get("severity") != "error")
    return {
        "kind": kind,
        "ok": len(issues) == 0,
        "issues": issues,
        "summary": {"total": len(issues), "errors": errors, "warnings": warns},
    }


def _payload_query(kind: str, payload: dict[str, Any]) -> str:
    labels = {
        "briefing": "입시설명회 운영계획서 예산 집행지침 구매규정 여비 수당 다과비 홍보물",
        "budget": "예산안 예산 집행지침 구매규정 여비 수당 견적서 다과비 홍보물 리플렛",
        "visit": "고교 방문 홍보 출장 여비규정",
        "fair": "입학 박람회 부스 홍보 출장 여비 구매",
    }
    bits = [labels.get(kind, "입학 행정 규정"), str(payload.get("event_name") or payload.get("title") or "")]
    if payload.get("department"):
        bits.append(str(payload["department"]))
    for row in _as_list(payload.get("budget_lines") or payload.get("items")):
        rec = _as_dict(row)
        bits.append(str(rec.get("name") or ""))
        bits.append(str(rec.get("basis") or ""))
    for row in _as_list(payload.get("programs")):
        rec = _as_dict(row)
        bits.append(str(rec.get("content") or ""))
    return " ".join(part for part in bits if part).strip()


# 문서 종류별 규정 검색 우선 카테고리. 모집요강은 예산 항목(다과·리플렛 등) 근거로 쓰지 않습니다.
_REGULATION_CATEGORIES: dict[str, list[str]] = {
    "budget": ["예산·행정 규정", "문서 양식", "재무현황"],
    "briefing": ["예산·행정 규정", "문서 양식", "재무현황"],
    "visit": ["예산·행정 규정", "입학처 공지"],
    "fair": ["예산·행정 규정", "문서 양식", "입학처 공지"],
}
_EXCLUDE_FROM_BUDGET_REGS = ("모집요강",)

TITLE_RELEVANCE_SYSTEM = (
    "당신은 행정문서 규정 검토용 참고자료를 고르는 담당자입니다. "
    "문서 종류·예산 항목과 제목·카테고리가 실제로 관련된 것만 relevant_ids에 넣으세요. "
    "예산안·계획서의 다과비·홍보물·리플렛·수당·여비 검토에 모집요강·전형요강은 관련 없습니다. "
    "예산·행정 규정, 구매/여비/집행 지침, 견적·수당 관련 문서가 우선입니다. "
    "반드시 JSON만 출력하세요: "
    '{"relevant_ids":[1,2],"rejected":[{"id":3,"reason":"모집요강으로 예산 항목과 무관"}]}'
)


def _regulation_search_chunks(
    db: Session, kind: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """종류에 맞는 카테고리에서만 규정 청크를 가져옵니다."""
    query = _payload_query(kind, payload)
    preferred = _REGULATION_CATEGORIES.get(kind, ["예산·행정 규정"])
    chunks = retrieve_relevant_chunks(db, query, top_k=16, categories=preferred)
    # 우선 카테고리가 비면 모집요강만 빼고 넓힙니다.
    if len(chunks) < 3 and kind in ("budget", "briefing"):
        extra = retrieve_relevant_chunks(
            db,
            query,
            top_k=16,
            exclude_categories=list(_EXCLUDE_FROM_BUDGET_REGS),
        )
        seen = {c["document_id"] for c in chunks}
        for row in extra:
            if row["document_id"] in seen:
                continue
            chunks.append(row)
            seen.add(row["document_id"])
        chunks.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
        chunks = chunks[:16]
    return chunks


def _heuristic_title_relevant(kind: str, filename: str, category: str) -> bool:
    name = (filename or "").lower()
    cat = (category or "").strip()
    if kind in ("budget", "briefing"):
        if cat in _EXCLUDE_FROM_BUDGET_REGS or cat == "모집요강":
            return False
        if any(token in name for token in ("모집요강", "수시모집", "정시모집", "입학전형요강")):
            return False
        if cat in ("예산·행정 규정", "문서 양식", "재무현황"):
            return True
    return True


def _filter_chunks_by_title_relevance(
    kind: str,
    payload: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """임베딩 후보를 문서 제목·카테고리 관련도로 한 번 더 거릅니다."""
    if not chunks:
        return []

    docs: dict[int, dict[str, Any]] = {}
    for chunk in chunks:
        doc_id = chunk.get("document_id")
        if doc_id is None or doc_id in docs:
            continue
        docs[int(doc_id)] = {
            "id": int(doc_id),
            "filename": chunk.get("filename") or "",
            "category": chunk.get("category") or "기타",
        }

    # 휴리스틱으로 명백히 무관한 모집요강류를 먼저 제거합니다.
    kept_ids = {
        doc_id
        for doc_id, meta in docs.items()
        if _heuristic_title_relevant(kind, str(meta["filename"]), str(meta["category"]))
    }

    llm = get_llm_service()
    if llm.provider != "mock" and docs:
        item_names = [
            str(_as_dict(row).get("name") or "").strip()
            for row in _as_list(payload.get("budget_lines") or payload.get("items"))
        ]
        item_names = [name for name in item_names if name]
        catalog = [
            {
                "id": meta["id"],
                "filename": meta["filename"],
                "category": meta["category"],
            }
            for meta in docs.values()
        ]
        user = (
            f"문서 종류: {kind}\n"
            f"문서 제목: {payload.get('title') or payload.get('event_name') or ''}\n"
            f"예산 항목: {item_names or '없음'}\n"
            "아래 후보 중 이 문서 검토에 실제로 쓸 자료의 id만 relevant_ids에 넣으세요.\n\n"
            f"{json.dumps(catalog, ensure_ascii=False)}"
        )
        try:
            raw = llm.chat([{"role": "user", "content": user}], system=TITLE_RELEVANCE_SYSTEM)
            data = _parse_json_payload(raw)
            relevant = data.get("relevant_ids")
            if isinstance(relevant, list) and relevant:
                parsed: set[int] = set()
                for value in relevant:
                    try:
                        parsed.add(int(value))
                    except (TypeError, ValueError):
                        continue
                # 모집요강 등 휴리스틱 탈락분은 LLM이 골라도 다시 넣지 않습니다.
                llm_kept = {
                    doc_id
                    for doc_id in parsed
                    if doc_id in docs
                    and _heuristic_title_relevant(
                        kind,
                        str(docs[doc_id]["filename"]),
                        str(docs[doc_id]["category"]),
                    )
                }
                if llm_kept:
                    kept_ids = llm_kept
        except Exception:  # noqa: BLE001
            logger.exception("문서 제목 관련도 판별 실패 — 휴리스틱만 적용")

    if not kept_ids:
        return []
    return [chunk for chunk in chunks if chunk.get("document_id") in kept_ids]


def _numbered_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""
    parts = []
    for i, c in enumerate(chunks, 1):
        cat = c.get("category") or "기타"
        parts.append(f"[{i}] ({cat}) {c.get('filename')}\n{c.get('content')}")
    return (
        "다음은 내부 규정·자료 DB에서 RAG로 검색된 근거입니다. "
        "카테고리·제목이 이 문서와 관련된 자료만 골라 두었습니다. "
        "이 내용에 없는 사실은 위반으로 단정하지 마세요.\n\n"
        + "\n\n---\n\n".join(parts)
    )


def _clip_quote(text: str, limit: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


_STOCK_CHECK_NOTE_RE = re.compile(
    r"^이 문서의 「[^」]*」 부분은 규정( 「[^」]*」)?과 대조해 검토가 필요함$"
)


def _is_substantive_check_reason(text: str) -> bool:
    """검토 필요 사유로 쓸 수 있는지. 기준을 낮춰 대부분을 통과시킵니다."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if len(t) < 6:
        return False
    if _STOCK_CHECK_NOTE_RE.fullmatch(t):
        return False
    if re.fullmatch(r"(검토|확인)(가|이)?\s*필요(합니다?|함)?\.?", t):
        return False
    return True


def _looks_clear_violation(item: dict[str, Any]) -> bool:
    """명백한 규정 충돌인지. 애매하면 False → check로 내립니다."""
    doc = str(item.get("document_excerpt") or "").strip()
    reg = str(item.get("regulation_excerpt") or "").strip()
    reason = str(item.get("reason") or item.get("mismatch_note") or "").strip()
    if not doc or not reg:
        return False
    strong = (
        "초과",
        "위반",
        "금지",
        "불가",
        "의무",
        "첨부",
        "이상",
        "이하",
        "한도",
        "필수",
        "해야",
        "않아",
        "없다",
        "없으며",
        "모순",
        "충돌",
    )
    blob = f"{reason} {doc} {reg}"
    if not any(tok in blob for tok in strong):
        return False
    # 규정·문서에 숫자가 함께 있으면 한도/금액 충돌 가능성이 큼
    if _NUM.search(doc) and _NUM.search(reg):
        return True
    return any(tok in reason for tok in ("위반", "금지", "불가", "초과", "모순", "충돌", "의무"))


def _compose_mismatch_note(
    status: str,
    document_excerpt: str,
    regulation_excerpt: str,
    fallback: str = "",
    *,
    reason: str = "",
) -> str:
    doc = _clip_quote(document_excerpt, 80) or "해당 기재"
    reg = _clip_quote(regulation_excerpt, 90)
    why = _clip_quote(reason or fallback, 180)
    if status == "violation":
        if reg:
            return f'이 문서의 「{doc}」 부분이 규정 「{reg}」에 맞지 않음'
        return f'이 문서의 「{doc}」 부분이 규정에 맞지 않음'
    if status == "check":
        if why and _is_substantive_check_reason(why):
            if reg:
                return f"검토 필요 이유: {why} (문서 「{doc}」 ↔ 규정 「{reg}」)"
            return f"검토 필요 이유: {why} (문서 「{doc}」)"
        if reg:
            return f'이 문서의 「{doc}」 부분은 규정 「{reg}」과 대조해 검토가 필요함'
        return f'이 문서의 「{doc}」 부분은 규정과 대조해 검토가 필요함'
    return fallback or f'이 문서의 「{doc}」 부분을 확인하세요.'


def _normalize_finding(item: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, Any] | None:
    status = item.get("status") if item.get("status") in ("violation", "check") else "check"
    citation_n = item.get("citation_n")
    try:
        citation_n = int(citation_n) if citation_n is not None else None
    except (TypeError, ValueError):
        citation_n = None
    title = str(item.get("regulation_title") or "").strip()
    if not title and citation_n and 1 <= citation_n <= len(chunks):
        title = str(chunks[citation_n - 1].get("filename") or "")
    document_excerpt = _clip_quote(
        str(item.get("document_excerpt") or item.get("problem") or ""),
        220,
    )
    regulation_excerpt = _clip_quote(str(item.get("regulation_excerpt") or ""), 360)
    if not regulation_excerpt and citation_n and 1 <= citation_n <= len(chunks):
        regulation_excerpt = _clip_quote(str(chunks[citation_n - 1].get("content") or ""), 360)

    reason = str(item.get("reason") or "").strip()
    note = str(item.get("mismatch_note") or item.get("explanation") or "").strip()
    if not reason and note:
        reason = note

    # 애매한 위반은 검토 필요로 내림 (위반 기준을 빡세게)
    if status == "violation" and not _looks_clear_violation(
        {
            "document_excerpt": document_excerpt,
            "regulation_excerpt": regulation_excerpt,
            "reason": reason or note,
            "mismatch_note": note,
        }
    ):
        status = "check"
        if not reason:
            reason = "규정 문장과 문서 기재를 담당자가 대조해 적합 여부를 확인할 필요가 있음"

    if status == "check" and not reason:
        if regulation_excerpt or title:
            reason = (
                f"관련 규정「{title or '내부 규정'}」과 문서 기재를 대조·확인할 필요가 있음"
            )
        else:
            reason = "관련 규정과 문서 기재를 담당자가 확인할 필요가 있음"

    if status == "check" and not _is_substantive_check_reason(reason):
        reason = "관련 규정과 문서 기재를 담당자가 대조·확인할 필요가 있음"

    if status == "violation":
        if "「" not in note:
            note = _compose_mismatch_note(status, document_excerpt, regulation_excerpt, note)
    else:
        note = _compose_mismatch_note(
            status,
            document_excerpt,
            regulation_excerpt,
            reason=reason,
        )

    if not document_excerpt and not regulation_excerpt and not reason:
        return None
    return {
        "status": status,
        "location": str(item.get("location") or "문서"),
        "problem": note,
        "document_excerpt": document_excerpt,
        "regulation_title": title,
        "citation_n": citation_n,
        "regulation_excerpt": regulation_excerpt,
        "reason": _clip_quote(reason, 220) if reason else "",
        "mismatch_note": note,
        "explanation": note,
    }


def _payload_document_excerpt(payload: dict[str, Any]) -> str:
    bits: list[str] = []
    for key in ("event_name", "title", "schedule", "location", "target", "department"):
        val = str(payload.get(key) or "").strip()
        if val:
            bits.append(val)
    for row in _as_list(payload.get("budget_lines") or payload.get("items"))[:4]:
        rec = _as_dict(row)
        name = str(rec.get("name") or "").strip()
        if name:
            bits.append(name)
    for row in _as_list(payload.get("programs"))[:3]:
        rec = _as_dict(row)
        content = str(rec.get("content") or "").strip()
        if content:
            bits.append(content)
    return _clip_quote(" / ".join(bits), 180) or "문서 본문"


def _fallback_regulation_findings(
    chunks: list[dict[str, Any]], payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """LLM 실패·빈 결과 시에도 관련 규정별로 검토 필요를 남깁니다."""
    doc_excerpt = _payload_document_excerpt(payload)
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for idx, chunk in enumerate(chunks[:8], start=1):
        title = str(chunk.get("filename") or "내부 규정").strip() or "내부 규정"
        if title in seen:
            continue
        seen.add(title)
        reg_excerpt = _clip_quote(str(chunk.get("content") or ""), 280)
        reason = (
            f"관련 규정「{title}」과 문서 기재를 담당자가 대조·확인할 필요가 있음"
        )
        findings.append(
            {
                "status": "check",
                "location": "규정 대조",
                "problem": f"검토 필요 이유: {reason}",
                "document_excerpt": doc_excerpt,
                "regulation_title": title,
                "citation_n": idx,
                "regulation_excerpt": reg_excerpt,
                "reason": reason,
                "mismatch_note": f"검토 필요 이유: {reason} (문서 「{doc_excerpt}」)",
                "explanation": f"검토 필요 이유: {reason}",
            }
        )
        if len(findings) >= 5:
            break
    return findings


def _attach_reference_mismatches(
    refs: list[dict[str, Any]],
    findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        name = str(finding.get("regulation_title") or "").strip()
        if name:
            by_name.setdefault(name, []).append(finding)
    out: list[dict[str, Any]] = []
    for ref in refs:
        filename = str(ref.get("filename") or "")
        related = by_name.get(filename, [])
        mismatch_parts: list[str] = []
        verdict = None
        for finding in related:
            quote = finding.get("regulation_excerpt") or finding.get("mismatch_note")
            if quote:
                mismatch_parts.append(str(quote))
            if finding.get("status") == "violation":
                verdict = "violation"
            elif verdict is None:
                verdict = "check"
        out.append(
            {
                "document_id": ref.get("document_id"),
                "filename": filename,
                "category": ref.get("category") or "기타",
                "relevance": ref.get("relevance"),
                "score": ref.get("score"),
                "snippet": ref.get("snippet"),
                "mismatch_excerpt": _clip_quote(" / ".join(mismatch_parts), 280)
                if mismatch_parts
                else _clip_quote(str(ref.get("snippet") or ""), 220),
                "verdict": verdict,
                "updated_at": ref.get("updated_at").isoformat()
                if hasattr(ref.get("updated_at"), "isoformat")
                else ref.get("updated_at"),
            }
        )
    out.sort(key=lambda r: int(r.get("relevance") or 0), reverse=True)
    return out


def review_plan_regulations(db: Session, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    raw_chunks = _regulation_search_chunks(db, kind, payload)
    chunks = _filter_chunks_by_title_relevance(kind, payload, raw_chunks)
    refs = aggregate_document_references(chunks, limit=6)
    context = _numbered_context(chunks[:8])

    findings: list[dict[str, Any]] = []
    if not chunks:
        findings.append(
            {
                "status": "check",
                "location": "규정 검토",
                "problem": "관련 카테고리(예산·행정 규정 등)에서 이 문서와 맞는 근거를 찾지 못했습니다.",
                "document_excerpt": "",
                "regulation_title": "",
                "citation_n": None,
                "regulation_excerpt": "",
                "reason": "예산·행정 관련 규정 자료가 없거나, 제목 관련도 검토에서 제외되어 적합 여부를 판단할 수 없음",
                "mismatch_note": "검토 필요 이유: 예산·행정 관련 규정 자료가 없거나, 제목 관련도 검토에서 제외되어 적합 여부를 판단할 수 없음",
                "explanation": "규정·자료 관리의 「예산·행정 규정」 등에 관련 문서를 등록한 뒤 다시 검토하세요.",
            }
        )
    else:
        llm = get_llm_service()
        system = f"{REGULATION_SYSTEM_PROMPT}\n\n{context}"
        user = (
            f"문서 종류: {kind}\n"
            "행정문서 JSON과 규정 원문을 한 문장씩 대조하세요. "
            "violation은 규정과 문서가 명백히 충돌할 때만. "
            "애매하거나 확인이 필요하면 대부분 check로 올리세요. "
            "관련 규정 청크가 있으면 findings를 거의 비우지 마세요. "
            "모집요강·전형요강 인용은 예산 항목(다과비·홍보물 등) 검토에 쓰지 마세요. "
            "문서 구절과 규정 구절을 그대로 인용하세요.\n\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)[:7000]}"
        )
        rows: list[Any] = []
        parsed_ok = False
        if llm.provider != "mock":
            raw = llm.chat([{"role": "user", "content": user}], system=system)
            data = _parse_json_payload(raw)
            parsed_ok = isinstance(data.get("findings"), list)
            rows = data.get("findings") if parsed_ok else []
        for row in rows:
            normalized = _normalize_finding(_as_dict(row), chunks)
            if normalized:
                findings.append(normalized)
        # LLM이 거의 안 올리거나 실패하면 관련 규정별 검토 필요로 채움
        if len(findings) < 2:
            existing_titles = {
                str(f.get("regulation_title") or "").strip() for f in findings
            }
            for extra in _fallback_regulation_findings(chunks, payload):
                title = str(extra.get("regulation_title") or "").strip()
                if title and title in existing_titles:
                    continue
                findings.append(extra)
                existing_titles.add(title)
                if len(findings) >= 5:
                    break
        if not findings and (llm.provider == "mock" or not parsed_ok):
            findings.extend(_fallback_regulation_findings(chunks, payload))

    findings.sort(key=lambda f: (0 if f.get("status") == "violation" else 1, f.get("citation_n") or 99))
    references = _attach_reference_mismatches(refs, findings)
    violations = sum(1 for item in findings if item.get("status") == "violation")
    checks = sum(1 for item in findings if item.get("status") != "violation")
    return {
        "kind": kind,
        "ok": len(findings) == 0,
        "findings": findings,
        "references": references,
        "summary": {
            "violations": violations,
            "needs_check": checks,
            "reference_count": len(references),
        },
    }
