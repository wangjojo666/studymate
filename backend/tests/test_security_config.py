from __future__ import annotations

import importlib
import sys

import pytest


def test_production_default_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "studymate-dev-secret-change-me")
    config = _reload_config()

    with pytest.raises(RuntimeError):
        config.validate_runtime_settings()


def test_production_short_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "too-short")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
        config.validate_runtime_settings()


def test_production_placeholder_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "replace-with-a-long-random-production-secret")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="占位"):
        config.validate_runtime_settings()


def test_production_accepts_long_non_placeholder_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-only-secret-with-more-than-32-chars")
    monkeypatch.setenv("CPP_RUN_ENABLED", "false")
    config = _reload_config()

    config.validate_runtime_settings()


def test_production_rejects_cpp_run_without_real_sandbox(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-only-secret-with-more-than-32-chars")
    monkeypatch.setenv("CPP_RUN_ENABLED", "true")
    monkeypatch.setenv("CPP_RUN_SANDBOX", "none")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="CPP_RUN_ENABLED"):
        config.validate_runtime_settings()


def test_unimplemented_cpp_sandbox_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CPP_RUN_ENABLED", "true")
    monkeypatch.setenv("CPP_RUN_SANDBOX", "docker")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="CPP_RUN_SANDBOX=docker"):
        config.validate_runtime_settings()


def _reload_config():
    sys.modules.pop("app.config", None)
    return importlib.import_module("app.config")
