"""행정문서 작성: 내용 정합성 점검 + 규정 RAG 검토."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.services.llm_service import get_llm_service
from app.services.rag_service import (
    aggregate_document_references,
    retrieve_relevant_chunks,
)

_NUM = re.compile(r"\d[\d,]*")
_BASIS_RE = re.compile(
    r"(?P<qty>\d[\d,]*)\s*(?P<unit>명|개|부|대|식|장|건|매|본)?\s*[×xX*]\s*(?P<price>\d[\d,]*)\s*원"
)
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[~\-–]\s*(\d{1,2}):(\d{2})")

CONTENT_SYSTEM_PROMPT = (
    "당신은 대학 입학처 행정문서를 검토하는 담당자입니다. "
    "제공된 문서 JSON 안에서만 모순을 찾으세요. "
    "인터넷·일반 시세·관행·외부 지식은 절대 사용하지 마세요. "
    "같은 불일치는 한 건만 보고하고, 어느 쪽 값을 고칠지 선택지(options)로 나누세요. "
    "예: 수량 4 vs 산출근거 2대 → 옵션1 수량 4→2, 옵션2 근거 2대→4대. "
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
    "인터넷 검색·일반론·추측·요약으로 대충 넘기지 마세요. "
    "각 건은 문서에서 문제 되는 구절을 그대로 따오고, 규정에서도 해당 문장을 그대로 따오세요. "
    "근거 자료에 없는 내용은 위반으로 단정하지 마세요. "
    "문제가 없으면 findings는 빈 배열입니다. "
    "반드시 JSON만 출력하세요: "
    '{"findings":[{"status":"violation"|"check","location":"예산 > 다과비",'
    '"document_excerpt":"문서에 적힌 문제 구절 그대로",'
    '"regulation_excerpt":"규정 원문 문장 그대로",'
    '"regulation_title":"규정 파일명","citation_n":1,'
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
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    total = 0
    for idx, raw in enumerate(lines):
        row = _as_dict(raw)
        name = str(row.get("name") or f"항목 {idx + 1}")
        basis = str(row.get("basis") or "")
        unit_price = _to_int(row.get("unit_price"))
        quantity = _to_int(row.get("quantity"), 1)
        amount = _to_int(row.get("amount"), unit_price * quantity)
        computed = unit_price * quantity
        total += computed
        loc = f"{prefix} > {name}"

        has_amount = row.get("amount") is not None
        if has_amount and amount != computed:
            issues.append(
                _issue(
                    iid=f"{path_prefix}-{idx}-amount",
                    location=loc,
                    field=f"{path_prefix}.{idx}.amount",
                    problem=f"금액 {_won(amount)}이 단가×수량({_won(computed)})과 다릅니다.",
                    guideline="금액과 단가·수량 중 실제와 맞는 쪽을 선택하세요.",
                    options=[
                        _option(
                            oid="amount-to-computed",
                            label=f"금액을 {_won(amount)} → {_won(computed)}로 변경",
                            before=f"금액 {_won(amount)}",
                            after=f"금액 {_won(computed)}",
                            patches=[{"path": f"{path_prefix}.{idx}.amount", "value": computed}],
                        )
                    ],
                )
            )

        match = _BASIS_RE.search(basis)
        basis_qty = _to_int(match.group("qty")) if match else 0
        basis_price = _to_int(match.group("price")) if match else 0
        unit = (match.group("unit") if match else "") or ""
        unit_label = unit or "개"
        qty_conflict = bool(match and basis_qty and quantity != basis_qty)
        price_conflict = bool(match and basis_price and unit_price != basis_price)

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


def _deterministic_issues(kind: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
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


def _llm_content_issues(
    kind: str,
    payload: dict[str, Any],
    existing: list[dict[str, Any]],
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
        "아래 문서 JSON에서 아직 없는 추가 내부 모순만 찾아 JSON으로 답하세요. "
        "같은 항목의 수량·단가·산출 근거 불일치는 다시 쓰지 마세요.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)[:8000]}"
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
    issues = _deterministic_issues(kind, payload)
    issues.extend(_llm_content_issues(kind, payload, issues))
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
        "briefing": "입시설명회 운영계획서 예산 집행 수당 여비 구매",
        "budget": "예산안 집행 수당 여비 구매 견적",
        "visit": "고교 방문 홍보 출장 여비",
        "fair": "입학 박람회 부스 홍보 출장",
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


def _numbered_context(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""
    parts = [f"[{i}] {c.get('filename')}\n{c.get('content')}" for i, c in enumerate(chunks, 1)]
    return (
        "다음은 내부 규정·자료 DB에서 RAG로 검색된 근거입니다. "
        "이 내용에 없는 사실은 위반으로 단정하지 마세요.\n\n"
        + "\n\n---\n\n".join(parts)
    )


def _clip_quote(text: str, limit: int = 280) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _compose_mismatch_note(
    status: str,
    document_excerpt: str,
    regulation_excerpt: str,
    fallback: str = "",
) -> str:
    doc = _clip_quote(document_excerpt, 80) or "해당 기재"
    reg = _clip_quote(regulation_excerpt, 90)
    if status == "violation":
        if reg:
            return f'이 문서의 「{doc}」 부분이 규정 「{reg}」에 맞지 않음'
        return f'이 문서의 「{doc}」 부분이 규정에 맞지 않음'
    if status == "check":
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
    note = str(item.get("mismatch_note") or item.get("explanation") or "").strip()
    if "「" not in note:
        note = _compose_mismatch_note(status, document_excerpt, regulation_excerpt, note)
    if not document_excerpt and not regulation_excerpt:
        return None
    return {
        "status": status,
        "location": str(item.get("location") or "문서"),
        "problem": note,
        "document_excerpt": document_excerpt,
        "regulation_title": title,
        "citation_n": citation_n,
        "regulation_excerpt": regulation_excerpt,
        "mismatch_note": note,
        "explanation": note,
    }


def _fallback_regulation_findings(chunks: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
    """LLM이 없거나 결과가 비었을 때, 관련 규정 원문을 인용해 검토 필요로 표시."""
    lines = _as_list(payload.get("budget_lines") or payload.get("items"))
    line_bits = []
    for raw in lines:
        rec = _as_dict(raw)
        name = str(rec.get("name") or "").strip()
        basis = str(rec.get("basis") or "").strip()
        if name:
            line_bits.append((name, f"{name} {basis}".strip()))
    findings: list[dict[str, Any]] = []
    for idx, chunk in enumerate(chunks[:4], 1):
        content = str(chunk.get("content") or "").strip()
        if len(content) < 20:
            continue
        hit = next((pair for pair in line_bits if pair[0] and pair[0] in content), None)
        document_excerpt = hit[1] if hit else str(payload.get("event_name") or payload.get("title") or "작성 문서")
        findings.append(
            {
                "status": "check",
                "location": hit[0] if hit else "문서 전반",
                "document_excerpt": document_excerpt,
                "regulation_excerpt": content,
                "regulation_title": str(chunk.get("filename") or ""),
                "citation_n": idx,
                "mismatch_note": "",
            }
        )
    out: list[dict[str, Any]] = []
    for raw in findings:
        normalized = _normalize_finding(raw, chunks)
        if normalized:
            out.append(normalized)
    return out


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
    query = _payload_query(kind, payload)
    chunks = retrieve_relevant_chunks(db, query, top_k=12)
    refs = aggregate_document_references(chunks, limit=6)
    context = _numbered_context(chunks[:8])

    findings: list[dict[str, Any]] = []
    if not chunks:
        findings.append(
            {
                "status": "check",
                "location": "규정 검토",
                "problem": "내부 규정·자료 DB에서 이 문서와 관련된 근거를 찾지 못했습니다.",
                "document_excerpt": "",
                "regulation_title": "",
                "citation_n": None,
                "regulation_excerpt": "",
                "mismatch_note": "등록된 규정 원문이 없어 이 문서의 적합성 여부를 판단할 수 없음",
                "explanation": "규정·자료 관리에 문서를 등록한 뒤 다시 검토하세요.",
            }
        )
    else:
        llm = get_llm_service()
        system = f"{REGULATION_SYSTEM_PROMPT}\n\n{context}"
        user = (
            f"문서 종류: {kind}\n"
            "행정문서 JSON의 각 항목(예산 단가·수량·산출근거·일정 등)을 규정 원문과 한 문장씩 대조하세요. "
            "요약하지 말고, 문서 구절과 규정 구절을 그대로 인용하세요.\n\n"
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
