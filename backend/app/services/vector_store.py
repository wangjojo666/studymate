from __future__ import annotations

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
from app.models.entities import ChunkKnowledgePoint, Course, Document, DocumentChunk
from app.services.chunker import TextChunk
from app.services.embedding_service import embed_texts, embedding_provider_label

logger = logging.getLogger(__name__)

TOKEN_RE = re.compile("[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")
CHROMA_COLLECTION_NAME = "studymate_course_chunks"
NON_RETRIEVABLE_DOCUMENT_STATUSES = {"deleting"}

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
            for row in db.query(DocumentChunk.id)
            .filter(DocumentChunk.document_id == document.id)
            .all()
        ]
        if chunk_ids:
            db.query(ChunkKnowledgePoint).filter(
                ChunkKnowledgePoint.chunk_id.in_(chunk_ids)
            ).delete(synchronize_session=False)
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
                db.query(ChunkKnowledgePoint).filter(
                    ChunkKnowledgePoint.chunk_id.in_(page_chunk_ids)
                ).delete(synchronize_session=False)
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
        db.query(func.count(DocumentChunk.id))
        .filter(DocumentChunk.document_id == document.id)
        .scalar()
        or 0
    )
    document.status = "indexed" if document.chunk_count else "empty"
    db.flush()


def search_course(db: Session, course_id: int, query: str, limit: int = 5) -> list[SearchResult]:
    # Chroma is an acceleration index only. Every hit is re-hydrated from SQL
    # so stale/tampered metadata can never grant access or resurrect content.
    chroma_results = _search_chroma_course(db, course_id, query, limit)
    if chroma_results:
        return chroma_results
    return _search_course_sqlite(db, course_id, query, limit)


def retrieval_provider_from_results(results: list[SearchResult]) -> str:
    if not results:
        return f"no_match/{embedding_provider_label()}"
    return results[0].retrieval_provider


def retrieval_backend_status() -> dict:
    chroma_available = _get_chroma_collection() is not None
    return {
        "chroma_available": chroma_available,
        "embedding_provider": embedding_provider_label(),
        "fallback_search": "sqlite_sparse",
        "active_backend": "chroma" if chroma_available else "sqlite_sparse",
        "search_order": ["chroma", "sqlite_sparse"] if chroma_available else ["sqlite_sparse"],
    }


def delete_chunks_from_index(chunk_ids: list[int]) -> bool:
    if not chunk_ids:
        return True
    collection = _get_chroma_collection()
    if collection is None:
        return True
    return _delete_chroma_ids(
        collection,
        [_chunk_chroma_id(chunk_id) for chunk_id in chunk_ids],
        reason="chunks",
    )


def delete_document_index(document_id: int) -> bool:
    collection = _get_chroma_collection()
    if collection is None:
        return True
    try:
        collection.delete(where={"document_id": document_id})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete Chroma document index: %s", exc)
        return False


def delete_course_index(course_id: int) -> bool:
    collection = _get_chroma_collection()
    if collection is None:
        return True
    try:
        collection.delete(where={"course_id": course_id})
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to delete Chroma course index: %s", exc)
        return False


