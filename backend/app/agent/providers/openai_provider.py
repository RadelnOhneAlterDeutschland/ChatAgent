"""OpenAI-backed `LLMProvider` (implementation.md §7). Real adapter, function-calling API.

No dedicated contract test — the fake (`tests/fakes/llm_provider.py`) is exercised
directly by `tests/unit/test_orchestrator.py` and `tests/features/chat.feature`; this
class is wired only in production, same precedent as `embedder.py`/`ocr.py` (Phase 2).
"""

import json

from openai import OpenAI

from app.agent.providers.base import AgentTurn, Message, ToolCall, ToolSpec

DEFAULT_MODEL = "gpt-4o-mini"


class OpenAIProvider:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model = model

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AgentTurn:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[_to_wire(message) for message in messages],
            tools=[_to_wire_tool(spec) for spec in tools] or None,
        )
        message = response.choices[0].message
        tool_calls = [
            ToolCall(
                id=call.id, name=call.function.name, arguments=json.loads(call.function.arguments)
            )
            for call in (message.tool_calls or [])
        ]
        return AgentTurn(content=message.content, tool_calls=tool_calls)


def _to_wire_tool(spec: ToolSpec) -> dict:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def _to_wire(message: Message) -> dict:
    wire: dict = {"role": message.role}
    if message.content is not None:
        wire["content"] = message.content
    if message.role == "tool":
        wire["tool_call_id"] = message.tool_call_id
    if message.role == "assistant" and message.tool_calls:
        wire["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return wire
