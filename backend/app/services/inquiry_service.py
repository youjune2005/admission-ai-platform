"""입시 문의 답변: 마스킹 · RAG · LLM 초안 생성."""

from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Inquiry, InquiryActivity
from app.services.llm_service import get_llm_service
from app.services.rag_service import (
    aggregate_document_references,
    build_context_block,
    retrieve_relevant_chunks,
)

INQUIRY_SYSTEM_PROMPT = (
    "당신은 대학 입학처 담당자가 학부모·학생 문의에 답변할 때 쓰는 초안을 작성하는 AI입니다. "
    "답변은 반드시 시스템에 제공된 내부 근거 자료(모집요강·공지·FAQ·규정 등 RAG 검색 결과)에서 "
    "관련 문구를 명확히 찾아 그에 근거해 작성하세요. "
    "근거 자료에 없는 내용은 추측·일반론으로 채우지 말고, "
    "「내부 등록 자료에서 확인되지 않아 담당자 확인이 필요합니다」라고만 안내하세요. "
    "「일반적으로」「보통」「대개」「통상」처럼 근거 없이 일반화하는 표현은 사용하지 마세요. "
    "답변은 정중하고 명확한 한국어로 작성하고, 핵심 내용을 번호/문단으로 정리하세요. "
    "근거가 되는 문장 뒤에는 [1], [2]처럼 출처 번호를 달아주세요. "
    "개인정보가 남아 있으면 답변에 그대로 반복하지 마세요."
)

STATUS_LABELS = {
    "pending": "대기",
    "generating": "답변 생성 중",
    "completed": "답변 완료",
    "reviewed": "검토 완료",
}

# 간단한 개인정보 마스킹
_PHONE_RE = re.compile(r"(?<!\d)(01[016789]-?\d{3,4}-?\d{4})(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_RRN_RE = re.compile(r"\b(\d{6})-?[1-4]\d{6}\b")


def mask_pii(text: str) -> str:
    masked = _PHONE_RE.sub("[전화번호]", text or "")
    masked = _EMAIL_RE.sub("[이메일]", masked)
    masked = _RRN_RE.sub("[주민번호]", masked)
    return masked


def _dumps(obj) -> str:
    def _default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    return json.dumps(obj, ensure_ascii=False, default=_default)


def _loads(raw: str | None, fallback):
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


def add_activity(db: Session, inquiry: Inquiry, message: str) -> InquiryActivity:
    act = InquiryActivity(
        inquiry_id=inquiry.id,
        message=message,
        created_at=datetime.utcnow(),
    )
    db.add(act)
    db.flush()  # id·시각을 확정해 이후 로그와 구분
    return act


def build_check_notes(question: str, refs: list[dict]) -> list[str]:
    notes = [
        "모집요강·공지 문구와 초안 표현이 일치하는지 확인하세요.",
        "최신 학년도·전형 기준이 맞는지 검토하세요.",
    ]
    if "동시" in question or "중복" in question or "복수" in question:
        notes.insert(0, "복수지원·동시지원 가능 여부 문구를 원문과 대조하세요.")
    if refs:
        notes.append(f"근거 문서 {len(refs)}건의 관련도·발췌 내용을 검토하세요.")
    return notes[:4]


def generate_inquiry_draft(
    db: Session,
    inquiry: Inquiry,
    *,
    document_ids: list[int] | None = None,
) -> Inquiry:
    """RAG + LLM으로 초안을 생성하고 inquiry에 저장합니다."""
    inquiry.status = "generating"
    db.commit()

    question = inquiry.masked_content or inquiry.content
    meta = (
        f"[학년도: {inquiry.academic_year}학년도] "
        f"[모집: {inquiry.admission_type}] "
        f"[전형: {inquiry.selection_type or '미지정'}] "
        f"[문의자: {inquiry.asker_type}]"
    )
    query = f"{meta}\n{question}"

    ids = document_ids if document_ids else _loads(inquiry.selected_document_ids_json, [])
    # 청크를 넉넉히 가져와 문서 단위로 묶음
    chunks = retrieve_relevant_chunks(
        db,
        query,
        top_k=12,
        document_ids=ids or None,
    )
    refs = aggregate_document_references(chunks, limit=5)
    context = build_context_block(chunks[:8])

    system = INQUIRY_SYSTEM_PROMPT
    if context:
        system = f"{INQUIRY_SYSTEM_PROMPT}\n\n{context}"
    else:
        system = (
            f"{INQUIRY_SYSTEM_PROMPT}\n\n"
            "현재 검색된 내부 근거 자료가 없습니다. "
            "일반론으로 답하지 말고, 내부 자료에서 확인되지 않아 담당자 확인이 필요하다고만 안내하세요."
        )

    llm = get_llm_service()
    user_prompt = (
        f"{meta}\n\n문의 내용:\n{question}\n\n"
        "위 문의에 대한 입학처 답변 초안을 작성해 주세요. "
        "내부 RAG 근거 자료에 명시된 내용만 사용하고, "
        "「일반적으로」 같은 표현은 쓰지 마세요."
    )
    answer = llm.chat([{"role": "user", "content": user_prompt}], system=system)

    inquiry.draft_answer = answer
    inquiry.ai_draft_answer = answer
    inquiry.references_json = _dumps(refs)
    inquiry.check_notes_json = _dumps(build_check_notes(question, refs))
    inquiry.status = "completed"
    inquiry.updated_at = datetime.utcnow()
    add_activity(db, inquiry, "AI 답변 초안 생성")
    if refs:
        add_activity(db, inquiry, f"근거 자료 매칭 완료 ({len(refs)}건)")
    else:
        add_activity(db, inquiry, "근거 자료 매칭 결과 없음 (문서·임베딩 확인 필요)")
    db.commit()
    db.refresh(inquiry)
    return inquiry


def _build_change_summary(original: str, modified: str) -> str:
    """간단한 줄 단위 변경 요약 (수정된 부분만)."""
    import difflib

    orig_lines = (original or "").splitlines()
    mod_lines = (modified or "").splitlines()
    diff = list(
        difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile="AI원본",
            tofile="수정본",
            lineterm="",
        )
    )
    # 헤더/@@ 제외하고 변경 줄만
    changes = [line for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))]
    if not changes:
        return "(텍스트 차이는 있으나 줄 단위 변경 요약을 만들지 못했습니다.)"
    # 너무 길면 자름
    text = "\n".join(changes)
    if len(text) > 4000:
        text = text[:4000] + "\n…(이하 생략)"
    return text


