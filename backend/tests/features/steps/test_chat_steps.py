"""Step defs for chat.feature. Scripts the fake LLM provider per scenario — same pattern
as documents.feature scripting the fake OCR service."""

from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from app.agent.providers.base import AgentTurn, ToolCall
from tests.features.steps.conftest import (
    auth_headers,
    build_single_page_pdf,
    login_user,
    register_user,
    run_folder_sync,
)

scenarios("chat.feature")


# --- Given -------------------------------------------------------------------


@given(parsers.parse('"{filename}" containing "{text}" is in the shared library'))
def _document_in_shared_library(
    db_engine, ingestion_fakes: dict, tmp_path: Path, filename: str, text: str
) -> None:
    (tmp_path / filename).write_bytes(build_single_page_pdf(text))
    run_folder_sync(db_engine, ingestion_fakes, tmp_path)


@given(parsers.parse('the assistant will look up "{query}" and reply "{text}"'))
def _assistant_looks_up(agent_fakes: dict, query: str, text: str) -> None:
    agent_fakes["llm_provider"].turns.extend(
        [
            AgentTurn(
                content=None,
                tool_calls=[ToolCall(id="call_1", name="pdf_search", arguments={"query": query})],
            ),
            AgentTurn(content=text),
        ]
    )


@given(parsers.parse('the assistant will reply directly "{text}"'))
def _assistant_replies_directly(agent_fakes: dict, text: str) -> None:
    agent_fakes["llm_provider"].turns.append(AgentTurn(content=text))


@given(parsers.parse('she asked "{message}" and started a session'))
def _she_asked_and_started_session(context: dict, message: str) -> None:
    response = context["client"].post(
        "/chat", headers=auth_headers(context), json={"message": message}
    )
    assert response.status_code == 200, response.text
    context["session_id"] = response.json()["session_id"]


@given(parsers.parse('another registered user "{email}" asked "{message}" and started a session'))
def _another_user_chatted(client, agent_fakes: dict, email: str, message: str) -> None:
    register_user(client, email)
    bob_token = login_user(client, email)
    agent_fakes["llm_provider"].turns.append(AgentTurn(content="Bob's private answer."))

    response = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {bob_token}"},
        json={"message": message},
    )
    assert response.status_code == 200, response.text


# --- When --------------------------------------------------------------------


@when(parsers.parse('she asks "{message}"'))
def _she_asks(context: dict, message: str) -> None:
    context["response"] = context["client"].post(
        "/chat", headers=auth_headers(context), json={"message": message}
    )


@when(parsers.parse('she asks "{message}" in the same session'))
def _she_asks_in_session(context: dict, message: str) -> None:
    context["response"] = context["client"].post(
        "/chat",
        headers=auth_headers(context),
        json={"message": message, "session_id": context["session_id"]},
    )


@when("she lists her chat sessions")
def _lists_sessions(context: dict) -> None:
    context["response"] = context["client"].get("/chat/sessions", headers=auth_headers(context))


# --- Then --------------------------------------------------------------------


@then(parsers.parse('she receives the answer "{text}"'))
def _receives_answer(context: dict, text: str) -> None:
    assert context["response"].status_code == 200, context["response"].text
    assert context["response"].json()["message"] == text


@then(parsers.parse('the answer cites page {page:d} of "{filename}"'))
def _answer_cites(context: dict, page: int, filename: str) -> None:
    citations = context["response"].json()["citations"]
    assert any(c["filename"] == filename and c["page"] == page for c in citations), citations


@then("the answer has no citations")
def _no_citations(context: dict) -> None:
    assert context["response"].json()["citations"] == []


@then("the assistant was shown her earlier message as history")
def _shown_history(context: dict, agent_fakes: dict) -> None:
    last_call_messages = agent_fakes["llm_provider"].received_messages[-1]
    assert any(message.content == "My name is Ana." for message in last_call_messages)


@then(parsers.parse('a session titled "{text}" is among them'))
def _session_titled(context: dict, text: str) -> None:
    titles = [session["title"] for session in context["response"].json()]
    assert text in titles, titles


@then("she has no chat sessions")
def _no_sessions(context: dict) -> None:
    assert context["response"].json() == []


@then("the request is refused as unauthorised")
def _refused_unauthorised(context: dict) -> None:
    assert context["response"].status_code == 401, context["response"].text
