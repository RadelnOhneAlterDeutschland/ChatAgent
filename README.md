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

Written for someone who has never installed developer tools before. It's longer than the
macOS/Linux guide because it explains every click — you don't need any prior coding
experience to follow it.

The folder-sync ingestion model (Phase 2b) was written with this host in mind: OneDrive's
Windows desktop client syncs cloud files into a real local folder, which is exactly what
this app watches for new PDFs.

Don't be put off by how long this page looks — it's long because every click is spelled
out, not because any of it is hard. Go one step at a time, top to bottom, and you'll get
there.

### What is "PowerShell" and how do I open it?

PowerShell is the built-in Windows program where you type text commands instead of
clicking things — that's how the rest of this guide talks to your computer. You don't
install it; it's already on Windows 11.

To open it: click the **Start** button (Windows logo, bottom-left of the screen), type
`PowerShell`, then click **Windows PowerShell** in the results. A blue-ish (or black)
window opens with a blinking cursor — that's it, that's the whole program. Every block
below that starts with `powershell` is something you type into that window, one line at a
time, pressing **Enter** after each line to run it.

Keep this window open as you work through the guide — you'll come back to it repeatedly.
If you ever close it, just reopen it the same way (Start → type `PowerShell` → Enter) and
`cd` back into the project folder (see Step 5) before continuing.

### Where do your PDF documents go?

Quick preview before you start, since this is usually the first question: this app has no
"upload" button anywhere. Instead, you point it at one folder on your computer — most
people use their OneDrive folder — and it watches that folder. Any PDF you drop in there
becomes searchable in the chat once you run one command telling it to look. You'll choose
that exact folder in Step 7 (a setting called `INGESTION_FOLDER_PATHS`) and actually use it
in Step 10. Nothing to do with it yet — just keep the idea in mind as you go.

### Step 1 — Install Docker Desktop

Docker is the program that runs the app's backend and database for you, already packaged
up — you won't need to install Postgres or configure anything yourself.

