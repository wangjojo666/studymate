from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import ChunkKnowledgePoint, Document, DocumentChunk
from app.services.chunker import TextChunk
from app.services.embedding_service import embed_texts, embedding_provider_label


logger = logging.getLogger(__name__)

TOKEN_RE = re.compile("[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")
CHROMA_COLLECTION_NAME = "studymate_course_chunks"

_chroma_client: Any | None = None
_chroma_collection: Any | None = None
_chroma_available: bool | None = None


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    document_id: int
    document_name: str
    page_number: int
    chunk_index: int
    content: str
    score: float
    retrieval_provider: str = "sqlite_sparse"


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.findall(text.lower()):
        if re.fullmatch("[\u4e00-\u9fff]+", match):
            tokens.extend(match)
            tokens.extend(match[i : i + 2] for i in range(len(match) - 1))
        else:
            tokens.append(match)
    return [token for token in tokens if token.strip()]


def vectorize(text: str) -> tuple[dict[str, float], float]:
    counts = Counter(tokenize(text))
    weights = {token: 1.0 + math.log(count) for token, count in counts.items() if count > 0}
    norm = math.sqrt(sum(weight * weight for weight in weights.values()))
    return weights, norm


def embed_text(text: str) -> list[float]:
    return embed_texts([text]).vectors[0]


def index_document_chunks(
    db: Session,
    document: Document,
    chunks: list[TextChunk],
    replace_document: bool = True,
    replace_page_numbers: list[int] | None = None,
) -> None:
    if replace_document:
        chunk_ids = [
            row[0]
            for row in db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document.id).all()
        ]
        if chunk_ids:
            db.query(ChunkKnowledgePoint).filter(ChunkKnowledgePoint.chunk_id.in_(chunk_ids)).delete(
                synchronize_session=False
            )
            delete_chunks_from_index(chunk_ids)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete(
            synchronize_session=False
        )
        first_index = 0
    else:
        page_numbers = sorted(set(replace_page_numbers or [chunk.page_number for chunk in chunks]))
        if page_numbers:
            page_chunk_ids = [
                row[0]
                for row in db.query(DocumentChunk.id)
                .filter(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.page_number.in_(page_numbers),
                )
                .all()
            ]
            if page_chunk_ids:
                db.query(ChunkKnowledgePoint).filter(ChunkKnowledgePoint.chunk_id.in_(page_chunk_ids)).delete(
                    synchronize_session=False
                )
                delete_chunks_from_index(page_chunk_ids)
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document.id,
                DocumentChunk.page_number.in_(page_numbers),
            ).delete(synchronize_session=False)
        max_index = (
            db.query(func.max(DocumentChunk.chunk_index))
            .filter(DocumentChunk.document_id == document.id)
            .scalar()
        )
        first_index = int(max_index or -1) + 1

    indexed_chunks: list[DocumentChunk] = []
    for offset, chunk in enumerate(chunks):
        weights, norm = vectorize(chunk.content)
        row = DocumentChunk(
            course_id=document.course_id,
            document_id=document.id,
            chunk_index=first_index + offset,
            page_number=chunk.page_number,
            content=chunk.content,
            token_weights=json.dumps(weights, ensure_ascii=False),
            vector_norm=norm,
        )
        db.add(row)
        indexed_chunks.append(row)

    db.flush()
    _upsert_chroma_chunks(indexed_chunks)
    document.chunk_count = (
        db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.document_id == document.id).scalar() or 0
    )
    document.status = "indexed" if document.chunk_count else "empty"
    db.flush()


def search_course(db: Session, course_id: int, query: str, limit: int = 5) -> list[SearchResult]:
    chroma_results = _search_chroma_course(course_id, query, limit)
    if chroma_results:
        return chroma_results
    return _search_course_sqlite(db, course_id, query, limit)


def retrieval_provider_from_results(results: list[SearchResult]) -> str:
    if not results:
        return f"no_match/{embedding_provider_label()}"
    return results[0].retrieval_provider


def delete_chunks_from_index(chunk_ids: list[int]) -> None:
    if not chunk_ids:
        return
    collection = _get_chroma_collection()
    if collection is None:
        return
    try:
        collection.delete(ids=[_chunk_chroma_id(chunk_id) for chunk_id in chunk_ids])
    except Exception as exc:  # noqa: BLE001 - Chroma is optional and should not break uploads.
        logger.warning("Failed to delete Chroma chunks: %s", exc)


