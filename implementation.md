# Technical Implementation Spec — Multi-Model PDF/DB Chat Agent

Companion to `plan.md`. This document is the technical reference for each component — schemas, contracts, config. Update in place as decisions land.

## 1. Architecture overview

```
                        ┌─────────────────────┐
                        │   Web Frontend       │
                        │  (React/Next, chat UI)│
                        └──────────┬───────────┘
                                   │ HTTPS/JWT
                        ┌──────────▼───────────┐
                        │  FastAPI Backend      │
                        │  - auth (JWT)         │
                        │  - chat endpoint      │
                        │  - upload endpoint    │
                        └──────────┬───────────┘
                                   │
                        ┌──────────▼───────────┐
                        │  Agent Orchestrator   │
                        │  (OpenAI function-    │
                        │   calling loop)       │
                        └───┬───────┬───────┬───┘
                            │       │       │
                 ┌──────────▼─┐ ┌───▼────┐ ┌▼─────────────┐
                 │ pdf_search │ │sql_query│ │flatfile_query│
                 │   tool     │ │  tool   │ │    tool      │
                 └─────┬──────┘ └───┬────┘ └──────────────┘
                       │            │
                ┌──────▼─────┐ ┌────▼──────┐
                │  Pinecone   │ │ RDS       │
                │ (vector DB) │ │ Postgres  │
                └──────┬──────┘ └───────────┘
                       │
                ┌──────▼──────┐
                │  S3 (PDF     │
                │  blob store) │
                └──────────────┘

Ingestion (Phase 2b: folder-sync cron, not a web upload):
watched folder (e.g. OneDrive-synced) → cron scan (app/ingestion/cli.py) → S3 →
parse (PyMuPDF) → chunk (recursive splitter) → embed (OpenAI) → Pinecone upsert, all under
one shared system-owner namespace. See §5a.
```

## 2. Repo layout

```
backend/
  app/
    main.py               # FastAPI app entrypoint
    api/
      auth.py              # signup/login/JWT
      chat.py               # POST /chat
      documents.py          # PDF upload/list/delete
    agent/
      orchestrator.py       # tool-calling loop (AgentOrchestrator)
      tool.py                # Tool: a ToolSpec + its execute callable
      deps.py                 # FastAPI provider wiring get_llm_provider
      tools/
        pdf_search.py          # wraps IngestionPipeline.search
        sql_query.py            # v2, deferred
        flatfile_query.py        # v2, deferred
      providers/
        base.py             # LLMProvider Protocol + Message/ToolSpec/ToolCall/AgentTurn
        openai_provider.py
    ingestion/
      ports.py               # BlobStore/VectorStore/Embedder/OcrService protocols + value objects
      parser.py               # PDF text extraction (PyMuPDF)
      chunker.py               # recursive splitter
      blob_store.py             # S3BlobStore (real adapter)
      vector_store.py            # PineconeVectorStore (real adapter)
      embedder.py                 # OpenAIEmbedder (real adapter)
      ocr.py                       # TextractOcrService (real adapter)
      deps.py                       # FastAPI providers wiring the adapters above
      pipeline.py                    # orchestrates parse->OCR->chunk->embed->upsert->status
      system_owner.py                 # ensure_system_user: the one shared-corpus owner (Phase 2b)
      folder_watcher.py                # discover_pdfs / sync_folder: cron ingestion trigger (Phase 2b)
      cli.py                            # `python -m app.ingestion.cli` — what cron actually calls
      scheduler.py                      # poll_forever / IngestionScheduler: auto-ingestion (Phase 8)
      topic_path.py                      # topic_path_for: citation provenance from source_path (Phase 8)
      topic_tree.py                       # discover_topic_tree: live folder taxonomy (Phase 8)
      intake.py                            # IntakeStagingStore / write_confirmed_intake (Phase 8)
      intake_classifier.py                  # suggest_placement: LLM folder suggestion (Phase 8)
    db/
      models.py              # SQLAlchemy models
      migrations/             # Alembic
    core/
      config.py               # env/settings
      security.py               # JWT, password hashing
  tests/
frontend/                 # Next.js 16 (App Router, Turbopack), TypeScript, Tailwind — fully client-rendered
  src/
    app/
      page.tsx             # redirects to /chat or /login based on auth state
      login/page.tsx
      signup/page.tsx
      chat/page.tsx          # the app shell: documents + sessions + chat panel
      layout.tsx               # wraps everything in AuthProvider
    components/
      AuthForm.tsx
      DocumentSidebar.tsx
      IntakeUpload.tsx          # smart intake: file picker -> suggestion -> confirm (Phase 8)
      SessionList.tsx
      ChatPanel.tsx
      MessageBubble.tsx
      CitationBadge.tsx        # the "[filename p.N]" link opening GET /documents/{id}/download
    lib/
      api.ts                    # fetch wrapper + types mirroring the backend's Pydantic response models
      auth-context.tsx            # token in localStorage, attached as a Bearer header
infra/
  terraform/ or cdk/
ingestion/
  (if run as separate batch job instead of inline in backend)
```

