from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_empty_database_upgrades_to_drift_free_head_with_enforced_foreign_keys(
    tmp_path: Path,
):
    database_path = tmp_path / "empty.db"
    _run_alembic(database_path, "upgrade", "head")
    check = _run_alembic(database_path, "check")
    assert "No new upgrade operations detected" in check.stdout

    engine = sa.create_engine(_database_url(database_path), future=True)
    inspector = sa.inspect(engine)
    course_columns = {item["name"]: item for item in inspector.get_columns("courses")}
    assert course_columns["user_id"]["nullable"] is False
    assert any(
        item["constrained_columns"] == ["user_id"] and item["referred_table"] == "users"
        for item in inspector.get_foreign_keys("courses")
    )
    course_uniques = {
        tuple(item["column_names"]) for item in inspector.get_unique_constraints("courses")
    }
    assert ("user_id", "name") in course_uniques
    assert ("name",) not in course_uniques

    document_columns = {item["name"] for item in inspector.get_columns("documents")}
    assert {"processing_stage", "processing_progress", "indexed_at"} <= document_columns
    chat_indexes = {item["name"] for item in inspector.get_indexes("chat_messages")}
    assert "ix_chat_messages_course_id" in chat_indexes

    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        with pytest.raises(IntegrityError):
            connection.execute(
                sa.text(
                    "INSERT INTO courses "
                    "(user_id, name, description, created_at, updated_at) "
                    "VALUES (999999, 'orphan', '', :now, :now)"
                ),
                {"now": datetime.now()},
            )
    engine.dispose()

    result = _run_python(
        database_path,
        "from sqlalchemy import text; "
        "from app.database import engine; "
        "c = engine.connect(); "
        "assert c.execute(text('PRAGMA foreign_keys')).scalar_one() == 1; "
        "c.close(); engine.dispose()",
    )
    assert result.returncode == 0


def test_upgrade_from_previous_head_preserves_data_and_repairs_course_constraints(
    tmp_path: Path,
):
    database_path = tmp_path / "old-head.db"
    _run_alembic(database_path, "upgrade", "20260620_0003")
    engine = sa.create_engine(_database_url(database_path), future=True)
    now = datetime.now()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(id, email, display_name, password_hash, created_at, updated_at) VALUES "
                "(1, 'first@example.test', 'First', '!disabled!', :now, :now), "
                "(2, 'second@example.test', 'Second', '!disabled!', :now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO courses "
                "(id, user_id, name, description, created_at, updated_at) "
                "VALUES (1, NULL, 'Legacy course', 'preserve me', :now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO documents "
                "(id, course_id, original_filename, stored_filename, file_type, file_path, "
                "status, page_count, chunk_count, error_message, created_at, updated_at) "
                "VALUES (1, 1, 'legacy.txt', 'legacy.txt', 'txt', '/legacy.txt', "
                "'indexed', 1, 1, '', :now, :now)"
            ),
            {"now": now},
        )
    engine.dispose()

    _run_alembic(database_path, "upgrade", "head")
    engine = sa.create_engine(_database_url(database_path), future=True)
    with engine.connect() as connection:
        owner_id = connection.execute(
            sa.text("SELECT user_id FROM courses WHERE id = 1")
        ).scalar_one()
        assert owner_id not in {1, 2}
        legacy_owner = connection.execute(
            sa.text("SELECT email, password_hash FROM users WHERE id = :owner_id"),
            {"owner_id": owner_id},
        ).one()
        assert legacy_owner == (
            "legacy-owner@invalid.local",
            "!disabled-legacy-owner!",
        )
        document_state = connection.execute(
            sa.text("SELECT processing_stage, processing_progress FROM documents WHERE id = 1")
        ).one()
        assert document_state == ("indexed", 100)

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO courses "
                "(user_id, name, description, created_at, updated_at) "
                "VALUES (2, 'Legacy course', '', :now, :now)"
            ),
            {"now": now},
        )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO courses "
                    "(user_id, name, description, created_at, updated_at) "
                    "VALUES (:owner_id, 'Legacy course', '', :now, :now)"
                ),
                {"owner_id": owner_id, "now": now},
            )
    engine.dispose()


def test_unversioned_known_legacy_schema_is_bridged_then_migrated(tmp_path: Path):
    database_path = tmp_path / "unversioned-legacy.db"
    _run_alembic(database_path, "upgrade", "20260620_0003")
    engine = sa.create_engine(_database_url(database_path), future=True)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE alembic_version"))
    engine.dispose()

    _run_python(
        database_path,
        "from app.database import init_database; init_database()",
    )

    engine = sa.create_engine(_database_url(database_path), future=True)
    with engine.connect() as connection:
        revision = connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        assert revision == "20260710_0004"
    engine.dispose()
    _run_alembic(database_path, "check")


def test_legacy_owner_quarantine_fails_when_reserved_email_is_login_capable(
    tmp_path: Path,
):
    database_path = tmp_path / "reserved-owner.db"
    _run_alembic(database_path, "upgrade", "20260620_0003")
    engine = sa.create_engine(_database_url(database_path), future=True)
    now = datetime.now()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users "
                "(id, email, display_name, password_hash, created_at, updated_at) "
                "VALUES (1, 'legacy-owner@invalid.local', 'Existing user', "
                "'login-capable-hash', :now, :now)"
            ),
            {"now": now},
        )
        connection.execute(
            sa.text(
                "INSERT INTO courses "
                "(id, user_id, name, description, created_at, updated_at) "
                "VALUES (1, NULL, 'Unowned course', '', :now, :now)"
            ),
            {"now": now},
        )
    engine.dispose()

    result = _run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        database_path,
        expect_success=False,
    )
    assert result.returncode != 0
    assert "reserved legacy owner email" in (result.stdout + result.stderr)


def _run_alembic(database_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "alembic", *arguments]
    return _run(command, database_path)


def _run_python(
    database_path: Path,
    source: str,
) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-c", source], database_path)


def _run(
    command: list[str],
    database_path: Path,
    *,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    assert database_path.is_absolute()
    assert BACKEND_DIR not in database_path.parents
    environment = os.environ.copy()
    environment.update(
        {
            "APP_ENV": "development",
            "AUTH_SECRET_KEY": "",
            "ENABLE_DEMO_USER": "false",
            "DATABASE_URL": _database_url(database_path),
            "STORAGE_DIR": str(database_path.parent / "storage"),
            "UPLOAD_DIR": str(database_path.parent / "storage" / "uploads"),
            "CHROMA_DIR": str(database_path.parent / "storage" / "chroma"),
        }
    )
    result = subprocess.run(
        command,
        cwd=BACKEND_DIR,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    if expect_success:
        assert result.returncode == 0, (
            f"command failed: {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _database_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"
