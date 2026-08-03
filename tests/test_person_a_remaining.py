"""Tests for JSONL logging, taint-only baseline and runtime metrics."""

from __future__ import annotations

import pytest

from benchmark import TaintOnlyCase, TaintOnlyRunner
from demo import DemoLLM
from evaluation import TokenPricing, evaluate_runtime
from runner import AgentRunner
from storage import JSONLLogger
from subjects import build_executor


def test_jsonl_and_taint_only_baseline(tmp_path):
    runner = AgentRunner(llm=DemoLLM(), executor=build_executor())
    logger = JSONLLogger(tmp_path / "taint_only.jsonl")
    baseline = TaintOnlyRunner(runner, logger=logger)

    records = baseline.run(
        [
            TaintOnlyCase(
                case_id="leak-001",
                prompt="Run the deterministic leak demo.",
                expected_leak=True,
            )
        ],
        repetitions=2,
    )

    assert len(records) == 2
    assert all(record.detected for record in records)
    assert all(record.correct is True for record in records)

    rows = logger.read_all()
    assert len(rows) == 2
    assert rows[0]["baseline"] == "taint_only"
    assert rows[0]["case_id"] == "leak-001"
    assert rows[0]["leak_detected"] is True
    assert rows[0]["witness_count"] == 1


def test_runtime_metrics():
    rows = [
        {
            "success": True,
            "detected": False,
            "elapsed_s": 0.2,
            "input_tokens": 100,
            "output_tokens": 20,
        },
        {
            "success": True,
            "detected": True,
            "elapsed_s": 0.3,
            "input_tokens": 150,
            "output_tokens": 30,
        },
        {
            "success": False,
            "detected": True,
            "elapsed_s": 0.5,
            "input_tokens": 50,
            "output_tokens": 10,
        },
    ]

    metrics = evaluate_runtime(
        rows,
        pricing=TokenPricing(input_per_million=1.0, output_per_million=2.0),
    )

    assert metrics.runs == 3
    assert metrics.successful_runs == 2
    assert metrics.triggered_runs == 2
    assert metrics.reproducibility == 2 / 3
    assert metrics.trials_to_trigger == 2
    assert metrics.time_to_trigger_s == 0.5
    assert metrics.latency.total_s == 1.0
    assert metrics.input_tokens == 300
    assert metrics.output_tokens == 60
    assert metrics.estimated_cost is not None
    assert metrics.estimated_cost.total_cost_usd == pytest.approx(0.00042)
