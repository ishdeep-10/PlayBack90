# Dribble360 Migration — Feature Audit & Plan

_Drafted 2026-10-27. Status: **plan only — nothing in the app or pipeline has been changed.**_

Evidence labels used below: **[verified]** = tested against live data; **[code-scan]** = inferred from a keyword scan of the repo (not a per-visual trace); **[assumed]** = needs checking.

## 1. Decision context

- Subscribed to **BigQuery Pro** (promo $99/mo for 3 months, then $149/mo; cancel any month). Elite API is being cancelled by Dribble360.
- Commercial licence confirmed in writing by Dribble360 (display + store). **Open:** whether training our own xG/xGOT/xA/xPass models on Pro data is allowed — the pricing page lists "model work" only under Max ($499). Get this in writing.
- Why migrate: WhoScored scraping is Cloudflare-blocked from cloud IPs (`docs/deployment-handoff.md`), so ingestion only runs from the dev laptop. Dribble360 is queryable from a server with no scraping, proxies or Selenium.
- Access: Google project `playback90-505308`, dataset `dribble360.football_pro` (app account + personal account have viewer access).

## 2. What Pro actually gives us

[verified] unless noted.

| Item | Finding |
|---|---|
| `match_events` | 25 columns: `id, match_id, team_id, player_id, event_id, type, time_min, time_sec, outcome, x, y, end_x, end_y, pass_length_m, pass_angle_rad, body_part, set_piece_type, is_assist, is_intentional_assist, is_big_chance, is_through_ball, is_switch_of_play, possession_pct, last_updated, match_slug` |
| Missing vs sample CSV (Max-only) | `period_id, goalmouth_y, goalmouth_z, blocked_x, blocked_y, qualifiers_json` |
| Sample match fidelity | 1,574 rows; **identical** to the CSV on every shared field when keyed on `(team_id, event_id)`. `event_id` alone is **not** unique per match. |
| Other tables | `leagues, seasons, matches, teams, players, player_matches (≈307 cols), team_matches (≈303 cols), managers, manager_matches, referees, referee_matches, transfers, product_manifest` |
| `matches` table | Only `id, date, description, home_score, away_score, season_id, status, slug` — **no home/away team ids, venue or attendance** (use `team_matches.side`). |
| Coverage (7 target competitions) | **Complete** for 2024/25, 2025/26 and 2026/27-to-date in PL, La Liga, Serie A, Bundesliga, Ligue 1, MLS. Champions League complete from the league phase; qualifiers (Jul–Aug) have no events. 9.2M events / 5,376 matches in scope. Avg ≈1,700 events/match. |
| Gotcha | "Serie A" exists twice (Italy `1r097lpxe0xn03ihb7wi98kao`, Brazil `scf9p4y91yjvqvg5jndxzhxj`). Always filter by `league_id`. |
| Freshness | Weekly snapshot (manifest: published 2026-10-25 01:20 UTC). Latest matches present: 23 Oct (MLS/UCL 21 Oct); matches played 24 Oct were **not** in it. Real lag is roughly **2–9 days** after a match, vs ~2.5h with the current scrape. |
| `is_big_chance` | Broken (true on 979 of 1,502 sample rows, false on all shots). Dribble360 confirmed; do not use. |
| Per-shot xG | Not provided. Match-level `expected_goals`, `expected_goals_ontarget`, `expected_assists`, `sca/gca`, `carries`, `ppda` exist in `player_matches` / `team_matches`. |

## 3. How the app consumes events today

- Ingestion produces WhoScored-shaped event frames (`Data/main.py::createEventsDF`, `Data/data_utils.py::data_preprocessing`): cumulative minutes, carries, xT, then xG/xGOT/xA/xPass/EPV models → parquet in R2 (`event_data/{league}/{season}/...`).
- The API reads that parquet. Contract = ~79 columns (see `apps/api/app/services/providers/wyscout.py::_base_event`); **55 of them are read by the API/views** [code-scan]. Most-used: `type, teamName, playerName, outcomeType, x, y, xG, minute, matchId, endX, endY, league, season, qualifiers`.
- **A provider-normalizer pattern already exists** (`providers/statsbomb.py`, `providers/wyscout.py`) that maps other feeds into this contract. Dribble360 should be a third normalizer, `providers/dribble360.py` — not a rewrite of the API.

