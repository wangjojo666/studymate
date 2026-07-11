from __future__ import annotations

import argparse
import html
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

BASE_URL = os.getenv("STUDYMATE_API_BASE_URL", "http://127.0.0.1:8000/api").rstrip("/")
QUALITY_METRICS = ("hit_at_k", "mrr", "refusal_accuracy", "citation_correctness")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run StudyMate RAG retrieval and refusal checks.")
    parser.add_argument(
        "cases",
        nargs="?",
        default=str(Path("docs") / "rag_eval_cases.example.json"),
        help="JSON evaluation cases.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="RAG top_k passed to the ask API.")
    parser.add_argument(
        "--output-dir", default="rag_eval_reports", help="JSON/HTML report directory."
    )
    parser.add_argument("--json-out", default="", help="Optional explicit JSON report path.")
    parser.add_argument("--html-out", default="", help="Optional explicit HTML report path.")
    parser.add_argument("--baseline", default="", help="Previous JSON report used as a baseline.")
    parser.add_argument(
        "--max-quality-drop",
        type=float,
        default=0.02,
        help="Maximum allowed absolute drop for quality metrics.",
    )
    parser.add_argument(
        "--max-latency-increase-pct",
        type=float,
        default=25.0,
        help="Maximum allowed average/P95 latency increase versus baseline.",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit non-zero when baseline comparison exceeds allowed regression.",
    )
    args = parser.parse_args()

    cases = _load_cases(Path(args.cases))
    if not cases:
        raise SystemExit("case file does not contain any evaluation cases")
    token = os.getenv("STUDYMATE_API_TOKEN") or _login()
    results = [
        _run_case(token, case, args.top_k, index) for index, case in enumerate(cases, start=1)
    ]
    metrics = _aggregate_metrics(results)
    baseline_comparison = None
    if args.baseline:
        baseline = _load_report(Path(args.baseline))
        baseline_comparison = _compare_to_baseline(
            metrics,
            baseline.get("metrics") or baseline,
            max_quality_drop=max(0.0, args.max_quality_drop),
            max_latency_increase_pct=max(0.0, args.max_latency_increase_pct),
        )
    report = {
        "schema_version": 2,
        "generated_at": datetime.now(UTC).isoformat(),
        "base_url": BASE_URL,
        "case_file": str(args.cases),
        "top_k": args.top_k,
        "metrics": metrics,
        "baseline_comparison": baseline_comparison,
        "results": results,
    }
    json_path, html_path = _report_paths(args)
    _write_json_report(json_path, report)
    _write_html_report(html_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        f"\nSummary: {metrics['passed_cases']}/{metrics['evaluated_cases']} cases passed; "
        f"Hit@K={_format_metric(metrics['hit_at_k'])}, MRR={_format_metric(metrics['mrr'])}, "
        f"refusal={_format_metric(metrics['refusal_accuracy'])}, "
        f"citation={_format_metric(metrics['citation_correctness'])}."
    )
    print(f"JSON report: {json_path}")
    print(f"HTML report: {html_path}")
    if args.fail_on_regression and baseline_comparison and not baseline_comparison["passed"]:
        return 2
    return 0 if metrics["failed_cases"] == 0 else 1


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path, "case file")
    if not isinstance(payload, list):
        raise SystemExit("case file must be a JSON array")
    return [item for item in payload if isinstance(item, dict)]


def _load_report(path: Path) -> dict[str, Any]:
    payload = _load_json(path, "baseline report")
    if not isinstance(payload, dict):
        raise SystemExit("baseline report must be a JSON object")
    return payload


