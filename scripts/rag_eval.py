from __future__ import annotations

import argparse
import html
import json
import os
import sys
import time
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
    parser.add_argument(
        "--output-dir",
        default=str(Path("rag_eval_reports")),
        help="Directory for JSON and HTML reports.",
    )
    parser.add_argument("--json-out", default="", help="Optional explicit JSON report path.")
    parser.add_argument("--html-out", default="", help="Optional explicit HTML report path.")
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases))
    token = os.getenv("STUDYMATE_API_TOKEN") or _login()
    results = [_run_case(token, case, args.top_k, index) for index, case in enumerate(cases, start=1)]
    report = {"base_url": BASE_URL, "case_file": str(args.cases), "results": results}
    json_path, html_path = _report_paths(args)
    _write_json_report(json_path, report)
    _write_html_report(html_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    passed = sum(1 for item in results if item["keyword_hit"] and item["source_hint_hit"])
    print(f"\nSummary: {passed}/{len(results)} cases matched both keyword and source hint checks.")
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
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

    started = time.perf_counter()
    response = _request_json(
        "POST",
        f"/courses/{course_id}/ask",
        {"question": question, "top_k": top_k},
        token=token,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
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
        "provider": response.get("provider") or response.get("llm_provider"),
        "retrieval_provider": response.get("retrieval_provider"),
        "llm_provider": response.get("llm_provider"),
        "elapsed_ms": elapsed_ms,
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


def _report_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = Path(args.json_out) if args.json_out else output_dir / "rag_eval_report.json"
    html_path = Path(args.html_out) if args.html_out else output_dir / "rag_eval_report.html"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    return json_path, html_path


def _write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_html_report(path: Path, report: dict[str, Any]) -> None:
    rows = []
    for item in report["results"]:
        if item.get("error"):
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(item.get('index')))}</td>"
                f"<td colspan='8'>{html.escape(str(item.get('error')))}</td>"
                "</tr>"
            )
            continue
        sources = "<br>".join(
            html.escape(
                f"{source.get('document_name')} P{source.get('page')} chunk {source.get('chunk_index')} "
                f"score {source.get('score')}: {source.get('preview')}"
            )
            for source in item.get("top_sources", [])
        )
        rows.append(
            "<tr>"
            f"<td>{item.get('index')}</td>"
            f"<td>{html.escape(str(item.get('question')))}</td>"
            f"<td>{html.escape(str(item.get('answer_status')))}</td>"
            f"<td>{html.escape(str(item.get('confidence')))}</td>"
            f"<td>{html.escape(str(item.get('provider')))}</td>"
            f"<td>{html.escape(str(item.get('retrieval_provider')))}</td>"
            f"<td>{html.escape(str(item.get('elapsed_ms')))} ms</td>"
            f"<td>{'yes' if item.get('keyword_hit') else 'no'} / {'yes' if item.get('source_hint_hit') else 'no'}</td>"
            f"<td>{sources}</td>"
            "</tr>"
        )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>StudyMate RAG Eval Report</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #0f172a; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px; vertical-align: top; font-size: 14px; }}
    th {{ background: #f8fafc; text-align: left; }}
    caption {{ text-align: left; margin-bottom: 12px; font-weight: 700; }}
  </style>
</head>
<body>
  <h1>StudyMate RAG Eval Report</h1>
  <p>Base URL: {html.escape(str(report.get("base_url")))}</p>
  <p>Case file: {html.escape(str(report.get("case_file")))}</p>
  <table>
    <caption>Cases</caption>
    <thead>
      <tr>
        <th>#</th>
        <th>Question</th>
        <th>Status</th>
        <th>Confidence</th>
        <th>Provider</th>
        <th>Retrieval</th>
        <th>Elapsed</th>
        <th>Keyword / Source Hit</th>
        <th>Top Sources</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


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
