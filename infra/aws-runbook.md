# AWS deployment runbook (Phase 6, v1: single EC2 instance)

Console click-through to stand up the one machine this app runs on in prod, plus the
one-time wiring so `git push` to `main` auto-deploys to it (`.github/workflows/ci.yml`'s
`deploy` job). Not Terraform/CDK — `infra/terraform/` stays empty for this pass; see
"Why no IaC yet" at the bottom.

**Companion doc, not a replacement:** [`SECRETS.md`](../SECRETS.md) explains every
`secrets.env` key. This runbook only covers what's specific to standing up the AWS side.

## What you'll end up with

One EC2 instance running `docker compose -f docker-compose.prod.yml` (Postgres, backend,
frontend, Caddy — see that file), reachable over HTTPS via an Elastic IP, deployed to by
pushing to `main`. `rclone`↔OneDrive sync and Postgres backups are **not** part of this
pass — see "Not covered yet" at the end.

## Decisions this runbook assumes

| | Choice | Why |
|---|---|---|
| Region | **`eu-central-1` (Frankfurt)**, not `eu-west-1` | Physically in Germany — meaningfully lower latency to German users than Ireland. If you'd rather stick with `eu-west-1`, every step below is identical, just pick that region in the console instead. |
| Instance type | **`t3.medium`** (2 vCPU, 4GB RAM) | `t3.small` and `t3.medium` have *identical* CPU (2 vCPU, 20% baseline, 24 credits/hr — the `t3` family's CPU allowance doesn't change until `t3.large`). The only difference is RAM: 2GB vs 4GB. Since this one box runs Postgres + backend + frontend + Caddy together (not just the backend, unlike the original Fargate-per-task estimate in `plan.md`), the extra 2GB is worth the small cost step-up (roughly $15/month more) — memory, not CPU, is the tighter constraint here. Resizing later is a stop/change-instance-type/start in the console, a few minutes of downtime, not a rebuild. |
| AMI | Ubuntu Server 24.04 LTS | Long support window, `apt` package availability for everything this needs. |
| Root volume | 30GB gp3 | Covers the OS, Docker images, and Postgres data at this scale. The one thing that could outgrow this is the `rclone`-mirrored OneDrive folder (Phase 6 follow-up) — check your actual corpus size before that step and resize the volume first if it's large. |
| Postgres | Containerized on this same box, **no backup job** | Your call (v1) — a lost instance/volume loses all data. Tracked as a v2 follow-up: migrate to managed RDS. |
| TLS | `nip.io` stopgap (real Let's Encrypt cert, zero domain purchase) | Swappable to a real domain later by changing one value (`PUBLIC_SITE_ADDRESS`) — see Step 9. |
| SSH key | Your existing `~/.ssh/id_ed25519.pub` | Reused for *your own* login only. Two more key pairs get created later in this runbook for the GitHub↔box automation — see Step 7 and Step 10 for why those have to be separate from this one. |

---

## Step 1 — Create the IAM role (no static AWS keys on the box)

This is what lets the box talk to S3 (PDF storage) and Textract (OCR) without a
long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` sitting in a file on disk. AWS
calls this an **instance profile**: a role attached directly to the EC2 instance, handing
out short-lived, auto-rotating credentials that the AWS SDK (`boto3`, which this backend
already uses) picks up automatically — no code change, no key to leak.

1. Console → **IAM** → **Policies** → **Create policy** → **JSON** tab, paste:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
         "Resource": [
           "arn:aws:s3:::YOUR-BUCKET-NAME",
           "arn:aws:s3:::YOUR-BUCKET-NAME/*"
         ]
       },
       {
         "Effect": "Allow",
         "Action": ["textract:DetectDocumentText"],
         "Resource": "*"
       }
     ]
   }
   ```
   Replace `YOUR-BUCKET-NAME` (twice) with the bucket from Step 2 below — if you haven't
   created it yet, come back and fill this in after. Name the policy
   `chatagent-backend-policy`, create it.
2. IAM → **Roles** → **Create role** → trusted entity type **AWS service** → use case
   **EC2** → attach the policy you just made → name it `chatagent-ec2-role` → create.

## Step 2 — Create the S3 bucket

Console → **S3** → **Create bucket** → pick a globally-unique name (e.g.
`chatagent-documents-prod-<something>`) → region **eu-central-1** → leave everything else
default → create. Put this name in `secrets.env` as `S3_BUCKET_NAME` later (Step 8), and
back-fill it into the IAM policy above if you created the role first.

## Step 3 — Create a security group

Console → **EC2** → **Security Groups** → **Create security group** → name
`chatagent-prod-sg` → same VPC you'll launch the instance into (the default VPC is fine
at this scale) → inbound rules:

