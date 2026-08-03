"""Unified CLI for Person A's runtime and Person B's path-sensitive fuzzer."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable

from storage import JSONLLogger
from storage.jsonl_logger import attempt_record, witness_record


def load_seed_prompts(seed_path: str | Path) -> list[str]:
    path = Path(seed_path)
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Seed file is empty: {path}")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        prompts = [str(item.get("prompt", "")).strip() for item in parsed if isinstance(item, dict)]
        return [prompt for prompt in prompts if prompt]
    if isinstance(parsed, dict) and str(parsed.get("prompt", "")).strip():
        return [str(parsed["prompt"]).strip()]
    return [line.strip() for line in content.splitlines() if line.strip()]


def load_seed_prompt(seed_path: str | Path) -> str:
    """Backward-compatible helper used by older callers."""
    return load_seed_prompts(seed_path)[0]


def _load_tasks(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not str(value.get("prompt", "")).strip():
                raise ValueError(f"Invalid task at line {number}: prompt is required")
            value.setdefault("attempt_id", f"attempt-{number:04d}")
            value.setdefault("seed", number)
            rows.append(value)
    return rows


def _run_offline_task(task: dict[str, Any]):
    # A fresh runner/executor per worker prevents taint and LLM state races.
    from demo import DemoLLM
    from runner import AgentRunner
    from subjects import build_executor

    runner = AgentRunner(DemoLLM(), build_executor())
    result = runner.run(str(task["prompt"]), metadata={"attempt_id": task["attempt_id"]})
    return task, result


def run_offline_campaign(args: argparse.Namespace) -> int:
    tasks = _load_tasks(args.tasks_file)
    run_dir = Path(args.results_dir) / "runs" / args.exp_id
    attempts = JSONLLogger(run_dir / "attempts.jsonl")
    witnesses = JSONLLogger(run_dir / "witnesses.jsonl")
    attempts.clear()
    witnesses.clear()

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_run_offline_task, task) for task in tasks]
        for future in as_completed(futures):
            task, result = future.result()
            row = attempt_record(
                result,
                exp_id=args.exp_id,
                subject="offline-demo",
                suite="offline",
                method="xflowfuzz",
                seed=int(task.get("seed", 0)),
                target_path=["read_document", "summarize", "send_email"],
                source_content=str(task["prompt"]),
            )
            row["attempt_id"] = task["attempt_id"]
            row["prompt"] = task["prompt"]
            attempts.log(row)
            for witness in result.witnesses:
                witness_row = witness_record(
                    witness,
                    exp_id=args.exp_id,
                    subject="offline-demo",
                    suite="offline",
                    method="xflowfuzz",
                    seed=int(task.get("seed", 0)),
                    first_trigger_s=result.elapsed_s,
                    llm_calls_to_find=result.llm_calls,
                    trace_ref=result.trace.run_id,
                )
                witness_row["attempt_id"] = task["attempt_id"]
                witnesses.log(witness_row)
    return 0


def run_dynamic_campaign(args: argparse.Namespace) -> int:
    from xFlowFuzz.fuzzer import XFlowFuzzer

    seeds = load_seed_prompts(args.seed)
    fuzzer = XFlowFuzzer(
        yaml_path=args.config,
        max_path_length=args.max_length,
        model=args.model,
        max_steps=args.max_steps,
    )
    fuzzer.run(max_budget=args.budget, seed_prompts=seeds)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="XFlowFuzz unified campaign runner")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true", help="Run deterministic offline integration campaign")
    mode.add_argument("-c", "--config", help="Path to benchmark/tool schema YAML")

    parser.add_argument("-s", "--seed", help="Seed prompt file for YAML campaign")
    parser.add_argument("-b", "--budget", type=int, default=20)
    parser.add_argument("-m", "--max-length", type=int, default=6)
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-steps", type=int, default=int(os.getenv("AGENT_MAX_STEPS", "8")))

    parser.add_argument("--tasks-file", help="JSONL tasks for offline mode")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--results-dir", default="results")
    parser.add_argument("--exp-id", default="offline-run")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.offline:
            if not args.tasks_file:
                raise ValueError("--tasks-file is required with --offline")
            return run_offline_campaign(args)
        if not args.seed:
            raise ValueError("--seed is required with --config")
        return run_dynamic_campaign(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"[xFlowFuzz] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
