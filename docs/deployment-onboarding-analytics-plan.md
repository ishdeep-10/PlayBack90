# PlayBack90 Deployment, Onboarding, Analytics, and Data Pipeline Plan

## Objective

Prepare PlayBack90 for a private testing deployment where only invited users can access the app, while giving us enough product analytics, feedback capture, observability, and pipeline automation to learn from the beta safely.

This plan covers:

- where to deploy the Next.js web app and FastAPI API
- how invited users sign in
- how we protect the API and user-uploaded/imported data
- how we track feature usage and collect feedback
- where season data pipelines and live scraping should run
- expected beta costs and later upgrade paths

## Current Architecture

The repo currently has three surfaces:

- `apps/web`: Next.js 15 frontend.
- `apps/api`: FastAPI backend serving match analysis, images, imports, live scrape jobs, standings, reports, and AI insights.
- `Data`: batch scraping and enrichment scripts that scrape WhoScored/Opta data, write to a local SQLite database, enrich models, generate season stats, and upload parquet files to Cloudflare R2.

Current data flow:

1. R2 stores match parquet data under `event_data/{league}/{season}/...`.
2. The FastAPI API reads R2 and builds analysis views.
3. User uploads for Wyscout/StatsBomb are normalized in memory and retained temporarily.
4. Live WhoScored imports run in the API process using an in-memory background thread.
5. Data pipelines currently run as local/container scripts and write to SQLite plus R2.

Main production gaps:

- No authentication or API authorization yet.
- In-memory job state will be lost on restart.
- Live scraping is coupled to the API web process.
- Pipeline state is local SQLite, not durable cloud storage.
- No user analytics, feedback, error monitoring, or uptime alerting.
- A Discord webhook URL exists in source history/current code and must be revoked before deployment.

## Recommended Beta Stack

Use a single Railway project for the private beta, keep Cloudflare R2 for analytical storage, and add managed auth/analytics/observability tools.

| Area | Recommendation | Why |
|---|---|---|
| Web hosting | Railway service for `apps/web` | Keeps frontend, API, workers, DB, and Redis in one project for beta operations. |
| API hosting | Railway service for `apps/api` | Existing Dockerfile is close to deployable and Python/matplotlib workloads fit container hosting. |
| Auth | Clerk invite-only/restricted mode | Fastest route to real app login, user management, invitation emails, and future account features. |
| API protection | Verify Clerk JWT in FastAPI and enforce an allowed-email policy server-side | Prevents direct API access bypassing the frontend. |
| Database | Railway Postgres | Durable job state, users/allowlist mirror, scrape runs, pipeline metadata, feedback metadata. |
| Queue/cache | Railway Redis | Job queue, transient import state, rate limits, cache invalidation, scrape/report worker coordination. |
| Object storage | Cloudflare R2 | Already used by the app; low-cost object storage with no egress fees. |
| Product analytics | PostHog Cloud | Tracks feature usage, funnels, cohorts, session replay sampling, and in-app surveys. |
| Feedback | PostHog surveys plus a lightweight feedback endpoint | In-app targeted prompts plus structured feedback tied to logged-in users and current match/view. |
| Error monitoring | Sentry | Frontend/API errors, deploy releases, worker failures, useful alerts during beta. |
| Uptime | Better Stack or Railway health checks first | Start with simple health checks; upgrade if external uptime history becomes important. |
| Pipeline scheduler | Railway cron services | Runs season ingestion jobs on schedule using existing Docker patterns. |
| Live scraping | Separate Railway worker service | Keeps Selenium/browser work out of the API request lifecycle. |

Why Railway-first: PlayBack90 is not just a static Next app. It has a Python API, matplotlib image generation, Selenium scraping, batch jobs, Redis-shaped queues, and a database-shaped need for durable state. A single Railway project is easier to reason about during beta than splitting Vercel + separate Python host + separate scheduler + separate Redis/Postgres.

## Viable Alternatives

### Option A - Railway-first beta

Best for the next 1-3 months.

- Deploy `apps/web`, `apps/api`, `worker`, `pipeline-cron`, Postgres, and Redis together.
- Lowest operational complexity.
- Good fit for Docker and Selenium.
- Easy to inspect logs in one place.

Tradeoff: Next.js edge/CDN performance will not be as polished as Vercel, but that is not the bottleneck for a private analytics beta.

### Option B - Vercel frontend + Railway backend/workers

Best once the product is more public.

- Deploy Next.js to Vercel.
- Keep API, workers, Postgres, Redis, and cron jobs on Railway.
- Better frontend deployment experience, previews, and CDN.

Tradeoff: more cross-origin auth, CORS, environment, and deploy coordination.

