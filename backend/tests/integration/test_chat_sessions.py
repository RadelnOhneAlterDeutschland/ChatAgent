"""Error-path coverage for `api/chat.py::_get_owned_session`, shared by `POST /chat`
(continuing a session) and `GET /chat/sessions/{id}`. Not a plan.md exit criterion on its
own, so it isn't in chat.feature — see `.claude/skills/bdd-tdd/SKILL.md`'s "cover each
branch, including error paths" rule.
"""

import uuid

from app.agent.providers.base import AgentTurn


def _signup_and_login(client, email: str, password: str = "correct-horse-battery") -> str:
    signup = client.post("/auth/signup", json={"email": email, "password": password})
    assert signup.status_code == 201, signup.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_continuing_an_unknown_session_id_is_not_found(client) -> None:
    token = _signup_and_login(client, "ana@example.com")

    response = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "hi", "session_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


def test_fetching_an_unknown_session_id_is_not_found(client) -> None:
    token = _signup_and_login(client, "ana@example.com")

    response = client.get(
        f"/chat/sessions/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404


def test_a_sessions_own_messages_are_returned_in_order(client, agent_fakes) -> None:
    token = _signup_and_login(client, "ana@example.com")
    agent_fakes["llm_provider"].turns.append(AgentTurn(content="Hi Ana."))
    headers = {"Authorization": f"Bearer {token}"}

    started = client.post("/chat", headers=headers, json={"message": "Hello"})
    session_id = started.json()["session_id"]

    detail = client.get(f"/chat/sessions/{session_id}", headers=headers)

    assert detail.status_code == 200
    roles = [message["role"] for message in detail.json()["messages"]]
    assert roles == ["user", "assistant"]
