from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import ChatMessage, Course, Document, DocumentChunk, GeneratedMaterial, KnowledgePoint
from app.services.learning_service import DIFFICULTY_LABELS, sync_course_knowledge_points
from app.services.llm_service import call_llm, offline_answer, offline_outline, offline_practice
from app.services.vector_store import (
    SearchResult,
    get_representative_chunks,
    retrieval_provider_from_results,
    search_course,
)


OFFLINE_PROVIDER = "mock/offline"
LOW_CONFIDENCE_MESSAGE = "资料中没有找到足够依据回答这个问题，请补充资料或换一个更贴近资料的问题。"


def answer_question(db: Session, course_id: int, question: str, top_k: int = 5) -> dict:
    # 问答流程：检索课程片段 -> 判断证据强度 -> 组装受限上下文 -> 调用模型。
    # 严格来源模式下，证据不足时直接拒答，避免生成“像真的”但无依据的答案。
    effective_top_k = max(1, min(int(top_k or settings.rag_top_k), max(1, settings.rag_top_k)))
    sources = search_course(db, course_id, question, effective_top_k)
    retrieval_provider = retrieval_provider_from_results(sources)
    top_score = sources[0].score if sources else 0.0
    answer_status = "answered"
    context = _build_context(sources)
    if not sources:
        answer_status = _knowledge_base_status(db, course_id)
        answer = _empty_knowledge_base_message(db, course_id) if answer_status != "low_confidence" else LOW_CONFIDENCE_MESSAGE
        llm_provider = "system"
    elif settings.rag_enable_strict_source_mode and top_score < settings.rag_min_score:
        answer_status = "low_confidence"
        answer = LOW_CONFIDENCE_MESSAGE
        llm_provider = "system"
    else:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 StudyMate 课程资料问答助手。只能基于用户上传资料片段回答，"
                    "不能引入片段之外的知识、猜测或常识补全。资料不足时必须明确说明不足。"
                    "回答要结构清晰，并提醒用户查看下方来源片段复核。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{question}\n\n课程资料片段：\n{context}",
            },
        ]
        llm_response = call_llm(messages)
        answer = llm_response.content if llm_response else offline_answer(question, context)
        llm_provider = llm_response.used_provider if llm_response else OFFLINE_PROVIDER
    confidence = _confidence_from_score(top_score, answer_status)
    source_payload = _sources_payload(sources)
    source_count = len(source_payload)
    sources_record = _chat_sources_record(
        source_payload,
        answer_status=answer_status,
        confidence=confidence,
        source_count=source_count,
        retrieval_provider=retrieval_provider,
        llm_provider=llm_provider,
    )

    db.add(
        ChatMessage(
            course_id=course_id,
            question=question,
            answer=answer,
            sources_json=json.dumps(sources_record, ensure_ascii=False),
        )
    )
    course = db.get(Course, course_id)
    if course:
        course.last_asked_at = datetime.utcnow()
    db.commit()
    return {
        "answer": answer,
        "answer_status": answer_status,
        "confidence": confidence,
        "source_count": source_count,
        "sources": source_payload,
        "provider": llm_provider,
        "llm_provider": llm_provider,
        "retrieval_provider": retrieval_provider,
    }


def generate_outline(db: Session, course_id: int) -> dict:
    sources = search_course(db, course_id, "核心概念 重点公式 易错点 可能考法", 8)
    if not sources:
        sources = get_representative_chunks(db, course_id, 8)
    context = _build_context(sources)
    messages = [
        {
            "role": "system",
            "content": (
                "你是课程复习教练。请只根据资料生成复习提纲，包含：核心概念、重点公式、"
                "易错点、可能考法。输出中文 Markdown。"
            ),
        },
        {"role": "user", "content": f"课程资料片段：\n{context}"},
    ]
    llm_response = call_llm(messages)
    content = llm_response.content if llm_response else offline_outline(context)
    return _save_material(db, course_id, "outline", content, sources, llm_response.used_provider if llm_response else OFFLINE_PROVIDER)


def generate_practice(
    db: Session,
    course_id: int,
    count: int,
    difficulty: str = "basic",
    knowledge_point_id: int | None = None,
    user_id: str | None = None,
) -> dict:
    sync_course_knowledge_points(db, course_id, user_id=user_id)
    focus_point = _get_focus_point(db, course_id, knowledge_point_id)
    focus_name = focus_point.name if focus_point else ""
    difficulty_label = DIFFICULTY_LABELS.get(difficulty, "基础题")
    query = f"{focus_name} {difficulty_label} 选择题 填空题 简答题 重点 练习 易错点"
    sources = search_course(db, course_id, query, 10)
    if not sources:
        sources = get_representative_chunks(db, course_id, 10)
    context = _build_context(sources)
    focus_instruction = f"重点围绕知识点“{focus_name}”。" if focus_name else "覆盖课程资料中的核心知识点。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是课程自适应练习题生成助手。请只根据资料生成题目，题型覆盖选择题、填空题、"
                "简答题，并给出答案、解析、关联知识点和常见错因。输出中文 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请生成 {count} 道{difficulty_label}。{focus_instruction}\n"
                "如果是易错题，请突出误区辨析和变式训练；如果是考试题，请提高综合性。\n\n"
                f"课程资料片段：\n{context}"
            ),
        },
    ]
    llm_response = call_llm(messages)
    content = (
        llm_response.content
        if llm_response
        else offline_practice(context, count, difficulty_label=difficulty_label, focus_name=focus_name)
    )
    return _save_material(
        db,
        course_id,
        f"practice:{difficulty}",
        content,
        sources,
        llm_response.used_provider if llm_response else OFFLINE_PROVIDER,
    )


