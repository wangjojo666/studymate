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
    assert payload["text_llm_provider"] == "mock"
    assert payload["embedding_provider"] == "hash"
    assert payload["embedding_provider_actual"] == "hash/384d"
    assert payload["ocr_llm_provider"] == "mock"
    assert payload["retrieval_provider"] == payload["retrieval"]["active_backend"]
    assert payload["active_backend"] == payload["retrieval"]["active_backend"]
    assert payload["provider_labels"]["text_generation"] == "离线规则生成"
    assert payload["provider_labels"]["embedding"] == "Hash 检索"
    assert payload["provider_labels"]["ocr"] == "离线文本提取"
    assert payload["capability_label"] == "离线规则生成 · Hash 检索"


def test_health_capability_uses_effective_embedding_fallback(client, monkeypatch):
    from dataclasses import replace

    from app import main

    monkeypatch.setattr(
        main,
        "settings",
        replace(
            main.settings,
            embedding_provider="sentence_transformers",
            embedding_model="BAAI/bge-small-zh-v1.5",
        ),
    )
    monkeypatch.setattr(
        main,
        "retrieval_backend_status",
        lambda: {
            "chroma_available": False,
            "embedding_provider": "sentence_transformers->hash (not installed)",
            "fallback_search": "sqlite_sparse",
            "active_backend": "sqlite_sparse",
            "search_order": ["sqlite_sparse"],
        },
    )

    response = client.get("/api/health/detail")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embedding_provider"] == "sentence_transformers"
    assert payload["embedding_provider_actual"].startswith("sentence_transformers->hash")
    assert payload["provider_labels"]["embedding"] == "Hash 检索"
    assert "BGE" not in payload["capability_label"]
