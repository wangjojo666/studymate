from __future__ import annotations

import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Document, DocumentChunk
from app.services.embedding_service import embedding_provider_label
from app.services.vector_store import (
    delete_chunks_from_index,
    delete_course_index,
    delete_document_index,
    upsert_chunks_to_index,
    vectorize,
)
from app.utils.time import utc_now


def reindex_course(db: Session, course_id: int) -> dict:
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.course_id == course_id)
        .order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc())
        .all()
    )
    delete_course_index(course_id)
    _refresh_chunk_sparse_vectors(chunks)
    upsert_chunks_to_index(chunks)

    documents = db.query(Document).filter(Document.course_id == course_id).all()
    touched_document_ids = {chunk.document_id for chunk in chunks}
    for document in documents:
        document.chunk_count = (
            db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.document_id == document.id).scalar() or 0
        )
        if document.id in touched_document_ids:
            document.status = "indexed" if document.chunk_count else "empty"
            document.processing_stage = document.status
            document.processing_progress = 100
            document.indexed_at = utc_now()
    db.commit()
    return {
        "ok": True,
        "scope": "course",
        "course_id": course_id,
        "document_count": len(touched_document_ids),
        "chunk_count": len(chunks),
        "embedding_provider": embedding_provider_label(),
    }


def reindex_document(db: Session, document: Document) -> dict:
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index.asc())
        .all()
    )
    if chunks:
        delete_chunks_from_index([chunk.id for chunk in chunks])
    else:
        delete_document_index(document.id)
    _refresh_chunk_sparse_vectors(chunks)
    upsert_chunks_to_index(chunks)

    document.chunk_count = len(chunks)
    if chunks:
        document.status = "indexed"
        document.processing_stage = "indexed"
        document.processing_progress = 100
        document.indexed_at = utc_now()
    db.commit()
    return {
        "ok": True,
        "scope": "document",
        "course_id": document.course_id,
        "document_id": document.id,
        "document_name": document.original_filename,
        "chunk_count": len(chunks),
        "embedding_provider": embedding_provider_label(),
    }


def _refresh_chunk_sparse_vectors(chunks: list[DocumentChunk]) -> None:
    for chunk in chunks:
        weights, norm = vectorize(chunk.content)
        chunk.token_weights = json.dumps(weights, ensure_ascii=False)
        chunk.vector_norm = norm
