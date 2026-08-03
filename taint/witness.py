"""Replayable XFlowFuzz witness model: w = (path, trace, label-trace)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class LabelTraceEntry:
    step: int
    tool: str
    direction: str  # source-output | transform-input | transform-output | sink-input


@dataclass(frozen=True, slots=True)
class Witness:
    """Confirmed policy-violating source-to-sink information-flow witness."""

    label: str
    source_tool: str
    sink_tool: str
    path: tuple[str, ...]
    label_trace: tuple[LabelTraceEntry, ...]
    violation_type: str
    data_preview: str
    source_step: int
    sink_step: int
    sink_effect_violation: bool = True
    canary_leaked: bool = False
    run_id: str | None = None
    trace_ref: str | None = None
    replay_seed: int | None = None
    id: str = field(default_factory=lambda: f"WIT-{uuid4().hex[:12]}")
    created_at: str = field(default_factory=_utc_now_iso)

    @property
    def path_len(self) -> int:
        return max(0, len(self.path) - 1)

    def with_run(self, run_id: str) -> "Witness":
        data = asdict(self)
        data["run_id"] = run_id
        data["path"] = tuple(self.path)
        data["label_trace"] = tuple(LabelTraceEntry(**x) for x in data["label_trace"])
        return Witness(**data)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["path"] = list(self.path)
        data["path_len"] = self.path_len
        return data

    def __str__(self) -> str:
        return (
            f"[{self.violation_type.upper()}] "
            + " -> ".join(self.path)
            + f" ({self.label})"
        )
