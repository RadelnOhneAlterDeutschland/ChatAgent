"""Step-local fixtures and the Given steps shared across every feature file.

pytest-bdd matches step text only within the fixture-resolution chain reachable from the
running test — a step defined inside one `test_*_steps.py` module is invisible to a
scenario in another. Steps genuinely shared across features (a signed-in user, an
anonymous visitor) live here instead, per `.claude/skills/bdd-tdd/SKILL.md`.
"""

from datetime import timedelta
from pathlib import Path

import fitz
import pytest
from pytest_bdd import given, parsers
from sqlalchemy.orm import sessionmaker

VALID_PASSWORD = "correct-horse-battery"


@pytest.fixture
def context() -> dict:
    return {}


def register_user(client, email: str, password: str = VALID_PASSWORD) -> None:
    response = client.post("/auth/signup", json={"email": email, "password": password})
    assert response.status_code == 201, response.text


def login_user(client, email: str, password: str = VALID_PASSWORD) -> str:
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def build_single_page_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text, fontsize=11)
    return document.tobytes()


def auth_headers(context: dict) -> dict:
    token = context.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def run_folder_sync(db_engine, ingestion_fakes: dict, folder: Path):
    """Simulates the Phase 2b cron job: `sync_folder` against the same SQLite engine and
    fakes the running `client` app is wired to (both from `tests/conftest.py`) — SQLite
    in-memory + `StaticPool` means every `Session` bound to that engine shares one real
    connection, so a commit made here is immediately visible to the app's own
    request-scoped sessions. Shared by `test_documents_steps.py` and `test_chat_steps.py`.
    """
    from app.ingestion.folder_watcher import sync_folder
    from app.ingestion.pipeline import IngestionPipeline

    factory = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    session = factory()
    pipeline = IngestionPipeline(
        blob_store=ingestion_fakes["blob_store"],
        ocr=ingestion_fakes["ocr"],
        embedder=ingestion_fakes["embedder"],
        vector_store=ingestion_fakes["vector_store"],
    )
    try:
        return sync_folder(session, pipeline, [str(folder)])
    finally:
        session.close()


@given(parsers.parse('a signed-in user "{email}"'))
def _signed_in_user(client, context: dict, email: str) -> None:
    context["client"] = client
    context["email"] = email
    register_user(client, email)
    context["token"] = login_user(client, email)


@given(parsers.parse('a signed-in user "{email}" whose token has expired'))
def _expired_token_user(client, context: dict, email: str) -> None:
    from app.core.security import create_access_token

    context["client"] = client
    context["email"] = email
    register_user(client, email)
    context["token"] = create_access_token(subject=email, expires_delta=timedelta(minutes=-1))


@given("a visitor who has not signed in")
def _anonymous_visitor(client, context: dict) -> None:
    context["client"] = client
    context["token"] = None
