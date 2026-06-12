from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.getenv("STUDYMATE_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run simple StudyMate RAG retrieval checks.")
    parser.add_argument(
        "cases",
        nargs="?",
        default=str(Path("docs") / "rag_eval_cases.example.json"),
        help="JSON file containing course_id, question, expected_keywords and expected_source_hint.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="RAG top_k passed to the ask API.")
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases))
    token = os.getenv("STUDYMATE_API_TOKEN") or _login()
    results = [_run_case(token, case, args.top_k, index) for index, case in enumerate(cases, start=1)]

    print(json.dumps({"base_url": BASE_URL, "results": results}, ensure_ascii=False, indent=2))
    passed = sum(1 for item in results if item["keyword_hit"] and item["source_hint_hit"])
    print(f"\nSummary: {passed}/{len(results)} cases matched both keyword and source hint checks.")
    return 0 if results else 1


def _load_cases(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"case file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise SystemExit("case file must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _login() -> str:
    payload = {
        "email": os.getenv("STUDYMATE_DEMO_EMAIL", "demo@studymate.local"),
        "password": os.getenv("STUDYMATE_DEMO_PASSWORD", "studymate-demo"),
    }
    data = _request_json("POST", "/auth/login", payload, token="")
    return str(data["access_token"])


def _run_case(token: str, case: dict[str, Any], top_k: int, index: int) -> dict[str, Any]:
    course_id = case.get("course_id")
    question = str(case.get("question") or "").strip()
    expected_keywords = [str(item) for item in case.get("expected_keywords") or []]
    expected_source_hint = str(case.get("expected_source_hint") or "").strip()
    if not course_id or not question:
        return {"index": index, "error": "course_id and question are required"}

    response = _request_json(
        "POST",
        f"/courses/{course_id}/ask",
        {"question": question, "top_k": top_k},
        token=token,
    )
    answer = str(response.get("answer") or "")
    sources = response.get("sources") or []
    keyword_hits = [keyword for keyword in expected_keywords if keyword and keyword in answer]
    source_hint_hit = _source_hint_hit(sources, expected_source_hint)
    return {
        "index": index,
        "course_id": course_id,
        "question": question,
        "answer_status": response.get("answer_status"),
        "confidence": response.get("confidence"),
        "retrieval_provider": response.get("retrieval_provider"),
        "llm_provider": response.get("llm_provider"),
        "keyword_hit": not expected_keywords or len(keyword_hits) == len(expected_keywords),
        "keyword_hits": keyword_hits,
        "source_hint_hit": not expected_source_hint or source_hint_hit,
        "top_sources": [
            {
                "document_name": item.get("document_name"),
                "page": item.get("page"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "preview": item.get("preview"),
            }
            for item in sources[:top_k]
        ],
    }


def _source_hint_hit(sources: list[dict[str, Any]], hint: str) -> bool:
    if not hint:
        return True
    return any(hint in f"{item.get('document_name', '')} {item.get('preview', '')}" for item in sources)


def _request_json(method: str, path: str, payload: dict[str, Any] | None = None, token: str = "") -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise SystemExit(f"{method} {path} failed: HTTP {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"{method} {path} failed: backend unavailable: {exc}") from exc


if __name__ == "__main__":
    sys.exit(main())
