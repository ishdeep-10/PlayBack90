# PlayBack90 App

Hosted PlayBack90 platform repo containing the Next.js web app, FastAPI API, data pipelines, models, and deployment docs.

## Local development

1. Copy `.env.example` to `.env` and fill local values. R2 credentials are required for hosted match fixtures and reports.
2. Install API dependencies:

   ```bash
   python3.11 -m venv apps/api/.venv
   apps/api/.venv/bin/pip install -r apps/api/requirements.txt
   ```

3. Install web dependencies:

   ```bash
   cd apps/web
   npm install
   ```

4. Start the API:

   ```bash
   cd apps/api
   .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
   ```

5. Start the web app:

   ```bash
   cd apps/web
   npm run dev -- --hostname 127.0.0.1 --port 3000
   ```

6. Open `http://127.0.0.1:3000`.

Useful checks:

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/api/leagues/premier-league/seasons
```

See `docs/deployment-onboarding-analytics-plan.md` for the private beta deployment plan.
