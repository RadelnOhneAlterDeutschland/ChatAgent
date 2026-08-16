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

Two moving parts to run locally: the **backend** (FastAPI + Postgres, via Docker Compose)
and the **frontend** (Next.js, via `npm` on your host — not containerized). PDFs are
ingested by dropping them into a watched folder and running a CLI command, not through a
web upload (see Phase 2b in `plan.md`). There are no local fakes wired into the running
app — OpenAI, Pinecone, and AWS are real for any manual test run (automated tests use
in-memory fakes instead; see "Tests" below).

Pick the guide for your OS:

- [Setup on Windows 11](#setup-on-windows-11)
- [Setup on macOS / Linux](#setup-on-macos--linux)

---

## Setup on Windows 11

The folder-sync ingestion model (Phase 2b) was written with this host in mind: OneDrive's
Windows desktop client syncs cloud files into a real local folder, which is exactly what
`INGESTION_FOLDER_PATHS` points at.

Two ways to run it; pick one and stay in it (don't mix — a venv or `node_modules` built on
one side won't run on the other).

### Option A — native Windows (PowerShell) — recommended if you use OneDrive-for-Windows

**Install prerequisites first:**

| Tool | Get it | Install notes |
|---|---|---|
| Docker Desktop | [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) | Run the installer, keep **"Use WSL 2 instead of Hyper-V"** checked. Reboot if asked. Adds `docker` to PATH itself. |
| Python 3.12+ | [python.org/downloads/windows](https://www.python.org/downloads/windows/) | On the first installer screen, tick **"Add python.exe to PATH"** before clicking Install — easy to miss, and without it `python`/`pip` won't resolve in a new terminal. |
| Node.js 20+ LTS | [nodejs.org](https://nodejs.org/) | Download the **LTS** installer — it adds `node`/`npm` to PATH automatically. |
| Git | [git-scm.com/download/win](https://git-scm.com/download/win) | Default options are fine; adds `git` to PATH automatically. |

Open a **new** PowerShell window after installing (PATH changes don't apply to already-open
terminals) and verify:

```powershell
docker --version
python --version
node --version
git --version
```

If any command isn't found after installing, PATH wasn't updated — fix it manually: Start
→ search "Environment Variables" → **Edit the system environment variables** → **Environment
Variables…** → under **User variables**, select `Path` → **Edit** → **New** → add the
tool's install folder (Python: e.g. `C:\Users\you\AppData\Local\Programs\Python\Python312\`
and its `Scripts\` subfolder) → OK everywhere → open a new terminal.

**Now set up the project:**

```powershell
git clone <this-repo-url>
cd ChatAgent
copy backend\.env.example backend\.env
notepad backend\.env
```

Fill in `backend\.env` — same variables as the macOS/Linux table below. For
`INGESTION_FOLDER_PATHS`, use a real Windows path to your OneDrive sync folder, e.g.
`C:\Users\you\OneDrive\ChatAgent-Inbox` (multiple folders: comma-separate them — Windows
paths don't contain commas, so this is safe).

```powershell
docker compose up --build
```

Docker Desktop handles the Windows-path-to-container translation. Confirm with
`http://localhost:8000/docs`.

Frontend:

```powershell
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Ingest a PDF — run the CLI **inside the container** (simplest; skips needing a native
Windows venv):

```powershell
docker compose exec backend python -m app.ingestion.cli
```

If you'd rather run the backend natively instead of in Docker, the venv activation script
differs from macOS/Linux:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install ".[dev]"
.venv\Scripts\alembic upgrade head
.venv\Scripts\uvicorn app.main:app --reload
.venv\Scripts\python -m app.ingestion.cli
```

AWS credentials (for boto3's default chain, used by S3 + Textract) live at
`%USERPROFILE%\.aws\credentials` — same format as macOS/Linux, just a different path.

### Option B — WSL2 (Ubuntu)

If you'd rather work in a Linux shell: install WSL2 with `wsl --install` (PowerShell, as
Administrator; reboot when it asks), which defaults to an Ubuntu distro. In Docker Desktop,
go to **Settings → Resources → WSL Integration** and enable it for that distro. Then open
the Ubuntu terminal and follow the **[macOS / Linux](#setup-on-macos--linux)** instructions
below verbatim — Docker Desktop's WSL2 integration exposes the same `docker`/
`docker compose` commands there.

One caveat: your OneDrive sync folder lives on the Windows filesystem, reachable from WSL
at `/mnt/c/Users/you/OneDrive/ChatAgent-Inbox` — use that path (not a `C:\` one) for
`INGESTION_FOLDER_PATHS` in this option, and expect cross-filesystem I/O (`/mnt/c/...`) to
be noticeably slower than a native WSL path. If that matters, drop PDFs into a plain WSL
directory instead and give up on syncing straight from OneDrive.

---

## Setup on macOS / Linux

**Install prerequisites first:**

| Tool | Get it | Install notes |
|---|---|---|
| Docker | [docker.com/get-started](https://www.docker.com/get-started/) | macOS: Docker Desktop installer, drag to Applications, launch once. Linux: follow the official per-distro steps at [docs.docker.com/engine/install](https://docs.docker.com/engine/install/) (e.g. `docs.docker.com/engine/install/ubuntu`) — installs `docker` and the `docker compose` plugin, both added to PATH by the package manager. |
| Python 3.12+ | [python.org/downloads](https://www.python.org/downloads/) | macOS: `brew install python@3.12` ([brew.sh](https://brew.sh) if you don't have Homebrew) puts it on PATH automatically. Linux: usually already present as `python3`; if it's older than 3.12, use your distro's package (e.g. the `deadsnakes` PPA on Ubuntu) or [pyenv](https://github.com/pyenv/pyenv). |
| Node.js 20+ LTS | [nodejs.org](https://nodejs.org/) | Either the official installer, `brew install node` on macOS, your distro's package, or [nvm](https://github.com/nvm-sh/nvm) if you want to switch versions — all add `node`/`npm` to PATH. |
| Git | [git-scm.com/downloads](https://git-scm.com/downloads) | Usually preinstalled on macOS/most Linux distros; `brew install git` / your distro's package otherwise. |

Verify in a new terminal:

```bash
docker --version
python3 --version
node --version
git --version
```

If a command isn't found, the install didn't land on your `PATH` — check where it installed
(`brew --prefix`, or `which -a python3`) and add that directory to `PATH` in your shell's
rc file (`~/.zshrc`, `~/.bashrc`, etc.), e.g. `export PATH="$HOME/.local/bin:$PATH"`, then
`source` it or open a new terminal.

**Now set up the project:**

Accounts/keys needed regardless of OS: OpenAI, Pinecone (an index created, dimension 1536,
metric cosine), AWS (an S3 bucket + credentials — used for PDF blob storage and, if any of
your PDFs are scanned, Textract OCR).

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
