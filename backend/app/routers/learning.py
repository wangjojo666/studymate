from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, learning_user_id
from app.models.entities import Course, User
from app.schemas import AttemptCreate, ReviewPlanRequest, ReviewTaskUpdate
from app.services.learning_service import (
    create_review_plan,
    get_knowledge_graph,
    get_learning_profile,
    get_wrong_attempts,
    record_question_attempt,
    sync_course_knowledge_points,
    update_review_task_status,
)
from app.services.report_service import generate_learning_report_pdf


router = APIRouter(prefix="/courses/{course_id}/learning", tags=["learning"])


@router.post("/sync")
def sync_learning_model(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    sync_course_knowledge_points(db, course_id, user_id=learning_user_id(current_user))
    db.commit()
    return {"ok": True}


@router.get("/profile")
def read_learning_profile(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    profile = get_learning_profile(db, course_id, learning_user_id(current_user))
    db.commit()
    return profile


@router.get("/graph")
def read_knowledge_graph(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    graph = get_knowledge_graph(db, course_id, learning_user_id(current_user))
    db.commit()
    return graph


@router.get("/wrong-attempts")
def read_wrong_attempts(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _ensure_course(db, course_id, current_user.id)
    return get_wrong_attempts(db, course_id, user_id=learning_user_id(current_user))


@router.get("/report.pdf")
def export_learning_report(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _ensure_course(db, course_id, current_user.id)
    try:
        content = generate_learning_report_pdf(db, course_id, learning_user_id(current_user))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    filename = f"studymate-course-{course_id}-learning-report.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/attempts")
def create_attempt(
    course_id: int,
    payload: AttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    return record_question_attempt(db, course_id, payload, learning_user_id(current_user))


@router.post("/review-plan")
def create_exam_review_plan(
    course_id: int,
    payload: ReviewPlanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    return create_review_plan(db, course_id, payload, learning_user_id(current_user))


@router.patch("/tasks/{task_id}")
def update_task(
    course_id: int,
    task_id: int,
    payload: ReviewTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    task = update_review_task_status(db, course_id, task_id, payload.status, learning_user_id(current_user))
    if task is None:
        raise HTTPException(status_code=404, detail="复习任务不存在")
    return task


def _ensure_course(db: Session, course_id: int, user_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id, Course.user_id == user_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course