def _load_json(path: Path, label: str) -> Any:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


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
    if not course_id or not question:
        return {
            "index": index,
            "case_id": case.get("id"),
            "passed": False,
            "error": "course_id and question are required",
        }

    started = time.perf_counter()
    response = _request_json(
        "POST",
        f"/courses/{course_id}/ask",
        {"question": question, "top_k": top_k},
        token=token,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    answer = str(response.get("answer") or "")
    sources = [item for item in response.get("sources") or [] if isinstance(item, dict)]
    expected_keywords = [str(item) for item in case.get("expected_keywords") or []]
    forbidden_keywords = [str(item) for item in case.get("forbidden_answer_keywords") or []]
    keyword_hits = [keyword for keyword in expected_keywords if keyword.lower() in answer.lower()]
    forbidden_hits = [
        keyword for keyword in forbidden_keywords if keyword.lower() in answer.lower()
    ]
    expected_statuses = _expected_statuses(case)
    answer_status = str(response.get("answer_status") or "")
    status_correct = answer_status in expected_statuses if expected_statuses else None
    expected_refusal = _expected_refusal(case, expected_statuses)
    actual_refusal = answer_status != "answered"
    refusal_correct = actual_refusal == expected_refusal if expected_refusal is not None else None
    relevance = _source_relevance(sources, case)
    relevant_rank = next(
        (rank for rank, is_relevant in enumerate(relevance, start=1) if is_relevant), None
    )
    relevance_labeled = _has_relevance_labels(case)
    hit_at_k = relevant_rank is not None if relevance_labeled else None
    reciprocal_rank = (
        round(1.0 / relevant_rank, 6) if relevant_rank else (0.0 if relevance_labeled else None)
    )
    citation_correct = _citation_correctness(sources, case)
    keyword_correct = not expected_keywords or len(keyword_hits) == len(expected_keywords)
    forbidden_correct = not forbidden_hits
    checks = [keyword_correct, forbidden_correct]
    checks.extend(
        value for value in (status_correct, refusal_correct, citation_correct) if value is not None
    )
    passed = all(checks)

    return {
        "index": index,
        "case_id": case.get("id") or f"case-{index}",
        "case_type": case.get("case_type") or "answerable",
        "course_id": course_id,
        "question": question,
        "answer": answer,
        "answer_status": answer_status,
        "confidence": response.get("confidence"),
        "provider": response.get("provider") or response.get("llm_provider"),
        "retrieval_provider": response.get("retrieval_provider"),
        "llm_provider": response.get("llm_provider"),
        "elapsed_ms": elapsed_ms,
        "passed": passed,
        "status_correct": status_correct,
        "expected_refusal": expected_refusal,
        "refusal_correct": refusal_correct,
        "keyword_hit": keyword_correct,
        "keyword_hits": keyword_hits,
        "forbidden_answer_hit": forbidden_hits,
        "hit_at_k": hit_at_k,
        "reciprocal_rank": reciprocal_rank,
        "citation_correct": citation_correct,
        "relevant_rank": relevant_rank,
        "top_sources": [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "document_name": item.get("document_name"),
                "page": item.get("page"),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "preview": item.get("preview"),
                "relevant": relevance[source_index] if source_index < len(relevance) else False,
            }
            for source_index, item in enumerate(sources[:top_k])
        ],
    }


def _expected_statuses(case: dict[str, Any]) -> set[str]:
    raw = case.get("expected_answer_status")
    if raw is None:
        return set()
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return {str(raw)}


def _expected_refusal(case: dict[str, Any], expected_statuses: set[str]) -> bool | None:
    if "expect_refusal" in case:
        return bool(case["expect_refusal"])
    if expected_statuses:
        return "answered" not in expected_statuses
    return None


def _source_hints(case: dict[str, Any]) -> list[str]:
    hints = [
        str(item).strip() for item in case.get("expected_source_hints") or [] if str(item).strip()
    ]
    legacy_hint = str(case.get("expected_source_hint") or "").strip()
    if legacy_hint:
        hints.append(legacy_hint)
    return hints


def _expected_chunk_ids(case: dict[str, Any]) -> set[int]:
    result: set[int] = set()
    for value in case.get("expected_chunk_ids") or []:
        try:
            result.add(int(value))
        except (TypeError, ValueError):
            continue
    return result


def _has_relevance_labels(case: dict[str, Any]) -> bool:
    return bool(_source_hints(case) or _expected_chunk_ids(case))


def _source_relevance(sources: list[dict[str, Any]], case: dict[str, Any]) -> list[bool]:
    hints = [hint.lower() for hint in _source_hints(case)]
    chunk_ids = _expected_chunk_ids(case)
    result: list[bool] = []
    for item in sources:
        haystack = f"{item.get('document_name', '')} {item.get('preview', '')}".lower()
        try:
            chunk_id = int(item.get("chunk_id") or 0)
        except (TypeError, ValueError):
            chunk_id = 0
        result.append(any(hint in haystack for hint in hints) or chunk_id in chunk_ids)
    return result


def _citation_correctness(sources: list[dict[str, Any]], case: dict[str, Any]) -> bool | None:
    hints = [hint.lower() for hint in _source_hints(case)]
    chunk_ids = _expected_chunk_ids(case)
    minimum_documents = int(case.get("minimum_source_documents") or 0)
    if not hints and not chunk_ids and not minimum_documents:
        return None
    source_texts = [
        f"{item.get('document_name', '')} {item.get('preview', '')}".lower() for item in sources
    ]
    returned_chunk_ids: set[int] = set()
    for item in sources:
        try:
            returned_chunk_ids.add(int(item.get("chunk_id") or 0))
        except (TypeError, ValueError):
            continue
    unique_documents = {item.get("document_id") or item.get("document_name") for item in sources}
    unique_documents.discard(None)
    return (
        all(any(hint in source_text for source_text in source_texts) for hint in hints)
        and chunk_ids.issubset(returned_chunk_ids)
        and len(unique_documents) >= minimum_documents
    )


