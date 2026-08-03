"""Convenience storage facade for one complete agent run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runner.agent_runner import AgentRunResult

from .trace_store import TraceStore
from .witness_store import WitnessStore


@dataclass(frozen=True, slots=True)
class StoredRun:
    trace_path: Path
    witness_path: Path


class ResultStore:
    """Persist trace and witnesses using a shared run identifier."""

    def __init__(self, base_dir: str | Path = "results") -> None:
        self.trace_store = TraceStore(base_dir)
        self.witness_store = WitnessStore(base_dir)

    def save(self, result: AgentRunResult) -> StoredRun:
        run_id = result.trace.run_id
        trace_path = self.trace_store.save(result.trace)
        witness_path = self.witness_store.save(
            result.witnesses,
            run_id=run_id,
        )
        return StoredRun(
            trace_path=trace_path,
            witness_path=witness_path,
        )
