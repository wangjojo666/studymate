from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Course
from app.schemas import CppAnalysisRequest
from app.services.cpp_service import analyze_cpp_code


router = APIRouter(prefix="/courses/{course_id}/cpp", tags=["cpp"])


@router.post("/analyze")
def analyze_cpp(course_id: int, payload: CppAnalysisRequest, db: Session = Depends(get_db)) -> dict:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    if not payload.problem_text.strip() and not payload.code_text.strip() and not payload.user_code.strip():
        raise HTTPException(status_code=400, detail="请填写题目、参考代码或用户代码。")
    return analyze_cpp_code(
        course_name=course.name,
        problem_text=payload.problem_text,
        code_text=payload.code_text,
        user_code=payload.user_code,
    )
