from __future__ import annotations


def test_health(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_detail_exposes_retrieval_backend(client):
    response = client.get("/api/health/detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload["retrieval"]["chroma_available"], bool)
    assert payload["retrieval"]["embedding_provider"]
    assert payload["retrieval"]["fallback_search"] == "sqlite_sparse"
