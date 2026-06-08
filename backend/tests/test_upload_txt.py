from __future__ import annotations


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
    assert uploaded["status"] == "indexed"
    assert uploaded["chunk_count"] >= 1

    ask_response = client.post(
        f"/api/courses/{course_id}/ask",
        json={"question": "虚函数为什么能实现运行时多态？", "top_k": 5},
    )
    assert ask_response.status_code == 200
    answer = ask_response.json()
    assert answer["provider"] == "mock/offline"
    assert "虚函数" in answer["answer"]
    assert answer["sources"]

    outline_response = client.post(f"/api/courses/{course_id}/review-outline")
    assert outline_response.status_code == 200
    assert outline_response.json()["provider"] == "mock/offline"

    profile_response = client.get(f"/api/courses/{course_id}/learning/profile")
    assert profile_response.status_code == 200
    profile = profile_response.json()
    assert profile["user_id"] == "demo-user"
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
