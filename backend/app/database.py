from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings


connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    from app.models.entities import (  # noqa: F401
        ChatMessage,
        ChunkKnowledgePoint,
        Course,
        Document,
        DocumentChunk,
        GeneratedMaterial,
        KnowledgePoint,
        OcrJob,
        QuestionAttempt,
        ReviewTask,
        User,
        UserKnowledgeStatus,
    )

    Base.metadata.create_all(bind=engine)
    _ensure_legacy_schema()

    with SessionLocal() as db:
        demo_user = _get_or_create_demo_user(db)
        _claim_legacy_user_rows(db, demo_user.id)
        _mark_interrupted_ocr_jobs(db)
        if db.query(Course).count() == 0:
            db.add_all(
                [
                    Course(user_id=demo_user.id, name="高等数学", description="函数、极限、导数、积分等复习资料"),
                    Course(user_id=demo_user.id, name="C++ 程序设计", description="语法基础、面向对象、STL 与实验讲义"),
                    Course(user_id=demo_user.id, name="大学物理", description="力学、电磁学、热学等课程资料"),
                ]
            )
            db.commit()
        else:
            db.query(Course).filter(Course.user_id.is_(None)).update(
                {Course.user_id: demo_user.id},
                synchronize_session=False,
            )
            db.commit()


def _ensure_legacy_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "courses" not in inspector.get_table_names():
        return
    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    document_columns = (
        {column["name"] for column in inspector.get_columns("documents")}
        if "documents" in inspector.get_table_names()
        else set()
    )
    with engine.begin() as connection:
        if "user_id" not in course_columns:
            connection.execute(text("ALTER TABLE courses ADD COLUMN user_id INTEGER"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_courses_user_id ON courses (user_id)"))
        if "documents" in inspector.get_table_names():
            if "processing_stage" not in document_columns:
                connection.execute(text("ALTER TABLE documents ADD COLUMN processing_stage VARCHAR(60) DEFAULT 'indexed'"))
            if "processing_progress" not in document_columns:
                connection.execute(text("ALTER TABLE documents ADD COLUMN processing_progress INTEGER DEFAULT 100"))
            if "indexed_at" not in document_columns:
                connection.execute(text("ALTER TABLE documents ADD COLUMN indexed_at DATETIME"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_processing_stage ON documents (processing_stage)"))


def _get_or_create_demo_user(db: Session):
    from app.models.entities import User
    from app.services.auth_service import hash_password, normalize_email

    email = normalize_email(settings.demo_user_email)
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(
        email=email,
        display_name="Demo User",
        password_hash=hash_password(settings.demo_user_password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _claim_legacy_user_rows(db: Session, demo_user_id: int) -> None:
    from app.models.entities import QuestionAttempt, ReviewTask, UserKnowledgeStatus

    for model in (QuestionAttempt, ReviewTask, UserKnowledgeStatus):
        db.query(model).filter(model.user_id == "demo-user").update(
            {model.user_id: str(demo_user_id)},
            synchronize_session=False,
        )
    db.commit()


def _mark_interrupted_ocr_jobs(db: Session) -> None:
    from app.models.entities import Document, OcrJob

    jobs = db.query(OcrJob).filter(OcrJob.status.in_(("queued", "running"))).all()
    if not jobs:
        return
    for job in jobs:
        document = db.get(Document, job.document_id)
        job.status = "failed"
        job.finished_at = datetime.utcnow()
        job.error_message = "OCR 任务因服务重启已中断，请使用快速索引模式重新开始。"
        if document:
            document.status = "indexed" if document.chunk_count else "needs_ocr"
            document.error_message = job.error_message
    db.commit()
