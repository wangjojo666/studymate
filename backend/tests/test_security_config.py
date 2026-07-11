from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


def test_production_missing_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "")
    monkeypatch.setenv("ENABLE_DEMO_USER", "false")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="explicit AUTH_SECRET_KEY"):
        config.validate_runtime_settings()


def test_production_short_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "too-short")
    monkeypatch.setenv("ENABLE_DEMO_USER", "false")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="AUTH_SECRET_KEY"):
        config.validate_runtime_settings()


def test_production_placeholder_secret_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "replace-with-a-long-random-production-secret")
    monkeypatch.setenv("ENABLE_DEMO_USER", "false")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="non-placeholder"):
        config.validate_runtime_settings()


def test_production_accepts_long_non_placeholder_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-only-secret-with-more-than-32-chars")
    monkeypatch.setenv("ENABLE_DEMO_USER", "false")
    monkeypatch.setenv("CPP_RUN_ENABLED", "false")
    config = _reload_config()

    config.validate_runtime_settings()


def test_production_rejects_demo_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-only-secret-with-more-than-32-chars")
    monkeypatch.setenv("ENABLE_DEMO_USER", "true")
    config = _reload_config()

    with pytest.raises(RuntimeError, match="ENABLE_DEMO_USER"):
        config.validate_runtime_settings()


def test_development_secret_is_random_when_unconfigured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_SECRET_KEY", "")
    first = _reload_config().settings
    second = _reload_config().settings

    assert not first.auth_secret_key_configured
    assert not second.auth_secret_key_configured
    assert len(first.auth_secret_key) >= 32
    assert first.auth_secret_key != second.auth_secret_key


@pytest.mark.parametrize("enabled, expected_users", [(False, 0), (True, 1)])
def test_demo_user_requires_explicit_development_opt_in(
    tmp_path: Path,
    monkeypatch,
    enabled: bool,
    expected_users: int,
):
    database_path = tmp_path / f"demo-{enabled}.db"
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("AUTH_SECRET_KEY", "")
    monkeypatch.setenv("ENABLE_DEMO_USER", str(enabled).lower())
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / f"storage-{enabled}"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / f"storage-{enabled}" / "uploads"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / f"storage-{enabled}" / "chroma"))
    _clear_app_modules()

    from app.database import SessionLocal, engine, init_database
    from app.models.entities import User

    try:
        init_database()
        with SessionLocal() as db:
            assert db.query(User).count() == expected_users
    finally:
        engine.dispose()
        _clear_app_modules()


def test_production_rejects_cpp_run_without_real_sandbox(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-only-secret-with-more-than-32-chars")
    monkeypatch.setenv("ENABLE_DEMO_USER", "false")
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


def _clear_app_modules() -> None:
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
