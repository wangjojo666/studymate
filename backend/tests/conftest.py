from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def unauthenticated_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'studymate-test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "storage" / "uploads"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "storage" / "chroma"))
    monkeypatch.setenv("TEXT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("TEXT_LLM_FALLBACK_PROVIDER", "none")
    monkeypatch.setenv("OCR_LLM_PROVIDER", "mock")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "384")
    monkeypatch.setenv("RAG_TOP_K", "5")
    monkeypatch.setenv("RAG_MIN_SCORE", "0.12")
    monkeypatch.setenv("RAG_CONTEXT_MAX_CHARS", "6000")
    monkeypatch.setenv("RAG_ENABLE_STRICT_SOURCE_MODE", "true")
    monkeypatch.setenv("CPP_RUN_ENABLED", "false")
    monkeypatch.setenv("APP_ENV", "development")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def client(unauthenticated_client):
    token = _login(unauthenticated_client, "demo@studymate.local", "studymate-demo")
    unauthenticated_client.headers.update({"Authorization": f"Bearer {token}"})
    yield unauthenticated_client


@pytest.fixture()
def auth_helpers(client):
    class Helpers:
        @staticmethod
        def create_user_and_login(email: str | None = None, password: str = "test-password") -> dict:
            address = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
            response = client.post(
                "/api/auth/register",
                json={"email": address, "password": password, "display_name": address.split("@", 1)[0]},
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            return {
                "email": address,
                "password": password,
                "token": payload["access_token"],
                "headers": {"Authorization": f"Bearer {payload['access_token']}"},
                "user": payload["user"],
            }

        @staticmethod
        def create_course(name: str | None = None, headers: dict | None = None) -> dict:
            response = client.post(
                "/api/courses",
                json={
                    "name": name or f"Test Course {uuid.uuid4().hex[:8]}",
                    "description": "pytest course",
                },
                headers=headers,
            )
            assert response.status_code == 200, response.text
            return response.json()

        @staticmethod
        def upload_text_file(
            course_id: int,
            text: str,
            filename: str = "notes.txt",
            headers: dict | None = None,
        ) -> dict:
            response = client.post(
                f"/api/courses/{course_id}/documents",
                files={"file": (filename, text.encode("utf-8"), "text/plain")},
                headers=headers,
            )
            assert response.status_code == 200, response.text
            return response.json()

        @staticmethod
        def wait_document_done(
            course_id: int,
            document_id: int,
            timeout_seconds: float = 5,
            headers: dict | None = None,
        ) -> dict:
            deadline = time.monotonic() + timeout_seconds
            last_document: dict | None = None
            terminal_statuses = {"indexed", "empty", "failed", "needs_ocr", "needs_vision"}
            while time.monotonic() < deadline:
                response = client.get(f"/api/courses/{course_id}", headers=headers)
                assert response.status_code == 200, response.text
                documents = response.json().get("documents", [])
                last_document = next((item for item in documents if item["id"] == document_id), None)
                if last_document and last_document.get("status") in terminal_statuses:
                    return last_document
                time.sleep(0.05)
            raise AssertionError(f"document {document_id} did not finish; last={last_document}")

    return Helpers()


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
