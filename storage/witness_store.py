"""JSON persistence for replayable XFlowFuzz witnesses."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from taint.witness import LabelTraceEntry, Witness


class WitnessStore:
    def __init__(self, base_dir: str | Path = "results") -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        witnesses: Iterable[Any],
        *,
        run_id: str,
        filename: str | None = None,
    ) -> Path:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        target = self.base_dir / (filename or f"witnesses_{run_id}.json")
        payload = [
            item.to_dict() if hasattr(item, "to_dict") else item
            for item in witnesses
        ]
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    def load(self, path: str | Path) -> list[Witness]:
        payload: Any = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Witness JSON root must be an array")

        result: list[Witness] = []
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError("Every witness entry must be an object")
            label_trace = tuple(
                LabelTraceEntry(**entry)
                for entry in item.get("label_trace", [])
            )
            result.append(
                Witness(
                    label=str(item["label"]),
                    source_tool=str(item["source_tool"]),
                    sink_tool=str(item["sink_tool"]),
                    path=tuple(item.get("path", [])),
                    label_trace=label_trace,
                    violation_type=str(item.get("violation_type", "exfiltration")),
                    data_preview=str(item.get("data_preview", "")),
                    source_step=int(item.get("source_step", 1)),
                    sink_step=int(item.get("sink_step", 1)),
                    sink_effect_violation=bool(item.get("sink_effect_violation", True)),
                    canary_leaked=bool(item.get("canary_leaked", False)),
                    run_id=item.get("run_id"),
                    trace_ref=item.get("trace_ref"),
                    replay_seed=item.get("replay_seed"),
                    id=str(item.get("id")),
                    created_at=str(item.get("created_at")),
                )
            )
        return result
