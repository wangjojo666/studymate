from __future__ import annotations

import json


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
    assert "已标记取消" in cancel_response.json()["error_message"]
    assert "不能强制中断" in cancel_response.json()["error_message"]


def test_recover_interrupted_processing_jobs_marks_active_work_failed(client, auth_helpers):
    course = auth_helpers.create_course("Interrupted Jobs")
    document_id = _create_document(course["id"], status="parsing", file_type="txt")
    pdf_document_id = _create_document(course["id"], status="ocr_processing", file_type="pdf")
    processing_job_id = _create_processing_job(course["id"], "document_parse", status="running", document_id=document_id)
    ocr_job_id = _create_ocr_job(course["id"], pdf_document_id, status="queued")

    from app.database import SessionLocal
    from app.models.entities import Document, OcrJob, ProcessingJob
    from app.services.processing_jobs import recover_interrupted_processing_jobs

    with SessionLocal() as db:
        recovered = recover_interrupted_processing_jobs(db)
        db.commit()

        processing_job = db.get(ProcessingJob, processing_job_id)
        document = db.get(Document, document_id)
        ocr_job = db.get(OcrJob, ocr_job_id)
        pdf_document = db.get(Document, pdf_document_id)

        assert recovered >= 2
        assert processing_job.status == "failed"
        assert processing_job.stage == "interrupted"
        assert "不会自动恢复" in processing_job.error_message
        assert document.status == "failed"
        assert document.processing_stage == "interrupted"
        assert ocr_job.status == "failed"
        assert "不会自动恢复" in ocr_job.error_message
        assert pdf_document.status == "needs_ocr"


def test_retry_document_parse_replaces_chunks_without_duplicates(client, auth_helpers):
    course = auth_helpers.create_course("Retry Parse No Duplicates")
    uploaded = auth_helpers.upload_text_file(course["id"], "virtual virtual override polymorphism")
    auth_helpers.wait_document_done(course["id"], uploaded["id"])
    before_count = _count_document_chunks(uploaded["id"])
    retry_job_id = _create_processing_job(
        course["id"],
        "document_parse",
        status="failed",
        document_id=uploaded["id"],
    )

    response = client.post(f"/api/courses/{course['id']}/jobs/{retry_job_id}/retry")

    assert response.status_code == 200, response.text
    auth_helpers.wait_document_done(course["id"], uploaded["id"])
    assert _count_document_chunks(uploaded["id"]) == before_count


def test_retry_ocr_rejects_when_ocr_job_already_active(client, auth_helpers):
    course = auth_helpers.create_course("Retry OCR Active")
    document_id = _create_document(course["id"], status="needs_ocr", file_type="pdf")
    processing_job_id = _create_processing_job(course["id"], "ocr", status="failed", document_id=document_id)
    _create_ocr_job(course["id"], document_id, status="running")

    response = client.post(f"/api/courses/{course['id']}/jobs/{processing_job_id}/retry")

    assert response.status_code == 409
    assert "已有 OCR 任务正在运行" in response.json()["detail"]


def test_delete_document_removes_processing_and_ocr_jobs(client, auth_helpers):
    course = auth_helpers.create_course("Delete Document Jobs")
    uploaded = auth_helpers.upload_text_file(course["id"], "delete cleanup chunks and jobs")
    auth_helpers.wait_document_done(course["id"], uploaded["id"])
    _create_processing_job(course["id"], "document_parse", status="failed", document_id=uploaded["id"])
    _create_ocr_job(course["id"], uploaded["id"], status="failed")

    response = client.delete(f"/api/courses/{course['id']}/documents/{uploaded['id']}")

    assert response.status_code == 200, response.text
    assert _count_document_processing_jobs(uploaded["id"]) == 0
    assert _count_ocr_jobs(uploaded["id"]) == 0
    assert _count_document_chunks(uploaded["id"]) == 0


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


def _create_processing_job(
    course_id: int,
    job_type: str,
    status: str,
    document_id: int | None = None,
    metadata: dict | None = None,
) -> int:
    from app.database import SessionLocal
    from app.models.entities import ProcessingJob

    with SessionLocal() as db:
        job = ProcessingJob(
            course_id=course_id,
            document_id=document_id,
            job_type=job_type,
            status=status,
            stage=status,
            progress=100 if status in {"failed", "cancelled", "completed"} else 0,
            error_message="pytest seeded job",
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def _create_document(course_id: int, status: str, file_type: str) -> int:
    from app.database import SessionLocal
    from app.models.entities import Document

    with SessionLocal() as db:
        document = Document(
            course_id=course_id,
            original_filename=f"seeded.{file_type}",
            stored_filename=f"seeded.{file_type}",
            file_type=file_type,
            file_path=f"/tmp/seeded.{file_type}",
            status=status,
            processing_stage=status,
            processing_progress=5,
            error_message="pytest seeded document",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document.id


def _create_ocr_job(course_id: int, document_id: int, status: str) -> int:
    from app.database import SessionLocal
    from app.models.entities import OcrJob

    with SessionLocal() as db:
        job = OcrJob(
            course_id=course_id,
            document_id=document_id,
            status=status,
            start_page=1,
            max_pages=2,
            error_message="pytest seeded ocr job",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job.id


def _count_document_chunks(document_id: int) -> int:
    from app.database import SessionLocal
    from app.models.entities import DocumentChunk

    with SessionLocal() as db:
        return db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).count()


def _count_document_processing_jobs(document_id: int) -> int:
    from app.database import SessionLocal
    from app.models.entities import ProcessingJob

    with SessionLocal() as db:
        return db.query(ProcessingJob).filter(ProcessingJob.document_id == document_id).count()


def _count_ocr_jobs(document_id: int) -> int:
    from app.database import SessionLocal
    from app.models.entities import OcrJob

    with SessionLocal() as db:
        return db.query(OcrJob).filter(OcrJob.document_id == document_id).count()
