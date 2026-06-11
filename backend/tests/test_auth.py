from __future__ import annotations

import uuid


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
