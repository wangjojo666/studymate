from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    page_number: int
    content: str


def split_pages_into_chunks(
    pages: list[tuple[int, str]], max_chars: int = 900, overlap: int = 160
) -> list[TextChunk]:
    # 将按页解析出的文本切成可检索片段，并保留页码用于前端展示来源。
    chunks: list[TextChunk] = []
    for page_number, text in pages:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not normalized:
            continue
        start = 0
        while start < len(normalized):
            end = min(start + max_chars, len(normalized))
            segment = normalized[start:end].strip()
            if segment:
                chunks.append(TextChunk(page_number=page_number, content=segment))
            if end >= len(normalized):
                break
            start = max(0, end - overlap)
    return chunks