def reconcile_course_index(db: Session, course_id: int) -> dict[str, int | bool | str]:
    """Remove Chroma rows that no longer have a live SQL chunk in this course.

    This is intentionally safe to run repeatedly. A failed delete is reported
    and can be retried by the next reindex/reconciliation run; searches remain
    safe in the meantime because they always re-check SQL.
    """
    collection = _get_chroma_collection()
    if collection is None:
        return {"available": False, "checked": 0, "stale": 0, "deleted": 0, "ok": True}
    try:
        response = collection.get(where={"course_id": course_id}, include=["metadatas"])
    except Exception as exc:  # noqa: BLE001 - Chroma is optional.
        logger.warning("Failed to inspect Chroma course index for reconciliation: %s", exc)
        return {
            "available": True,
            "checked": 0,
            "stale": 0,
            "deleted": 0,
            "ok": False,
            "error": str(exc)[:300],
        }

    raw_ids = [str(value) for value in response.get("ids") or []]
    live_ids = {
        row[0]
        for row in (
            db.query(DocumentChunk.id)
            .join(Document, Document.id == DocumentChunk.document_id)
            .join(Course, Course.id == Document.course_id)
            .filter(
                Course.id == course_id,
                Document.course_id == course_id,
                DocumentChunk.course_id == course_id,
                ~Document.status.in_(NON_RETRIEVABLE_DOCUMENT_STATUSES),
            )
            .all()
        )
    }
    stale_raw_ids = [
        raw_id
        for raw_id in raw_ids
        if (_parse_chroma_chunk_id(raw_id) == 0 or _parse_chroma_chunk_id(raw_id) not in live_ids)
    ]
    ok = _delete_chroma_ids(collection, stale_raw_ids, reason=f"course {course_id} reconciliation")
    return {
        "available": True,
        "checked": len(raw_ids),
        "stale": len(stale_raw_ids),
        "deleted": len(stale_raw_ids) if ok else 0,
        "ok": ok,
    }


def reconcile_vector_index(db: Session) -> dict[str, int | bool | str]:
    """Globally reconcile Chroma identifiers and metadata against live SQL rows."""
    collection = _get_chroma_collection()
    if collection is None:
        return {"available": False, "checked": 0, "stale": 0, "deleted": 0, "ok": True}
    try:
        response = collection.get(include=["metadatas"])
    except Exception as exc:  # noqa: BLE001 - optional index must not break SQL operations.
        logger.warning("Failed to inspect Chroma index for global reconciliation: %s", exc)
        return {
            "available": True,
            "checked": 0,
            "stale": 0,
            "deleted": 0,
            "ok": False,
            "error": str(exc)[:300],
        }

    raw_ids = [str(value) for value in response.get("ids") or []]
    metadatas = list(response.get("metadatas") or [])
    candidate_ids = {_parse_chroma_chunk_id(raw_id) for raw_id in raw_ids}
    candidate_ids.discard(0)
    rows = (
        db.query(DocumentChunk, Document, Course)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(Course, Course.id == Document.course_id)
        .filter(
            DocumentChunk.id.in_(candidate_ids),
            Document.course_id == DocumentChunk.course_id,
            ~Document.status.in_(NON_RETRIEVABLE_DOCUMENT_STATUSES),
        )
        .all()
        if candidate_ids
        else []
    )
    authoritative = {
        chunk.id: (chunk.document_id, chunk.course_id) for chunk, _document, _course in rows
    }
    stale_raw_ids: list[str] = []
    for index, raw_id in enumerate(raw_ids):
        chunk_id = _parse_chroma_chunk_id(raw_id)
        metadata = metadatas[index] if index < len(metadatas) else {}
        metadata = metadata or {}
        expected = authoritative.get(chunk_id)
        if expected is None:
            stale_raw_ids.append(raw_id)
            continue
        document_id, course_id = expected
        try:
            indexed_document_id = int(metadata.get("document_id") or 0)
            indexed_course_id = int(metadata.get("course_id") or 0)
        except (TypeError, ValueError):
            stale_raw_ids.append(raw_id)
            continue
        if indexed_document_id != document_id or indexed_course_id != course_id:
            stale_raw_ids.append(raw_id)

    ok = _delete_chroma_ids(collection, stale_raw_ids, reason="global reconciliation")
    return {
        "available": True,
        "checked": len(raw_ids),
        "stale": len(stale_raw_ids),
        "deleted": len(stale_raw_ids) if ok else 0,
        "ok": ok,
    }


def upsert_chunks_to_index(chunks: list[DocumentChunk]) -> None:
    _upsert_chroma_chunks(chunks)


def get_representative_chunks(db: Session, course_id: int, limit: int = 8) -> list[SearchResult]:
    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(Course, Course.id == Document.course_id)
        .filter(
            Course.id == course_id,
            Document.course_id == course_id,
            DocumentChunk.course_id == course_id,
            ~Document.status.in_(NON_RETRIEVABLE_DOCUMENT_STATUSES),
        )
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


