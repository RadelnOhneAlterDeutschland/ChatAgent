# Implementation Plan — Multi-Model PDF/DB Chat Agent

Phased delivery plan. Each phase produces a working, testable increment. See `implementation.md` for technical detail per component.

## Assumptions locked from requirements discussion

- LLM: OpenAI GPT (function/tool-calling agent), architecture kept provider-pluggable for future Anthropic/Google addition.
- **MVP scope: PDF RAG only.** SQL DB and flat-file tools deferred to v2 — SQL schema not yet defined. Agent ships with a single tool (`pdf_search`) until v2.
- Routing: agent decides which tool(s) to call per query (no hardcoded fan-out) — trivial with one tool now, matters once SQL/flatfile land in v2.
- Frontend: web app with multi-user auth.
- Stack: Python/FastAPI backend.
- Vector DB: Pinecone (managed).
- App DB (users, chat history, document metadata): AWS RDS Postgres.
- PDF storage: S3.
- Embedding model: `text-embedding-3-small`.
- Chunking: recursive/semantic splitter, ~500 tokens, ~50–100 token overlap.
- OCR: required (scanned PDFs in corpus) — AWS Textract, async job per upload, keeps CPU-heavy OCR off the chat backend.
- Chat history: no auto-expiry/retention policy — stored indefinitely, user can manually delete own sessions.
- Cloud: AWS (ECS Fargate, RDS, S3, ALB). Fargate task sized small (~0.5 vCPU/1GB) and autoscaled by task count rather than one large fixed instance.

Open items still needing a decision before their phase starts are flagged inline as **DECIDE**.

---

## Development discipline (applies to every phase)

Double-loop: BDD outer (Gherkin acceptance criteria, `backend/tests/features/`), TDD inner
(pytest units, `backend/tests/unit/`). Every exit criterion below becomes at least one
Gherkin scenario; the phase is not done until that scenario is green. See
`.claude/skills/bdd-tdd/SKILL.md`.

---

## Phase 0 — Project scaffolding — **DONE**

- Repo structure: `backend/`, `frontend/`, `infra/`, `ingestion/`.
- Python project setup (FastAPI, `pyproject.toml`, ruff, pytest + pytest-bdd).
- `.env` / secrets convention (local `.env` via `pydantic-settings`, AWS Secrets Manager in prod).
- Docker Compose for local dev: Postgres, backend (Pinecone stays cloud — no local vector DB).
- CI skeleton: GitHub Actions — lint, test, build image.

**Exit criteria:** `docker compose up` runs FastAPI app + Postgres locally; CI green on push.
Covered by `tests/features/health.feature`.

---

## Phase 1 — Auth + data model — **DONE**
echo $ANTHROPIC_API_KEY
- Postgres schema: `users`, `chat_sessions`, `chat_messages`, `documents` (PDF metadata),
  `document_chunks` (chunk-to-Pinecone-id mapping).
- Multi-user auth: JWT issue/verify, password hashing, signup/login endpoints.
  **RESOLVED: own auth (PyJWT HS256 + bcrypt), not Cognito** — no AWS dependency in the test
  loop, and the `users` table was already specified.
- Per-user chat history persistence — stored indefinitely, no auto-expiry (resolved).
- Alembic migrations set up (`0001_initial_schema`), with a drift test asserting every model
  column appears in a migration.

**Exit criteria:** user can register, log in, get JWT; chat history tables ready to receive rows.
Covered by `tests/features/auth.feature` + `tests/integration/test_data_model.py`.

---

## Phase 2 — PDF ingestion pipeline — **DONE**

- S3 bucket + upload endpoint (direct backend upload, multipart — not presigned URL).
- Parser: PyMuPDF, extract text per page.
- OCR: AWS Textract for pages with near-zero extractable text (scanned pages) —
  **RESOLVED: synchronous per-page `DetectDocumentText` against a rendered page image**,
  not the async `StartDocumentTextDetection` job originally sketched. A handful of
  scanned pages per upload doesn't warrant job-polling; revisit if a corpus with many
  scanned pages per document shows up.
- Chunker: recursive splitter (paragraph → sentence → word boundaries), target/overlap in
  tokens, overlap reserved out of the target budget so no chunk ever exceeds it.
- Embedder: OpenAI `text-embedding-3-small`, batch calls (batch size configurable).
- Pinecone upsert: vector + metadata (`document_id`, `owner_id`, `filename`, `page`);
  namespace per owner (`owner-{owner_id}`) for hard isolation, not just a metadata filter.
