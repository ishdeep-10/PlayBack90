# PlayBack90 Deployment Handoff

Living document of the actual current production deployment — read this first in any
new session before touching hosting, auth, or the deploy process. Update it whenever
the deployment changes; it should always reflect reality, not the original plan.

Superseded by this doc (kept for history only, do not follow): `hosting-budget-options.md`,
`railway-phase2-deployment-runbook.md`, `deployment-onboarding-analytics-plan.md`. Those
assumed Railway; the actual deployment is AWS Lightsail, decided after hitting Lightsail
Container Service quota limits on a brand-new AWS account (see "Key decisions" below).

## Live site

- **URL**: https://playback90.com
- **Status**: public, open sign-up (no invite allowlist), live scraping disabled
- **Health check**: `GET /health` (always reflects real status). `GET /ready` is stricter
  and intentionally reports `database: false` (no Postgres deployed); its `auth` check may
  also read `false` — see "Known quirks" below. Don't use `/ready` as the uptime check;
  use `/health`.

## Infrastructure inventory

| Item | Value |
|---|---|
| Host | AWS Lightsail VM, instance name `playback90-app` |
| Region | `ap-south-1` (Mumbai) — the only Lightsail region close to India; confirmed via `aws lightsail get-regions` |
| Bundle/size | `micro_3_1` — 1GB RAM, 2 vCPU, ~$7-10/mo. **This is the ceiling**, not a choice: Small and Medium were both blocked by a new-account quota (`InvalidInputException: account can not create an instance using this Lightsail plan size`). Worth retrying a size increase now that the account has usage history. |
| Static IP | `35.154.255.109` (Lightsail static IP `playback90-app-ip`, attached) |
| Swap | 2GB swapfile at `/swapfile` on the instance — added because 1GB RAM is tight running API (pandas/xgboost/matplotlib/Firefox) + web + Caddy together. Monitor `free -h` on the box if things feel slow; swap usage sitting at 700-800MB/2GB is normal, not yet an emergency. |
| SSH key | `~/.lightsail/playback90-key.pem` on the deploying machine (downloaded via `aws lightsail download-default-key-pair`) |
| Firewall | Ports 22 (SSH), 80, 443 open via `aws lightsail put-instance-public-ports` |
| AWS account | New account, using a $100 promotional credit (check exact expiry in AWS Console → Billing → Credits — burn rate at current usage is roughly 3-5 months, but the credit may have its own hard expiry independent of spend) |
| IAM credential | `playback90-deploy` IAM user, local machine has it configured via `aws configure` (`~/.aws/credentials`). Scoped to a custom policy (`PlayBack90LightsailDeploy`, effectively `lightsail:*`) — **deliberately cannot see billing/Cost Explorer**. Extend the policy if a future session needs to query AWS costs directly. |

Container images are **not** stored in any registry — there is no CI/CD. Images are built
locally on a dev machine (must be Docker with `--platform linux/amd64` since the Mac
building them is typically Apple Silicon and the server is x86_64), saved with `docker save`,
`scp`'d to the server, and loaded with `docker load`. See "Deploy runbook" below.

## DNS

- Registrar and DNS: **Cloudflare** (`playback90.com`)
- One `A` record: `@` → `35.154.255.109`
- **Proxy status: DNS only (grey cloud)** — must stay this way. If Cloudflare's proxy is
  turned on, it intercepts port 80/443 before Caddy sees it and breaks Caddy's automatic
  Let's Encrypt HTTP/TLS-ALPN challenge.

## Architecture

```
Internet → Caddy (ports 80/443, auto Let's Encrypt cert for playback90.com)
             ├─ /api/*, /health, /ready → api:8000  (FastAPI)
             └─ everything else          → web:3000  (Next.js standalone)
```

All three (`api`, `web`, `caddy`) run as Docker Compose services on the single Lightsail VM.
Compose file and Caddy config are versioned in this repo at `deploy/docker-compose.yml` and
`deploy/Caddyfile` — the copies on the server (`~ubuntu/docker-compose.yml`,
`~ubuntu/Caddyfile`) should always match these; if you edit one, sync the other.

