from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
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
    ProcessingJob,
    QuestionAttempt,
    ReviewTask,
    User,
    UserKnowledgeStatus,
)
from app.schemas import CourseCreate
from app.services.embedding_service import embedding_provider_label
from app.services.file_storage import (
    FileCleanupError,
    finalize_staged_deletions,
    restore_staged_deletions,
    stage_files_for_deletion,
)
from app.services.learning_service import get_dashboard_summary
from app.services.processing_jobs import (
    cancel_processing_job,
    complete_processing_job,
    create_processing_job,
    fail_processing_job,
    latest_jobs_by_document,
    processing_job_payload,
    start_processing_job,
)
from app.services.reindex_service import reindex_course
from app.services.vector_store import delete_course_index
from app.utils.time import utc_now

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
        document_count = (
            db.query(func.count(Document.id)).filter(Document.course_id == course.id).scalar() or 0
        )
        chunk_count = (
            db.query(func.count(DocumentChunk.id))
            .filter(DocumentChunk.course_id == course.id)
            .scalar()
            or 0
        )
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


@router.get("/dashboard-summary")
def read_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    courses = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .order_by(Course.updated_at.desc())
        .all()
    )
    payload = get_dashboard_summary(db, courses, str(current_user.id))
    payload["courses"] = []
    for course in courses:
        document_count = (
            db.query(func.count(Document.id)).filter(Document.course_id == course.id).scalar() or 0
        )
        chunk_count = (
            db.query(func.count(DocumentChunk.id))
            .filter(DocumentChunk.course_id == course.id)
            .scalar()
            or 0
        )
        payload["courses"].append(_course_payload(course, document_count, chunk_count))
    db.commit()
    return payload


@router.get("/{course_id}")
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = (
        db.query(Course).filter(Course.id == course_id, Course.user_id == current_user.id).first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    documents = (
        db.query(Document)
        .filter(Document.course_id == course_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.course_id == course_id, ProcessingJob.document_id.isnot(None))
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )
    latest_jobs = latest_jobs_by_document(jobs)
    chunk_count = (
        db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.course_id == course_id).scalar()
        or 0
    )
    payload = _course_payload(course, len(documents), chunk_count)
    payload["documents"] = [
        _document_payload(document, latest_jobs.get(document.id)) for document in documents
    ]
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


@router.post("/{course_id}/reindex")
def reindex_course_index(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = (
        db.query(Course).filter(Course.id == course_id, Course.user_id == current_user.id).first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    job = create_processing_job(
        db,
        course_id=course_id,
        document_id=None,
        job_type="reindex",
        error_message="课程重新索引任务已创建。",
    )
    db.commit()
    try:
        start_processing_job(
            db, job, stage="reindexing", progress=10, message="正在重新索引课程知识库。"
        )
        result = reindex_course(db, course_id)
        complete_processing_job(db, job, stage="completed", message="课程重新索引完成。")
        db.commit()
        db.refresh(job)
        result["job"] = processing_job_payload(job)
        return result
    except Exception as exc:  # noqa: BLE001 - keep failure retryable through ProcessingJob.
        message = str(exc).strip()[:500] or "重新索引失败，请稍后重试。"
        fail_processing_job(db, job, stage="failed", message=message)
        db.commit()
        raise HTTPException(status_code=500, detail=message) from exc


@router.delete("/{course_id}")
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = (
        db.query(Course).filter(Course.id == course_id, Course.user_id == current_user.id).first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")

    documents = db.query(Document).filter(Document.course_id == course_id).all()
    message = "课程删除前已取消相关后台任务。"
    for job in (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.course_id == course_id,
            ProcessingJob.status.in_(("queued", "running")),
        )
        .all()
    ):
        cancel_processing_job(db, job, message=message)
    now = utc_now()
    (
        db.query(OcrJob)
        .filter(OcrJob.course_id == course_id, OcrJob.status.in_(("queued", "running")))
        .update(
            {
                OcrJob.status: "cancelled",
                OcrJob.finished_at: now,
                OcrJob.error_message: message,
                OcrJob.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    for document in documents:
        document.status = "deleting"
        document.processing_stage = "deleting"
        document.processing_progress = 100
        document.error_message = message
    db.commit()

    file_paths = [Path(document.file_path) for document in documents]
    try:
        staged_files = stage_files_for_deletion(file_paths, allowed_root=settings.upload_dir)
    except FileCleanupError as exc:
        for document in db.query(Document).filter(Document.course_id == course_id).all():
            document.status = "indexed" if document.chunk_count else "cancelled"
            document.processing_stage = "cleanup_failed"
            document.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    try:
        _delete_course_dependents(db, course_id)
        db.delete(course)
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_deletions(staged_files)
        raise

    vector_deleted = delete_course_index(course_id)
    cleanup_failures = finalize_staged_deletions(staged_files)
    _remove_empty_course_directory(settings.upload_dir / str(course_id))
    warnings: list[str] = []
    if not vector_deleted:
        warnings.append("向量索引清理失败；SQL 已删除课程，陈旧结果不会被授权检索，可稍后对账。")
    if cleanup_failures:
        warnings.append("部分临时清理文件删除失败，请检查 storage/uploads。")
    payload: dict = {"ok": True}
    if warnings:
        payload["warning"] = " ".join(warnings)
    return payload


def _course_payload(course: Course, document_count: int, chunk_count: int) -> dict:
    return {
        "id": course.id,
        "user_id": course.user_id,
        "name": course.name,
        "description": course.description,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "embedding_provider": embedding_provider_label(),
        "last_asked_at": course.last_asked_at,
        "created_at": course.created_at,
        "updated_at": course.updated_at,
    }


def _document_payload(document: Document, latest_job: ProcessingJob | None = None) -> dict:
    payload = {
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
    payload["latest_job"] = processing_job_payload(latest_job, document) if latest_job else None
    return payload


def _chat_message_payload(message: ChatMessage) -> dict:
    source_record = _parse_chat_sources(message.sources_json)
    return {
        "id": message.id,
        "course_id": message.course_id,
        "question": message.question,
        "answer": message.answer,
        "sources": source_record["sources"],
        "answer_status": source_record["answer_status"],
        "confidence": source_record["confidence"],
        "source_count": source_record["source_count"],
        "retrieval_provider": source_record["retrieval_provider"],
        "llm_provider": source_record["llm_provider"],
        "created_at": message.created_at,
    }


def _parse_chat_sources(raw_json: str) -> dict:
    try:
        raw = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        raw = []
    if isinstance(raw, list):
        return {
            "sources": raw,
            "answer_status": "answered" if raw else "empty_knowledge_base",
            "confidence": "medium" if raw else "low",
            "source_count": len(raw),
            "retrieval_provider": "",
            "llm_provider": "",
        }
    if isinstance(raw, dict):
        sources = raw.get("sources") or []
        return {
            "sources": sources if isinstance(sources, list) else [],
            "answer_status": raw.get("answer_status")
            or ("answered" if sources else "empty_knowledge_base"),
            "confidence": raw.get("confidence") or ("medium" if sources else "low"),
            "source_count": int(raw.get("source_count") or len(sources)),
            "retrieval_provider": raw.get("retrieval_provider") or "",
            "llm_provider": raw.get("llm_provider") or "",
        }
    return {
        "sources": [],
        "answer_status": "empty_knowledge_base",
        "confidence": "low",
        "source_count": 0,
        "retrieval_provider": "",
        "llm_provider": "",
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
        ProcessingJob,
    ):
        db.query(model).filter(model.course_id == course_id).delete(synchronize_session=False)


def _remove_empty_course_directory(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return
