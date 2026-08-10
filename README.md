# PlayBack90

**Football, translated.** PlayBack90 turns event data into interactive match analysis for analysts, coaches, and supporters who want to understand the game beyond the scoreline.

[Open PlayBack90](https://playback90.com)

## What the app does

- Browse fixtures by league, season, matchday, and completion state across Europe's top five leagues.
- Explore post-match analysis through Match Dynamics, Shots and SCA, In Possession, Out of Possession, Duels & Transitions, and Player Analysis views.
- Inspect xG flow, passing networks, chance creation, defensive shape, territory, transitions, set pieces, goalkeeper actions, and player-level output.
- Import a saved WhoScored Match Centre page, Wyscout JSON, StatsBomb JSON, or an official StatsBomb open-data sample.
- Compare match performance with season baselines and league context.
- Build opposition dossiers and export analysis reports when the corresponding feature flags and services are enabled.
- Protect hosted routes with Clerk and monitor production through optional PostHog and Sentry integrations.

## Architecture

| Layer | Technology |
| --- | --- |
| Web | Next.js 15, React 19, TypeScript, Plotly, D3, GSAP |
| API | FastAPI, Pydantic, Pandas, NumPy, SciPy, scikit-learn |
| Models | xG, xGOT, xA, xPass, EPV, and supporting match-context models |
| Match storage | Cloudflare R2 with Parquet event data |
| Authentication | Clerk |
| Providers | WhoScored HTML, Wyscout JSON, StatsBomb JSON/open data, football-data.org |
| Operations | Docker, Caddy, Sentry, PostHog, optional Redis and PostgreSQL |

```text
PlayBack90/
├── apps/
│   ├── api/            FastAPI endpoints, provider adapters, models, and tests
│   └── web/            Next.js application and demo automation
├── Data/               Data-processing and backfill utilities
├── deploy/             Production Compose and Caddy configuration
├── docs/               Architecture, deployment, and product plans
└── docker-compose.yml  Local two-service stack
```

## Local development

### Prerequisites

- Node.js 20 or newer
- Python 3.11
- npm
- Cloudflare R2 credentials for hosted historical match data

### 1. Configure the environment

Create the shared API environment file:

```bash
cp .env.example .env
```

Create the web environment file:

```bash
cp apps/web/.env.example apps/web/.env.local
```

For a basic unauthenticated local session, set `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api` and leave the Clerk values empty. Add Clerk credentials to both environments when testing the protected application.

### 2. Install dependencies

```bash
python3.11 -m venv apps/api/.venv
apps/api/.venv/bin/pip install -r apps/api/requirements.txt
npm --prefix apps/web install
```

### 3. Start the API

```bash
apps/api/.venv/bin/uvicorn app.main:app \
  --app-dir apps/api \
  --host 127.0.0.1 \
  --port 8000 \
  --reload
```

### 4. Start the web app

In another terminal:

```bash
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3000
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

### 5. Verify the services

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/api/leagues/premier-league/seasons
```

## Run with Docker

After creating the root `.env` file:

```bash
docker compose up --build
```

The web app runs on port `3000` and the API on port `8000`.

## Match imports

Open `/live-scrape` and select an import source:

- **WhoScored HTML:** save a completed Match Centre page and upload the HTML file.
- **Wyscout JSON:** upload a match export containing match metadata and an events array.
- **StatsBomb JSON:** upload event data, optionally with lineups and match metadata, or select an included open-data sample.

Imported files are normalized into PlayBack90's common event model and open in the same analysis workspace as hosted matches.

## Environment reference

| Variable | Purpose |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | API URL used by the Next.js app |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_BUCKET` | Historical match storage |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | Web authentication and demo testing |
| `AUTH_REQUIRED`, `CLERK_JWKS_URL`, `CLERK_ISSUER` | API authentication enforcement |
| `FOOTBALL_DATA_API_KEY` | Official schedules and standings |
| `X_APISPORTS_KEY` | Optional coach and transfer context fallback |
| `ANTHROPIC_API_KEY` | Optional AI-assisted insights |
| `REDIS_URL` | Optional persistent job storage |
| `NEXT_PUBLIC_POSTHOG_KEY` | Optional product analytics |
| `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` | Optional API and web error reporting |
| `NEXT_PUBLIC_OPPOSITION_ANALYSIS_ENABLED` | Enables the opposition-analysis interface |

See [.env.example](.env.example), [apps/web/.env.example](apps/web/.env.example), and [apps/api/.env.example](apps/api/.env.example) for the complete templates. Never commit real credentials.

## Tests and checks

Run the API test suite:

```bash
apps/api/.venv/bin/python -m pytest apps/api/tests
```

Build the production web application:

```bash
npm --prefix apps/web run build
```

## Record the signup product demo

The repository includes browser automation for the signup-to-match journey. It records signup, import options, the landing-page walkthrough, league and fixture selection, and the resulting analysis.

The script uses Clerk's official test-user convention and deletes its disposable account when the run finishes. Chrome and valid Clerk development credentials are required.

```bash
npm --prefix apps/web run demo:signup
```

Optional overrides:

```bash
PB90_DEMO_URL=http://127.0.0.1:3000 \
PB90_CHROME_PATH=/path/to/chrome \
PB90_DEMO_VIDEO_DIR=/tmp/playback90-demo \
npm --prefix apps/web run demo:signup
```

The command prints the generated WebM path when it completes. Rendered social assets are intentionally not committed to the repository.

## Deployment and project documentation

- [Technology stack](docs/app-tech-stack.md)
- [Deployment handoff](docs/deployment-handoff.md)
- [Hosted-app migration checklist](docs/hosted-app-repo-migration-checklist.md)
- [Railway deployment runbook](docs/railway-phase2-deployment-runbook.md)
- [Match-analysis roadmap](docs/match-analysis-roadmap.md)
- [Opposition-analysis plan](docs/opposition-analysis-plan.md)
