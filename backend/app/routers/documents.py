from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import get_current_user, learning_user_id
from app.models.entities import (
    ChunkKnowledgePoint,
    Course,
    Document,
    DocumentChunk,
    KnowledgePoint,
    OcrJob,
    ProcessingJob,
    User,
)
from app.schemas import OcrRequest
from app.services.chunker import split_pages_into_chunks
from app.services.document_parser import parse_document
from app.services.file_storage import (
    FileCleanupError,
    finalize_staged_deletions,
    restore_staged_deletions,
    stage_files_for_deletion,
)
from app.services.learning_service import sync_course_knowledge_points
from app.services.ocr_service import ocr_pdf_with_qwen_vl
from app.services.processing_jobs import (
    CANCEL_MARKED_MESSAGE,
    cancel_processing_job,
    complete_processing_job,
    create_processing_job,
    fail_processing_job,
    job_metadata,
    latest_jobs_by_document,
    processing_job_payload,
    reset_failed_processing_job,
    set_job_metadata,
    start_processing_job,
    update_processing_job,
)
from app.services.reindex_service import reindex_course, reindex_document
from app.services.upload_validation import UploadValidationError, validate_upload_file
from app.services.vector_store import (
    delete_chunks_from_index,
    delete_document_index,
    index_document_chunks,
)
from app.services.vision_service import IMAGE_SUFFIXES, describe_courseware_image
from app.utils.time import utc_now

router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])
jobs_router = APIRouter(prefix="/courses/{course_id}/jobs", tags=["processing-jobs"])

OCR_MODE_LABELS = {
    "fast": "快速索引",
    "full": "精确 OCR",
}

UPLOAD_CHUNK_SIZE = 1024 * 1024


class _ProcessingCancelled(RuntimeError):
    """Internal control flow used when a conditional job update loses to cancel."""


@router.post("")
def upload_document(
    course_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = _get_owned_course(db, course_id, current_user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".pptx", ".docx", ".txt", *IMAGE_SUFFIXES}:
        raise HTTPException(status_code=400, detail="仅支持 PDF、PPTX、DOCX、TXT、PNG、JPG、WEBP")
    max_bytes = _max_upload_bytes(suffix)

    course_dir = settings.upload_dir / str(course_id)
    course_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}{suffix}"
    target = course_dir / stored_filename
    temporary_target = course_dir / f".{uuid4().hex}.upload"
    _save_upload_with_limit(file, temporary_target, max_bytes)
    try:
        validate_upload_file(temporary_target, suffix)
        temporary_target.replace(target)
    except UploadValidationError as exc:
        temporary_target.unlink(missing_ok=True)
        _remove_empty_parent(course_dir)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        temporary_target.unlink(missing_ok=True)
        _remove_empty_parent(course_dir)
        raise HTTPException(status_code=500, detail="上传文件落盘失败，请重试") from exc

    document = Document(
        course_id=course_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_type=suffix.replace(".", ""),
        file_path=str(target),
        status="queued",
        processing_stage="uploaded",
        processing_progress=0,
        error_message="已上传，等待后台解析。",
    )
    try:
        db.add(document)
        db.flush()
        job = create_processing_job(
            db,
            course_id=course_id,
            document_id=document.id,
            job_type="document_parse",
            error_message="资料已上传，等待后台解析。",
        )
        db.commit()
        db.refresh(document)
        db.refresh(job)
    except Exception:
        db.rollback()
        target.unlink(missing_ok=True)
        _remove_empty_parent(course_dir)
        raise

    background_tasks.add_task(
        _process_uploaded_document, document.id, learning_user_id(current_user), job.id
    )
    payload = _document_payload(document)
    payload["latest_job"] = processing_job_payload(job, document)
    return payload


