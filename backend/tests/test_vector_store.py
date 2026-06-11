from __future__ import annotations


def test_hash_embedding_is_normalized_and_stable():
    from app.services.embedding_service import embed_texts

    first = embed_texts(["虚函数 动态绑定 多态"], purpose="query")
    second = embed_texts(["虚函数 动态绑定 多态"], purpose="query")

    assert first.provider == "hash"
    assert first.dimension == 384
    assert first.vectors == second.vectors
    assert len(first.vectors[0]) == 384
    assert any(value != 0 for value in first.vectors[0])
