from __future__ import annotations

from types import SimpleNamespace


class _FakeCollection:
    def __init__(self, ids: list[str], metadatas: list[dict], *, fail_deletes: int = 0):
        self.ids = ids
        self.metadatas = metadatas
        self.fail_deletes = fail_deletes
        self.delete_calls: list[dict] = []

    def query(self, **_kwargs):
        return {
            "ids": [self.ids],
            "documents": [["tampered external index text" for _item in self.ids]],
            "metadatas": [self.metadatas],
            "distances": [[0.05 + index * 0.01 for index, _item in enumerate(self.ids)]],
        }

    def get(self, **_kwargs):
        return {"ids": self.ids, "metadatas": self.metadatas}

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)
        if self.fail_deletes:
            self.fail_deletes -= 1
            raise RuntimeError("temporary vector store failure")


def _use_fake_chroma(monkeypatch, collection: _FakeCollection) -> None:
    monkeypatch.setattr("app.services.vector_store._get_chroma_collection", lambda: collection)
    monkeypatch.setattr(
        "app.services.vector_store.embed_texts",
        lambda _texts, purpose="document": SimpleNamespace(
            vectors=[[0.1, 0.2]],
            provider=f"hash/{purpose}",
        ),
    )


def test_chroma_hits_are_rehydrated_from_authoritative_sql(client, auth_helpers, monkeypatch):
    course = auth_helpers.create_course("SQL Authoritative RAG")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "SQL authoritative content about virtual dispatch and runtime polymorphism.",
        filename="authoritative.txt",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    from app.database import SessionLocal
    from app.models.entities import DocumentChunk
    from app.services.vector_store import search_course

    with SessionLocal() as db:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.document_id == uploaded["id"]).first()
        assert chunk is not None
        chunk_id = chunk.id
        sql_content = chunk.content

    collection = _FakeCollection(
        ids=[f"chunk-{chunk_id}", "chunk-999999"],
        metadatas=[
            {
                "course_id": 999,
                "document_id": 999,
                "document_name": "forged.txt",
                "embedding_provider": "fake",
            },
            {"course_id": course["id"], "document_id": uploaded["id"]},
        ],
    )
    _use_fake_chroma(monkeypatch, collection)

    with SessionLocal() as db:
        results = search_course(db, course["id"], "virtual dispatch", limit=5)

    assert len(results) == 1
    assert results[0].content == sql_content
    assert results[0].document_name == "authoritative.txt"
    assert results[0].document_id == uploaded["id"]
    assert results[0].content != "tampered external index text"
    assert any(call.get("ids") == ["chunk-999999"] for call in collection.delete_calls)


def test_failed_vector_delete_is_retried_and_deleted_sql_content_never_resurfaces(
    client,
    auth_helpers,
    monkeypatch,
):
    course = auth_helpers.create_course("Delete Reconciliation")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "OBSOLETE_DELETED_MARKER vector deletion reconciliation",
        filename="obsolete.txt",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    from app.database import SessionLocal
    from app.models.entities import DocumentChunk
    from app.services.vector_store import search_course

    with SessionLocal() as db:
        chunk_id = (
            db.query(DocumentChunk.id).filter(DocumentChunk.document_id == uploaded["id"]).scalar()
        )
    collection = _FakeCollection(
        ids=[f"chunk-{chunk_id}"],
        metadatas=[
            {
                "course_id": course["id"],
                "document_id": uploaded["id"],
                "document_name": "obsolete.txt",
            }
        ],
        fail_deletes=1,
    )
    _use_fake_chroma(monkeypatch, collection)

    response = client.delete(f"/api/courses/{course['id']}/documents/{uploaded['id']}")
    assert response.status_code == 200, response.text
    assert "向量索引清理失败" in response.json().get("warning", "")

    with SessionLocal() as db:
        results = search_course(db, course["id"], "OBSOLETE_DELETED_MARKER", limit=5)

    assert results == []
    assert len(collection.delete_calls) >= 2
    assert collection.delete_calls[-1].get("ids") == [f"chunk-{chunk_id}"]


def test_global_vector_reconciliation_removes_deleted_courses(client, monkeypatch):
    from app.database import SessionLocal
    from app.services.vector_store import reconcile_vector_index

    collection = _FakeCollection(
        ids=["chunk-987654", "invalid-id"],
        metadatas=[
            {"course_id": 987654, "document_id": 987654},
            {"course_id": 1, "document_id": 1},
        ],
    )
    _use_fake_chroma(monkeypatch, collection)

    with SessionLocal() as db:
        result = reconcile_vector_index(db)

    assert result == {
        "available": True,
        "checked": 2,
        "stale": 2,
        "deleted": 2,
        "ok": True,
    }
    assert collection.delete_calls[-1]["ids"] == ["chunk-987654", "invalid-id"]


def test_staged_file_cleanup_can_be_retried(tmp_path):
    from app.services.file_storage import reconcile_staged_deletions

    tombstone = tmp_path / "course" / ".notes.txt.token.deleting"
    tombstone.parent.mkdir(parents=True)
    tombstone.write_text("orphaned cleanup payload", encoding="utf-8")

    result = reconcile_staged_deletions(tmp_path)

    assert result["ok"] is True
    assert result["checked"] == 1
    assert result["deleted"] == 1
    assert not tombstone.exists()


def test_representative_and_reindex_paths_reject_cross_course_chunk_drift(
    client,
    auth_helpers,
):
    source_course = auth_helpers.create_course("Source Course")
    other_course = auth_helpers.create_course("Other Course")
    uploaded = auth_helpers.upload_text_file(
        source_course["id"],
        "cross course drift must never become representative context",
        filename="source.txt",
    )
    auth_helpers.wait_document_done(source_course["id"], uploaded["id"])

    from app.database import SessionLocal
    from app.models.entities import DocumentChunk
    from app.services.reindex_service import reindex_course
    from app.services.vector_store import get_representative_chunks

    with SessionLocal() as db:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.document_id == uploaded["id"]).one()
        chunk.course_id = other_course["id"]
        db.commit()

    with SessionLocal() as db:
        assert get_representative_chunks(db, other_course["id"], limit=8) == []
        result = reindex_course(db, other_course["id"])
        assert result["chunk_count"] == 0
