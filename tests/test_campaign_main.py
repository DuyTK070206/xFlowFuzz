from __future__ import annotations

import json

from main import main


def test_offline_campaign_runs_in_parallel_and_logs(tmp_path):
    tasks = tmp_path / "tasks.jsonl"
    tasks.write_text(
        "\n".join(
            [
                json.dumps({"attempt_id": "a-1", "prompt": "first", "seed": 1}),
                json.dumps({"attempt_id": "a-2", "prompt": "second", "seed": 2}),
                json.dumps({"attempt_id": "a-3", "prompt": "third", "seed": 3}),
            ]
        ),
        encoding="utf-8",
    )

    code = main(
        [
            "--offline",
            "--tasks-file",
            str(tasks),
            "--workers",
            "3",
            "--results-dir",
            str(tmp_path / "results"),
            "--exp-id",
            "test-exp",
        ]
    )

    assert code == 0
    run_dir = tmp_path / "results" / "runs" / "test-exp"
    attempt_rows = [
        json.loads(line)
        for line in (run_dir / "attempts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    witness_rows = [
        json.loads(line)
        for line in (run_dir / "witnesses.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert len(attempt_rows) == 3
    assert len(witness_rows) == 3
    assert {row["attempt_id"] for row in attempt_rows} == {"a-1", "a-2", "a-3"}
    assert all(row["realized_taint_paths"] for row in attempt_rows)
