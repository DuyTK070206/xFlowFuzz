"""Deterministic replay of previously recorded tool traces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tool_executor import ToolExecutor
from .trace import ExecutionTrace, TraceEvent, TraceRecorder


@dataclass
class ReplayResult:
    original_run_id: str
    replay_trace: ExecutionTrace
    matched: bool
    mismatches: list[str] = field(default_factory=list)

    @property
    def reproducible(self) -> bool:
        return self.matched


class ReplayRunner:
    """Replay tool calls from a saved trace using current tool implementations."""

    def __init__(self, executor: ToolExecutor) -> None:
        self.executor = executor

    def replay(
        self,
        original: ExecutionTrace,
        *,
        compare_outputs: bool = True,
    ) -> ReplayResult:
        self.executor.reset_taint()
        replay_trace = ExecutionTrace(
            metadata={
                "replay_of": original.run_id,
                "compare_outputs": compare_outputs,
            }
        )
        recorder = TraceRecorder(replay_trace)
        previous_recorder = self.executor.trace_recorder
        self.executor.set_trace_recorder(recorder)

        mismatches: list[str] = []

        try:
            for original_event in original.events:
                replay_output = self.executor.execute(
                    original_event.tool_name,
                    original_event.arguments,
                )

                replay_event = replay_trace.events[-1]
                self._compare_event(
                    original_event,
                    replay_event,
                    replay_output,
                    compare_outputs,
                    mismatches,
                )
        finally:
            recorder.finish()
            self.executor.set_trace_recorder(previous_recorder)

        return ReplayResult(
            original_run_id=original.run_id,
            replay_trace=replay_trace,
            matched=not mismatches,
            mismatches=mismatches,
        )

    @staticmethod
    def _compare_event(
        original: TraceEvent,
        replayed: TraceEvent,
        replay_output: Any,
        compare_outputs: bool,
        mismatches: list[str],
    ) -> None:
        if original.tool_name != replayed.tool_name:
            mismatches.append(
                f"Step {original.step}: tool changed from "
                f"{original.tool_name!r} to {replayed.tool_name!r}."
            )

        if original.arguments != replayed.arguments:
            mismatches.append(
                f"Step {original.step}: arguments changed."
            )

        if bool(original.error) != bool(replayed.error):
            mismatches.append(
                f"Step {original.step}: success/error status changed."
            )

        if compare_outputs and original.output != replay_output:
            mismatches.append(
                f"Step {original.step}: output changed from "
                f"{original.output!r} to {replay_output!r}."
            )
