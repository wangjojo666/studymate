from __future__ import annotations

import zipfile


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
    object.__setattr__(settings, "rate_limit_login_per_minute", 2)
    object.__setattr__(settings, "rate_limit_window_seconds", 60)

    payload = {"email": "nobody@example.com", "password": "wrong-password"}
    first = unauthenticated_client.post("/api/auth/login", json=payload)
    second = unauthenticated_client.post("/api/auth/login", json=payload)
    third = unauthenticated_client.post("/api/auth/login", json=payload)

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429
    assert "请求过于频繁" in third.json()["detail"]
