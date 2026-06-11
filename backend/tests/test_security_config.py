from __future__ import annotations

import importlib
import sys

import pytest


def test_production_default_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "studymate-dev-secret-change-me")
    sys.modules.pop("app.config", None)

    config = importlib.import_module("app.config")

    with pytest.raises(RuntimeError):
        config.validate_runtime_settings()
