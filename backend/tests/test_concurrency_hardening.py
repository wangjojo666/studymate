from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def test_same_name_uploads_use_distinct_uuid_paths(client, auth_helpers):
    course = auth_helpers.create_course("Concurrent Upload Names")

    def upload(content: str):
        return client.post(
            f"/api/courses/{course['id']}/documents",
            files={"file": ("same-name.txt", content.encode("utf-8"), "text/plain")},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(
            pool.map(upload, ["first concurrent payload", "second concurrent payload"])
        )

    assert all(response.status_code == 200 for response in responses), [
        response.text for response in responses
    ]
    document_ids = [response.json()["id"] for response in responses]

    from app.database import SessionLocal
    from app.models.entities import Document

    with SessionLocal() as db:
        documents = db.query(Document).filter(Document.id.in_(document_ids)).all()
        assert len(documents) == 2
        assert len({document.stored_filename for document in documents}) == 2
        assert all(len(Path(document.stored_filename).stem) == 32 for document in documents)
        contents = {Path(document.file_path).read_text(encoding="utf-8") for document in documents}
    assert contents == {"first concurrent payload", "second concurrent payload"}


def test_repeated_done_transition_increments_mastery_once(client, auth_helpers):
    from datetime import date, timedelta

    course = auth_helpers.create_course("Idempotent Review Completion")
    profile = client.get(f"/api/courses/{course['id']}/learning/profile").json()
    point_id = profile["knowledge_points"][0]["id"]
    plan_response = client.post(
        f"/api/courses/{course['id']}/learning/review-plan",
        json={
            "exam_date": (date.today() + timedelta(days=3)).isoformat(),
            "daily_minutes": 45,
            "goals": profile["knowledge_points"][0]["name"],
        },
    )
    assert plan_response.status_code == 200, plan_response.text
    task = next(
        item for item in plan_response.json()["tasks"] if item["knowledge_point_id"] == point_id
    )

    from app.database import SessionLocal
    from app.models.entities import UserKnowledgeStatus

    with SessionLocal() as db:
        before = (
            db.query(UserKnowledgeStatus)
            .filter(
                UserKnowledgeStatus.course_id == course["id"],
                UserKnowledgeStatus.knowledge_point_id == point_id,
            )
            .one()
        )
        before_score = before.mastery_score
        before_reviews = before.review_count

    first = client.patch(
        f"/api/courses/{course['id']}/learning/tasks/{task['id']}",
        json={"status": "done"},
    )
    second = client.patch(
        f"/api/courses/{course['id']}/learning/tasks/{task['id']}",
        json={"status": "done"},
    )
    assert first.status_code == second.status_code == 200

    with SessionLocal() as db:
        after = (
            db.query(UserKnowledgeStatus)
            .filter(
                UserKnowledgeStatus.course_id == course["id"],
                UserKnowledgeStatus.knowledge_point_id == point_id,
            )
            .one()
        )
        assert after.mastery_score == min(100.0, before_score + 6.0)
        assert after.review_count == before_reviews + 1


def test_cancelled_or_deleted_job_cannot_be_completed(client, auth_helpers):
    course = auth_helpers.create_course("Conditional Job Completion")

    from app.database import SessionLocal
    from app.models.entities import ProcessingJob
    from app.services.processing_jobs import cancel_processing_job, complete_processing_job

    with SessionLocal() as db:
        job = ProcessingJob(
            course_id=course["id"],
            document_id=None,
            job_type="reindex",
            status="running",
            stage="running",
        )
        db.add(job)
        db.commit()
        job_id = job.id

    worker_db = SessionLocal()
    stale_job = worker_db.get(ProcessingJob, job_id)
    worker_db.expunge(stale_job)
    worker_db.rollback()
    try:
        with SessionLocal() as db:
            cancel_job = db.get(ProcessingJob, job_id)
            cancel_processing_job(db, cancel_job)
            db.commit()
        assert complete_processing_job(worker_db, stale_job) is False
        worker_db.rollback()
        with SessionLocal() as db:
            assert db.get(ProcessingJob, job_id).status == "cancelled"

        with SessionLocal() as db:
            db.query(ProcessingJob).filter(ProcessingJob.id == job_id).delete()
            db.commit()
        assert complete_processing_job(worker_db, stale_job) is False
        worker_db.rollback()
    finally:
        worker_db.close()


def test_retry_claim_is_conditional(client, auth_helpers):
    course = auth_helpers.create_course("Conditional Job Retry")

    from app.database import SessionLocal
    from app.models.entities import ProcessingJob
    from app.services.processing_jobs import reset_failed_processing_job

    with SessionLocal() as db:
        job = ProcessingJob(
            course_id=course["id"],
            document_id=None,
            job_type="reindex",
            status="failed",
            stage="failed",
        )
        db.add(job)
        db.commit()
        job_id = job.id

    with SessionLocal() as db:
        first = db.get(ProcessingJob, job_id)
        assert reset_failed_processing_job(db, first) is True
        db.commit()

    with SessionLocal() as db:
        stale = ProcessingJob(
            id=job_id, course_id=course["id"], job_type="reindex", status="failed"
        )
        assert reset_failed_processing_job(db, stale) is False
        db.rollback()


def test_course_delete_removes_uploaded_files(client, auth_helpers):
    course = auth_helpers.create_course("Course Physical Cleanup")
    uploaded = auth_helpers.upload_text_file(course["id"], "course cleanup physical file")
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    from app.database import SessionLocal
    from app.models.entities import Document

    with SessionLocal() as db:
        file_path = Path(db.get(Document, uploaded["id"]).file_path)
    assert file_path.exists()

    response = client.delete(f"/api/courses/{course['id']}")

    assert response.status_code == 200, response.text
    assert not file_path.exists()
