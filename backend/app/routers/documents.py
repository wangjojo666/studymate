from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.entities import ChunkKnowledgePoint, Course, Document, DocumentChunk, KnowledgePoint, OcrJob
from app.schemas import OcrRequest
from app.services.chunker import split_pages_into_chunks
from app.services.document_parser import parse_document
from app.services.learning_service import sync_course_knowledge_points
from app.services.ocr_service import ocr_pdf_with_qwen_vl
from app.services.vector_store import index_document_chunks


router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])

OCR_MODE_LABELS = {
    "fast": "快速索引",
    "full": "精确 OCR",
}

UPLOAD_CHUNK_SIZE = 1024 * 1024


@router.post("")
def upload_document(
    course_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".pdf", ".pptx", ".docx", ".txt"}:
        raise HTTPException(status_code=400, detail="仅支持 PDF、PPTX、DOCX、TXT")
    max_bytes = _max_upload_bytes(suffix)

    course_dir = settings.upload_dir / str(course_id)
    course_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{_safe_filename(file.filename)}"
    target = course_dir / stored_filename
    _save_upload_with_limit(file, target, max_bytes)

    document = Document(
        course_id=course_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_type=suffix.replace(".", ""),
        file_path=str(target),
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        pages = parse_document(target)
        chunks = split_pages_into_chunks(pages)
        document.page_count = len(pages)
        index_document_chunks(db, document, chunks)
        _finalize_parse_status(document, suffix, bool(chunks), bool(pages))
        sync_course_knowledge_points(db, course_id, document.id)
        db.commit()
        db.refresh(document)
    except Exception as exc:  # noqa: BLE001 - return parser errors to the UI.
        document.status = "failed"
        document.error_message = str(exc)
        db.commit()
        db.refresh(document)

    return _document_payload(document)


@router.get("")
def list_documents(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    documents = (
        db.query(Document)
        .filter(Document.course_id == course_id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [_document_payload(document) for document in documents]


@router.delete("/{document_id}")
def delete_document(course_id: int, document_id: int, db: Session = Depends(get_db)) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")

    file_path = Path(document.file_path)
    chunk_ids = [
        row[0]
        for row in db.query(DocumentChunk.id).filter(DocumentChunk.document_id == document_id).all()
    ]
    if chunk_ids:
        db.query(ChunkKnowledgePoint).filter(ChunkKnowledgePoint.chunk_id.in_(chunk_ids)).delete(
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

    if file_path.exists():
        try:
            file_path.unlink()
        except OSError:
            return {"ok": True, "warning": "资料记录已删除，但本地文件删除失败，请手动检查 storage/uploads。"}
    _remove_empty_parent(file_path.parent)
    return {"ok": True}


@router.post("/{document_id}/ocr")
def ocr_document(
    course_id: int,
    document_id: int,
    payload: OcrRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    course = db.get(Course, course_id)
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
    db.add(job)
    document.status = "ocr_queued"
    mode_label = OCR_MODE_LABELS.get(payload.mode, "快速索引")
    job.error_message = (
        f"[mode:{payload.mode}] {mode_label}任务已加入后台队列：从第 {payload.start_page} 页开始，"
        f"最多处理 {payload.max_pages} 页。"
    )
    document.error_message = (
        f"{mode_label}任务已加入后台队列：从第 {payload.start_page} 页开始，最多处理 {payload.max_pages} 页。"
    )
    db.commit()
    db.refresh(job)
    db.refresh(document)

    background_tasks.add_task(_run_ocr_job, job.id)
    return _ocr_job_payload(job, document)


@router.get("/{document_id}/ocr-jobs/{job_id}")
def get_ocr_job(course_id: int, document_id: int, job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(OcrJob, job_id)
    if job is None or job.course_id != course_id or job.document_id != document_id:
        raise HTTPException(status_code=404, detail="OCR 任务不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    return _ocr_job_payload(job, document)


@router.post("/{document_id}/ocr-jobs/{job_id}/cancel")
def cancel_ocr_job(course_id: int, document_id: int, job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(OcrJob, job_id)
    if job is None or job.course_id != course_id or job.document_id != document_id:
        raise HTTPException(status_code=404, detail="OCR 任务不存在")
    document = db.get(Document, document_id)
    if document is None or document.course_id != course_id:
        raise HTTPException(status_code=404, detail="资料不存在")
    if job.status in {"completed", "failed", "cancelled"}:
        return _ocr_job_payload(job, document)

    job.status = "cancelled"
    job.finished_at = datetime.utcnow()
    job.error_message = f"OCR 已停止，已保留 {job.processed_pages} 页识别结果。"
    document.status = "indexed" if document.chunk_count else "needs_ocr"
    document.error_message = job.error_message
    db.commit()
    db.refresh(job)
    db.refresh(document)
    return _ocr_job_payload(job, document)


def _run_ocr_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(OcrJob, job_id)
        if job is None:
            return
        document = db.get(Document, job.document_id)
        if document is None:
            job.status = "failed"
            job.error_message = "资料不存在，OCR 任务无法继续。"
            job.finished_at = datetime.utcnow()
            db.commit()
            return

        job.status = "running"
        job.current_page = job.start_page
        job.total_pages = document.page_count
        mode = _ocr_mode_from_message(job.error_message)
        mode_label = OCR_MODE_LABELS.get(mode, "快速索引")
        document.status = "ocr_processing"
        document.error_message = (
            f"正在后台{mode_label}：从第 {job.start_page} 页开始，最多处理 {job.max_pages} 页。"
        )
        job.error_message = f"[mode:{mode}] {document.error_message}"
        db.commit()

        def should_stop() -> bool:
            db.refresh(job)
            return job.status == "cancelled"

        def mark_page_start(page_number: int) -> None:
            db.refresh(job)
            if job.status == "cancelled":
                return
            job.current_page = page_number
            job.error_message = (
                f"[mode:{mode}] 正在{mode_label}第 {page_number} 页，"
                f"已完成 {job.processed_pages}/{job.max_pages} 页。"
            )
            document.status = "ocr_processing"
            document.error_message = job.error_message.replace(f"[mode:{mode}] ", "", 1)
            db.commit()

        def mark_page_done(page_number: int, text: str) -> None:
            db.refresh(job)
            if job.status == "cancelled":
                return
            page_chunks = split_pages_into_chunks([(page_number, text)])
            index_document_chunks(
                db,
                document,
                page_chunks,
                replace_document=False,
                replace_page_numbers=[page_number],
            )
            job.current_page = page_number
            job.processed_pages += 1
            job.chunk_count += len(page_chunks)
            job.error_message = (
                f"[mode:{mode}] 已处理到第 {page_number} 页，"
                f"共完成 {job.processed_pages}/{job.max_pages} 页。"
            )
            document.status = "ocr_processing"
            document.error_message = job.error_message.replace(f"[mode:{mode}] ", "", 1)
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
                document.error_message = f"OCR 已停止，已保留 {job.processed_pages} 页识别结果。"
                job.error_message = document.error_message
                db.commit()
                return
            chunks = split_pages_into_chunks(result.pages)
            document.page_count = result.total_pages
            index_document_chunks(
                db,
                document,
                chunks,
                replace_document=False,
                replace_page_numbers=[page_number for page_number, _text in result.pages],
            )
            sync_course_knowledge_points(db, document.course_id, document.id)
            job.status = "completed"
            job.total_pages = result.total_pages
            job.processed_pages = result.processed_pages
            job.chunk_count = len(chunks)
            job.finished_at = datetime.utcnow()
            if document.chunk_count:
                document.status = "indexed"
                document.error_message = (
                    f"{mode_label}已处理第 {job.start_page} 页起的 {result.processed_pages} 页，"
                    f"新增 {len(chunks)} 个知识片段。"
                )
            else:
                document.status = "needs_ocr"
                document.error_message = "OCR 没有识别到有效文字。请减少页数或检查模型是否支持图片输入。"
            job.error_message = document.error_message
            db.commit()
        except Exception as exc:  # noqa: BLE001 - surface OCR failure to the UI.
            job.status = "failed"
            job.error_message = str(exc)
            job.finished_at = datetime.utcnow()
            document.status = "indexed" if document.chunk_count else "needs_ocr"
            document.error_message = str(exc)
            db.commit()


def _finalize_parse_status(document: Document, suffix: str, has_chunks: bool, has_pages: bool) -> None:
    if has_chunks:
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


def _safe_filename(filename: str) -> str:
    name = re.sub("[^\\w.\\-\u4e00-\u9fff]+", "_", filename, flags=re.UNICODE)
    return name[:160] or "upload"


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


def _document_payload(document: Document) -> dict:
    return {
        "id": document.id,
        "course_id": document.course_id,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "status": document.status,
        "page_count": document.page_count,
        "chunk_count": document.chunk_count,
        "error_message": document.error_message,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


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
