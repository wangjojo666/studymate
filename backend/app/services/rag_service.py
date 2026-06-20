from __future__ import annotations

import json
import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.entities import ChatMessage, Course, Document, DocumentChunk, GeneratedMaterial, KnowledgePoint
from app.services.learning_service import DIFFICULTY_LABELS, sync_course_knowledge_points
from app.services.llm_service import call_llm, offline_answer, offline_outline
from app.services.vector_store import (
    SearchResult,
    get_representative_chunks,
    retrieval_provider_from_results,
    search_course,
)
from app.utils.time import utc_now


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
        course.last_asked_at = utc_now()
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
    if not context.strip():
        content = "当前课程还没有可用于生成练习题的资料。请先上传资料并等待入库后再生成专项练习。"
        return _save_material(
            db,
            course_id,
            f"practice:{difficulty}",
            content,
            sources,
            "system",
            extra={"items": []},
        )
    focus_instruction = f"重点围绕知识点“{focus_name}”。" if focus_name else "覆盖课程资料中的核心知识点。"
    messages = [
        {
            "role": "system",
            "content": (
                "你是课程自适应练习题生成助手。请只根据资料生成题目，题型覆盖选择题、填空题、"
                "简答题，并给出答案、解析、关联知识点和来源。只输出严格 JSON 数组，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"请生成 {count} 道{difficulty_label}。{focus_instruction}\n"
                "如果是易错题，请突出误区辨析和变式训练；如果是考试题，请提高综合性。\n\n"
                "每项字段：question_type、question、options、reference_answer、explanation、knowledge_points、source_numbers。\n"
                "source_numbers 使用课程资料片段标题中的编号，例如 [1,2]。\n\n"
                f"课程资料片段：\n{context}"
            ),
        },
    ]
    llm_response = call_llm(messages)
    source_payload = _sources_payload(sources)
    items = (
        _parse_practice_items(llm_response.content, source_payload, count, difficulty_label, focus_name)
        if llm_response
        else []
    )
    provider = llm_response.used_provider if llm_response and items else OFFLINE_PROVIDER
    if not items:
        items = _offline_practice_items(sources, count, difficulty_label=difficulty_label, focus_name=focus_name)
    content = _practice_items_to_markdown(items)
    return _save_material(
        db,
        course_id,
        f"practice:{difficulty}",
        content,
        sources,
        provider,
        extra={"items": items},
    )


def _save_material(
    db: Session,
    course_id: int,
    kind: str,
    content: str,
    sources: list[SearchResult],
    provider: str,
    extra: dict | None = None,
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
    payload = {"content": content, "sources": source_payload, "provider": provider}
    if extra:
        payload.update(extra)
    return payload


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
                "chunk_id": source.chunk_id,
                "document_id": source.document_id,
                "document_name": source.document_name,
                "page": source.page_number,
                "chunk_index": source.chunk_index,
                "score": round(source.score, 4),
                "preview": preview[:180],
                "retrieval_provider": source.retrieval_provider,
            }
        )
    return payload


def _parse_practice_items(
    content: str,
    source_payload: list[dict],
    count: int,
    difficulty_label: str,
    focus_name: str,
) -> list[dict]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        raw_items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(raw_items, list):
        return []

    items: list[dict] = []
    for index, raw in enumerate(raw_items[:count], start=1):
        if not isinstance(raw, dict):
            continue
        question = str(raw.get("question") or raw.get("题干") or "").strip()
        reference_answer = str(raw.get("reference_answer") or raw.get("answer") or raw.get("参考答案") or "").strip()
        if not question or not reference_answer:
            continue
        question_type = str(raw.get("question_type") or raw.get("type") or raw.get("题型") or "简答题").strip()
        options = raw.get("options") or raw.get("选项") or []
        if isinstance(options, str):
            options = [line.strip() for line in options.splitlines() if line.strip()]
        if not isinstance(options, list):
            options = []
        source_numbers = raw.get("source_numbers") or raw.get("sources") or []
        sources = _sources_from_numbers(source_numbers, source_payload) or source_payload[:1]
        knowledge_points = raw.get("knowledge_points") or raw.get("关联知识点") or []
        if isinstance(knowledge_points, str):
            knowledge_points = [knowledge_points]
        if not knowledge_points:
            knowledge_points = [focus_name or _first_practice_keyword(question) or difficulty_label]
        items.append(
            {
                "id": f"practice-{index}",
                "question_type": question_type,
                "type": question_type,
                "question": question,
                "options": [str(option).strip() for option in options if str(option).strip()],
                "reference_answer": reference_answer,
                "answer": reference_answer,
                "explanation": str(raw.get("explanation") or raw.get("解析") or "请结合来源片段复核答案依据。").strip(),
                "knowledge_points": [str(point).strip() for point in knowledge_points if str(point).strip()],
                "sources": sources,
            }
        )
    return items


