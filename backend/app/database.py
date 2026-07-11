from __future__ import annotations

import logging
import sqlite3

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import BASE_DIR, settings
from app.utils.time import utc_now

logger = logging.getLogger(__name__)

connect_args = {}
if settings.database_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.database_url, connect_args=connect_args, future=True)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(
        dbapi_connection: sqlite3.Connection,
        _connection_record,
    ) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            enabled = cursor.execute("PRAGMA foreign_keys").fetchone()
        finally:
            cursor.close()
        if not enabled or enabled[0] != 1:
            raise RuntimeError("SQLite foreign key enforcement could not be enabled")


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


_LEGACY_BASE_TABLES = {
    "courses",
    "documents",
    "chat_messages",
    "document_chunks",
    "generated_materials",
    "knowledge_points",
    "ocr_jobs",
    "question_attempts",
    "review_tasks",
    "chunk_knowledge_points",
    "user_knowledge_status",
}


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_database() -> None:
    """Prepare storage and bring the database to the Alembic head revision."""

    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)

    migrate_database()
    verify_database_state()

    from app.models.entities import Course

    with SessionLocal() as db:
        if settings.enable_demo_user:
            demo_user = _get_or_create_demo_user(db)
            _claim_legacy_user_rows(db, demo_user.id)
            if db.query(Course).filter(Course.user_id == demo_user.id).count() == 0:
                db.add_all(
                    [
                        Course(
                            user_id=demo_user.id,
                            name="高等数学",
                            description="函数、极限、导数、积分等复习资料",
                        ),
                        Course(
                            user_id=demo_user.id,
                            name="C++ 程序设计",
                            description="语法基础、面向对象、STL 与实验讲义",
                        ),
                        Course(
                            user_id=demo_user.id,
                            name="大学物理",
                            description="力学、电磁学、热学等课程资料",
                        ),
                    ]
                )
                db.commit()
        _mark_interrupted_ocr_jobs(db)


def migrate_database() -> None:
    """Run schema changes exclusively through Alembic.

    Databases created by older StudyMate releases used ``create_all`` and have
    no Alembic revision. A narrow compatibility bridge stamps only schemas that
    match a known historical shape; the following Alembic revisions then do all
    structural reconciliation.
    """

    alembic_config = _alembic_config()
    legacy_revision = _detect_unversioned_legacy_revision()
    if legacy_revision is not None:
        logger.warning(
            "Detected an unversioned legacy StudyMate schema; stamping %s before migration",
            legacy_revision,
        )
        command.stamp(alembic_config, legacy_revision)
    command.upgrade(alembic_config, "head")


def verify_database_state() -> None:
    """Fail startup when migrations or SQLite FK enforcement are incomplete."""

    alembic_config = _alembic_config()
    expected_head = ScriptDirectory.from_config(alembic_config).get_current_head()
    with engine.connect() as connection:
        if connection.dialect.name == "sqlite":
            enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
            if enabled != 1:
                raise RuntimeError("SQLite foreign key enforcement is disabled")
        current_revision = _current_revision(connection)
    if current_revision != expected_head:
        raise RuntimeError(
            f"Database revision {current_revision!r} does not match Alembic head {expected_head!r}"
        )


def _alembic_config() -> Config:
    config = Config(str(BASE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BASE_DIR / "migrations"))
    # ConfigParser treats percent signs as interpolation markers.
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
    return config


def _current_revision(connection: Connection) -> str | None:
    if "alembic_version" not in inspect(connection).get_table_names():
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()


def _detect_unversioned_legacy_revision() -> str | None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    application_tables = table_names - {"alembic_version", "sqlite_sequence"}
    if not application_tables:
        return None

    with engine.connect() as connection:
        if _current_revision(connection) is not None:
            return None

    missing_base_tables = _LEGACY_BASE_TABLES - application_tables
    if missing_base_tables:
        missing = ", ".join(sorted(missing_base_tables))
        raise RuntimeError(
            "Refusing to stamp an unknown partial legacy schema; "
            f"missing expected tables: {missing}"
        )

    course_columns = {column["name"] for column in inspector.get_columns("courses")}
    has_users_table = "users" in table_names
    has_course_owner = "user_id" in course_columns
    if has_users_table != has_course_owner:
        raise RuntimeError(
            "Refusing to stamp an inconsistent legacy schema: users table and "
            "courses.user_id must either both exist or both be absent"
        )
    if not has_users_table:
        return "20260608_0001"
    if "processing_jobs" not in table_names:
        return "20260610_0002"
    return "20260620_0003"


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
        job.finished_at = utc_now()
        job.error_message = "OCR 任务因服务重启已中断，请使用快速索引模式重新开始。"
        if document:
            document.status = "indexed" if document.chunk_count else "needs_ocr"
            document.error_message = job.error_message
    db.commit()
