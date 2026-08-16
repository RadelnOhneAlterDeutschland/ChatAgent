"""`GET /documents/{id}/download` — the citation link target (plan.md Phase 5).

Documents come from the shared library (Phase 2b's folder-sync), not a web upload — see
`tests/features/steps/conftest.py::run_folder_sync` for why this can seed a document by
calling the sync function directly against the same engine/fakes `client` is wired to.
"""

import uuid

from tests.features.steps.conftest import build_single_page_pdf, run_folder_sync


def _signup_and_login(client, email: str, password: str = "correct-horse-battery") -> str:
    signup = client.post("/auth/signup", json={"email": email, "password": password})
    assert signup.status_code == 201, signup.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _seed_document(db_engine, ingestion_fakes, tmp_path, client, token, filename="revenue.pdf"):
    data = build_single_page_pdf("Fake pdf content for a download test.")
    (tmp_path / filename).write_bytes(data)
    run_folder_sync(db_engine, ingestion_fakes, tmp_path)

    listing = client.get("/documents", headers={"Authorization": f"Bearer {token}"})
    assert listing.status_code == 200, listing.text
    (document,) = [doc for doc in listing.json() if doc["filename"] == filename]
    return document["id"], data


def test_downloading_via_bearer_header_returns_the_ingested_bytes(
    client, db_engine, ingestion_fakes, tmp_path
) -> None:
    token = _signup_and_login(client, "ana@example.com")
    document_id, data = _seed_document(db_engine, ingestion_fakes, tmp_path, client, token)

    response = client.get(
        f"/documents/{document_id}/download", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content == data


def test_downloading_via_token_query_param_also_works(
    client, db_engine, ingestion_fakes, tmp_path
) -> None:
    token = _signup_and_login(client, "ana@example.com")
    document_id, data = _seed_document(db_engine, ingestion_fakes, tmp_path, client, token)

    response = client.get(f"/documents/{document_id}/download?token={token}")

    assert response.status_code == 200
    assert response.content == data


def test_downloading_without_any_credentials_is_unauthorised(
    client, db_engine, ingestion_fakes, tmp_path
) -> None:
    token = _signup_and_login(client, "ana@example.com")
    document_id, _data = _seed_document(db_engine, ingestion_fakes, tmp_path, client, token)

    response = client.get(f"/documents/{document_id}/download")

    assert response.status_code == 401


def test_any_signed_in_user_can_download_a_shared_document(
    client, db_engine, ingestion_fakes, tmp_path
) -> None:
    """Documents are one shared library (plan.md Phase 2b) — unlike the old per-user
    model, a second account is expected to reach the same document, not get a 404."""
    ana_token = _signup_and_login(client, "ana@example.com")
    document_id, data = _seed_document(db_engine, ingestion_fakes, tmp_path, client, ana_token)
    bob_token = _signup_and_login(client, "bob@example.com")

    response = client.get(
        f"/documents/{document_id}/download", headers={"Authorization": f"Bearer {bob_token}"}
    )

    assert response.status_code == 200
    assert response.content == data


def test_downloading_an_unknown_document_id_is_not_found(client) -> None:
    token = _signup_and_login(client, "ana@example.com")

    response = client.get(
        f"/documents/{uuid.uuid4()}/download", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_a_document_row_whose_blob_is_gone_is_reported_not_found(
    client, db_engine, ingestion_fakes, tmp_path
) -> None:
    """The row survived (e.g. the blob store lost the object) — still a 404, not a 500."""
    token = _signup_and_login(client, "ana@example.com")
    document_id, _data = _seed_document(db_engine, ingestion_fakes, tmp_path, client, token)
    ingestion_fakes["blob_store"].objects.clear()

    response = client.get(
        f"/documents/{document_id}/download", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_deleting_an_unknown_document_id_is_not_found(client) -> None:
    token = _signup_and_login(client, "ana@example.com")

    response = client.delete(
        f"/documents/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
