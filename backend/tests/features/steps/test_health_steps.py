from pytest_bdd import given, scenarios, then, when

scenarios("health.feature")


@given("the service is running")
def _service_running(client, context: dict) -> None:
    context["client"] = client


@when("an operator checks the service health")
def _check_health(context: dict) -> None:
    context["response"] = context["client"].get("/health")


@then("the service reports that it is healthy")
def _reports_healthy(context: dict) -> None:
    response = context["response"]

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@then("the service reports its version")
def _reports_version(context: dict) -> None:
    version = context["response"].json()["version"]

    assert isinstance(version, str)
    assert version
