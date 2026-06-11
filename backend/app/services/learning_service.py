from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from itertools import combinations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.entities import (
    ChatMessage,
    ChunkKnowledgePoint,
    Course,
    Document,
    DocumentChunk,
    GeneratedMaterial,
    KnowledgePoint,
    QuestionAttempt,
    ReviewTask,
    UserKnowledgeStatus,
)
from app.schemas import AttemptCreate, ReviewPlanRequest
from app.services.llm_service import call_llm


DEMO_USER_ID = "demo-user"

DIFFICULTY_LABELS = {
    "basic": "基础题",
    "advanced": "提高题",
    "exam": "考试题",
    "mistake": "易错题",
}

DEFAULT_KNOWLEDGE_POINTS = {
    "math": [
        "函数极限",
        "导数与微分",
        "不定积分",
        "定积分应用",
        "二重积分换序",
        "格林公式",
        "级数收敛",
    ],
    "cpp": [
        "类与对象",
        "构造函数",
        "继承与派生",
        "虚函数与多态",
        "运算符重载",
        "模板",
        "STL 容器",
    ],
    "physics": [
        "牛顿运动定律",
        "动量守恒",
        "刚体转动",
        "静电场",
        "磁场与电磁感应",
        "热力学第一定律",
        "机械振动",
    ],
    "generic": [
        "核心概念",
        "基本公式",
        "典型题型",
        "易错点",
        "综合应用",
    ],
}

KNOWN_CONCEPTS = [
    "函数极限",
    "连续性",
    "导数",
    "微分",
    "洛必达法则",
    "泰勒公式",
    "不定积分",
    "定积分",
    "反常积分",
    "二重积分",
    "二重积分换序",
    "三重积分",
    "曲线积分",
    "曲面积分",
    "格林公式",
    "高斯公式",
    "斯托克斯公式",
    "级数",
    "幂级数",
    "矩阵",
    "线性方程组",
    "类与对象",
    "构造函数",
    "析构函数",
    "继承",
    "多态",
    "虚函数",
    "模板",
    "异常处理",
    "STL",
    "vector",
    "map",
    "迭代器",
    "递归",
    "排序算法",
    "牛顿运动定律",
    "动量守恒",
    "机械能守恒",
    "刚体转动",
    "静电场",
    "电势",
    "磁场",
    "电磁感应",
    "热力学",
    "波动光学",
]

CONCEPT_MARKERS = (
    "定义",
    "定理",
    "公式",
    "法则",
    "性质",
    "方法",
    "算法",
    "模型",
    "结构",
    "函数",
    "积分",
    "导数",
    "极限",
    "级数",
    "继承",
    "多态",
    "模板",
    "守恒",
)

LLM_EXTRACTION_CHUNK_LIMIT = 12


def sync_course_knowledge_points(
    db: Session,
    course_id: int,
    document_id: int | None = None,
    user_id: str | None = None,
) -> None:
    user_id = _resolve_user_id(db, course_id, user_id)
    course = db.get(Course, course_id)
    if course is None:
        return

    query = db.query(DocumentChunk).filter(DocumentChunk.course_id == course_id)
    if document_id is not None:
        query = query.filter(DocumentChunk.document_id == document_id)
    chunks = query.order_by(DocumentChunk.document_id.asc(), DocumentChunk.chunk_index.asc()).limit(160).all()

    if chunks:
        llm_candidates = _llm_candidate_points_for_chunks(course.name, chunks) if document_id is not None else {}
        for chunk in chunks:
            rule_candidates = [
                {
                    "name": name,
                    "description": f"从课程资料中识别出的知识点：{name}",
                    "evidence": chunk.content[:240],
                }
                for name in _candidate_names_for_chunk(course.name, chunk.content)
            ]
            for item in _unique_candidate_items([*llm_candidates.get(chunk.id, []), *rule_candidates])[:4]:
                point = _get_or_create_knowledge_point(
                    db,
                    course_id=course_id,
                    name=item["name"],
                    description=item["description"],
                    source_document_id=chunk.document_id,
                    source_page=chunk.page_number,
                    evidence=item["evidence"] or chunk.content[:240],
                )
                _link_chunk_to_point(db, course_id, chunk.id, point.id)
                _ensure_status(db, course_id, point.id, user_id)
    elif db.query(KnowledgePoint).filter(KnowledgePoint.course_id == course_id).count() == 0:
        _seed_course_knowledge_points(db, course, user_id)

    _ensure_all_statuses(db, course_id, user_id)
    db.flush()


