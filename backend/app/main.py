from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings, validate_runtime_settings
from app.database import SessionLocal, init_database
from app.middleware.rate_limit import InMemoryRateLimitMiddleware
from app.routers import assistant, auth, courses, cpp_tools, documents, learning
from app.services.processing_jobs import recover_interrupted_processing_jobs
from app.services.vector_store import retrieval_backend_status


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_settings()
    init_database()
    with SessionLocal() as db:
        recovered_jobs = recover_interrupted_processing_jobs(db)
        if recovered_jobs:
            db.commit()
            logging.getLogger(__name__).warning(
                "Marked %s interrupted background job(s) as failed after startup",
                recovered_jobs,
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
    return {
        "status": "ok",
        "name": settings.app_name,
        "retrieval": retrieval_backend_status(),
    }
