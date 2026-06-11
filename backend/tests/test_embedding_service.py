from __future__ import annotations

from contextlib import contextmanager


def test_hash_embedding_stable():
    from app.services.embedding_service import embed_texts

    first = embed_texts(["virtual function dynamic binding"], purpose="query")
    second = embed_texts(["virtual function dynamic binding"], purpose="query")

    assert first.provider == "hash"
    assert first.dimension == 384
    assert first.vectors == second.vectors
    assert any(value != 0 for value in first.vectors[0])


def test_unknown_embedding_provider_falls_back_to_hash():
    from app.services import embedding_service

    with _temporary_setting(embedding_service.settings, "embedding_provider", "nonsense"):
        batch = embedding_service.embed_texts(["fallback check"], purpose="query")

    assert batch.provider == "hash"
    assert batch.dimension == 384


def test_openai_compatible_without_base_url_falls_back_to_hash():
    from app.services import embedding_service

    with _temporary_setting(embedding_service.settings, "embedding_provider", "openai_compatible"):
        with _temporary_setting(embedding_service.settings, "embedding_base_url", ""):
            batch = embedding_service.embed_texts(["fallback check"], purpose="query")

    assert batch.provider.startswith("openai_compatible->hash")
    assert batch.dimension == 384


@contextmanager
def _temporary_setting(settings, name: str, value):
    old_value = getattr(settings, name)
    object.__setattr__(settings, name, value)
    try:
        yield
    finally:
        object.__setattr__(settings, name, old_value)