- Ingestion job trigger: synchronous on upload (small corpus) — the upload endpoint
  doesn't return until the document is `ready` or `failed`.
- **RESOLVED (new, not in the original endpoint table): `POST /documents/search`** —
  interim HTTP surface for this phase's retrieval spot-check. Phase 4's `pdf_search` tool
  wraps `IngestionPipeline.search` directly rather than re-implementing retrieval; the
  endpoint stays as a debugging/ops surface.
- Upload validation: `.pdf` extension required (415 otherwise), 20MB size cap (413
  otherwise, **DECIDE**: placeholder limit, no target given yet).

**Exit criteria:** upload a PDF, confirm chunks land in Pinecone with correct metadata, spot-check retrieval via direct similarity query. Covered by `tests/features/documents.feature`.

**SUPERSEDED by Phase 2b below**: the per-user web upload endpoint this phase built is
removed. What's described above is still what Phase 2 built and is worth keeping as
history — the ingestion internals (parser, OCR, chunker, embedder, Pinecone upsert,
`IngestionPipeline`) are unchanged and still exactly what Phase 2b reuses; only the
*trigger* (web upload → folder-scan cron) and the *ownership model* (per-user → shared)
changed.

---

## Phase 2b — Ingestion pivot: shared corpus via folder-sync cron — **DONE**

Requested after Phase 5 shipped: documents should come from PDFs dropped into a watched
folder (in practice, a OneDrive-synced local folder) rather than a per-user web upload,
and be visible to every signed-in user as one shared library rather than isolated per
uploader.

- **Trigger: folder-scan cron job, not web upload.** `POST /documents/upload` and its
  frontend button are removed. `app/ingestion/folder_watcher.py::sync_folder` walks one
  or more local directories (`INGESTION_FOLDER_PATHS`, comma-separated absolute paths),
  finds `*.pdf` files, and for each new-or-modified file (tracked by `source_path` +
  mtime) reads the bytes, puts them through the *same* `blob_store.put` → `pipeline.ingest`
  path the old upload endpoint used — no ingestion-internals rework, only a new entry
  point. `app/ingestion/cli.py` (`python -m app.ingestion.cli`) is what a host cron entry
  or a scheduled container run actually calls.
- **OneDrive:** not a distinct integration. The OneDrive desktop client syncs cloud files
  into a real local directory; that directory is just one of `INGESTION_FOLDER_PATHS`.
  Reading directly from Microsoft Graph (no local sync client) was considered and
  rejected as unnecessary scope for now — **DECIDE** if a host without OneDrive-desktop
  access ever needs this.
- **Ownership: one shared corpus, not per-user.** All folder-ingested documents belong to
  a single well-known system user (`SYSTEM_OWNER_EMAIL`, get-or-created by
  `app/ingestion/system_owner.py::ensure_system_user` — not a real login). Every signed-in
  user's `pdf_search` tool call and `GET /documents`/`POST /documents/search` now resolve
  to *that* owner's Pinecone namespace, not `current_user.id`. This removes Phase 1's
  per-user document isolation for PDFs entirely — chat search and the document list are
  the same for every account. `DELETE /documents/{id}` still works (any signed-in user can
  delete any shared document — **no admin-only restriction yet, DECIDE**) but a deleted
  file still present in the watched folder is **not** currently protected: the next cron
  run has no record of it and re-ingests it. See "not built" below.
- **Not built (explicit backlog, not silently skipped):**
  - **Deletion sync.** Removing a file from the watched folder does not remove its
    `Document`/vectors — the watcher only handles new/modified files. A manually
    `DELETE`d document reappears on the next cron run if the file is still on disk.
  - **Direct Microsoft Graph API integration**, if a non-OneDrive-desktop host ever needs
    cloud-direct reads instead of a synced local folder.
  - Cron scheduling itself is left to the deploy environment (a host crontab line or a
    scheduled container run) — not wired into `docker-compose.yml` as a service in this
    pass.

**Exit criteria:** a PDF placed in a watched folder becomes searchable by any signed-in
user without any web upload step; a modified file re-ingests; a corrupt file lands
`status="failed"` rather than crashing the sync. Covered by `tests/features/documents.feature`
(rewritten this phase — upload/isolation scenarios retired, folder-sync/shared-search
scenarios added) and `tests/unit/test_folder_watcher.py`.

---

## Phase 3 (v2, deferred) — Structured data (SQL + flat file) tools

Not part of MVP — SQL schema not yet defined. Revisit once a schema/source DB is chosen.

