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

## Phase 6 — AWS deployment — **IN PROGRESS, v1 revised down from the original ECS plan**

**Original plan (below, superseded for v1):** Terraform/CDK provisioning VPC, ECS
Fargate, ALB, RDS Postgres, S3, IAM roles, Secrets Manager; GitHub Actions build → push
ECR → deploy ECS. Written before Phase 2b/8 reframed this as one organization's internal
document library at a scale plan.md itself estimated at ~50-150 concurrent sessions — not
a public multi-tenant SaaS. Revisited at implementation time in favor of the simpler v1
below; the ECS/ALB/RDS version is still the right answer if this ever needs to scale past
one box (a second environment, autoscaling, uptime SLAs) — see "v2" below.

**v1, as being built — single EC2 instance, no Terraform:**
- **Compute:** one EC2 instance (`t3.medium`, `eu-central-1`/Frankfurt — physically in
  Germany, lower latency to the user base than `eu-west-1`/Ireland) running
  `docker-compose.prod.yml`: Postgres, backend (`base` Dockerfile target), frontend (new
  `frontend/Dockerfile`, `output: "standalone"`, Node `next start` — the frontend was
  host-`npm run dev`-only through Phase 5, this is its first containerized form), and
  Caddy (reverse proxy + automatic Let's Encrypt TLS). **RESOLVED: `t3.medium` over
  `t3.small`** — the two share identical CPU (2 vCPU, 20% baseline, 24 credits/hr; `t3`'s
  CPU allowance doesn't change until `t3.large`), so the only real tradeoff is RAM (2GB
  vs 4GB) for a small cost step-up, and this box runs four services sharing memory, not
  just the backend the original Fargate-task estimate sized for.
- **Single origin, not CORS:** Caddy path-routes `/api/*` → backend, everything else →
  frontend, on the same host — so the browser only ever makes same-origin requests and
  `main.py`'s CORS middleware needed no prod-specific change.
- **Postgres:** containerized on the same box, **no backup job in v1** (accepted
  tradeoff — an instance/volume loss loses all data). **v2: migrate to managed RDS**
  (automated backups/patching/failover) — tracked as open, see the decision table.
- **IAM:** an EC2 instance role/profile scoped to just the S3 bucket + Textract, not
  static `AWS_ACCESS_KEY_ID`/`SECRET` in `secrets.env` — no long-lived key on the box.
- **TLS/domain:** no domain purchased yet — `nip.io` (free, real Let's Encrypt cert
  against the Elastic IP) is the beta stopgap; swapping to a real domain later is one
  `PUBLIC_SITE_ADDRESS` value change, nothing else. Elastic IP costs $0.005/hr regardless
  (AWS's Feb-2024 pricing change made this the same whether it's a default public IP or
  an Elastic IP, attached or idle) — it's not an extra cost over having a public IP at
  all, just the one that doesn't change under you.
- **Deploy:** GitHub Actions (`deploy` job in `.github/workflows/ci.yml`, after
  `lint-and-test`/`build-image` pass on `main`) SSHes into the box and runs `git pull &&
  docker compose -f docker-compose.prod.yml up -d --build` directly on it — no image
  registry (ECR/GHCR) yet, since there's only the one box to roll out to.
- **IaC:** none written for v1 (`infra/terraform/` stays empty) — hand-provisioned once
  via the console, documented step by step in `infra/aws-runbook.md`. Revisit Terraform
  once there's a second environment or instance to keep in sync with the first.
- **Not built yet (v1 gap, tracked):** `rclone`↔OneDrive-for-Business bidirectional sync
  feeding `INGESTION_FOLDER_PATHS` on the box — blocked on the org's Microsoft 365 tenant
  OAuth consent, not an engineering blocker for the rest of Phase 6. See
  `infra/aws-runbook.md`'s "Not covered yet".
- **Observability:** not yet added (structured logging/alarms) — CloudWatch's original
  role in the ECS plan doesn't map cleanly onto one plain EC2 instance; revisit alongside
  whatever monitoring approach fits v1 or the v2 RDS/ECS migration.

**Exit criteria:** app reachable over HTTPS via the Elastic IP (`nip.io` address), same
user journey as Phase 5 works against this instance.

---

## Phase 7 — Hardening

- Rate limiting on chat endpoint (cost control for LLM calls).
- Input validation / prompt-injection mitigation on tool-calling paths (especially SQL tool).
- Retrieval eval: sample query set, check chunk relevance, tune chunk size/overlap if needed.
- Load test basic concurrency target — **DECIDE:** expected concurrent user count.
- Cost monitoring: OpenAI usage + Pinecone + RDS.

**Exit criteria:** agreed non-functional targets (latency, cost/query, concurrency) met.

---

## Phase 8 — Smart intake, citation provenance, automatic ingestion — **DONE**

Requested after Phase 5 shipped. Extends Phase 2b (ingestion), Phase 4 (citations), and
Phase 5 (frontend) rather than replacing any of them — the folder-sync cron keeps working
unchanged for the existing corpus.

**As built:** no migration needed — `documents.source_path`/`uploaded_at` already existed
(Phase 2b), so citation provenance is derived at read time
(`app/ingestion/topic_path.py::topic_path_for`) rather than stored redundantly.
`app/ingestion/scheduler.py` (`poll_forever` + `IngestionScheduler`) runs the same
`sync_folder` the CLI uses, on a background thread started from `app/main.py`'s lifespan;
inert by default (`INGESTION_FOLDER_PATHS` unset, as in every test run). Smart intake is
`app/ingestion/{topic_tree,intake,intake_classifier}.py` plus two new endpoints,
`POST /documents/intake/suggest` and `POST /documents/intake/confirm` — the pending upload
sits in an in-memory `IntakeStagingStore` between the two calls (**known simplification**:
lost on restart, same tracked-gap pattern as Phase 2b's deletion sync). Frontend:
`IntakeUpload.tsx` (file picker → suggestion → editable topic/subfolder picker → confirm)
and `CitationBadge.tsx` now render `[filename p.N, topic_path, uploaded YYYY-MM-DD]` when
those fields are present. 225 backend tests (`tests/features/intake.feature`,
`tests/unit/test_{scheduler,topic_path,topic_tree,intake,intake_classifier}.py`, updated
`chat.feature`/`test_pdf_search_tool.py`), all green; frontend unverified by `tsc`/build in
this pass — no Node runtime available in the environment that built it, verify locally per
the README before relying on it.

**Context that reframes the original ask:** the corpus isn't a mix of external
sources with varying trust levels — it's one organization's internal library, already
organized as ten numbered top-level topic folders (`00 Inhaltsverzeichnis` …
`10 Verschiedenes`), each with its own subfolders/categories. So "reliability of sources"
here doesn't mean a trust tier per publisher — it means: which category a document belongs
to, and how current it is. Citations reflect that: topic path + upload/update date, not a
verified/unverified badge.

- **Automatic ingestion — resolves Phase 2b's open "cron scheduling mechanism" decision.**
  An in-process scheduler (APScheduler, or a plain background thread on a sleep loop
  started from FastAPI's lifespan) polls `INGESTION_FOLDER_PATHS` every
  `INGESTION_POLL_MINUTES` (new setting, default e.g. 10) and runs the same
  `sync_folder` path the CLI already calls — no OS-level cron/Task Scheduler entry needed
  on any platform. `app/ingestion/cli.py` stays as-is for anyone who still wants a manual
  or externally-scheduled trigger.
- **Citation provenance:** `documents` gains `source_path` (the topic/category folder path
  relative to the watched root, e.g. `05 Finanzierung & Fundraising/Foerderantraege`) and
  reuses existing `uploaded_at`. Pinecone chunk metadata gains the same two fields so the
  agent has them without a DB round-trip. Citation shape grows to
  `{document_id, filename, page, source_path, uploaded_at}`. System prompt instructs the
  model to quote the date inline, e.g. `[filename p.N, 05 Finanzierung & Fundraising,
  uploaded 2026-03-12]`. `CitationBadge` (frontend) renders the date alongside the
  filename/page it already shows.
- **Smart intake (new upload flow, distinct from the removed Phase 2b bulk upload):** a
  small "Add document" flow back in the frontend. Author picks a PDF in the browser →
  backend parses it (reuses Phase 2's `parser.py`, no rework) → an LLM call is given the
  extracted text plus the *live* folder/subfolder tree (walked from
  `INGESTION_FOLDER_PATHS` at request time, not a static config — stays correct as the
  taxonomy evolves) → returns a suggested folder path with a short rationale → frontend
  shows the suggestion pre-selected in a folder picker (built from that same live tree) →
  **author confirms or picks a different existing folder before anything is saved** — the
  suggestion is never auto-applied. On confirm, the backend writes the file to the chosen
  path on disk (the real OneDrive-synced tree, so it joins the organized library exactly
  like a manually-filed document) and immediately runs it through the ingestion pipeline
  rather than waiting for the next poll.
- **RESOLVED: new subfolders are allowed.** The LLM may propose a new category name under
  an existing top-level topic (never a brand-new top-level topic — the ten stay fixed) when
  nothing existing fits well; the author can also type a custom subfolder name at confirm
  time regardless of what was suggested. The folder picker is therefore a tree select for
  the top-level topic plus existing subfolders, with a "new folder…" text input as an
  always-available alternative to picking one.

**Exit criteria:** a PDF dropped directly into an already-organized folder is searchable
within one poll interval with no manual command; a PDF submitted through the new intake
flow gets a folder suggestion the author can accept or override, and only lands on disk
after that confirmation; a chat answer citing that document quotes its upload date and
topic folder.

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
| 2b | Cron scheduling mechanism (host crontab vs docker-compose service) | **Resolved by Phase 8: in-process scheduler**, no OS-level cron needed |
| 2b | Shared-document delete: admin-only vs any signed-in user | Open — currently any signed-in user |
| 3 (v2) | New SQL schema vs existing production DB | Open |
| 7 | Target concurrent user count | Open |
| 8 | Smart-intake placement: existing folders only vs author/LLM can create a new subfolder | **Resolved: new subfolders allowed**, new top-level topics are not |
| 6 | Compute: ECS Fargate (original plan) vs single EC2 instance | **Resolved (v1): single EC2 instance**, `docker-compose.prod.yml` — revisit ECS if this needs to scale past one box |
| 6 | Region | **Resolved: `eu-central-1` (Frankfurt)**, not `eu-west-1` — lower latency to the German user base |
| 6 | Instance size | **Resolved: `t3.medium`** — identical CPU to `t3.small`, more RAM headroom for a box running Postgres+backend+frontend+Caddy together |
| 6 | Postgres: containerized on the box vs managed RDS | **Resolved (v1): containerized, no backup job** — v2: migrate to managed RDS |
| 6 | IaC: Terraform vs hand-provisioned | **Resolved (v1): hand-provisioned via console**, `infra/aws-runbook.md` — revisit Terraform at a second environment/instance |
| 6 | TLS/domain | **Resolved (v1): `nip.io` stopgap**, real domain swap-in deferred until convenient |
| 6 | Ingestion source in prod: OneDrive access model | **Resolved: `rclone bisync` on the EC2 box** (bidirectional — Phase 8's intake-confirm flow writes into the same watched folder, so a one-way mirror isn't sufficient) — blocked on Microsoft 365 tenant OAuth consent, not yet built |
