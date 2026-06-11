from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.entities import (
    ChatMessage,
    ChunkKnowledgePoint,
    Course,
    Document,
    DocumentChunk,
    GeneratedMaterial,
    OcrJob,
    QuestionAttempt,
    ReviewTask,
    User,
    UserKnowledgeStatus,
)
from app.schemas import CourseCreate
from app.services.vector_store import delete_course_index


router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    rows = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .order_by(Course.updated_at.desc())
        .all()
    )
    result: list[dict] = []
    for course in rows:
        document_count = db.query(func.count(Document.id)).filter(Document.course_id == course.id).scalar() or 0
        chunk_count = db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.course_id == course.id).scalar() or 0
        result.append(_course_payload(course, document_count, chunk_count))
    return result


@router.post("")
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    exists = (
        db.query(Course)
        .filter(Course.user_id == current_user.id, Course.name == payload.name.strip())
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="课程名称已存在")
    course = Course(
        user_id=current_user.id,
        name=payload.name.strip(),
        description=payload.description.strip(),
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return _course_payload(course, 0, 0)


@router.get("/{course_id}")
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.user_id == current_user.id)
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    documents = (
        db.query(Document)
        .filter(Document.course_id == course_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    chunk_count = db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.course_id == course_id).scalar() or 0
    payload = _course_payload(course, len(documents), chunk_count)
    payload["documents"] = [_document_payload(document) for document in documents]
    payload["recent_messages"] = [
        _chat_message_payload(message)
        for message in (
            db.query(ChatMessage)
            .filter(ChatMessage.course_id == course_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(6)
            .all()
        )
    ]
    return payload


@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.user_id == current_user.id)
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    delete_course_index(course_id)
    _delete_course_dependents(db, course_id)
    db.delete(course)
    db.commit()
    return {"ok": True}


def _course_payload(course: Course, document_count: int, chunk_count: int) -> dict:
    return {
        "id": course.id,
        "user_id": course.user_id,
        "name": course.name,
        "description": course.description,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "last_asked_at": course.last_asked_at,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
    }


def _document_payload(document: Document) -> dict:
    return {
        "id": document.id,
        "course_id": document.course_id,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "status": document.status,
        "processing_stage": document.processing_stage,
        "processing_progress": document.processing_progress,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
        "error_message": document.error_message,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "indexed_at": document.indexed_at,
    }


def _chat_message_payload(message: ChatMessage) -> dict:
    return {
        "id": message.id,
        "course_id": message.course_id,
        "question": message.question,
        "answer": message.answer,
        "sources": json.loads(message.sources_json or "[]"),
        "created_at": message.created_at,
    }


def _delete_course_dependents(db: Session, course_id: int) -> None:
    for model in (
        ChatMessage,
        GeneratedMaterial,
        QuestionAttempt,
        ReviewTask,
        UserKnowledgeStatus,
        ChunkKnowledgePoint,
        OcrJob,
    ):
        db.query(model).filter(model.course_id == course_id).delete(synchronize_session=False)
