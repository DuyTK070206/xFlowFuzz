from evaluation.metrics import EvaluationFramework


def test_evaluation_uses_confirmed_realized_paths_and_clear_ttt_names():
    evaluator = EvaluationFramework(
        total_attack_paths=43,
        sensitive_sinks={"send_email", "upload_to_cloud"},
    )
    evaluator.log_iteration(
        iteration=1,
        path=["source", "send_email"],
        target_sink="send_email",
        is_success=True,
        tool_calls=2,
        has_witness=True,
        score=4.0,
        actual_execution=["source", "send_email"],
        realized_taint_paths=[["source", "send_email"]],
    )
    evaluator.log_iteration(
        iteration=3,
        path=["source", "transform", "upload_to_cloud"],
        target_sink="upload_to_cloud",
        is_success=True,
        tool_calls=3,
        has_witness=True,
        score=3.0,
        actual_execution=["source", "transform", "upload_to_cloud"],
        realized_taint_paths=[["source", "transform", "upload_to_cloud"]],
    )

    metrics = evaluator._calculate_metrics()
    assert metrics["distinct_realized_paths"] == 2
    assert metrics["first_trigger_iteration"] == 1
    assert metrics["mean_trigger_iteration"] == 2.0
    assert metrics["new_paths_per_attempt"] == 1.0
    assert metrics["attempts_per_new_path"] == 1.0
    assert metrics["average_target_score"] == 3.5

    report = evaluator.summary()
    assert "Time to First Trigger" in report
    assert "Mean Trigger Iteration" in report
    assert "Scheduler Effic." not in report


def test_target_path_does_not_count_without_confirmed_taint_path():
    evaluator = EvaluationFramework(
        total_attack_paths=43,
        sensitive_sinks={"send_email"},
    )
    evaluator.log_iteration(
        iteration=1,
        path=["source", "send_email"],
        target_sink="send_email",
        is_success=False,
        tool_calls=2,
        has_witness=False,
        score=4.0,
        actual_execution=["source", "send_email"],
        realized_taint_paths=[],
    )
    metrics = evaluator._calculate_metrics()
    assert metrics["distinct_realized_paths"] == 0
    assert metrics["path_coverage_percent"] == 0.0
    assert metrics["sink_coverage_percent"] == 100.0
