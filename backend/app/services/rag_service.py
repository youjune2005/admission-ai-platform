"""문서를 청크로 분할하고 임베딩해 저장/검색하는 간단한 RAG(검색 증강 생성) 서비스.

별도의 벡터DB 없이 SQLite에 임베딩을 JSON으로 저장하고, 검색 시 코사인 유사도를
직접 계산합니다. 데이터 규모가 커지면 전용 벡터DB(Chroma, pgvector 등)로 교체 가능합니다.
"""

import json
import logging
import math

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import DocumentChunk, UploadedDocument

logger = logging.getLogger(__name__)

CHUNK_SIZE = 800
CHUNK_OVERLAP = 150


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = text.strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start = end - overlap
    return chunks


def _is_embedding_available() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """OpenAI 임베딩 API로 텍스트 목록을 임베딩합니다. 키가 없으면 빈 리스트를 반환합니다."""
    if not texts:
        return []
    if not _is_embedding_available():
        return []

    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=settings.openai_embedding_model, input=texts)
    return [item.embedding for item in response.data]


def ingest_document(db: Session, document: UploadedDocument, text: str) -> int:
    """문서 텍스트를 청크로 분할하고 임베딩해 저장합니다. 저장된 청크 수를 반환합니다."""
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

    chunks = chunk_text(text)
    if not chunks:
        db.commit()
        return 0

    try:
        embeddings = embed_texts(chunks)
    except Exception:  # noqa: BLE001
        logger.exception("임베딩 생성 실패 (document_id=%s)", document.id)
        embeddings = []

    if not embeddings:
        db.commit()
        return 0

    for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        db.add(
            DocumentChunk(
                document_id=document.id,
                chunk_index=idx,
                content=chunk,
                embedding=json.dumps(embedding),
            )
        )
    db.commit()
    return len(chunks)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_relevant_chunks(db: Session, query: str, top_k: int | None = None) -> list[dict]:
    """질문과 관련된 문서 청크를 유사도 순으로 반환합니다.
    [{"filename": str, "content": str, "score": float}, ...]
    """
    if not _is_embedding_available():
        return []

    settings = get_settings()
    top_k = top_k or settings.rag_top_k

    try:
        query_embedding = embed_texts([query])[0]
    except Exception:  # noqa: BLE001
        logger.exception("질문 임베딩 생성 실패")
        return []

    rows = (
        db.query(DocumentChunk, UploadedDocument)
        .join(UploadedDocument, DocumentChunk.document_id == UploadedDocument.id)
        .all()
    )
    if not rows:
        return []

    scored = []
    for chunk, doc in rows:
        try:
            embedding = json.loads(chunk.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        score = _cosine_similarity(query_embedding, embedding)
        scored.append({"filename": doc.filename, "content": chunk.content, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def build_context_block(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    parts = [
        f"[참고 문서: {c['filename']}]\n{c['content']}"
        for c in chunks
    ]
    return (
        "다음은 업로드된 입시 관련 문서에서 검색된 참고 내용입니다. "
        "답변 시 아래 내용을 우선적으로 참고하고, 문서에 없는 내용은 일반적인 지식임을 밝혀주세요.\n\n"
        + "\n\n---\n\n".join(parts)
    )
