"""Taint-only baseline for XFlowFuzz.

This baseline does not mutate prompts or prioritize paths. It executes each
provided prompt and reports whether dynamic taint tracking produced a witness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from runner.agent_runner import AgentRunResult, AgentRunner
from storage.jsonl_logger import JSONLLogger, agent_result_record


@dataclass(frozen=True, slots=True)
class TaintOnlyCase:
    case_id: str
    prompt: str
    expected_leak: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TaintOnlyRecord:
    case_id: str
    repetition: int
    expected_leak: bool | None
    detected: bool
    success: bool
    run_id: str
    elapsed_s: float
    input_tokens: int
    output_tokens: int
    realized_path: tuple[str, ...]
    witness_count: int
    stopped_reason: str

    @property
    def correct(self) -> bool | None:
        if self.expected_leak is None:
            return None
        return self.detected == self.expected_leak

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "repetition": self.repetition,
            "expected_leak": self.expected_leak,
            "detected": self.detected,
            "success": self.success,
            "run_id": self.run_id,
            "elapsed_s": self.elapsed_s,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "realized_path": list(self.realized_path),
            "witness_count": self.witness_count,
            "stopped_reason": self.stopped_reason,
            "correct": self.correct,
        }


class TaintOnlyRunner:
    """Execute benchmark cases using only runtime taint detection."""

    def __init__(
        self,
        runner: AgentRunner,
        *,
        logger: JSONLLogger | None = None,
    ) -> None:
        self.runner = runner
        self.logger = logger

    def run_case(
        self,
        case: TaintOnlyCase,
        *,
        repetition: int = 1,
    ) -> tuple[TaintOnlyRecord, AgentRunResult]:
        if repetition < 1:
            raise ValueError("repetition must start from 1.")

        metadata = {
            "baseline": "taint_only",
            "case_id": case.case_id,
            "repetition": repetition,
            **case.metadata,
        }
        result = self.runner.run(case.prompt, metadata=metadata)
        record = self._build_record(case, repetition, result)

        if self.logger is not None:
            payload = agent_result_record(
                result,
                case_id=case.case_id,
                baseline="taint_only",
                repetition=repetition,
                extra={
                    "expected_leak": case.expected_leak,
                    "correct": record.correct,
                    "case_metadata": case.metadata,
                },
            )
            self.logger.log(payload)

        return record, result

    def run(
        self,
        cases: Iterable[TaintOnlyCase],
        *,
        repetitions: int = 1,
    ) -> list[TaintOnlyRecord]:
        if repetitions < 1:
            raise ValueError("repetitions must be at least 1.")

        records: list[TaintOnlyRecord] = []
        for case in cases:
            for repetition in range(1, repetitions + 1):
                record, _ = self.run_case(case, repetition=repetition)
                records.append(record)
        return records

    @staticmethod
    def _build_record(
        case: TaintOnlyCase,
        repetition: int,
        result: AgentRunResult,
    ) -> TaintOnlyRecord:
        return TaintOnlyRecord(
            case_id=case.case_id,
            repetition=repetition,
            expected_leak=case.expected_leak,
            detected=result.leak_detected,
            success=result.success,
            run_id=result.trace.run_id,
            elapsed_s=result.elapsed_s,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            realized_path=tuple(result.realized_path),
            witness_count=len(result.witnesses),
            stopped_reason=result.stopped_reason,
        )
