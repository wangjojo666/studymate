from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, Course, Document, GeneratedMaterial
from app.services.llm_service import call_llm, offline_answer, offline_outline, offline_practice
from app.services.vector_store import SearchResult, get_representative_chunks, search_course


def answer_question(db: Session, course_id: int, question: str, top_k: int = 5) -> dict:
    sources = search_course(db, course_id, question, top_k)
    context = _build_context(sources)
    if sources:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是 StudyMate 课程资料问答助手。只能基于用户上传的课程资料回答；"
                    "如果资料不足，要明确说明。回答要结构清晰，并在最后提示用户查看来源。"
                ),
            },
            {
                "role": "user",
                "content": f"问题：{question}\n\n课程资料片段：\n{context}",
            },
        ]
        llm_response = call_llm(messages)
        answer = llm_response.content if llm_response else offline_answer(question, context)
        provider = llm_response.used_provider if llm_response else "mock"
    else:
        answer = _empty_knowledge_base_message(db, course_id)
        provider = "system"
    source_payload = _sources_payload(sources)

    db.add(
        ChatMessage(
            course_id=course_id,
            question=question,
            answer=answer,
            sources_json=json.dumps(source_payload, ensure_ascii=False),
        )
    )
    course = db.get(Course, course_id)
    if course:
        course.last_asked_at = datetime.utcnow()
    db.commit()
    return {"answer": answer, "sources": source_payload, "provider": provider}


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
    return _save_material(db, course_id, "outline", content, sources, llm_response.used_provider if llm_response else "mock")


def generate_practice(db: Session, course_id: int, count: int) -> dict:
    sources = search_course(db, course_id, "选择题 填空题 简答题 重点 练习", 10)
    if not sources:
        sources = get_representative_chunks(db, course_id, 10)
    context = _build_context(sources)
    messages = [
        {
            "role": "system",
            "content": (
                "你是课程练习题生成助手。请只根据资料生成题目，题型覆盖选择题、填空题、"
                "简答题，并给出答案和简短解析。输出中文 Markdown。"
            ),
        },
        {"role": "user", "content": f"请生成 {count} 道练习题。\n\n课程资料片段：\n{context}"},
    ]
    llm_response = call_llm(messages)
    content = llm_response.content if llm_response else offline_practice(context, count)
    return _save_material(db, course_id, "practice", content, sources, llm_response.used_provider if llm_response else "mock")


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
    for index, source in enumerate(sources, start=1):
        parts.append(
            f"[{index}] 文件：{source.document_name}，页码：P{source.page_number}\n{source.content}"
        )
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


def _empty_knowledge_base_message(db: Session, course_id: int) -> str:
    documents = db.query(Document).filter(Document.course_id == course_id).all()
    if not documents:
        return "当前课程还没有上传资料。请先上传课程 PDF、PPT、Word 或 TXT。"
    if any(document.status == "needs_ocr" for document in documents):
        return (
            "你已经上传了资料，但这份 PDF 是扫描版/图片版，没有可提取的文字层，"
            "所以还没有进入可检索知识库。请先对 PDF 做 OCR，生成带文本层的 PDF 后重新上传，"
            "再进行问答、复习提纲和练习题生成。"
        )
    if any(document.status == "failed" for document in documents):
        return "资料上传后解析失败，请查看资料卡片上的错误提示，处理后重新上传。"
    return "当前课程资料还没有生成可检索片段。请确认文件中包含可复制的文本内容。"
