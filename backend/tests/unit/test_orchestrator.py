"""Inner loop: the tool-calling agent loop, against a scripted fake provider.

No network, no DB — `Tool.execute` is a plain callable here, standing in for whatever a
real tool (pdf_search, and later sql_query/flatfile_query) would do.
"""

import pytest

from app.agent.orchestrator import AgentOrchestrator
from app.agent.providers.base import AgentTurn, Message, ToolCall, ToolSpec
from app.agent.tool import Tool
from tests.fakes.llm_provider import FakeLLMProvider

ECHO_SPEC = ToolSpec(name="echo", description="echoes its input", parameters={"type": "object"})


def echo_tool(execute=None) -> Tool:
    return Tool(spec=ECHO_SPEC, execute=execute or (lambda args: {"echoed": args}))


class TestFinalAnswerWithoutTools:
    def test_a_turn_with_no_tool_calls_returns_its_content_directly(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="Hello there.")])
        orchestrator = AgentOrchestrator(provider, tools=[])

        result = orchestrator.run(history=[], user_message="hi")

        assert result.content == "Hello there."

    def test_no_tool_calls_means_no_citations(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="Hello there.")])
        orchestrator = AgentOrchestrator(provider, tools=[])

        result = orchestrator.run(history=[], user_message="hi")

        assert result.citations == []

    def test_the_user_message_is_appended_to_history_before_the_first_call(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="ok")])
        orchestrator = AgentOrchestrator(provider, tools=[])

        orchestrator.run(history=[], user_message="hi")

        sent = provider.received_messages[0]
        assert sent[-1] == Message(role="user", content="hi")

    def test_prior_history_is_sent_before_the_new_user_message(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="ok")])
        orchestrator = AgentOrchestrator(provider, tools=[])
        history = [
            Message(role="user", content="earlier"),
            Message(role="assistant", content="reply"),
        ]

        orchestrator.run(history=history, user_message="hi")

        sent = provider.received_messages[0]
        assert sent[0].role == "system"
        assert sent[1:3] == history


class TestToolCalling:
    def test_a_tool_call_is_executed_and_its_result_sent_back_to_the_model(self) -> None:
        calls = []
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="echo", arguments={"q": "x"})],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(
            provider, tools=[echo_tool(execute=lambda args: calls.append(args) or {"ok": True})]
        )

        result = orchestrator.run(history=[], user_message="hi")

        assert calls == [{"q": "x"}]
        assert result.content == "done"

    def test_the_second_call_includes_the_tool_result_as_a_tool_message(self) -> None:
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="echo", arguments={"q": "x"})],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(provider, tools=[echo_tool()])

        orchestrator.run(history=[], user_message="hi")

        second_call_messages = provider.received_messages[1]
        tool_message = second_call_messages[-1]
        assert tool_message.role == "tool"
        assert tool_message.tool_call_id == "call_1"
        assert tool_message.name == "echo"

    def test_multiple_tool_calls_in_one_turn_are_all_executed(self) -> None:
        seen = []
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="echo", arguments={"q": "a"}),
                        ToolCall(id="call_2", name="echo", arguments={"q": "b"}),
                    ],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(
            provider, tools=[echo_tool(execute=lambda args: seen.append(args) or {})]
        )

        orchestrator.run(history=[], user_message="hi")

        assert seen == [{"q": "a"}, {"q": "b"}]

    def test_an_unknown_tool_name_does_not_crash_the_loop(self) -> None:
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="not_a_real_tool", arguments={})],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(provider, tools=[])

        result = orchestrator.run(history=[], user_message="hi")

        assert result.content == "done"


class TestCitations:
    def test_citations_in_a_tool_result_are_collected(self) -> None:
        citation = {"document_id": "d1", "filename": "revenue.pdf", "page": 1}
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[ToolCall(id="call_1", name="echo", arguments={})],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(
            provider, tools=[echo_tool(execute=lambda args: {"citations": [citation]})]
        )

        result = orchestrator.run(history=[], user_message="hi")

        assert result.citations == [citation]

    def test_duplicate_citations_across_tool_calls_are_deduplicated(self) -> None:
        citation = {"document_id": "d1", "filename": "revenue.pdf", "page": 1}
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None,
                    tool_calls=[
                        ToolCall(id="call_1", name="echo", arguments={}),
                        ToolCall(id="call_2", name="echo", arguments={}),
                    ],
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(
            provider, tools=[echo_tool(execute=lambda args: {"citations": [citation]})]
        )

        result = orchestrator.run(history=[], user_message="hi")

        assert result.citations == [citation]

    def test_a_tool_result_without_citations_contributes_none(self) -> None:
        provider = FakeLLMProvider(
            [
                AgentTurn(
                    content=None, tool_calls=[ToolCall(id="call_1", name="echo", arguments={})]
                ),
                AgentTurn(content="done"),
            ]
        )
        orchestrator = AgentOrchestrator(provider, tools=[echo_tool()])

        result = orchestrator.run(history=[], user_message="hi")

        assert result.citations == []


class TestMaxTurns:
    def test_exceeding_the_turn_cap_returns_a_fallback_instead_of_looping_forever(self) -> None:
        endless_tool_call = AgentTurn(
            content=None, tool_calls=[ToolCall(id="call_1", name="echo", arguments={})]
        )
        provider = FakeLLMProvider([endless_tool_call] * 10)
        orchestrator = AgentOrchestrator(provider, tools=[echo_tool()], max_turns=3)

        result = orchestrator.run(history=[], user_message="hi")

        assert "try rephrasing" in result.content.lower() or "couldn't" in result.content.lower()

    def test_the_turn_cap_bounds_how_many_times_the_provider_is_called(self) -> None:
        endless_tool_call = AgentTurn(
            content=None, tool_calls=[ToolCall(id="call_1", name="echo", arguments={})]
        )
        provider = FakeLLMProvider([endless_tool_call] * 10)
        orchestrator = AgentOrchestrator(provider, tools=[echo_tool()], max_turns=3)

        orchestrator.run(history=[], user_message="hi")

        assert len(provider.received_messages) == 3


class TestSystemPrompt:
    def test_a_system_message_is_prepended_when_none_is_in_history(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="ok")])
        orchestrator = AgentOrchestrator(provider, tools=[])

        orchestrator.run(history=[], user_message="hi")

        sent = provider.received_messages[0]
        assert sent[0].role == "system"

    def test_the_system_message_is_not_duplicated_when_already_in_history(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="ok")])
        orchestrator = AgentOrchestrator(provider, tools=[])
        history = [Message(role="system", content="custom prompt")]

        orchestrator.run(history=history, user_message="hi")

        sent = provider.received_messages[0]
        assert [message.role for message in sent].count("system") == 1


class TestToolSchemaPassthrough:
    def test_registered_tool_specs_are_offered_to_the_provider(self) -> None:
        provider = FakeLLMProvider([AgentTurn(content="ok")])
        orchestrator = AgentOrchestrator(provider, tools=[echo_tool()])

        orchestrator.run(history=[], user_message="hi")

        assert provider.received_tools[0] == [ECHO_SPEC]


@pytest.mark.parametrize("max_turns", [0, -1])
def test_max_turns_must_be_positive(max_turns: int) -> None:
    with pytest.raises(ValueError, match="max_turns"):
        AgentOrchestrator(FakeLLMProvider([]), tools=[], max_turns=max_turns)
