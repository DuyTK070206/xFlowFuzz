from runner import (
    AgentRunner,
    ExecutionTrace,
    LLMResponse,
    ReplayRunner,
    ToolCall,
    ToolExecutor,
    TraceEvent,
)


class FakeLLM:
    def __init__(self):
        self.step = 0

    def complete(self, *, messages, tools):
        self.step += 1

        if self.step == 1:
            return LLMResponse(
                content="I will read the document.",
                tool_calls=[
                    ToolCall(
                        name="read_document",
                        arguments={"path": "notes.txt"},
                        call_id="call-1",
                    )
                ],
            )

        if self.step == 2:
            return LLMResponse(
                content="I will summarize it.",
                tool_calls=[
                    ToolCall(
                        name="summarize",
                        arguments={"text": "secret document"},
                        call_id="call-2",
                    )
                ],
            )

        return LLMResponse(content="Done.")


def test_trace_realized_path():
    trace = ExecutionTrace()
    trace.add(
        TraceEvent(
            step=1,
            tool_name="echo",
            arguments={"text": "hello"},
            output="hello",
        )
    )
    assert trace.realized_path() == ["echo"]


def test_tool_executor():
    executor = ToolExecutor()
    executor.register("echo", lambda text: text)
    assert executor.execute("echo", {"text": "hello"}) == "hello"


def test_agent_runner_and_replay():
    executor = ToolExecutor()
    executor.register(
        "read_document",
        lambda path: "secret document",
        metadata={"tool_type": "source"},
    )
    executor.register(
        "summarize",
        lambda text: f"summary:{text}",
        metadata={"tool_type": "transform"},
    )

    runner = AgentRunner(FakeLLM(), executor, max_steps=5)
    result = runner.run("Read and summarize notes.txt")

    assert result.realized_path == ["read_document", "summarize"]
    assert result.final_response == "Done."
    assert result.stopped_reason == "final_response"

    replay = ReplayRunner(executor).replay(result.trace)
    assert replay.reproducible is True
