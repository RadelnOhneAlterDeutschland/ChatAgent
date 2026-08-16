---
name: bdd-tdd
description: Double-loop development discipline for this repo — BDD (Gherkin/pytest-bdd) drives the outer acceptance loop from plan.md exit criteria, TDD (pytest) drives the inner unit loop. Use when implementing any phase from plan.md, adding a feature, adding an endpoint, adding a tool to the agent, or when the user says "TDD", "BDD", "write tests first", "red-green-refactor", "acceptance criteria", "gherkin", or "implement phase N".
---

# Double-loop development (BDD outer, TDD inner)

Two nested loops. Never write production code that no failing test demands.

```
OUTER (BDD, business language)          INNER (TDD, technical language)
1. Write .feature scenario  ──────┐
2. Run it — RED (steps missing)   │
3. Write step defs — RED (impl)   │
                                  ├──► 4. Write failing unit test  (RED)
                                  │    5. Minimal code to pass     (GREEN)
                                  │    6. Refactor, tests stay green
                                  │    repeat 4-6 until scenario can pass
7. Scenario GREEN  ◄──────────────┘
8. Refactor across units, all green
9. Commit
```

## Which loop for which work

| Work | Loop |
|---|---|
| API endpoint, user journey, `plan.md` exit criterion | Outer (BDD) first, then inner |
| Pure logic: chunker, SQL validator, token counter, JWT encode/decode | Inner (TDD) only |
| External adapter: Pinecone, S3, OpenAI, Textract | Inner (TDD) against a fake implementing the port interface; one contract test marked `@pytest.mark.integration` |
| Bug fix | Inner: failing test reproducing the bug first, then fix |

Rule: every `plan.md` phase exit criterion becomes at least one Gherkin scenario. The phase is not done until that scenario is green.

## Layout

```
backend/tests/
  conftest.py              # shared fixtures: client, db_session, test_user
  unit/                    # fast, no I/O, no DB — pure functions and classes
    test_security.py
  integration/             # DB / external services, marked @pytest.mark.integration
  features/
    auth.feature           # Gherkin, business language only
    documents.feature
    steps/
      test_auth_steps.py   # MUST be named test_*.py for pytest collection
      conftest.py          # step-local fixtures + scenario context
```

pytest-bdd collects step-def modules, not `.feature` files. The module needs
`scenarios("../auth.feature")` (bind whole file) or `@scenario(...)` per scenario.

## Gherkin rules

Write scenarios in the language of the person who asked for the feature. No
function names, no HTTP status codes, no SQL, no JSON in the steps.

```gherkin
# GOOD — business language, one behaviour per scenario
Scenario: Registered user signs in
  Given a registered user "ana@example.com" with password "correct-horse"
  When she signs in with password "correct-horse"
  Then she receives an access token

# BAD — leaks implementation into the spec
Scenario: POST /auth/login returns 200 with JWT in body.access_token
```

- One behaviour per scenario. If the name needs "and", split it.
- `Given` = state, `When` = the single action under test, `Then` = observable outcome.
- Use `Scenario Outline` + `Examples` for the same behaviour over varying data;
  do not copy-paste scenarios.
- `Background` only for setup shared by *every* scenario in the file.
- Assert on outcomes the requester cares about ("is refused", "receives a token"),
  not on wire format. Put the status-code assertion inside the step def.

## Step definition rules

- Steps carry state through a single mutable `context` dict fixture — never module globals.
- A step does one thing. Reuse steps across features via `features/steps/conftest.py`.
- Parse arguments with `parsers.parse` / `parsers.cfparse`, not regex, unless regex is required.
- Step defs may assert on status codes and JSON — that is where implementation detail belongs.

## Unit test rules (inner loop)

- Name: `test_<unit>_<condition>_<expected>`. e.g. `test_verify_token_expired_raises`.
- Arrange-Act-Assert, blank line between the three.
- One logical assertion per test. Parametrize instead of looping inside a test.
- No network, no real DB, no sleeping, no `time.time()` freedom — inject a clock.
- Test behaviour through the public interface, not private helpers.
- Mock only at architecture boundaries (the port/adapter seam). Never mock the unit under test.

## Ports and adapters (keeps external services testable)

Every external service sits behind an abstract port in the module that needs it.
Production wires the real adapter; tests wire an in-memory fake.

```python
# app/ingestion/ports.py
class VectorStore(Protocol):
    def upsert(self, vectors: list[Vector], namespace: str) -> None: ...
    def query(self, vector: list[float], top_k: int, namespace: str) -> list[Match]: ...
```

Fakes live in `tests/fakes/` and are themselves tested by one shared contract
test parametrized over `[FakeVectorStore, PineconeVectorStore]`, so the fake
cannot drift from the real adapter. Mark the real-adapter run
`@pytest.mark.integration`.

## Commands

```bash
cd backend
.venv/bin/pytest                                  # everything except integration
.venv/bin/pytest tests/unit -q                    # inner loop, fast
.venv/bin/pytest tests/features -q                # outer loop
.venv/bin/pytest -m integration                   # real external services
.venv/bin/pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
```

`-m "not integration"` is the default via `addopts` in `pyproject.toml`.

## Definition of done for a phase

1. Every exit criterion in `plan.md` for that phase has a green scenario.
2. Unit tests cover each branch of new pure logic, including error paths.
3. `ruff check` and `ruff format --check` clean.
4. No production code exists that no test exercises.
5. `plan.md` / `implementation.md` updated in place if a decision landed.

## Anti-patterns — reject these

- Writing implementation first, then tests that describe what the code happens to do.
- Gherkin that reads like an HTTP transcript.
- A scenario asserting several unrelated behaviours so it "covers more".
- Mocking the class under test, or mocking your own pure functions.
- Tests sharing mutable state through module-level variables or import order.
- Skipping the RED step — an unverified test may be asserting nothing.
