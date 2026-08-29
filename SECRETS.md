# Secrets & configuration reference

Every secret/config key the backend reads, what it's for, whether it's required, and where
to get or generate a real value. The sourceable template listing just these keys (no
values) is [`secrets.example.env`](secrets.example.env) at the repo root — copy it to
`secrets.env`, fill in values using this page, and `docker compose up` picks it up
automatically (`docker-compose.yml`'s `env_file:` points at `secrets.env`).

`secrets.env` is gitignored — it holds real credentials and must never be committed.

## App

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `ENVIRONMENT` | No (default `local`) | Distinguishes local/dev from prod behavior. | Leave as `local` for local dev. |
| `DATABASE_URL` | No, when using Docker | Connection string for the app's Postgres (users, chat history, document metadata). | `docker-compose.yml` overrides this to point at its own `postgres` service — leave blank/unset for the Docker flow. Only needed if you're running the backend natively against your own Postgres instance. |

## Auth

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `JWT_SECRET` | **Yes** | Signs login tokens (HS256). Anyone with this value could forge a valid login. | Generate one yourself — don't reuse a value from anywhere else: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` (or `python` instead of `python3` on Windows). |
| `JWT_EXPIRY_MINUTES` | No (default `30`) | How long a login token stays valid before you have to log in again. | Pick a number. No refresh-token flow exists yet, so this is the whole session length. |

## OpenAI

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** | Powers chat answers and document embeddings. | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) — create a key on an account with billing enabled. |
| `OPENAI_CHAT_MODEL` | No (default `gpt-4o-mini`) | Which OpenAI chat model answers questions. | Any valid OpenAI chat-completions model name, if you want to override the default. |

## Pinecone

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `PINECONE_API_KEY` | **Yes** | Authenticates to your Pinecone project — this is where document chunks are stored as vectors for search. | [app.pinecone.io](https://app.pinecone.io/) → API Keys, on your account/project. |
| `PINECONE_INDEX_NAME` | **Yes** | Which Pinecone index to read/write. | Create an index first in the Pinecone console — **dimension `1536`, metric `cosine`** (must match `text-embedding-3-small`'s output) — then put its name here. |

## AWS

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `AWS_REGION` | **Yes** | Which AWS region your S3 bucket (and Textract, if used) lives in. | e.g. `eu-west-1`, `us-east-1` — wherever you created the bucket below. |
| `S3_BUCKET_NAME` | **Yes** | Where uploaded PDF bytes are stored. | Create a bucket in the [S3 console](https://console.aws.amazon.com/s3/) and put its name here. |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | No, if you'd rather configure `~/.aws/credentials` (`%USERPROFILE%\.aws\credentials` on Windows) instead | Credentials boto3 uses to talk to S3, and to Textract for OCR on scanned PDF pages. | [IAM console](https://console.aws.amazon.com/iam/) → Users → your user → Security credentials → Create access key. Needs S3 read/write on the bucket above and (if you'll test OCR) `textract:DetectDocumentText`. If you set these two here, they take priority over anything in `~/.aws/credentials` — simplest option for local dev, one less file to manage. **Prod (Phase 6): leave both blank** — the EC2 instance has an IAM role attached instead (`infra/aws-runbook.md`), which boto3 picks up automatically with no long-lived key sitting on the box. Filling these in on the box would override the role, not add to it. |

## PDF ingestion (Phase 2b: folder-sync)

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `INGESTION_FOLDER_PATHS` | No, but nothing gets ingested without it | The folder(s) this app watches for PDFs — drop a file in here, then run the ingestion CLI, and it becomes searchable. Comma-separated for more than one. | Any folder on your machine. The common case is a OneDrive-desktop-synced folder, e.g. `C:\Users\you\OneDrive\ChatAgent-Inbox` on Windows or `/home/you/chatagent-inbox` on macOS/Linux — but any folder works. |
| `SYSTEM_OWNER_EMAIL` | No (default `shared-library@system.local`) | Every folder-ingested document is owned by one shared system account internally (not a real login) — this sets its email. | Leave the default unless you specifically need to change it. |

## Prod only (Phase 6)

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `PUBLIC_SITE_ADDRESS` | No — unused in local dev, required for the Caddy service in `docker-compose.prod.yml` | The address Caddy serves on and gets a TLS cert for. See `infra/Caddyfile` and `infra/aws-runbook.md`. | e.g. `https://<elastic-ip-with-dashes>.nip.io` as a free stopgap, `https://your-domain` once you have one, or `:80` for plain HTTP with no TLS (beta-only, only if access is already restricted to known IPs/VPN). |

## v2 (deferred, plan.md Phase 3)

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `BUSINESS_DATABASE_URL` | No — not used yet | Read-only connection for the not-yet-built SQL query tool. | N/A until Phase 3 lands. Leave unset. |

## Frontend

The frontend has exactly one config value, and it isn't a secret (it's a public URL meant
to end up in the browser bundle, hence the `NEXT_PUBLIC_` prefix — Next.js only inlines
vars with that prefix into client code). It lives in its own file,
[`frontend/.env.example`](frontend/.env.example), copied to `frontend/.env.local`:

| Key | Required | What it's for | Where to get it |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | No (default `http://localhost:8000`) | Where the frontend sends its API requests. | The default is correct for local dev against the Docker-Compose backend — only change it if your backend runs somewhere else. |
