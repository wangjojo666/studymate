from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import Document, ProcessingJob
from app.utils.time import utc_now


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


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
) -> None:
    if job is None:
        return
    if job.status == "cancelled":
        return
    job.status = "running"
    job.stage = stage
    job.progress = _clamp_progress(progress)
    job.error_message = message
    job.started_at = job.started_at or utc_now()
    job.finished_at = None
    db.flush()


def update_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str,
    progress: int,
    message: str = "",
) -> None:
    if job is None or job.status == "cancelled":
        return
    job.status = "running"
    job.stage = stage
    job.progress = _clamp_progress(progress)
    job.error_message = message
    job.started_at = job.started_at or utc_now()
    db.flush()


def complete_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str = "completed",
    message: str = "",
) -> None:
    if job is None:
        return
    if job.status == "cancelled":
        return
    job.status = "completed"
    job.stage = stage
    job.progress = 100
    job.error_message = message
    job.started_at = job.started_at or utc_now()
    job.finished_at = utc_now()
    db.flush()


def fail_processing_job(
    db: Session,
    job: ProcessingJob | None,
    *,
    stage: str = "failed",
    message: str,
) -> None:
    if job is None:
        return
    if job.status == "cancelled":
        return
    job.status = "failed"
    job.stage = stage
    job.progress = 100
    job.error_message = message[:1000]
    job.started_at = job.started_at or utc_now()
    job.finished_at = utc_now()
    db.flush()


def cancel_processing_job(
    db: Session,
    job: ProcessingJob,
    *,
    message: str = "任务已取消。",
) -> ProcessingJob:
    if job.status not in TERMINAL_STATUSES:
        job.status = "cancelled"
        job.stage = "cancelled"
        job.progress = 100
        job.error_message = message
        job.finished_at = utc_now()
        db.flush()
    return job


def reset_failed_processing_job(db: Session, job: ProcessingJob) -> ProcessingJob:
    job.status = "queued"
    job.stage = "queued"
    job.progress = 0
    job.error_message = ""
    job.started_at = None
    job.finished_at = None
    db.flush()
    return job


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
