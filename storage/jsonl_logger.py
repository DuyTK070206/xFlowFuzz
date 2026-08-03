"""Append-only logs matching PLAN.md section 6.2 data contract."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Iterator, Mapping


class JSONLLogger:
    _registry_guard = Lock()
    _path_locks: dict[str, Lock] = {}

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        key = str(self.path.resolve())
        with self._registry_guard:
            self._lock = self._path_locks.setdefault(key, Lock())

    def log(self, record: Mapping[str, Any] | Any) -> Path:
        payload = _json_safe(record)
        if not isinstance(payload, dict):
            raise TypeError("JSONL records must serialize to objects")
        payload.setdefault("logged_at", _utc_now_iso())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(line + "\n")
            file.flush()
        return self.path

    def log_many(self, records: Iterable[Mapping[str, Any] | Any]) -> Path:
        for record in records:
            self.log(record)
        return self.path

    def iter_records(self, *, skip_invalid: bool = False) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as file:
            for line_number, raw in enumerate(file, 1):
                if not raw.strip():
                    continue
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError as exc:
                    if skip_invalid:
                        continue
                    raise ValueError(f"Invalid JSONL line {line_number}") from exc
                if not isinstance(value, dict):
                    if skip_invalid:
                        continue
                    raise ValueError(f"JSONL line {line_number} is not an object")
                yield value

    def read_all(self, *, skip_invalid: bool = False) -> list[dict[str, Any]]:
        return list(self.iter_records(skip_invalid=skip_invalid))

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


def attempt_record(
    result: Any,
    *,
    exp_id: str,
    subject: str,
    suite: str,
    method: str,
    seed: int,
    target_path: Iterable[str] = (),
    agent_model: str = "offline",
    mutator_model: str = "none",
    source_content: str = "",
    usd_cost: float = 0.0,
) -> dict[str, Any]:
    """Create one PLAN-compatible attempts.jsonl row."""

    witnesses = list(getattr(result, "witnesses", []) or [])
    first = witnesses[0] if witnesses else None
    return {
        "exp_id": exp_id,
        "ts": _utc_now_iso(),
        "subject": subject,
        "suite": suite,
        "method": method,
        "seed": seed,
        "target_path": list(target_path),
        "realized_path": list(getattr(result, "realized_path", []) or []),
        "execution_path": list(getattr(result, "execution_path", []) or []),
        "realized_taint_paths": list(getattr(result, "realized_taint_paths", []) or []),
        "agent_model": agent_model,
        "mutator_model": mutator_model,
        "llm_calls": int(getattr(result, "llm_calls", 0) or 0),
        "prompt_tokens": int(getattr(result, "input_tokens", 0) or 0),
        "completion_tokens": int(getattr(result, "output_tokens", 0) or 0),
        "usd_cost": float(usd_cost),
        "latency_s": float(getattr(result, "elapsed_s", 0.0) or 0.0),
        "taint_reached_sink": bool(witnesses),
        "sink_effect_violation": bool(
            first and getattr(first, "sink_effect_violation", False)
        ),
        "witness_id": getattr(first, "id", None),
        "elapsed_s": float(getattr(result, "elapsed_s", 0.0) or 0.0),
        "source_content_sha256": hashlib.sha256(
            source_content.encode("utf-8")
        ).hexdigest(),
        "run_id": getattr(getattr(result, "trace", None), "run_id", None),
    }


def witness_record(
    witness: Any,
    *,
    exp_id: str,
    subject: str,
    suite: str,
    method: str,
    seed: int,
    first_trigger_s: float,
    llm_calls_to_find: int,
    replay_attempts: int = 0,
    replay_successes: int = 0,
    trace_ref: str | None = None,
) -> dict[str, Any]:
    """Create one PLAN-compatible witnesses.jsonl row."""

    path = list(getattr(witness, "path", []) or [])
    return {
        "exp_id": exp_id,
        "witness_id": getattr(witness, "id", None),
        "subject": subject,
        "suite": suite,
        "method": method,
        "seed": seed,
        "path": path,
        "path_len": max(0, len(path) - 1),
        "violation_type": getattr(witness, "violation_type", "exfiltration"),
        "first_trigger_s": float(first_trigger_s),
        "llm_calls_to_find": int(llm_calls_to_find),
        "replay_attempts": int(replay_attempts),
        "replay_successes": int(replay_successes),
        "canary_leaked": bool(getattr(witness, "canary_leaked", False)),
        "trace_ref": trace_ref,
        "label": getattr(witness, "label", None),
        "label_trace": _json_safe(getattr(witness, "label_trace", [])),
    }


def agent_result_record(result: Any, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible compact row used by older tests."""
    case_id = kwargs.pop("case_id", None)
    baseline = kwargs.pop("baseline", None)
    repetition = kwargs.pop("repetition", None)
    extra = kwargs.pop("extra", None)
    witnesses = list(getattr(result, "witnesses", []) or [])
    record = {
        "run_id": getattr(getattr(result, "trace", None), "run_id", None),
        "case_id": case_id,
        "baseline": baseline,
        "repetition": repetition,
        "success": bool(getattr(result, "success", False)),
        "stopped_reason": getattr(result, "stopped_reason", None),
        "leak_detected": bool(witnesses),
        "witness_count": len(witnesses),
        "witnesses": _json_safe(witnesses),
        "realized_path": list(getattr(result, "realized_path", []) or []),
        "realized_taint_paths": list(getattr(result, "realized_taint_paths", []) or []),
        "elapsed_s": float(getattr(result, "elapsed_s", 0.0) or 0.0),
        "llm_calls": int(getattr(result, "llm_calls", 0) or 0),
        "input_tokens": int(getattr(result, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(result, "output_tokens", 0) or 0),
    }
    if extra:
        record.update(_json_safe(extra))
    return record


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    return repr(value)
