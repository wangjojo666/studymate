from __future__ import annotations


def test_courses_require_auth(unauthenticated_client):
    response = unauthenticated_client.get("/api/courses")

    assert response.status_code in {401, 403}


def test_course_isolation_between_users(client, auth_helpers):
    course = auth_helpers.create_course("Owner Course")
    other_user = auth_helpers.create_user_and_login()

    detail_response = client.get(f"/api/courses/{course['id']}", headers=other_user["headers"])
    delete_response = client.delete(f"/api/courses/{course['id']}", headers=other_user["headers"])
    upload_response = client.post(
        f"/api/courses/{course['id']}/documents",
        files={"file": ("stolen.txt", b"should not upload", "text/plain")},
        headers=other_user["headers"],
    )

    assert detail_response.status_code == 404
    assert delete_response.status_code == 404
    assert upload_response.status_code == 404
