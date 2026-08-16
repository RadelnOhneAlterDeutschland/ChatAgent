from pytest_bdd import given, parsers, scenarios, then, when

from tests.features.steps.conftest import register_user

scenarios("auth.feature")


# --- Given -------------------------------------------------------------------


@given(parsers.parse('no one has registered with "{email}"'))
def _nobody_registered(client, context: dict, email: str) -> None:
    context["client"] = client
    context["email"] = email


@given(parsers.parse('a registered user "{email}" with password "{password}"'))
def _registered_user(client, context: dict, email: str, password: str) -> None:
    context["client"] = client
    context["email"] = email
    context["password"] = password
    register_user(client, email, password)


# --- When --------------------------------------------------------------------


@when(parsers.parse('she registers with "{email}" and password "{password}"'))
@when(parsers.parse('someone else tries to register with "{email}" and password "{password}"'))
def _register(context: dict, email: str, password: str) -> None:
    context["response"] = context["client"].post(
        "/auth/signup", json={"email": email, "password": password}
    )


@when(parsers.parse('she signs in with password "{password}"'))
def _sign_in(context: dict, password: str) -> None:
    context["response"] = context["client"].post(
        "/auth/login", json={"email": context["email"], "password": password}
    )


@when(parsers.parse('"{email}" signs in with password "{password}"'))
def _sign_in_as(context: dict, email: str, password: str) -> None:
    context["response"] = context["client"].post(
        "/auth/login", json={"email": email, "password": password}
    )


@when("she asks who she is")
def _ask_identity(context: dict) -> None:
    token = context.get("token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    context["response"] = context["client"].get("/auth/me", headers=headers)


@when("she asks who she is using a tampered token")
def _ask_identity_tampered(context: dict) -> None:
    tampered = context["token"][:-4] + "AAAA"
    context["response"] = context["client"].get(
        "/auth/me", headers={"Authorization": f"Bearer {tampered}"}
    )


# --- Then --------------------------------------------------------------------


@then("her account exists")
def _account_exists(context: dict) -> None:
    response = context["response"]

    assert response.status_code == 201, response.text
    assert response.json()["email"] == context["email"]
    assert response.json()["id"]


@then("she is not told her own password back")
def _no_password_echo(context: dict) -> None:
    body = context["response"].text

    assert "password" not in body.lower()


@then("the registration is refused as already taken")
def _refused_duplicate(context: dict) -> None:
    assert context["response"].status_code == 409, context["response"].text


@then("the registration is refused as invalid")
def _refused_invalid(context: dict) -> None:
    assert context["response"].status_code == 422, context["response"].text


@then("she receives an access token")
def _receives_token(context: dict) -> None:
    body = context["response"].json()

    assert context["response"].status_code == 200, context["response"].text
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2


@then("she is refused access")
def _refused_access(context: dict) -> None:
    assert context["response"].status_code == 401, context["response"].text


@then(parsers.parse('she is told her email is "{email}"'))
def _told_email(context: dict, email: str) -> None:
    response = context["response"]

    assert response.status_code == 200, response.text
    assert response.json()["email"] == email
