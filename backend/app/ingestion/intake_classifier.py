"""Asks the configured LLM to suggest which existing (or new) topic/subfolder a newly
submitted document belongs in, given the live folder tree (plan.md Phase 8). The
suggestion is advisory only — `api/documents.py`'s confirm endpoint is what actually
writes anything to disk; nothing here has a side effect.
"""

import json

from app.agent.providers.base import LLMProvider, Message
from app.ingestion.topic_tree import TopicFolder

CLASSIFIER_SYSTEM_PROMPT = (
    "You file documents into an existing folder taxonomy. You are given the current "
    "top-level topics and, for each, its existing subfolders, plus the extracted text of "
    "a new document. Pick the single best-fitting top-level topic from the list — never "
    "invent a new top-level topic. For the subfolder, prefer an existing one if it fits; "
    "only propose a new subfolder name when nothing existing fits well. Respond with "
    "strict JSON only, no prose outside the JSON object, in this exact shape: "
    '{"topic": "<one of the given top-level topic names>", '
    '"subfolder": "<an existing or new subfolder name, or null>", '
    '"is_new_subfolder": <true|false>, "rationale": "<one sentence, same language as the '
    'document>"}'
)


class IntakeClassificationError(Exception):
    """The model's response could not be parsed into a placement suggestion, or named a
    topic that doesn't exist."""


def suggest_placement(provider: LLMProvider, topics: list[TopicFolder], excerpt: str) -> dict:
    if not topics:
        raise IntakeClassificationError("no topic folders are configured to file into")

    tree_description = "\n".join(
        f"- {topic.name} (subfolders: {', '.join(topic.subfolders) or 'none yet'})"
        for topic in topics
    )
    user_prompt = (
        f"Existing folder taxonomy:\n{tree_description}\n\nNew document excerpt:\n{excerpt}"
    )

    turn = provider.chat(
        [
            Message(role="system", content=CLASSIFIER_SYSTEM_PROMPT),
            Message(role="user", content=user_prompt),
        ],
        [],
    )

    try:
        parsed = json.loads(turn.content or "")
        topic = parsed["topic"]
        subfolder = parsed.get("subfolder") or None
        rationale = parsed.get("rationale", "")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IntakeClassificationError(f"could not parse placement suggestion: {exc}") from exc

    valid_topics = {topic.name for topic in topics}
    if topic not in valid_topics:
        raise IntakeClassificationError(f"model suggested an unknown topic: {topic!r}")

    return {"topic": topic, "subfolder": subfolder, "rationale": rationale}