Env files (`~ubuntu/api.env.production`, `~ubuntu/web.env.production` on the server) are
**not** committed — see `deploy/api.env.production.example` and
`deploy/web.env.production.example` for the real shape with placeholder values.

## What's enabled / disabled right now

| Feature | State | Why |
|---|---|---|
| Auth (Clerk) | **Enabled**, open sign-up | `AUTH_REQUIRED=true`, `AUTH_ALLOWED_EMAILS` empty on purpose. Users still need an account; anyone can create one. Clerk dashboard restricted mode must also be **off** (Protect → Restrictions) — both sides had to change together. |
| Opposition Analysis | **Disabled** | Feature still under development. Gated via `OPPOSITION_ANALYSIS_ENABLED=false` (backend, returns 404) and `NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED=false` (frontend build arg, shows "coming soon"). Flip both to re-enable — no code changes needed. |
| Live WhoScored scraping | **Disabled** | `LIVE_SCRAPE_ENABLED=false` (backend 404s the endpoint) + the "WhoScored URL" tab is disabled in the Import Match UI. **Root cause: Cloudflare actively blocks scrape requests from the AWS Lightsail IP** (confirmed via direct test — got a literal Cloudflare "Attention Required! Sorry, you have been blocked" page). This is not a bug to fix in this codebase; it needs either a residential/mobile proxy or anti-bot-bypass API (ScraperAPI/ZenRows/etc.), or running the scrape step from a non-cloud IP. Wyscout/StatsBomb JSON import still work fine (no WhoScored involved). |
| AI insights (Claude) | **Disabled (by omission)** | `ANTHROPIC_API_KEY` is unset in production. The app already has a deterministic-insights fallback (`ai_analyst.insights_available()` gates it) so this costs nothing and isn't user-visible as broken — "AI deep dive" button just doesn't appear. |
| Postgres / Redis | **Not deployed** | Job stores (live scrape, imports, reports) are in-memory. Fine for current traffic. `/ready` reports these as `false` — expected, not a bug. |

## Deploy runbook

There is no CI/CD. Every deploy is a manual local-build → ship cycle. Run from the repo root
on the dev machine with Docker Desktop running and the AWS CLI configured.

### Rebuild + ship the API (after any `apps/api` change)

```bash
docker build --platform linux/amd64 -f apps/api/Dockerfile -t playback90-api:latest .
docker save playback90-api:latest | gzip > /tmp/api.tar.gz
scp -i ~/.lightsail/playback90-key.pem /tmp/api.tar.gz ubuntu@35.154.255.109:~/
ssh -i ~/.lightsail/playback90-key.pem ubuntu@35.154.255.109 '
  sudo docker load -i ~/api.tar.gz
  sudo docker compose up -d --force-recreate api
'
```

### Rebuild + ship the web app (after any `apps/web` change)

`NEXT_PUBLIC_*` values are baked in at **build time**, not read from the server's env file —
this build-arg list must stay in sync with what the server's live config expects:

```bash
PK=$(grep "^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=" .env | cut -d= -f2-)
docker build --platform linux/amd64 \
  -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL="https://playback90.com/api" \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="${PK}" \
  --build-arg NEXT_PUBLIC_CLERK_SIGN_IN_URL="/sign-in" \
  --build-arg NEXT_PUBLIC_CLERK_SIGN_UP_URL="/sign-up" \
  --build-arg NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED="false" \
  -t playback90-web:latest \
  apps/web
docker save playback90-web:latest | gzip > /tmp/web.tar.gz
scp -i ~/.lightsail/playback90-key.pem /tmp/web.tar.gz ubuntu@35.154.255.109:~/
ssh -i ~/.lightsail/playback90-key.pem ubuntu@35.154.255.109 '
  sudo docker load -i ~/web.tar.gz
  sudo docker compose up -d --force-recreate web
'
```

### Updating the Caddyfile or compose file itself

