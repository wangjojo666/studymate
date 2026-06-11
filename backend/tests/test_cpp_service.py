from __future__ import annotations


def test_cpp_analyze_empty_payload_returns_400(client, auth_helpers):
    course = auth_helpers.create_course("CPP Empty")

    response = client.post(f"/api/courses/{course['id']}/cpp/analyze", json={})

    assert response.status_code == 400


def test_cpp_compile_success_or_graceful_no_gpp(client, auth_helpers):
    course = auth_helpers.create_course("CPP Success")
    code = '#include <iostream>\nusing namespace std;\nint main(){ cout << "ok"; return 0; }'

    response = client.post(
        f"/api/courses/{course['id']}/cpp/analyze",
        json={"user_code": code},
    )

    assert response.status_code == 200, response.text
    compile_result = response.json()["compile_result"]
    assert compile_result["compiler"] == "g++"
    if compile_result["compiler_available"]:
        assert compile_result["success"] is True
    else:
        assert "g++" in compile_result["stderr"]


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
    if compile_result["compiler_available"]:
        assert compile_result["success"] is False
        assert compile_result["errors"] or compile_result["stderr"]
        assert any(item["level"] == "error" for item in payload["error_diagnosis"])
    else:
        assert "g++" in compile_result["stderr"]


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
    if compile_result["compiler_available"]:
        assert compile_result["success"] is True
        assert run_result["executed"] is True
        assert "42" in run_result["stdout"]
    else:
        assert run_result["executed"] is False
        assert "g++" in compile_result["stderr"]
