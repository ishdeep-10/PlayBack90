# Competition expansion plan (Dribble360)

Written 2026-10-28. Goal: keep **current-season** data for the major leagues and cups. No 2025/26 backfill for now.
Builds on `docs/dribble360-migration-plan.md` (the top-5 rebuild is done first, then this).

## 1. What Dribble360 has for 2026/27

Played matches to 2026-10-25 (`matches.status = PLAYED`), checked against the vendor metadata tables (no events scan):

| Group | Competition (vendor name) | Played | Upcoming | Clubs | Clubs with no legacy id |
|---|---|---|---|---|---|
| Done | Premier League, La Liga, Serie A, Bundesliga, Ligue 1 | 395 | yes | 94 | 0 |
| Phase 1 | MLS (2026) | 466 | – | 30 | 0 |
| Phase 1 | UEFA Champions League | 144 | 54 | 81 | 59 |
| Phase 1 | UEFA Europa League | 134 | 54 | 76 | 64 |
| Phase 2 | Eredivisie | 90 | 62 | 18 | 18 |
| Phase 2 | Primeira Liga | 81 | – | 18 | 18 |
| Phase 2 | Süper Lig | 81 | – | 18 | 18 |
| Phase 2 | Belgian First Division A | 80 | – | 18 | 18 |
| Phase 2 | Saudi League | 94 | – | 18 | 18 |
| Phase 2 | Brazil Série A (2026, vendor name is also "Serie A") | 319 | – | 20 | 20 |
| Phase 3 | League Cup 76, DFB Pokal 32, Coppa Italia 28, Copa del Rey 20, Super Cups / Community Shield ~6 | ~160 | – | many lower-league | most |
| Optional | UEFA Conference League | 294 | – | 165 | 160 |
| Skip for now | FA Cup (743, incl. qualifying rounds, 699 clubs), EFL Trophy (64), Taça de Portugal (114, 146 clubs) | | | | |
| Not offered | EFL Championship and the second divisions (the app's legacy `league-one` / Segunda files stay as they are) | | | | |

Upcoming fixtures exist in the vendor `matches` table (`status = FIXTURE`, date only, no kickoff time or round).

## 2. What each new competition needs in the app

1. **Team identity (the big one).** The app keys everything on a numeric `teamId` plus a name from `TEAM_DICT` (`apps/api/app/domain.py`, 220 hardcoded entries) and a second copy in `Data/data_utils.py`. `crosswalk_teams.csv` covers 140 clubs. About 200 more clubs are needed for Phase 1 and 2 leagues, and 1,300 across everything.
   - Add `Data/dribble360/team_registry.csv` (`d360_team_id, numeric_id, name, country`), built from the vendor `teams` table.
   - Clubs with a WhoScored id keep it. New clubs get a deterministic id (md5 hash into a range above every WhoScored id, the same approach as the player ids), so ids never change between runs.
   - The API and `data_utils` read the registry on top of `TEAM_DICT`, so adding a competition no longer means editing Python dictionaries.
2. **League registry.** Today the league list lives in `build_crosswalk.LEAGUES`, `domain.LEAGUE_NAME_MAP`, `apps/web/lib/leagues.ts` (plus logos), `schedules.py` and `live_scrape.py`. Replace the sync side with one `competitions.json` (key, vendor league id, display name, season format, kind = league | cup | europe). R2 layout stays `event_data/{league}/{season}/`.
   - Keys: `champions-league` (already used by legacy R2 `season_stats`), `europa-league`, `conference-league`, `eredivisie`, `primeira-liga`, `super-lig`, `belgian-pro-league`, `saudi-pro-league`, `brasileirao`, `league-cup`, `dfb-pokal`, `coppa-italia`, `copa-del-rey`.
   - Season format: Europe `2026/2027`; MLS and Brazil are calendar years (`2026`), same as MLS today.
3. **Cups and Europe change the page logic.**
   - No league table for knockout cups. The Champions League and Europa League league phase can use the existing `calculated` standings source.
   - Two-leg ties, extra time and shootouts: `normalize.derive_period` and the clock fix only handle regular time. **Test on a real extra-time and shootout match before enabling any cup** (period 3 to 5 offsets, shootout penalties must not count as shots in xG).
   - Fixture hub and rounds: `fixture_rounds.py` assumes matchdays. Cups need a stage label (the vendor `description` column may carry it; check).
4. **Schedules.**
   - Top 5: football-data (unchanged). MLS: official MLS API (unchanged).
   - Champions League, Eredivisie, Primeira Liga and Brazil are on football-data's free tier (verify with the key before relying on it). Europa League, Süper Lig, Belgium, Saudi and the cups are not.
   - Fallback for all of those: the vendor `matches` table (date only, no kickoff time or round). One extra metadata query per week, about 0 GB.
5. **Player images.** `build_player_image_map.py` crawls 15 SoccerWiki countries. Add the countries Champions League and Europa League clubs come from (DEN, SCO, AUT, SUI, CZE, CRO, SRB, NOR, GRE, UKR, ISR and so on). Unmatched clubs still fall back to the global name index, so this only affects accuracy.
6. **Season stats.** `generate_season_stats.py --source r2 --season <s> --league <key>` already works per competition. Run it after each competition lands. The season page's league selector needs the new keys.

## 3. Cost and volume

- BigQuery: an events pull scans about 12.3 GB whatever the number of matches or competitions, so adding competitions adds no cost. The project is in the sandbox (1 TiB/month cap, $0, no billing account). One pull per phase is fine; roughly 80 pulls a month would hit the cap.
- R2: about 0.28 MB per match (measured on the 395 live files). Phases 1 to 3 add about 1,650 matches (about 0.5 GB). A full season of everything above would stay under 2 GB of the 10 GB limit.
- Processing: not measured. The earlier 2,146-match estimate was about 45 minutes, so about 1,650 matches should be of that order. Time the Phase 1a run and update this line.

## 4. Sequence

| Phase | Scope | Why this order | Gate |
|---|---|---|---|
| 0 (2026-10-29) | Single rebuild of the top 5 on the republished data, then season stats 2026/27 | Already agreed | Audit passes on all pages |
| 1a | MLS 2026 (466) | All 30 clubs already have ids, so no registry work. Pages need MLS data to be non-empty | Dry run shows no missing clubs (confirmed 2026-10-28) |
| 1b | Team registry + `competitions.json`, then Champions League + Europa League (278) | Needs the registry for about 120 new clubs | Extra-time test passes; standings view for the league phase |
| 2 | Eredivisie, Primeira Liga, Süper Lig, Belgium, Saudi, Brazil (745) | Same mechanics as 1b once the registry exists | Schedule source decided per league |
| 3 | League Cup, DFB Pokal, Coppa Italia, Copa del Rey, super cups | Knockout pages and lower-league clubs; needs the cup rules from section 2.3 | Cup page design agreed |

Each phase is one `sync_current_season.py --league ... ` run, then `--upload-local --live`, then `generate_season_stats.py` for that competition.

## 5. Decisions needed

1. **Qualifiers.** UEFA competitions start on 2026-07-07 with qualifying rounds against obscure clubs. Include them, or start at the league phase? (Including them adds clubs that need ids and images but have no value to most users.) Default proposal: league phase onward.
2. **Conference League** (294 matches, 160 unknown clubs): include or leave out?
3. **FA Cup:** skip until a rule exists to keep only the proper rounds (qualifying rounds are 699 clubs).
4. **Weekly sync host.** The sync needs BigQuery access, R2 keys, and enough memory to hold one 12 GB-scan events pull as a dataframe (not measured; check on the first run). Options: this machine on a schedule, or a small job on the Lightsail box. Needs deciding before cutover (and before WhoScored ingestion is switched off).
5. **Where schedules come from** for the non-football-data competitions (vendor `matches` fallback is the proposal).

## 6. Phase 1 trial run (2026-10-28, local only, nothing uploaded)

`sync_current_season.py --league mls --league champions-league --league europa-league --since 2026-01-01 --out Data/dribble360/out/phase1`, on the pre-republish snapshot.

- **Result:** 651 of 744 matches built, 0 failures: MLS 466 of 466, Champions League 88 of 144, Europa League 97 of 134. The other 93 are July to August qualifying-round matches where the vendor has published no events yet (they retry on each run).
- **Timing:** about 47 minutes in total: about 14 minutes for the BigQuery download, about 33 minutes for 651 matches (about 3 s each). Size: 0.28 MB per match, 182 MB for the 651.
- **Team ids:** `build_team_registry.py` gave all 126 Champions League / Europa League clubs an id: 33 from the crosswalk, 10 reused from `TEAM_DICT` (including Slavia Praha and Bodø/Glimt by hand), 83 minted (10,000,000 and up). All 127 team ids in the output resolve to names in the app.
- **Bugs the trial found and fixed in `normalize.py`:**
  - Penalty-shootout kicks were counted as shots (about 7.8 xG in one match) and goals. They are now retyped `ShootoutGoal` / `ShootoutSavedShot` / `ShootoutMissedShots` / `ShootoutShotOnPost` and are not shots.
  - Late-logged second-half events landed in extra time (raw minutes as low as 74). Extra time and the shootout now have time floors (90:00, 105:00, 120:00), like the 1H/2H rule.
  - `expandedMinute` now continues through extra time (ET1 starts where the 2H ended, ET2 where ET1 ended). **Unverified against WhoScored** (the legacy database has no extra-time matches); it follows the usual Opta convention.
- **Still to do before enabling cups:** the match summary page and score display for a match decided on penalties (shootout score, "pens" label); standings view for the league phase; stage labels.
- **Deliberately not done yet:** `LEAGUE_NAME_MAP` in `apps/api/app/domain.py` does not list the Champions League / Europa League, so they stay out of the league picker until their data is uploaded. Add `"Champions League": "champions-league"` and `"Europa League": "europa-league"` (and update `tests/test_api.py::test_list_leagues`) in the same deploy as the upload. `apps/web/lib/leagues.ts` already has their name and logo.

## 7. Status update (2026-10-29)

- **Phase 0 and Phase 1 are live in R2** (uploaded 2026-10-29): top five 395 matches, MLS 466, Champions League 88,
  Europa League 97; season stats generated; the API lists the Champions League and Europa League and the home globe
  shows them (row of competition chips in the Europe view).
- Team registry built and in use (`Data/dribble360/team_registry.csv`, 126 clubs).
- Not done: Phase 2 (Eredivisie, Primeira Liga, Super Lig, Belgium, Saudi, Brazil), Phase 3 (cups), the decisions in
  section 5, the cup rules in section 2.3 (league-phase table, penalties label on the match page, stage labels).
- Measured: ~3 s per match to process, ~14 min per events download, 0.28 MB per match.
- Runbooks: `dribble360-handoff.md` section 4.