def get_learning_profile(db: Session, course_id: int, user_id: str | None = None) -> dict:
    user_id = _resolve_user_id(db, course_id, user_id)
    sync_course_knowledge_points(db, course_id, user_id=user_id)
    points = _knowledge_status_payloads(db, course_id, user_id)
    weak_points = sorted(points, key=lambda item: (item["mastery_score"], -item["wrong_count"]))[:5]
    attempts_count = db.query(func.count(QuestionAttempt.id)).filter(
        QuestionAttempt.course_id == course_id,
        QuestionAttempt.user_id == user_id,
    ).scalar() or 0
    correct_count = db.query(func.count(QuestionAttempt.id)).filter(
        QuestionAttempt.course_id == course_id,
        QuestionAttempt.user_id == user_id,
        QuestionAttempt.is_correct.is_(True),
    ).scalar() or 0
    question_count = db.query(func.count(ChatMessage.id)).filter(ChatMessage.course_id == course_id).scalar() or 0
    generated_count = (
        db.query(func.count(GeneratedMaterial.id)).filter(GeneratedMaterial.course_id == course_id).scalar()
        or 0
    )
    document_count = db.query(func.count(Document.id)).filter(Document.course_id == course_id).scalar() or 0
    chunk_count = db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.course_id == course_id).scalar() or 0
    pending_tasks = _review_task_payloads(
        db,
        course_id,
        user_id,
        status_filter=("pending", "planned"),
        limit=8,
    )
    recent_attempts = _attempt_payloads(db, course_id, user_id, only_wrong=False, limit=6)
    recent_questions = _recent_question_payloads(db, course_id, limit=3)

    overall_mastery = (
        round(sum(point["mastery_score"] for point in points) / len(points), 1) if points else 0.0
    )
    accuracy = round((correct_count / attempts_count) * 100, 1) if attempts_count else 0.0

    return {
        "user_id": user_id,
        "summary": {
            "study_actions": question_count + generated_count + attempts_count,
            "question_count": question_count,
            "practice_attempt_count": attempts_count,
            "practice_accuracy": accuracy,
            "overall_mastery": overall_mastery,
            "knowledge_point_count": len(points),
            "document_count": document_count,
            "chunk_count": chunk_count,
        },
        "knowledge_points": points,
        "weak_points": weak_points,
        "recommendations": _recommendations_from_weak_points(weak_points),
        "recent_questions": recent_questions,
        "recent_attempts": recent_attempts,
        "pending_tasks": pending_tasks,
    }


def get_knowledge_graph(db: Session, course_id: int, user_id: str | None = None) -> dict:
    user_id = _resolve_user_id(db, course_id, user_id)
    sync_course_knowledge_points(db, course_id, user_id=user_id)
    nodes = _knowledge_status_payloads(db, course_id, user_id)
    node_ids = {node["id"] for node in nodes}
    edges: set[tuple[int, int, str]] = set()

    for point in db.query(KnowledgePoint).filter(KnowledgePoint.course_id == course_id).all():
        if point.parent_id and point.parent_id in node_ids:
            edges.add((point.parent_id, point.id, "parent"))

    links = (
        db.query(ChunkKnowledgePoint.chunk_id, ChunkKnowledgePoint.knowledge_point_id)
        .filter(ChunkKnowledgePoint.course_id == course_id)
        .limit(600)
        .all()
    )
    by_chunk: dict[int, list[int]] = defaultdict(list)
    for chunk_id, point_id in links:
        by_chunk[chunk_id].append(point_id)
    for point_ids in by_chunk.values():
        unique_ids = sorted(set(point_ids))
        for source_id, target_id in combinations(unique_ids[:4], 2):
            edges.add((source_id, target_id, "co_occurs"))

    return {
        "nodes": nodes,
        "edges": [
            {"source": source_id, "target": target_id, "relation": relation}
            for source_id, target_id, relation in sorted(edges)
        ],
    }


