"""Dynamic taint labels for XFlowFuzz tool-boundary tracking."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class TaintLabel:
    """Provenance label attached to attacker-controlled source output."""

    id: str
    source_tool: str
    source_step: int
    created_at: str = field(default_factory=_utc_now_iso)

    @classmethod
    def create(cls, source_tool: str, source_step: int) -> "TaintLabel":
        source_tool = source_tool.strip()
        if not source_tool:
            raise ValueError("source_tool cannot be empty")
        if source_step < 1:
            raise ValueError("source_step must be >= 1")
        return cls(
            id=f"TAINT-{uuid4().hex[:12]}",
            source_tool=source_tool,
            source_step=source_step,
        )

    @property
    def source(self) -> str:
        """Backward-compatible alias."""
        return self.source_tool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
