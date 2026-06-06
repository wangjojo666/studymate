from __future__ import annotations

from pydantic import BaseModel, Field


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=12)


class PracticeRequest(BaseModel):
    count: int = Field(10, ge=1, le=30)


class OcrRequest(BaseModel):
    start_page: int = Field(1, ge=1)
    max_pages: int = Field(10, ge=1, le=50)
