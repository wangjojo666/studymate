from __future__ import annotations


def test_ask_without_documents_friendly_message(client, auth_helpers):
    course = auth_helpers.create_course("No Documents RAG")

    response = client.post(
        f"/api/courses/{course['id']}/ask",
        json={"question": "What should I review?", "top_k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sources"] == []
    assert payload["llm_provider"] == "system"
    assert payload["answer_status"] == "empty_knowledge_base"
    assert payload["confidence"] == "low"
    assert payload["source_count"] == 0
    assert payload["answer"]


def test_ask_after_txt_upload_returns_sources_and_providers(client, auth_helpers):
    course = auth_helpers.create_course("RAG With Sources")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "Virtual functions enable runtime polymorphism through dynamic dispatch and overriding.",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    response = client.post(
        f"/api/courses/{course['id']}/ask",
        json={"question": "Why do virtual functions support runtime polymorphism?", "top_k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["answer"]
    assert payload["sources"]
    assert payload["answer_status"] == "answered"
    assert payload["confidence"] in {"medium", "high"}
    assert payload["source_count"] == len(payload["sources"])
    assert "score" in payload["sources"][0]
    assert "chunk_id" in payload["sources"][0]
    assert payload["llm_provider"]
    assert payload["retrieval_provider"]

    source = payload["sources"][0]
    chunk_response = client.get(
        f"/api/courses/{course['id']}/chunks/{source['chunk_id']}",
        params={"score": source["score"], "retrieval_provider": payload["retrieval_provider"]},
    )
    assert chunk_response.status_code == 200, chunk_response.text
    chunk_payload = chunk_response.json()
    assert chunk_payload["document_name"] == source["document_name"]
    assert chunk_payload["page"] == source["page"]
    assert chunk_payload["chunk_index"] == source["chunk_index"]
    assert "Virtual functions" in chunk_payload["content"]
    assert chunk_payload["retrieval_provider"] == payload["retrieval_provider"]

    other_user = auth_helpers.create_user_and_login()
    forbidden_response = client.get(
        f"/api/courses/{course['id']}/chunks/{source['chunk_id']}",
        headers=other_user["headers"],
    )
    assert forbidden_response.status_code == 404


def test_low_confidence_question_refuses_to_answer(client, auth_helpers):
    course = auth_helpers.create_course("RAG Low Confidence")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "Virtual functions enable runtime polymorphism through dynamic dispatch and overriding.",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    response = client.post(
        f"/api/courses/{course['id']}/ask",
        json={"question": "photosynthesis chlorophyll mitochondria astronomy", "top_k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["answer_status"] == "low_confidence"
    assert payload["confidence"] == "low"
    assert payload["llm_provider"] == "system"
    assert "没有找到足够依据" in payload["answer"]


def test_answer_verification_downgrades_unsupported_generated_answer(client, auth_helpers, monkeypatch):
    from app.services.llm_service import LlmResponse

    course = auth_helpers.create_course("RAG Verification")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "Virtual functions enable runtime polymorphism through dynamic dispatch and overriding.",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])
    monkeypatch.setattr(
        "app.services.rag_service.call_llm",
        lambda _messages: LlmResponse(
            content="Photosynthesis depends on chlorophyll inside plant leaves.",
            used_provider="fake/test",
        ),
    )

    response = client.post(
        f"/api/courses/{course['id']}/ask",
        json={"question": "Why do virtual functions support runtime polymorphism?", "top_k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["answer_status"] == "low_confidence"
    assert payload["confidence"] == "low"
    assert "没有找到足够依据" in payload["answer"]
    assert payload["sources"]