## 3. Data model (Postgres)

```sql
users (
  id UUID PK,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
)

chat_sessions (
  id UUID PK,
  user_id UUID FK -> users.id,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
)

chat_messages (
  id UUID PK,
  session_id UUID FK -> chat_sessions.id,
  role TEXT CHECK (role IN ('user','assistant','tool')),
  content TEXT,
  tool_calls JSONB,          -- record of which tools invoked, for audit/citation
  created_at TIMESTAMPTZ DEFAULT now()
)

documents (
  id UUID PK,
  owner_id UUID FK -> users.id,
  filename TEXT,
  s3_key TEXT,
  status TEXT CHECK (status IN ('pending','processing','ready','failed')),
  uploaded_at TIMESTAMPTZ DEFAULT now()
)

document_chunks (
  id UUID PK,
  document_id UUID FK -> documents.id,
  pinecone_id TEXT,           -- vector id in Pinecone
  page INT,
  chunk_index INT,
  text TEXT                   -- store raw chunk for citation display / debugging
)
```

Business SQL tables (the data the `sql_query` tool answers questions about) are a separate schema/connection — see §6, kept distinct from app tables above so the agent's read-only role can't touch `users`/`chat_*`.

## 4. Pinecone index

- Index dimension: 1536 (matches `text-embedding-3-small` default; can truncate via `dimensions` param if switching).
- Metric: cosine.
- Metadata per vector: `{document_id, page, chunk_index, owner_id}`.
- Namespace: one per `owner_id` if per-user document isolation is required (confirm access model — currently assumed each user only queries their own uploaded PDFs).

## 5. Ingestion pipeline detail

1. `POST /documents/upload` → stream file to S3 → insert `documents` row (`status='pending'`).
2. Pipeline runs synchronously in request (small corpus, acceptable latency) or as a background task via FastAPI `BackgroundTasks`:
   - Parse: `fitz` (PyMuPDF) — extract text per page. Flag pages with near-zero extractable text (likely scanned image).
   - OCR: flagged pages sent to AWS Textract. **RESOLVED (Phase 2): synchronous
     `DetectDocumentText` per flagged page**, not the async `StartDocumentTextDetection`
     job originally sketched — Textract's sync API takes one image, so each flagged page
     is rendered to a PNG (PyMuPDF, 300 DPI) and sent individually. A handful of scanned
     pages per upload doesn't warrant job-polling; revisit if a corpus with many scanned
     pages per document shows up. A page OCR can't read is skipped (chunker drops empty
     pages), not treated as a document failure. Keeps OCR compute off the chat backend
     (AWS-managed call, not a local Tesseract process).
   - Chunk: recursive splitter — try paragraph boundaries first, fall back to sentence, target ~500 tokens, ~50–100 token overlap. Preserve `page` number per chunk.
   - Embed: batch chunks through `text-embedding-3-small`.
   - Upsert: Pinecone `upsert` with metadata; write `document_chunks` rows mapping `pinecone_id` back to `document_id`/`page`.
   - Update `documents.status = 'ready'` (or `'failed'` with error logged).

## 6. Tool contracts

All tools exposed to the agent via OpenAI function-calling schema. Each returns structured JSON (not raw prose) so the orchestrator can attach citations.

**MVP scope: `pdf_search` only.** `sql_query`/`flatfile_query` below are v2 (deferred — see `plan.md` Phase 3), documented here for the target contract once the SQL schema is defined.

### `pdf_search(query: str, top_k: int = 5) -> list[Chunk]`
- Embed `query`, similarity search Pinecone (filtered by `owner_id` namespace).
- Return `[{document_id, filename, page, text, score, uploaded_at, source_path, topic_path}]`
  — the last three added in Phase 8: `uploaded_at`/`source_path` come straight from the
  `Document` row (`IngestionPipeline.search`, no Pinecone metadata change needed since
  Phase 2b already had `source_path`); `topic_path` is derived from `source_path` by the
  tool itself (`app/ingestion/topic_path.py::topic_path_for`), not by the pipeline.
