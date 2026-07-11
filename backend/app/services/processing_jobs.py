from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import Document, OcrJob, ProcessingJob
from app.utils.time import utc_now

ACTIVE_STATUSES = {"queued", "running"}
ACTIVE_DOCUMENT_STATUSES = {
    "queued",
    "uploaded",
    "parsing",
    "chunking",
    "indexing",
    "syncing_knowledge_points",
    "ocr_queued",
    "ocr_processing",
    "vision_processing",
}
CANCEL_MARKED_MESSAGE = (
    "任务已标记取消；FastAPI BackgroundTasks 不能强制中断已开始的工作，已写入结果会保留。"
)
INTERRUPTED_JOB_MESSAGE = (
    "服务进程已重启，FastAPI BackgroundTasks 不会自动恢复该任务；请确认已写入结果后手动重试。"
)


def create_processing_job(
    db: Session,
    *,
    course_id: int,
    document_id: int | None,
    job_type: str,
    status: str = "queued",
    stage: str = "queued",
    progress: int = 0,
    error_message: str = "",
    metadata: dict[str, Any] | None = None,
) -> ProcessingJob:
    job = ProcessingJob(
        course_id=course_id,
        document_id=document_id,
        job_type=job_type,
        status=status,
        stage=stage,
        progress=_clamp_progress(progress),
        error_message=error_message,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
    )
    db.add(job)
    db.flush()
    return job


def start_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str = "running",
    progress: int = 1,
    message: str = "",
) -> bool:
    if job is None:
        return False
    now = utc_now()
    return _conditional_job_update(
        db,
        job,
        allowed_statuses=ACTIVE_STATUSES,
        values={
            ProcessingJob.status: "running",
            ProcessingJob.stage: stage,
            ProcessingJob.progress: _clamp_progress(progress),
            ProcessingJob.error_message: message,
            ProcessingJob.started_at: func.coalesce(ProcessingJob.started_at, now),
            ProcessingJob.finished_at: None,
            ProcessingJob.updated_at: now,
        },
    )


def update_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str,
    progress: int,
    message: str = "",
) -> bool:
    if job is None:
        return False
    now = utc_now()
    return _conditional_job_update(
        db,
        job,
        allowed_statuses=ACTIVE_STATUSES,
        values={
            ProcessingJob.status: "running",
            ProcessingJob.stage: stage,
            ProcessingJob.progress: _clamp_progress(progress),
            ProcessingJob.error_message: message,
            ProcessingJob.started_at: func.coalesce(ProcessingJob.started_at, now),
            ProcessingJob.updated_at: now,
        },
    )


def complete_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str = "completed",
    message: str = "",
) -> bool:
    if job is None:
        return False
    now = utc_now()
    return _conditional_job_update(
        db,
        job,
        allowed_statuses=ACTIVE_STATUSES,
        values={
            ProcessingJob.status: "completed",
            ProcessingJob.stage: stage,
            ProcessingJob.progress: 100,
            ProcessingJob.error_message: message,
            ProcessingJob.started_at: func.coalesce(ProcessingJob.started_at, now),
            ProcessingJob.finished_at: now,
            ProcessingJob.updated_at: now,
        },
    )


def fail_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str = "failed",
    message: str,
) -> bool:
    if job is None:
        return False
    now = utc_now()
    return _conditional_job_update(
        db,
        job,
        allowed_statuses=ACTIVE_STATUSES,
        values={
            ProcessingJob.status: "failed",
            ProcessingJob.stage: stage,
            ProcessingJob.progress: 100,
            ProcessingJob.error_message: message[:1000],
            ProcessingJob.started_at: func.coalesce(ProcessingJob.started_at, now),
            ProcessingJob.finished_at: now,
            ProcessingJob.updated_at: now,
        },
    )


def cancel_processing_job(
    db: Session,
    job: ProcessingJob,
    *,
    message: str = CANCEL_MARKED_MESSAGE,
) -> ProcessingJob:
    now = utc_now()
    _conditional_job_update(
        db,
        job,
        allowed_statuses=ACTIVE_STATUSES,
        values={
            ProcessingJob.status: "cancelled",
            ProcessingJob.stage: "cancelled",
            ProcessingJob.progress: 100,
            ProcessingJob.error_message: message,
            ProcessingJob.finished_at: now,
            ProcessingJob.updated_at: now,
        },
    )
    return job


