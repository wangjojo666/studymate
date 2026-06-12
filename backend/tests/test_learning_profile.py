from __future__ import annotations


def test_mastery_formula_explains_wrong_attempt(client, auth_helpers):
    course = auth_helpers.create_course("Mastery Formula")
    profile_response = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert profile_response.status_code == 200, profile_response.text
    point = profile_response.json()["knowledge_points"][0]
    assert point["mastery_score"] == 60.0
    assert point["explanation"]
    assert point["mastery_formula"]
    assert point["recent_attempts_summary"]
    assert point["next_action"]
    assert "初始掌握度" in point["mastery_formula"]

    attempt_response = client.post(
        f"/api/courses/{course['id']}/learning/attempts",
        json={
            "knowledge_point_id": point["id"],
            "question_text": "写出该概念的定义并说明适用条件",
            "user_answer": "不会",
            "correct_answer": "应写清定义、条件和反例。",
            "is_correct": False,
            "error_reason": "公式/定义记忆错误",
            "difficulty": "exam",
        },
    )
    assert attempt_response.status_code == 200, attempt_response.text
    status = attempt_response.json()["knowledge_status"]
    assert status["mastery_score"] == 42.0
    assert status["wrong_count"] == 1
    assert status["main_error_type"] == "formula_error"
    assert "公式/定义记忆错误" in status["explanation"]
    assert "答错" in status["recent_attempts_summary"]
    assert "当前" in status["next_action"]


def test_correct_attempt_increases_mastery(client, auth_helpers):
    course = auth_helpers.create_course("Correct Attempt")
    profile_response = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert profile_response.status_code == 200, profile_response.text
    point = profile_response.json()["knowledge_points"][0]
    assert point["mastery_score"] == 60.0

    attempt_response = client.post(
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
    assert attempt_response.status_code == 200, attempt_response.text

    updated_profile = client.get(f"/api/courses/{course['id']}/learning/profile").json()
    updated_point = _point_by_id(updated_profile, point["id"])
    assert updated_point["mastery_score"] > 60
    assert updated_point["correct_count"] == 1
    assert updated_point["wrong_count"] == 0
    assert "答对 1 次" in updated_point["explanation"]


def test_wrong_attempt_creates_review_task(client, auth_helpers):
    course = auth_helpers.create_course("Wrong Attempt")
    profile_response = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert profile_response.status_code == 200, profile_response.text
    point = profile_response.json()["knowledge_points"][0]

    attempt_response = client.post(
        f"/api/courses/{course['id']}/learning/attempts",
        json={
            "knowledge_point_id": point["id"],
            "question_text": "exam check",
            "user_answer": "wrong",
            "correct_answer": "right",
            "is_correct": False,
            "error_reason": "概念混淆",
            "difficulty": "exam",
        },
    )
    assert attempt_response.status_code == 200, attempt_response.text

    updated_profile = client.get(f"/api/courses/{course['id']}/learning/profile")
    assert updated_profile.status_code == 200, updated_profile.text
    payload = updated_profile.json()
    tasks = payload["pending_tasks"]
    assert tasks
    assert any(
        task["knowledge_point_id"] == point["id"]
        or point["name"] in task["title"]
        or point["name"] in task["description"]
        for task in tasks
    )
    weak_point = _point_by_id({"knowledge_points": payload["weak_points"]}, point["id"])
    assert weak_point["wrong_count"] >= 1


def test_error_type_classification():
    from app.services.mastery_service import classify_error_type

    assert classify_error_type("公式/定义记忆错误") == "formula_error"
    assert classify_error_type("步骤跳跃，推导过程漏了一步") == "procedure_gap"
    assert classify_error_type("语法错误，少分号") == "coding_syntax"
    assert classify_error_type("粗心看错题") == "careless"
    assert classify_error_type("概念混淆") == "concept_confusion"
    assert classify_error_type("不知道") == "unknown"


def test_ask_without_documents_returns_friendly_message(client, auth_helpers):
    course = auth_helpers.create_course("No Documents")

    response = client.post(
        f"/api/courses/{course['id']}/ask",
        json={"question": "这门课重点是什么？", "top_k": 5},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["sources"] == []
    assert payload["llm_provider"] == "system"
    assert payload["answer"]


def _point_by_id(profile: dict, point_id: int) -> dict:
    return next(point for point in profile["knowledge_points"] if point["id"] == point_id)