- **Implemented in Phase 2 as `IngestionPipeline.search`** (`app/ingestion/pipeline.py`),
  ahead of the Phase 4 agent tool that will wrap it. Reachable now over HTTP via
  `POST /documents/search` — see §8.

### `sql_query(question: str) -> QueryResult` — v2, deferred
- GPT generates SQL against a fixed, injected schema description (table/column names + types, no live introspection at call time to avoid prompt injection via schema).
- **Validation gate before execution:**
  - Reject if statement is not a single `SELECT`.
  - Reject on presence of `;` followed by another statement (stacked queries).
  - Execute via a DB role granted `SELECT` only, no `INSERT/UPDATE/DELETE/DDL` privileges — defense in depth, not the only check.
  - Row limit enforced (`LIMIT 200` appended if absent) to cap response size/cost.
- Return `{sql, columns, rows}`.

### `flatfile_query(question: str, file_id: str) -> QueryResult` — v2, deferred
- Load target CSV/Excel into DuckDB in-process (or pandas `query`/`eval` for simple cases).
- Same SELECT-only generation + validation pattern as `sql_query`, executed against DuckDB.

## 7. Agent orchestrator (Phase 4, implemented)

- Provider interface (`providers/base.py`):
  ```python
  class LLMProvider(Protocol):
      def chat(self, messages: list[Message], tools: list[ToolSpec]) -> AgentTurn: ...
  ```
  **RESOLVED: sync, not `async` as originally sketched** — every other request-path
  dependency in this codebase (`DbSession`, `IngestionPipeline`) is sync; mixing an async
  provider call into an otherwise-sync SQLAlchemy request buys nothing at this scale.
  `openai_provider.py` implements this against OpenAI's function-calling API (`OpenAI().chat.completions.create`).
  Adding a second provider later = new class + swap what `agent/deps.py::get_llm_provider` returns, no orchestrator changes.
- Loop (`AgentOrchestrator.run`, `app/agent/orchestrator.py`): send message history + tool
  specs → model returns either a final answer or tool call(s) → execute tool(s) → append
  tool result to history → re-call model → repeat until final answer or `max_turns` (default
  6). Exceeding the cap returns a fallback message rather than raising, so a runaway loop
  degrades to a user-facing "please rephrase" instead of a 500.
- Citation convention: a tool's `execute(arguments) -> dict` result may include a
  `"citations"` key — a list of `{document_id/table, filename/…, page/…}`-shaped dicts.
  The orchestrator collects and dedupes these across every tool call in the run onto the
  final `AgentResult.citations`, independent of whether the model cited inline in prose.
  `pdf_search` derives one citation per unique `(document_id, page)` from its matches, now
  also carrying `uploaded_at`/`topic_path` (Phase 8, `null` when either is unknown);
  future tools (`sql_query`, `flatfile_query`) follow the same convention rather than
  inventing their own shape.
- System prompt instructs the model to prefer tool lookups over prior knowledge, cite
  `[filename p.N]` inline — extended to `[filename p.N, topic_path, uploaded YYYY-MM-DD]`
  when a result carries those fields (Phase 8) — and, per §11, treat retrieved tool
  content as untrusted data, never as instructions to follow.

