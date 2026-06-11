from __future__ import annotations


def test_mastery_formula_explains_wrong_attempt(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "掌握度公式验证", "description": "测试学习画像解释"},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    profile_response = client.get(f"/api/courses/{course_id}/learning/profile")
    assert profile_response.status_code == 200
    point = profile_response.json()["knowledge_points"][0]
    assert point["mastery_score"] == 60.0
    assert point["explanation"]

    attempt_response = client.post(
        f"/api/courses/{course_id}/learning/attempts",
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
    assert attempt_response.status_code == 200
    status = attempt_response.json()["knowledge_status"]
    assert status["mastery_score"] == 42.0
    assert status["wrong_count"] == 1
    assert status["main_error_type"] == "formula_error"
    assert "公式/定义记忆错误" in status["explanation"]


def test_ask_without_documents_returns_friendly_message(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "空资料问答验证", "description": ""},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    response = client.post(
        f"/api/courses/{course_id}/ask",
        json={"question": "这门课重点是什么？", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == []
    assert payload["llm_provider"] == "system"
    assert "上传" in payload["answer"]