| Type | Port | Source |
|---|---|---|
| SSH | 22 | **Your IP only** (the console has a "My IP" autofill button) — never `0.0.0.0/0` |
| HTTP | 80 | `0.0.0.0/0` (needed for Let's Encrypt's validation request, even if you only serve HTTPS) |
| HTTPS | 443 | `0.0.0.0/0` |

Notice **8000 (backend), 3000 (frontend), and 5432 (Postgres) are not opened** — only
Caddy is reachable from outside; everything else talks over the compose network
internally (`docker-compose.prod.yml`).

## Step 4 — Launch the instance

EC2 console → **Launch instance**:
- Name: `chatagent-prod`
- AMI: **Ubuntu Server 24.04 LTS**
- Instance type: **t3.medium** (or your own choice — see the decision table above)
- Key pair: select **your existing key pair** (the one matching
  `~/.ssh/id_ed25519.pub`) — if it's not already registered in this AWS account, EC2 →
  Key Pairs → Import key pair → paste the contents of `~/.ssh/id_ed25519.pub`, then it'll
  show up here.
- Network settings: select the security group from Step 3 (`chatagent-prod-sg`), not
  "create new"
- Storage: 30GB gp3 (see decision table)
- Advanced details → **IAM instance profile** → select `chatagent-ec2-role` from Step 1
  — this is the step that's easy to miss and means going back to attach it after the fact
  if skipped (Instances → select instance → Actions → Security → Modify IAM role)

Launch. Wait for **Status check: 2/2 checks passed** before continuing (a minute or two).

## Step 5 — Allocate and associate an Elastic IP

EC2 console → **Elastic IPs** → **Allocate Elastic IP address** → default settings → allocate.
Then select it → **Actions** → **Associate Elastic IP address** → pick the
`chatagent-prod` instance → associate.

Note the IP address (e.g. `18.184.x.x`) — you'll need it in every step below.

## Step 6 — First SSH login, install base software

```bash
ssh ubuntu@<elastic-ip>
```

Once in:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git rclone

# Docker + the compose plugin (Ubuntu's official convenience script)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# Log out and back in (or `newgrp docker`) for the group change to take effect:
exit
```

```bash
ssh ubuntu@<elastic-ip>
docker --version && docker compose version   # confirm both work without sudo
```

## Step 7 — Give the box read access to the private GitHub repo

The box needs its own credential to `git pull` — this is a **separate** key from your
personal one and from the CI key in Step 10 (three keys total by the end of this runbook,
each with a narrow, revocable purpose: yours for admin SSH login, this one for the box
reading from GitHub, Step 10's for GitHub Actions writing to the box).

On the box:

```bash
ssh-keygen -t ed25519 -C "chatagent-box-deploy-key" -f ~/.ssh/github_deploy_key -N ""
cat ~/.ssh/github_deploy_key.pub
```

Copy that output. On GitHub: repo → **Settings → Deploy keys → Add deploy key** → paste
it, leave "Allow write access" **unchecked** (read-only is all a pull needs) → add.

Back on the box, tell git to use this key for GitHub and clone:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/github_deploy_key
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

git clone git@github.com:<your-org-or-user>/ChatAgent.git ~/ChatAgent
cd ~/ChatAgent
```

## Step 8 — Configure secrets

```bash
cp secrets.example.env secrets.env
nano secrets.env    # or your editor of choice
```

Fill in every key per [`SECRETS.md`](../SECRETS.md), with these Phase-6-specific notes:

- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — **leave both blank.** Step 1's instance
  role covers this; setting them here would override the role rather than add to it.