def get_wrong_attempts(
    db: Session,
    course_id: int,
    limit: int = 20,
    user_id: str | None = None,
) -> list[dict]:
    user_id = _resolve_user_id(db, course_id, user_id)
    return _attempt_payloads(db, course_id, user_id, only_wrong=True, limit=limit)


def record_question_attempt(
    db: Session,
    course_id: int,
    payload: AttemptCreate,
    user_id: str | None = None,
) -> dict:
    user_id = _resolve_user_id(db, course_id, user_id)
    sync_course_knowledge_points(db, course_id, user_id=user_id)
    point = _resolve_attempt_point(db, course_id, payload.knowledge_point_id, user_id)
    error_reason = payload.error_reason.strip() or _infer_error_reason(payload)
    correct_answer = payload.correct_answer.strip() or (payload.user_answer.strip() if payload.is_correct else "")

    attempt = QuestionAttempt(
        user_id=user_id,
        course_id=course_id,
        knowledge_point_id=point.id if point else None,
        question_text=payload.question_text.strip(),
        user_answer=payload.user_answer.strip(),
        correct_answer=correct_answer,
        is_correct=payload.is_correct,
        error_reason=error_reason,
        difficulty=payload.difficulty,
    )
    db.add(attempt)

    status_payload = None
    if point:
        status = _ensure_status(db, course_id, point.id, user_id)
        delta = _mastery_delta(payload.difficulty, payload.is_correct)
        status.mastery_score = max(0.0, min(100.0, status.mastery_score + delta))
        status.review_count += 1
        status.last_review_time = datetime.utcnow()
        if not payload.is_correct:
            status.wrong_count += 1
            _create_wrong_task(db, course_id, point, error_reason, payload.difficulty, user_id)
        db.flush()
        status_payload = _status_payload(point, status)

    db.commit()
    db.refresh(attempt)

    return {
        "attempt": _attempt_payload(db, attempt),
        "knowledge_status": status_payload,
        "next_training": _next_training_suggestion(point, payload.difficulty, payload.is_correct),
    }


