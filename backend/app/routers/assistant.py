from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, learning_user_id
from app.models.entities import Course, User
from app.schemas import AskRequest, PracticeRequest
from app.services.rag_service import answer_question, generate_outline, generate_practice


router = APIRouter(prefix="/courses/{course_id}", tags=["assistant"])


@router.post("/ask")
def ask_course(
    course_id: int,
    payload: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    return answer_question(db, course_id, payload.question, payload.top_k)


@router.post("/review-outline")
def create_review_outline(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    return generate_outline(db, course_id)


@router.post("/practice")
def create_practice(
    course_id: int,
    payload: PracticeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _ensure_course(db, course_id, current_user.id)
    return generate_practice(
        db,
        course_id,
        payload.count,
        difficulty=payload.difficulty,
        knowledge_point_id=payload.knowledge_point_id,
        user_id=learning_user_id(current_user),
    )


def _ensure_course(db: Session, course_id: int, user_id: int) -> Course:
    course = db.query(Course).filter(Course.id == course_id, Course.user_id == user_id).first()
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course
