from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Course
from app.schemas import AskRequest, PracticeRequest
from app.services.rag_service import answer_question, generate_outline, generate_practice


router = APIRouter(prefix="/courses/{course_id}", tags=["assistant"])


@router.post("/ask")
def ask_course(course_id: int, payload: AskRequest, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    return answer_question(db, course_id, payload.question, payload.top_k)


@router.post("/review-outline")
def create_review_outline(course_id: int, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    return generate_outline(db, course_id)


@router.post("/practice")
def create_practice(course_id: int, payload: PracticeRequest, db: Session = Depends(get_db)) -> dict:
    _ensure_course(db, course_id)
    return generate_practice(db, course_id, payload.count)


def _ensure_course(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course
