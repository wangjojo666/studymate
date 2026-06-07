from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Course
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


router = APIRouter(prefix="/courses/{course_id}/learning", tags=["learning"])


@router.post("/sync")
def sync_learning_model(course_id: int, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    sync_course_knowledge_points(db, course_id)
    db.commit()
    return {"ok": True}


@router.get("/profile")
def read_learning_profile(course_id: int, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    profile = get_learning_profile(db, course_id)
    db.commit()
    return profile


@router.get("/graph")
def read_knowledge_graph(course_id: int, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    graph = get_knowledge_graph(db, course_id)
    db.commit()
    return graph


@router.get("/wrong-attempts")
def read_wrong_attempts(course_id: int, db: Session = Depends(get_db)) -> list[dict]:
    _ensure_course(db, course_id)
    return get_wrong_attempts(db, course_id)


@router.post("/attempts")
def create_attempt(course_id: int, payload: AttemptCreate, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    return record_question_attempt(db, course_id, payload)


@router.post("/review-plan")
def create_exam_review_plan(
    course_id: int,
    payload: ReviewPlanRequest,
    db: Session = Depends(get_db),
) -> dict:
    _ensure_course(db, course_id)
    return create_review_plan(db, course_id, payload)


@router.patch("/tasks/{task_id}")
def update_task(
    course_id: int,
    task_id: int,
    payload: ReviewTaskUpdate,
    db: Session = Depends(get_db),
) -> dict:
    _ensure_course(db, course_id)
    task = update_review_task_status(db, course_id, task_id, payload.status)
    if task is None:
        raise HTTPException(status_code=404, detail="复习任务不存在")
    return task


def _ensure_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course