- Load target SQL tables into RDS Postgres (or connect to existing DB — **DECIDE:** new schema vs pointing at existing production tables).
- Read-only DB role for the agent's SQL execution path.
- Text-to-SQL tool: GPT generates SQL from schema + question; validate against allowlist (SELECT-only, no DDL/DML) before execution.
- Flat-file tool: load CSV/Excel into a queryable form (pandas / DuckDB in-process), expose as a callable tool.
- Agent orchestrator (Phase 4) gets `sql_query`/`flatfile_query` registered alongside `pdf_search` at this point; routing logic already generic, no rework needed.

**Exit criteria:** natural-language question against SQL table returns correct row(s); same for a sample flat file; destructive query attempts are rejected.

---

## Phase 4 — Agent orchestration (MVP: PDF only) — **DONE**

- Tool definitions: `pdf_search(query)` (only tool registered for MVP; `sql_query`/`flatfile_query` added in Phase 3/v2 without orchestrator changes) — wraps `IngestionPipeline.search` (Phase 2), not reimplemented.
- Agent loop (OpenAI function calling): system prompt, tool schema registration, multi-turn tool chaining, citation passthrough (source file/page). Max 6 turns; exceeding the cap returns a fallback message instead of raising.
- Chat endpoint: `POST /chat` — takes user message + session id, runs agent loop.
  **RESOLVED: JSON response, not SSE streaming** — the orchestrator only has a complete
  turn once every tool call resolves, so there's no incremental token stream to forward
  yet. Revisit alongside Phase 5's frontend integration.
- Provider abstraction layer: `LLMProvider` (`app/agent/providers/base.py`), thin interface so a second LLM provider can be added later without touching tool code.
  **RESOLVED: sync, not `async`** — every other request-path dependency in this codebase
  (`DbSession`, `IngestionPipeline`) is sync; matches the OCR/embedder precedent from
  Phase 2 of narrowing an aspirational sketch to what the rest of the stack actually is.
- Citation convention: any tool's `execute` result may carry a `"citations"` key (list of
  `{document_id, filename, page}`-shaped dicts); the orchestrator collects and dedupes
  these across all tool calls in a turn onto the final `AgentResult`, independent of
  whether the model inlined a citation in its prose. Future tools (`sql_query`,
  `flatfile_query`) follow the same convention.
- `GET /chat/sessions` / `GET /chat/sessions/{id}` implemented per implementation.md §8
  (not a separate exit criterion, but needed for a session to be continuable at all).

**Exit criteria:** query against uploaded PDFs returns a correct, cited answer (source file + page) through the chat endpoint. Covered by `tests/features/chat.feature`.

---

## Phase 5 — Frontend — **DONE**

- Stack: Next.js 16 (App Router, Turbopack), TypeScript, Tailwind. Fully client-rendered
  (every page/component is `"use client"`) — nothing here depends on Next 16's server-side
  request APIs (`cookies()`/`headers()`/async `params`), so none of that migration surface
  applies. Auth token lives in `localStorage`, attached as a Bearer header by
  `frontend/src/lib/api.ts`.
- Chat UI: message list, source citation display.
  **RESOLVED: JSON response, not streaming** — matches Phase 4's `POST /chat` shape as
  shipped. See "Backlog" below for SSE.
  **RESOLVED: citations are a `[filename p.N]` link badge that opens the PDF in a new
  browser tab** (`GET /documents/{id}/download`, `#page=N`), not an embedded in-app PDF
  viewer — no new rendering dependency for the MVP.
- Auth UI: login/signup, session handling.
  **RESOLVED: no refresh-token flow** — the existing 30-minute access token is it; the
  user re-logs-in after expiry. See "Backlog" below.
- PDF upload UI: per-user (matches Phase 1's access model — each user only sees their own
  documents), a sidebar with upload/status/delete alongside the chat panel and session list.
  **SUPERSEDED by Phase 2b:** the upload button is removed — documents now arrive via a
  folder-sync cron job into one shared corpus. The sidebar keeps status/delete, listing
  the shared library rather than a per-user one.
- **New backend surface added to support this phase:** `GET /documents/{id}/download`
  (§8) — the citation link target. Auth accepts `?token=` as well as a Bearer header
  (`CurrentUserFlexible`, `app/api/deps.py`) since a citation is opened as a plain browser
  navigation that can't set a header. **KNOWN SIMPLIFICATION:** this puts the access token
  in a URL (browser history, server logs) — swap for a presigned S3 URL before production
  (see "Backlog").
- **No automated frontend tests** — verified manually (typecheck, lint, `next build`, and
  a dev-server render check of `/login`, `/signup`, `/chat`). See "Backlog" for adding
  Playwright e2e coverage of the exit criterion below.

