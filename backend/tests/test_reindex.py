from __future__ import annotations

import json


def test_reindex_document_and_course_rebuild_sparse_vectors(client, auth_helpers):
    course = auth_helpers.create_course("Reindex Course")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "virtual dispatch runtime polymorphism override vtable",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    _corrupt_document_chunks(uploaded["id"])
    document_response = client.post(
        f"/api/courses/{course['id']}/documents/{uploaded['id']}/reindex"
    )
    assert document_response.status_code == 200, document_response.text
    document_payload = document_response.json()
    assert document_payload["scope"] == "document"
    assert document_payload["chunk_count"] >= 1
    assert document_payload["embedding_provider"]
    _assert_document_chunks_rebuilt(uploaded["id"])

    _corrupt_document_chunks(uploaded["id"])
    course_response = client.post(f"/api/courses/{course['id']}/reindex")
    assert course_response.status_code == 200, course_response.text
    course_payload = course_response.json()
    assert course_payload["scope"] == "course"
    assert course_payload["chunk_count"] >= 1
    assert course_payload["document_count"] == 1
    assert course_payload["embedding_provider"]
    _assert_document_chunks_rebuilt(uploaded["id"])


def test_reindex_isolated_by_course_owner(client, auth_helpers):
    course = auth_helpers.create_course("Private Reindex")
    uploaded = auth_helpers.upload_text_file(course["id"], "owner only reindex material")
    auth_helpers.wait_document_done(course["id"], uploaded["id"])
    other_user = auth_helpers.create_user_and_login()

    course_response = client.post(
        f"/api/courses/{course['id']}/reindex",
        headers=other_user["headers"],
    )
    document_response = client.post(
        f"/api/courses/{course['id']}/documents/{uploaded['id']}/reindex",
        headers=other_user["headers"],
    )
    assert course_response.status_code == 404
    assert document_response.status_code == 404


def test_reindex_empty_course_returns_zero_counts(client, auth_helpers):
    course = auth_helpers.create_course("Empty Reindex")

    response = client.post(f"/api/courses/{course['id']}/reindex")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["scope"] == "course"
    assert payload["chunk_count"] == 0
    assert payload["document_count"] == 0


def _corrupt_document_chunks(document_id: int) -> None:
    from app.database import SessionLocal
    from app.models.entities import DocumentChunk

    with SessionLocal() as db:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        assert chunks
        for chunk in chunks:
            chunk.token_weights = "{}"
            chunk.vector_norm = 0.0
        db.commit()


def _assert_document_chunks_rebuilt(document_id: int) -> None:
    from app.database import SessionLocal
    from app.models.entities import DocumentChunk

    with SessionLocal() as db:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        assert chunks
        for chunk in chunks:
            weights = json.loads(chunk.token_weights)
            assert weights
            assert chunk.vector_norm > 0