### Option C - AWS/GCP/Fly/Render production stack

Best later, when scale, compliance, or custom infrastructure becomes important.

- More control.
- More setup and operational burden.
- Not needed for the first closed beta.

## Security and Privacy Principles

1. The app must not be publicly usable before authentication is active.
2. API endpoints must enforce auth, not just frontend pages.
3. User-uploaded Wyscout/StatsBomb files should remain ephemeral unless the user explicitly opts into saving later.
4. Uploaded/imported user data should not be sent to analytics tools.
5. Session replay must mask analysis text and user-upload surfaces by default.
6. Secrets must only live in provider environment variables.
7. The committed Discord webhook must be revoked and moved to `DISCORD_WEBHOOK_URL`.
8. Live scraping should have per-user and global rate limits.
9. Background jobs should have durable status, expiry, and cleanup.
10. Logs must not include uploaded JSON payloads, full URLs with sensitive tokens, or raw event data.

## Authentication and Onboarding Plan

Recommended flow for private beta:

1. Create a Clerk app.
2. Enable restricted mode or invitation-only sign-up.
3. Invite specific tester emails from Clerk.
4. Add Clerk to Next.js:
   - public routes: sign-in, sign-up/invitation acceptance, health/static assets
   - protected routes: landing app, matches, analysis, import pages, reports
5. Add FastAPI JWT verification:
   - verify token signature, issuer, audience, expiry
   - extract `sub`, email, name
   - reject if email is not allowed or user is disabled
6. Store minimal user profile in Postgres:
   - `auth_user_id`
   - `email`
   - `name`
   - `role`
   - `status`
   - `created_at`
   - `last_seen_at`
7. Add admin-only beta allowlist management later if managing users in Clerk dashboard becomes painful.

Initial roles:

- `admin`: full access, can inspect operational pages.
- `tester`: normal beta user.
- `disabled`: blocked at API level even if auth provider still has an account.

## Product Analytics Plan

Use PostHog for product analytics because it covers event analytics, funnels, session replay, feature flags, and surveys in one tool.

Track only product behavior, not raw football event data.

Core events:

- `signed_in`
- `league_selected`
- `round_selected`
- `fixture_selected`
- `analysis_opened`
- `analysis_tab_viewed`
- `analysis_filter_changed`
- `share_export_opened`
- `share_export_downloaded`
- `live_scrape_started`
- `live_scrape_completed`
- `live_scrape_failed`
- `wyscout_import_started`
- `statsbomb_import_started`
- `import_completed`
- `import_failed`
- `report_generation_started`
- `feedback_submitted`

Recommended event properties:

- `user_id`: Clerk user id
- `email_domain`: domain only, not full email in public dashboards
- `league`
- `season`
- `match_id`
- `source`: `r2`, `live`, `wyscout`, `statsbomb`, `statsbomb_sample`
- `view_id`
- `team`
- `duration_ms`
- `status`

Avoid capturing:

- uploaded JSON payloads
- full WhoScored/Wyscout/StatsBomb URLs if they may include private identifiers
- player-level raw event arrays
- screenshots of user-uploaded data in session replay

Useful beta dashboards:

- activation: invited -> signed in -> first match analysis
- feature usage: most-used tabs and filters
- import adoption: live scrape vs Wyscout vs StatsBomb
- friction: failed imports, failed scrapes, abandoned reports
- retention: users active on 2+ days
- performance: analysis view load times by tab and source

## Feedback Plan

Use two feedback channels:

1. Passive in-app feedback button:
   - always visible in the app shell after login
   - captures current route, league, match, view, source, browser, and optional message/rating
   - stores feedback in Postgres
   - sends a notification to Slack/Discord/email via webhook

2. Targeted PostHog surveys:
   - after a user opens 3 analyses: "What was most useful?"
   - after an import completes: "Did the imported report match expectations?"
   - after an import fails: "Can we contact you for the file/source issue?"
   - weekly beta NPS/CSAT prompt for active testers

Feedback database table:

```sql
feedback (
  id uuid primary key,
  user_id text not null,
  email text not null,
  route text not null,
  match_id text,
  league text,
  season text,
  view_id text,
  source text,
  rating integer,
  message text not null,
  browser text,
  created_at timestamptz not null default now()
)
```

## Durable Jobs and Data Model

Move in-memory jobs into Postgres/Redis.

Tables:

```sql
jobs (
  id uuid primary key,
  user_id text,
  kind text not null,
  status text not null,
  message text,
  error text,
  input_ref text,
  result_ref text,
  match_id text,
  provider text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  expires_at timestamptz
)
```

