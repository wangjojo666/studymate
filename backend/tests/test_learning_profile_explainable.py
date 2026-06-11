from __future__ import annotations


def test_correct_attempt_increases_mastery(client, auth_helpers):
    course = auth_helpers.create_course("Correct Attempt")
    profile_response = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert profile_response.status_code == 200, profile_response.text
    point = profile_response.json()["knowledge_points"][0]

    response = client.post(
        f"/api/courses/{course['id']}/learning/attempts",
        json={
            "knowledge_point_id": point["id"],
            "question_text": "basic check",
            "user_answer": "correct",
            "correct_answer": "correct",
            "is_correct": True,
            "error_reason": "",
            "difficulty": "basic",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["knowledge_status"]["mastery_score"] > 60


def test_wrong_attempt_creates_review_task(client, auth_helpers):
    course = auth_helpers.create_course("Wrong Attempt")
    profile_response = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert profile_response.status_code == 200, profile_response.text
    point = profile_response.json()["knowledge_points"][0]

    response = client.post(
        f"/api/courses/{course['id']}/learning/attempts",
        json={
            "knowledge_point_id": point["id"],
            "question_text": "exam check",
            "user_answer": "wrong",
            "correct_answer": "right",
            "is_correct": False,
            "error_reason": "concept confusion",
            "difficulty": "exam",
        },
    )
    assert response.status_code == 200, response.text

    updated = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert updated.status_code == 200, updated.text
    tasks = updated.json()["pending_tasks"]
    assert any(task["knowledge_point_id"] == point["id"] for task in tasks)


def test_error_type_classification():
    from app.services.mastery_service import classify_error_type

    assert classify_error_type("公式/定义记忆错误") == "formula_error"
    assert classify_error_type("步骤跳跃") == "procedure_gap"
    assert classify_error_type("语法错误，少分号") == "coding_syntax"
    assert classify_error_type("粗心看错题") == "careless"
    assert classify_error_type("概念混淆") == "concept_confusion"
