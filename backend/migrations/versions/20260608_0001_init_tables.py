"""init tables

Revision ID: 20260608_0001
Revises:
Create Date: 2026-06-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260608_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_asked_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_courses_id"), "courses", ["id"], unique=False)
    op.create_index(op.f("ix_courses_name"), "courses", ["name"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_documents_course_id"), "documents", ["course_id"], unique=False)
    op.create_index(op.f("ix_documents_id"), "documents", ["id"], unique=False)
    op.create_index(op.f("ix_documents_status"), "documents", ["status"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_id"), "chat_messages", ["id"], unique=False)

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_weights", sa.Text(), nullable=False),
        sa.Column("vector_norm", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_course_id"), "document_chunks", ["course_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_chunks_id"), "document_chunks", ["id"], unique=False)

    op.create_table(
        "generated_materials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generated_materials_course_id"), "generated_materials", ["course_id"], unique=False)
    op.create_index(op.f("ix_generated_materials_id"), "generated_materials", ["id"], unique=False)
    op.create_index(op.f("ix_generated_materials_kind"), "generated_materials", ["kind"], unique=False)

    op.create_table(
        "knowledge_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("source_document_id", sa.Integer(), nullable=True),
        sa.Column("source_page", sa.Integer(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["knowledge_points.id"]),
        sa.ForeignKeyConstraint(["source_document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", "name", name="uq_knowledge_point_course_name"),
    )
    op.create_index(op.f("ix_knowledge_points_course_id"), "knowledge_points", ["course_id"], unique=False)
    op.create_index(op.f("ix_knowledge_points_id"), "knowledge_points", ["id"], unique=False)
    op.create_index(op.f("ix_knowledge_points_name"), "knowledge_points", ["name"], unique=False)

    op.create_table(
        "ocr_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("total_pages", sa.Integer(), nullable=False),
        sa.Column("current_page", sa.Integer(), nullable=False),
        sa.Column("processed_pages", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ocr_jobs_course_id"), "ocr_jobs", ["course_id"], unique=False)
    op.create_index(op.f("ix_ocr_jobs_document_id"), "ocr_jobs", ["document_id"], unique=False)
    op.create_index(op.f("ix_ocr_jobs_id"), "ocr_jobs", ["id"], unique=False)
    op.create_index(op.f("ix_ocr_jobs_status"), "ocr_jobs", ["status"], unique=False)

    op.create_table(
        "question_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("user_answer", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("error_reason", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_question_attempts_course_id"), "question_attempts", ["course_id"], unique=False)
    op.create_index(op.f("ix_question_attempts_id"), "question_attempts", ["id"], unique=False)
    op.create_index(op.f("ix_question_attempts_knowledge_point_id"), "question_attempts", ["knowledge_point_id"], unique=False)
    op.create_index(op.f("ix_question_attempts_user_id"), "question_attempts", ["user_id"], unique=False)

    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=True),
        sa.Column("task_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("deadline", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_review_tasks_course_id"), "review_tasks", ["course_id"], unique=False)
    op.create_index(op.f("ix_review_tasks_id"), "review_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_review_tasks_knowledge_point_id"), "review_tasks", ["knowledge_point_id"], unique=False)
    op.create_index(op.f("ix_review_tasks_status"), "review_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_review_tasks_task_type"), "review_tasks", ["task_type"], unique=False)
    op.create_index(op.f("ix_review_tasks_user_id"), "review_tasks", ["user_id"], unique=False)

    op.create_table(
        "chunk_knowledge_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["document_chunks.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chunk_id", "knowledge_point_id", name="uq_chunk_knowledge_point"),
    )
    op.create_index(op.f("ix_chunk_knowledge_points_chunk_id"), "chunk_knowledge_points", ["chunk_id"], unique=False)
    op.create_index(op.f("ix_chunk_knowledge_points_course_id"), "chunk_knowledge_points", ["course_id"], unique=False)
    op.create_index(op.f("ix_chunk_knowledge_points_id"), "chunk_knowledge_points", ["id"], unique=False)
    op.create_index(op.f("ix_chunk_knowledge_points_knowledge_point_id"), "chunk_knowledge_points", ["knowledge_point_id"], unique=False)

    op.create_table(
        "user_knowledge_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(length=80), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_point_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("wrong_count", sa.Integer(), nullable=False),
        sa.Column("review_count", sa.Integer(), nullable=False),
        sa.Column("last_review_time", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["knowledge_point_id"], ["knowledge_points.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "course_id", "knowledge_point_id", name="uq_user_course_knowledge_status"),
    )
    op.create_index(op.f("ix_user_knowledge_status_course_id"), "user_knowledge_status", ["course_id"], unique=False)
    op.create_index(op.f("ix_user_knowledge_status_id"), "user_knowledge_status", ["id"], unique=False)
    op.create_index(op.f("ix_user_knowledge_status_knowledge_point_id"), "user_knowledge_status", ["knowledge_point_id"], unique=False)
    op.create_index(op.f("ix_user_knowledge_status_user_id"), "user_knowledge_status", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_knowledge_status_user_id"), table_name="user_knowledge_status")
    op.drop_index(op.f("ix_user_knowledge_status_knowledge_point_id"), table_name="user_knowledge_status")
    op.drop_index(op.f("ix_user_knowledge_status_id"), table_name="user_knowledge_status")
    op.drop_index(op.f("ix_user_knowledge_status_course_id"), table_name="user_knowledge_status")
    op.drop_table("user_knowledge_status")
    op.drop_index(op.f("ix_chunk_knowledge_points_knowledge_point_id"), table_name="chunk_knowledge_points")
    op.drop_index(op.f("ix_chunk_knowledge_points_id"), table_name="chunk_knowledge_points")
    op.drop_index(op.f("ix_chunk_knowledge_points_course_id"), table_name="chunk_knowledge_points")
    op.drop_index(op.f("ix_chunk_knowledge_points_chunk_id"), table_name="chunk_knowledge_points")
    op.drop_table("chunk_knowledge_points")
    op.drop_index(op.f("ix_review_tasks_user_id"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_task_type"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_status"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_knowledge_point_id"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_id"), table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_course_id"), table_name="review_tasks")
    op.drop_table("review_tasks")
    op.drop_index(op.f("ix_question_attempts_user_id"), table_name="question_attempts")
    op.drop_index(op.f("ix_question_attempts_knowledge_point_id"), table_name="question_attempts")
    op.drop_index(op.f("ix_question_attempts_id"), table_name="question_attempts")
    op.drop_index(op.f("ix_question_attempts_course_id"), table_name="question_attempts")
    op.drop_table("question_attempts")
    op.drop_index(op.f("ix_ocr_jobs_status"), table_name="ocr_jobs")
    op.drop_index(op.f("ix_ocr_jobs_id"), table_name="ocr_jobs")
    op.drop_index(op.f("ix_ocr_jobs_document_id"), table_name="ocr_jobs")
    op.drop_index(op.f("ix_ocr_jobs_course_id"), table_name="ocr_jobs")
    op.drop_table("ocr_jobs")
    op.drop_index(op.f("ix_knowledge_points_name"), table_name="knowledge_points")
    op.drop_index(op.f("ix_knowledge_points_id"), table_name="knowledge_points")
    op.drop_index(op.f("ix_knowledge_points_course_id"), table_name="knowledge_points")
    op.drop_table("knowledge_points")
    op.drop_index(op.f("ix_generated_materials_kind"), table_name="generated_materials")
    op.drop_index(op.f("ix_generated_materials_id"), table_name="generated_materials")
    op.drop_index(op.f("ix_generated_materials_course_id"), table_name="generated_materials")
    op.drop_table("generated_materials")
    op.drop_index(op.f("ix_document_chunks_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_index(op.f("ix_document_chunks_course_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index(op.f("ix_chat_messages_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_course_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_courses_name"), table_name="courses")
    op.drop_index(op.f("ix_courses_id"), table_name="courses")
    op.drop_table("courses")
