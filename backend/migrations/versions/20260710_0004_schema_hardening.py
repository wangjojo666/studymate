"""align schema constraints, processing state, and query indexes

Revision ID: 20260710_0004
Revises: 20260620_0003
Create Date: 2026-07-10
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260710_0004"
down_revision = "20260620_0003"
branch_labels = None
depends_on = None


_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_LEGACY_OWNER_EMAIL = "legacy-owner@invalid.local"
_LEGACY_OWNER_PASSWORD_HASH = "!disabled-legacy-owner!"


def upgrade() -> None:
    connection = op.get_bind()
    is_sqlite = connection.dialect.name == "sqlite"
    if is_sqlite:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Cannot migrate a database with existing foreign key violations: "
                f"{violations[:5]}"
            )

    _backfill_course_owners()
    _harden_courses()
    _add_document_processing_state()
    _add_chat_message_course_index()
    _make_user_email_index_unique()

    if is_sqlite:
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "Schema migration introduced foreign key violations: "
                f"{violations[:5]}"
            )
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")

    inspector = sa.inspect(connection)
    document_indexes = {item["name"] for item in inspector.get_indexes("documents")}
    if "ix_documents_processing_stage" in document_indexes:
        op.drop_index("ix_documents_processing_stage", table_name="documents")
    document_columns = {item["name"] for item in inspector.get_columns("documents")}
    with op.batch_alter_table(
        "documents",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        for column_name in ("indexed_at", "processing_progress", "processing_stage"):
            if column_name in document_columns:
                batch_op.drop_column(column_name)

    chat_indexes = {item["name"] for item in sa.inspect(connection).get_indexes("chat_messages")}
    if "ix_chat_messages_course_id" in chat_indexes:
        op.drop_index("ix_chat_messages_course_id", table_name="chat_messages")

    user_indexes = {item["name"]: item for item in sa.inspect(connection).get_indexes("users")}
    if user_indexes.get("ix_users_email", {}).get("unique"):
        op.drop_index("ix_users_email", table_name="users")
        op.create_index("ix_users_email", "users", ["email"], unique=False)

    course_inspector = sa.inspect(connection)
    course_foreign_keys = course_inspector.get_foreign_keys("courses")
    course_uniques = course_inspector.get_unique_constraints("courses")
    with op.batch_alter_table(
        "courses",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        for constraint in course_uniques:
            if set(constraint["column_names"]) == {"user_id", "name"}:
                batch_op.drop_constraint(
                    constraint["name"] or "uq_courses_user_id",
                    type_="unique",
                )
        for foreign_key in course_foreign_keys:
            if foreign_key["constrained_columns"] == ["user_id"]:
                batch_op.drop_constraint(
                    foreign_key["name"] or "fk_courses_user_id_users",
                    type_="foreignkey",
                )
        batch_op.alter_column(
            "user_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_unique_constraint("uq_courses_name", ["name"])

    op.create_index("uq_course_user_name", "courses", ["user_id", "name"], unique=True)
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def _backfill_course_owners() -> None:
    connection = op.get_bind()
    null_owner_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM courses WHERE user_id IS NULL")
    ).scalar_one()
    if not null_owner_count:
        return

    legacy_owner = connection.execute(
        sa.text("SELECT id, password_hash FROM users WHERE email = :email"),
        {"email": _LEGACY_OWNER_EMAIL},
    ).one_or_none()
    if legacy_owner is not None and legacy_owner.password_hash != _LEGACY_OWNER_PASSWORD_HASH:
        raise RuntimeError(
            "Cannot quarantine unowned legacy courses because the reserved legacy owner "
            "email is already used by a login-capable account"
        )
    if legacy_owner is None:
        result = connection.execute(
            sa.text(
                "INSERT INTO users "
                "(email, display_name, password_hash, created_at, updated_at) "
                "VALUES (:email, :display_name, :password_hash, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "email": _LEGACY_OWNER_EMAIL,
                "display_name": "Legacy data owner",
                # Deliberately not a valid password hash: this migration must not
                # create a login-capable default account.
                "password_hash": _LEGACY_OWNER_PASSWORD_HASH,
            },
        )
        owner_id = result.lastrowid
    else:
        owner_id = legacy_owner.id
    connection.execute(
        sa.text("UPDATE courses SET user_id = :owner_id WHERE user_id IS NULL"),
        {"owner_id": owner_id},
    )


def _harden_courses() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    indexes = {item["name"]: item for item in inspector.get_indexes("courses")}
    unique_constraints = inspector.get_unique_constraints("courses")
    foreign_keys = inspector.get_foreign_keys("courses")
    user_id_column = next(item for item in inspector.get_columns("courses") if item["name"] == "user_id")

    if "uq_course_user_name" in indexes:
        op.drop_index("uq_course_user_name", table_name="courses")

    has_owner_unique_constraint = any(
        set(item["column_names"]) == {"user_id", "name"} for item in unique_constraints
    )
    has_global_name_unique = any(
        item["column_names"] == ["name"] for item in unique_constraints
    )
    has_owner_foreign_key = any(
        item["constrained_columns"] == ["user_id"] and item["referred_table"] == "users"
        for item in foreign_keys
    )

    with op.batch_alter_table(
        "courses",
        recreate="always",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        if has_global_name_unique:
            global_constraint = next(
                item for item in unique_constraints if item["column_names"] == ["name"]
            )
            batch_op.drop_constraint(
                global_constraint["name"] or "uq_courses_name",
                type_="unique",
            )
        if user_id_column["nullable"]:
            batch_op.alter_column(
                "user_id",
                existing_type=sa.Integer(),
                nullable=False,
            )
        if not has_owner_foreign_key:
            batch_op.create_foreign_key(
                "fk_courses_user_id_users",
                "users",
                ["user_id"],
                ["id"],
            )
        if not has_owner_unique_constraint:
            batch_op.create_unique_constraint("uq_course_user_name", ["user_id", "name"])


def _add_document_processing_state() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {item["name"]: item for item in inspector.get_columns("documents")}

    if "processing_stage" not in columns:
        op.add_column(
            "documents",
            sa.Column("processing_stage", sa.String(length=60), nullable=True),
        )
    if "processing_progress" not in columns:
        op.add_column(
            "documents",
            sa.Column("processing_progress", sa.Integer(), nullable=True),
        )
    if "indexed_at" not in columns:
        op.add_column("documents", sa.Column("indexed_at", sa.DateTime(), nullable=True))

    connection.execute(
        sa.text(
            "UPDATE documents SET processing_stage = "
            "COALESCE(processing_stage, CASE WHEN status = 'indexed' THEN 'indexed' ELSE 'uploaded' END), "
            "processing_progress = COALESCE(processing_progress, "
            "CASE WHEN status IN ('indexed', 'empty', 'failed', 'needs_ocr', 'needs_vision') "
            "THEN 100 ELSE 0 END)"
        )
    )

    refreshed_columns = {
        item["name"]: item for item in sa.inspect(connection).get_columns("documents")
    }
    if refreshed_columns["processing_stage"]["nullable"] or refreshed_columns[
        "processing_progress"
    ]["nullable"]:
        with op.batch_alter_table(
            "documents",
            recreate="always",
            naming_convention=_NAMING_CONVENTION,
        ) as batch_op:
            if refreshed_columns["processing_stage"]["nullable"]:
                batch_op.alter_column(
                    "processing_stage",
                    existing_type=sa.String(length=60),
                    nullable=False,
                )
            if refreshed_columns["processing_progress"]["nullable"]:
                batch_op.alter_column(
                    "processing_progress",
                    existing_type=sa.Integer(),
                    nullable=False,
                )

    document_indexes = {
        item["name"] for item in sa.inspect(connection).get_indexes("documents")
    }
    if "ix_documents_processing_stage" not in document_indexes:
        op.create_index(
            "ix_documents_processing_stage",
            "documents",
            ["processing_stage"],
            unique=False,
        )


def _add_chat_message_course_index() -> None:
    indexes = {item["name"] for item in sa.inspect(op.get_bind()).get_indexes("chat_messages")}
    if "ix_chat_messages_course_id" not in indexes:
        op.create_index(
            "ix_chat_messages_course_id",
            "chat_messages",
            ["course_id"],
            unique=False,
        )


def _make_user_email_index_unique() -> None:
    indexes = {
        item["name"]: item for item in sa.inspect(op.get_bind()).get_indexes("users")
    }
    email_index = indexes.get("ix_users_email")
    if email_index and not email_index["unique"]:
        op.drop_index("ix_users_email", table_name="users")
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    elif email_index is None:
        op.create_index("ix_users_email", "users", ["email"], unique=True)
