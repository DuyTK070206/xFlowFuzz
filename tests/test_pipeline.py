"""Integration tests for the complete offline XFlowFuzz MVP pipeline."""

from __future__ import annotations

import json

from demo import DemoLLM
from runner import AgentRunner
from storage import ResultStore, TraceStore, WitnessStore
from subjects import build_executor


def test_offline_pipeline_detects_leak_and_records_path(tmp_path):
    runner = AgentRunner(
        llm=DemoLLM(),
        executor=build_executor(),
        max_steps=8,
    )

    result = runner.run(
        "Run the deterministic offline leak-flow demo.",
        metadata={"test": "pipeline"},
    )

    assert result.success is True
    assert result.stopped_reason == "final_response"
    assert result.realized_path == [
        "read_document",
        "summarize",
        "send_email",
    ]
    assert len(result.tool_results) == 3
    assert result.leak_detected is True
    assert len(result.witnesses) == 1

    witness = result.witnesses[0]
    assert witness.source_tool == "read_document"
    assert witness.sink_tool == "send_email"

    events = result.trace.events
    assert len(events) == 3
    assert events[0].tool_type == "source"
    assert events[1].tool_type == "transform"
    assert events[2].tool_type == "sink"
    assert events[0].taint_out
    assert events[1].taint_in
    assert events[1].taint_out
    assert events[2].taint_in
    assert events[2].witness_ids == [witness.id]

    stored = ResultStore(tmp_path).save(result)
    assert stored.trace_path.exists()
    assert stored.witness_path.exists()

    trace_payload = json.loads(stored.trace_path.read_text(encoding="utf-8"))
    witness_payload = json.loads(
        stored.witness_path.read_text(encoding="utf-8")
    )

    assert trace_payload["realized_path"] == result.realized_path
    assert len(witness_payload) == 1
    assert witness_payload[0]["id"] == witness.id


def test_storage_round_trip(tmp_path):
    runner = AgentRunner(llm=DemoLLM(), executor=build_executor())
    result = runner.run("Run storage round-trip test.")

    stored = ResultStore(tmp_path).save(result)

    loaded_trace = TraceStore(tmp_path).load(stored.trace_path)
    loaded_witnesses = WitnessStore(tmp_path).load(stored.witness_path)

    assert loaded_trace.run_id == result.trace.run_id
    assert loaded_trace.realized_path() == result.realized_path
    assert len(loaded_witnesses) == len(result.witnesses)
    assert loaded_witnesses[0].id == result.witnesses[0].id


def test_dynamic_sink_without_effects_confirms_canary_leak():
    """A YAML sink is sensitive even when its optional effects list is absent."""
    from xFlowFuzz.graph.schema_parser import SchemaParser
    from xFlowFuzz.subjects.dynamic_executor import build_dynamic_executor

    schema = SchemaParser("configs/subjects/injecagent_tools.yaml").parse()
    executor = build_dynamic_executor(schema)

    source = executor.execute(
        "fetch_web_page", {"url": "https://example.test"}
    )
    executor.execute(
        "send_email",
        {
            "email_body": source,
            "to_address": "urgent_updates@example.com",
        },
    )

    witnesses = executor.get_witnesses()
    assert len(witnesses) == 1
    assert list(witnesses[0].path) == ["fetch_web_page", "send_email"]
    assert witnesses[0].canary_leaked is True
