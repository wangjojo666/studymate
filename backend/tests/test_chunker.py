from __future__ import annotations

from app.services.chunker import split_pages_into_chunks


def test_split_pages_into_chunks_keeps_page_number():
    chunks = split_pages_into_chunks([(3, "alpha beta gamma")], max_chars=100, overlap=10)

    assert len(chunks) == 1
    assert chunks[0].page_number == 3
    assert chunks[0].content == "alpha beta gamma"


def test_split_pages_into_chunks_splits_long_text():
    text = "x" * 260
    chunks = split_pages_into_chunks([(1, text)], max_chars=100, overlap=20)

    assert len(chunks) > 1
    assert all(chunk.page_number == 1 for chunk in chunks)
    assert all(chunk.content for chunk in chunks)


def test_split_pages_into_chunks_ignores_empty_text():
    chunks = split_pages_into_chunks([(1, "  \n\t "), (2, "")])

    assert chunks == []
