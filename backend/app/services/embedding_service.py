from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

TOKEN_RE = re.compile("[\u4e00-\u9fff]+|[a-zA-Z0-9_]+")

_sentence_model: Any | None = None
_sentence_model_name: str | None = None
_provider_fallback_reason: str = ""


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: list[list[float]]
    provider: str
    dimension: int


def tokenize_for_hash(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_RE.findall(text.lower()):
        if re.fullmatch("[\u4e00-\u9fff]+", match):
            tokens.extend(match)
            tokens.extend(match[i : i + 2] for i in range(len(match) - 1))
        else:
            tokens.append(match)
    return [token for token in tokens if token.strip()]


def embed_text(text: str, purpose: str = "document") -> list[float]:
    return embed_texts([text], purpose=purpose).vectors[0]


def embed_texts(texts: list[str], purpose: str = "document") -> EmbeddingBatch:
    provider = settings.embedding_provider
    if provider == "sentence_transformers":
        return _embed_with_sentence_transformers(texts, purpose)
    if provider == "openai_compatible":
        return _embed_with_openai_compatible(texts)
    return _hash_batch(texts, provider="hash")


def embedding_provider_label() -> str:
    if settings.embedding_provider == "hash":
        return f"hash/{settings.embedding_dimension}d"
    if _provider_fallback_reason:
        return f"{settings.embedding_provider}->hash ({_provider_fallback_reason})"
    if settings.embedding_provider == "sentence_transformers":
        return f"sentence_transformers/{settings.embedding_model}"
    if settings.embedding_provider == "openai_compatible":
        return f"openai_compatible/{settings.embedding_model}"
    return settings.embedding_provider


def _hash_batch(texts: list[str], provider: str) -> EmbeddingBatch:
    vectors = [_hash_embedding(text) for text in texts]
    return EmbeddingBatch(vectors=vectors, provider=provider, dimension=len(vectors[0]) if vectors else settings.embedding_dimension)


def _hash_embedding(text: str) -> list[float]:
    dimension = max(32, int(settings.embedding_dimension))
    vector = [0.0] * dimension
    tokens = tokenize_for_hash(text)
    if not tokens:
        return vector

    counts = Counter(tokens)
    for token, count in counts.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimension
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign * (1.0 + math.log(count))
    return _normalize(vector)


def _embed_with_sentence_transformers(texts: list[str], purpose: str) -> EmbeddingBatch:
    global _provider_fallback_reason
    try:
        model = _get_sentence_transformer()
        method_name = "encode_document" if purpose == "document" else "encode_query"
        if hasattr(model, method_name):
            raw_vectors = getattr(model, method_name)(
                texts,
                batch_size=settings.embedding_batch_size,
                normalize_embeddings=True,
            )
        else:
            raw_vectors = model.encode(
                texts,
                batch_size=settings.embedding_batch_size,
                normalize_embeddings=True,
            )
        vectors = [_normalize([float(value) for value in vector]) for vector in raw_vectors]
        _provider_fallback_reason = ""
        return EmbeddingBatch(
            vectors=vectors,
            provider=f"sentence_transformers/{settings.embedding_model}",
            dimension=len(vectors[0]) if vectors else settings.embedding_dimension,
        )
    except Exception as exc:  # noqa: BLE001 - embedding must degrade gracefully for demos.
        reason = _short_reason(exc)
        _provider_fallback_reason = reason
        logger.warning("sentence-transformers embedding unavailable; falling back to hash: %s", reason)
        return _hash_batch(texts, provider=f"sentence_transformers->hash ({reason})")


def _get_sentence_transformer():
    global _sentence_model, _sentence_model_name
    if _sentence_model is not None and _sentence_model_name == settings.embedding_model:
        return _sentence_model
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("sentence-transformers 未安装") from exc

    _sentence_model = SentenceTransformer(settings.embedding_model)
    _sentence_model_name = settings.embedding_model
    return _sentence_model


def _embed_with_openai_compatible(texts: list[str]) -> EmbeddingBatch:
    global _provider_fallback_reason
    if not settings.embedding_base_url:
        reason = "EMBEDDING_BASE_URL 未配置"
        _provider_fallback_reason = reason
        return _hash_batch(texts, provider=f"openai_compatible->hash ({reason})")
    if not settings.embedding_model:
        reason = "EMBEDDING_MODEL 未配置"
        _provider_fallback_reason = reason
        return _hash_batch(texts, provider=f"openai_compatible->hash ({reason})")

    url = settings.embedding_base_url.rstrip("/")
    if not url.endswith("/embeddings"):
        url = f"{url}/embeddings"
    headers = {"Content-Type": "application/json"}
    if settings.embedding_api_key:
        headers["Authorization"] = f"Bearer {settings.embedding_api_key}"

    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), settings.embedding_batch_size):
            batch = texts[start : start + settings.embedding_batch_size]
            response = httpx.post(
                url,
                headers=headers,
                json={"model": settings.embedding_model, "input": batch},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
            vectors.extend(_normalize([float(value) for value in item["embedding"]]) for item in data)
        if len(vectors) != len(texts):
            raise RuntimeError("embedding API 返回数量不匹配")
        _provider_fallback_reason = ""
        return EmbeddingBatch(
            vectors=vectors,
            provider=f"openai_compatible/{settings.embedding_model}",
            dimension=len(vectors[0]) if vectors else settings.embedding_dimension,
        )
    except Exception as exc:  # noqa: BLE001
        reason = _short_reason(exc)
        _provider_fallback_reason = reason
        logger.warning("OpenAI-compatible embedding unavailable; falling back to hash: %s", reason)
        return _hash_batch(texts, provider=f"openai_compatible->hash ({reason})")


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _short_reason(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return text.replace("\n", " ")[:120]