## 4. Impact by feature

Legend: ✅ works as-is · 🔧 derivable from Pro data · ⚠️ degraded · ❌ lost on Pro

### Match Dynamics (summary tab)
| Feature | Status | Notes |
|---|---|---|
| Possession, pass accuracy, PPDA, turnovers by third / 15' window | ✅ | Coordinates + type + outcome only. `period` is needed for the time axis → 🔧 (see §5). |
| xG battle, xG by situation | 🔧 | Per-shot xG comes from **our** model; needs the retrain note in §5. Cross-check vs Dribble360 `team_matches.expected_goals`. |
| Stat breakdowns (goals, shots, big chances) | ⚠️ | Big chances: per-event flag unavailable → show match totals from `team_matches.big_chance_*` only, drop the per-event list. |
| Lineups & substitutions | ❌/🔧 | Today parsed from `FormationSet` qualifiers + `RelatedEventId`. **Correction (§10): BigQuery Pro `player_matches` has no `position`, `shirt_number` or `formation_place`, and `team_matches` has no `formation`** — those exist only in the Elite REST API. Starters/subs can still be derived from events (`PLAYER_ON/OFF`); formation layout cannot. |

### Shots & SCA
| Feature | Status | Notes |
|---|---|---|
| Shot map (location, outcome, xG, situation, body part) | ✅ / 🔧 | `body_part`, `set_piece_type` provided. |
| Blocked vs saved vs off-target | 🔧 | `ATTEMPT_SAVED` covers both. Separate by pairing with an opponent `SAVE` event and the saver's position (GK = save, outfield = block). Tested on the sample: Palace on-target 3/3 ✓, Arsenal 8 vs 7 — close, **needs validation across many matches**. |
| Blocked-shot location | 🔧 (approx) | Outfield `SAVE` event's x,y ≈ block position. |
| Goal-face shot placement | ❌ | Needs `goalmouth_y/z` (Max only). |
| xGOT (per shot) | ❌ | Same. Existing historical xGOT stays; new matches get none. Substitute: match/player-level `expected_goals_ontarget` for totals only. |
| SCA / GCA | 🔧 | Our own derivation continues to work from event sequences; also available as aggregates for validation. |
| Key passes / shot assists | 🔧 | Pass immediately preceding a same-team shot (sequence/`relatedEventId` replacement). |

### In Possession
| Feature | Status | Notes |
|---|---|---|
| Pass network (incl. by-substitution phases), channels, half-spaces, final-third entries, combinations | ✅ | Coordinates + player ids. Sub phases need sub times from `PLAYER_ON/OFF`. |
| Carries, progressive carries, xT | 🔧 | Re-use `insert_ball_carries` + xT unchanged; needs `period` and an `eventId`/qualifiers shim. Cross-check against `player_matches.carries`. |
| Pass types: through ball, switch of play | ✅ | Provided as flags. |
| Pass types: cross, long ball, chipped | ⚠️ | No qualifier flags. Long ball ≈ `pass_length_m` threshold; cross ≈ geometry (wide start → box end) — approximations that will not equal WhoScored counts. |
| Set pieces | ✅ / ⚠️ | `set_piece_type` gives corner/free-kick/throw-in. Delivery-type detail is lost. |
| xA / xPass | ⚠️ | Models use qualifier text; they will run on fewer features and must be re-checked/retrained. |

### Out of Possession, Duels & Transitions, Player Analysis, GK
| Feature | Status | Notes |
|---|---|---|
| Defensive actions, pressing, tackles/interceptions/clearances, aerials, recoveries | ✅ | Event types present; tackle/aerial outcomes via `outcome`. Totals matched `team_matches` for tackles/interceptions/goals/shots on the sample. |
| Transitions (turnover → shot) | ✅ | Needs possession sequencing → 🔧 `get_possessions` already exists (`data_utils.py`). |
| Player analysis (touches, shots, duels) | ✅ | |
| Goalkeeper panel | ⚠️/❌ | Saves and claims are present; **shot placement / goals-prevented views need goalmouth** [code-scan — confirm in `views/goalkeeper.py`]. |

