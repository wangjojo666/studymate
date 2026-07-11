from __future__ import annotations


def test_dashboard_summary_aggregates_every_course(client, auth_helpers):
    user = auth_helpers.create_user_and_login()
    courses = [
        auth_helpers.create_course(f"Dashboard Aggregate {index}", headers=user["headers"])
        for index in range(1, 6)
    ]

    first_response = client.get("/api/courses/dashboard-summary", headers=user["headers"])
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["summary"]["course_count"] == 5
    assert first_response.json()["summary"]["knowledge_point_count"] == 25

    from app.database import SessionLocal
    from app.models.entities import KnowledgePoint

    fifth_course = courses[-1]
    with SessionLocal() as db:
        point = (
            db.query(KnowledgePoint).filter(KnowledgePoint.course_id == fifth_course["id"]).first()
        )
        point_id = point.id
    attempt_response = client.post(
        f"/api/courses/{fifth_course['id']}/learning/attempts",
        headers=user["headers"],
        json={
            "knowledge_point_id": point_id,
            "question_text": "aggregate weak point regression",
            "user_answer": "wrong",
            "correct_answer": "correct",
            "is_correct": False,
            "difficulty": "exam",
        },
    )
    assert attempt_response.status_code == 200, attempt_response.text

    response = client.get("/api/courses/dashboard-summary", headers=user["headers"])
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["courses"]) == 5
    assert payload["summary"]["course_count"] == 5
    assert payload["summary"]["knowledge_point_count"] == 25
    assert payload["summary"]["weak_point_count"] == 1
    assert payload["weak_points"][0]["course_id"] == fifth_course["id"]
    assert payload["weak_points"][0]["course_name"] == fifth_course["name"]
    assert all("course_id" in item and "course_name" in item for item in payload["recommendations"])
