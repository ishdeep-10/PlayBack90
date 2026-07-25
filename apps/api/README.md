# PlayBack90 API

FastAPI backend for the hosted PlayBack90 migration.

## Run locally

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API expects the existing repo `.env` and `Data/.env` files for R2 credentials.

## Current phase-1 coverage

- league, season, and fixture browsing
- match loading from Cloudflare R2 parquet files
- summary analysis endpoints for hosted Post Match Analysis
- server-rendered PNG assets for complex visuals
- generated PDF match reports
- async live scrape job scaffolding