def _save_material(
    db: Session, course_id: int, kind: str, content: str, sources: list[SearchResult], provider: str
) -> dict:
    source_payload = _sources_payload(sources)
    db.add(
        GeneratedMaterial(
            course_id=course_id,
            kind=kind,
            content=content,
            sources_json=json.dumps(source_payload, ensure_ascii=False),
        )
    )
    db.commit()
    return {"content": content, "sources": source_payload, "provider": provider}


def _build_context(sources: list[SearchResult]) -> str:
    parts: list[str] = []
    max_chars = max(500, settings.rag_context_max_chars)
    used_chars = 0
    for index, source in enumerate(sources, start=1):
        header = (
            f"[{index}] 文件：{source.document_name}，页码：P{source.page_number}，"
            f"chunk_index：{source.chunk_index}，score：{source.score:.4f}\n"
        )
        remaining = max_chars - used_chars - len(header)
        if remaining <= 0:
            break
        content = source.content.strip()
        if len(content) > remaining:
            content = f"{content[: max(0, remaining - 12)].rstrip()}\n[片段已截断]"
        block = f"{header}{content}"
        parts.append(block)
        used_chars += len(block) + 2
    return "\n\n".join(parts)


def _sources_payload(sources: list[SearchResult]) -> list[dict]:
    payload: list[dict] = []
    seen: set[tuple[int, int, int]] = set()
    for source in sources:
        key = (source.document_id, source.page_number, source.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        preview = source.content.replace("\n", " ")
        payload.append(
            {
                "document_id": source.document_id,
                "document_name": source.document_name,
                "page": source.page_number,
                "chunk_index": source.chunk_index,
                "score": round(source.score, 4),
                "preview": preview[:180],
            }
        )
    return payload


def _chat_sources_record(
    sources: list[dict],
    answer_status: str,
    confidence: str,
    source_count: int,
    retrieval_provider: str,
    llm_provider: str,
) -> dict:
    return {
        "sources": sources,
        "answer_status": answer_status,
        "confidence": confidence,
        "source_count": source_count,
        "retrieval_provider": retrieval_provider,
        "llm_provider": llm_provider,
    }


def _confidence_from_score(score: float, answer_status: str) -> str:
    if answer_status != "answered":
        return "low"
    if score >= 0.55:
        return "high"
    if score >= settings.rag_min_score:
        return "medium"
    return "low"


def _knowledge_base_status(db: Session, course_id: int) -> str:
    chunk_count = db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.course_id == course_id).scalar() or 0
    if chunk_count:
        return "low_confidence"

    documents = db.query(Document).filter(Document.course_id == course_id).all()
    if not documents:
        return "empty_knowledge_base"
    if any(document.status == "needs_ocr" for document in documents):
        return "needs_ocr"
    processing_statuses = {"uploaded", "queued", "parsing", "chunking", "indexing", "syncing_knowledge_points"}
    if any(document.status in processing_statuses for document in documents):
        return "processing"
    return "empty_knowledge_base"


def _empty_knowledge_base_message(db: Session, course_id: int) -> str:
    documents = db.query(Document).filter(Document.course_id == course_id).all()
    if not documents:
        return "当前课程还没有上传资料。请先上传 PDF、PPT、Word 或 TXT 资料。"
    if any(document.status == "needs_ocr" for document in documents):
        return (
            "已上传资料，但部分 PDF 可能是扫描版或图片版，暂时没有可检索文本。"
            "请在资料卡片中启动 OCR，或上传带文本层的 PDF 后再提问。"
        )
    processing_statuses = {"uploaded", "queued", "parsing", "chunking", "indexing", "syncing_knowledge_points"}
    if any(document.status in processing_statuses for document in documents):
        return "资料正在后台解析入库，请稍后刷新状态，等资料显示为已入库后再提问。"
    if any(document.status == "failed" for document in documents):
        return "资料解析失败，请查看资料卡片上的错误提示，处理后重新上传。"
    return LOW_CONFIDENCE_MESSAGE


def _get_focus_point(db: Session, course_id: int, knowledge_point_id: int | None) -> KnowledgePoint | None:
    if knowledge_point_id is None:
        return None
    point = db.get(KnowledgePoint, knowledge_point_id)
    if point is None or point.course_id != course_id:
        return None
    return point
