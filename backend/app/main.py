from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_runtime_settings
from app.database import SessionLocal, init_database
from app.middleware.rate_limit import InMemoryRateLimitMiddleware
from app.routers import assistant, auth, courses, cpp_tools, documents, learning
from app.services.file_storage import reconcile_staged_deletions
from app.services.processing_jobs import recover_interrupted_processing_jobs
from app.services.vector_store import reconcile_vector_index, retrieval_backend_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_settings()
    init_database()
    file_reconciliation = reconcile_staged_deletions(settings.upload_dir)
    if not file_reconciliation["ok"]:
        logger.warning(
            "Upload tombstone reconciliation left %s failure(s)",
            len(file_reconciliation["failures"]),
        )
    with SessionLocal() as db:
        recovered_jobs = recover_interrupted_processing_jobs(db)
        if recovered_jobs:
            db.commit()
            logger.warning(
                "Marked %s interrupted background job(s) as failed after startup",
                recovered_jobs,
            )
        vector_reconciliation = reconcile_vector_index(db)
        if not vector_reconciliation["ok"]:
            logger.warning(
                "Vector index reconciliation failed; SQL-backed retrieval filtering remains active"
            )
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(InMemoryRateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(courses.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(documents.router, prefix=settings.api_prefix)
app.include_router(documents.jobs_router, prefix=settings.api_prefix)
app.include_router(assistant.router, prefix=settings.api_prefix)
app.include_router(learning.router, prefix=settings.api_prefix)
app.include_router(cpp_tools.router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


@app.get(f"{settings.api_prefix}/health")
def health() -> dict:
    return {"status": "ok", "name": settings.app_name}


@app.get(f"{settings.api_prefix}/health/detail")
def health_detail() -> dict:
    retrieval = retrieval_backend_status()
    provider_labels = {
        "text_generation": _text_provider_label(),
        "embedding": _embedding_provider_label(retrieval["embedding_provider"]),
        "ocr": _ocr_provider_label(),
        "retrieval": _retrieval_provider_label(retrieval["active_backend"]),
    }
    return {
        "status": "ok",
        "name": settings.app_name,
        # Raw identifiers are stable and machine-readable. Display labels make
        # offline/mock capabilities explicit so the UI never implies that a
        # real model was called when it was not.
        "text_llm_provider": settings.text_llm_provider,
        "text_llm_model": settings.text_llm_model,
        "embedding_provider": settings.embedding_provider,
        "embedding_provider_actual": retrieval["embedding_provider"],
        "embedding_model": settings.embedding_model,
        "ocr_llm_provider": settings.ocr_llm_provider,
        "ocr_llm_model": settings.ocr_llm_model,
        "retrieval_provider": retrieval["active_backend"],
        "active_backend": retrieval["active_backend"],
        "provider_labels": provider_labels,
        "capability_label": _capability_label(provider_labels),
        "retrieval": retrieval,
    }


def _text_provider_label() -> str:
    provider = settings.text_llm_provider
    if provider in {"mock", "offline", "none"}:
        return "离线规则生成"
    if provider == "deepseek":
        return "DeepSeek"
    if provider == "ollama":
        return "Ollama"
    return provider.replace("_", " ").title()


def _embedding_provider_label(actual_provider: str) -> str:
    normalized = actual_provider.lower()
    if normalized.startswith("hash") or "->hash" in normalized:
        return "Hash 检索"
    if "bge" in normalized:
        if "configured, not verified" in normalized:
            return "BGE Embedding（已配置，未验证）"
        return "BGE Embedding"
    if normalized.startswith("sentence_transformers"):
        if "configured, not verified" in normalized:
            return "Sentence Transformers（已配置，未验证）"
        return "Sentence Transformers Embedding"
    if "configured, not verified" in normalized:
        return f"{settings.embedding_provider.replace('_', ' ').title()}（已配置，未验证）"
    return f"{actual_provider.replace('_', ' ').title()} Embedding"


def _ocr_provider_label() -> str:
    provider = settings.ocr_llm_provider
    if provider in {"mock", "offline", "none"}:
        return "离线文本提取"
    if provider == "ollama":
        return "Ollama · 本地 OCR"
    return f"{provider.replace('_', ' ').title()} OCR"


def _capability_label(provider_labels: dict[str, str]) -> str:
    labels = [provider_labels["text_generation"], provider_labels["embedding"]]
    if settings.ocr_llm_provider not in {"mock", "offline", "none"}:
        labels.append(provider_labels["ocr"])
    return " · ".join(labels)


def _retrieval_provider_label(provider: str) -> str:
    if provider == "sqlite_sparse":
        return "SQLite 稀疏检索"
    if provider == "chroma":
        return "Chroma 向量索引"
    return provider.replace("_", " ").title()
