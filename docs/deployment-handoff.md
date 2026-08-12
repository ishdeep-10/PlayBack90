# PlayBack90 Deployment Handoff

Living document of the actual current production deployment — read this first in any
new session before touching hosting, auth, or the deploy process. Update it whenever
the deployment changes; it should always reflect reality, not the original plan.

Superseded by this doc (kept for history only, do not follow): `hosting-budget-options.md`,
`railway-phase2-deployment-runbook.md`, `deployment-onboarding-analytics-plan.md`. Those
assumed Railway; the actual deployment is AWS Lightsail, decided after hitting Lightsail
Container Service quota limits on a brand-new AWS account (see "Key decisions" below).

## Production hardening checklist

Started 2026-08-07 after a review of what's missing for a small public app. Update the
checkboxes as items land; each item should get a short note on what was actually done
(not just checked off blind) since a future session needs to know the real state, not
just that a box is ticked.

- [x] **1. Error monitoring (Sentry)** — Code wired 2026-08-07: `@sentry/nextjs` added
      (`instrumentation.ts`, `instrumentation-client.ts`, `sentry.server.config.ts`,
      `sentry.edge.config.ts`, `app/global-error.tsx`, `next.config.mjs`), and `sentry-sdk`
      added to `apps/api` (`main.py`, gated + wrapped in try/except so a malformed DSN can
      never crash the app on boot — this actually caught a real bug: a stale
      `SENTRY_DSN=replace_me` placeholder in local `.env` crashed every test until fixed).
      Same no-op-when-unset gating pattern as Clerk/PostHog throughout.
      **Still needed to actually activate**: a real Sentry DSN (backend `SENTRY_DSN`,
      frontend `NEXT_PUBLIC_SENTRY_DSN` + runtime `SENTRY_DSN` in `web.env.production`) —
      not deployed to production yet, waiting on Sentry account creation.
      Note: `@sentry/nextjs` adds real bundle weight even when disabled (First Load JS on
      `/analysis/[matchId]` went 299kB → 379kB, middleware 90.7kB → 172kB) — acceptable
      tradeoff for error visibility, but worth knowing.
      Source-map upload (readable stack traces) needs `SENTRY_ORG`/`SENTRY_PROJECT`/
      `SENTRY_AUTH_TOKEN` build args — optional, deferred, no-op without them.
      Note: Docker's build linter flags `SENTRY_AUTH_TOKEN` as "secrets used in ARG/ENV"
      (build args land in image layer history, readable via `docker history`) — harmless
      today since it's unset, but if source-map upload is ever turned on, switch to a
      BuildKit `--secret` mount instead of `--build-arg` for that one value specifically.
- [x] **2. Uptime monitoring** — UptimeRobot configured 2026-08-07, monitoring
      `https://playback90.com/health` (not `/ready` — see "Known quirks") with email alerts.
      No code changes needed, purely external.
