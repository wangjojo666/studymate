from __future__ import annotations

import zipfile
from collections import deque


def test_office_zip_bomb_is_rejected(tmp_path):
    from app.services import upload_validation
    from app.services.upload_validation import UploadValidationError, validate_upload_file

    object.__setattr__(upload_validation.settings, "office_zip_max_total_uncompressed_bytes", 1024)
    object.__setattr__(upload_validation.settings, "office_zip_max_member_bytes", 1024)
    path = tmp_path / "bomb.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types></Types>")
        archive.writestr("word/document.xml", "<w:document></w:document>")
        archive.writestr("word/media/large.bin", b"0" * 2048)

    try:
        validate_upload_file(path, ".docx")
    except UploadValidationError as exc:
        assert "过大" in str(exc)
    else:
        raise AssertionError("zip bomb payload should be rejected")


def test_login_rate_limit_returns_429(unauthenticated_client):
    from app.config import settings
    from app.middleware.rate_limit import clear_rate_limit_state

    clear_rate_limit_state()
    original_enabled = settings.rate_limit_enabled
    original_limit = settings.rate_limit_login_per_minute
    original_window = settings.rate_limit_window_seconds
    object.__setattr__(settings, "rate_limit_enabled", True)
    object.__setattr__(settings, "rate_limit_login_per_minute", 2)
    object.__setattr__(settings, "rate_limit_window_seconds", 60)

    try:
        payload = {"email": "nobody@example.com", "password": "wrong-password"}
        first = unauthenticated_client.post("/api/auth/login", json=payload)
        second = unauthenticated_client.post("/api/auth/login", json=payload)
        third = unauthenticated_client.post("/api/auth/login", json=payload)
    finally:
        object.__setattr__(settings, "rate_limit_enabled", original_enabled)
        object.__setattr__(settings, "rate_limit_login_per_minute", original_limit)
        object.__setattr__(settings, "rate_limit_window_seconds", original_window)
        clear_rate_limit_state()

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert "请求过于频繁" in third.json()["detail"]


def test_login_rate_limit_ignores_untrusted_bearer_tokens(unauthenticated_client):
    from app.config import settings
    from app.middleware.rate_limit import clear_rate_limit_state

    clear_rate_limit_state()
    original_enabled = settings.rate_limit_enabled
    original_limit = settings.rate_limit_login_per_minute
    object.__setattr__(settings, "rate_limit_enabled", True)
    object.__setattr__(settings, "rate_limit_login_per_minute", 2)
    try:
        payload = {"email": "nobody@example.com", "password": "wrong-password"}
        responses = [
            unauthenticated_client.post(
                "/api/auth/login",
                json=payload,
                headers={"Authorization": f"Bearer forged-{index}"},
            )
            for index in range(3)
        ]
    finally:
        object.__setattr__(settings, "rate_limit_enabled", original_enabled)
        object.__setattr__(settings, "rate_limit_login_per_minute", original_limit)
        clear_rate_limit_state()

    assert [response.status_code for response in responses] == [401, 401, 429]


def test_register_rate_limit_returns_429(unauthenticated_client):
    from app.config import settings
    from app.middleware.rate_limit import clear_rate_limit_state

    clear_rate_limit_state()
    original_enabled = settings.rate_limit_enabled
    original_limit = settings.rate_limit_register_per_minute
    object.__setattr__(settings, "rate_limit_enabled", True)
    object.__setattr__(settings, "rate_limit_register_per_minute", 1)
    try:
        first = unauthenticated_client.post(
            "/api/auth/register",
            json={"email": "first@example.com", "password": "strong-password"},
        )
        second = unauthenticated_client.post(
            "/api/auth/register",
            json={"email": "second@example.com", "password": "strong-password"},
        )
    finally:
        object.__setattr__(settings, "rate_limit_enabled", original_enabled)
        object.__setattr__(settings, "rate_limit_register_per_minute", original_limit)
        clear_rate_limit_state()

    assert first.status_code == 200
    assert second.status_code == 429


def test_expired_rate_limit_buckets_are_reclaimed():
    from app.middleware.rate_limit import (
        _hits,
        clear_rate_limit_state,
        prune_expired_rate_limit_state,
    )

    clear_rate_limit_state()
    _hits["login:expired"] = deque([10.0])
    _hits["login:active"] = deque([95.0])

    removed = prune_expired_rate_limit_state(now=100.0, window=30)

    assert removed == 1
    assert "login:expired" not in _hits
    assert list(_hits["login:active"]) == [95.0]
    clear_rate_limit_state()
