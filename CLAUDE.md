# PlayBack90: notes for Claude Code sessions

Football match-analysis app, live at https://playback90.com (AWS Lightsail). Solo developer. Next.js web (`apps/web`),
FastAPI API (`apps/api`), match data in Cloudflare R2 read by the API. Event data for the current season comes from
Dribble360 (BigQuery Pro, the Opta feed) via `Data/dribble360/`.

## Read first (in this order)
1. `docs/dribble360-handoff.md` current state, rules, code map, runbooks, gotchas, open items.
2. `docs/deployment-handoff.md` hosting, deploy runbook, rollback, production quirks (read before any deploy).
3. `docs/dribble360-licence.md` what the data licence allows (read before any export, download, post or email).
4. `docs/competition-expansion-plan.md` which competitions exist, what adding one takes.
5. `docs/dribble360-migration-plan.md` history and the page-by-page audits (long; sections 13-14 are the latest).
`docs/README.md` lists every doc and marks the superseded ones.

## Hard rules
- BigQuery project `playback90-505308` is a billing-free sandbox: never link a billing account; keep
  `maximum_bytes_billed` on every query; an events pull scans ~12.3 GB whatever the match count.
- Never ship raw data: no CSV/JSON export, no event rows in PDFs. Credit is "Data by Dribble (dribble360.com)",
  no Dribble logo, never name Opta.
- Never print API keys or secrets (check existence/length only). Web builds use the `pk_live_` Clerk key.
- R2 uploads/deletes, deploys, pushes and public posts are outward-facing: confirm first, use explicit flags.
- We do not train models. Emails to Dribble are in the first person ("I"); do not say "partnership".

## Commands
- API tests: `cd apps/api && .venv/bin/python -m pytest -q` (75 pass). Web types: `cd apps/web && npx tsc --noEmit`.
- Sync, rebuild, upload, season stats, audits: see the runbooks in `docs/dribble360-handoff.md`.
- Use `apps/api/.venv/bin/python` for anything touching `Data/` (it has xgboost/sklearn).

## Conventions
- Match the surrounding code's style and comment density; no new dependencies without a reason.
- Do not commit: `Data/playback90.db`, `Data/dribble360/out/`, `cache/`, vendor sample files (CSV/PDF from Dribble360),
  secrets, `.env`. `Data/main.py`, `Data/run_all.py`, `Streamlit/`, `social-media/` and the demo scripts under
  `apps/web/scripts/` are older, separate work: leave them unless asked.
- A Docker `COPY` with a wildcard that matches nothing succeeds silently: verify image contents after building.
- Update the relevant doc in the same change when behaviour, runbooks or rules change.
