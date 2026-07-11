from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


def test_register_and_login_success(unauthenticated_client):
    email = f"auth-{uuid.uuid4().hex[:8]}@example.com"
    password = "strong-password"

    register_response = unauthenticated_client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Auth Test"},
    )
    assert register_response.status_code == 200, register_response.text
    token = register_response.json()["access_token"]
    assert token

    login_response = unauthenticated_client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200, login_response.text
    login_token = login_response.json()["access_token"]
    assert login_token

    me_response = unauthenticated_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login_token}"},
    )
    assert me_response.status_code == 200, me_response.text
    assert me_response.json()["email"] == email


def test_duplicate_register_returns_409(unauthenticated_client):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "strong-password", "display_name": "Dup"}

    assert unauthenticated_client.post("/api/auth/register", json=payload).status_code == 200
    duplicate_response = unauthenticated_client.post("/api/auth/register", json=payload)

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "账号已存在"


def test_register_unique_constraint_race_returns_409_and_rolls_back():
    from app.routers.auth import register
    from app.schemas import RegisterRequest

    class RaceSession:
        rolled_back = False

        def query(self, _model):
            return self

        def filter(self, *_conditions):
            return self

        def first(self):
            return None

        def add(self, _user):
            return None

        def commit(self):
            raise IntegrityError("INSERT INTO users", {}, Exception("UNIQUE constraint failed"))

        def rollback(self):
            self.rolled_back = True

    db = RaceSession()
    payload = RegisterRequest(email="race@example.com", password="strong-password")

    with pytest.raises(HTTPException) as captured:
        register(payload, db)

    assert captured.value.status_code == 409
    assert captured.value.detail == "账号已存在"
    assert db.rolled_back is True


def test_invalid_login_returns_401(unauthenticated_client):
    email = f"bad-login-{uuid.uuid4().hex[:8]}@example.com"
    password = "right-password"
    register_response = unauthenticated_client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "display_name": "Bad Login"},
    )
    assert register_response.status_code == 200, register_response.text

    login_response = unauthenticated_client.post(
        "/api/auth/login",
        json={"email": email, "password": "wrong-password"},
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "账号或密码错误"


def test_tampered_token_returns_401(client):
    token = client.headers["Authorization"].split(" ", 1)[1]
    tampered = f"{token[:-1]}{'a' if token[-1] != 'a' else 'b'}"

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_expired_token_returns_401(client):
    from app.services import auth_service

    header = {"alg": auth_service.TOKEN_ALGORITHM, "typ": "JWT"}
    payload = {"sub": "1", "exp": 1}
    signing_input = ".".join([auth_service._json_b64(header), auth_service._json_b64(payload)])
    expired_token = f"{signing_input}.{auth_service._sign(signing_input)}"

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"


def test_token_for_missing_user_returns_401(unauthenticated_client):
    from app.services.auth_service import create_access_token

    missing_user_token = create_access_token(999_999)

    response = unauthenticated_client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {missing_user_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "请先登录"