def _aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid = [item for item in results if not item.get("error")]
    latencies = [float(item["elapsed_ms"]) for item in valid]
    return {
        "evaluated_cases": len(results),
        "passed_cases": sum(1 for item in results if item.get("passed")),
        "failed_cases": sum(1 for item in results if not item.get("passed")),
        "pass_rate": round(sum(1 for item in results if item.get("passed")) / len(results), 6)
        if results
        else 0.0,
        "hit_at_k": _mean_optional(item.get("hit_at_k") for item in valid),
        "mrr": _mean_optional(item.get("reciprocal_rank") for item in valid),
        "refusal_accuracy": _mean_optional(item.get("refusal_correct") for item in valid),
        "citation_correctness": _mean_optional(item.get("citation_correct") for item in valid),
        "average_latency_ms": round(mean(latencies), 2) if latencies else 0.0,
        "p95_latency_ms": _percentile(latencies, 0.95),
    }


def _mean_optional(values: Any) -> float | None:
    labeled = [float(value) for value in values if value is not None]
    return round(mean(labeled), 6) if labeled else None


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 2)


def _compare_to_baseline(
    current: dict[str, Any],
    baseline: dict[str, Any],
    *,
    max_quality_drop: float,
    max_latency_increase_pct: float,
) -> dict[str, Any]:
    comparisons: dict[str, dict[str, Any]] = {}
    regressions: list[str] = []
    for key in QUALITY_METRICS:
        current_value = current.get(key)
        baseline_value = baseline.get(key)
        if current_value is None or baseline_value is None:
            continue
        delta = round(float(current_value) - float(baseline_value), 6)
        regressed = delta < -max_quality_drop
        comparisons[key] = {
            "baseline": baseline_value,
            "current": current_value,
            "delta": delta,
            "regressed": regressed,
        }
        if regressed:
            regressions.append(key)
    for key in ("average_latency_ms", "p95_latency_ms"):
        current_value = float(current.get(key) or 0.0)
        baseline_value = float(baseline.get(key) or 0.0)
        increase_pct = (
            round(((current_value - baseline_value) / baseline_value) * 100, 2)
            if baseline_value > 0
            else 0.0
        )
        regressed = baseline_value > 0 and increase_pct > max_latency_increase_pct
        comparisons[key] = {
            "baseline": baseline_value,
            "current": current_value,
            "increase_pct": increase_pct,
            "regressed": regressed,
        }
        if regressed:
            regressions.append(key)
    return {"passed": not regressions, "regressions": regressions, "metrics": comparisons}


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
    metrics = report["metrics"]
    metric_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(_format_metric(metrics.get(key)))}</td></tr>"
        for key, label in (
            ("pass_rate", "Pass rate"),
            ("hit_at_k", "Hit@K"),
            ("mrr", "MRR"),
            ("refusal_accuracy", "Refusal accuracy"),
            ("citation_correctness", "Citation correctness"),
            ("average_latency_ms", "Average latency (ms)"),
            ("p95_latency_ms", "P95 latency (ms)"),
        )
    )
    rows: list[str] = []
    for item in report["results"]:
        sources = "<br>".join(
            html.escape(
                f"{source.get('document_name')} P{source.get('page')} chunk {source.get('chunk_index')} "
                f"score {source.get('score')}: {source.get('preview')}"
            )
            for source in item.get("top_sources", [])
        )
        rows.append(
            "<tr>"
            f"<td>{html.escape(str(item.get('case_id') or item.get('index')))}</td>"
            f"<td>{html.escape(str(item.get('case_type', '')))}</td>"
            f"<td>{html.escape(str(item.get('question', '')))}</td>"
            f"<td>{html.escape(str(item.get('answer_status', item.get('error', ''))))}</td>"
            f"<td>{'yes' if item.get('passed') else 'no'}</td>"
            f"<td>{html.escape(str(item.get('elapsed_ms', '')))} ms</td>"
            f"<td>{sources}</td>"
            "</tr>"
        )
    baseline = report.get("baseline_comparison")
    baseline_text = ""
    if baseline:
        baseline_text = (
            f"<p>Baseline comparison: {'passed' if baseline.get('passed') else 'regressed'}; "
            f"regressions: {html.escape(', '.join(baseline.get('regressions') or []) or 'none')}.</p>"
        )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>StudyMate RAG Eval Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #0f172a; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 20px; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px; vertical-align: top; font-size: 14px; }}
    th {{ background: #f8fafc; text-align: left; }}
  </style>
</head>
<body>
  <h1>StudyMate RAG Eval Report</h1>
  <p>Base URL: {html.escape(str(report.get("base_url")))}</p>
  <p>Case file: {html.escape(str(report.get("case_file")))}</p>
  {baseline_text}
  <h2>Metrics</h2>
  <table><tbody>{metric_rows}</tbody></table>
  <h2>Cases</h2>
  <table>
    <thead><tr><th>ID</th><th>Type</th><th>Question</th><th>Status</th><th>Passed</th><th>Latency</th><th>Top sources</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )


def _format_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str = "",
) -> dict[str, Any]:
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