FEEDBACK_SYSTEM_PROMPT = (
    "당신은 대학 입학처 담당자가 수정한 입시 문의 답변 초안을 검토하는 AI입니다. "
    "반드시 '수정된 부분'에 대해서만 피드백하세요. 수정되지 않은 문장·문단은 언급하지 마세요. "
    "피드백은 한국어로, 간결한 불릿 목록으로 작성하세요. "
    "각 수정에 대해 (1) 무엇을 바꿨는지 (2) 입학처 답변으로서 적절한지 "
    "(3) 규정 표현·정확성·톤 측면에서 보완할 점이 있는지를 짧게 적어주세요. "
    "전체 초안을 다시 쓰거나 장황한 재작성은 하지 마세요."
)


def generate_draft_feedback(
    *,
    question: str,
    original_draft: str,
    modified_draft: str,
) -> str:
    if (original_draft or "").strip() == (modified_draft or "").strip():
        return "수정된 내용이 없습니다. 초안을 수정한 뒤 다시 시도해 주세요."

    change_summary = _build_change_summary(original_draft, modified_draft)
    llm = get_llm_service()
    user_prompt = (
        f"원본 문의:\n{question}\n\n"
        f"AI 원본 초안:\n{original_draft}\n\n"
        f"담당자 수정본:\n{modified_draft}\n\n"
        f"줄 단위 변경 요약(수정된 줄만):\n{change_summary}\n\n"
        "위 변경 요약에 해당하는 수정 부분에 한해 피드백을 작성해 주세요."
    )
    return llm.chat([{"role": "user", "content": user_prompt}], system=FEEDBACK_SYSTEM_PROMPT)


def inquiry_to_dict(inquiry: Inquiry) -> dict:
    refs_raw = _loads(inquiry.references_json, [])
    references = []
    for r in refs_raw:
        updated = r.get("updated_at")
        if isinstance(updated, str):
            try:
                updated = datetime.fromisoformat(updated)
            except ValueError:
                updated = None
        references.append(
            {
                "document_id": r.get("document_id", 0),
                "filename": r.get("filename", ""),
                "relevance": int(r.get("relevance", 0)),
                "score": float(r.get("score", 0)),
                "snippet": r.get("snippet", ""),
                "updated_at": updated,
            }
        )

    activities = sorted(
        list(inquiry.activities or []),
        key=lambda a: (a.created_at or datetime.min, a.id or 0),
        reverse=True,
    )

    return {
        "id": inquiry.id,
        "academic_year": inquiry.academic_year,
        "admission_type": inquiry.admission_type,
        "selection_type": inquiry.selection_type or "",
        "asker_type": inquiry.asker_type,
        "content": inquiry.content,
        "masked_content": inquiry.masked_content,
        "draft_answer": inquiry.draft_answer,
        "ai_draft_answer": getattr(inquiry, "ai_draft_answer", None) or inquiry.draft_answer,
        "status": inquiry.status,
        "status_label": STATUS_LABELS.get(inquiry.status, inquiry.status),
        "selected_document_ids": _loads(inquiry.selected_document_ids_json, []),
        "references": references,
        "check_notes": _loads(inquiry.check_notes_json, []),
        "activities": activities,
        "created_at": inquiry.created_at,
        "updated_at": inquiry.updated_at,
    }