@router.get("")
def list_documents(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    course = _get_owned_course(db, course_id, current_user.id)
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
    return [_document_payload(document, latest_jobs.get(document.id)) for document in documents]


@router.delete("/{document_id}")
def delete_document(
    course_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = _get_owned_course(db, course_id, current_user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")

    file_path = Path(document.file_path)
    _cancel_document_jobs_for_deletion(db, document)
    document.status = "deleting"
    document.processing_stage = "deleting"
    document.processing_progress = 100
    document.error_message = "资料正在删除，相关后台任务已取消。"
    db.commit()

    try:
        staged_files = stage_files_for_deletion([file_path], allowed_root=settings.upload_dir)
    except FileCleanupError as exc:
        document = db.get(Document, document_id)
        if document is not None:
            document.status = "indexed" if document.chunk_count else "cancelled"
            document.processing_stage = "cleanup_failed"
            document.error_message = str(exc)
            db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    chunk_ids = [
        row[0]
        for row in db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document_id).all()
    ]
    try:
        if chunk_ids:
            db.query(ChunkKnowledgePoint).filter(
                ChunkKnowledgePoint.chunk_id.in_(chunk_ids)
            ).delete(synchronize_session=False)
        db.query(ProcessingJob).filter(ProcessingJob.document_id == document_id).delete(
            synchronize_session=False
        )
        db.query(OcrJob).filter(OcrJob.document_id == document_id).delete(synchronize_session=False)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(
            synchronize_session=False
        )
        (
            db.query(KnowledgePoint)
            .filter(KnowledgePoint.source_document_id == document_id)
            .update(
                {
                    KnowledgePoint.source_document_id: None,
                    KnowledgePoint.source_page: 0,
                    KnowledgePoint.evidence: "来源资料已删除，请重新同步或上传资料。",
                },
                synchronize_session=False,
            )
        )
        db.delete(document)
        db.commit()
    except Exception:
        db.rollback()
        restore_staged_deletions(staged_files)
        raise

    vector_deleted = (
        delete_chunks_from_index(chunk_ids) if chunk_ids else delete_document_index(document_id)
    )
    cleanup_failures = finalize_staged_deletions(staged_files)
    _remove_empty_parent(file_path.parent)
    warnings: list[str] = []
    if not vector_deleted:
        warnings.append(
            "向量索引清理失败；SQL 记录已删除，检索会过滤陈旧结果，可稍后运行重新索引对账。"
        )
    if cleanup_failures:
        warnings.append("资料记录已删除，但临时清理文件删除失败，请检查 storage/uploads。")
    payload: dict = {"ok": True}
    if warnings:
        payload["warning"] = " ".join(warnings)
    return payload


def _cancel_document_jobs_for_deletion(db: Session, document: Document) -> None:
    message = "资料删除前已取消相关后台任务。"
    processing_jobs = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.document_id == document.id,
            ProcessingJob.status.in_(("queued", "running")),
        )
        .all()
    )
    for job in processing_jobs:
        cancel_processing_job(db, job, message=message)

    ocr_jobs = (
        db.query(OcrJob)
        .filter(OcrJob.document_id == document.id, OcrJob.status.in_(("queued", "running")))
        .all()
    )
    for job in ocr_jobs:
        _conditional_ocr_job_update(
            db,
            job,
            allowed_statuses={"queued", "running"},
            values={
                OcrJob.status: "cancelled",
                OcrJob.finished_at: utc_now(),
                OcrJob.error_message: message,
                OcrJob.updated_at: utc_now(),
            },
        )


