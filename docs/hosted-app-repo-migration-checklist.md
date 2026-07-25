# Hosted App Repo Migration Checklist

## Goal

Create a clean private repository for the hosted PlayBack90 app without carrying the old Streamlit code or legacy git history into deployment.

## What Codex Prepared

- `Data/run_all.py` now reads `DISCORD_WEBHOOK_URL` from the environment instead of source code.
- `.env.example` documents shared deployment variables without real values.
- `apps/api/.env.example` includes API deployment variables.
- `scripts/export-hosted-app.sh` exports a clean hosted-app repository skeleton.
- `docs/deployment-onboarding-analytics-plan.md` contains the end-to-end beta deployment plan.

## Manual Steps

1. Revoke the old Discord webhook.
   - The URL was previously committed in `Data/run_all.py`.
   - Create a new webhook only if pipeline notifications are still needed.
   - Store the new value only in Railway/GitHub/local env, never in source.

2. Rotate any production credentials that may have been exposed.
   - R2 access key and secret.
   - Football-data API key.
   - Anthropic API key.
   - Any future Clerk/PostHog/Sentry secrets if they are ever pasted into files.

3. Create a new private GitHub repository.
   - Recommended name: `playback90-app`.
   - Create it empty, without README/license/gitignore, because the export script creates the first commit.

4. Run the export script locally.

   ```bash
   scripts/export-hosted-app.sh ../playback90-app
   ```

5. Push the exported repo.

   ```bash
   cd ../playback90-app
   git remote add origin git@github.com:YOUR_ORG_OR_USER/playback90-app.git
   git branch -M main
   git push -u origin main
   ```

6. Add required repo secrets or deployment provider variables.
   - Start with Railway environment variables, not GitHub Actions secrets, unless CI is added.
   - Use `.env.example` as the checklist.

7. Keep the old repo archived but available.
   - Do not delete this repo yet.
   - It is still useful for comparing Streamlit behavior and recovering migration context.

## First Work After The New Repo Exists

1. Verify local dev in the new repo:
   - API starts.
   - Web app starts.
   - R2-backed match analysis loads.
   - Wyscout/StatsBomb imports still work.
   - Live scrape dependency path is understood.

2. Implement private beta auth:
   - Clerk in Next.js.
   - JWT verification in FastAPI.
   - Server-side email allowlist.

3. Deploy staging on Railway:
   - `web`
   - `api`
   - Postgres
   - Redis

4. Add analytics, feedback, and Sentry before inviting testers.

5. Move live scraping from in-process API threads to a worker service.