- `S3_BUCKET_NAME` / `AWS_REGION` — the bucket from Step 2, `eu-central-1`.
- `INGESTION_FOLDER_PATHS` — leave blank for now (the `rclone`↔OneDrive follow-up isn't
  built yet — see "Not covered yet"). The app runs fine with ingestion inert.
- `PUBLIC_SITE_ADDRESS` — using the `nip.io` stopgap:
  `https://<elastic-ip-with-dots-replaced-by-dashes>.nip.io`, e.g. `18.184.1.2` becomes
  `https://18-184-1-2.nip.io`. Swap this to a real domain later with no other change
  needed anywhere (see `infra/Caddyfile`).

## Step 9 — First boot

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f
```

First run downloads base images and builds both app images — a few minutes. Watch for
`alembic upgrade head` completing without error, then `Uvicorn running`. Ctrl-C out of
`logs -f` (this doesn't stop the containers, just detaches your terminal).

Verify from your own machine, not the box:

```bash
curl https://<your-nip.io-address>/api/health
```

Should return `{"status":"ok",...}`. Open the same address in a browser — you should see
the login page, TLS padlock included (Caddy requests the Let's Encrypt cert on first
request, so the very first load may take a couple of seconds longer).

## Step 10 — Wire up GitHub Actions auto-deploy

A **third** key pair, distinct from Step 7's (that one lets the box *pull from* GitHub;
this one lets GitHub Actions *SSH into* the box — opposite direction of trust, and
compromising one shouldn't hand over the other).

On your own machine (not the box):

```bash
ssh-keygen -t ed25519 -C "chatagent-ci-deploy" -f /tmp/chatagent_ci_key -N ""
```

Copy the **public** half onto the box, as an additional authorized key (don't replace
your own):

```bash
cat /tmp/chatagent_ci_key.pub | ssh ubuntu@<elastic-ip> 'cat >> ~/.ssh/authorized_keys'
```

Then in the GitHub repo → **Settings → Secrets and variables → Actions → New repository
secret**, add three:

| Secret | Value |
|---|---|
| `DEPLOY_HOST` | the Elastic IP (or the `nip.io`/domain address) |
| `DEPLOY_USER` | `ubuntu` |
| `DEPLOY_SSH_KEY` | contents of `/tmp/chatagent_ci_key` (the **private** half) |

Delete `/tmp/chatagent_ci_key*` from your own machine once it's pasted in — it only needs
to exist in the GitHub secret and on the box's `authorized_keys` from here on.

Push to `main` (or merge a PR into it) and watch the **Actions** tab — the `deploy` job in
`.github/workflows/ci.yml` should run after `lint-and-test`/`build-image` go green, and end
in a passing health check.

---

## Not covered yet

- **`rclone`↔OneDrive-for-Business bidirectional sync** feeding
  `INGESTION_FOLDER_PATHS`. Needs your Microsoft 365 tenant's OAuth consent sorted first
  (can happen in parallel with everything above) — a follow-up to this runbook once
  that's ready, not a blocker for getting the app itself deployed and reachable.
- **Postgres backups.** Explicitly deferred (v1 decision, see the table above) — add a
  nightly `pg_dump`-to-S3 cron whenever that risk stops being acceptable, or jump straight
  to the v2 managed-RDS migration.
- **Real domain.** Buy one whenever convenient, point its A record at the Elastic IP from
  Step 5, change `PUBLIC_SITE_ADDRESS` in `secrets.env`, `docker compose -f
  docker-compose.prod.yml up -d` (no `--build` needed) to pick up the new value. Caddy
  requests a fresh cert automatically.

## Why no IaC yet

`plan.md`/`implementation.md` originally specced this as Terraform/CDK provisioning ECS
Fargate + ALB + RDS. That's still the right answer if this ever needs to scale past one
box — but for a single EC2 instance stood up once, hand-provisioning via the console this
one time is less total effort than writing and debugging Terraform for it, and every
resource here (instance, Elastic IP, security group, IAM role) is small enough to
recreate by hand if needed. Revisit Terraform when there's a second environment
(staging) or a second instance to keep in sync — that's when hand-clicking stops scaling
and IaC starts paying for itself.