def _search_course_sqlite(
    db: Session, course_id: int, query: str, limit: int
) -> list[SearchResult]:
    q_weights, q_norm = vectorize(query)
    if q_norm == 0:
        return []

    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(Course, Course.id == Document.course_id)
        .filter(
            Course.id == course_id,
            Document.course_id == course_id,
            DocumentChunk.course_id == course_id,
            ~Document.status.in_(NON_RETRIEVABLE_DOCUMENT_STATUSES),
        )
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
        collection.upsert(
            ids=ids, embeddings=batch.vectors, documents=documents, metadatas=metadatas
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to upsert Chroma chunks: %s", exc)


def _search_chroma_course(
    db: Session,
    course_id: int,
    query: str,
    limit: int,
) -> list[SearchResult]:
    collection = _get_chroma_collection()
    if collection is None or not query.strip():
        return []
    try:
        query_batch = embed_texts([query], purpose="query")
        response = collection.query(
            query_embeddings=query_batch.vectors,
            # Ask for a few extra candidates so stale rows do not crowd out
            # live SQL-backed results while reconciliation catches up.
            n_results=max(limit, limit * 3),
            where={"course_id": course_id},
            include=["documents", "metadatas", "distances"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to query Chroma, falling back to SQLite search: %s", exc)
        return []

    ids = (response.get("ids") or [[]])[0]
    metadatas = (response.get("metadatas") or [[]])[0]
    distances = (response.get("distances") or [[]])[0]
    ranked: list[tuple[str, int, float, str]] = []
    for index, raw_id in enumerate(ids):
        chunk_id = _parse_chroma_chunk_id(str(raw_id))
        metadata = metadatas[index] if index < len(metadatas) else {}
        metadata = metadata or {}
        distance = float(distances[index]) if index < len(distances) else 1.0
        ranked.append(
            (
                str(raw_id),
                chunk_id,
                max(0.0, 1.0 - distance),
                str(metadata.get("embedding_provider") or query_batch.provider),
            )
        )

    candidate_ids = {chunk_id for _raw_id, chunk_id, _score, _provider in ranked if chunk_id > 0}
    rows = (
        db.query(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .join(Course, Course.id == Document.course_id)
        .filter(
            DocumentChunk.id.in_(candidate_ids),
            Course.id == course_id,
            Document.course_id == course_id,
            DocumentChunk.course_id == course_id,
            ~Document.status.in_(NON_RETRIEVABLE_DOCUMENT_STATUSES),
        )
        .all()
        if candidate_ids
        else []
    )
    authoritative = {chunk.id: (chunk, document) for chunk, document in rows}

    # Invalid identifiers or SQL-deleted chunks are safe to remove. Hits that
    # exist in another SQL course are ignored but not deleted here.
    globally_live_ids = (
        {
            row[0]
            for row in db.query(DocumentChunk.id).filter(DocumentChunk.id.in_(candidate_ids)).all()
        }
        if candidate_ids
        else set()
    )
    stale_raw_ids = [
        raw_id
        for raw_id, chunk_id, _score, _provider in ranked
        if chunk_id == 0 or chunk_id not in globally_live_ids
    ]
    _delete_chroma_ids(collection, stale_raw_ids, reason="stale search hits")

    results: list[SearchResult] = []
    seen: set[int] = set()
    for _raw_id, chunk_id, score, provider in ranked:
        if chunk_id in seen or chunk_id not in authoritative:
            continue
        seen.add(chunk_id)
        chunk, document = authoritative[chunk_id]
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=document.id,
                document_name=document.original_filename,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=score,
                retrieval_provider=f"chroma/{provider}",
            )
        )
        if len(results) >= limit:
            break
    return results


def _delete_chroma_ids(collection: Any, raw_ids: list[str], *, reason: str) -> bool:
    if not raw_ids:
        return True
    try:
        collection.delete(ids=raw_ids)
        return True
    except Exception as exc:  # noqa: BLE001 - callers can retry/reconcile later.
        logger.warning("Failed to delete Chroma %s: %s", reason, exc)
        return False


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
