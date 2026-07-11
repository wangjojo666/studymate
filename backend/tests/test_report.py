from __future__ import annotations


def test_report_pdf_returns_pdf(client, auth_helpers):
    course = auth_helpers.create_course("Report PDF")

    response = client.get(f"/api/courses/{course['id']}/learning/report.pdf")

    assert response.status_code == 200, response.text
    assert "application/pdf" in response.headers["content-type"]
    assert response.content.startswith(b"%PDF")


def test_report_with_empty_data_does_not_crash(client, auth_helpers):
    course = auth_helpers.create_course("Empty Report")

    response = client.get(f"/api/courses/{course['id']}/learning/report.pdf")

    assert response.status_code == 200, response.text
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 100


def test_report_failure_is_logged_without_leaking_internal_details(
    client, auth_helpers, monkeypatch
):
    from app.routers import learning

    course = auth_helpers.create_course("Broken Report")
    internal_detail = "font missing at C:/private/fonts/internal.ttf"
    logged = []

    def fail_report(*_args, **_kwargs):
        raise RuntimeError(internal_detail)

    monkeypatch.setattr(learning, "generate_learning_report_pdf", fail_report)
    monkeypatch.setattr(learning.logger, "exception", lambda *args: logged.append(args))

    response = client.get(f"/api/courses/{course['id']}/learning/report.pdf")

    assert response.status_code == 500
    assert response.json()["detail"] == "学习报告生成失败，请稍后重试"
    assert internal_detail not in response.text
    assert logged