**Exit criteria:** full user journey in browser — log in, upload PDF, ask question, see cited answer.

### Backlog (deferred out of Phase 5, not blocking)

- **SSE streaming for `/chat`.** Phase 4 shipped a JSON response; the orchestrator would
  need to stream through tool-calling turns and the OpenAI provider would need to stream
  deltas — real backend work, not just a frontend change. Revisit once buffered JSON
  proves too slow/unresponsive in practice.
- **Refresh-token flow.** New table + endpoint + silent-renewal client logic. Revisit once
  a 30-minute forced re-login is actually reported as annoying.
- **Presigned S3 download URLs**, replacing `GET /documents/{id}/download`'s
  `?token=`-in-query-string pattern, once real S3 (not the local fake) is in the loop.
- **Playwright e2e test** driving the Phase 5 exit criterion end to end (login → upload →
  ask → see cited answer) in a real browser — the only piece of the double-loop discipline
  skipped this phase.

---

## Phase 6 — AWS deployment

- Terraform/CDK: VPC, ECS Fargate service, ALB, RDS Postgres, S3 bucket, IAM roles, Secrets Manager entries.
- Fargate task sizing: start small (~0.5 vCPU / 1GB per task, roughly `t3.medium`-equivalent handles ~50-150 concurrent chat sessions since the backend is I/O-bound, not CPU-bound). Autoscale task count on request/CPU rather than fixing one large instance — cheaper at idle, scales up under load.
- GitHub Actions: build → push ECR → deploy ECS on merge to main.
- Pinecone: prod index provisioned, API key in Secrets Manager.
- Observability: structured logging, basic CloudWatch alarms (5xx rate, latency).

**Exit criteria:** app reachable via ALB URL in AWS, same user journey as Phase 5 works against prod infra.

---

## Phase 7 — Hardening

- Rate limiting on chat endpoint (cost control for LLM calls).
- Input validation / prompt-injection mitigation on tool-calling paths (especially SQL tool).
- Retrieval eval: sample query set, check chunk relevance, tune chunk size/overlap if needed.
- Load test basic concurrency target — **DECIDE:** expected concurrent user count.
- Cost monitoring: OpenAI usage + Pinecone + RDS.

**Exit criteria:** agreed non-functional targets (latency, cost/query, concurrency) met.

---

## Decisions still needed (blockers by phase)

| Phase | Decision | Status |
|---|---|---|
| 1 | Own auth vs Cognito | **Resolved: own auth, PyJWT HS256 + bcrypt** |
| 2 | Textract async job vs sync per-page | **Resolved: sync `DetectDocumentText` per flagged page** |
| 2 | Upload size limit | **Superseded by Phase 2b** — the endpoint this limited is removed |
| 4 | `LLMProvider.chat` async vs sync | **Resolved: sync** — matches the rest of the request path |
| 4 | `/chat` streaming vs JSON | **Resolved: JSON for now** — SSE deferred, now Phase 5's backlog |
| 4 | Chat model | `gpt-4o-mini` default, `OPENAI_CHAT_MODEL` env override — **DECIDE:** revisit for quality/cost once real usage exists |
| 5 | SSE streaming | **Resolved: deferred** — backlog item, JSON stays until buffered responses prove too slow |
| 5 | Refresh-token flow | **Resolved: deferred** — backlog item, 30-min forced re-login stays until reported annoying |
| 5 | Citation UX: link badge vs embedded viewer | **Resolved: simple link badge** — opens PDF in a new tab via `GET /documents/{id}/download#page=N` |
| 5 | Frontend automated tests | **Resolved: none for now** — backlog item, Playwright e2e is the plan when picked back up |
| 2b | Ingestion trigger: web upload vs folder-sync cron | **Resolved: folder-sync cron**, web upload removed |
| 2b | Document ownership: per-user vs shared corpus | **Resolved: one shared corpus** — Phase 1's per-user PDF isolation is gone |
| 2b | OneDrive: synced local folder vs direct Graph API | **Resolved: synced local folder** — Graph API integration is open if a host has no OneDrive desktop client |
| 2b | Deletion sync (folder → DB/vectors) | Open — not built; see Phase 2b "not built" |
| 2b | Cron scheduling mechanism (host crontab vs docker-compose service) | Open — left to the deploy environment |
| 2b | Shared-document delete: admin-only vs any signed-in user | Open — currently any signed-in user |
| 3 (v2) | New SQL schema vs existing production DB | Open |
| 7 | Target concurrent user count | Open |
