"""The `LLMProvider` port (implementation.md §7) and the value objects that cross it.

Sync, not `async` as originally sketched — every other request-path dependency in this
codebase (`DbSession`, `IngestionPipeline`) is sync, and mixing an async provider call
into an otherwise-sync SQLAlchemy request would buy nothing at this scale. Revisit if a
streaming response (plan.md Phase 5/SSE) needs it.

Production wires `openai_provider.py`. Tests wire `tests/fakes/llm_provider.py`.
"""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolSpec:
    """A tool's OpenAI-function-calling-shaped schema, provider-agnostic."""

    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # set on role="tool" replies
    name: str | None = None  # tool name, set on role="tool" replies


@dataclass(frozen=True)
class AgentTurn:
    """One model turn: either a final answer (`tool_calls` empty) or a request to call
    tools (`content` may still carry reasoning text alongside the calls)."""

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AgentTurn: ...
