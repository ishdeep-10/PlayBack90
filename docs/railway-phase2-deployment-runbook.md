# Railway Phase 2 Deployment Runbook

This runbook turns the Phase 2 plan into the first staging deployment for the private beta.

## Target Services

Create one Railway project with these services first:

| Service | Source | Deploy command | Public? |
|---|---|---|---|
| `web` | GitHub repo, root `apps/web` | Dockerfile in `apps/web`; start uses `npm run start` | Yes |
| `api` | GitHub repo, repo root build context, Dockerfile `apps/api/Dockerfile` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` via Dockerfile | Yes |
| `postgres` | Railway Postgres plugin | managed | No |
| `redis` | Railway Redis plugin | managed | No |

Workers and pipeline cron services start in later phases.

## Manual Railway Steps

1. Create a new Railway project named `PlayBack90 Staging`.
2. Add a GitHub repo service for the API.
   - Repo: `ishdeep-10/PlayBack90`
   - Root directory/build context: repo root
   - Dockerfile path: `apps/api/Dockerfile`
   - Health check path: `/ready`
3. Add a GitHub repo service for the web app.
   - Repo: `ishdeep-10/PlayBack90`
   - Root directory: `apps/web`
   - Dockerfile path: `apps/web/Dockerfile`
   - Health check path: `/`
4. Add Railway Postgres.
5. Add Railway Redis.
6. Generate public domains for `api` and `web`.
7. Add the staging environment variables below.
8. Deploy API first, then web.
9. After staging works, clone the Railway environment/project for `production-beta` and swap to production Clerk/PostHog/Sentry/R2 values.

## API Environment Variables

Set these on the `api` service. Do not expose these to the web service unless explicitly marked public.

```dotenv
ENVIRONMENT=staging
APP_ENV=staging
FRONTEND_URL=https://your-web-staging-domain.up.railway.app
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}

AUTH_REQUIRED=true
CLERK_JWKS_URL=https://your-clerk-instance.clerk.accounts.dev/.well-known/jwks.json
CLERK_ISSUER=https://your-clerk-instance.clerk.accounts.dev
CLERK_AUDIENCE=
AUTH_ALLOWED_EMAILS=admin@example.com,tester@example.com
AUTH_ALLOWED_USER_IDS=

R2_ACCOUNT_ID=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET=...

FOOTBALL_DATA_API_KEY=...
ANTHROPIC_API_KEY=...
SENTRY_DSN=
DISCORD_WEBHOOK_URL=
```

## Web Environment Variables

Set these on the `web` service. `NEXT_PUBLIC_*` values are public browser values and must be available at build time.

```dotenv
NODE_ENV=production
NEXT_PUBLIC_API_BASE_URL=https://your-api-staging-domain.up.railway.app/api
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
NEXT_PUBLIC_CLERK_SIGN_IN_URL=/sign-in
NEXT_PUBLIC_CLERK_SIGN_UP_URL=/sign-up
NEXT_PUBLIC_POSTHOG_KEY=
NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
NEXT_PUBLIC_SENTRY_DSN=
```

## Clerk Staging Setup

1. Create a Clerk development/staging app.
2. Enable restricted or invitation-only access.
3. Add the Railway web domain as an allowed origin/redirect URL.
4. Invite only the initial tester emails.
5. Confirm Clerk JWTs include email claims if using `AUTH_ALLOWED_EMAILS`. If not, use `AUTH_ALLOWED_USER_IDS` for the beta.

## Validation Commands

After deployment, run these locally:

```bash
curl -s https://your-api-staging-domain.up.railway.app/health
curl -s https://your-api-staging-domain.up.railway.app/ready
curl -I https://your-web-staging-domain.up.railway.app
```

Expected `/ready` when all required config exists:

```json
{
  "ok": true,
  "environment": "staging",
  "checks": {
    "r2": true,
    "redis": true,
    "database": true,
    "auth": true
  }
}
```

If `/ready` returns `503`, fix the false check before sharing the beta URL.

## Production Beta Promotion

Before promoting staging to `production-beta`:

- Use production Clerk restricted access.
- Set `FRONTEND_URL` to the production web domain.
- Set `NEXT_PUBLIC_API_BASE_URL` to the production API domain plus `/api`.
- Confirm `AUTH_REQUIRED=true`.
- Confirm only allowed beta testers are invited/allowlisted.
- Confirm `/ready` returns `200`.
- Run one known match analysis from R2.
- Run one Wyscout/StatsBomb import locally against staging if needed.

## Known Phase 2 Limits

- Postgres and Redis are configured but not yet used for durable jobs. That starts in Phase 4.
- Live scraping still runs inside the API process until the worker migration.
- Sentry/PostHog are documented here, but code integration starts in Phase 3.
