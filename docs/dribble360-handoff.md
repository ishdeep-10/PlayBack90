# Dribble360 data pipeline: handoff (read this first)

Living document. Last updated **2026-10-29**. It describes what is true now, how to operate the pipeline, and the
rules that must not be broken. History and reasoning live in `dribble360-migration-plan.md` (long; sections 13-14 are
the latest audit) and `competition-expansion-plan.md`. Hosting is in `deployment-handoff.md`. The licence record is
`dribble360-licence.md`.

## 1. State of play

- **Source of match data for the current season is Dribble360** (BigQuery Pro, `dribble360.football_pro`), the same
  Opta feed WhoScored shows. The old WhoScored scraper still exists in `Data/` but is no longer the source for
  2026/27. **Open:** stop WhoScored ingestion at cutover and decide where the weekly sync runs.
- **Live in R2 (`event_data/`, bucket root, replaced 2026-10-29):** 1,046 matches. Premier League 80, La Liga 100,
  Serie A 80, Bundesliga 63, Ligue 1 72 (season `2026_2027`), MLS 466 (`2026`), Champions League 88, Europa League 97
  (`2026_2027`). Latest matches: top five 25-26 Oct 2026, MLS 26 Oct, Champions League 21 Oct, Europa League 22 Oct.
  93 UEFA qualifying matches have no vendor events yet (the sync retries them).
- **`season_stats/`** regenerated for the same eight competitions from the new frames.
- **Deployed 2026-10-29** (API and web, Lightsail). Details and rollback in `deployment-handoff.md`.
- **Not in scope yet:** 2025/26 backfill (not wanted), Conference League, FA Cup, domestic cups, other leagues
  (plan in `competition-expansion-plan.md`).

## 2. Rules that must not be broken

1. **BigQuery billing.** Project `playback90-505308` is the sandbox: no billing account, hard cap 1 TiB/month, $0.
   **Never link a billing account to it.** Every query carries `maximum_bytes_billed`. One events pull scans about
   12.3 GB whatever the number of matches (billed by columns), and takes ~14 minutes to download; the sync caches it.
2. **Licence** (`dribble360-licence.md`): paywall and derived metrics are allowed; **never ship raw data** (no CSV/JSON
   export, no event rows in PDFs, no feed/API of the data); credit text is "Data by Dribble (dribble360.com)"; **no
   Dribble logo; do not name Opta**. Keep data behind login and rate-limited; `/terms` forbids scraping.
3. **R2 uploads and deletes need explicit flags** and, for anything new, the owner's go-ahead. Bucket limit is 10 GB
   (about 0.28 MB per match). Never print API keys or R2 secrets; check existence/length only.
4. **No model training.** xG/xA/EPV/xPass models are existing lookups (`models/`), not trained on Dribble data.
5. **Web builds use the production Clerk key** (`NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY_PROD`, `pk_live_`); the root `.env`
   keeps a test key as the main one for local dev. A test-key build breaks sign-in for everyone.
6. Emails to Dribble are written in the first person ("I"). Do not call the relationship a "partnership".
7. Confirm before destructive or outward-facing actions (deploys, uploads, deletes, pushes, posts).

## 3. Code map (`Data/dribble360/`)

| File | Purpose |
|---|---|
| `sync_current_season.py` | The weekly sync: list played matches, one events pull, normalize each match, write parquet under `out/`, optionally upload. State in `out/synced_matches.json`, download cache in `out/_fetch/` with `requested_ids.json` |
| `normalize.py` | Vendor events to the WhoScored contract: types, periods, clock (`expandedMinute`, extra time), shots/xG inputs, key passes and assists, qualifiers the pages search for (corner, free kick, aerial Defensive, ...), shootout retyping |
| `process_match.py` | Runs normalize, contract, `Data/data_utils.data_preprocessing` (xG/xA/EPV/xPass models) and the lineup rebuild for one match |
| `lineups.py`, `position_history.json`, `build_position_history.py` | Rebuilds lineups from events and minutes (no formation name: the shape is an estimate, flagged `FormationEstimated`) |
| `build_crosswalk.py`, `crosswalk_*.csv` | `LEAGUES` (vendor league ids) and the Dribble id to legacy WhoScored id maps for clubs and the 19 parity matches |
| `build_team_registry.py`, `team_registry.csv`, `apps/api/app/team_registry.json` | Numeric ids and names for clubs outside the crosswalk (Champions/Europa League). Stable: existing rows are never changed |
| `validate_vendor_flags.py` | Precision/recall of the vendor flags and our final fields against WhoScored on the 19 parity matches. **Run after every vendor republish** |
| `precheck_upload.py` | Sanity checks on `out/` before an upload |
| `audit_pages.py` | Every page's view builder on 25 matches, old WhoScored backup vs new frames |
| `parity_*`, `compare_*`, `xg_*`, `fetch_parity_data.py` | Earlier parity and xG experiments (history) |

Other pieces: `Data/generate_season_stats.py` (season stats from R2), `Data/build_player_image_map.py` (player photos),
`apps/api/app/services/rate_limit.py` and `main.py` (rate limit), `apps/web/app/terms/page.tsx`.

## 4. Runbooks

Environment: use `apps/api/.venv/bin/python` (it has xgboost/sklearn). It lacks the BigQuery client, so install it to a
side folder and put that on `PYTHONPATH`:
`apps/api/.venv/bin/pip install --target ~/.d360-bq google-cloud-bigquery db-dtypes` then
`PYTHONPATH=~/.d360-bq ...`. BigQuery auth is application-default credentials of an account with viewer access to the
dataset. R2 keys come from the root `.env`. Set `AWS_DEFAULT_REGION=auto` if boto3 complains about the region.
Billing project argument is `playback90-505308`.

