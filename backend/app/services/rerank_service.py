from __future__ import annotations

from dataclasses import replace

from app.config import settings
from app.services.vector_store import SearchResult, tokenize


def rerank_results(query: str, results: list[SearchResult]) -> tuple[list[SearchResult], str, bool]:
    provider = settings.rerank_provider
    if provider == "none" or not results:
        return results, "none", False
    if provider != "rule":
        provider = "rule"

    query_terms = set(tokenize(query))
    if not query_terms:
        return results, provider, False

    reranked: list[SearchResult] = []
    for result in results:
        content_terms = set(tokenize(result.content))
        overlap = len(query_terms & content_terms) / max(1, len(query_terms))
        adjusted_score = (result.score * 0.78) + (overlap * 0.22)
        reranked.append(replace(result, score=adjusted_score))
    reranked.sort(key=lambda item: item.score, reverse=True)
    return reranked, provider, True


def combine_retrieval_provider(retrieval_provider: str, rerank_provider: str, applied: bool) -> str:
    if not applied:
        return retrieval_provider
    return f"{retrieval_provider}+rerank/{rerank_provider}"
