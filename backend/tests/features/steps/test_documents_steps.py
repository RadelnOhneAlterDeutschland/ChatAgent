"""Step defs for documents.feature (Phase 2b: shared corpus via folder-sync cron).

The "cron job" is simulated by calling `sync_folder` directly against the same SQLite
engine and fakes the running `client` app is wired to (`db_engine`/`ingestion_fakes`,
both from `tests/conftest.py`) — SQLite in-memory + `StaticPool` means every `Session`
bound to that engine shares one real connection, so a commit made here is immediately
visible to the app's own request-scoped sessions. This is the same relationship a real
cron process has to the running backend: independent process, same database.
"""

import os
from pathlib import Path

from pytest_bdd import given, parsers, scenarios, then, when

from tests.features.steps.conftest import (
    auth_headers,
    build_single_page_pdf,
    login_user,
    register_user,
    run_folder_sync,
)

scenarios("documents.feature")


def _find_document(client, headers: dict, filename: str) -> dict:
    response = client.get("/documents", headers=headers)
    assert response.status_code == 200, response.text
    matches = [doc for doc in response.json() if doc["filename"] == filename]
    assert matches, f"{filename!r} not found among {response.json()}"
    return matches[0]


# --- Given -------------------------------------------------------------------


@given(parsers.parse('the scanning service can read "{text}" from page {page:d}'))
def _scanner_reads(ingestion_fakes: dict, text: str, page: int) -> None:
    ingestion_fakes["ocr"].page_text[page] = text


@given(parsers.parse('a PDF named "{filename}" containing "{text}" sits in the watched folder'))
def _pdf_in_folder(tmp_path: Path, filename: str, text: str) -> None:
    (tmp_path / filename).write_bytes(build_single_page_pdf(text))


@given(parsers.parse('a scanned PDF named "{filename}" sits in the watched folder'))
def _scanned_pdf_in_folder(tmp_path: Path, filename: str) -> None:
    # No text layer at all — the parser flags it and the pipeline routes it to OCR.
    (tmp_path / filename).write_bytes(build_single_page_pdf(""))


@given(
    parsers.parse('a file named "{filename}" that is not really a PDF sits in the watched folder')
)
def _corrupt_file_in_folder(tmp_path: Path, filename: str) -> None:
    (tmp_path / filename).write_bytes(b"this is not a pdf at all")


@given("the folder-sync job has already run once")
@given("the folder-sync job runs")
@when("the folder-sync job runs")
def _run_sync(db_engine, ingestion_fakes: dict, tmp_path: Path) -> None:
    run_folder_sync(db_engine, ingestion_fakes, tmp_path)


@given(parsers.parse('another registered user "{email}" signs in'))
def _another_user_signs_in(client, context: dict, email: str) -> None:
    register_user(client, email)
    context["bob_token"] = login_user(client, email)


# --- When --------------------------------------------------------------------


@when(
    parsers.parse(
        'the file "{filename}" in the watched folder is replaced with a PDF containing "{text}"'
    )
)
def _replace_file(tmp_path: Path, filename: str, text: str) -> None:
    path = tmp_path / filename
    path.write_bytes(build_single_page_pdf(text))
    os.utime(path, (path.stat().st_mtime + 10, path.stat().st_mtime + 10))


@when("she lists the shared documents")
def _she_lists(context: dict) -> None:
    context["response"] = context["client"].get("/documents", headers=auth_headers(context))


@when("Bob lists the shared documents")
def _bob_lists(client, context: dict) -> None:
    headers = {"Authorization": f"Bearer {context['bob_token']}"}
    context["response"] = client.get("/documents", headers=headers)


@when(parsers.parse('Bob searches for "{query}"'))
def _bob_searches(client, context: dict, query: str) -> None:
    headers = {"Authorization": f"Bearer {context['bob_token']}"}
    context["response"] = client.post("/documents/search", headers=headers, json={"query": query})


@when(parsers.parse('she deletes "{filename}"'))
def _she_deletes(context: dict, filename: str) -> None:
    document = _find_document(context["client"], auth_headers(context), filename)
    context["response"] = context["client"].delete(
        f"/documents/{document['id']}", headers=auth_headers(context)
    )


# --- Then --------------------------------------------------------------------


@then(parsers.parse('"{filename}" is ready in the shared library'))
def _ready(context: dict, filename: str) -> None:
    document = _find_document(context["client"], auth_headers(context), filename)
    assert document["status"] == "ready", document


@then(parsers.parse('"{filename}" is listed as failed in the shared library'))
def _failed(context: dict, filename: str) -> None:
    document = _find_document(context["client"], auth_headers(context), filename)
    assert document["status"] == "failed", document


@then(parsers.parse('"{filename}" appears exactly once in the shared library'))
def _appears_once(context: dict, filename: str) -> None:
    response = context["client"].get("/documents", headers=auth_headers(context))
    matches = [doc for doc in response.json() if doc["filename"] == filename]
    assert len(matches) == 1, response.json()


@then(parsers.parse('"{filename}" is among them'))
def _filename_among(context: dict, filename: str) -> None:
    names = [doc["filename"] for doc in context["response"].json()]
    assert filename in names, names


@then(parsers.parse('"{filename}" is no longer among the shared documents'))
def _filename_gone(context: dict, filename: str) -> None:
    response = context["client"].get("/documents", headers=auth_headers(context))
    names = [doc["filename"] for doc in response.json()]
    assert filename not in names, names


@then(parsers.parse('Bob finds page {page:d} of "{filename}"'))
def _bob_finds(context: dict, page: int, filename: str) -> None:
    results = context["response"].json()
    assert any(r["filename"] == filename and r["page"] == page for r in results), results


@then(parsers.parse('searching for "{query}" finds page {page:d} of "{filename}"'))
def _search_finds(context: dict, query: str, page: int, filename: str) -> None:
    response = context["client"].post(
        "/documents/search", headers=auth_headers(context), json={"query": query}
    )

    assert response.status_code == 200, response.text
    results = response.json()
    assert results, "expected at least one search result"
    assert results[0]["filename"] == filename
    assert results[0]["page"] == page


@then(parsers.parse('searching for "{query}" finds nothing'))
def _search_finds_nothing(context: dict, query: str) -> None:
    response = context["client"].post(
        "/documents/search", headers=auth_headers(context), json={"query": query}
    )

    assert response.status_code == 200, response.text
    assert response.json() == [], response.text


@then("the request is refused as unauthorised")
def _refused_unauthorised(context: dict) -> None:
    assert context["response"].status_code == 401, context["response"].text
