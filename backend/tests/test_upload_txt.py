from __future__ import annotations


def _document_from_course(client, course_id: int, document_id: int) -> dict:
    course_detail = client.get(f"/api/courses/{course_id}")
    assert course_detail.status_code == 200
    return next(document for document in course_detail.json()["documents"] if document["id"] == document_id)


def test_upload_txt_then_ask_outline_and_profile(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "C++ 自动化验证", "description": "虚函数与多态"},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    text = (
        "虚函数可以通过动态绑定实现运行时多态。"
        "当基类指针指向派生类对象并调用被重写的虚函数时，程序会在运行期选择派生类实现。"
        "学习时要区分函数重载、函数重写和虚函数表。"
    )
    upload_response = client.post(
        f"/api/courses/{course_id}/documents",
        files={"file": ("polymorphism.txt", text.encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["status"] == "queued"
    assert uploaded["processing_stage"] == "uploaded"

    indexed_document = _document_from_course(client, course_id, uploaded["id"])
    assert indexed_document["status"] == "indexed"
    assert indexed_document["chunk_count"] >= 1

    ask_response = client.post(
        f"/api/courses/{course_id}/ask",
        json={"question": "虚函数为什么能实现运行时多态？", "top_k": 5},
    )
    assert ask_response.status_code == 200
    answer = ask_response.json()
    assert answer["provider"] == "mock/offline"
    assert answer["llm_provider"] == "mock/offline"
    assert answer["retrieval_provider"]
    assert "虚函数" in answer["answer"]
    assert answer["sources"]

    outline_response = client.post(f"/api/courses/{course_id}/review-outline")
    assert outline_response.status_code == 200
    assert outline_response.json()["provider"] == "mock/offline"

    profile_response = client.get(f"/api/courses/{course_id}/learning/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["user_id"].isdigit()
    assert profile["summary"]["knowledge_point_count"] >= 1


def test_delete_uploaded_document(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "资料删除验证", "description": ""},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    upload_response = client.post(
        f"/api/courses/{course_id}/documents",
        files={"file": ("delete-me.txt", "用于删除接口测试".encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 200
    document_id = upload_response.json()["id"]

    delete_response = client.delete(f"/api/courses/{course_id}/documents/{document_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["ok"] is True

    course_detail = client.get(f"/api/courses/{course_id}").json()
    assert course_detail["document_count"] == 0
    assert course_detail["documents"] == []


def test_reject_oversized_txt_upload(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "上传限制验证", "description": ""},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]
    oversized = b"x" * (10 * 1024 * 1024 + 1)

    upload_response = client.post(
        f"/api/courses/{course_id}/documents",
        files={"file": ("too-large.txt", oversized, "text/plain")},
    )

    assert upload_response.status_code == 413


def test_upload_image_courseware_with_mock_vision(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "多模态课件验证", "description": "公式图片与代码截图"},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    upload_response = client.post(
        f"/api/courses/{course_id}/documents",
        files={"file": ("virtual-function.png", b"fake-image-bytes", "image/png")},
    )

    assert upload_response.status_code == 200
    uploaded = upload_response.json()
    assert uploaded["status"] == "queued"
    assert uploaded["file_type"] == "png"
    indexed_document = _document_from_course(client, course_id, uploaded["id"])
    assert indexed_document["status"] == "indexed"
    assert indexed_document["chunk_count"] >= 1

    ask_response = client.post(
        f"/api/courses/{course_id}/ask",
        json={"question": "这张图片课件识别了什么？", "top_k": 5},
    )
    assert ask_response.status_code == 200
    assert ask_response.json()["sources"]


def test_cpp_code_analysis_identifies_exam_points(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "C++ 专项验证", "description": "继承、虚函数、友元、运算符重载"},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    code = """
class Base {
public:
    virtual void show() {}
};
class Derived : public Base {
public:
    void show() override {}
    friend ostream& operator<<(ostream& out, const Derived& d);
};
"""
    response = client.post(
        f"/api/courses/{course_id}/cpp/analyze",
        json={
            "problem_text": "分析下面代码的面向对象考点。",
            "code_text": code,
            "user_code": "class Derived : public Base { public: void show() {} };",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    point_names = {point["name"] for point in payload["exam_points"]}
    assert "继承与派生" in point_names
    assert "虚函数与多态" in point_names
    assert payload["similar_exercises"]
    assert payload["error_diagnosis"]
    assert "compile_result" in payload
    assert "run_result" in payload


def test_learning_report_pdf_export(client):
    course_response = client.post(
        "/api/courses",
        json={"name": "报告导出验证", "description": "学习报告"},
    )
    assert course_response.status_code == 200
    course_id = course_response.json()["id"]

    response = client.get(f"/api/courses/{course_id}/learning/report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
