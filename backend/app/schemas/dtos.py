from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=12)


class PracticeRequest(BaseModel):
    count: int = Field(10, ge=1, le=30)
    difficulty: str = Field("basic", pattern="^(basic|advanced|exam|mistake)$")
    knowledge_point_id: int | None = None


class OcrRequest(BaseModel):
    start_page: int = Field(1, ge=1)
    max_pages: int = Field(10, ge=1, le=20)
    mode: str = Field("fast", pattern="^(fast|full)$")


class AttemptCreate(BaseModel):
    knowledge_point_id: int | None = None
    question_text: str = Field(..., min_length=1, max_length=3000)
    user_answer: str = Field("", max_length=3000)
    correct_answer: str = Field("", max_length=3000)
    is_correct: bool = False
    error_reason: str = Field("", max_length=500)
    difficulty: str = Field("basic", pattern="^(basic|advanced|exam|mistake)$")


class ReviewPlanRequest(BaseModel):
    exam_date: date
    daily_minutes: int = Field(90, ge=20, le=480)
    goals: str = Field("", max_length=500)


class ReviewTaskUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending|planned|done|skipped)$")


class CppAnalysisRequest(BaseModel):
    problem_text: str = Field("", max_length=4000)
    code_text: str = Field("", max_length=12000)
    user_code: str = Field("", max_length=12000)
