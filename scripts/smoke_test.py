from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


BASE_URL = os.getenv("STUDYMATE_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    course_name = f"Smoke Test {suffix}"
    course_id = None
    text = (
        "虚函数可以通过动态绑定实现运行时多态。"
        "当基类指针指向派生类对象并调用被重写的虚函数时，程序会在运行期选择派生类实现。"
        "复习时要关注虚函数表、函数重写、基类指针和派生类对象之间的关系。"
    )

    try:
        health = request_json("GET", "/health")
        print_step("health", health.get("status") == "ok", health)

        course = request_json("POST", "/courses", {"name": course_name, "description": "smoke test"})
        course_id = course["id"]
        print_step("create course", bool(course_id), course)

        document = upload_txt(course_id, "polymorphism.txt", text)
        print_step("upload txt", document.get("status") == "indexed", document)

        answer = request_json(
            "POST",
            f"/courses/{course_id}/ask",
            {"question": "虚函数为什么能实现运行时多态？", "top_k": 5},
        )
        print_step("ask", bool(answer.get("answer")), {"provider": answer.get("provider")})

        outline = request_json("POST", f"/courses/{course_id}/review-outline")
        print_step("outline", bool(outline.get("content")), {"provider": outline.get("provider")})

        profile = request_json("GET", f"/courses/{course_id}/learning/profile")
        print_step("profile", profile.get("user_id") == "demo-user", profile.get("summary"))
    except Exception as exc:  # noqa: BLE001 - smoke test should print actionable failure.
        print(f"[FAIL] {exc}")
        return 1
    finally:
        if course_id is not None:
            try:
                request_json("DELETE", f"/courses/{course_id}")
                print_step("cleanup", True, {"course_id": course_id})
            except Exception as exc:  # noqa: BLE001 - cleanup failure should not hide the main result.
                print(f"[WARN] cleanup failed for course_id={course_id}: {exc}")
    return 0


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def upload_txt(course_id: int, filename: str, content: str) -> dict:
    boundary = f"----studymate-smoke-{int(time.time())}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
    ).encode("utf-8")
    body += content.encode("utf-8")
    body += f"\r\n--{boundary}--\r\n".encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}/courses/{course_id}/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"upload failed: HTTP {exc.code} {detail}") from exc


def print_step(name: str, ok: bool, detail: object) -> None:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        raise RuntimeError(f"{name} check failed")


if __name__ == "__main__":
    sys.exit(main())
