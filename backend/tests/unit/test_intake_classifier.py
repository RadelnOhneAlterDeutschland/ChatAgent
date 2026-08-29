"""Inner loop: `suggest_placement` turns one LLM turn into a placement suggestion, or a
typed error when the response can't be trusted (plan.md Phase 8)."""

import json

import pytest

from app.agent.providers.base import AgentTurn
from app.ingestion.intake_classifier import IntakeClassificationError, suggest_placement
from app.ingestion.topic_tree import TopicFolder
from tests.fakes.llm_provider import FakeLLMProvider

TOPICS = [
    TopicFolder(name="05 Finanzierung", subfolders=["Foerderantraege"]),
    TopicFolder(name="09 Rechtliches", subfolders=[]),
]


def _provider_replying(payload: dict) -> FakeLLMProvider:
    return FakeLLMProvider(turns=[AgentTurn(content=json.dumps(payload))])


def test_no_topics_configured_raises_without_calling_the_model() -> None:
    provider = FakeLLMProvider()

    with pytest.raises(IntakeClassificationError):
        suggest_placement(provider, [], "some text")

    assert provider.received_messages == []


def test_a_valid_response_returns_the_suggested_topic_and_subfolder() -> None:
    provider = _provider_replying(
        {
            "topic": "05 Finanzierung",
            "subfolder": "Foerderantraege",
            "is_new_subfolder": False,
            "rationale": "It's a grant application.",
        }
    )

    result = suggest_placement(provider, TOPICS, "This is a grant application for a rikscha.")

    assert result == {
        "topic": "05 Finanzierung",
        "subfolder": "Foerderantraege",
        "rationale": "It's a grant application.",
    }


def test_a_null_subfolder_is_returned_as_none() -> None:
    provider = _provider_replying(
        {"topic": "09 Rechtliches", "subfolder": None, "rationale": "General legal document."}
    )

    result = suggest_placement(provider, TOPICS, "some legal text")

    assert result["subfolder"] is None


def test_the_folder_tree_is_sent_to_the_model() -> None:
    provider = _provider_replying({"topic": "05 Finanzierung", "subfolder": None, "rationale": "x"})

    suggest_placement(provider, TOPICS, "excerpt text")

    sent = provider.received_messages[0]
    user_message = next(m for m in sent if m.role == "user")
    assert "05 Finanzierung" in user_message.content
    assert "Foerderantraege" in user_message.content
    assert "excerpt text" in user_message.content


def test_a_topic_outside_the_given_list_raises() -> None:
    provider = _provider_replying(
        {"topic": "99 Made Up Topic", "subfolder": None, "rationale": "x"}
    )

    with pytest.raises(IntakeClassificationError):
        suggest_placement(provider, TOPICS, "some text")


def test_unparseable_json_raises() -> None:
    provider = FakeLLMProvider(turns=[AgentTurn(content="not json at all")])

    with pytest.raises(IntakeClassificationError):
        suggest_placement(provider, TOPICS, "some text")


def test_a_response_missing_the_topic_key_raises() -> None:
    provider = _provider_replying({"subfolder": "x", "rationale": "x"})

    with pytest.raises(IntakeClassificationError):
        suggest_placement(provider, TOPICS, "some text")
