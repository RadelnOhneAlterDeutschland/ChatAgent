"""Edge paths that would clutter the business-language feature file."""

from sqlalchemy import select

from app.core.security import create_access_token
from app.db.models import User


def test_a_valid_token_for_a_deleted_account_is_refused(client, db_session) -> None:
    client.post("/auth/signup", json={"email": "ana@example.com", "password": "correct-horse-1"})
    token = client.post(
        "/auth/login", json={"email": "ana@example.com", "password": "correct-horse-1"}
    ).json()["access_token"]
    user = db_session.execute(select(User).where(User.email == "ana@example.com")).scalar_one()
    db_session.delete(user)
    db_session.commit()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_a_token_for_an_account_that_never_existed_is_refused(client) -> None:
    token = create_access_token(subject="ghost@example.com")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_signup_normalises_the_email_so_case_cannot_create_a_duplicate(client) -> None:
    client.post("/auth/signup", json={"email": "Ana@Example.com", "password": "correct-horse-1"})

    duplicate = client.post(
        "/auth/signup", json={"email": "ana@example.com", "password": "correct-horse-2"}
    )

    assert duplicate.status_code == 409


def test_login_is_case_insensitive_on_the_email(client) -> None:
    client.post("/auth/signup", json={"email": "ana@example.com", "password": "correct-horse-1"})

    response = client.post(
        "/auth/login", json={"email": "ANA@example.com", "password": "correct-horse-1"}
    )

    assert response.status_code == 200


def test_an_unparseable_authorization_header_is_refused(client) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})

    assert response.status_code == 401
