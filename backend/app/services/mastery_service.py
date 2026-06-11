from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.entities import KnowledgePoint, QuestionAttempt, UserKnowledgeStatus


INITIAL_MASTERY = 60.0
# Older rows may still carry the pre-formula default before 60.0 was standardized.
LEGACY_DEFAULT_MASTERY = 55.0

ERROR_TYPE_LABELS = {
    "concept_confusion": "概念混淆",
    "formula_error": "公式/定义记忆错误",
    "procedure_gap": "步骤跳跃",
    "coding_syntax": "代码语法错误",
    "careless": "粗心",
    "unknown": "未分类",
}


@dataclass(frozen=True)
class MasteryResult:
    score: float
    level: str
    level_label: str
    correct_count: int
    wrong_count: int
    last_practiced_at: datetime | None
    main_error_type: str
    main_error_label: str
    explanation: str


def calculate_mastery(
    db: Session,
    point: KnowledgePoint,
    status: UserKnowledgeStatus | None,
    user_id: str,
) -> MasteryResult:
    attempts = (
        db.query(QuestionAttempt)
        .filter(
            QuestionAttempt.user_id == user_id,
            QuestionAttempt.course_id == point.course_id,
            QuestionAttempt.knowledge_point_id == point.id,
        )
        .order_by(QuestionAttempt.created_at.asc())
        .all()
    )

    score = INITIAL_MASTERY
    correct_count = 0
    wrong_count = 0
    error_counter: Counter[str] = Counter()
    recent_wrong_count = 0
    last_practiced_at = attempts[-1].created_at if attempts else None

    for attempt in attempts:
        if attempt.is_correct:
            correct_count += 1
        else:
            wrong_count += 1
            error_type = classify_error_type(attempt.error_reason, attempt.question_text, attempt.user_answer)
            error_counter[error_type] += 1
            if _age_days(attempt.created_at) <= 7:
                recent_wrong_count += 1
        score += mastery_delta(attempt.difficulty, attempt.is_correct) * recency_weight(attempt.created_at)

    if not attempts and status is not None:
        if status.review_count > 0 or status.mastery_score != LEGACY_DEFAULT_MASTERY:
            score = max(INITIAL_MASTERY, float(status.mastery_score))

    score = round(max(0.0, min(100.0, score)), 1)
    level, level_label = mastery_level(score)
    main_error_type = error_counter.most_common(1)[0][0] if error_counter else "unknown"
    main_error_label = ERROR_TYPE_LABELS[main_error_type]
    explanation = build_explanation(
        point.name,
        score,
        level_label,
        correct_count,
        wrong_count,
        recent_wrong_count,
        main_error_label,
    )

    return MasteryResult(
        score=score,
        level=level,
        level_label=level_label,
        correct_count=correct_count,
        wrong_count=wrong_count,
        last_practiced_at=last_practiced_at,
        main_error_type=main_error_type,
        main_error_label=main_error_label,
        explanation=explanation,
    )


def apply_mastery_to_status(
    db: Session,
    point: KnowledgePoint,
    status: UserKnowledgeStatus,
    user_id: str,
) -> MasteryResult:
    result = calculate_mastery(db, point, status, user_id)
    status.mastery_score = result.score
    status.wrong_count = result.wrong_count
    status.review_count = result.correct_count + result.wrong_count
    status.last_review_time = result.last_practiced_at
    return result


def mastery_delta(difficulty: str, is_correct: bool) -> float:
    if is_correct:
        return {
            "basic": 5.0,
            "advanced": 8.0,
            "exam": 10.0,
            "mistake": 8.0,
        }.get(difficulty, 5.0)
    return {
        "basic": -8.0,
        "advanced": -12.0,
        "exam": -15.0,
        "mistake": -15.0,
    }.get(difficulty, -8.0)


def recency_weight(created_at: datetime | None) -> float:
    days = _age_days(created_at)
    if days <= 7:
        return 1.2
    if days <= 30:
        return 1.0
    return 0.6


def classify_error_type(reason: str, question_text: str = "", answer_text: str = "") -> str:
    text = f"{reason} {question_text} {answer_text}".lower()
    if any(word in text for word in ("公式", "定义", "定理")):
        return "formula_error"
    if any(word in text for word in ("步骤", "推导", "过程", "证明", "跳跃")):
        return "procedure_gap"
    if any(word in text for word in ("语法", "编译", "分号", "少分号")):
        return "coding_syntax"
    if any(word in text for word in ("粗心", "看错", "漏看")):
        return "careless"
    if any(word in text for word in ("概念", "混淆", "不清")):
        return "concept_confusion"
    if any(word in text for word in ("公式", "定义", "定理", "formula")):
        return "formula_error"
    if any(word in text for word in ("步骤", "推导", "过程", "证明", "procedure")):
        return "procedure_gap"
    if any(word in text for word in ("语法", "编译", "cout", "cin", "分号", "syntax", "compile")):
        return "coding_syntax"
    if any(word in text for word in ("粗心", "看错", "漏看", "careless")):
        return "careless"
    if any(word in text for word in ("概念", "混淆", "不清", "concept")):
        return "concept_confusion"
    return "unknown"


def mastery_level(score: float) -> tuple[str, str]:
    if score < 40:
        return "high_risk", "高危薄弱"
    if score < 60:
        return "needs_review", "需要复习"
    if score < 80:
        return "basic_mastery", "基本掌握"
    return "solid", "掌握良好"


def build_explanation(
    point_name: str,
    score: float,
    level_label: str,
    correct_count: int,
    wrong_count: int,
    recent_wrong_count: int,
    main_error_label: str,
) -> str:
    if correct_count == 0 and wrong_count == 0:
        return f"该知识点暂无练习记录，系统按初始掌握度 60 分展示，建议先完成基础题建立诊断样本。"
    recent = f"最近 7 天答错 {recent_wrong_count} 次，" if recent_wrong_count else ""
    return (
        f"该知识点累计答对 {correct_count} 次、答错 {wrong_count} 次，"
        f"{recent}主要错因为{main_error_label}，当前掌握度 {score} 分，因此被判定为{level_label}。"
    )


def _age_days(created_at: datetime | None) -> int:
    if created_at is None:
        return 0
    return max(0, (datetime.utcnow() - created_at).days)