- [x] **3. Exposed origin IP / no Cloudflare proxy** — Fixed 2026-08-07. DNS record is now
      **Proxied** (orange cloud) with Cloudflare SSL/TLS mode **Full (strict)**. Caddy no
      longer does automatic Let's Encrypt for this domain — it serves a static Cloudflare
      Origin CA certificate instead (15-year validity, issued via Cloudflare Dashboard →
      SSL/TLS → Origin Server; only trusted by Cloudflare's proxy, which is fine since all
      public traffic now routes through it). Cert + key live in `certs/` at repo root
      (gitignored — **never commit these**, see `.gitignore`). Caddyfile's `tls` directive
      now points at them explicitly instead of relying on `auto_https`.
      Verified: `server: cloudflare` + `cf-ray` headers present, browsers see a
      publicly-trusted Cloudflare edge cert, site functions identically.
      Rollback path if ever needed: flip DNS back to "DNS only" AND restore
      `~/Caddyfile.letsencrypt.bak` on the server (Caddy's previous Let's Encrypt cert is
      still cached in the `caddy_data` volume, so recovery doesn't need fresh ACME issuance).
      **Residual gap, not done**: the origin IP itself (`35.154.255.109`) still accepts
      direct connections if someone already knows it and ignores the cert warning —
      Cloudflare's proxy protects the *domain*, not the IP. A future hardening step would
      be restricting the Lightsail firewall to only Cloudflare's published IP ranges.
- [x] **4. CI running the test suite** — `.github/workflows/ci.yml` added 2026-08-07: two
      jobs, `api-tests` (pytest, no secrets needed — verified the full suite passes with
      zero `.env` present, fully self-contained/mocked) and `web-checks` (`tsc --noEmit` +
      `next build` with a placeholder API URL). Deliberately excludes `next lint` — it was
      never actually configured in this project (no ESLint config exists; running it
      prompts an interactive first-time setup wizard that would hang in CI). Adding real
      ESLint config would be a separate, bigger task if wanted later.
      **Not yet verified via an actual GitHub Actions run** — all commands pass locally,
      but the workflow can't execute until it's pushed to GitHub. This machine's git is
      authenticated as `ishdeep-score`, which does not have push access to
      `ishdeep-10/PlayBack90` (`403` on push, confirmed 2026-08-07) — needs either that
      account added as a collaborator, or pushing from a session authenticated as
      `ishdeep-10`. Confirm the first real CI run went green once that's resolved.
- [ ] **5. Backup of `Data/playback90.db`** — 7.6GB SQLite file, sole source of truth for
      everything ever scraped, lives only on the dev laptop. **Deliberately skipped
      2026-08-07** — user is about to delete some of its data, so backing up the current
      state first would be wasted effort. Revisit once the data cleanup is done.
- [x] **6. Lightsail instance snapshots** — Done 2026-08-07 via CLI (our
      `playback90-deploy` IAM user's `lightsail:*` policy already covers this, no console
      access needed): enabled the `AutoSnapshot` add-on (daily, 18:00), plus took one
      manual baseline snapshot (`playback90-app-baseline-2026-08-07`) immediately since the
      automatic one only starts from the next scheduled window. Lightsail auto-snapshots
      retain a rolling window (last few days) automatically. Small added cost (~$0.05/GB of
      disk snapshotted per month, so a few dollars/month on the 40GB disk) — draws from the
      AWS credit like everything else. To restore: Lightsail console or
      `aws lightsail create-instance-from-snapshot`.
- [x] **7. API rate limiting / abuse protection** — Done 2026-08-07:
      `apps/api/app/services/rate_limit.py`, a small in-memory sliding-window limiter keyed
      by authenticated user id (falls back to client IP if unauthenticated) — in-memory is
      fine since this is a single-instance deployment; move to Redis if it's ever scaled to
      multiple replicas. Applied via `enforce_rate_limit(http_request, bucket=..., limit=...,
      window_seconds=60)` at the top of each expensive endpoint in `main.py`:
      - PNG asset generation (`/analysis/{id}/assets/{id}.png`): 60/min (generous — a single
        tab view can trigger several chart requests)
      - PDF report generation (`create_report_job` + `/report.pdf`): 5/min
      - Imports (Wyscout/StatsBomb/StatsBomb sample): 10/min
      - Live scrape job creation: now actually enforces `LIVE_SCRAPE_RATE_LIMIT_PER_MINUTE`,
        which was declared in `config.py` but never wired to anything before this
      Returns `429` past the limit. Verified with a real request-flood test (10 allowed,
      11th+ correctly `429`).
- [x] **8. Confirm AWS Budget alert actually exists** — Checked 2026-08-07: it did not
      (`describe-budgets` returned empty). Created `playback90-monthly`, $30/month, email
      alerts to ishdeepsinghchadha@gmail.com at 80% actual spend and 100% forecasted spend.
      Needed widening the `playback90-deploy` IAM policy first (added `budgets:*` +
      `ce:GetCostAndUsage`/`ce:GetCostForecast` — the credential could not grant itself
      this, that required a manual console step, which is correct IAM behavior not a bug).
      Note: Cost Explorer itself (`aws ce get-cost-and-usage`) still returns
      `DataUnavailableException` — likely needs to be manually enabled in the console and
      takes ~24h to start ingesting; the budget alert itself doesn't depend on this and is
      confirmed active regardless.
- [x] **9. Privacy policy** — Done 2026-08-07: `apps/web/app/privacy/page.tsx`, plain-
      language disclosure (not a lawyer-drafted binding ToS — this is a solo hobby project,
      not a company; get real legal review before that's needed) covering what's actually
      collected (Clerk email, PostHog usage events, Sentry error reports, uploaded files
      processed in-memory only) and which third parties are involved. Linked from a new
      footer on every page. Added to `middleware.ts`'s public-route allowlist so it's
      viewable without signing in (standard practice, and the honest thing to do — you
      shouldn't need an account to read the privacy policy).

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
| IAM credential | `playback90-deploy` IAM user, local machine has it configured via `aws configure` (`~/.aws/credentials`). Custom policy `PlayBack90LightsailDeploy`: `lightsail:*` plus (added 2026-08-07) `budgets:*`/`ce:GetCostAndUsage`/`ce:GetCostForecast` for the budget alert. Still no IAM/EC2/other-service access — narrowly scoped by design. |

Container images are **not** stored in any registry — there is no CI/CD. Images are built
locally on a dev machine (must be Docker with `--platform linux/amd64` since the Mac
building them is typically Apple Silicon and the server is x86_64), saved with `docker save`,
`scp`'d to the server, and loaded with `docker load`. See "Deploy runbook" below.

## DNS

- Registrar and DNS: **Cloudflare** (`playback90.com`)
- One `A` record: `@` → `35.154.255.109`
- **Proxy status: Proxied (orange cloud)**, as of 2026-08-07 — see checklist item 3 above.
  SSL/TLS mode is **Full (strict)**. Caddy no longer does automatic Let's Encrypt for this
  domain; it serves a static Cloudflare Origin CA cert from `certs/` instead (gitignored).
  Do not flip this back to "DNS only" without also reverting the Caddy config — see the
  rollback note in checklist item 3.

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
| Auth (Clerk) | **Enabled**, open sign-up, **Production instance** (migrated 2026-08-12) | `AUTH_REQUIRED=true`, `AUTH_ALLOWED_EMAILS` empty on purpose. Users still need an account; anyone can create one. Clerk dashboard restricted mode must also be **off** (Protect → Restrictions). Moved off the Development instance (`meet-fish-22.clerk.accounts.dev`, 100-user hard cap) to Production on custom domain `clerk.playback90.com`. DNS: 5 CNAME records in Cloudflare (`clerk`, `accounts`, `clkmail`, `clk._domainkey`, `clk2._domainkey`) pointing at `*.clerk.services`, all set **DNS only** (grey cloud) — Clerk terminates TLS on those subdomains itself, same reasoning as our own origin cert. `CLERK_JWKS_URL`/`CLERK_ISSUER` on the API now point at `https://clerk.playback90.com`; web build now uses the `pk_live_...`/`sk_live_...` keys (previously `_PROD`-suffixed in `.env`, now the primary values). All 100 existing Development-instance users were carried over via CSV export (Dashboard → Settings → Export all users, includes bcrypt `password_digest`) + Clerk's `CreateUser` Backend API (`scripts/migrate_clerk_users.py`, one-off, not part of the deploy runbook) — they keep their existing password, no re-registration needed. |
| Opposition Analysis | **Disabled** | Feature still under development. Gated via `OPPOSITION_ANALYSIS_ENABLED=false` (backend, returns 404) and `NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED=false` (frontend build arg, shows "coming soon"). Flip both to re-enable — no code changes needed. |
| Live WhoScored scraping (server-side, via `/live-scrape-jobs`) | **Still disabled** | `LIVE_SCRAPE_ENABLED=false` (backend 404s the endpoint), unrelated to the row below. **Root cause: Cloudflare actively blocks scrape requests from the AWS Lightsail IP** (confirmed via direct test — got a literal Cloudflare "Attention Required! Sorry, you have been blocked" page). Not a bug to fix in this codebase; needs a residential/mobile proxy, anti-bot-bypass API, or running the scrape step from a non-cloud IP. |
| WhoScored **HTML** import (`/import-jobs/whoscored-html`) | **Enabled**, added 2026-08-09 | Sidesteps the Cloudflare block entirely: the user saves the WhoScored Match Centre page from their own browser (real residential IP, never blocked) and uploads the `.html` file; the server parses the same embedded `matchCentreData` JSON payload the old live-scraper extracted, via `apps/api/app/services/providers/whoscored_html.py`. Reuses the existing `Data/main.py`/`Data/data_utils.py` normalization pipeline for consistent output. 20MB upload cap, rate-limited under the shared `import` bucket (10/min), detects and rejects Cloudflare block-page HTML with a helpful error. This is now the primary "WhoScored" tab in the Import Match UI — Wyscout/StatsBomb JSON import work the same as before. |
| Upcoming-season scraping + R2 upload pipeline | **Local only, not deployed** | The recurring scrape/enrichment/upload workflow for upcoming-season data still runs from the dev laptop/local environment, not from AWS. This is intentional for now because cloud-hosted WhoScored scraping is blocked from the Lightsail IP, and the full `Data` database remains local. Hosted production only reads already-uploaded R2 parquet/metadata files; it does not scrape, enrich, or upload new season data itself. |
| AI insights (Claude) | **Disabled (by omission)** | `ANTHROPIC_API_KEY` is unset in production. The app already has a deterministic-insights fallback (`ai_analyst.insights_available()` gates it) so this costs nothing and isn't user-visible as broken — "AI deep dive" button just doesn't appear. |
| Postgres / Redis | **Not deployed** | Job stores (live scrape, imports, reports) are in-memory. Fine for current traffic. `/ready` reports these as `false` — expected, not a bug. |
| Product analytics (PostHog) | **Enabled once `NEXT_PUBLIC_POSTHOG_KEY` is set** | Wired via `lib/posthog.ts` + `components/PostHogProvider.tsx` (autocapture + pageviews on every route change, including analysis tab switches since those are URL changes) and `components/PostHogIdentify.tsx` (identifies by Clerk user id once signed in, `posthog.reset()` on sign-out). Custom events beyond autocapture: `share_export_opened`/`share_export_downloaded` (`DownloadPngButton.tsx`), `import_started`/`import_completed`/`import_failed` with a `provider` property (`LiveScrapeForm.tsx`), `ai_insight_requested` (`AiInsightCard.tsx`). Entirely a no-op with zero runtime cost if the key is unset — same gating pattern as Clerk. Needs `NEXT_PUBLIC_POSTHOG_KEY`/`NEXT_PUBLIC_POSTHOG_HOST` as **build args** (baked in at build time, not read from the server's env file) — see the deploy runbook below. |

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
  sudo docker image prune -a -f --filter "until=1h"
'
```

### Rebuild + ship the web app (after any `apps/web` change)

`NEXT_PUBLIC_*` values are baked in at **build time**, not read from the server's env file —
this build-arg list must stay in sync with what the server's live config expects:

```bash
PK=$(grep "^NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=" .env | cut -d= -f2-)
PH=$(grep "^NEXT_PUBLIC_POSTHOG_KEY=" .env | cut -d= -f2-)
SENTRY=$(grep "^NEXT_PUBLIC_SENTRY_DSN=" .env | cut -d= -f2-)
docker build --platform linux/amd64 \
  -f apps/web/Dockerfile \
  --build-arg NEXT_PUBLIC_API_BASE_URL="https://playback90.com/api" \
  --build-arg NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY="${PK}" \
  --build-arg NEXT_PUBLIC_CLERK_SIGN_IN_URL="/sign-in" \
  --build-arg NEXT_PUBLIC_CLERK_SIGN_UP_URL="/sign-up" \
  --build-arg NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED="false" \
  --build-arg NEXT_PUBLIC_POSTHOG_KEY="${PH}" \
  --build-arg NEXT_PUBLIC_POSTHOG_HOST="https://us.i.posthog.com" \
  --build-arg NEXT_PUBLIC_SENTRY_DSN="${SENTRY}" \
  -t playback90-web:latest \
  apps/web
docker save playback90-web:latest | gzip > /tmp/web.tar.gz
scp -i ~/.lightsail/playback90-key.pem /tmp/web.tar.gz ubuntu@35.154.255.109:~/
ssh -i ~/.lightsail/playback90-key.pem ubuntu@35.154.255.109 '
  sudo docker load -i ~/web.tar.gz
  sudo docker compose up -d --force-recreate web
  sudo docker image prune -a -f --filter "until=1h"
'
```

**Always run the prune step after `--force-recreate`.** The Micro instance's 40GB disk fills up
fast — each `docker load` leaves the previous image's layers behind as dangling/untagged once
the new one takes over the `latest` tag, and repeated same-day redeploys accumulate quickly. Hit
this for real on 2026-08-09: disk filled to 98% (37GB used) after ~10 redeploys in one session,
which made a `docker load` fail mid-extraction with "no space left on device" — the site itself
stayed up throughout (the running container keeps working even if its image tag becomes
orphaned), but the new deploy silently didn't take effect until the disk was cleared. Recovery
was `sudo docker image prune -a -f --filter "until=1h"` (reclaimed 16.65GB) followed by re-running
`docker compose up -d --force-recreate` for the affected service.

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
7. **PostHog for product analytics**: picked over Umami/Plausible because the ask was
   specifically "which features are people using," not just pageview counts — PostHog's
   autocapture + pageview tracking covers that out of the box (every route change, including
   analysis tab switches, is a pageview), with a handful of custom events layered on for the
   async actions autocapture can't see (imports, exports, AI insights). Free tier, no CC.
8. **Cloudflare Origin CA over DNS-01 Caddy plugin**: once the DNS record went Proxied,
   Caddy's automatic Let's Encrypt (TLS-ALPN-01/HTTP-01) stopped working since Cloudflare
   terminates TLS at the edge before challenges reach the origin. Chose a static Cloudflare
   Origin CA certificate over rebuilding Caddy with a DNS-01 Cloudflare plugin — simpler
   (no custom image, no API token in Caddy config, no xcaddy build step) and purpose-built
   for exactly this always-behind-Cloudflare scenario. 15-year cert, so no renewal
   automation needed for a long time.
9. **Clerk Development → Production migration**: forced by a real user hitting the
   Development instance's hard 100-user cap. Considered removing Clerk auth entirely
   (app has no per-user data, so it was a live option) but the login wall itself was a
   deliberate earlier choice and Production has no user cap on the free tier, so migrating
   was the smaller change. Existing users were **not** lost — Clerk's Backend API supports
   creating users with a pre-existing bcrypt `password_digest`, so all 100 accounts were
   carried over intact (`scripts/migrate_clerk_users.py`) rather than forcing a mass
   re-registration.
