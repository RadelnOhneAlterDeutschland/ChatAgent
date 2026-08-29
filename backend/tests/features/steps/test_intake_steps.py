"""Step defs for intake.feature (plan.md Phase 8: smart intake).

`FolderPathsDep` is overridden per scenario to point at `tmp_path`, the same override
pattern `conftest.py`'s `client` fixture already uses for the ingestion adapters — see
`app.ingestion.deps.get_ingestion_folder_paths`.
"""

import json
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from app.agent.providers.base import AgentTurn
from app.ingestion.deps import get_ingestion_folder_paths
from tests.features.steps.conftest import auth_headers, build_single_page_pdf

scenarios("intake.feature")


# --- Given -------------------------------------------------------------------


@given(parsers.parse('the topic folders "{topic_a}" and "{topic_b}" already exist'))
def _topic_folders_exist(context: dict, tmp_path: Path, topic_a: str, topic_b: str) -> None:
    (tmp_path / topic_a).mkdir(parents=True, exist_ok=True)
    (tmp_path / topic_b).mkdir(parents=True, exist_ok=True)
    context["client"].app.dependency_overrides[get_ingestion_folder_paths] = lambda: [str(tmp_path)]
    context["watched_folder"] = tmp_path


@given(parsers.parse('"{topic}" already has the subfolder "{subfolder}"'))
def _subfolder_exists(tmp_path: Path, topic: str, subfolder: str) -> None:
    (tmp_path / topic / subfolder).mkdir(parents=True, exist_ok=True)


@given(
    parsers.parse(
        'the classifier will suggest topic "{topic}", subfolder "{subfolder}", '
        'because "{rationale}"'
    )
)
def _classifier_suggests(agent_fakes: dict, topic: str, subfolder: str, rationale: str) -> None:
    payload = {"topic": topic, "subfolder": subfolder, "rationale": rationale}
    agent_fakes["llm_provider"].turns.append(AgentTurn(content=json.dumps(payload)))


@given(parsers.parse('she submitted "{filename}" containing "{text}" for placement'))
def _she_submitted(context: dict, filename: str, text: str) -> None:
    _submit(context, filename, text)


# --- When --------------------------------------------------------------------


def _submit(context: dict, filename: str, text: str) -> None:
    response = context["client"].post(
        "/documents/intake/suggest",
        headers=auth_headers(context),
        files={"file": (filename, build_single_page_pdf(text), "application/pdf")},
    )
    context["response"] = response
    if response.status_code == 200:
        context["suggestion"] = response.json()


@when(parsers.parse('she submits "{filename}" containing "{text}" for placement'))
def _she_submits(context: dict, filename: str, text: str) -> None:
    _submit(context, filename, text)


@when("she confirms the suggested placement")
def _confirms_suggested(context: dict) -> None:
    suggestion = context["suggestion"]
    context["response"] = context["client"].post(
        "/documents/intake/confirm",
        headers=auth_headers(context),
        json={
            "intake_id": suggestion["intake_id"],
            "topic": suggestion["suggested_topic"],
            "subfolder": suggestion["suggested_subfolder"],
        },
    )


@when(parsers.parse('she confirms placement under "{topic}" instead'))
def _confirms_override(context: dict, topic: str) -> None:
    suggestion = context["suggestion"]
    context["response"] = context["client"].post(
        "/documents/intake/confirm",
        headers=auth_headers(context),
        json={"intake_id": suggestion["intake_id"], "topic": topic, "subfolder": None},
    )


@when(parsers.parse('she confirms placement under "{topic}" with new subfolder "{subfolder}"'))
def _confirms_new_subfolder(context: dict, topic: str, subfolder: str) -> None:
    suggestion = context["suggestion"]
    context["response"] = context["client"].post(
        "/documents/intake/confirm",
        headers=auth_headers(context),
        json={"intake_id": suggestion["intake_id"], "topic": topic, "subfolder": subfolder},
    )


# --- Then --------------------------------------------------------------------


@then(parsers.parse('she is offered "{topic}" / "{subfolder}" as the suggested placement'))
def _offered(context: dict, topic: str, subfolder: str) -> None:
    assert context["response"].status_code == 200, context["response"].text
    suggestion = context["response"].json()
    assert suggestion["suggested_topic"] == topic
    assert suggestion["suggested_subfolder"] == subfolder


@then(parsers.parse('"{filename}" is not yet in the shared library'))
def _not_yet_in_library(context: dict, filename: str) -> None:
    response = context["client"].get("/documents", headers=auth_headers(context))
    names = [doc["filename"] for doc in response.json()]
    assert filename not in names, names


@then(parsers.parse('"{filename}" is not yet filed anywhere on disk'))
def _not_yet_on_disk(context: dict, filename: str) -> None:
    matches = list(context["watched_folder"].rglob(filename))
    assert matches == [], matches


@then(parsers.parse('"{filename}" is ready in the shared library'))
def _ready(context: dict, filename: str) -> None:
    response = context["client"].get("/documents", headers=auth_headers(context))
    matches = [doc for doc in response.json() if doc["filename"] == filename]
    assert matches, response.json()
    assert matches[0]["status"] == "ready", matches[0]


@then(parsers.parse('"{filename}" is filed under "{topic_path}"'))
def _filed_under(context: dict, filename: str, topic_path: str) -> None:
    expected = context["watched_folder"] / topic_path / filename
    assert expected.is_file(), list(context["watched_folder"].rglob("*"))


@then("the request is refused as unauthorised")
def _refused_unauthorised(context: dict) -> None:
    assert context["response"].status_code == 401, context["response"].text
