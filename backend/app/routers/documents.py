from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.models.entities import Course, Document, OcrJob
from app.schemas import OcrRequest
from app.services.chunker import split_pages_into_chunks
from app.services.document_parser import parse_document
from app.services.ocr_service import ocr_pdf_with_qwen_vl
from app.services.vector_store import index_document_chunks


router = APIRouter(prefix="/courses/{course_id}/documents", tags=["documents"])


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

    course_dir = settings.upload_dir / str(course_id)
    course_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{_safe_filename(file.filename)}"
    target = course_dir / stored_filename
    with target.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)

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
    document.error_message = (
        f"OCR 任务已加入后台队列：从第 {payload.start_page} 页开始，最多识别 {payload.max_pages} 页。"
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
        document.status = "ocr_processing"
        document.error_message = (
            f"正在后台 OCR：从第 {job.start_page} 页开始，最多识别 {job.max_pages} 页。"
        )
        db.commit()

        def mark_page_done(page_number: int, text: str) -> None:
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
            job.error_message = f"已识别到第 {page_number} 页，共完成 {job.processed_pages} 页。"
            document.status = "ocr_processing"
            document.error_message = job.error_message
            db.commit()

        try:
            result = ocr_pdf_with_qwen_vl(
                Path(document.file_path),
                start_page=job.start_page,
                max_pages=job.max_pages,
                on_page_done=mark_page_done,
            )
            chunks = split_pages_into_chunks(result.pages)
            document.page_count = result.total_pages
            index_document_chunks(
                db,
                document,
                chunks,
                replace_document=False,
                replace_page_numbers=[page_number for page_number, _text in result.pages],
            )
            job.status = "completed"
            job.total_pages = result.total_pages
            job.processed_pages = result.processed_pages
            job.chunk_count = len(chunks)
            job.finished_at = datetime.utcnow()
            if document.chunk_count:
                document.status = "indexed"
                document.error_message = (
                    f"OCR 已识别第 {job.start_page} 页起的 {result.processed_pages} 页，"
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
