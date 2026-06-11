from __future__ import annotations


def test_create_and_list_courses(client):
    create_response = client.post(
        "/api/courses",
        json={"name": "测试课程", "description": "用于接口测试"},
    )

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["name"] == "测试课程"
    assert created["document_count"] == 0

    list_response = client.get("/api/courses")
    assert list_response.status_code == 200
    assert any(course["id"] == created["id"] for course in list_response.json())


def test_course_requires_login(client):
    token = client.headers.pop("Authorization", None)
    try:
        response = client.get("/api/courses")
    finally:
        if token:
            client.headers.update({"Authorization": token})

    assert response.status_code == 401


def test_reject_duplicate_course_name(client):
    payload = {"name": "重复课程", "description": ""}

    assert client.post("/api/courses", json=payload).status_code == 200
    duplicate_response = client.post("/api/courses", json=payload)

    assert duplicate_response.status_code == 409


def test_courses_are_scoped_to_logged_in_user(client):
    create_response = client.post(
        "/api/courses",
        json={"name": "用户一课程", "description": "只能被当前用户看到"},
    )
    assert create_response.status_code == 200

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "second@example.com",
            "password": "second-password",
            "display_name": "Second",
        },
    )
    assert register_response.status_code == 200
    second_headers = {"Authorization": f"Bearer {register_response.json()['access_token']}"}

    second_list = client.get("/api/courses", headers=second_headers)
    assert second_list.status_code == 200
    assert all(course["name"] != "用户一课程" for course in second_list.json())

    second_create = client.post(
        "/api/courses",
        json={"name": "用户一课程", "description": "同名但属于另一个用户"},
        headers=second_headers,
    )
    assert second_create.status_code == 200
