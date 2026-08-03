"""Safe registry, execution and taint instrumentation for agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import inspect
import time
from typing import Any, Callable, Mapping, get_args, get_origin

from .trace import TraceEvent, TraceRecorder


class ToolExecutorError(RuntimeError):
    """Base error for tool-executor failures."""


class ToolNotFoundError(ToolExecutorError):
    """Raised when an unknown tool is requested."""


class ToolRegistrationError(ToolExecutorError):
    """Raised when a tool cannot be registered."""


class ToolExecutionError(ToolExecutorError):
    """Raised when a registered tool fails."""

    def __init__(self, tool_name: str, message: str) -> None:
        super().__init__(f"Tool '{tool_name}' failed: {message}")
        self.tool_name = tool_name


@dataclass(slots=True)
class RegisteredTool:
    name: str
    function: Callable[..., Any]
    description: str = ""
    metadata: dict[str, Any] | None = None
    parameters: dict[str, Any] | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolExecutor:
    """Execute every tool call through one instrumentable boundary."""

    def __init__(
        self,
        *,
        trace_recorder: TraceRecorder | None = None,
        taint_engine: Any | None = None,
        raise_on_error: bool = False,
    ) -> None:
        self._tools: dict[str, RegisteredTool] = {}
        self.trace_recorder = trace_recorder
        self.taint_engine = taint_engine
        self.raise_on_error = raise_on_error

    def set_trace_recorder(self, recorder: TraceRecorder | None) -> None:
        self.trace_recorder = recorder

    def set_taint_engine(self, engine: Any | None) -> None:
        self.taint_engine = engine

    def reset_taint(self) -> None:
        if self.taint_engine is not None:
            clear = getattr(self.taint_engine, "clear", None)
            if callable(clear):
                clear()

    def get_witnesses(self) -> list[Any]:
        if self.taint_engine is None:
            return []

        getter = getattr(self.taint_engine, "get_witnesses", None)
        if callable(getter):
            return list(getter() or [])

        return list(getattr(self.taint_engine, "witnesses", []) or [])

    def register(
        self,
        name: str,
        function: Callable[..., Any],
        *,
        description: str = "",
        metadata: Mapping[str, Any] | None = None,
        parameters: Mapping[str, Any] | None = None,
        overwrite: bool = False,
    ) -> None:
        clean_name = name.strip()
        if not clean_name:
            raise ToolRegistrationError("Tool name cannot be empty.")
        if not callable(function):
            raise ToolRegistrationError(
                f"Tool '{clean_name}' must be callable."
            )
        if clean_name in self._tools and not overwrite:
            raise ToolRegistrationError(
                f"Tool '{clean_name}' is already registered."
            )

        self._tools[clean_name] = RegisteredTool(
            name=clean_name,
            function=function,
            description=description,
            metadata=dict(metadata or {}),
            parameters=dict(parameters) if parameters is not None else None,
        )

    def unregister(self, name: str) -> None:
        if name not in self._tools:
            raise ToolNotFoundError(f"Unknown tool: {name}")
        del self._tools[name]

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tools(self) -> list[str]:
        return sorted(self._tools)

    def describe_tools(self) -> list[dict[str, Any]]:
        """Return provider-neutral tool descriptions with JSON Schema inputs."""

        descriptions: list[dict[str, Any]] = []
        for tool in self._tools.values():
            descriptions.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "signature": str(inspect.signature(tool.function)),
                    "parameters": dict(tool.parameters) if tool.parameters is not None else _parameters_schema(tool.function),
                    "metadata": dict(tool.metadata or {}),
                }
            )
        return descriptions

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any] | None = None,
        *,
        call_id: str | None = None,
    ) -> Any:
        if name not in self._tools:
            raise ToolNotFoundError(f"Unknown tool: {name}")

        args = dict(arguments or {})
        tool = self._tools[name]
        metadata = dict(tool.metadata or {})
        tool_type = str(metadata.get("type", metadata.get("tool_type", "tool")))

        step = (
            self.trace_recorder.next_step
            if self.trace_recorder is not None
            else 1
        )
        started_at = _utc_now_iso()
        started_ns = time.perf_counter_ns()

        taint_in = self._label_ids_for(args)
        taint_out: list[str] = []
        witness_ids: list[str] = []
        output: Any = None
        error: str | None = None

        try:
            output = tool.function(**args)
            taint_out, witness_ids = self._apply_taint_policy(
                tool_name=name,
                tool_type=tool_type,
                arguments=args,
                output=output,
                step=step,
                metadata=metadata,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        duration_ms = (time.perf_counter_ns() - started_ns) / 1_000_000

        if self.trace_recorder is not None:
            self.trace_recorder.record(
                TraceEvent(
                    step=step,
                    tool_name=name,
                    arguments=args,
                    output=output,
                    error=error,
                    call_id=call_id,
                    tool_type=tool_type,
                    started_at=started_at,
                    finished_at=_utc_now_iso(),
                    duration_ms=duration_ms,
                    taint_in=taint_in,
                    taint_out=taint_out,
                    witness_ids=witness_ids,
                    metadata=metadata,
                )
            )

        if error is not None and self.raise_on_error:
            raise ToolExecutionError(name, error)

        if error is not None:
            return {"ok": False, "error": error}

        return output

    def _apply_taint_policy(
        self,
        *,
        tool_name: str,
        tool_type: str,
        arguments: dict[str, Any],
        output: Any,
        step: int,
        metadata: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        if self.taint_engine is None:
            return [], []

        normalized_type = tool_type.lower()

        if normalized_type == "source":
            self.taint_engine.mark_source(output, tool_name, step=step)
        elif normalized_type in {"transform", "processor"}:
            self.taint_engine.propagate(
                arguments, output, tool_name=tool_name, step=step
            )
        elif normalized_type == "sink":
            witnesses = self.taint_engine.check_sink(
                arguments,
                tool_name,
                step=step,
                output=output,
                policy_checker=metadata.get("policy_checker"),
            )
            return (
                self._label_ids_for(output),
                [witness.id for witness in witnesses],
            )
        elif self._label_ids_for(arguments):
            # Unknown tools conservatively propagate input taint to output.
            self.taint_engine.propagate(
                arguments, output, tool_name=tool_name, step=step
            )

        return self._label_ids_for(output), []

    def _label_ids_for(self, data: Any) -> list[str]:
        if self.taint_engine is None:
            return []

        getter = getattr(self.taint_engine, "label_ids_for", None)
        if callable(getter):
            return list(getter(data) or [])

        labels_for = getattr(self.taint_engine, "labels_for", None)
        if callable(labels_for):
            return [label.id for label in labels_for(data)]

        return []

def _parameters_schema(function: Callable[..., Any]) -> dict[str, Any]:
    """Build a compact JSON Schema from a Python callable signature."""

    signature = inspect.signature(function)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, parameter in signature.parameters.items():
        if name in {"self", "cls"}:
            continue
        if parameter.kind in {
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        }:
            continue

        schema = _annotation_schema(parameter.annotation)
        if parameter.default is not inspect.Parameter.empty:
            schema["default"] = parameter.default
        else:
            required.append(name)

        properties[name] = schema

    result: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        result["required"] = required
    return result


def _annotation_schema(annotation: Any) -> dict[str, Any]:
    if annotation is inspect.Parameter.empty or annotation is Any:
        return {}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin in {list, tuple, set}:
        item_annotation = args[0] if args else Any
        return {
            "type": "array",
            "items": _annotation_schema(item_annotation),
        }

    if origin is dict:
        return {"type": "object"}

    if origin is not None and type(None) in args:
        non_none = [item for item in args if item is not type(None)]
        if len(non_none) == 1:
            schema = _annotation_schema(non_none[0])
            schema["nullable"] = True
            return schema

    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    json_type = mapping.get(annotation)
    return {"type": json_type} if json_type else {}

