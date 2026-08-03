"""OpenAI adapter for the provider-neutral XFlowFuzz agent runner."""

from __future__ import annotations

import json
from typing import Any, Sequence

from .agent_runner import LLMResponse, ToolCall


class OpenAIClient:
    """Use OpenAI Chat Completions behind the LLMClient protocol.

    The OpenAI SDK is imported lazily so the offline demo and unit tests can run
    without installing the SDK.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,  # [MỚI THÊM] Cho phép nhận đường dẫn API của Groq
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        timeout: float = 60.0,
        force_tool_choice: bool = False,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key cannot be empty.")

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "The 'openai' package is not installed. "
                "Run: pip install -r requirements.txt"
            ) from exc

        self.model = model
        self.temperature = temperature
        self.force_tool_choice = force_tool_choice
        # [MỚI SỬA] Truyền base_url vào thư viện OpenAI gốc
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def complete(
        self,
        *,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]],
    ) -> LLMResponse:
        """Send one normalized agent turn to OpenAI."""

        request: dict[str, Any] = {
            "model": self.model,
            "messages": [self._convert_message(item) for item in messages],
            "temperature": self.temperature,
        }

        openai_tools = [self._convert_tool(item) for item in tools]
        if openai_tools:
            request["tools"] = openai_tools
            if self.force_tool_choice and len(openai_tools) == 1:
                request["tool_choice"] = {
                    "type": "function",
                    "function": {"name": openai_tools[0]["function"]["name"]},
                }
                request["parallel_tool_calls"] = False
            else:
                request["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**request)
        choice = response.choices[0]
        message = choice.message

        normalized_calls: list[ToolCall] = []
        for call in message.tool_calls or []:
            arguments = self._parse_arguments(call.function.arguments)
            normalized_calls.append(
                ToolCall(
                    name=call.function.name,
                    arguments=arguments,
                    call_id=call.id,
                )
            )

        usage = getattr(response, "usage", None)
        return LLMResponse(
            content=message.content,
            tool_calls=normalized_calls,
            raw=response,
            input_tokens=getattr(usage, "prompt_tokens", None),
            output_tokens=getattr(usage, "completion_tokens", None),
        )

    @staticmethod
    def _convert_tool(tool: dict[str, Any]) -> dict[str, Any]:
        """Convert ToolExecutor metadata into an OpenAI function tool."""

        parameters = tool.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }

        return {
            "type": "function",
            "function": {
                "name": str(tool["name"]),
                "description": str(tool.get("description", "")),
                "parameters": parameters,
            },
        }

    @staticmethod
    def _convert_message(message: dict[str, Any]) -> dict[str, Any]:
        """Convert provider-neutral history into OpenAI message format."""

        role = str(message.get("role", "user"))

        if role == "assistant" and message.get("tool_calls"):
            converted_calls = []
            for call in message["tool_calls"]:
                converted_calls.append(
                    {
                        "id": call.get("id"),
                        "type": "function",
                        "function": {
                            "name": str(call["name"]),
                            "arguments": json.dumps(
                                call.get("arguments", {}),
                                ensure_ascii=False,
                            ),
                        },
                    }
                )

            return {
                "role": "assistant",
                "content": message.get("content") or None,
                "tool_calls": converted_calls,
            }

        if role == "tool":
            converted: dict[str, Any] = {
                "role": "tool",
                "tool_call_id": message.get("tool_call_id"),
                "content": str(message.get("content", "")),
            }
            return converted

        return {
            "role": role,
            "content": str(message.get("content", "")),
        }

    @staticmethod
    def _parse_arguments(raw_arguments: str | None) -> dict[str, Any]:
        if not raw_arguments:
            return {}

        try:
            parsed = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"OpenAI returned invalid tool arguments: {raw_arguments}"
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError("Tool arguments must be a JSON object.")

        return parsed