```sql
pipeline_runs (
  id uuid primary key,
  pipeline text not null,
  league text,
  season text,
  status text not null,
  started_at timestamptz not null,
  finished_at timestamptz,
  matches_discovered integer default 0,
  matches_scraped integer default 0,
  matches_uploaded integer default 0,
  error text,
  log_url text
)
```

```sql
matches_index (
  match_id text primary key,
  league text not null,
  season text not null,
  start_date date,
  home_team text,
  away_team text,
  score text,
  r2_key text,
  source text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
)
```

Redis use:

- queue pending live scrape/report/import jobs
- short-lived imported DataFrame references if still in memory
- rate limit counters
- API cache invalidation markers

For user uploads, do not store files in R2 during beta. Normalize in the worker, keep a short-lived job result, and expire after 60 minutes as previously decided.

## Live Scraping Plan

Current live scrape work happens inside the API process. Move it to a worker service.

Recommended implementation:

1. API receives WhoScored URL and creates a `jobs` row.
2. API enqueues a job in Redis.
3. Worker consumes the job and runs Selenium/WhoScored extraction.
4. Worker stores normalized data in a short-lived result store.
5. API reads result by `job_id` when the frontend opens the generated analysis.
6. Job expires and cleanup deletes temporary data.

Worker requirements:

- Docker image with Firefox ESR and geckodriver.
- `max_concurrency=1` or `2` initially.
- Per-user rate limit, for example 3 live scrapes per hour.
- Global rate limit, for example 10 live scrapes per hour during beta.
- Timeout, for example 5-8 minutes per scrape.
- Structured scrape errors shown to users.

Important deployment point: Selenium/browser dependencies should be in the worker image, not necessarily the API image. This keeps API startup faster and reduces memory pressure.

## Season Data Pipeline Plan

Recommended target:

- Railway cron service for scheduled runs.
- Railway Postgres for pipeline metadata.
- Cloudflare R2 for parquet outputs.
- Optional Railway volume only for temporary SQLite compatibility during migration.

Beta pipeline phases:

### Phase 1 - Lift current pipeline

- Containerize `Data/run_all.py` with environment variables.
- Remove hardcoded Discord webhook.
- Run one league/season per cron job or per command argument.
- Write pipeline run metadata to Postgres.
- Upload event parquets and season stats to R2.
- Keep current SQLite flow inside the container temporarily.

### Phase 2 - Make pipeline database durable

- Replace `Data/playback90.db` SQLite state with Postgres tables:
  - known matches
  - processed matches
  - event data staging or raw event JSON/parquet references
  - upload status
- Make each match scrape idempotent by `match_id`.
- Add resumable runs and retry failed matches.

### Phase 3 - Split enrichment and publishing

Separate the pipeline into discrete steps:

1. discover fixtures
2. scrape completed matches
3. normalize events
4. enrich xG/xGOT/xA/xPass/EPV
5. write match parquet to R2
6. regenerate season stats
7. update fixture/round manifests
8. notify success/failure

Suggested schedule during season:

- Top 5 leagues fixture discovery: every 6 hours.
- Completed-match scrape: every 2-4 hours on matchdays, daily otherwise.
- Season stats regeneration: after successful upload batch.
- Player image map refresh: monthly and after transfer windows.
- Standings cache refresh: every 30-60 minutes on matchdays.

## Environments

Create three environments:

1. `local`
   - localhost web/API
   - local `.env`
   - no production auth required, or use Clerk dev instance

2. `staging`
   - Railway staging services
   - Clerk development/staging app
   - separate PostHog project
   - separate Sentry environment
   - R2 can use same bucket with `staging/` prefix or separate bucket

3. `production-beta`
   - Railway production services
   - Clerk production app in restricted mode
   - production PostHog/Sentry projects
   - production R2 bucket/prefix

Required environment variables:

```dotenv
APP_ENV=production
FRONTEND_URL=https://app.playback90.com
API_BASE_URL=https://api.playback90.com/api
NEXT_PUBLIC_API_BASE_URL=https://api.playback90.com/api

DATABASE_URL=postgresql://...
REDIS_URL=redis://...

CLERK_SECRET_KEY=...
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=...
CLERK_JWKS_URL=...
CLERK_ISSUER=...
AUTH_ALLOWED_EMAILS=...

R2_ACCOUNT_ID=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=...

FOOTBALL_DATA_API_KEY=...
ANTHROPIC_API_KEY=...

NEXT_PUBLIC_POSTHOG_KEY=...
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
SENTRY_DSN=...
NEXT_PUBLIC_SENTRY_DSN=...

DISCORD_WEBHOOK_URL=...
```

## Deployment Services

Railway project services:

- `web`
  - root: `apps/web`
  - command: `npm run start`
  - build: existing Dockerfile or Railway Nixpacks
  - public domain: `app.playback90.com`

