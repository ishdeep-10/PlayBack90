# PlayBack90 App Tech Stack

This document summarizes the current PlayBack90 technical stack and separates what is already implemented from what is planned for deployment.

## Application Surfaces

| Surface | Path | Purpose |
|---|---|---|
| Web app | `apps/web` | Next.js user interface for fixtures, imports, match analysis, reports, and visualizations. |
| API | `apps/api` | FastAPI backend for match data access, analysis views, imports, live scrape jobs, images, standings, and model-backed metrics. |
| Data pipeline | `Data` | Local/container scripts for scraping, enrichment, model feature generation, parquet output, and R2 uploads. |
| Models | `models` | Trained model artifacts, feature schemas, metrics, and reports for xG, xA, xPass, xGOT, and EPV-related work. |

## Frontend Stack

- Next.js 15
- React 19
- TypeScript
- CSS through `apps/web/app/globals.css`
- Plotly.js and `react-plotly.js` for interactive charts
- D3 Geo and `react-simple-maps` for geographic/map views
- GSAP for animation
- Lucide React for icons
- Clerk Next.js SDK for authentication UI and session integration

## Backend Stack

- Python 3.11
- FastAPI
- Uvicorn
- Pydantic and `pydantic-settings`
- PyJWT with crypto support for Clerk JWT verification
- Pandas, NumPy, and PyArrow for football event data processing
- Matplotlib, Pillow, and mplsoccer for football visualizations
- SciPy, scikit-learn, XGBoost, and joblib for model-backed analytics
- Requests, BeautifulSoup, lxml, and Selenium for scraping/import workflows

## Data, Storage, and Formats

- Cloudflare R2 stores hosted match and season analytical files.
- Parquet is the main analytical data format used by the API and pipeline outputs.
- Local SQLite is currently used by `Data` pipeline scripts for pipeline state and intermediate storage.
- Postgres is configured/planned for hosted durable state, including users, jobs, feedback, scrape runs, and pipeline metadata.
- Redis is configured/planned for transient job state, queues, cache, rate limits, and worker coordination.

## Authentication and Access Control

- Clerk is the planned/private-beta authentication provider.
- The web app already includes Clerk integration points and sign-in/sign-up routes.
- The API includes Clerk JWT verification configuration and allowlist controls.
- Private beta access should use Clerk restricted or invitation-only access plus server-side API enforcement.

## Analytics, Feedback, and Monitoring

These are deployment-plan items and are not fully integrated yet:

- PostHog for product analytics, feature usage, funnels, surveys, and optional session replay.
- Sentry for frontend/API error monitoring.
- Better Stack or Railway health checks for uptime monitoring.
- A lightweight feedback endpoint backed by Postgres is planned for beta feedback capture.

## Deployment Stack

- Docker is used for both the API and web app.
- Railway is the planned first deployment platform.
- Initial Railway services:
  - `web`: Next.js app from `apps/web`
  - `api`: FastAPI app using `apps/api/Dockerfile`
  - `postgres`: Railway managed Postgres
  - `redis`: Railway managed Redis
- Later deployment phases may add:
  - live scrape worker service
  - pipeline cron services
  - dedicated background workers

## External Data and APIs

- Cloudflare R2 API for object storage.
- football-data.org API for official standings and competition data.
- WhoScored/Opta scraping flow for live or batch match ingestion.
- Wyscout JSON import.
- StatsBomb JSON import and StatsBomb Open Data samples.

## Legacy or Optional Items

- `anthropic` is currently present in `apps/api/requirements.txt`, and API settings include `ANTHROPIC_API_KEY` / `ai_model`.
- The app does not intend to use Anthropic going forward, so this dependency and related AI insight code can be removed or disabled before production deployment.

