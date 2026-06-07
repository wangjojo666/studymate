from __future__ import annotations

from sqlalchemy import create_engine
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

    from app.models.entities import (  # noqa: F401
        ChatMessage,
        Course,
        Document,
        DocumentChunk,
        GeneratedMaterial,
        OcrJob,
    )

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        if db.query(Course).count() == 0:
            db.add_all(
                [
                    Course(name="高等数学", description="函数、极限、导数、积分等复习资料"),
                    Course(name="C++ 程序设计", description="语法基础、面向对象、STL 与实验讲义"),
                    Course(name="大学物理", description="力学、电磁学、热学等课程资料"),
                ]
            )
            db.commit()
