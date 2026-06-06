from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.entities import Course, Document
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

    document.status = "ocr_processing"
    document.error_message = "正在调用本地 qwen3-vl:30b 进行 OCR，请稍等。"
    db.commit()

    try:
        result = ocr_pdf_with_qwen_vl(
            Path(document.file_path),
            start_page=payload.start_page,
            max_pages=payload.max_pages,
        )
        chunks = split_pages_into_chunks(result.pages)
        document.page_count = result.total_pages
        index_document_chunks(db, document, chunks)
        if chunks:
            document.status = "indexed"
            document.error_message = (
                f"OCR 已识别第 {payload.start_page} 页起的 {result.processed_pages} 页，"
                f"生成 {len(chunks)} 个知识片段。"
            )
        else:
            document.status = "needs_ocr"
            document.error_message = "OCR 没有识别到有效文字。请减少页数或检查模型是否支持图片输入。"
        db.commit()
        db.refresh(document)
    except Exception as exc:  # noqa: BLE001 - surface OCR failure to the UI.
        document.status = "needs_ocr"
        document.error_message = str(exc)
        db.commit()
        db.refresh(document)

    return _document_payload(document)


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