### Weekly sync (incremental)
```
PYTHONPATH=~/.d360-bq apps/api/.venv/bin/python -W ignore Data/dribble360/sync_current_season.py playback90-505308 \
  --league premier-league --league laliga --league serie-a --league bundesliga --league ligue-1 \
  --league mls --league champions-league --league europa-league --since 2026-01-01 --dry-run
```
Drop `--dry-run` to build locally into `Data/dribble360/out/` (new matches only). Add `--upload --live` to upload as it
goes. `--since 2026-01-01` is needed for MLS (calendar-year season). The default league list is the top five only.

### Full rebuild after a vendor republish
1. `PYTHONPATH=~/.d360-bq apps/api/.venv/bin/python Data/dribble360/validate_vendor_flags.py playback90-505308 --refetch`
   and compare with the reference numbers in its docstring. If the flags changed, fix `normalize._derive_pass_fields`.
2. `rm -rf Data/dribble360/out`, then the sync command above without `--dry-run` (~14 min download + ~3 s per match).
3. `apps/api/.venv/bin/python Data/dribble360/precheck_upload.py`.
4. Upload: `... sync_current_season.py playback90-505308 --upload-local --live --overwrite` (deletes and re-uploads each key;
   ~2 s per file; prints a summary only at the end). Then list the bucket and diff against `out/` (should be exactly equal).
5. Season stats, from `Data/`: `../apps/api/.venv/bin/python generate_season_stats.py --source r2 --season 2026_2027` and
   `--season 2026 --league mls`.
6. From `apps/api`: `.venv/bin/python ../../Data/dribble360/audit_pages.py`.

### Add a competition
Add its vendor league id to `LEAGUES` in `build_crosswalk.py`; run `build_team_registry.py <project> --league <key>`
(new clubs get ids); dry-run the sync for it (it prints clubs missing ids); build locally; check; upload; season stats;
add it to `LEAGUE_NAME_MAP` in `apps/api/app/domain.py` (and the test in `tests/test_api.py`) and to
`apps/web/lib/leagues.ts` (a country league goes in `LEAGUE_PRESENTATION`, a continental cup in
`COMPETITION_PRESENTATION`). Cups need the checks listed in `competition-expansion-plan.md` first.

### Player photos
`apps/api/.venv/bin/python Data/build_player_image_map.py` crawls SoccerWiki country pages (needs network, ~2 min) and
rewrites `player_images_map.json` (merging with the old map). The API also needs the SoccerWiki player JSON at the repo
root as the name fallback; the API Dockerfile copies it with `SoccerWiki*.json` (an escaped-space glob once silently
copied nothing).

## 5. Data semantics and gotchas

- **Vendor columns (25 in `match_events`)** have no qualifiers, period id, goal-mouth, shirt numbers or formation ids.
  Join key between sources is `(team_id, event_id)`.
- **`is_assist` is a shot assist** (flags every pass that leads to a shot). It is the source of `passKey`; a goal
  `assist` is a flagged pass whose same-team next shot by someone else within 8 s is a goal. `is_big_chance` is correct
  on shots (exact); `bigChanceCreated` is derived from it. `pass_length_m` is metres. Check the numbers with
  `validate_vendor_flags.py` whenever the vendor republishes.
- **Clock:** `expandedMinute` for the second half is minute + (last first-half minute - 44); extra time continues from the
  second half (unverified against WhoScored, no extra-time match locally). Half-time substitutions go to the second half.
- **Shootout kicks** are retyped `ShootoutGoal` / `ShootoutSavedShot` / ... and are not shots or goals.
- **Aerials** get Opta's `Defensive`/`Offensive` tag from position (x <= 52.5 means Defensive; 99.9% match).
- **Player ids** are hashed to stable numbers (md5, first 8 hex digits); the vendor id is kept in `d360_player_id`.
- **Team ids** are legacy WhoScored ids where known, else minted (>= 10,000,000). Names are filled by the API from
  `TEAM_DICT` plus `team_registry.json`.
- **Hidden by design** because Pro has no goal-mouth: xGOT everywhere, the goal-face map, goalkeeper goals-prevented.
  Lineups show an estimated shape without a formation name.
- **Vendor data lag:** matches appear in `matches` before their events; they retry on the next sync.

## 6. Open items (as of 2026-10-29)

0. **Git push is blocked.** This machine's GitHub login is `ishdeep-score`, which gets `403` on
   `ishdeep-10/PlayBack90`. All work up to 2026-10-29 is committed locally on `main` (17 commits ahead of `origin/main`)
   and deployed, but not on GitHub. Fix: add `ishdeep-score` as a collaborator with write access (repo Settings,
   Collaborators), or push from a session logged in as `ishdeep-10`; then `git push origin main`.
1. Audit differences not yet explained: progressive passes -15%, progressive carries -18%, transitions to attack -27%,
   box entries -14%, channel xT and flow, goal difference before shots (own goals or ordering?). Next step: compare one
   match event by event, old vs new.
2. Stop WhoScored ingestion; decide where the weekly sync runs (this machine on a schedule, or the Lightsail box).
3. Decisions: UEFA qualifiers (93 matches without events), Conference League, FA Cup, domestic cups, other leagues.
4. Legal read of `/terms`; payment and refund wording; governing law.
5. Remove the `previous` Docker images on the server after the deploy is trusted (`deployment-handoff.md`).
6. The WhoScored HTML import endpoint still exists server-side (only the UI tab is removed).
7. Pro price steps from $99 to $149 after month 3: set a reminder.
8. Ask Dribble360 to confirm `is_assist` means "shot assist" (it behaves as one).
9. Season Stats page, matches list, AI analyst/insights and reports were not audited on the new data.