def delete_document_index(document_id: int) -> None:
    collection = _get_chroma_collection()
    if collection is None:
        return
    try:
        collection.delete(where={"document_id": document_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete Chroma document index: %s", exc)


def delete_course_index(course_id: int) -> None:
    collection = _get_chroma_collection()
    if collection is None:
        return
    try:
        collection.delete(where={"course_id": course_id})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete Chroma course index: %s", exc)


def get_representative_chunks(db: Session, course_id: int, limit: int = 8) -> list[SearchResult]:
    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(DocumentChunk.course_id == course_id)
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
        .limit(limit)
        .all()
    )
    return [
        SearchResult(
            chunk_id=chunk.id,
            document_id=document.id,
            document_name=document.original_filename,
            page_number=chunk.page_number,
            chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=1.0,
                retrieval_provider="representative_chunks",
            )
        for chunk, document in rows
    ]


def _search_course_sqlite(db: Session, course_id: int, query: str, limit: int) -> list[SearchResult]:
    q_weights, q_norm = vectorize(query)
    if q_norm == 0:
        return []

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .filter(DocumentChunk.course_id == course_id)
        .all()
    )
    results: list[SearchResult] = []
    query_text = query.strip().lower()
    for chunk, document in rows:
        if not chunk.token_weights or chunk.vector_norm == 0:
            continue
        c_weights = json.loads(chunk.token_weights)
        dot = 0.0
        for token, q_weight in q_weights.items():
            dot += q_weight * float(c_weights.get(token, 0.0))
        score = dot / (q_norm * chunk.vector_norm)
        if query_text and query_text in chunk.content.lower():
            score += 0.12
        if score <= 0:
            continue
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.original_filename,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=score,
                retrieval_provider="sqlite_sparse",
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]


def _upsert_chroma_chunks(chunks: list[DocumentChunk]) -> None:
    if not chunks:
        return
    collection = _get_chroma_collection()
    if collection is None:
        return

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    for chunk in chunks:
        document_name = chunk.document.original_filename if chunk.document else ""
        ids.append(_chunk_chroma_id(chunk.id))
        documents.append(chunk.content)
        metadatas.append(
            {
                "course_id": chunk.course_id,
                "document_id": chunk.document_id,
                "document_name": document_name,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
            }
        )
    try:
        batch = embed_texts(documents, purpose="document")
        for metadata in metadatas:
            metadata["embedding_provider"] = batch.provider
            metadata["embedding_dimension"] = batch.dimension
        collection.upsert(ids=ids, embeddings=batch.vectors, documents=documents, metadatas=metadatas)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to upsert Chroma chunks: %s", exc)


def _search_chroma_course(course_id: int, query: str, limit: int) -> list[SearchResult]:
    collection = _get_chroma_collection()
    if collection is None or not query.strip():
        return []
    try:
        query_batch = embed_texts([query], purpose="query")
        response = collection.query(
            query_embeddings=query_batch.vectors,
            n_results=limit,
            where={"course_id": course_id},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to query Chroma, falling back to SQLite search: %s", exc)
        return []

    ids = (response.get("ids") or [[]])[0]
    documents = (response.get("documents") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    results: list[SearchResult] = []
    for index, raw_id in enumerate(ids):
        metadata = metadatas[index] or {}
        content = documents[index] or ""
        distance = float(distances[index]) if index < len(distances) else 1.0
        score = max(0.0, 1.0 - distance)
        results.append(
            SearchResult(
                chunk_id=_parse_chroma_chunk_id(raw_id),
                document_id=int(metadata.get("document_id") or 0),
                document_name=str(metadata.get("document_name") or ""),
                page_number=int(metadata.get("page_number") or 1),
                chunk_index=int(metadata.get("chunk_index") or 0),
                content=content,
                score=score,
                retrieval_provider=f"chroma/{metadata.get('embedding_provider') or query_batch.provider}",
            )
        )
    return results


def _get_chroma_collection():
    global _chroma_available, _chroma_client, _chroma_collection
    if _chroma_available is False:
        return None
    if _chroma_collection is not None:
        return _chroma_collection
    try:
        import chromadb

        _chroma_client = chromadb.PersistentClient(path=str(settings.chroma_dir))
        _chroma_collection = _chroma_client.get_or_create_collection(
            CHROMA_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        _chroma_available = True
        return _chroma_collection
    except Exception as exc:  # noqa: BLE001
        _chroma_available = False
        logger.info("Chroma is unavailable; SQLite fallback search is active: %s", exc)
        return None


def _chunk_chroma_id(chunk_id: int) -> str:
    return f"chunk-{chunk_id}"


def _parse_chroma_chunk_id(value: str) -> int:
    try:
        return int(str(value).split("-", 1)[1])
    except (IndexError, ValueError):
        return 0