def _offline_practice_items(
    sources: list[SearchResult],
    count: int,
    difficulty_label: str,
    focus_name: str,
) -> list[dict]:
    source_payload = _sources_payload(sources)
    if not sources:
        return []
    question_types = ["选择题", "填空题", "简答题"]
    items: list[dict] = []
    for index in range(count):
        source = sources[index % len(sources)]
        source_ref = source_payload[index % len(source_payload)] if source_payload else {}
        basis = _compact_practice_basis(source.content)
        question_type = question_types[index % len(question_types)]
        knowledge = focus_name or _first_practice_keyword(basis) or "核心概念"
        prefix = f"{difficulty_label}｜{knowledge}"
        if question_type == "选择题":
            question = f"【{prefix}】根据资料，下面哪一项最接近原文重点？"
            options = [
                f"A. {basis[:46]}",
                "B. 与课程资料无关的说法",
                "C. 只记结论不需要理解条件",
                "D. 与原文相反的表述",
            ]
            answer = "A"
            explanation = f"依据来源片段：{basis[:90]}"
        elif question_type == "填空题":
            keyword = _first_practice_keyword(basis) or knowledge
            question = f"【{prefix}】资料中强调的关键词之一是：____。"
            options = []
            answer = keyword
            explanation = f"该关键词来自来源片段：{basis[:90]}"
        else:
            question = f"【{prefix}】请简要说明以下知识点的含义或应用场景：{basis[:60]}"
            options = []
            answer = f"应围绕资料中的核心表述展开，可概括为：{basis[:120]}"
            explanation = "作答时需要说明定义、适用条件和与来源片段的对应关系。"
        items.append(
            {
                "id": f"practice-{index + 1}",
                "question_type": question_type,
                "type": question_type,
                "question": question,
                "options": options,
                "reference_answer": answer,
                "answer": answer,
                "explanation": explanation,
                "knowledge_points": [knowledge],
                "sources": [source_ref] if source_ref else [],
            }
        )
    return items


def _practice_items_to_markdown(items: list[dict]) -> str:
    if not items:
        return "当前课程还没有可用于生成练习题的资料。请先上传资料并等待入库后再生成专项练习。"
    blocks: list[str] = []
    for index, item in enumerate(items, start=1):
        options = "\n".join(str(option) for option in item.get("options") or [])
        knowledge = "、".join(item.get("knowledge_points") or [])
        source_text = "；".join(
            f"{source.get('document_name', '')} P{source.get('page', '-')}"
            for source in item.get("sources", [])
        )
        block_parts = [
            f"{index}. 【{item.get('question_type', '练习题')}】{item.get('question', '')}",
        ]
        if options:
            block_parts.append(options)
        block_parts.extend(
            [
                f"参考答案：{item.get('reference_answer') or item.get('answer') or ''}",
                f"解析：{item.get('explanation', '')}",
                f"关联知识点：{knowledge or '核心概念'}",
                f"来源：{source_text or '课程资料片段'}",
            ]
        )
        blocks.append("\n".join(block_parts))
    return "\n\n".join(blocks)


def _sources_from_numbers(raw_numbers: object, source_payload: list[dict]) -> list[dict]:
    if not isinstance(raw_numbers, list):
        return []
    sources: list[dict] = []
    for value in raw_numbers:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= len(source_payload):
            sources.append(source_payload[number - 1])
    return sources


def _compact_practice_basis(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact or "课程资料核心内容"


def _first_practice_keyword(text: str) -> str:
    match = re.search(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9_]{2,}", text)
    return match.group(0) if match else ""


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
