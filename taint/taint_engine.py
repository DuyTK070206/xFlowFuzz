"""Path-aware dynamic taint tracking at XFlowFuzz tool I/O boundaries.

The paper requires explicit-flow tracking using string containment and
structural provenance. This engine therefore combines:
  * object identity for values passed directly,
  * stable structural fingerprints for JSON reconstruction, and
  * containment matching for copied string fragments.

It also records the exact tool sequence traversed by each label so the runtime
can return REALIZEDPATH(sigma, labels), not merely the full execution path.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
from typing import Any, Callable, Iterable, Mapping

from .taint_label import TaintLabel
from .witness import LabelTraceEntry, Witness

PolicyChecker = Callable[[Mapping[str, Any], Any], bool | str | Mapping[str, Any]]


class TaintEngine:
    def __init__(self, *, min_string_fragment: int = 4) -> None:
        self.min_string_fragment = max(1, min_string_fragment)
        self._object_labels: dict[int, dict[str, TaintLabel]] = {}
        self._fingerprint_labels: dict[str, dict[str, TaintLabel]] = {}
        self._string_fragments: dict[str, dict[str, TaintLabel]] = {}
        self._labels: dict[str, TaintLabel] = {}
        self._paths: dict[str, list[str]] = {}
        self._label_traces: dict[str, list[LabelTraceEntry]] = {}
        self._witnesses: list[Witness] = []

    @property
    def witnesses(self) -> list[Witness]:
        return self.get_witnesses()

    def mark_source(self, data: Any, source_tool: str, *, step: int) -> TaintLabel:
        label = TaintLabel.create(source_tool, step)
        self._labels[label.id] = label
        self._paths[label.id] = [source_tool]
        self._label_traces[label.id] = [
            LabelTraceEntry(step=step, tool=source_tool, direction="source-output")
        ]
        self._attach_labels(data, [label], remember_strings=True)
        
        print(f"\n   [Taint Tracker] 🟢 Source Tool: {source_tool}")
        print(f"      └─ Generated label: {label.id}")
        
        return label

    def propagate(
        self,
        source: Any,
        destination: Any,
        *,
        tool_name: str,
        step: int,
    ) -> list[TaintLabel]:
        labels = self.labels_for(source)
        
        print(f"\n   [Taint Tracker] 🔄 Intermediate Tool: {tool_name}")
        print(f"      ├─ Input Taints: {[l.id for l in labels] if labels else 'None'}")
        
        if not labels:
            print("      └─ ❌ TAINT LOST (Canary missing or format corrupted).")
            return []
            
        for label in labels:
            self._append_path(label.id, tool_name)
            self._label_traces[label.id].append(
                LabelTraceEntry(step=step, tool=tool_name, direction="transform-input")
            )
        self._attach_labels(destination, labels, remember_strings=True)
        for label in labels:
            self._label_traces[label.id].append(
                LabelTraceEntry(step=step, tool=tool_name, direction="transform-output")
            )
            
        print(f"      └─ ✅ Taint propagated successfully.")
        return labels

    def check_sink(
        self,
        data: Any,
        sink_tool: str,
        *,
        step: int,
        output: Any = None,
        policy_checker: PolicyChecker | None = None,
    ) -> list[Witness]:
        labels = self.labels_for(data)
        
        print(f"\n   [Taint Tracker] 🛑 Sink Tool: {sink_tool}")
        print(f"      ├─ Labels at Sink: {[l.id for l in labels] if labels else 'None'}")
        
        if not labels:
            print("      └─ ❌ Failed: No sensitive data reached the sink.")
            return []

        policy = self._evaluate_policy(policy_checker, data, output)
        if not policy["violates"]:
            print("      └─ ❌ Failed: Data reached sink but policy evaluated it as safe.")
            return []

        print("      └─ 🚨 SUCCESS! Leak confirmed and witness generated.")

        # ... (Keep the rest of the check_sink logic unchanged) ...
        preview = self._preview(data)
        created: list[Witness] = []
        for label in labels:
            self._append_path(label.id, sink_tool)
            self._label_traces[label.id].append(
                LabelTraceEntry(step=step, tool=sink_tool, direction="sink-input")
            )
            witness = Witness(
                label=label.id,
                source_tool=label.source_tool,
                sink_tool=sink_tool,
                path=tuple(self._paths[label.id]),
                label_trace=tuple(self._label_traces[label.id]),
                violation_type=str(policy["violation_type"]),
                data_preview=preview,
                source_step=label.source_step,
                sink_step=step,
                canary_leaked=bool(policy.get("canary_leaked", False)),
            )
            self._witnesses.append(witness)
            created.append(witness)
        return created

    def labels_for(self, data: Any) -> list[TaintLabel]:
        found: dict[str, TaintLabel] = {}
        self._collect_labels(data, found, set())
        return list(found.values())

    def label_ids_for(self, data: Any) -> list[str]:
        return [label.id for label in self.labels_for(data)]

    def realized_paths(self) -> list[list[str]]:
        """Return exact source-to-sink paths confirmed by witnesses."""
        unique: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for witness in self._witnesses:
            if witness.path not in seen:
                seen.add(witness.path)
                unique.append(list(witness.path))
        return unique

    def partial_taint_paths(self) -> list[list[str]]:
        """Return current taint-carrying prefixes, useful to Person B's frontier."""
        return [list(path) for path in self._paths.values()]

    def get_witnesses(self) -> list[Witness]:
        return list(self._witnesses)

    def clear(self) -> None:
        self._object_labels.clear()
        self._fingerprint_labels.clear()
        self._string_fragments.clear()
        self._labels.clear()
        self._paths.clear()
        self._label_traces.clear()
        self._witnesses.clear()

    def _append_path(self, label_id: str, tool_name: str) -> None:
        path = self._paths.setdefault(label_id, [])
        if not path or path[-1] != tool_name:
            path.append(tool_name)

    def _attach_labels(
        self,
        data: Any,
        labels: Iterable[TaintLabel],
        *,
        remember_strings: bool,
    ) -> None:
        label_map = {label.id: label for label in labels}
        if not label_map:
            return
        self._object_labels.setdefault(id(data), {}).update(label_map)
        self._fingerprint_labels.setdefault(self._fingerprint(data), {}).update(label_map)
        if remember_strings:
            for text in self._iter_strings(data):
                if len(text) >= self.min_string_fragment:
                    self._string_fragments.setdefault(text, {}).update(label_map)

    def _collect_labels(
        self,
        data: Any,
        found: dict[str, TaintLabel],
        visited: set[int],
    ) -> None:
        object_id = id(data)
        if object_id in visited:
            return
        visited.add(object_id)
        found.update(self._object_labels.get(object_id, {}))
        found.update(self._fingerprint_labels.get(self._fingerprint(data), {}))

        if isinstance(data, str) and len(data) >= self.min_string_fragment:
            for fragment, labels in self._string_fragments.items():
                if fragment in data or data in fragment:
                    found.update(labels)

        if isinstance(data, Mapping):
            for value in data.values():
                self._collect_labels(value, found, visited)
        elif isinstance(data, (list, tuple, set, frozenset)):
            for item in data:
                self._collect_labels(item, found, visited)

    @staticmethod
    def _evaluate_policy(
        checker: PolicyChecker | None,
        arguments: Any,
        output: Any,
    ) -> dict[str, Any]:
        if checker is None:
            # Sink classification alone is not sufficient for witness soundness.
            return {"violates": False, "violation_type": "none"}
        raw = checker(arguments, output)
        if isinstance(raw, Mapping):
            return {
                "violates": bool(raw.get("violates", False)),
                "violation_type": raw.get("violation_type", "exfiltration"),
                "canary_leaked": bool(raw.get("canary_leaked", False)),
            }
        if isinstance(raw, str):
            return {"violates": True, "violation_type": raw}
        return {
            "violates": bool(raw),
            "violation_type": "exfiltration" if raw else "none",
        }

    @classmethod
    def _fingerprint(cls, data: Any) -> str:
        encoded = json.dumps(
            cls._json_safe(data),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if is_dataclass(value):
            return cls._json_safe(asdict(value))
        if hasattr(value, "to_dict"):
            return cls._json_safe(value.to_dict())
        if isinstance(value, Mapping):
            return {str(k): cls._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(v) for v in value]
        if isinstance(value, (set, frozenset)):
            return sorted(repr(v) for v in value)
        return repr(value)

    @classmethod
    def _iter_strings(cls, value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, Mapping):
            for item in value.values():
                yield from cls._iter_strings(item)
        elif isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                yield from cls._iter_strings(item)

    @classmethod
    def _preview(cls, data: Any, limit: int = 160) -> str:
        text = json.dumps(cls._json_safe(data), ensure_ascii=False)
        return text[:limit]