### Platform / data layer
| Item | Status | Notes |
|---|---|---|
| Season stats generation (`generate_season_stats.py`) | 🔧 | Runs on the normalized frame. |
| IDs | 🔧 | Dribble360 uses 25-char string ids for match/team/player. App uses numeric WhoScored ids in R2 file names, `/analysis/[matchId]` URLs, `TEAM_DICT`, kit colours and logos. **Needs a crosswalk** (team by name; matches by date+teams). Biggest hidden task. |
| Venue / attendance | ⚠️ | Not in BQ `matches`. Elite API `/matches` had `venue_id`/`attendance` but no names. |
| Opposition Analysis (currently disabled) | ⚠️ | Re-check when re-enabled. |
| Live in-match / same-day reports | ❌ | Weekly BQ refresh cannot support same-day analysis. |

## 5. What we can derive ourselves (recipes)

1. **`period`** — ~~order by global `id`~~ **superseded, see §10 (use each team's own `event_id` order);** originally: order by `id`; events between `START(0:00)` and the first `END` are period 1, then period 2, etc. Verified exactly on the sample (1H ends 48:05, 2H starts 45:00, ends 98:04). **Test on an extra-time match before relying on it.**
2. **`cumulative_mins`, carries, xT, possessions** — reuse existing code after (1).
3. **`teamName/playerName/h_a`** — join `teams`, `players`, `team_matches.side`.
4. **`shotBlocked / shotOnTarget`** — see Shots table; validate against `team_matches.ontarget_scoring_att` over ~100 matches before shipping.
5. **Key pass / big-chance-created proxy** — last same-team pass before a shot; xG-based "big chance" = shot xG ≥ 0.35 (matches the app's existing `xG>0.35` convention in insights).
6. **xG** — run the existing model. It lists `is_big_chance` as a feature (`xg_features.py`); Dribble360's flag is unusable, so **retrain without that feature** (or substitute xG-threshold-free inputs) and check calibration: per-match sum of our xG vs `team_matches.expected_goals` on a few hundred matches.
7. **Lineups** — `player_matches` + `team_matches.formation`.

## 6. Risks / things still to verify

1. **Freshness regression** (2–9 days vs hours). Decide whether recent matches stay on WhoScored (local scrape) until Dribble360 lands them.
2. **Model-training licence** on Pro (ask Dribble360).
3. **ID crosswalk** and URL/R2 key scheme.
4. **Parity**: sample of ~20 matches run through both feeds; compare derived stats before any cutover.
5. **Extra time / penalties** period handling.
6. **Goalkeeper panel** dependence on goalmouth.
7. Schema drift: manifest shows `schema_version 2026-08-30`; pin and re-check on each refresh.
8. Dribble360 has no stated SLA; keep the WhoScored pipeline runnable until Dribble360 has proven stable.

## 7. Migration plan

**Principle:** additive and reversible. Historical WhoScored parquet in R2 is left untouched; Dribble360 is added as a second provider, validated, then promoted per season/league.

### Phase 0 — Close open questions (this week, $0)
- Written answer on model-training licence; ask whether a Max 7-day evaluation is possible (to see goalmouth/qualifiers on real data).
- ~~Set a daily query quota and budget alert~~ — **not needed / not possible** (checked 2026-10-27). `playback90-505308` has **no billing account**, so it runs in the BigQuery sandbox: hard 1 TiB/month query limit, cannot be charged. (The "Query usage per day" quota is also non-adjustable.) **Do not link a billing account to this project.** Keep `maximum_bytes_billed` in every script as a per-query guard.
- Decide cutover policy for recent matches (risk 1).

### Phase 1 — Parity harness (≈2–3 days, ≈$0)
- Add `Data/dribble360/` loader: one BigQuery pull per sync (never per match; the table is ≈12 GB per scan regardless of filter).
- Normalizer `providers/dribble360.py` → the WhoScored-shaped contract, reusing `insert_ball_carries`, xT, possessions.
- Crosswalk tables: team ids, match ids.
- Run 20 matches already in R2 through both feeds; produce a diff report (counts by type, shots on target/blocked, passes, carries, xG vs `expected_goals`).
- **Gate:** agree thresholds (e.g. goals/shots exact; passes within ±2%; carries within ±10%; on-target exact on ≥95% of matches).

### Phase 2 — Models & visuals adaptation (≈3–5 days)
- Retrain xG without `is_big_chance`; re-check xA/xPass; mark xGOT "unavailable" for Dribble360-sourced matches and hide goal-face views for them (data-driven flag, not a global removal).
- Lineups from `player_matches`.
- Big-chance handling per §4.

### Phase 3 — Backfill (one query, ≈$0)
- One pull for 7 competitions × 2024/25–2026/27 (≈9.2M rows, 12 GB scan — ≈1.2% of the monthly free tier), saved to parquet locally. Process and upload to a **separate R2 prefix** (e.g. `event_data_d360/`) so nothing existing is overwritten.

### Phase 4 — Shadow run (2–3 weeks, within the $99 promo)
- Weekly automated sync on a server (no scraping needed): fetch new matches, normalize, enrich, upload to R2, regenerate season stats.
- Compare against WhoScored for matches that exist in both. Fix drift.

### Phase 5 — Cutover (month 3, before price goes to $149)
- Promote Dribble360 to primary for leagues that passed the gate; keep WhoScored parquet as fallback for historical seasons.
- Decommission the Selenium/proxy ingestion path only after one clean month.
- **Decision point at start of month 3:** keep Pro at $149, or cancel. Revisit Max only if goal-face/xGOT/qualifier features are shown to drive user value.

## 8. Cost summary

| Item | Cost |
|---|---|
| Dribble360 BigQuery Pro | **$99/mo × 3, then $149/mo** (cancel any month) |
| Elite API | $0 (inside free month; cancelled by Dribble360) |
| BigQuery query cost | **$0, and cannot exceed $0**: project is in the sandbox (no billing account), capped at 1 TiB/month. Backfill ≈12 GB; weekly sync ≈12 GB/week ≈ 50 GB/month. Sandbox tables expire after 60 days — irrelevant, as data is stored in R2, not BigQuery. |
| BigQuery storage in our project | $0 (if used, free up to 10 GB) |
| R2 storage | existing; second prefix adds roughly the same parquet footprint |
| Server for weekly sync | can run on the existing small host; no browser needed (removes the $6 Droplet/Firefox requirement and any proxy) |
| **Avoided** | residential proxy / manual laptop scraping |
| Max tier (only if needed) | $499/mo — not planned |

Rough first-year view: Pro ≈ $99×3 + $149×9 = **$1,638**, vs Max alternative ≈ $5,988.

## 9. Immediate next actions

1. Email Dribble360: model-training licence + Max evaluation.
2. ~~Set Google Cloud quota + budget alert~~ — done/not needed (sandbox, see Phase 0).
3. Build the Phase 1 parity harness on 20 matches.


## 10. Parity harness results (2026-10-27, 19 matches, 29,300 WhoScored events)

Code: `Data/dribble360/{build_crosswalk,pick_parity_matches,fetch_parity_data,normalize,compare_parity}.py`; results in `parity_report.md`, `parity_by_match.csv`, `parity_shots.csv`; match crosswalk in `crosswalk_matches.csv` (2,376 of 2,377 local matches mapped, 5 leagues + MLS, 2025/26 and 2026/27).

**Headline: Dribble360 and WhoScored are the same Opta feed.** Event ids, types, outcomes and coordinates are identical.

| Check | Result |
|---|---|
| WhoScored events found by `(team, event_id)` | 99.75% |
| Event type / outcome identical | 100% / 100% |
| Coordinates identical | 99.9% (Dribble360 is 0-100 %; the stored WhoScored data is x*1.05, y*0.68) |
| Period (derived) | 99.4% |
| Shots on target / blocked flag (derived from GK `SAVE`) | 98.2% / 98.8% |
| Shot body part | 100% |
| Shot situation (derived) | 82.5% — misses are penalties (54 shots WhoScored labels with no situation) and direct free kicks (10); corner shots 74/82 |
| Key pass recall / precision (derived) | 84% / 93% |
| Carries, existing `insert_ball_carries` unchanged | 94% of WhoScored carries reproduced, but **+22% extra** |
| Carries, starting only from passes/clearances | recall 91%, precision 93% |

### Corrections to earlier sections
1. **Aggregate tables are much slimmer in BigQuery Pro than the REST API.** `player_matches`: 39 cols (API: 307); `team_matches`: 22 cols (API: 303). Missing in BQ: `position`, `shirt_number`, `formation_place`, `formation`, `ppda`, `sca/gca`, `possession_percentage` (empty), `expected_goals_ontarget` (empty). Dribble360 said Pro replaces Elite; for these fields it does not. **Open decision: lineups/formations need another source (or keep Elite).**
2. **`pass_angle_rad` holds the pass length in metres** (corr 0.9999 with length computed from coordinates); `pass_length_m` is empty. Real angle must be computed from coordinates (done in `normalize.py`). Worth reporting to Dribble360.
3. **`period` must be derived per team by `event_id`, not by global `id`.** `id` is not chronological (late-logged events get large ids). Per-team START/END markers ordered by `event_id` give 99.4%; END at 0:00 = post-game.
4. **`set_piece_type` exists only on passes** (corner, free_kick, goal_kick, throw_in); shot situation is derived from a preceding set-piece pass by the same team within 12 s.
5. **GK identification:** no `position` column; `player_matches.saves` is non-null only for goalkeepers.
6. **Carries:** WhoScored's stored carries start almost only from passes/clearances; the same code on Dribble360 also starts them after recoveries/take-ons/tackles (+22%). The cause in the original raw feed is not visible in the stored data. Either apply the pass/clearance rule (labelled as empirical) or backfill-compare further before deciding.

### Not yet tested
Extra-time/penalty-shootout period handling (no cup matches in the sample), xG/xA/xPass model outputs on Dribble360 input, season-stats regeneration, the numeric-id crosswalk for URLs/R2 keys, and the remaining 71 contract columns (qualifier-derived flags such as crosses, long balls, chipped).


## 11. Decisions (2026-10-27)

| # | Decision |
|---|---|
| 1 | **Lineups: derive from events.** Starters = players with events who did not enter via `PLAYER_ON`; position/side estimated from average event location; formation approximate. Elite is **not** needed for lineups (Max `premier_league_lineups` is Premier League only). |
| 2 | Email Dribble360 to confirm the undocumented extra Pro `match_events` columns are stable (PDF documents 13, live table has 25), and to report the data bugs below. |
| 3 | **Carries: existing `insert_ball_carries` unchanged** (accepts ~+22% vs the historical WhoScored carries; do not mix carry stats across sources in the same view without a note). |
| 4 | **Accept the weekly refresh lag; WhoScored ingestion will be stopped.** Do the stop at cutover, i.e. once the Dribble360 weekly sync for the current season is running and validated — not before, or there is a gap with no source. |
| 5 | **`is_big_chance` is broken globally**, not just in the sample: across all 34,369 matches in `football_pro` (2020-present) ~100% of passes are flagged and ~0% of shots; only 50 matches have any flagged shot. Reported to Dribble360 for a fix. Until fixed, ignore the flag. |
| 6 | **IDs:** Dribble360 string ids become the primary key for all new (Dribble360-sourced) matches; URLs accept both. Existing WhoScored numeric ids stay valid and resolve through `crosswalk_matches.csv`. |
| 7 | **Hide goal-face shot placement and xGOT** for Dribble360-sourced matches (data-driven, per match; not removed for historical WhoScored matches). |
| 8 | **Scope: current season first** (2026/27 for the five leagues and Champions League; MLS 2026). Historical WhoScored data stays as-is; no backfill of earlier seasons for now. |

### Schema reference notes (Dribble_BigQuery_Schema_Reference.pdf, checked 2026-09-17)
- Pro `match_events` is documented as 13 columns; the live table has 25 (adds end coordinates, pass/body-part/set-piece/assist flags, `possession_pct`). **Reliance on undocumented columns — confirm with Dribble360.**
- Max adds 7 tables, **all `premier_league_*`** (events with `period_id`/`qualifiers_json`/formation, qualifiers, lineups, versions). Max does not appear to help non-PL leagues.
- Pro `player_matches` = 39 columns (no position/shirt number); the `dribble-player_matches-sample.csv` with positions is richer than Pro.


## 12. Full-chain results and the xG gap (2026-10-27)

Pipeline: `normalize.py` -> `process_match.py` (existing `data_utils.data_preprocessing`: carries, xT, EPV, xA, xPass, xG) on the 19 parity matches; checked column-by-column against the stored WhoScored frame (`compare_contract.py`, `contract_columns.csv`). Run with `apps/api/.venv/bin/python` (has xgboost/sklearn).

**Match well (>=99%):** isTouch/touches, isShot, isGoal, shotOffTarget, shotOnPost, foulGiven/Committed, turnover, dispossessed, cornerAwarded, throwIn, passCorner, through balls, penalties (4/4 scored, 2/2 missed, location + isolation rule), cumulative_mins (corr 0.9999), x/y/endX/endY, prog_pass/prog_carry.
**Approximate:** shotBlocked (96% recall), passKey (84% recall / 94% precision), long balls (~83-95%), crosses (precision 46-81%), aerials (97%).
**Unavailable on Pro (set False/empty):** shotCounter, passChipped, isOwnGoal/goalOwn, assist* delivery split (tiny counts).

### xG gap: root cause = the broken `is_big_chance` input
Current xG model run on both datasets, 483 shots:
| Dribble360 build | total xG (WS data = 49.7) | corr | mean abs err/shot |
|---|---|---|---|
| big-chance input empty | 28.5 (-43%) | 0.73 | 0.046 |
| geometry stand-in (shot <=11 m from goal and <=10 m laterally) | 52.7 (+5.9%) | 0.81 | 0.041 |
| true WhoScored big-chance flags | 47.5 (-4.4%) | **0.977** | **0.008** |
Everything else rebuilt (situation, penalties, previous-action context, body part, carries) reproduces the model almost exactly. Independent anchor: Dribble360's own team `expected_goals` total for the 19 matches is 50.7; our stand-in build gives 52.7 (team-match corr 0.84) vs 0.75 for the WhoScored build. **The stand-in is enabled by default (`to_contract(big_chance="proxy")`); replace it with the vendor flag once Dribble360 fixes it** (expected corr ~0.98). No model training involved.

### Findings about the existing app (independent of this migration)
1. **`passFreekick` is identical to `passCorner` on every pass in the stored data (100%).** Free-kick passes are mislabelled (the API reads `passFreekick` in 2 files). Dribble360 matches use the correct definition, so free-kick stats will differ from history.
2. **Stored xG is from a different/older model version and is incomplete:** 141 of 483 stored shots (29%) have no xG (e.g. 41 of 115 Premier League shots in the local R2 cache). Recomputing with the current model gives 40.1 vs 52.6 stored (corr 0.74). New Dribble360 matches will carry current-model xG; history will not match it exactly.
3. The `sqlite` event table has no `xGOT` column; xGOT lives only in R2 parquet.

### Still to build
`sync_current_season.py` (weekly one-query pull, process, write local parquet; R2 upload behind an explicit flag), team crosswalk for newly promoted clubs, and the Champions League league key.

## 13. Page-by-page audit of live Dribble360 frames (2026-10-28)

Method: ran every API view builder on 25 fixtures that exist in both the old WhoScored files and the new Dribble360 files and diffed the payloads (`scratchpad/audit_all.py`). No builder errored. Lists were truncated at 400 items per list, so ID/minute sums are unreliable; counts and presence are reliable.

### Broken (feature empty or wrong) — fix before next rebuild
| # | Page | Symptom | Cause | Fix |
|---|---|---|---|---|
| 1 | Set Pieces | corners, free kicks, throw-ins, goal kicks all empty (e.g. 111 corner deliveries -> 0) | views detect them via `qualifiers` text (`CornerTaken`, `FreekickTaken`, `ThrowIn`, `GoalKick`); ours has `FromCorner`/`ThrowinSetPiece` only | write the Opta qualifier names in `to_contract` (+ `RightFoot`/`LeftFoot` for corner swing, `ShotAssist`/`IntentionalGoalAssist`/`BigChanceCreated`, `Penalty`) |
| 2 | Defensive Actions | aerials 329 -> 0 | `matches.py:350` keeps aerials only if qualifiers contain `Defensive` | derive Defensive/Offensive aerial qualifier; validate heuristic on WhoScored truth |
| 3 | Shots, Player Analysis, team totals | assists 59 -> 0 | vendor `is_assist` wrong until 28 Oct 23:00 UTC publish | fallback derivation already coded in `normalize.py`; vendor flag takes over after republish |
| 4 | Lineups | panel empty | no qualifiers on FormationSet/Sub rows | done (`lineups.py`), roles estimated, formation shape hidden |
| 5 | Clock | `expandedMinute` = raw minute (no first-half stoppage offset; WhoScored's 2H starts at 51 after 5' added) and half-time substitutions land in period 1 | `normalize.py` | expandedMinute = minute + (last 1H minute - 44) for period 2; subs/cards logged after the 1H END marker at 45:00 -> period 2. Affects sub windows (pass network, in-possession), lineups phases, windowed charts |

### Hidden by design (no goal-mouth placement)
Goal-face map and xGOT: Shots (done), Match Dynamics header (xGOT), Goalkeeper shots-faced goal map, Player Analysis shot placement. Big Chances row on Match Dynamics: stand-in until vendor flag is live.

### Degraded / approximate
Situation labels 82% (direct free kicks, some corner shots read as open play), long balls +15%, crosses approximate, `passChipped` always False, `OffsideGiven` events absent (91 -> 0 in sample), no shirt numbers/unused subs/formation shape, carries differ in membership (+30% vs 2025/26 WhoScored, -47% carry xT vs old 2026/27 frames), position-timeline has fewer phase splits (no FORMATION_CHANGE).

### Out of Possession and Duels & Transitions (re-checked on 40 fixtures, both teams)
- Out of Possession: tackles, interceptions, clearances, recoveries, blocked passes, possession-loss opportunities (2,072) and confirmed regains (1,666) are **identical**. Only break: **aerials 1,084 -> 0** (needs the `Defensive` qualifier, fix #2); this also undercounts the player panel "Aerials" and the "emergency actions" text in `DefensiveActionsPlotly.tsx`. Counterpress actions/regains ~5-6% lower; recovery-time buckets within +-6%.
- Duels & Transitions: 7,415 duel rows in both sources, transitions 2,071 vs 2,061, aerial duels 172/176 vs 171/177 (won/lost). Small outcome shifts on a few types (foul success/fail +-17 events, tackle lost 115 -> 95, take-on lost 151 -> 175 over 15 fixtures) look like feed revisions, not mapping errors (parity matches agree 100% on outcomes).
- Neither page uses xGOT, goal-mouth placement, lineups or big chances. Visuals were checked at the data/field level only; not yet looked at in a browser.

### Still to re-check after fixes 1-5
Pass network progressive passes (-18%), progressive carries (-19%) and channel-analysis xT (-21%): whole-match `prog_pass` is identical, so these point at the sub-window clock bug (#5). The earlier "-12 to -23%" figures for defensive attacking-third / loss locations were small-sample noise plus the missing aerials.

### Better than before
EPV and xPass populated on new matches (old 2026/27 frames had none), situation filled for 99% of shots (88% before).

## 14. Vendor republish check (2026-10-29)

- The corrected tables were already live when checked: `match_events` last modified 2026-10-28 04:47 UTC (earlier than the announced 23:00 UTC). The 651-match local trial of 2026-10-28 was therefore already on the corrected snapshot (`pass_length_m` populated, average 18 m).
- Checked against WhoScored on the 19 parity matches (33,020 events):
  - `is_big_chance` on shots: **fixed**, 82 of 82 identical to WhoScored. It is not set on passes (BigChanceCreated is still derived).
  - `is_assist`: **still wrong**. 460 flagged vs 20 real goal assists (precision 4%, recall 100%): it flags every pass that leads to a shot. `is_intentional_assist` is the same (487 flagged).
  - `is_switch_of_play`: 135 flagged; WhoScored has no such tag locally, so it cannot be checked.
- Fix in `normalize._derive_pass_fields`: a vendor-flagged pass keeps `assist` only if the same team's next shot by another player within 8 s (same period) is a goal. Against WhoScored: precision 0.96, recall 0.93 (5 s: 0.96 / 0.86; 12 s: same as 8 s). The old fallback (key pass of a goal, ignoring the vendor flag) gave 0.73 / 0.76.
- Ask Dribble360 whether `is_assist` is meant to mean "shot assist" (it behaves like one).
