"""JSON persistence for XFlowFuzz execution traces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from runner.trace import ExecutionTrace


class TraceStore:
    """Save and load execution traces as JSON files."""

    def __init__(self, base_dir: str | Path = "results") -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        trace: ExecutionTrace,
        *,
        filename: str | None = None,
    ) -> Path:
        """Persist one trace and return the created path."""

        self.base_dir.mkdir(parents=True, exist_ok=True)
        target = self.base_dir / (filename or f"trace_{trace.run_id}.json")
        target.write_text(
            json.dumps(trace.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    def load(self, path: str | Path) -> ExecutionTrace:
        """Load one execution trace from JSON."""

        target = Path(path)
        payload: Any = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Trace JSON root must be an object.")
        return ExecutionTrace.from_dict(payload)
