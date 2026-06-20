from __future__ import annotations


def test_upload_txt_returns_queued_then_indexed(auth_helpers):
    course = auth_helpers.create_course("Document Status")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "virtual function dynamic binding polymorphism override vtable runtime dispatch",
    )

    assert uploaded["status"] in {"queued", "uploaded", "parsing", "indexed"}
    indexed = auth_helpers.wait_document_done(course["id"], uploaded["id"])
    assert indexed["status"] == "indexed"
    assert indexed["chunk_count"] > 0
    assert indexed["processing_progress"] == 100
    assert indexed["indexed_at"]


def test_upload_empty_txt_becomes_empty(auth_helpers):
    course = auth_helpers.create_course("Empty Document")
    uploaded = auth_helpers.upload_text_file(course["id"], "   \n\t  ", filename="empty.txt")

    done = auth_helpers.wait_document_done(course["id"], uploaded["id"])

    assert done["status"] in {"empty", "failed"}
    assert done["processing_progress"] == 100
    assert done["error_message"]


def test_upload_unsupported_file_returns_400(client, auth_helpers):
    course = auth_helpers.create_course("Unsupported Upload")

    response = client.post(
        f"/api/courses/{course['id']}/documents",
        files={"file": ("malware.exe", b"not really executable", "application/octet-stream")},
    )

    assert response.status_code == 400


def test_reject_fake_pdf_upload(client, auth_helpers):
    course = auth_helpers.create_course("Fake PDF Upload")

    response = client.post(
        f"/api/courses/{course['id']}/documents",
        files={"file": ("fake.pdf", b"not a real pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_reject_fake_png_upload(client, auth_helpers):
    course = auth_helpers.create_course("Fake PNG Upload")

    response = client.post(
        f"/api/courses/{course['id']}/documents",
        files={"file": ("fake.png", b"not a real png", "image/png")},
    )

    assert response.status_code == 400
    assert "PNG" in response.json()["detail"]


def test_upload_valid_txt_still_indexes(auth_helpers):
    course = auth_helpers.create_course("Valid TXT Upload")

    uploaded = auth_helpers.upload_text_file(course["id"], "normal utf-8 text for validation")
    indexed = auth_helpers.wait_document_done(course["id"], uploaded["id"])

    assert indexed["status"] == "indexed"
    assert indexed["chunk_count"] >= 1