Edit `deploy/Caddyfile` / `deploy/docker-compose.yml` in the repo, then:

```bash
scp -i ~/.lightsail/playback90-key.pem deploy/Caddyfile deploy/docker-compose.yml ubuntu@35.154.255.109:~/
ssh -i ~/.lightsail/playback90-key.pem ubuntu@35.154.255.109 'sudo docker compose up -d'
```

### Updating an env var

Edit the real file directly on the server (`~ubuntu/api.env.production` or
`~ubuntu/web.env.production`) — there's no local copy with real secrets except your own
`.env` at repo root, which is the source you pull values from. Then
`sudo docker compose up -d --force-recreate <service>` to pick it up. Remember: web's
`NEXT_PUBLIC_*` vars don't work this way — those need a full rebuild (above).

### Verifying after any deploy

```bash
curl -s https://playback90.com/health
curl -s -I https://playback90.com/   # sign-in redirect should point at playback90.com, not 0.0.0.0
```

## Known quirks (not bugs, don't "fix" without cause)

- `/ready` shows `database: false`, and currently `auth: false` too (the auth readiness
  check was written for the invite-only-allowlist design; now that the allowlist is
  intentionally empty, that specific check reads as "not ready" even though auth works
  correctly). Use `/health` for monitoring instead. If this bothers a future session,
  the fix is in `apps/api/app/main.py`'s `_auth_is_ready()`.
- The `redis_configured` field in `/health` always reads `true` — `Settings.redis_url` has
  a non-None default string, so the boolean check is trivially true regardless of whether
  Redis is actually deployed (it isn't). Cosmetic only, nothing depends on it.
- Local dev machines that have ever run `aws configure` for this project will have
  `region = ap-south-1` in `~/.aws/config`, which **breaks local R2 access** (boto3 applies
  it globally, and R2/Cloudflare rejects AWS region names). Local scripts/tests need
  `AWS_DEFAULT_REGION=auto` set explicitly to work around this. This does not affect the
  production server (no AWS CLI config there).

## Key decisions and why (chronological)

1. **Railway → AWS Lightsail**: originally planned around Railway (see the superseded docs),
   switched to AWS because the user had $100 in AWS credit to use. Considered Lightsail
   Containers first (closer to Railway's UX, free HTTPS subdomain) but that hit a hard
   `Lightsail Container Services` quota of 0 on the brand-new account — pivoted to a plain
   Lightsail VM + docker-compose, which had no such block.
2. **Only Micro instance size available**: Small/Medium blocked by account age/quota, not
   a cost choice. Added 2GB swap as a mitigation.
3. **`nip.io` → real domain**: launched on `35.154.255.109.nip.io` (free wildcard DNS trick
   for HTTPS without owning a domain) as a stopgap, migrated to `playback90.com` (bought via
   Cloudflare) once available. The `nip.io` URL no longer resolves to this Caddy config.
4. **R2 file paths removed from all URLs/API contracts**: originally `?filePath=playback90/event_data/...`
   was exposed directly in the browser URL and API request bodies. Refactored so the client
   only ever sends `league`+`season`+`match_id`; the API resolves the actual R2 object path
   server-side via `r2.find_file_path()`. Touched ~10 frontend components and most of
   `apps/api/app/main.py`'s analysis endpoints — see git history around this doc's creation
   for the full diff if debugging something in that area.
5. **Live scraping disabled, not fixed**: discovered live-instance-caused Cloudflare block
   during testing (see table above). Decided to disable rather than pursue a proxy, given
   this is a small private-turned-public beta, not a scraping-dependent product yet.
6. **Ligue 1 / Serie A fixture-linking bug**: root cause was two-fold — (a) missing team-name
   aliases for French clubs' official provider names in `apps/api/app/services/standings.py`'s
   `_TEAM_ALIASES` (fixed), and (b) genuine data gaps in R2 (Serie A's last 2 matchdays and
   one Ligue 1 match had never been scraped) — fixed by running `Data/run_all.py` locally
   (must run off a non-AWS IP, same Cloudflare-block reason as live scraping).
