# Hosted Migration Workspace

This repo now contains two parallel application surfaces:

- `PlayBack90.py` and `pages/`: the original Streamlit app
- `apps/api`: the new FastAPI backend
- `apps/web`: the new Next.js frontend

## Recommended local workflow

1. Start the API:
   ```bash
   cd apps/api
   uvicorn app.main:app --reload
   ```
2. Start the web app:
   ```bash
   cd apps/web
   NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api npm run dev
   ```
3. Keep Streamlit available during migration for behavior comparison.

## Implementation notes

- Historical match data still loads from Cloudflare R2 parquet files.
- Live scrape jobs are abstracted behind a job service now; local development uses in-process background execution.
- Complex pitch visualizations are exposed as PNG assets from the backend in phase 1 instead of being fully rewritten client-side.
- `Season Stats` and `Opposition Analysis` now have stable hosted routes, but remain placeholder pages until phase 2.
