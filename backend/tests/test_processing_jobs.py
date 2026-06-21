from __future__ import annotations


def test_upload_creates_processing_jobs(client, auth_helpers):
    course = auth_helpers.create_course("Processing Jobs")
    uploaded = auth_helpers.upload_text_file(course["id"], "runtime polymorphism virtual function notes")
    document = auth_helpers.wait_document_done(course["id"], uploaded["id"])

    response = client.get(f"/api/courses/{course['id']}/jobs")

    assert response.status_code == 200, response.text
    jobs = response.json()
    assert any(job["job_type"] == "document_parse" and job["status"] == "completed" for job in jobs)
    assert any(job["job_type"] == "knowledge_sync" and job["status"] == "completed" for job in jobs)
    detail_response = client.get(f"/api/courses/{course['id']}")
    assert detail_response.status_code == 200, detail_response.text
    latest_job = next(item for item in detail_response.json()["documents"] if item["id"] == document["id"])["latest_job"]
    assert latest_job["job_type"] in {"document_parse", "knowledge_sync"}


def test_processing_job_retry_and_cancel(client, auth_helpers):
    course = auth_helpers.create_course("Retry Processing Job")
    reindex_job_id = _create_processing_job(course["id"], "reindex", status="failed")

    retry_response = client.post(f"/api/courses/{course['id']}/jobs/{reindex_job_id}/retry")

    assert retry_response.status_code == 200, retry_response.text
    retry_payload = retry_response.json()
    assert retry_payload["job"]["status"] == "completed"
    assert retry_payload["scope"] == "course"

    cancel_job_id = _create_processing_job(course["id"], "knowledge_sync", status="queued")
    cancel_response = client.post(f"/api/courses/{course['id']}/jobs/{cancel_job_id}/cancel")

    assert cancel_response.status_code == 200, cancel_response.text
    assert cancel_response.json()["status"] == "cancelled"


def test_processing_jobs_are_isolated_by_course_owner(client, auth_helpers):
    course = auth_helpers.create_course("Private Processing Jobs")
    job_id = _create_processing_job(course["id"], "reindex", status="failed")
    other_user = auth_helpers.create_user_and_login()

    list_response = client.get(f"/api/courses/{course['id']}/jobs", headers=other_user["headers"])
    retry_response = client.post(
        f"/api/courses/{course['id']}/jobs/{job_id}/retry",
        headers=other_user["headers"],
    )
    cancel_response = client.post(
        f"/api/courses/{course['id']}/jobs/{job_id}/cancel",
        headers=other_user["headers"],
    )

    assert list_response.status_code == 404
    assert retry_response.status_code == 404
    assert cancel_response.status_code == 404


def _create_processing_job(course_id: int, job_type: str, status: str) -> int:
    from app.database import SessionLocal
    from app.models.entities import ProcessingJob

    with SessionLocal() as db:
        job = ProcessingJob(
            course_id=course_id,
            document_id=None,
            job_type=job_type,
            status=status,
            stage=status,
            progress=100 if status in {"failed", "cancelled", "completed"} else 0,
            error_message="pytest seeded job",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id
