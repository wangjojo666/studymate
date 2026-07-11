from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_rag_eval_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "rag_eval.py"
    spec = importlib.util.spec_from_file_location("studymate_rag_eval", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_deterministic_rag_metrics_and_percentiles():
    rag_eval = _load_rag_eval_module()
    results = [
        {
            "passed": True,
            "elapsed_ms": 100,
            "hit_at_k": True,
            "reciprocal_rank": 1.0,
            "refusal_correct": True,
            "citation_correct": True,
        },
        {
            "passed": False,
            "elapsed_ms": 200,
            "hit_at_k": False,
            "reciprocal_rank": 0.0,
            "refusal_correct": True,
            "citation_correct": False,
        },
        {
            "passed": True,
            "elapsed_ms": 300,
            "hit_at_k": None,
            "reciprocal_rank": None,
            "refusal_correct": True,
            "citation_correct": None,
        },
    ]

    metrics = rag_eval._aggregate_metrics(results)

    assert metrics == {
        "evaluated_cases": 3,
        "passed_cases": 2,
        "failed_cases": 1,
        "pass_rate": 0.666667,
        "hit_at_k": 0.5,
        "mrr": 0.5,
        "refusal_accuracy": 1.0,
        "citation_correctness": 0.5,
        "average_latency_ms": 200.0,
        "p95_latency_ms": 300.0,
    }


def test_rag_baseline_comparison_flags_quality_and_latency_regressions():
    rag_eval = _load_rag_eval_module()
    current = {
        "hit_at_k": 0.7,
        "mrr": 0.8,
        "refusal_accuracy": 1.0,
        "citation_correctness": 0.9,
        "average_latency_ms": 130.0,
        "p95_latency_ms": 180.0,
    }
    baseline = {
        "hit_at_k": 0.9,
        "mrr": 0.8,
        "refusal_accuracy": 1.0,
        "citation_correctness": 0.9,
        "average_latency_ms": 100.0,
        "p95_latency_ms": 120.0,
    }

    comparison = rag_eval._compare_to_baseline(
        current,
        baseline,
        max_quality_drop=0.05,
        max_latency_increase_pct=25.0,
    )

    assert comparison["passed"] is False
    assert set(comparison["regressions"]) == {
        "hit_at_k",
        "average_latency_ms",
        "p95_latency_ms",
    }


def test_fixed_rag_catalog_covers_required_regression_scenarios():
    path = Path(__file__).resolve().parents[2] / "docs" / "rag_eval_cases.example.json"
    cases = json.loads(path.read_text(encoding="utf-8"))

    assert {case["case_type"] for case in cases} == {
        "answerable",
        "no_material",
        "low_confidence_refusal",
        "multi_document",
        "prompt_injection",
        "deleted_or_reindexed",
    }
    assert all(case.get("id") and case.get("question") for case in cases)
