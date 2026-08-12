"""채팅 세션 조회용 최소 API (대시보드 집계 호환).

입시 문의 답변은 /api/inquiry 를 사용합니다.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import ChatMessage, ChatSession
from app.schemas.chat import ChatMessageIn, ChatMessageOut, ChatSessionDetail, ChatSessionOut
from app.services.llm_service import SYSTEM_PROMPT, get_llm_service
from app.services.rag_service import build_context_block, retrieve_relevant_chunks

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(db: Session = Depends(get_db)):
    return db.query(ChatSession).order_by(ChatSession.created_at.desc()).all()


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
def get_session(session_id: int, db: Session = Depends(get_db)):
    session = db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return session


@router.post("/message", response_model=ChatMessageOut)
def send_message(payload: ChatMessageIn, db: Session = Depends(get_db)):
    """비스트리밍 단건 응답 (내부/호환용)."""
    session = db.get(ChatSession, payload.session_id) if payload.session_id else None
    if session is None:
        session = ChatSession(title=payload.message[:30] or "새 상담")
        db.add(session)
        db.flush()

    user_msg = ChatMessage(session_id=session.id, role="user", content=payload.message)
    db.add(user_msg)
    db.flush()

    history = [{"role": m.role, "content": m.content} for m in session.messages]

    relevant_chunks = retrieve_relevant_chunks(db, payload.message)
    context_block = build_context_block(relevant_chunks)
    system_prompt = f"{SYSTEM_PROMPT}\n\n{context_block}" if context_block else SYSTEM_PROMPT

    llm = get_llm_service()
    answer = llm.chat(history, system=system_prompt)

    assistant_msg = ChatMessage(session_id=session.id, role="assistant", content=answer)
    db.add(assistant_msg)
    db.commit()
    db.refresh(assistant_msg)

    return assistant_msg
