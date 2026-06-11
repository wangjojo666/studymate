from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'studymate-test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "storage" / "uploads"))
    monkeypatch.setenv("TEXT_LLM_PROVIDER", "mock")
    monkeypatch.setenv("TEXT_LLM_FALLBACK_PROVIDER", "none")
    monkeypatch.setenv("OCR_LLM_PROVIDER", "mock")

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    from app.main import app

    with TestClient(app) as test_client:
        login_response = test_client.post(
            "/api/auth/login",
            json={"email": "demo@studymate.local", "password": "studymate-demo"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        test_client.headers.update({"Authorization": f"Bearer {token}"})
        yield test_client
