# ChatAgent

Multi-model chat agent over your own PDFs. FastAPI + OpenAI function calling, Pinecone for
retrieval, Postgres for users and chat history, S3 for the documents themselves, Next.js
chat UI on top.

- `plan.md` — phased delivery plan and exit criteria.
- `implementation.md` — technical reference: schemas, contracts, config.
- `.claude/skills/bdd-tdd/SKILL.md` — the development discipline this repo follows.

**Status:** Phase 0–5 complete (scaffolding, auth, PDF ingestion + folder-sync pivot, agent
orchestration, frontend). Phase 6 (AWS deployment) and Phase 7 (hardening) not started —
see `plan.md` for what's left.

---

## Local setup guide

Two moving parts: the **backend** (FastAPI + Postgres, run via Docker Compose) and the
**frontend** (Next.js, run with `npm` on your host — not containerized). PDFs are ingested
by dropping them into a watched folder and running a CLI command, not through a web upload
(see Phase 2b in `plan.md`).

### Prerequisites

- Docker + Docker Compose
- Node.js 20+ / npm (frontend)
- Python 3.12+ (only needed if running the backend without Docker)
- Accounts/keys for: OpenAI, Pinecone (an index created, dimension 1536, metric cosine),
  AWS (an S3 bucket + credentials — used for PDF blob storage and, if any of your PDFs are
  scanned, Textract OCR)

There are no local fakes wired into the running app — the four external services above are
real for any manual test run. (Tests use in-memory fakes instead; see "Tests" below.)

### 1. Backend

```bash
cp backend/.env.example backend/.env
```

Fill in `backend/.env`:

| Variable | Notes |
|---|---|
| `JWT_SECRET` | generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `OPENAI_API_KEY` | used for chat + embeddings |
| `OPENAI_CHAT_MODEL` | optional, defaults to `gpt-4o-mini` |
| `PINECONE_API_KEY`, `PINECONE_INDEX_NAME` | index must exist already, dim 1536 / cosine |
| `S3_BUCKET_NAME`, `AWS_REGION` | boto3 uses your default AWS credential chain (`~/.aws/credentials`, env vars, etc.) — not set in `.env` |
| `INGESTION_FOLDER_PATHS` | comma-separated absolute path(s) to watch for PDFs, e.g. `/home/you/chatagent-inbox` |
| `DATABASE_URL` | leave as the example value — `docker-compose.yml` overrides it to point at the `postgres` service |

Then:

```bash
docker compose up --build
```

Starts Postgres + backend on `:8000`, runs Alembic migrations on boot. Confirm with
`open http://localhost:8000/docs` or `curl localhost:8000/health`.

Without Docker:

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install ".[dev]"
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```
(you'll need a Postgres reachable at your `DATABASE_URL` in this case)

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local     # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm install
npm run dev
```

Serves on `:3000`. Auth token lives in `localStorage`; there's no server-rendering
concern here — everything is `"use client"`.

### 3. Ingest a PDF

No web upload endpoint (removed in Phase 2b). Drop a PDF into a directory listed in
`INGESTION_FOLDER_PATHS`, then trigger a sync manually:

```bash
cd backend
.venv/bin/python -m app.ingestion.cli          # or, inside the running container:
docker compose exec backend python -m app.ingestion.cli
```

Logs report new/modified/failed counts. In production this is a cron entry (see the
docstring in `app/ingestion/cli.py`); nothing polls the folder automatically in local dev.
All folder-ingested documents land in one shared corpus (`SYSTEM_OWNER_EMAIL`) visible to
every signed-in user — there's no per-user document isolation for PDFs.

### 4. Try the full journey

1. Open `localhost:3000` → sign up → log in.
2. `/chat` → ask a question about the PDF you ingested.
3. Answer should include a `[filename p.N]` citation badge → click it → opens the PDF at
   that page via `GET /documents/{id}/download#page=N`.

### Known rough edges in local dev

- Deleting a document via the UI doesn't stop the folder watcher from re-ingesting it next
  sync if the file is still on disk (deletion sync not built — `plan.md` Phase 2b).
- No refresh token: JWT expires after 30 minutes, re-login after.
- Textract OCR only fires on pages with near-zero extractable text; needs Textract IAM
  permission on the same AWS credentials as the S3 access.

---

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

Frontend has no automated tests yet (tracked backlog item, `plan.md` Phase 5) — verify
manually with `tsc --noEmit`, `next lint`, `next build`.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + version |
| POST | `/auth/signup` | create account |
| POST | `/auth/login` | issue JWT |
| GET | `/auth/me` | current account |
| GET | `/documents` | list shared document library + status |
| GET | `/documents/{id}/download` | raw PDF bytes; accepts `?token=` for citation-link navigation |
| DELETE | `/documents/{id}` | remove doc + its Pinecone vectors (any signed-in user, not admin-gated yet) |
| POST | `/documents/search` | similarity search spot-check surface (interim, predates the agent tool) |
| POST | `/chat` | send message, run the tool-calling agent loop, returns `{session_id, message, citations}` |
| GET | `/chat/sessions` | list past sessions |
| GET | `/chat/sessions/{id}` | get session history (404 if not the caller's own) |

## Layout

```
backend/app/api/        FastAPI routers and request dependencies
backend/app/core/       settings, password hashing, JWT
backend/app/db/         SQLAlchemy models, session wiring, Alembic migrations
backend/app/agent/      tool-calling orchestrator, tools, LLM providers (Phase 4)
backend/app/ingestion/  parse, chunk, embed, upsert, folder-sync cron (Phase 2 / 2b)
backend/tests/          unit / integration / contract / features
frontend/               Next.js chat UI (Phase 5)
infra/terraform/        VPC, ECS, RDS, S3, IAM — not started yet (Phase 6)
```
