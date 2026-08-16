"""Scriptable fake `LLMProvider`. Each `.turns` entry is returned in order; the last one
should have empty `tool_calls` or the orchestrator will run out of turns."""

from app.agent.providers.base import AgentTurn, Message, ToolSpec


class FakeLLMProvider:
    def __init__(self, turns: list[AgentTurn] | None = None) -> None:
        self.turns: list[AgentTurn] = list(turns or [])
        self.received_messages: list[list[Message]] = []
        self.received_tools: list[list[ToolSpec]] = []

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AgentTurn:
        self.received_messages.append(list(messages))
        self.received_tools.append(list(tools))
        if not self.turns:
            raise AssertionError("FakeLLMProvider ran out of scripted turns")
        return self.turns.pop(0)
