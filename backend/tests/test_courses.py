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


def test_reject_duplicate_course_name(client):
    payload = {"name": "重复课程", "description": ""}

    assert client.post("/api/courses", json=payload).status_code == 200
    duplicate_response = client.post("/api/courses", json=payload)

    assert duplicate_response.status_code == 409
