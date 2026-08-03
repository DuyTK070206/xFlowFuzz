from demo import DemoLLM
from runner import AgentRunner, ReplayRunner
from subjects import build_executor


def test_witness_is_exact_path_trace_and_policy_violation():
    result = AgentRunner(DemoLLM(), build_executor()).run("benign user task")
    assert result.execution_path == ["read_document", "summarize", "send_email"]
    assert result.realized_taint_paths == [["read_document", "summarize", "send_email"]]
    witness = result.witnesses[0]
    assert list(witness.path) == result.realized_taint_paths[0]
    assert witness.path_len == 2
    assert witness.violation_type == "exfiltration"
    assert witness.sink_effect_violation is True
    assert witness.run_id == result.trace.run_id
    assert [x.direction for x in witness.label_trace] == [
        "source-output", "transform-input", "transform-output", "sink-input"
    ]


def test_same_taint_to_trusted_email_does_not_emit_witness():
    executor = build_executor()
    executor.execute("read_document", {"filename": "secret.txt"})
    executor.execute("send_email", {"to": "owner@example.com", "body": "XFLOW-CANARY secret"})
    assert executor.get_witnesses() == []


def test_replay_resets_taint_and_reproduces_trace():
    executor = build_executor()
    result = AgentRunner(DemoLLM(), executor).run("benign user task")
    replay = ReplayRunner(executor).replay(result.trace)
    assert replay.reproducible
    assert replay.replay_trace.realized_path() == result.execution_path
