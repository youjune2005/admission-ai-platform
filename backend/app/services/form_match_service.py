"""행정문서 PDF 생성 전 RAG 등록 양식(서식) 매칭.

우선순위:
  1. 「문서 양식」 분류 + 파일명/본문이 문서 종류·기입 내용과 맞는 서식
  2. 그 외 분류라도 파일명에 양식·서식·별지·해당 문서유형 키워드가 있는 자료
  3. 매칭 실패·저신뢰도 → 호출측이 기본(하드코딩) PDF 생성기로 폴백

흐름:
  후보 수집 → RAG 유사도 검색 → 규칙 가점 → (선택) LLM으로 구조 추출
  → 양식 구조에 기입값을 채워 Markdown → admin PDF 렌더러
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.db.models import DocumentChunk, UploadedDocument
from app.services.admin_document_pdf_service import generate_admin_document_files
from app.services.form_pdf_service import TuitionStatementFiles
from app.services.llm_service import get_llm_service
from app.services.rag_service import aggregate_document_references, retrieve_relevant_chunks

logger = logging.getLogger(__name__)

# 이 점수 미만이면 양식을 쓰지 않고 기본 생성기로 갑니다.
MIN_MATCH_SCORE = 0.38

KIND_META: dict[str, dict[str, Any]] = {
    "briefing": {
        "label": "입시설명회 운영계획서",
        "doc_type": "계획서",
        "keywords": (
            "운영계획서",
            "설명회 운영",
            "입시설명회",
            "행사 운영계획",
            "설명회계획",
        ),
        "sections_hint": "목적, 행사개요, 세부일정, 업무분장, 예산, 기대효과",
    },
    "budget": {
        "label": "예상 예산안",
        "doc_type": "예산안",
        "keywords": ("예산안", "예상 예산", "예산 편성", "산출내역", "예산서"),
        "sections_hint": "예산 개요, 세부 산출내역(항목·산출근거·단가·수량·금액)",
    },
    "visit": {
        "label": "고교 방문 홍보계획서",
        "doc_type": "계획서",
        "keywords": ("방문 홍보", "홍보계획서", "고교 방문", "학교방문", "방문계획"),
        "sections_hint": "목적, 개요, 세부일정, 업무분장, 준비사항",
    },
    "fair": {
        "label": "박람회 참가계획서",
        "doc_type": "계획서",
        "keywords": ("박람회", "참가계획서", "부스 운영", "대입정보박람회"),
        "sections_hint": "목적, 개요, 부스운영계획, 업무분장, 준비사항",
    },
}

FORM_NAME_HINTS = ("양식", "서식", "별지", "템플릿", "form", "양식지")


@dataclass
class FormMatch:
    document_id: int
    filename: str
    category: str
    score: float
    relevance: int
    snippet: str = ""
    reason: str = ""
    used_form: bool = False
    sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_json_object(text: str) -> dict[str, Any]:
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


def _kind_meta(kind: str) -> dict[str, Any]:
    return KIND_META.get(kind) or KIND_META["briefing"]


def _collect_candidate_ids(db: Session, kind: str) -> list[int]:
    """양식 후보 문서 id. 문서 양식 분류를 최우선으로 모읍니다."""
    meta = _kind_meta(kind)
    keywords: tuple[str, ...] = tuple(meta["keywords"]) + FORM_NAME_HINTS

    indexed_ids = {
        r[0] for r in db.query(DocumentChunk.document_id).distinct().all() if r[0]
    }
    if not indexed_ids:
        return []

    docs = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.id.in_(indexed_ids))
        .filter(UploadedDocument.status.in_(("latest", "needs_update")))
        .all()
    )

    preferred: list[int] = []
    secondary: list[int] = []
    for doc in docs:
        name = (doc.filename or "").lower()
        cat = (getattr(doc, "category", None) or "").strip()
        blob = f"{doc.filename} {getattr(doc, 'summary', '') or ''}"
        is_form_cat = cat == "문서 양식"
        has_form_word = any(h in blob for h in FORM_NAME_HINTS)
        has_kind_word = any(k in blob for k in keywords)

        if is_form_cat or (has_form_word and has_kind_word):
            preferred.append(doc.id)
        elif has_kind_word or has_form_word:
            secondary.append(doc.id)

    # 문서 양식이 비어 있으면 종류 키워드 후보라도 검색합니다.
    ordered = preferred or secondary
    # 중복 제거, 순서 유지
    seen: set[int] = set()
    out: list[int] = []
    for i in ordered:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _build_search_query(kind: str, title: str, payload: dict[str, Any]) -> str:
    meta = _kind_meta(kind)
    parts = [
        f"문서 종류: {meta['label']}",
        f"찾는 것: {meta['label']} 작성에 쓸 공식 양식·서식·별지",
        f"예상 구성: {meta['sections_hint']}",
    ]
    if title:
        parts.append(f"작성 제목: {title}")

    # 기입 내용에서 매칭에 쓸 만한 짧은 단서만 뽑습니다.
    for key in (
        "event_name",
        "target",
        "location",
        "schedule",
        "department",
        "school_name",
        "fair_name",
    ):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(f"{key}: {val.strip()[:80]}")

    if kind == "budget":
        items = payload.get("items") or []
        names = [
            str(it.get("name") or it.get("item") or "").strip()
            for it in items
            if isinstance(it, dict)
        ]
        names = [n for n in names if n][:8]
        if names:
            parts.append("예산 항목: " + ", ".join(names))

    programs = payload.get("programs") or []
    if isinstance(programs, list) and programs:
        parts.append(f"일정/프로그램 {len(programs)}건 포함")

    return "\n".join(parts)


def _boost_score(
    base: float,
    *,
    filename: str,
    category: str,
    kind: str,
) -> float:
    score = float(base)
    meta = _kind_meta(kind)
    name = filename or ""
    kind_hits = sum(1 for k in meta["keywords"] if k in name)
    if category == "문서 양식":
        score += 0.18 if kind_hits else 0.04
    if any(h in name for h in FORM_NAME_HINTS):
        score += 0.12 if kind_hits else 0.04
    score += min(0.22, kind_hits * 0.08)
    # 등록금 명세서 등 명백히 다른 서식은 감점
    if kind != "budget" and any(
        x in name for x in ("등록금", "수업료", "입학금", "제8호")
    ):
        score -= 0.25
    if kind == "budget" and any(
        x in name
        for x in ("등록금", "수업료", "입학금", "제8호", "운영계획서", "홍보계획서", "참가계획서")
    ):
        score -= 0.28
    return max(0.0, min(1.0, score))


def find_best_form_match(
    db: Session,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
) -> FormMatch | None:
    """RAG에서 가장 적합한 양식 문서 1건을 고릅니다. 없으면 None."""
    candidate_ids = _collect_candidate_ids(db, kind)
    if not candidate_ids:
        logger.info("양식 후보 없음 (kind=%s)", kind)
        return None

    query = _build_search_query(kind, title, payload)
    chunks = retrieve_relevant_chunks(
        db,
        query,
        top_k=16,
        document_ids=candidate_ids,
    )
    if not chunks:
        # 임베딩이 비어 있어도 파일명에 문서 종류 키워드가 있는 양식만 고릅니다.
        meta = _kind_meta(kind)
        docs = (
            db.query(UploadedDocument)
            .filter(UploadedDocument.id.in_(candidate_ids))
            .all()
        )
        scored: list[FormMatch] = []
        for doc in docs:
            blob = f"{doc.filename} {getattr(doc, 'summary', '') or ''}"
            if not any(k in blob for k in meta["keywords"]):
                continue
            s = _boost_score(
                0.32,
                filename=doc.filename,
                category=doc.category or "",
                kind=kind,
            )
            scored.append(
                FormMatch(
                    document_id=doc.id,
                    filename=doc.filename,
                    category=doc.category or "기타",
                    score=s,
                    relevance=int(round(s * 100)),
                    reason="파일명·분류 휴리스틱",
                )
            )
        scored.sort(key=lambda m: m.score, reverse=True)
        best = scored[0] if scored else None
        if best and best.score >= MIN_MATCH_SCORE:
            return best
        return None

    refs = aggregate_document_references(chunks, limit=8)
    matches: list[FormMatch] = []
    meta = _kind_meta(kind)
    for ref in refs:
        doc = db.get(UploadedDocument, ref["document_id"])
        if not doc:
            continue
        boosted = _boost_score(
            float(ref.get("score") or 0.0),
            filename=doc.filename,
            category=getattr(doc, "category", None) or "",
            kind=kind,
        )
        matches.append(
            FormMatch(
                document_id=doc.id,
                filename=doc.filename,
                category=getattr(doc, "category", None) or "기타",
                score=boosted,
                relevance=int(round(boosted * 100)),
                snippet=str(ref.get("snippet") or ""),
                reason="RAG 유사도 + 양식/종류 가점",
            )
        )
    matches.sort(key=lambda m: m.score, reverse=True)
    best = matches[0] if matches else None
    if not best or best.score < MIN_MATCH_SCORE:
        logger.info(
            "양식 매칭 미달 (kind=%s, best=%s)",
            kind,
            f"{best.filename}:{best.score:.2f}" if best else None,
        )
        return None

    # 파일명에 종류 단서가 전혀 없으면, RAG 점수가 매우 높을 때만 채택합니다.
    blob = f"{best.filename} {best.snippet}"
    has_kind = any(k in blob for k in meta["keywords"])
    if not has_kind and best.score < 0.62:
        logger.info(
            "양식 종류 단서 부족으로 제외: %s (score=%.2f, kind=%s)",
            best.filename,
            best.score,
            kind,
        )
        return None

    logger.info(
        "양식 매칭 성공: %s (id=%s, score=%.2f, kind=%s)",
        best.filename,
        best.document_id,
        best.score,
        kind,
    )
    return best


def _form_text_for_doc(db: Session, document_id: int, *, limit_chars: int = 6000) -> str:
    rows = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.id.asc())
        .all()
    )
    parts: list[str] = []
    total = 0
    for row in rows:
        text = (row.content or "").strip()
        if not text:
            continue
        if total + len(text) > limit_chars:
            parts.append(text[: max(0, limit_chars - total)])
            break
        parts.append(text)
        total += len(text)
    return "\n\n".join(parts).strip()


def _payload_digest(kind: str, title: str, payload: dict[str, Any]) -> str:
    """LLM에 넘길 기입값 요약(JSON)."""
    data = dict(payload)
    data["_document_title"] = title
    data["_document_kind"] = kind
    # 너무 긴 필드는 자릅니다.
    raw = json.dumps(data, ensure_ascii=False, default=str)
    if len(raw) > 5000:
        raw = raw[:5000] + "…"
    return raw


def build_form_filled_markdown(
    db: Session,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    match: FormMatch,
) -> tuple[str, list[str]]:
    """매칭된 양식 원문을 기준으로, 기입값으로 채운 Markdown을 만듭니다."""
    meta = _kind_meta(kind)
    form_text = _form_text_for_doc(db, match.document_id)
    if not form_text:
        raise ValueError("양식 본문 텍스트가 비어 있습니다.")

    system = (
        "당신은 대학 입시행정 공식 문서 작성 보조입니다. "
        "주어진 '공식 양식 원문'의 구성(장·절 제목, 표 열, 순서)을 최우선으로 따르세요. "
        "양식에 있는 섹션·표 헤더는 가능한 한 그대로 유지하고, "
        "기입값으로만 칸을 채우세요. 양식에 없는 내용은 지어내지 마세요. "
        "값이 없으면 '{입력 필요}'로 두세요. "
        "출력은 GitHub Flavored Markdown만 허용합니다. "
        "첫 줄은 # 제목 이고, 이어서 양식 순서의 섹션을 작성하세요. "
        "표는 | 헤더 | 형식과 구분 행을 포함하세요. "
        "설명 문장·코드블록·JSON은 넣지 마세요."
    )
    user = (
        f"작성할 문서: {meta['label']}\n"
        f"문서 제목: {title}\n"
        f"양식 파일명: {match.filename}\n"
        f"양식에서 기대하는 구성 힌트: {meta['sections_hint']}\n\n"
        f"[공식 양식 원문]\n{form_text}\n\n"
        f"[담당자가 기입한 내용(JSON)]\n{_payload_digest(kind, title, payload)}\n\n"
        "위 양식 구조를 최우선으로 하여 완성본 Markdown을 작성하세요."
    )

    llm = get_llm_service()
    markdown = llm.chat([{"role": "user", "content": user}], system=system).strip()
    if markdown.startswith("```"):
        markdown = re.sub(r"^```(?:markdown|md)?\s*", "", markdown)
        markdown = re.sub(r"\s*```$", "", markdown)

    if not markdown or len(markdown) < 40:
        raise ValueError("양식 기반 Markdown 생성 결과가 비어 있습니다.")

    # 섹션 제목 추출(미리보기/메타용)
    sections = [
        re.sub(r"^#+\s*", "", line).strip()
        for line in markdown.splitlines()
        if re.match(r"^#{1,3}\s+\S", line.strip())
        or re.match(r"^\*\*\d*[\.\s].+\*\*$", line.strip())
        or re.match(r"^\d+\.\S", line.strip())
    ]
    sections = [s for s in sections if s][:12]
    return markdown, sections


def generate_pdf_from_matched_form(
    db: Session,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    match: FormMatch,
    filename_stem: str,
) -> tuple[TuitionStatementFiles, FormMatch]:
    markdown, sections = build_form_filled_markdown(
        db, kind=kind, title=title, payload=payload, match=match
    )
    files = generate_admin_document_files(
        markdown,
        title_hint=title,
        filename_stem=filename_stem,
    )
    match.used_form = True
    match.sections = sections
    match.reason = (
        match.reason or "RAG 양식 매칭"
    ) + f" → 「{match.filename}」 구조로 작성"
    return files, match


def generate_pdf_preferring_form(
    db: Session,
    *,
    kind: str,
    title: str,
    payload: dict[str, Any],
    filename_stem: str,
    fallback: Callable[[], TuitionStatementFiles],
) -> tuple[TuitionStatementFiles, FormMatch | None]:
    """양식 매칭을 최우선으로 시도하고, 실패하면 fallback PDF 생성기를 씁니다."""
    match = find_best_form_match(db, kind=kind, title=title, payload=payload)
    if match is not None:
        try:
            return generate_pdf_from_matched_form(
                db,
                kind=kind,
                title=title,
                payload=payload,
                match=match,
                filename_stem=filename_stem,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "양식 기반 PDF 생성 실패 — 기본 생성기로 폴백 (form=%s, kind=%s)",
                match.filename,
                kind,
            )

    return fallback(), None
