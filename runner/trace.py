"""Execution-trace models used by the XFlowFuzz runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_safe(value: Any) -> Any:
    """Recursively convert common Python values into JSON-safe values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            return repr(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return repr(value)


@dataclass(slots=True)
class TraceEvent:
    """One observed tool invocation."""

    step: int
    tool_name: str
    arguments: dict[str, Any]
    output: Any = None
    error: str | None = None
    call_id: str | None = None
    tool_type: str | None = None
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: str | None = None
    duration_ms: float | None = None
    taint_in: list[str] = field(default_factory=list)
    taint_out: list[str] = field(default_factory=list)
    witness_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["arguments"] = _json_safe(self.arguments)
        data["output"] = _json_safe(self.output)
        data["metadata"] = _json_safe(self.metadata)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        return cls(
            step=int(data["step"]),
            tool_name=str(data["tool_name"]),
            arguments=dict(data.get("arguments", {})),
            output=data.get("output"),
            error=data.get("error"),
            call_id=data.get("call_id"),
            tool_type=data.get("tool_type"),
            started_at=str(data.get("started_at", _utc_now_iso())),
            finished_at=data.get("finished_at"),
            duration_ms=data.get("duration_ms"),
            taint_in=list(data.get("taint_in", [])),
            taint_out=list(data.get("taint_out", [])),
            witness_ids=list(data.get("witness_ids", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ExecutionTrace:
    """Complete tool-call trace for one agent run."""

    run_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=_utc_now_iso)
    finished_at: str | None = None
    events: list[TraceEvent] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add(self, event: TraceEvent) -> None:
        if event.step < 1:
            raise ValueError("Trace step must start from 1.")
        if self.events and event.step <= self.events[-1].step:
            raise ValueError("Trace steps must be strictly increasing.")
        self.events.append(event)

    def extend(self, events: Iterable[TraceEvent]) -> None:
        for event in events:
            self.add(event)

    def realized_path(self, include_failed: bool = False) -> list[str]:
        return [
            event.tool_name
            for event in self.events
            if include_failed or event.succeeded
        ]

    def successful_events(self) -> list[TraceEvent]:
        return [event for event in self.events if event.succeeded]

    def failed_events(self) -> list[TraceEvent]:
        return [event for event in self.events if not event.succeeded]

    def finish(self) -> None:
        if self.finished_at is None:
            self.finished_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "events": [event.to_dict() for event in self.events],
            "metadata": _json_safe(self.metadata),
            "realized_path": self.realized_path(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionTrace":
        trace = cls(
            run_id=str(data.get("run_id", uuid4().hex)),
            started_at=str(data.get("started_at", _utc_now_iso())),
            finished_at=data.get("finished_at"),
            metadata=dict(data.get("metadata", {})),
        )
        trace.extend(
            TraceEvent.from_dict(event)
            for event in data.get("events", [])
        )
        return trace

    def save_json(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    @classmethod
    def load_json(cls, path: str | Path) -> "ExecutionTrace":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Trace JSON root must be an object.")
        return cls.from_dict(payload)


class TraceRecorder:
    """Mutable helper used by ToolExecutor while a run is active."""

    def __init__(self, trace: ExecutionTrace | None = None) -> None:
        self.trace = trace or ExecutionTrace()

    @property
    def next_step(self) -> int:
        return len(self.trace.events) + 1

    def record(self, event: TraceEvent) -> None:
        self.trace.add(event)

    def finish(self) -> ExecutionTrace:
        self.trace.finish()
        return self.trace
