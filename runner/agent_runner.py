"""Generic tool-calling agent loop for XFlowFuzz.

The runner is provider-neutral. Any OpenAI/Anthropic/local adapter only needs
to implement the LLMClient protocol and return LLMResponse objects.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
import time
from typing import Any, Protocol, Sequence

from .tool_executor import ToolExecutor
from .trace import ExecutionTrace, TraceRecorder


@dataclass(slots=True)
class ToolCall:
    """Normalized tool call returned by an LLM adapter."""

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None


@dataclass(slots=True)
class LLMResponse:
    """Provider-neutral LLM response."""

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class LLMClient(Protocol):
    """Minimal interface required by AgentRunner."""

    def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> LLMResponse:
        ...


@dataclass(slots=True)
class AgentRunResult:
    """Stable contract shared with fuzzing and evaluation modules."""

    prompt: str
    final_response: str | None
    trace: ExecutionTrace
    messages: list[dict[str, Any]]
    llm_calls: int
    stopped_reason: str
    elapsed_s: float
    input_tokens: int = 0
    output_tokens: int = 0
    witnesses: list[Any] = field(default_factory=list)

    @property
    def tool_results(self) -> list[Any]:
        """Outputs of executed tools, retained for Person A compatibility."""
        return [event.output for event in self.trace.events if event.error is None]

    @property
    def execution_path(self) -> list[str]:
        """All successfully executed tools (control-flow trace)."""
        return self.trace.realized_path()

    @property
    def realized_taint_paths(self) -> list[list[str]]:
        """Confirmed source-to-sink paths carrying a taint label."""
        paths: list[list[str]] = []
        seen: set[tuple[str, ...]] = set()
        for witness in self.witnesses:
            path = tuple(getattr(witness, "path", ()) or ())
            if path and path not in seen:
                seen.add(path)
                paths.append(list(path))
        return paths

    @property
    def realized_path(self) -> list[str]:
        """Compatibility alias: first confirmed taint path, else execution path."""
        return self.realized_taint_paths[0] if self.realized_taint_paths else self.execution_path

    @property
    def success(self) -> bool:
        return not self.stopped_reason.startswith("error:")

    @property
    def leak_detected(self) -> bool:
        return bool(self.witnesses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "final_response": self.final_response,
            "trace": self.trace.to_dict(),
            "messages": _json_safe(self.messages),
            "llm_calls": self.llm_calls,
            "stopped_reason": self.stopped_reason,
            "elapsed_s": self.elapsed_s,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "execution_path": self.execution_path,
            "realized_path": self.realized_path,
            "realized_taint_paths": self.realized_taint_paths,
            "success": self.success,
            "leak_detected": self.leak_detected,
            "witnesses": [_json_safe(item) for item in self.witnesses],
        }


class AgentRunner:
    """Run an LLM agent until it answers, errors or reaches the step limit."""

    def __init__(
        self,
        llm: LLMClient,
        executor: ToolExecutor,
        *,
        max_steps: int = 8,
        system_prompt: str | None = None,
    ) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be at least 1.")

        self.llm = llm
        self.executor = executor
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    def run(
        self,
        prompt: str,
        *,
        metadata: dict[str, Any] | None = None,
        allowed_path: Sequence[str] | None = None,
    ) -> AgentRunResult:
        if not prompt.strip():
            raise ValueError("Prompt cannot be empty.")

        self.executor.reset_taint()
        reset_llm = getattr(self.llm, "reset", None)
        if callable(reset_llm):
            reset_llm()

        trace = ExecutionTrace(metadata=dict(metadata or {}))
        recorder = TraceRecorder(trace)
        previous_recorder = self.executor.trace_recorder
        self.executor.set_trace_recorder(recorder)

        messages: list[dict[str, Any]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt})

        final_response: str | None = None
        stopped_reason = "max_steps"
        llm_calls = 0
        input_tokens = 0
        output_tokens = 0
        started = time.perf_counter()

        expected_path = [str(name) for name in (allowed_path or []) if str(name).strip()]
        path_index = 0
        previous_output: Any = None

        try:
            for _ in range(self.max_steps):
                all_tools = self.executor.describe_tools()
                if expected_path:
                    if path_index >= len(expected_path):
                        stopped_reason = "path_completed"
                        break
                    expected_tool = expected_path[path_index]
                    visible_tools = [
                        tool for tool in all_tools
                        if tool.get("name") == expected_tool
                    ]
                    if not visible_tools:
                        raise ValueError(
                            f"Target path references an unregistered tool: {expected_tool}"
                        )
                else:
                    expected_tool = None
                    visible_tools = all_tools

                response = self.llm.complete(
                    messages=messages,
                    tools=visible_tools,
                )
                llm_calls += 1
                input_tokens += response.input_tokens or 0
                output_tokens += response.output_tokens or 0

                messages.append(self._assistant_message(response))

                if not response.tool_calls:
                    final_response = response.content
                    stopped_reason = (
                        "missing_required_tool_call" if expected_path
                        else "final_response"
                    )
                    break

                calls = response.tool_calls[:1] if expected_path else response.tool_calls
                for tool_call in calls:
                    if expected_tool is not None and tool_call.name != expected_tool:
                        stopped_reason = "unexpected_tool_call"
                        final_response = (
                            f"Expected '{expected_tool}', received '{tool_call.name}'."
                        )
                        break

                    arguments = dict(tool_call.arguments or {})
                    if expected_tool is not None:
                        arguments = self._complete_path_arguments(
                            expected_tool, arguments, previous_output
                        )
                        tool_call = ToolCall(
                            name=tool_call.name,
                            arguments=arguments,
                            call_id=tool_call.call_id,
                        )

                    output = self.executor.execute(
                        tool_call.name,
                        tool_call.arguments,
                        call_id=tool_call.call_id,
                    )
                    messages.append(self._tool_message(tool_call, output))
                    previous_output = output

                    if expected_tool is not None:
                        path_index += 1

                if stopped_reason in {"unexpected_tool_call"}:
                    break

                if expected_path and path_index >= len(expected_path):
                    stopped_reason = "path_completed"
                    break
            else:
                stopped_reason = "max_steps"

        except Exception as exc:
            stopped_reason = f"error:{type(exc).__name__}"
            final_response = str(exc)
        finally:
            recorder.finish()
            self.executor.set_trace_recorder(previous_recorder)

        raw_witnesses = self.executor.get_witnesses()
        witnesses = [
            witness.with_run(trace.run_id)
            if hasattr(witness, "with_run") else witness
            for witness in raw_witnesses
        ]

        return AgentRunResult(
            prompt=prompt,
            final_response=final_response,
            trace=trace,
            messages=messages,
            llm_calls=llm_calls,
            stopped_reason=stopped_reason,
            elapsed_s=time.perf_counter() - started,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            witnesses=witnesses,
        )

    def _complete_path_arguments(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        previous_output: Any,
    ) -> dict[str, Any]:
        """Fill missing path arguments without overwriting model choices.

        The previous tool output is bound to a type-compatible data parameter.
        Remaining required control parameters receive safe benchmark defaults.
        This keeps path-guided execution generic across YAML subjects.
        """
        description = next(
            (item for item in self.executor.describe_tools() if item.get("name") == tool_name),
            None,
        )
        if description is None:
            return arguments

        schema = description.get("parameters") or {}
        properties = schema.get("properties") or {}
        required = list(schema.get("required") or [])
        completed = dict(arguments)

        if previous_output is not None:
            output_type = _json_type(previous_output)
            candidates = [
                name for name in required
                if name not in completed
                and _schema_accepts(properties.get(name, {}), output_type)
            ]
            if not candidates:
                candidates = [
                    name for name, item in properties.items()
                    if name not in completed
                    and _schema_accepts(item, output_type)
                ]
            if candidates:
                completed[candidates[0]] = previous_output

        for name in required:
            if name not in completed:
                completed[name] = _default_argument(
                    name, properties.get(name, {}).get("type", "string")
                )

        return completed

    @staticmethod
    def _assistant_message(response: LLMResponse) -> dict[str, Any]:
        message: dict[str, Any] = {
            "role": "assistant",
            "content": response.content or "",
        }

        if response.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.call_id,
                    "name": call.name,
                    "arguments": dict(call.arguments),
                }
                for call in response.tool_calls
            ]

        return message

    @staticmethod
    def _tool_message(tool_call: ToolCall, output: Any) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call.call_id,
            "name": tool_call.name,
            "content": _serialize_tool_output(output),
        }



def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "string"


def _schema_accepts(schema: dict[str, Any], value_type: str) -> bool:
    expected = schema.get("type")
    if isinstance(expected, list):
        return value_type in expected
    if expected == "number" and value_type == "integer":
        return True
    return expected in {None, value_type}


def _default_argument(name: str, kind: str) -> Any:
    lower = name.lower()
    if "email" in lower or "address" in lower or lower.startswith("to_"):
        return "attacker@test.com"
    if "url" in lower or "endpoint" in lower or "host" in lower:
        return "https://untrusted.example/xflow"
    if "file" in lower or "path" in lower:
        return "/tmp/xflow-output.txt"
    if "sql" in lower or "query" in lower:
        return "SELECT * FROM users"
    if kind == "boolean":
        return True
    if kind == "integer":
        return 1
    if kind == "number":
        return 1.0
    if kind == "array":
        return []
    if kind == "object":
        return {}
    return "xflowfuzz-input"

def _serialize_tool_output(output: Any) -> str:
    if isinstance(output, str):
        return output

    try:
        return json.dumps(_json_safe(output), ensure_ascii=False)
    except (TypeError, ValueError):
        return str(output)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if hasattr(value, "to_dict"):
        try:
            return _json_safe(value.to_dict())
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)