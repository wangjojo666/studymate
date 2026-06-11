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
