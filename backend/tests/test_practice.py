from __future__ import annotations


def test_generate_practice_returns_structured_items(client, auth_helpers):
    course = auth_helpers.create_course("Structured Practice")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "Virtual functions use dynamic dispatch. Override methods through a base pointer to achieve runtime polymorphism.",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    response = client.post(
        f"/api/courses/{course['id']}/practice",
        json={"count": 3, "difficulty": "basic"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["content"]
    assert payload["sources"]
    assert len(payload["items"]) == 3
    first = payload["items"][0]
    assert first["question_type"]
    assert first["question"]
    assert first["reference_answer"]
    assert first["explanation"]
    assert first["knowledge_points"]
    assert first["sources"]
    assert first["sources"][0]["chunk_id"]


def test_practice_attempt_updates_mastery(client, auth_helpers):
    course = auth_helpers.create_course("Practice Attempt Mastery")
    uploaded = auth_helpers.upload_text_file(
        course["id"],
        "A virtual function enables runtime polymorphism through overriding and dynamic dispatch.",
    )
    auth_helpers.wait_document_done(course["id"], uploaded["id"])

    profile = client.get(f"/api/courses/{course['id']}/learning/profile").json()
    point = profile["knowledge_points"][0]
    practice = client.post(
        f"/api/courses/{course['id']}/practice",
        json={"count": 1, "difficulty": "exam", "knowledge_point_id": point["id"]},
    ).json()
    item = practice["items"][0]

    response = client.post(
        f"/api/courses/{course['id']}/learning/attempts",
        json={
            "knowledge_point_id": point["id"],
            "question_text": item["question"],
            "user_answer": "wrong",
            "correct_answer": item["reference_answer"],
            "is_correct": False,
            "error_reason": "概念混淆",
            "difficulty": "exam",
        },
    )

    assert response.status_code == 200, response.text
    status = response.json()["knowledge_status"]
    assert status["mastery_score"] < point["mastery_score"]
    assert status["wrong_count"] == 1


def test_generate_practice_without_materials_returns_friendly_message(client, auth_helpers):
    course = auth_helpers.create_course("Practice Empty Materials")

    response = client.post(
        f"/api/courses/{course['id']}/practice",
        json={"count": 2, "difficulty": "basic"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["items"] == []
    assert payload["sources"] == []
    assert "还没有可用于生成练习题的资料" in payload["content"]
    assert payload["provider"] == "system"
