from __future__ import annotations


def test_cpp_analyze_empty_payload_returns_400(client, auth_helpers):
    course = auth_helpers.create_course("CPP Empty")

    response = client.post(f"/api/courses/{course['id']}/cpp/analyze", json={})

    assert response.status_code == 400


def test_cpp_run_disabled_does_not_execute_compile_or_run(client, auth_helpers):
    course = auth_helpers.create_course("CPP Safe Mode")
    code = '#include <iostream>\nusing namespace std;\nint main(){ cout << "ok"; return 0; }'

    response = client.post(
        f"/api/courses/{course['id']}/cpp/analyze",
        json={"user_code": code},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    compile_result = payload["compile_result"]
    run_result = payload["run_result"]
    assert payload["sandbox_level"] == "disabled"
    assert compile_result["compiler"] == "g++"
    assert compile_result["executed"] is False
    assert compile_result["success"] is False
    assert run_result["executed"] is False
    assert "安全演示模式" in compile_result["stderr"]


def test_cpp_compile_error_reported(client, auth_helpers):
    course = auth_helpers.create_course("CPP Error")
    code = '#include <iostream>\nusing namespace std;\nint main(){ cout << "ok" return 0; }'

    response = client.post(
        f"/api/courses/{course['id']}/cpp/analyze",
        json={"user_code": code},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    compile_result = payload["compile_result"]
    assert payload["sandbox_level"] == "disabled"
    assert compile_result["executed"] is False
    assert any(item["title"] == "安全演示模式" for item in payload["error_diagnosis"])


def test_cpp_sample_run_output(client, auth_helpers):
    course = auth_helpers.create_course("CPP Run")
    code = "#include <iostream>\nusing namespace std;\nint main(){ int x; cin >> x; cout << x + 1; }"

    response = client.post(
        f"/api/courses/{course['id']}/cpp/analyze",
        json={"user_code": code, "sample_input": "41"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    compile_result = payload["compile_result"]
    run_result = payload["run_result"]
    assert payload["sandbox_level"] == "disabled"
    assert compile_result["executed"] is False
    assert run_result["executed"] is False
