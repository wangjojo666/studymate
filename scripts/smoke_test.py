from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid


BASE_URL = os.getenv("STUDYMATE_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
AUTH_TOKEN = ""
TERMINAL_DOCUMENT_STATUSES = {"indexed", "empty", "failed", "needs_ocr", "needs_vision"}


def main() -> int:
    global AUTH_TOKEN
    suffix = uuid.uuid4().hex[:8]
    course_name = f"Smoke Test {suffix}"
    course_id = None
    text = (
        "Virtual functions support runtime polymorphism through dynamic binding. "
        "When a base class pointer points to a derived object and calls an overridden "
        "virtual function, C++ chooses the derived implementation at runtime. "
        "Review virtual tables, overriding, base pointers, and derived objects together."
    )

    try:
        health = request_json("GET", "/health")
        print_step("health", health.get("status") == "ok", health)

        auth = request_json(
            "POST",
            "/auth/login",
            {
                "email": os.getenv("STUDYMATE_DEMO_EMAIL", "demo@studymate.local"),
                "password": os.getenv("STUDYMATE_DEMO_PASSWORD", "studymate-demo"),
            },
        )
        AUTH_TOKEN = auth["access_token"]
        print_step("login", bool(AUTH_TOKEN), {"user": auth.get("user")})

        course = request_json("POST", "/courses", {"name": course_name, "description": "smoke test"})
        course_id = course["id"]
        print_step("create course", bool(course_id), course)

        document = upload_txt(course_id, "polymorphism.txt", text)
        print_step(
            "upload txt",
            document.get("status") in {"queued", "uploaded", "parsing", "indexed"},
            document,
        )
        document = wait_document_indexed(course_id, document["id"], timeout_seconds=30, interval=1)
        print_step("wait indexed", document.get("status") == "indexed", document)

        answer = request_json(
            "POST",
            f"/courses/{course_id}/ask",
            {"question": "Why can virtual functions implement runtime polymorphism?", "top_k": 5},
        )
        print_step(
            "ask",
            bool(answer.get("answer"))
            and bool(answer.get("retrieval_provider"))
            and bool(answer.get("llm_provider")),
            {
                "llm_provider": answer.get("llm_provider"),
                "retrieval_provider": answer.get("retrieval_provider"),
                "sources": len(answer.get("sources") or []),
            },
        )

        outline = request_json("POST", f"/courses/{course_id}/review-outline")
        print_step("outline", bool(outline.get("content")), {"provider": outline.get("provider")})

        profile = request_json("GET", f"/courses/{course_id}/learning/profile")
        print_step("profile", str(profile.get("user_id", "")).isdigit(), profile.get("summary"))
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
    if AUTH_TOKEN:
        headers["Authorization"] = f"Bearer {AUTH_TOKEN}"
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: backend is unavailable: {exc}") from exc


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
        headers={
            "Authorization": f"Bearer {AUTH_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"upload failed: HTTP {exc.code} {detail}") from exc


def wait_document_indexed(
    course_id: int,
    document_id: int,
    timeout_seconds: int = 30,
    interval: float = 1.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_document: dict | None = None
    while time.monotonic() < deadline:
        course = request_json("GET", f"/courses/{course_id}")
        documents = course.get("documents") or []
        last_document = next((item for item in documents if item.get("id") == document_id), None)
        if last_document is None:
            raise RuntimeError(f"document {document_id} disappeared from course {course_id}")
        print(
            "[INFO] document status: "
            f"status={last_document.get('status')} "
            f"stage={last_document.get('processing_stage')} "
            f"progress={last_document.get('processing_progress')} "
            f"error={last_document.get('error_message') or ''}"
        )
        status = last_document.get("status")
        if status == "indexed":
            return last_document
        if status in TERMINAL_DOCUMENT_STATUSES:
            raise RuntimeError(
                f"document {document_id} ended with status={status}: "
                f"{last_document.get('error_message') or 'no error_message'}"
            )
        time.sleep(interval)
    raise RuntimeError(f"document {document_id} did not reach indexed within {timeout_seconds}s; last={last_document}")


def print_step(name: str, ok: bool, detail: object) -> None:
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {name}: {detail}")
    if not ok:
        raise RuntimeError(f"{name} check failed")


if __name__ == "__main__":
    sys.exit(main())