- `api`
  - Dockerfile: `apps/api/Dockerfile`
  - command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  - public domain: `api.playback90.com`

- `worker-live`
  - Dockerfile: worker-specific Python/Selenium image
  - command: `python -m app.workers.live_scrape_worker`
  - no public domain

- `worker-reports`
  - command: `python -m app.workers.report_worker`
  - no public domain

- `pipeline-top5`
  - Dockerfile: `Data/Dockerfile`
  - cron schedule in UTC
  - no public domain

- `postgres`
  - Railway Postgres

- `redis`
  - Railway Redis

## Cost Estimate for Private Beta

Costs change over time, but this is a realistic starting range for a small private beta.

| Item | Expected beta cost |
|---|---:|
| Railway Pro baseline | about $20/month minimum plus usage |
| Railway compute for web/API/workers/cron | about $20-$80/month depending on scraping frequency and memory |
| Railway Postgres/Redis usage | included in usage, expect low beta usage |
| Cloudflare R2 | likely free or a few dollars unless storage/requests grow; R2 includes free monthly storage/operation allowances and no egress fees |
| Clerk | likely free for private beta unless paid features/branding removal are needed |
| PostHog | likely free at beta scale with event/replay sampling |
| Sentry | free developer tier initially, team plan later if needed |
| Domain/email/webhooks | about $0-$20/month depending on provider |

Expected private beta total: roughly $40-$120/month.

Expected public beta with more scraping and users: roughly $100-$300/month before any heavy AI usage.

## Implementation Phases

### Phase 0 - Pre-deployment security cleanup

- Revoke the committed Discord webhook.
- Move webhook config to `DISCORD_WEBHOOK_URL`.
- Confirm `.env`, `.env.local`, databases, and secrets are ignored.
- Add `.env.example` files with placeholder names only.
- Add production CORS settings that do not allow arbitrary origins.
- Add a deployment checklist.

### Phase 1 - Auth-gated beta app

- Add Clerk to Next.js.
- Add protected middleware/routes.
- Add login/sign-out UI.
- Add FastAPI JWT verification.
- Add server-side email allowlist enforcement.
- Add authenticated fetch from frontend to API.
- Add tests for protected API routes.

### Phase 2 - Deployment foundation

- Create Railway project.
- Add Postgres and Redis.
- Configure `web` and `api` services.
- Add health/readiness endpoints.
- Configure production environment variables.
- Deploy staging first.
- Deploy production beta behind Clerk restricted access.

### Phase 3 - Analytics, feedback, and monitoring

- Add PostHog provider to the web app.
- Identify logged-in users by Clerk id.
- Track core feature events.
- Add session replay with strict masking and sampling.
- Add feedback button and API endpoint.
- Add Sentry to Next.js and FastAPI.
- Add basic alerting for API errors and job failures.

### Phase 4 - Durable jobs and workers

- Add Postgres job store.
- Add Redis queue.
- Move live scrape jobs from in-process thread pool to `worker-live`.
- Move report jobs to a worker if report generation causes API latency or memory pressure.
- Keep imported Wyscout/StatsBomb data ephemeral with 60-minute expiry.
- Add cleanup job.

### Phase 5 - Pipeline deployment

- Parameterize `Data/run_all.py`.
- Remove hardcoded job list.
- Move all webhooks/secrets to env variables.
- Add Postgres pipeline run tracking.
- Deploy pipeline cron service for the top 5 leagues.
- Add match index updates after R2 upload.
- Add failure notifications.

### Phase 6 - Production hardening

- Add staging/production separation.
- Add database backups.
- Add rate limits per user and per IP.
- Add admin operations page for jobs and users.
- Add uptime monitoring.
- Add privacy policy and beta terms.
- Add a runbook for common failures.

## First Decision

The recommended decision is:

Use Railway-first for the private beta, Clerk for invite-only auth, PostHog for analytics/feedback, Sentry for errors, Railway Postgres/Redis for durable state, and Cloudflare R2 for match/season analytical files.

This gives PlayBack90 the fastest path to a controlled beta without boxing the product into a weak architecture. The frontend can still move to Vercel later if public traffic and frontend deployment workflow justify it.

## External References Checked

- Railway pricing and plan resources: https://docs.railway.com/pricing
- Railway cron jobs: https://docs.railway.com/cron-jobs
- Clerk restricted access: https://clerk.com/docs/guides/secure/restricting-access
- Clerk pricing: https://clerk.com/pricing
- PostHog analytics, session replay, and surveys: https://posthog.com
- Cloudflare R2 pricing: https://www.cloudflare.com/products/r2/
