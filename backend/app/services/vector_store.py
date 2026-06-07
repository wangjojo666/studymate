from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Document, DocumentChunk
from app.services.chunker import TextChunk


TOKEN_RE = re.compile("[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")


@dataclass(frozen=True)
class SearchResult:
    chunk_id: int
    document_id: int
    document_name: str
    page_number: int
    chunk_index: int
    content: str
    score: float


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


def index_document_chunks(
    db: Session,
    document: Document,
    chunks: list[TextChunk],
    replace_document: bool = True,
    replace_page_numbers: list[int] | None = None,
) -> None:
    if replace_document:
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        first_index = 0
    else:
        page_numbers = sorted(set(replace_page_numbers or [chunk.page_number for chunk in chunks]))
        if page_numbers:
            db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document.id,
                DocumentChunk.page_number.in_(page_numbers),
            ).delete()
        max_index = (
            db.query(func.max(DocumentChunk.chunk_index))
            .filter(DocumentChunk.document_id == document.id)
            .scalar()
        )
        first_index = int(max_index or -1) + 1

    for offset, chunk in enumerate(chunks):
        weights, norm = vectorize(chunk.content)
        db.add(
            DocumentChunk(
                course_id=document.course_id,
                document_id=document.id,
                chunk_index=first_index + offset,
                page_number=chunk.page_number,
                content=chunk.content,
                token_weights=json.dumps(weights, ensure_ascii=False),
                vector_norm=norm,
            )
        )
    db.flush()
    document.chunk_count = (
        db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.document_id == document.id).scalar() or 0
    )
    document.status = "indexed" if document.chunk_count else "empty"
    db.flush()


def search_course(db: Session, course_id: int, query: str, limit: int = 5) -> list[SearchResult]:
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
            )
        )
    results.sort(key=lambda item: item.score, reverse=True)
    return results[:limit]


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
        )
        for chunk, document in rows
    ]