## 8. API endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/signup` | create user |
| POST | `/auth/login` | issue JWT |
| POST | `/documents/upload` | upload PDF, triggers ingestion synchronously |
| GET | `/documents` | list user's documents + status |
| GET | `/documents/{id}/download` | raw PDF bytes, for a citation link (Phase 5, not in the original table). Auth via Bearer header or `?token=` — see §11 and §12 |
| DELETE | `/documents/{id}` | remove doc + its Pinecone vectors |
| POST | `/documents/search` | similarity search over the caller's own documents (Phase 2 interim surface for `pdf_search`; not in the original table) |
| POST | `/documents/intake/suggest` | smart intake step 1 (Phase 8): parse an uploaded PDF, ask the LLM for a placement suggestion against the live folder tree, stage it — nothing written to disk yet |
| POST | `/documents/intake/confirm` | smart intake step 2: write the staged file to the author's chosen (or overridden) topic/subfolder and ingest it immediately |
| POST | `/chat` | send message, run agent loop, return `{session_id, message, citations}` as JSON — **RESOLVED: not SSE**, see §7 |
| GET | `/chat/sessions` | list past sessions |
| GET | `/chat/sessions/{id}` | get session history (404 if not the caller's own) |

## 9. Config / secrets (env vars)

```
OPENAI_API_KEY
OPENAI_CHAT_MODEL         # default gpt-4o-mini
PINECONE_API_KEY
PINECONE_INDEX_NAME
DATABASE_URL              # app DB (users, chat, documents)
BUSINESS_DATABASE_URL     # SQL tool target, read-only role
S3_BUCKET_NAME
AWS_REGION
JWT_SECRET
JWT_EXPIRY_MINUTES
INGESTION_FOLDER_PATHS    # comma-separated watched folder(s), Phase 2b
INGESTION_POLL_MINUTES    # default 10 — auto-ingestion poll interval, Phase 8
SYSTEM_OWNER_EMAIL        # default shared-library@system.local, Phase 2b
```

Local: `.env` file, loaded via `pydantic-settings`. Prod: AWS Secrets Manager, injected as ECS task environment variables.

## 10. Deployment (AWS)

**Original plan (below), revised for v1 — see `plan.md` Phase 6 for the full rationale.**
The ECS/ALB/RDS/Terraform architecture described in this section is still the intended
answer if this needs to scale past one box; what's actually being built for v1 is
simpler, documented step by step in `infra/aws-runbook.md`:

- **Compute:** one EC2 instance (`t3.medium`, `eu-central-1`), not ECS/Fargate/ALB —
  `docker-compose.prod.yml` runs Postgres, backend, frontend, and Caddy (reverse proxy +
  automatic TLS) on it directly. No autoscaling in v1.
- **DB:** Postgres containerized on the same instance, not RDS — **no backup job in v1**
  (an instance/volume loss loses all data, an accepted v1 tradeoff). v2: migrate to
  managed RDS.
- **Storage:** S3 bucket — unchanged from the original plan.
- **Vector DB:** Pinecone (external SaaS) — unchanged.
- **Secrets:** `secrets.env` on the instance (same file/format as local dev), not Secrets
  Manager — AWS credentials specifically come from an **EC2 instance role** instead of a
  static key pair, so nothing long-lived sits in that file for S3/Textract access.
- **CI/CD:** GitHub Actions (`.github/workflows/ci.yml`'s `deploy` job) — on push to
  `main`, after lint/test/build-check pass: SSH into the instance, `git pull`, `docker
  compose -f docker-compose.prod.yml up -d --build` directly on the box. No image
  registry (ECR/GHCR) in v1 — only one instance to roll out to.
- **IaC:** none written for v1 — `infra/terraform/` stays empty; the instance, security
  group, Elastic IP, and IAM role are hand-provisioned once via the console
  (`infra/aws-runbook.md`). Revisit Terraform once there's a second environment/instance.

## 11. Security notes

- SQL/flatfile tools: SELECT-only enforcement is layered (prompt instruction + regex/AST validation + DB role privilege) — no single layer trusted alone.
- Prompt injection: PDF content is untrusted input to the model: treat retrieved chunk text as data, not instructions — system prompt explicitly tells model to ignore instructions embedded in retrieved content.
- Per-user document isolation via Pinecone namespace + `owner_id` filter on every query, checked at the tool layer (not just trusted from the prompt).
- JWT short expiry + refresh token pattern for the web app session.
  **RESOLVED (Phase 5): no refresh token yet** — see §12, plan.md Phase 5 backlog.
- `GET /documents/{id}/download` accepts the access token as `?token=` (query string), not
  only a Bearer header, so a citation link opened as a plain browser navigation can
  authenticate. **KNOWN SIMPLIFICATION:** a token in a URL lands in browser history and
  server logs — acceptable for the MVP's local/fake blob store, but swap for a
  short-lived presigned S3 URL (`plan.md` Phase 5 backlog) before this points at real S3.

## 12. Auth implementation (Phase 1, decided)

Own auth, not Cognito. Rejected Cognito because every local test would need a mocked JWKS
endpoint and offline `docker compose` could not authenticate.

- **Hashing:** bcrypt via the `bcrypt` package directly. `passlib` 1.7.4 is *not* used — it
  reads `bcrypt.__about__`, removed in bcrypt 4.1+, so it raises on a current bcrypt.
- **72-byte limit:** bcrypt silently ignores input past 72 bytes, so a long passphrase would
  collide with its own prefix. Passwords are SHA-256 digested and base64-encoded before
  bcrypt (`app/core/security.py::_prepare`). Changing this scheme invalidates stored hashes.
- **Tokens:** PyJWT, HS256, claims `{sub: email, iat, exp}`, `require=["exp","sub"]` on decode.
  All failures collapse to `InvalidTokenError`, surfaced as `401` — never `403` or `500`.
- **Password policy:** minimum 12 characters, enforced by Pydantic (`422` on violation).
- **Email normalised to lowercase** on signup and login, so case cannot create a duplicate
  account or block a valid sign-in.
- **Login timing:** an unknown email still runs a bcrypt hash, so response time does not
  reveal whether an account exists.
- **Serialisation:** `UserPublic` is an explicit response model; the `User` ORM object is
  never serialised directly, so `password_hash` cannot leak.

Refresh tokens are not implemented yet — access token expiry is 30 minutes (§9).
**RESOLVED (Phase 5): still deferred**, not built as part of the frontend after all — the
frontend re-sends the user to `/login` on a 401 rather than silently renewing. Revisit as
a backlog item (`plan.md` Phase 5 backlog) once a 30-minute forced re-login is reported as
actually annoying.

## 13. Testing strategy

Double-loop: BDD outer, TDD inner. Full discipline in `.claude/skills/bdd-tdd/SKILL.md`.

```
backend/tests/
  conftest.py            # client + db_session fixtures; SQLite in-memory (StaticPool)
  unit/                  # pure logic, no I/O
  integration/           # DB-backed and edge paths
  features/*.feature     # Gherkin, one scenario per plan.md exit criterion
  features/steps/        # step defs; status codes and JSON live here, not in the feature
```

- Tests run against SQLite in-memory; models stay portable via `sa.Uuid` and
  `JSON().with_variant(JSONB, "postgresql")`.
- `tests/integration/test_migrations.py` renders the Alembic chain in **offline mode**
  (`alembic upgrade head --sql`, no DB connection) and asserts every model column appears —
  this is the guard against "models edited, migration forgotten".
- `@pytest.mark.integration` marks anything touching a real external service; excluded by
  default via `addopts` in `pyproject.toml`.
- Phase 2+ external services (Pinecone, S3, OpenAI, Textract) sit behind Protocol ports
  (`app/ingestion/ports.py`) with in-memory fakes in `tests/fakes/`, kept honest by one
  contract test parametrized over both the fake and the real adapter — currently covers
  `BlobStore` and `VectorStore` (`tests/contract/test_port_contracts.py`); `Embedder` and
  `OcrService` have fakes but no contract test yet since nothing constrains their output
  shape beyond "list of floats" / "dict of page to text".
- Phase 0 + 1 status: 52 tests, 100% statement coverage of `app/`.
- Phase 2 status: 124 tests total, 93% statement coverage of `app/` — the gap is entirely
  the four real adapters (`blob_store.py`, `vector_store.py`, `embedder.py`, `ocr.py`),
  exercised only by `@pytest.mark.integration` runs against live services, not by default.
- Phase 4 status: 159 tests total, 100% statement coverage of `app/` outside the real
  adapters (now also `openai_provider.py`) — 92% overall, same shape as the Phase 2 gap.
  Chat scenarios script `tests/fakes/llm_provider.py::FakeLLMProvider` per-scenario, the
  same pattern `documents.feature` uses to script the fake OCR service.
- Phase 5 status: 164 backend tests (added `GET /documents/{id}/download` coverage),
  same double-loop discipline as every other phase. **The frontend itself has no
  automated tests** — a deliberate, tracked exception (`plan.md` Phase 5 backlog: add
  Playwright e2e coverage of the login → upload → ask → cited-answer journey). Verified
  manually instead: `tsc --noEmit`, `next lint`, `next build`, and a dev-server render
  check of `/login`, `/signup`, `/chat`.
- Phase 8 status: 225 backend tests, 90% statement coverage of `app/` — same shape of gap
  as every earlier phase (real adapters + `cli.py`, exercised only by
  `@pytest.mark.integration`), plus the new `IngestionScheduler`'s one genuinely
  timing-dependent test (`test_a_second_tick_runs_after_the_interval_elapses`), marked
  `@pytest.mark.integration` for the same reason. `IntakeUpload.tsx` and the
  `CitationBadge.tsx` date/topic rendering were **not** verified by `tsc`/`next build` this
  pass — no Node runtime in the environment this was built in; run the frontend "Tests"
  commands from the README before trusting it.

## 14. Open items (see `plan.md` decision table)

- SQL tool target (v2): new schema vs existing production DB.
- Target concurrency for load testing.
- Refresh-token flow — deferred out of Phase 5, tracked as backlog.
- SSE streaming for `/chat` — deferred out of Phase 5, tracked as backlog.
- Presigned S3 download URLs, replacing the `?token=`-in-query-string pattern.
- Playwright e2e test for Phase 5's exit criterion.
