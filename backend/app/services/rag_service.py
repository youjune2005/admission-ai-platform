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
        logger.warning("OpenAI API 키가 없어 임베딩을 건너뜁니다.")
        return []

    from openai import OpenAI

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    # API 입력 한도 대비 배치 처리
    batch_size = 64
    all_embeddings: list[list[float]] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.embeddings.create(model=settings.openai_embedding_model, input=batch)
        # index 순으로 정렬
        ordered = sorted(response.data, key=lambda item: item.index)
        all_embeddings.extend(item.embedding for item in ordered)
    return all_embeddings


def ingest_document(db: Session, document: UploadedDocument, text: str) -> int:
    """문서 텍스트를 청크로 분할하고 임베딩해 저장합니다. 저장된 청크 수를 반환합니다.

    임베딩 실패 시 0을 반환하며, 기존 청크는 삭제된 상태로 남을 수 있습니다.
    """
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()

    chunks = chunk_text(text)
    if not chunks:
        db.commit()
        logger.warning("RAG 인제스트: 텍스트 청크 없음 (document_id=%s)", document.id)
        return 0

    try:
        embeddings = embed_texts(chunks)
    except Exception:  # noqa: BLE001
        logger.exception("임베딩 생성 실패 (document_id=%s)", document.id)
        db.commit()
        return 0

    if not embeddings or len(embeddings) != len(chunks):
        logger.error(
            "RAG 인제스트 실패: 임베딩 수 불일치 (document_id=%s, chunks=%s, embeddings=%s)",
            document.id,
            len(chunks),
            len(embeddings) if embeddings else 0,
        )
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
    logger.info("RAG 인제스트 완료 (document_id=%s, chunks=%s)", document.id, len(chunks))
    return len(chunks)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_relevant_chunks(
    db: Session,
    query: str,
    top_k: int | None = None,
    document_ids: list[int] | None = None,
) -> list[dict]:
    """질문과 관련된 문서 청크를 유사도 순으로 반환합니다.
    [{"document_id": int, "filename": str, "content": str, "score": float}, ...]
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

    q = db.query(DocumentChunk, UploadedDocument).join(
        UploadedDocument, DocumentChunk.document_id == UploadedDocument.id
    )
    if document_ids:
        q = q.filter(UploadedDocument.id.in_(document_ids))
    rows = q.all()
    if not rows:
        return []

    scored = []
    for chunk, doc in rows:
        try:
            embedding = json.loads(chunk.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        score = _cosine_similarity(query_embedding, embedding)
        scored.append(
            {
                "document_id": doc.id,
                "filename": doc.filename,
                "content": chunk.content,
                "score": score,
                "updated_at": doc.updated_at or doc.created_at,
            }
        )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]


def aggregate_document_references(
    chunks: list[dict],
    *,
    limit: int = 5,
) -> list[dict]:
    """청크 결과를 문서 단위로 묶고 관련도(%)를 계산합니다."""
    best: dict[int, dict] = {}
    for c in chunks:
        doc_id = c.get("document_id")
        if doc_id is None:
            continue
        prev = best.get(doc_id)
        if prev is None or c["score"] > prev["score"]:
            snippet = (c.get("content") or "").strip().replace("\n", " ")
            if len(snippet) > 160:
                snippet = snippet[:157] + "…"
            best[doc_id] = {
                "document_id": doc_id,
                "filename": c["filename"],
                "score": float(c["score"]),
                "relevance": int(round(max(0.0, min(1.0, float(c["score"]))) * 100)),
                "snippet": snippet,
                "updated_at": c.get("updated_at"),
            }
    refs = sorted(best.values(), key=lambda x: x["score"], reverse=True)
    return refs[:limit]


def build_context_block(chunks: list[dict]) -> str:
    if not chunks:
        return ""
    parts = [
        f"[참고 문서: {c['filename']}]\n{c['content']}"
        for c in chunks
    ]
    return (
        "다음은 내부 규정·자료 DB에서 RAG로 검색된 근거입니다. "
        "답변은 아래 내용만을 근거로 작성하고, 여기에 없는 사실은 일반 지식으로 보완하지 마세요. "
        "「일반적으로」 등 근거 없는 표현은 쓰지 마세요. "
        "근거 문장에는 [1], [2] 형태로 출처 번호를 달아주세요.\n\n"
        + "\n\n---\n\n".join(parts)
    )