def recover_interrupted_processing_jobs(db: Session) -> int:
    """Mark in-memory BackgroundTasks left behind by a process restart as retryable failures."""
    recovered = 0
    now = utc_now()
    jobs = db.query(ProcessingJob).filter(ProcessingJob.status.in_(ACTIVE_STATUSES)).all()
    for job in jobs:
        job.status = "failed"
        job.stage = "interrupted"
        job.progress = 100
        job.error_message = INTERRUPTED_JOB_MESSAGE
        job.started_at = job.started_at or job.created_at or now
        job.finished_at = now
        _mark_document_interrupted(db, job)
        recovered += 1

    ocr_jobs = db.query(OcrJob).filter(OcrJob.status.in_(ACTIVE_STATUSES)).all()
    for ocr_job in ocr_jobs:
        ocr_job.status = "failed"
        ocr_job.error_message = INTERRUPTED_JOB_MESSAGE
        ocr_job.finished_at = now
        document = db.get(Document, ocr_job.document_id)
        if document and document.status in ACTIVE_DOCUMENT_STATUSES:
            document.status = "needs_ocr"
            document.processing_stage = "interrupted"
            document.processing_progress = 100
            document.error_message = INTERRUPTED_JOB_MESSAGE
        recovered += 1

    if recovered:
        db.flush()
    return recovered


def reset_failed_processing_job(db: Session, job: ProcessingJob) -> bool:
    return _conditional_job_update(
        db,
        job,
        allowed_statuses={"failed", "cancelled"},
        values={
            ProcessingJob.status: "queued",
            ProcessingJob.stage: "queued",
            ProcessingJob.progress: 0,
            ProcessingJob.error_message: "",
            ProcessingJob.started_at: None,
            ProcessingJob.finished_at: None,
            ProcessingJob.updated_at: utc_now(),
        },
    )


def job_metadata(job: ProcessingJob | None) -> dict[str, Any]:
    if job is None:
        return {}
    try:
        payload = json.loads(job.metadata_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def set_job_metadata(db: Session, job: ProcessingJob, metadata: dict[str, Any]) -> None:
    job.metadata_json = json.dumps(metadata, ensure_ascii=False)
    db.flush()


def processing_job_payload(job: ProcessingJob, document: Document | None = None) -> dict:
    metadata = job_metadata(job)
    safe_metadata = {
        key: metadata[key]
        for key in ("ocr_job_id", "start_page", "max_pages", "mode")
        if key in metadata
    }
    return {
        "id": job.id,
        "course_id": job.course_id,
        "document_id": job.document_id,
        "job_type": job.job_type,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "metadata": safe_metadata,
        "ocr_job_id": safe_metadata.get("ocr_job_id") if job.job_type == "ocr" else None,
        "document": _document_summary(document) if document is not None else None,
    }


def latest_jobs_by_document(jobs: list[ProcessingJob]) -> dict[int, ProcessingJob]:
    latest: dict[int, ProcessingJob] = {}
    for job in jobs:
        if job.document_id is None:
            continue
        current = latest.get(job.document_id)
        if current is None or job.created_at > current.created_at:
            latest[job.document_id] = job
    return latest


def _document_summary(document: Document) -> dict:
    return {
        "id": document.id,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "status": document.status,
        "processing_stage": document.processing_stage,
        "processing_progress": document.processing_progress,
        "chunk_count": document.chunk_count,
    }


def _clamp_progress(value: int) -> int:
    return max(0, min(100, int(value)))


def _conditional_job_update(
    db: Session,
    job: ProcessingJob,
    *,
    allowed_statuses: set[str],
    values: dict,
) -> bool:
    """Apply a state transition only while the persisted job is eligible.

    The status predicate is evaluated by the database, which closes the race
    where a worker holds a stale ORM object after another request cancels it.
    """
    with db.no_autoflush:
        updated = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.id == job.id,
                ProcessingJob.status.in_(allowed_statuses),
            )
            .update(values, synchronize_session=False)
        )
    if not updated:
        return False
    db.flush()
    db.refresh(job)
    return True


def _mark_document_interrupted(db: Session, job: ProcessingJob) -> None:
    if job.document_id is None:
        return
    document = db.get(Document, job.document_id)
    if document is None or document.status not in ACTIVE_DOCUMENT_STATUSES:
        return
    if job.job_type == "ocr":
        document.status = "needs_ocr"
    elif job.job_type == "document_parse":
        document.status = "failed"
    elif job.job_type == "knowledge_sync":
        document.status = "indexed" if document.chunk_count else "failed"
    elif job.job_type == "reindex":
        document.status = "indexed" if document.chunk_count else "failed"
    else:
        document.status = "failed"
    document.processing_stage = "interrupted"
    document.processing_progress = 100
    document.error_message = INTERRUPTED_JOB_MESSAGE