1. Go to [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
   in your browser and click **Download for Windows**.
2. Open the downloaded file and click through the installer with the default options. When
   it asks about **"Use WSL 2 instead of Hyper-V"**, leave that checked.
3. It will likely ask you to **restart your computer** — do that now.
4. After restarting, open **Docker Desktop** from the Start menu (search for it, same as
   PowerShell above) and leave it running. Wait until the whale icon in the bottom-right
   system tray stops animating and Docker Desktop's window says it's running — this can
   take a minute. **Docker Desktop needs to stay open in the background** every time you
   use this app; if it's closed, the commands below will fail.

**If something goes wrong:**
- *"WSL 2 installation is incomplete"* — Docker will show a link to a Microsoft page with a
  small extra installer ("WSL2 Linux kernel update package"); download and run that, then
  reopen Docker Desktop.
- *Install says virtualization is disabled* — this is a setting in your PC's BIOS/UEFI
  (outside Windows), and the exact steps differ per PC manufacturer. Search
  `"enable virtualization" <your PC brand> BIOS` and follow that guide, then restart.
- *Docker Desktop window never finishes starting* — restart your computer once, reopen
  Docker Desktop, and give it a couple of minutes.

### Step 2 — Install Python

1. Go to [python.org/downloads/windows](https://www.python.org/downloads/windows/) and
   click the yellow **Download Python 3.1x.x** button (anything 3.12 or newer).
2. Run the installer. **On the very first screen**, before clicking anything else, tick the
   checkbox at the bottom that says **"Add python.exe to PATH"**. This step is the one
   people miss most often — if you skip it, Windows won't know where to find `python` later.
3. Click **Install Now** and let it finish.

**If something goes wrong:**
- Later on, if PowerShell says `'python' is not recognized as the name of a cmdlet...`,
  you likely missed the checkbox in step 2. Easiest fix: run the installer again, choose
  **Uninstall**, then reinstall and tick the box this time. (Manual fix, if you'd rather not
  reinstall: see "Fixing PATH manually" at the end of this section.)

### Step 3 — Install Node.js

1. Go to [nodejs.org](https://nodejs.org/) and click the button offering the **LTS**
   version (the "recommended for most users" one, not "Current").
2. Run the installer and click **Next** through every screen, keeping all the defaults.
   This one adds itself to PATH automatically — no checkbox to remember.

### Step 4 — Install Git

1. Go to [git-scm.com/download/win](https://git-scm.com/download/win) — the download
   should start automatically, or click the 64-bit installer link.
2. Run the installer and click **Next** through every screen, keeping all the defaults.

### Step 5 — Check everything installed correctly

Close any PowerShell window you had open and open a **new** one (Start → type
`PowerShell` → Enter) — this matters, because a window opened before installing won't see
the updates. Type each of these lines and press Enter after each one:

```powershell
docker --version
python --version
node --version
git --version
```

Each should print a version number (e.g. `Python 3.12.4`), not an error. If one prints
something like `'docker' is not recognized as the name of a cmdlet, function...`, that
tool's install didn't finish or didn't reach PATH — see "Fixing PATH manually" below, or
just reinstall that one tool and make sure to restart PowerShell afterward.

**Fixing PATH manually** (only needed if a command above still isn't found after
reinstalling): click Start → type `Environment Variables` → open **"Edit the system
environment variables"** → click the **"Environment Variables…"** button → in the top box
labeled **User variables**, click `Path` → **Edit** → **New** → paste in the missing tool's
install folder (for Python, something like
`C:\Users\<you>\AppData\Local\Programs\Python\Python312\` — and, as a second `New` entry,
that same folder's `Scripts\` subfolder) → click **OK** on every open window → close and
reopen PowerShell.

That's the installing done — genuinely the most tedious part. Everything from here is
mostly copying commands and pasting them in.

### Step 6 — Get the project onto your computer

If you already have the project as a folder (e.g. someone sent it to you as a zip), skip
to Step 7 — just make sure you extract the zip first (right-click it → **Extract All**),
don't run it straight from inside the zip.

Otherwise, download it with Git. In PowerShell:

```powershell
cd Documents
git clone <this-repo-url>
cd ChatAgent
```

(`cd` means "go into this folder". The first line moves into your Documents folder, the
second line downloads the project into a new `ChatAgent` folder there, the third line
moves into it. Everything from here on assumes you're inside that `ChatAgent` folder — if
you ever get an error about a file "not found", check you're still in it.)

### Step 7 — Configure the backend

```powershell
copy backend\.env.example backend\.env
notepad backend\.env
```

This copies a template settings file and opens it in Notepad. It's a plain text file —
each line is `SOME_NAME=value`. Fill in the values in this table (the file already has
placeholder lines for each of these; replace the placeholder text after the `=`, leave the
name before the `=` alone):

| Line to fill in | What to put there |
|---|---|
| `JWT_SECRET=` | Any long random text. To generate one: open a **second** PowerShell window (Start → PowerShell → Enter) and run `python -c "import secrets; print(secrets.token_urlsafe(48))"` — copy the printed text in. |
| `OPENAI_API_KEY=` | Your API key from [platform.openai.com](https://platform.openai.com/api-keys) (used for chat + embeddings). |
| `PINECONE_API_KEY=` | Your API key from your Pinecone account. |
| `PINECONE_INDEX_NAME=` | The name of a Pinecone index you've already created (dimension `1536`, metric `cosine`). |
| `S3_BUCKET_NAME=` | Name of an S3 bucket you've created in AWS. |
| `AWS_REGION=` | The AWS region your bucket is in, e.g. `eu-west-1`. |
| `INGESTION_FOLDER_PATHS=` | The folder this app watches for new PDFs — see below. |
| `DATABASE_URL=` | Leave this one exactly as it already is — Docker fills in the real value itself. |

**This `INGESTION_FOLDER_PATHS` line is where you tell the app which folder your documents
live in** — it's the answer to "where do I put my PDFs?" from earlier. Use your OneDrive
folder's real path, e.g. `C:\Users\you\OneDrive\ChatAgent-Inbox` (it doesn't have to be
inside OneDrive — any folder works — but OneDrive is the common case this was built for).
Pick a folder now, or create a new empty one for this purpose (right-click inside File
Explorer → **New → Folder**) if you don't already have one in mind.

To get the exact path without typing it by hand and risking a typo: open File Explorer,
navigate to that folder, right-click it, choose **Copy as path**, then paste into Notepad
and delete the quote marks (`"`) it adds at each end. (Multiple folders: separate them with
a comma — Windows paths don't contain commas, so that's always safe.)

Also needed but *not* in this file: AWS credentials for S3/Textract access, which come from
a separate file at `%USERPROFILE%\.aws\credentials` (created by running `aws configure` if
you've installed the [AWS CLI](https://aws.amazon.com/cli/), or by hand — ask whoever set
up your AWS account if you're not sure).

When done editing, press **Ctrl+S** to save, then close Notepad.

### Step 8 — Start the backend

Back in your first PowerShell window (make sure you're still in the `ChatAgent` folder —
run `cd` commands again if unsure), run:

```powershell
docker compose up --build
```

The first run downloads a few things and can take several minutes — that's normal, let it
run. You'll see a scroll of log text; leave this window open and running (this is now your
"server" — closing the window stops the app). It's ready once the scrolling slows down and
you see lines mentioning `Uvicorn running` or `Application startup complete`.

Check it worked: open your web browser and go to `http://localhost:8000/docs` — you should
see an interactive API page, not an error.

**If something goes wrong:**
- *"Cannot connect to the Docker daemon"* — Docker Desktop isn't running; open it from the
  Start menu and wait for it to fully start, then try the command again.
- *"port is already allocated"* (mentions `5432` or `8000`) — something else on your
  computer is already using that port. Close other apps that might use a database or web
  server, or restart your computer, then try again.
- *Complains about a missing `.env` file* — Step 7 wasn't completed; re-run the `copy`
  command from that step.

### Step 9 — Start the frontend (the web page itself)

Open a **new, second** PowerShell window (leave the first one running Docker) and:

```powershell
cd Documents\ChatAgent\frontend
copy .env.example .env.local
npm install
npm run dev
```

`npm install` downloads the frontend's dependencies — first time only, can take a couple of
minutes. `npm run dev` then starts the web page and keeps running (same as Docker, leave
this window open). Once it prints something like `Local: http://localhost:3000`, open that
address in your browser.

**If something goes wrong:**
- *`'npm' is not recognized...`* — close this PowerShell window, reopen a fresh one, and
  try again (PATH from Node's install may not have reached this window yet).
- *`npm install` fails with permission or network errors* — check your internet connection;
  if it persists, close and reopen PowerShell and retry once.

### Step 10 — Add a PDF and try it out

Here's where the folder from Step 7 comes back in. Open File Explorer, go to the exact
folder you put in `INGESTION_FOLDER_PATHS`, and drag-and-drop (or copy/paste) a PDF file
into it — that's the only "upload" step this app has. Any PDF placed in that one folder is
what becomes searchable in the chat.

Then, back in PowerShell (your first window, or open a third one — still needs to be
inside the `ChatAgent\backend` folder), run:

```powershell
docker compose exec backend python -m app.ingestion.cli
```

This is the command that tells the app "go look in that folder for anything new." You'll
see log lines confirming what it found. It doesn't run by itself in local dev — re-run this
one command every time you add another PDF to the folder.

Now in your browser:

1. Go to `http://localhost:3000` → sign up for an account → log in.
2. Ask a question about the PDF you added.
3. The answer should include a small `[filename p.N]` badge — click it to open that PDF at
   the exact page it came from.

If you got this far and see a real answer with a citation, the whole thing is working end
to end — nicely done.

### Advanced alternative: WSL2 (Ubuntu) instead of native Windows

Skip this unless you already know what Linux/WSL is and specifically want it. Install WSL2
with `wsl --install` in PowerShell (run as Administrator — right-click PowerShell in the
Start menu, choose **Run as administrator**), reboot when asked. In Docker Desktop, go to
**Settings → Resources → WSL Integration** and enable it for the Ubuntu distro that
installs. Then open the Ubuntu terminal and follow the
**[macOS / Linux](#setup-on-macos--linux)** guide below verbatim.

Your OneDrive folder is reachable from WSL at
`/mnt/c/Users/you/OneDrive/ChatAgent-Inbox` (use that instead of a `C:\` path for
`INGESTION_FOLDER_PATHS` in this mode) — expect it to run slower than a plain WSL folder,
since it's crossing between Windows and Linux filesystems on every read.

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