def create_review_plan(
    db: Session,
    course_id: int,
    payload: ReviewPlanRequest,
    user_id: str | None = None,
) -> dict:
    user_id = _resolve_user_id(db, course_id, user_id)
    sync_course_knowledge_points(db, course_id, user_id=user_id)
    today = date.today()
    days_left = max(1, (payload.exam_date - today).days)
    points = _select_plan_points(db, course_id, payload.goals, user_id)
    if not points:
        return {"exam_date": payload.exam_date.isoformat(), "days_left": days_left, "tasks": []}

    slots_per_day = max(1, min(4, payload.daily_minutes // 45))
    total_slots = max(slots_per_day, min(days_left * slots_per_day, 24))
    tasks: list[dict] = []
    for index in range(total_slots):
        plan_day = today + timedelta(days=index // slots_per_day)
        point = points[index % len(points)]
        difficulty = "mistake" if point["mastery_score"] < 55 else "exam"
        deadline = datetime.combine(plan_day, time(hour=21, minute=30))
        title = f"复习{point['name']}并完成{DIFFICULTY_LABELS[difficulty]}"
        description = _plan_description(point, difficulty, payload.daily_minutes)
        task = _get_or_create_review_task(
            db,
            course_id=course_id,
            user_id=user_id,
            point_id=point["id"],
            title=title,
            description=description,
            deadline=deadline,
            task_type="exam_plan",
            status="planned",
            estimated_minutes=min(45, max(20, payload.daily_minutes // slots_per_day)),
            priority=3 if point["mastery_score"] < 55 else 2,
        )
        db.flush()
        tasks.append(_review_task_payload(task, point["name"]))

    db.commit()
    return {
        "exam_date": payload.exam_date.isoformat(),
        "days_left": days_left,
        "daily_minutes": payload.daily_minutes,
        "goals": payload.goals,
        "tasks": tasks,
    }


def update_review_task_status(
    db: Session,
    course_id: int,
    task_id: int,
    status: str,
    user_id: str | None = None,
) -> dict | None:
    user_id = _resolve_user_id(db, course_id, user_id)
    task = db.get(ReviewTask, task_id)
    if task is None or task.course_id != course_id or task.user_id != user_id:
        return None
    task.status = status
    if status == "done" and task.knowledge_point_id:
        knowledge_status = _ensure_status(db, course_id, task.knowledge_point_id, user_id)
        knowledge_status.mastery_score = min(100.0, knowledge_status.mastery_score + 6)
        knowledge_status.review_count += 1
        knowledge_status.last_review_time = datetime.utcnow()
    db.commit()
    point_name = ""
    if task.knowledge_point_id:
        point = db.get(KnowledgePoint, task.knowledge_point_id)
        point_name = point.name if point else ""
    return _review_task_payload(task, point_name)


def _seed_course_knowledge_points(db: Session, course: Course, user_id: str) -> None:
    for name in _default_seed_names(course.name):
        point = _get_or_create_knowledge_point(
            db,
            course_id=course.id,
            name=name,
            description=f"{course.name} 的核心复习知识点",
            source_document_id=None,
            source_page=0,
            evidence="暂无资料片段，系统按课程名称生成初始学习画像。",
        )
        _ensure_status(db, course.id, point.id, user_id)


def _default_seed_names(course_name: str) -> list[str]:
    lowered = course_name.lower()
    if "c++" in lowered or "程序" in course_name or "编程" in course_name:
        return DEFAULT_KNOWLEDGE_POINTS["cpp"]
    if "物理" in course_name:
        return DEFAULT_KNOWLEDGE_POINTS["physics"]
    if "数学" in course_name or "高数" in course_name or "微积分" in course_name:
        return DEFAULT_KNOWLEDGE_POINTS["math"]
    return DEFAULT_KNOWLEDGE_POINTS["generic"]


def _candidate_names_for_chunk(course_name: str, content: str) -> list[str]:
    candidates: dict[str, int] = {}
    compact = re.sub(r"\s+", "", content)
    lowered = compact.lower()
    for name in [*_default_seed_names(course_name), *KNOWN_CONCEPTS]:
        if name.lower() in lowered:
            candidates[name] = candidates.get(name, 0) + len(name) + 8

    for line in content.splitlines()[:60]:
        clean = re.sub(r"^[\s#*·\-—\d.、（）()第章节]+", "", line.strip())
        clean = re.sub(r"[:：].*$", "", clean)
        clean = clean.strip(" 。，,；;")
        if 2 <= len(clean) <= 18 and any(marker in clean for marker in CONCEPT_MARKERS):
            candidates[clean] = candidates.get(clean, 0) + 6

    if not candidates:
        for name in _default_seed_names(course_name)[:2]:
            candidates[name] = 1

    return [
        name
        for name, _score in sorted(
            candidates.items(),
            key=lambda item: (item[1], len(item[0])),
            reverse=True,
        )
    ][:8]


def _llm_candidate_points_for_chunks(course_name: str, chunks: list[DocumentChunk]) -> dict[int, list[dict]]:
    sampled_chunks = chunks[:LLM_EXTRACTION_CHUNK_LIMIT]
    if not sampled_chunks:
        return {}

    context = "\n\n".join(
        f"[chunk_id:{chunk.id}] P{chunk.page_number}\n{chunk.content[:900]}"
        for chunk in sampled_chunks
    )
    messages = [
        {
            "role": "system",
            "content": (
                "你是课程知识点抽取助手。只根据给定课程片段抽取知识点，"
                "返回严格 JSON 数组，不要 Markdown，不要额外解释。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"课程名称：{course_name}\n\n课程片段：\n{context}\n\n"
                "请返回数组，每项包含 chunk_id、name、description、evidence、difficulty。"
                "difficulty 只能是 easy、medium、hard；name 控制在 2 到 18 个中文字符或英文术语内。"
            ),
        },
    ]
    response = call_llm(messages, temperature=0)
    if response is None:
        return {}

    parsed = _parse_llm_points(response.content)
    valid_chunk_ids = {chunk.id for chunk in sampled_chunks}
    fallback_chunk_id = sampled_chunks[0].id
    result: dict[int, list[dict]] = defaultdict(list)
    for item in parsed[:36]:
        if not isinstance(item, dict):
            continue
        name = _clean_knowledge_name(str(item.get("name") or ""))
        if not name:
            continue
        chunk_id = _coerce_int(item.get("chunk_id"))
        if chunk_id not in valid_chunk_ids:
            chunk_id = fallback_chunk_id
        description = str(item.get("description") or f"由大模型从课程资料中抽取出的知识点：{name}").strip()
        evidence = str(item.get("evidence") or "").strip()[:240]
        difficulty = str(item.get("difficulty") or "").strip().lower()
        if difficulty in {"easy", "medium", "hard"} and "难度" not in description:
            description = f"{description}（难度：{difficulty}）"
        result[chunk_id].append(
            {
                "name": name,
                "description": description[:500],
                "evidence": evidence,
            }
        )
    return result


def _parse_llm_points(content: str) -> list[dict]:
    text = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


def _unique_candidate_items(items: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for item in items:
        name = _clean_knowledge_name(str(item.get("name") or ""))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(
            {
                "name": name,
                "description": str(item.get("description") or f"从课程资料中识别出的知识点：{name}").strip(),
                "evidence": str(item.get("evidence") or "").strip()[:240],
            }
        )
    return unique


def _clean_knowledge_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", name).strip(" 。，,；;：:")
    if not (2 <= len(cleaned) <= 120):
        return ""
    return cleaned[:120]


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _get_or_create_knowledge_point(
    db: Session,
    course_id: int,
    name: str,
    description: str,
    source_document_id: int | None,
    source_page: int,
    evidence: str,
) -> KnowledgePoint:
    normalized = re.sub(r"\s+", " ", name).strip()[:120]
    point = (
        db.query(KnowledgePoint)
        .filter(KnowledgePoint.course_id == course_id, KnowledgePoint.name == normalized)
        .first()
    )
    if point:
        if not point.evidence and evidence:
            point.evidence = evidence
        if not point.source_page and source_page:
            point.source_page = source_page
        if not point.source_document_id and source_document_id:
            point.source_document_id = source_document_id
        return point
    point = KnowledgePoint(
        course_id=course_id,
        name=normalized,
        description=description,
        source_document_id=source_document_id,
        source_page=source_page,
        evidence=evidence,
    )
    db.add(point)
    db.flush()
    return point


def _link_chunk_to_point(db: Session, course_id: int, chunk_id: int, point_id: int) -> None:
    exists = (
        db.query(ChunkKnowledgePoint)
        .filter(
            ChunkKnowledgePoint.chunk_id == chunk_id,
            ChunkKnowledgePoint.knowledge_point_id == point_id,
        )
        .first()
    )
    if exists:
        return
    db.add(
        ChunkKnowledgePoint(
            course_id=course_id,
            chunk_id=chunk_id,
            knowledge_point_id=point_id,
            weight=1.0,
        )
    )


def _resolve_user_id(db: Session, course_id: int, user_id: str | None) -> str:
    if user_id:
        return str(user_id)
    course = db.get(Course, course_id)
    if course is not None and course.user_id:
        return str(course.user_id)
    return DEMO_USER_ID


def _ensure_all_statuses(db: Session, course_id: int, user_id: str) -> None:
    point_ids = [row[0] for row in db.query(KnowledgePoint.id).filter(KnowledgePoint.course_id == course_id).all()]
    for point_id in point_ids:
        _ensure_status(db, course_id, point_id, user_id)


def _ensure_status(db: Session, course_id: int, point_id: int, user_id: str) -> UserKnowledgeStatus:
    status = (
        db.query(UserKnowledgeStatus)
        .filter(
            UserKnowledgeStatus.user_id == user_id,
            UserKnowledgeStatus.course_id == course_id,
            UserKnowledgeStatus.knowledge_point_id == point_id,
        )
        .first()
    )
    if status:
        return status
    status = UserKnowledgeStatus(
        user_id=user_id,
        course_id=course_id,
        knowledge_point_id=point_id,
        mastery_score=55.0,
    )
    db.add(status)
    db.flush()
    return status


def _knowledge_status_payloads(db: Session, course_id: int, user_id: str) -> list[dict]:
    rows = (
        db.query(KnowledgePoint, UserKnowledgeStatus)
        .join(
            UserKnowledgeStatus,
            UserKnowledgeStatus.knowledge_point_id == KnowledgePoint.id,
        )
        .filter(
            KnowledgePoint.course_id == course_id,
            UserKnowledgeStatus.user_id == user_id,
        )
        .order_by(KnowledgePoint.id.asc())
        .all()
    )
    return [_status_payload(point, status) for point, status in rows]


def _status_payload(point: KnowledgePoint, status: UserKnowledgeStatus) -> dict:
    score = _decayed_mastery(status)
    return {
        "id": point.id,
        "name": point.name,
        "description": point.description,
        "mastery_score": score,
        "raw_mastery_score": round(status.mastery_score, 1),
        "wrong_count": status.wrong_count,
        "review_count": status.review_count,
        "last_review_time": status.last_review_time,
        "source_page": point.source_page,
        "source_document_id": point.source_document_id,
        "evidence": point.evidence[:180] if point.evidence else "",
        "state": _mastery_state(score),
    }


def _decayed_mastery(status: UserKnowledgeStatus) -> float:
    score = status.mastery_score
    if status.last_review_time:
        days = max(0, (datetime.utcnow() - status.last_review_time).days - 3)
        score -= min(18, days * 1.2)
    return round(max(0.0, min(100.0, score)), 1)


def _mastery_state(score: float) -> str:
    if score >= 80:
        return "solid"
    if score >= 60:
        return "review"
    return "weak"


def _recommendations_from_weak_points(weak_points: list[dict]) -> list[dict]:
    recommendations: list[dict] = []
    for index, point in enumerate(weak_points[:5], start=1):
        difficulty = "mistake" if point["wrong_count"] else "basic"
        page_text = f"回看资料 P{point['source_page']}" if point["source_page"] else "补充课程资料来源"
        recommendations.append(
            {
                "rank": index,
                "knowledge_point_id": point["id"],
                "title": f"先复习{point['name']}",
                "reason": f"掌握度 {point['mastery_score']}%，错题 {point['wrong_count']} 次",
                "action": f"{page_text}，再做 3 道{DIFFICULTY_LABELS[difficulty]}和 1 道变式题。",
                "difficulty": difficulty,
            }
        )
    return recommendations


def _resolve_attempt_point(
    db: Session, course_id: int, knowledge_point_id: int | None, user_id: str
) -> KnowledgePoint | None:
    if knowledge_point_id:
        point = db.get(KnowledgePoint, knowledge_point_id)
        if point and point.course_id == course_id:
            return point
    weak_points = _knowledge_status_payloads(db, course_id, user_id)
    if not weak_points:
        return None
    weakest_id = sorted(weak_points, key=lambda item: (item["mastery_score"], -item["wrong_count"]))[0]["id"]
    return db.get(KnowledgePoint, weakest_id)


def _infer_error_reason(payload: AttemptCreate) -> str:
    if payload.is_correct:
        return "掌握较好"
    text = f"{payload.question_text} {payload.user_answer} {payload.correct_answer}"
    if any(symbol in text for symbol in ("=", "+", "-", "∫", "lim", "公式")):
        return "公式记错"
    if len(payload.user_answer.strip()) < 8:
        return "概念不清"
    if any(word in payload.question_text for word in ("步骤", "证明", "推导", "计算")):
        return "步骤跳跃"
    return "题型识别错误"


def _mastery_delta(difficulty: str, is_correct: bool) -> float:
    if is_correct:
        return {"basic": 8, "advanced": 11, "exam": 13, "mistake": 10}.get(difficulty, 8)
    return {"basic": -16, "advanced": -15, "exam": -12, "mistake": -15}.get(difficulty, -15)


def _create_wrong_task(
    db: Session,
    course_id: int,
    point: KnowledgePoint,
    error_reason: str,
    difficulty: str,
    user_id: str,
) -> None:
    deadline = datetime.utcnow() + timedelta(days=1)
    title = f"错题复盘：{point.name}"
    description = (
        f"错因：{error_reason}。建议回看资料 P{point.source_page or '-'}，"
        f"完成 3 道{DIFFICULTY_LABELS.get(difficulty, '基础题')}和 1 道变式题。"
    )
    db.add(
        ReviewTask(
            user_id=user_id,
            course_id=course_id,
            knowledge_point_id=point.id,
            task_type="wrong_question",
            title=title,
            description=description,
            deadline=deadline,
            status="pending",
            estimated_minutes=25,
            priority=3,
        )
    )


def _next_training_suggestion(
    point: KnowledgePoint | None,
    difficulty: str,
    is_correct: bool,
) -> dict:
    if not point:
        return {
            "title": "补充知识点标签",
            "description": "先在课程资料中抽取知识点，再进行专项练习。",
            "difficulty": difficulty,
        }
    if is_correct:
        return {
            "title": f"升级训练：{point.name}",
            "description": f"本题已掌握，下一轮建议做 2 道{DIFFICULTY_LABELS['advanced']}或 1 道考试综合题。",
            "difficulty": "advanced",
        }
    return {
        "title": f"专项补弱：{point.name}",
        "description": "先复盘错因，再完成 3 道同类基础题和 1 道变式题。",
        "difficulty": "mistake",
    }


def _select_plan_points(db: Session, course_id: int, goals: str, user_id: str) -> list[dict]:
    points = _knowledge_status_payloads(db, course_id, user_id)
    goal_terms = [term.lower() for term in re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9_+]+", goals)]
    if goal_terms:
        matched = [
            point
            for point in points
            if any(term in point["name"].lower() or term in point["description"].lower() for term in goal_terms)
        ]
        if matched:
            points = matched
    return sorted(points, key=lambda item: (item["mastery_score"], -item["wrong_count"]))[:8]


def _plan_description(point: dict, difficulty: str, daily_minutes: int) -> str:
    page_text = f"资料 P{point['source_page']}" if point["source_page"] else "对应课程资料"
    practice_count = 5 if daily_minutes >= 90 else 3
    return (
        f"先回看{page_text}，整理 {point['name']} 的定义、条件和易错点；"
        f"随后完成 {practice_count} 道{DIFFICULTY_LABELS[difficulty]}，错题写入错题本。"
    )


def _get_or_create_review_task(
    db: Session,
    course_id: int,
    user_id: str,
    point_id: int,
    title: str,
    description: str,
    deadline: datetime,
    task_type: str,
    status: str,
    estimated_minutes: int,
    priority: int,
) -> ReviewTask:
    task = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.user_id == user_id,
            ReviewTask.course_id == course_id,
            ReviewTask.knowledge_point_id == point_id,
            ReviewTask.title == title,
            ReviewTask.deadline == deadline,
        )
        .first()
    )
    if task:
        task.description = description
        task.status = status
        task.estimated_minutes = estimated_minutes
        task.priority = priority
        return task
    task = ReviewTask(
        user_id=user_id,
        course_id=course_id,
        knowledge_point_id=point_id,
        task_type=task_type,
        title=title,
        description=description,
        deadline=deadline,
        status=status,
        estimated_minutes=estimated_minutes,
        priority=priority,
    )
    db.add(task)
    return task


def _attempt_payloads(
    db: Session,
    course_id: int,
    user_id: str,
    only_wrong: bool,
    limit: int,
) -> list[dict]:
    query = db.query(QuestionAttempt).filter(
        QuestionAttempt.course_id == course_id,
        QuestionAttempt.user_id == user_id,
    )
    if only_wrong:
        query = query.filter(QuestionAttempt.is_correct.is_(False))
    attempts = query.order_by(QuestionAttempt.created_at.desc()).limit(limit).all()
    return [_attempt_payload(db, attempt) for attempt in attempts]


def _recent_question_payloads(db: Session, course_id: int, limit: int) -> list[dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.course_id == course_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": message.id,
            "course_id": message.course_id,
            "question": message.question,
            "answer": message.answer[:180],
            "created_at": message.created_at,
        }
        for message in messages
    ]


def _attempt_payload(db: Session, attempt: QuestionAttempt) -> dict:
    point_name = ""
    if attempt.knowledge_point_id:
        point = db.get(KnowledgePoint, attempt.knowledge_point_id)
        point_name = point.name if point else ""
    return {
        "id": attempt.id,
        "course_id": attempt.course_id,
        "knowledge_point_id": attempt.knowledge_point_id,
        "knowledge_point_name": point_name,
        "question_text": attempt.question_text,
        "user_answer": attempt.user_answer,
        "correct_answer": attempt.correct_answer,
        "is_correct": attempt.is_correct,
        "error_reason": attempt.error_reason,
        "difficulty": attempt.difficulty,
        "difficulty_label": DIFFICULTY_LABELS.get(attempt.difficulty, attempt.difficulty),
        "created_at": attempt.created_at,
    }


def _review_task_payloads(
    db: Session,
    course_id: int,
    user_id: str,
    status_filter: tuple[str, ...],
    limit: int,
) -> list[dict]:
    tasks = (
        db.query(ReviewTask)
        .filter(
            ReviewTask.course_id == course_id,
            ReviewTask.user_id == user_id,
            ReviewTask.status.in_(status_filter),
        )
        .order_by(ReviewTask.priority.desc(), ReviewTask.deadline.asc().nullslast(), ReviewTask.created_at.desc())
        .limit(limit)
        .all()
    )
    point_names: dict[int, str] = {}
    for task in tasks:
        if task.knowledge_point_id and task.knowledge_point_id not in point_names:
            point = db.get(KnowledgePoint, task.knowledge_point_id)
            point_names[task.knowledge_point_id] = point.name if point else ""
    return [_review_task_payload(task, point_names.get(task.knowledge_point_id or 0, "")) for task in tasks]


def _review_task_payload(task: ReviewTask, point_name: str) -> dict:
    return {
        "id": task.id,
        "course_id": task.course_id,
        "knowledge_point_id": task.knowledge_point_id,
        "knowledge_point_name": point_name,
        "task_type": task.task_type,
        "title": task.title,
        "description": task.description,
        "deadline": task.deadline,
        "status": task.status,
        "estimated_minutes": task.estimated_minutes,
        "priority": task.priority,
        "created_at": task.created_at,
    }
