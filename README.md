# ChatAgent

Multi-model chat agent over your own PDFs. FastAPI + OpenAI function calling, Pinecone for
retrieval, Postgres for users and chat history, S3 for the documents themselves.

- `plan.md` — phased delivery plan and exit criteria.
- `implementation.md` — technical reference: schemas, contracts, config.
- `.claude/skills/bdd-tdd/SKILL.md` — the development discipline this repo follows.

**Status:** Phase 0 (scaffolding) and Phase 1 (auth + data model) complete. Phase 2 (PDF
ingestion) is next.

## Local development

```bash
cp backend/.env.example backend/.env    # then fill in the secrets
docker compose up --build              # Postgres + backend on :8000, migrations applied
open http://localhost:8000/docs
```

Without Docker:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

## Tests

Double-loop: Gherkin scenarios drive acceptance, pytest units drive the code inside.

```bash
cd backend
.venv/bin/pytest                                     # everything except integration
.venv/bin/pytest tests/unit -q                       # inner loop, fast
.venv/bin/pytest tests/features -q                   # outer loop, acceptance
.venv/bin/pytest -m integration                      # real external services
.venv/bin/pytest --cov=app --cov-report=term-missing
.venv/bin/ruff check app tests && .venv/bin/ruff format --check app tests
```

## Endpoints so far

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + version |
| POST | `/auth/signup` | create account |
| POST | `/auth/login` | issue JWT |
| GET | `/auth/me` | current account |

## Layout

```
backend/app/api/        FastAPI routers and request dependencies
backend/app/core/       settings, password hashing, JWT
backend/app/db/         SQLAlchemy models, session wiring, Alembic migrations
backend/app/agent/      tool-calling orchestrator, tools, LLM providers (Phase 4)
backend/app/ingestion/  parse, chunk, embed, upsert (Phase 2)
backend/tests/          unit / integration / features
frontend/               Next.js chat UI (Phase 5)
infra/terraform/        VPC, ECS, RDS, S3, IAM (Phase 6)
```