@router.post("/{document_id}/reindex")
def reindex_single_document(
    course_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = _get_owned_course(db, course_id, current_user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    job = create_processing_job(
        db,
        course_id=course_id,
        document_id=document.id,
        job_type="reindex",
        error_message="资料重新索引任务已创建。",
    )
    db.commit()
    try:
        start_processing_job(
            db, job, stage="reindexing", progress=10, message="正在重新索引资料片段。"
        )
        result = reindex_document(db, document)
        complete_processing_job(db, job, stage="completed", message="资料重新索引完成。")
        db.commit()
        db.refresh(job)
        result["job"] = processing_job_payload(job, document)
        return result
    except Exception as exc:  # noqa: BLE001 - expose reindex failure as a retryable job.
        message = _friendly_error(exc)
        fail_processing_job(db, job, stage="failed", message=message)
        db.commit()
        raise HTTPException(status_code=500, detail=message) from exc


@router.post("/{document_id}/vision")
def index_image_document(
    course_id: int,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = _get_owned_course(db, course_id, current_user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    if f".{document.file_type.lower()}" not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="只有图片课件需要视觉识别入库")

    document.status = "vision_processing"
    document.error_message = "正在识别图片课件内容。"
    db.commit()
    try:
        _index_image_document(db, course, document, learning_user_id(current_user))
        db.commit()
        db.refresh(document)
    except Exception as exc:  # noqa: BLE001 - surface vision failure to the UI.
        document.status = "needs_vision"
        document.error_message = str(exc)
        db.commit()
        db.refresh(document)
    return _document_payload(document)


@router.post("/{document_id}/ocr")
def ocr_document(
    course_id: int,
    document_id: int,
    payload: OcrRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    course = _get_owned_course(db, course_id, current_user.id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    if document.file_type != "pdf":
        raise HTTPException(status_code=400, detail="只有扫描版 PDF 需要 OCR")
    if payload.max_pages > settings.ocr_max_pages_per_request:
        raise HTTPException(
            status_code=400,
            detail=f"OCR 单次最多处理 {settings.ocr_max_pages_per_request} 页，请减少页数后重试",
        )

    running_job = (
        db.query(OcrJob)
        .filter(
            OcrJob.document_id == document_id,
            OcrJob.status.in_(("queued", "running")),
        )
        .first()
    )
    if running_job:
        raise HTTPException(status_code=409, detail="该资料已有 OCR 任务正在运行")

    job = OcrJob(
        course_id=course_id,
        document_id=document_id,
        status="queued",
        start_page=payload.start_page,
        max_pages=payload.max_pages,
        total_pages=document.page_count,
    )
    processing_job = create_processing_job(
        db,
        course_id=course_id,
        document_id=document_id,
        job_type="ocr",
        error_message="OCR 任务已创建，等待后台处理。",
        metadata={
            "start_page": payload.start_page,
            "max_pages": payload.max_pages,
            "mode": payload.mode,
        },
    )
    db.add(job)
    document.status = "ocr_queued"
    document.processing_stage = "ocr_queued"
    document.processing_progress = 0
    mode_label = OCR_MODE_LABELS.get(payload.mode, "快速索引")
    job.error_message = (
        f"[mode:{payload.mode}] {mode_label}任务已加入后台队列：从第 {payload.start_page} 页开始，"
        f"最多处理 {payload.max_pages} 页。"
    )
    document.error_message = f"{mode_label}任务已加入后台队列：从第 {payload.start_page} 页开始，最多处理 {payload.max_pages} 页。"
    db.commit()
    set_job_metadata(
        db,
        processing_job,
        {
            "ocr_job_id": job.id,
            "start_page": payload.start_page,
            "max_pages": payload.max_pages,
            "mode": payload.mode,
        },
    )
    db.commit()
    db.refresh(job)
    db.refresh(document)
    db.refresh(processing_job)

    background_tasks.add_task(_run_ocr_job, job.id, processing_job.id)
    payload = _ocr_job_payload(job, document)
    payload["processing_job"] = processing_job_payload(processing_job, document)
    return payload


@router.get("/{document_id}/ocr-jobs/{job_id}")
def get_ocr_job(
    course_id: int,
    document_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if _get_owned_course(db, course_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    job = db.get(OcrJob, job_id)
    if job is None or job.course_id != course_id or job.document_id != document_id:
        raise HTTPException(status_code=404, detail="OCR 任务不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    return _ocr_job_payload(job, document)


@router.post("/{document_id}/ocr-jobs/{job_id}/cancel")
def cancel_ocr_job(
    course_id: int,
    document_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if _get_owned_course(db, course_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    job = db.get(OcrJob, job_id)
    if job is None or job.course_id != course_id or job.document_id != document_id:
        raise HTTPException(status_code=404, detail="OCR 任务不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    if job.status in {"completed", "failed", "cancelled"}:
        return _ocr_job_payload(job, document)

    cancel_message = (
        f"OCR 已标记取消；后台会在下一次检查后停止，已保留 {job.processed_pages} 页识别结果。"
    )
    if not _conditional_ocr_job_update(
        db,
        job,
        allowed_statuses={"queued", "running"},
        values={
            OcrJob.status: "cancelled",
            OcrJob.finished_at: utc_now(),
            OcrJob.error_message: cancel_message,
            OcrJob.updated_at: utc_now(),
        },
    ):
        return _ocr_job_payload(job, document)
    document.status = "indexed" if document.chunk_count else "needs_ocr"
    document.processing_stage = document.status
    document.processing_progress = 100
    document.error_message = cancel_message
    processing_job = _find_processing_job_for_ocr(db, job.id)
    if processing_job:
        cancel_processing_job(db, processing_job, message=cancel_message)
    db.commit()
    db.refresh(job)
    db.refresh(document)
    return _ocr_job_payload(job, document)


@jobs_router.get("")
def list_processing_jobs(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    if _get_owned_course(db, course_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    documents = {
        document.id: document
        for document in db.query(Document).filter(Document.course_id == course_id).all()
    }
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.course_id == course_id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(100)
        .all()
    )
    return [processing_job_payload(job, documents.get(job.document_id or 0)) for job in jobs]


@jobs_router.post("/{job_id}/retry")
def retry_processing_job(
    course_id: int,
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if _get_owned_course(db, course_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    job = db.get(ProcessingJob, job_id)
    if job is None or job.course_id != course_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status not in {"failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="只有失败或已取消的任务可以重试")

    document = db.get(Document, job.document_id) if job.document_id else None
    if job.document_id and (document is None or document.course_id != course_id):
        raise HTTPException(status_code=404, detail="任务关联的资料不存在")
    if job.job_type in {"document_parse", "ocr"} and document is None:
        raise HTTPException(status_code=400, detail="任务缺少关联资料，无法重试")
    if _has_active_processing_job(db, job, document):
        raise HTTPException(
            status_code=409, detail="同一资料或课程已有同类任务正在运行，请等待当前任务结束后再重试"
        )
    if job.job_type == "ocr" and document is not None:
        running_ocr_job = (
            db.query(OcrJob)
            .filter(
                OcrJob.document_id == document.id,
                OcrJob.status.in_(("queued", "running")),
            )
            .first()
        )
        if running_ocr_job:
            raise HTTPException(
                status_code=409, detail="该资料已有 OCR 任务正在运行，请等待当前任务结束后再重试"
            )

    if not reset_failed_processing_job(db, job):
        raise HTTPException(status_code=409, detail="任务状态已被其他请求更新，请刷新后重试")
    db.commit()
    db.refresh(job)

    if job.job_type == "document_parse":
        background_tasks.add_task(
            _process_uploaded_document, job.document_id, learning_user_id(current_user), job.id
        )
        return processing_job_payload(job, document)
    if job.job_type == "ocr":
        if document is None:
            raise HTTPException(status_code=400, detail="OCR 任务缺少关联资料，无法重试")
        legacy_job = _create_retry_ocr_job(db, job, document)
        db.commit()
        db.refresh(job)
        db.refresh(legacy_job)
        background_tasks.add_task(_run_ocr_job, legacy_job.id, job.id)
        payload = processing_job_payload(job, document)
        payload["ocr_job"] = _ocr_job_payload(legacy_job, document)
        return payload
    if job.job_type == "reindex":
        return _retry_reindex_job(db, job, document)
    if job.job_type == "knowledge_sync":
        return _retry_knowledge_sync_job(db, job, current_user, document)

    fail_processing_job(db, job, stage="failed", message=f"暂不支持重试任务类型：{job.job_type}")
    db.commit()
    raise HTTPException(status_code=400, detail=f"暂不支持重试任务类型：{job.job_type}")


@jobs_router.post("/{job_id}/cancel")
def cancel_processing_job_endpoint(
    course_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if _get_owned_course(db, course_id, current_user.id) is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    job = db.get(ProcessingJob, job_id)
    if job is None or job.course_id != course_id:
        raise HTTPException(status_code=404, detail="任务不存在")
    document = db.get(Document, job.document_id) if job.document_id else None
    message = CANCEL_MARKED_MESSAGE

    if job.job_type == "ocr":
        metadata = job_metadata(job)
        ocr_job_id = metadata.get("ocr_job_id")
        legacy_job = db.get(OcrJob, int(ocr_job_id)) if ocr_job_id else None
        if legacy_job and legacy_job.status not in {"completed", "failed", "cancelled"}:
            legacy_message = f"OCR 已标记取消；后台会在下一次检查后停止，已保留 {legacy_job.processed_pages} 页识别结果。"
            cancelled = _conditional_ocr_job_update(
                db,
                legacy_job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "cancelled",
                    OcrJob.finished_at: utc_now(),
                    OcrJob.error_message: legacy_message,
                    OcrJob.updated_at: utc_now(),
                },
            )
            message = legacy_message if cancelled else message
            if cancelled and document:
                document.status = "indexed" if document.chunk_count else "needs_ocr"
                document.processing_stage = document.status
                document.processing_progress = 100
                document.error_message = message

    cancel_processing_job(db, job, message=message)
    if job.status == "cancelled" and document and job.job_type != "ocr":
        document.status = "indexed" if document.chunk_count else "cancelled"
        document.processing_stage = "cancelled"
        document.processing_progress = 100
        document.error_message = message
    db.commit()
    db.refresh(job)
    return processing_job_payload(job, document)


def _create_retry_ocr_job(db: Session, processing_job: ProcessingJob, document: Document) -> OcrJob:
    metadata = job_metadata(processing_job)
    start_page = int(metadata.get("start_page") or 1)
    max_pages = int(metadata.get("max_pages") or settings.ocr_default_max_pages)
    mode = str(metadata.get("mode") or "fast")
    mode = mode if mode in OCR_MODE_LABELS else "fast"
    legacy_job = OcrJob(
        course_id=document.course_id,
        document_id=document.id,
        status="queued",
        start_page=start_page,
        max_pages=max_pages,
        total_pages=document.page_count,
        error_message=f"[mode:{mode}] OCR 重试任务已加入后台队列。",
    )
    db.add(legacy_job)
    db.flush()
    document.status = "ocr_queued"
    document.processing_stage = "ocr_queued"
    document.processing_progress = 0
    document.error_message = "OCR 重试任务已加入后台队列。"
    set_job_metadata(
        db,
        processing_job,
        {
            **metadata,
            "ocr_job_id": legacy_job.id,
            "start_page": start_page,
            "max_pages": max_pages,
            "mode": mode,
        },
    )
    return legacy_job


def _retry_reindex_job(db: Session, job: ProcessingJob, document: Document | None) -> dict:
    try:
        start_processing_job(db, job, stage="reindexing", progress=10, message="正在重新索引。")
        if document:
            result = reindex_document(db, document)
        else:
            result = reindex_course(db, job.course_id)
        complete_processing_job(db, job, stage="completed", message="重新索引完成。")
        db.commit()
        db.refresh(job)
        result["job"] = processing_job_payload(job, document)
        return result
    except Exception as exc:  # noqa: BLE001
        message = _friendly_error(exc)
        fail_processing_job(db, job, stage="failed", message=message)
        db.commit()
        raise HTTPException(status_code=500, detail=message) from exc


def _retry_knowledge_sync_job(
    db: Session,
    job: ProcessingJob,
    current_user: User,
    document: Document | None,
) -> dict:
    try:
        start_processing_job(
            db, job, stage="syncing_knowledge_points", progress=10, message="正在同步知识点。"
        )
        sync_course_knowledge_points(
            db, job.course_id, job.document_id, learning_user_id(current_user)
        )
        complete_processing_job(db, job, stage="completed", message="知识点同步完成。")
        db.commit()
        db.refresh(job)
        return processing_job_payload(job, document)
    except Exception as exc:  # noqa: BLE001
        message = _friendly_error(exc)
        fail_processing_job(db, job, stage="failed", message=message)
        db.commit()
        raise HTTPException(status_code=500, detail=message) from exc


def _run_ocr_job(job_id: int, processing_job_id: int | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(OcrJob, job_id)
        if job is None:
            return
        processing_job = (
            db.get(ProcessingJob, processing_job_id)
            if processing_job_id
            else _find_processing_job_for_ocr(db, job_id)
        )
        document = db.get(Document, job.document_id)
        if document is None:
            job.status = "failed"
            job.error_message = "资料不存在，OCR 任务无法继续。"
            job.finished_at = utc_now()
            fail_processing_job(db, processing_job, stage="failed", message=job.error_message)
            db.commit()
            return

        if not _conditional_ocr_job_update(
            db,
            job,
            allowed_statuses={"queued", "running"},
            values={
                OcrJob.status: "running",
                OcrJob.current_page: job.start_page,
                OcrJob.total_pages: document.page_count,
                OcrJob.updated_at: utc_now(),
            },
        ):
            db.rollback()
            return
        mode = _ocr_mode_from_message(job.error_message)
        mode_label = OCR_MODE_LABELS.get(mode, "快速索引")
        if processing_job is not None and not start_processing_job(
            db,
            processing_job,
            stage="ocr_processing",
            progress=5,
            message=f"正在后台{mode_label}",
        ):
            _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "cancelled",
                    OcrJob.finished_at: utc_now(),
                    OcrJob.error_message: CANCEL_MARKED_MESSAGE,
                    OcrJob.updated_at: utc_now(),
                },
            )
            db.commit()
            return
        document.status = "ocr_processing"
        document.processing_stage = "ocr_processing"
        document.processing_progress = 5
        document.error_message = (
            f"正在后台{mode_label}：从第 {job.start_page} 页开始，最多处理 {job.max_pages} 页。"
        )
        job.error_message = f"[mode:{mode}] {document.error_message}"
        update_processing_job(
            db,
            processing_job,
            stage="ocr_processing",
            progress=5,
            message=document.error_message,
        )
        db.commit()

        def should_stop() -> bool:
            db.refresh(job)
            if processing_job is not None:
                db.refresh(processing_job)
            return job.status == "cancelled" or (
                processing_job is not None and processing_job.status == "cancelled"
            )

        def mark_page_start(page_number: int) -> None:
            message = (
                f"[mode:{mode}] 正在{mode_label}第 {page_number} 页，"
                f"已完成 {job.processed_pages}/{job.max_pages} 页。"
            )
            if not _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "running",
                    OcrJob.current_page: page_number,
                    OcrJob.error_message: message,
                    OcrJob.updated_at: utc_now(),
                },
            ):
                db.rollback()
                raise _ProcessingCancelled
            document.status = "ocr_processing"
            document.processing_stage = "ocr_processing"
            document.processing_progress = min(
                95, round((job.processed_pages / max(1, job.max_pages)) * 100)
            )
            document.error_message = job.error_message.replace(f"[mode:{mode}] ", "", 1)
            update_processing_job(
                db,
                processing_job,
                stage="ocr_processing",
                progress=document.processing_progress,
                message=document.error_message,
            )
            db.commit()

        def mark_page_done(page_number: int, text: str) -> None:
            page_chunks = split_pages_into_chunks([(page_number, text)])
            next_processed_pages = job.processed_pages + 1
            next_progress = min(95, round((next_processed_pages / max(1, job.max_pages)) * 100))
            next_message = (
                f"[mode:{mode}] 已处理到第 {page_number} 页，"
                f"共完成 {next_processed_pages}/{job.max_pages} 页。"
            )
            if not _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "running",
                    OcrJob.current_page: page_number,
                    OcrJob.processed_pages: OcrJob.processed_pages + 1,
                    OcrJob.chunk_count: OcrJob.chunk_count + len(page_chunks),
                    OcrJob.error_message: next_message,
                    OcrJob.updated_at: utc_now(),
                },
            ):
                db.rollback()
                raise _ProcessingCancelled
            _claim_processing_job(
                db,
                processing_job,
                "ocr_processing",
                next_progress,
                "正在写入 OCR 结果",
            )
            index_document_chunks(
                db,
                document,
                page_chunks,
                replace_document=False,
                replace_page_numbers=[page_number],
            )
            document.status = "ocr_processing"
            document.processing_stage = "ocr_processing"
            document.processing_progress = min(
                95, round((job.processed_pages / max(1, job.max_pages)) * 100)
            )
            document.error_message = job.error_message.replace(f"[mode:{mode}] ", "", 1)
            update_processing_job(
                db,
                processing_job,
                stage="ocr_processing",
                progress=document.processing_progress,
                message=document.error_message,
            )
            db.commit()

        try:
            result = ocr_pdf_with_qwen_vl(
                Path(document.file_path),
                start_page=job.start_page,
                max_pages=job.max_pages,
                mode=mode,
                on_page_done=mark_page_done,
                on_page_start=mark_page_start,
                should_stop=should_stop,
            )
            db.refresh(job)
            if job.status == "cancelled":
                document.status = "indexed" if document.chunk_count else "needs_ocr"
                document.processing_stage = document.status
                document.processing_progress = 100
                document.error_message = f"OCR 已标记取消；后台会在下一次检查后停止，已保留 {job.processed_pages} 页识别结果。"
                job.error_message = document.error_message
                cancel_processing_job(
                    db, processing_job, message=document.error_message
                ) if processing_job else None
                db.commit()
                return
            chunks = split_pages_into_chunks(result.pages)
            if not _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={OcrJob.status: "running", OcrJob.updated_at: utc_now()},
            ):
                db.rollback()
                return
            _claim_processing_job(
                db,
                processing_job,
                "ocr_processing",
                96,
                "正在完成 OCR 索引",
            )
            document.page_count = result.total_pages
            index_document_chunks(
                db,
                document,
                chunks,
                replace_document=False,
                replace_page_numbers=[page_number for page_number, _text in result.pages],
            )
            course = db.get(Course, document.course_id)
            sync_course_knowledge_points(
                db,
                document.course_id,
                document.id,
                str(course.user_id) if course else None,
            )
            if document.chunk_count:
                document.status = "indexed"
                document.processing_stage = "indexed"
                document.processing_progress = 100
                document.indexed_at = utc_now()
                document.error_message = (
                    f"{mode_label}已处理第 {job.start_page} 页起的 {result.processed_pages} 页，"
                    f"新增 {len(chunks)} 个知识片段。"
                )
            else:
                document.status = "needs_ocr"
                document.processing_stage = "needs_ocr"
                document.processing_progress = 100
                document.error_message = (
                    "OCR 没有识别到有效文字。请减少页数或检查模型是否支持图片输入。"
                )
            if not _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "completed",
                    OcrJob.total_pages: result.total_pages,
                    OcrJob.processed_pages: result.processed_pages,
                    OcrJob.chunk_count: len(chunks),
                    OcrJob.finished_at: utc_now(),
                    OcrJob.error_message: document.error_message,
                    OcrJob.updated_at: utc_now(),
                },
            ):
                db.rollback()
                return
            if processing_job is not None and not complete_processing_job(
                db,
                processing_job,
                stage=document.status,
                message=document.error_message,
            ):
                db.rollback()
                return
            db.commit()
        except _ProcessingCancelled:
            db.rollback()
            return
        except Exception as exc:  # noqa: BLE001 - surface OCR failure to the UI.
            if not _conditional_ocr_job_update(
                db,
                job,
                allowed_statuses={"queued", "running"},
                values={
                    OcrJob.status: "failed",
                    OcrJob.error_message: str(exc),
                    OcrJob.finished_at: utc_now(),
                    OcrJob.updated_at: utc_now(),
                },
            ):
                db.rollback()
                return
            document.status = "indexed" if document.chunk_count else "needs_ocr"
            document.processing_stage = document.status
            document.processing_progress = 100
            document.error_message = str(exc)
            if processing_job is not None and not fail_processing_job(
                db,
                processing_job,
                stage="failed",
                message=_friendly_error(exc),
            ):
                db.rollback()
                return
            db.commit()


def _process_uploaded_document(
    document_id: int, user_id: str | None, processing_job_id: int | None = None
) -> None:
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        if document is None:
            return
        processing_job = db.get(ProcessingJob, processing_job_id) if processing_job_id else None
        course = db.get(Course, document.course_id)
        if course is None:
            document.status = "failed"
            document.processing_stage = "failed"
            document.processing_progress = 100
            document.error_message = "课程不存在，资料无法入库。"
            fail_processing_job(db, processing_job, stage="failed", message=document.error_message)
            db.commit()
            return

        suffix = f".{document.file_type.lower()}"
        try:
            if suffix in IMAGE_SUFFIXES:
                _set_processing(db, document, "parsing", 20, "正在识别图片课件内容", processing_job)
                _claim_processing_job(db, processing_job, "parsing", 20, "正在识别图片课件内容")
                _index_image_document(db, course, document, user_id)
                _finish_document_processing(document)
                if not complete_processing_job(
                    db,
                    processing_job,
                    stage=document.status,
                    message=document.error_message,
                ):
                    db.rollback()
                    return
                db.commit()
                return

            _set_processing(db, document, "parsing", 20, "正在解析文本", processing_job)
            pages = parse_document(Path(document.file_path))
            document.page_count = len(pages)

            _set_processing(db, document, "chunking", 45, "正在切分知识片段", processing_job)
            chunks = split_pages_into_chunks(pages)
            if not chunks:
                _finalize_parse_status(document, suffix, has_chunks=False, has_pages=bool(pages))
                _finish_document_processing(document)
                if not complete_processing_job(
                    db,
                    processing_job,
                    stage=document.status,
                    message=document.error_message,
                ):
                    db.rollback()
                    return
                db.commit()
                return

            _set_processing(db, document, "indexing", 70, "正在写入向量库", processing_job)
            _claim_processing_job(db, processing_job, "indexing", 70, "正在写入向量库")
            index_document_chunks(db, document, chunks)
            db.commit()

            _set_processing(
                db, document, "syncing_knowledge_points", 90, "正在同步知识点", processing_job
            )
            _claim_processing_job(
                db,
                processing_job,
                "syncing_knowledge_points",
                90,
                "正在同步知识点",
            )
            _run_knowledge_sync_job(db, document.course_id, document.id, user_id)
            _finalize_parse_status(document, suffix, has_chunks=True, has_pages=bool(pages))
            _finish_document_processing(document)
            if not complete_processing_job(
                db,
                processing_job,
                stage=document.status,
                message=document.error_message,
            ):
                db.rollback()
                return
            db.commit()
        except _ProcessingCancelled:
            db.rollback()
            return
        except Exception as exc:  # noqa: BLE001 - background task should persist a user-readable error.
            document.status = "needs_vision" if suffix in IMAGE_SUFFIXES else "failed"
            document.processing_stage = document.status
            document.processing_progress = 100
            document.error_message = _friendly_error(exc)
            if processing_job is not None and not fail_processing_job(
                db,
                processing_job,
                stage="failed",
                message=document.error_message,
            ):
                db.rollback()
                return
            db.commit()


def _set_processing(
    db: Session,
    document: Document,
    stage: str,
    progress: int,
    message: str,
    processing_job: ProcessingJob | None = None,
) -> None:
    if processing_job is not None and not update_processing_job(
        db,
        processing_job,
        stage=stage,
        progress=progress,
        message=message,
    ):
        db.rollback()
        raise _ProcessingCancelled
    document.status = stage
    document.processing_stage = stage
    document.processing_progress = progress
    document.error_message = message
    db.commit()
    db.refresh(document)


def _claim_processing_job(
    db: Session,
    processing_job: ProcessingJob | None,
    stage: str,
    progress: int,
    message: str,
) -> None:
    """Acquire the persisted job transition before writing stage results."""
    if processing_job is not None and not update_processing_job(
        db,
        processing_job,
        stage=stage,
        progress=progress,
        message=message,
    ):
        db.rollback()
        raise _ProcessingCancelled


def _conditional_ocr_job_update(
    db: Session,
    job: OcrJob,
    *,
    allowed_statuses: set[str],
    values: dict,
) -> bool:
    """Apply OCR state changes with a database-side cancellation guard."""
    with db.no_autoflush:
        updated = (
            db.query(OcrJob)
            .filter(OcrJob.id == job.id, OcrJob.status.in_(allowed_statuses))
            .update(values, synchronize_session=False)
        )
    if not updated:
        return False
    db.flush()
    db.refresh(job)
    return True


def _finish_document_processing(document: Document) -> None:
    document.processing_stage = document.status
    document.processing_progress = 100
    if document.status == "indexed":
        document.indexed_at = utc_now()


def _friendly_error(exc: Exception) -> str:
    text = str(exc).strip()
    if not text:
        return "资料解析失败，请检查文件是否损坏或格式是否受支持。"
    return text[:500]


def _finalize_parse_status(
    document: Document, suffix: str, has_chunks: bool, has_pages: bool
) -> None:
    if has_chunks:
        document.status = "indexed"
        document.error_message = ""
    elif suffix == ".pdf" and has_pages:
        document.status = "needs_ocr"
        document.error_message = (
            "这份 PDF 有页数但没有可提取的文字层，通常是扫描版或图片版。"
            "请点击 OCR 入库，或先用其他 OCR 工具生成带文本层的 PDF 后重新上传。"
        )
    else:
        document.status = "empty"
        document.error_message = "未从文件中解析到可检索文本。"


def _index_image_document(
    db: Session, course: Course, document: Document, user_id: str | None
) -> None:
    document.status = "vision_processing"
    document.processing_stage = "vision_processing"
    document.processing_progress = 35
    text = describe_courseware_image(Path(document.file_path), course.name)
    pages = [(1, text)]
    chunks = split_pages_into_chunks(pages)
    document.page_count = 1
    index_document_chunks(db, document, chunks)
    if chunks:
        document.status = "indexed"
        document.processing_stage = "indexed"
        document.processing_progress = 100
        document.indexed_at = utc_now()
        document.error_message = "图片课件已完成多模态识别并加入知识库。"
    else:
        document.status = "empty"
        document.processing_stage = "empty"
        document.processing_progress = 100
        document.error_message = "图片课件识别完成，但没有生成可检索文本。"
    _run_knowledge_sync_job(db, course.id, document.id, user_id)


def _run_knowledge_sync_job(
    db: Session,
    course_id: int,
    document_id: int | None,
    user_id: str | None,
) -> ProcessingJob:
    job = create_processing_job(
        db,
        course_id=course_id,
        document_id=document_id,
        job_type="knowledge_sync",
        error_message="知识点同步任务已创建。",
    )
    start_processing_job(
        db, job, stage="syncing_knowledge_points", progress=10, message="正在同步知识点。"
    )
    try:
        sync_course_knowledge_points(db, course_id, document_id, user_id)
        complete_processing_job(db, job, stage="completed", message="知识点同步完成。")
        db.flush()
        return job
    except Exception as exc:  # noqa: BLE001 - keep sync failures retryable.
        fail_processing_job(db, job, stage="failed", message=_friendly_error(exc))
        db.flush()
        raise


def _get_owned_course(db: Session, course_id: int, user_id: int) -> Course | None:
    return db.query(Course).filter(Course.id == course_id, Course.user_id == user_id).first()


def _has_active_processing_job(db: Session, job: ProcessingJob, document: Document | None) -> bool:
    query = db.query(ProcessingJob).filter(
        ProcessingJob.course_id == job.course_id,
        ProcessingJob.job_type == job.job_type,
        ProcessingJob.status.in_(("queued", "running")),
        ProcessingJob.id != job.id,
    )
    if document is not None:
        query = query.filter(ProcessingJob.document_id == document.id)
    elif job.document_id is None:
        query = query.filter(ProcessingJob.document_id.is_(None))
    else:
        query = query.filter(ProcessingJob.document_id == job.document_id)
    return query.first() is not None


def _max_upload_bytes(suffix: str) -> int:
    if suffix == ".txt":
        return settings.txt_upload_max_bytes
    return settings.document_upload_max_bytes


def _save_upload_with_limit(file: UploadFile, target: Path, max_bytes: int) -> None:
    total = 0
    try:
        with target.open("wb") as out_file:
            while True:
                chunk = file.file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件过大。当前类型最大允许 {_format_bytes(max_bytes)}。",
                    )
                out_file.write(chunk)
            out_file.flush()
            os.fsync(out_file.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        return f"{value // (1024 * 1024)}MB"
    return f"{value // 1024}KB"


def _remove_empty_parent(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        return


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


def _ocr_mode_from_message(message: str) -> str:
    if "[mode:full]" in (message or ""):
        return "full"
    return "fast"


def _ocr_job_payload(job: OcrJob, document: Document) -> dict:
    return {
        "id": job.id,
        "course_id": job.course_id,
        "document_id": job.document_id,
        "status": job.status,
        "start_page": job.start_page,
        "max_pages": job.max_pages,
        "total_pages": job.total_pages,
        "current_page": job.current_page,
        "processed_pages": job.processed_pages,
        "chunk_count": job.chunk_count,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "finished_at": job.finished_at,
        "document": _document_payload(document),
    }


def _find_processing_job_for_ocr(db: Session, ocr_job_id: int) -> ProcessingJob | None:
    candidates = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.job_type == "ocr")
        .order_by(ProcessingJob.created_at.desc())
        .all()
    )
    for candidate in candidates:
        if job_metadata(candidate).get("ocr_job_id") == ocr_job_id:
            return candidate
    return None
