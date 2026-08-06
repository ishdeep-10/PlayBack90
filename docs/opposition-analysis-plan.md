# Opposition Analysis Plan

## Objective

Build Opposition Analysis into a pre-match team dossier inside PlayBack90. The report should help a coach, analyst, or scouting user answer:

- What does this opponent usually do?
- Where are they dangerous?
- Where are they vulnerable?
- Which players matter most?
- What should our tactical plan account for?

The current app already has a lightweight Opposition Analysis route and API service:

- Frontend: `apps/web/app/opposition-analysis/page.tsx`
- API routes: `/api/leagues/{league}/seasons/{season}/opposition/{team}/report` and `/assets/{asset_id}.png`
- Service: `apps/api/app/services/opposition.py`

The initial implementation is useful as a seed, but the target product should become a multi-match opposition dossier rather than a simple season percentile page.

## First User Flow and UX Target

Opposition Analysis should be reached from the same league/map exploration flow as Post Match Analysis. The first experience should not ask the user to understand two separate products. It should present the season's football calendar, then route completed fixtures to post-match analysis and upcoming fixtures to opposition analysis.

### League Map Entry

When the user lands on the league coverage map, they should be able to:

- select a league from the existing map/chip interface
- choose a season, including `2026_2027`
- see a unified fixture schedule for that league/season
- quickly distinguish completed matches from upcoming matches
- open completed matches in Post Match Analysis
- open upcoming matches in Opposition Analysis

### Season Filter

The league fixtures page should add a prominent season selector before the map/list view.

Expected behavior:

- default to the latest available season
- include `2026/27` once the schedule is available
- preserve selected season in the URL
- refresh league table, completed fixtures, upcoming fixtures, and round/matchday navigation when the season changes
- show clear empty states when a season has schedule data but no event data yet

Suggested URL shape:

```text
/matches/{league}?season=2026_2027
/matches/{league}/{roundId}?season=2026_2027
```

The current links that use `/matches/{league}/latest` can remain as shortcuts, but the destination should resolve to the selected/latest season-aware fixture hub.

### Unified Fixture States

The fixture map and rail should support two fixture states.

Completed fixtures:

- source: R2 event parquet / completed match archive
- primary action: `Open match analysis`
- destination: `/analysis/{matchId}?source=r2&filePath=...`
- display: final score, completed badge, post-match analysis affordance

Upcoming fixtures:

- source: FootballData schedule
- primary action: `Analyse opposition`
- destination: `/opposition-analysis?league={league}&season={season}&home={homeTeam}&away={awayTeam}&fixtureId={fixtureId}`
- display: kickoff date/time, venue if available, upcoming badge, opposition analysis affordance

For upcoming fixtures, the opposition page should know both teams. The user should be able to scout either side:

- home team's view of the away opponent
- away team's view of the home opponent
- neutral analyst view where a user selects a reference team/style and studies how the opponent performs against similar profiles
- optional comparison mode once the matchup-specific report exists

### Fixture Hub Layout

The first version should adapt the current `MatchdayExplorer` pattern rather than building a new browsing surface from scratch.

Expected layout:

- top season selector
- league context header
- segmented control: `All`, `Completed`, `Upcoming`
- map of fixtures by home stadium
- right rail grouped by matchday/date
- fixture cards with clear state-specific actions
- league table panel using the selected season
- low-data banner for seasons where schedule exists but post-match event data has not been scraped yet

### Opposition Analysis Entry From Upcoming Fixture

When a user clicks an upcoming fixture, the opposition report should open with matchup context at the top.

Expected content:

- fixture date/time
- home and away teams
- selected reference context: `Reference: {team}` / `Scout: {opponent}`
- opponent's relevant-match sample
- note if the upcoming season has no completed matches yet and the report is using previous-season data

Fallback rule:

- if `2026_2027` schedule exists but there are not enough completed matches in that season, default the analytical sample to the previous completed season while keeping the fixture context as `2026_2027`.
- the default sample should not be a plain "last 10" when a reference team is available. It should prioritize how the opponent played against teams with a similar style profile to the selected reference team, then fall back to recent matches when the similar-team sample is too small.
- show this clearly in the report metadata.

## Target Report Shape

### 1. Executive Summary

High-signal first screen for the selected opponent.

Expected content:

- opponent, league, season, recent form, home/away context
- 4-6 tactical insight bullets
- strengths and weaknesses
- key risk players
- recommended attacking and defensive approach
- report freshness and sample size

### 2. Team Profile

League and style context.

Expected content:

- league table context
- recent xG/xGA form
- possession share
- directness
- PPDA / pressing intensity
- field tilt
- territory entries
- transition threat
- set-piece reliance
- percentile comparison against league

### 3. Recent Form

Opponent trajectory over the last 5-10 matches.

Expected content:

- result strip
- goals for/against
- xG/xGA trend
- shot volume and shot quality trend
- home/away split
- trend notes for improving/declining metrics

### 4. In Possession

How the opponent builds, progresses, and creates.

Expected content:

- build-up shape
- pass network tendencies
- main progression routes
- final-third entries
- box entries
- half-space use
- top pass pairs / hubs
- top creators
- "how to stop them" tactical notes

### 5. Chance Creation and Shooting

Where their threat comes from.

Expected content:

- shot map over selected sample
- xG by zone/type
- big chances
- open-play vs set-piece threat
- cutbacks, crosses, through balls, carries into box
- top shooters
- top shot creators
- "protect these zones" callout

### 6. Out of Possession

How the opponent defends and where they can be attacked.

Expected content:

- pressing profile
- defensive action map
- PPDA by thirds
- final-third entries conceded
- box entries conceded
- half-space receptions conceded
- shots conceded by zone
- transition vulnerability after losing possession
- "where to attack them" callout

### 7. Transitions

How they behave immediately after regains and losses.

Expected content:

- recoveries leading to shots
- counterattack frequency
- turnover locations
- xT/xG after regains
- shots conceded after turnovers
- players who drive counters
- rest-defence risk notes

### 8. Set Pieces

Attacking and defending set-piece profile.

Expected content:

- corner takers and targets
- delivery zones
- inswinger/outwinger tendencies
- shots/goals from corners
- attacking free-kick profile
- throw-in and goal-kick patterns
- set-piece shots conceded
- defensive set-piece weaknesses

### 9. Key Players

Role-based player threat board.

Expected content:

- primary scorer
- primary creator
- progression hub
- ball-winner
- aerial threat
- set-piece taker
- player cards with minutes, starts, goals, xG, xA, xT, shots, SCA, progressive actions, defensive actions

### 10. Likely XI and Shape

Expected lineup and structural tendencies.

Expected content:

- most recent XI
- most common XI
- most-used formations
- formation frequency
- player starts by position
- substitutions by minute/player
- formation changes
- likely XI confidence score

### 11. Head-to-Head and Comparable Matchups

Context from relevant previous games.

Expected content:

- recent head-to-head results if available
- opponent results against teams similar to the selected reference team
- performance against high press, low block, possession-heavy, and direct teams
- tactical lessons from comparable fixtures

### 12. Action Plan

Final tactical recommendations.

Expected content:

- attacking recommendations
- defensive recommendations
- key matchups
- set-piece instructions
- risk flags
- short "analyst notes" summary that can be exported/shared

## Data Requirements

### Already Available or Partially Available

- R2 event parquet files by league/season/match
- fixture manifests and parsed fixture metadata
- match-level analysis builders for shots, pass networks, entries, defensive actions, duels/transitions, set pieces, lineups, and player analysis
- season team stats
- season player stats
- team form strip endpoint
- league table endpoint
- player images
- deterministic insight generation patterns
- FootballData standings provider and top-five league code mapping

### New or Expanded Data Needed

- team-match index: all matches for a selected team in a league/season
- multi-match event loader for the selected opponent
- recent N match sample selector
- home/away splits
- game-state splits
- opponent-conceded aggregates
- season-level lineup and formation history
- player role aggregation across matches
- set-piece attacking and defending aggregates
- transition aggregates across matches
- comparable-match tagging or clustering
- team style profiles for similarity matching
- reference-team style vector for fixture-driven reports
- opponent match samples against similar teams
- FootballData fixture/schedule ingestion for upcoming matches
- persisted or cached schedule records for `2026_2027`
- fixture state classification: completed, upcoming, postponed, cancelled, live if later supported
- provider-to-local team-name mapping for scheduled fixtures
- matchday/round grouping for provider fixtures
- optional external availability data: injuries, suspensions, transfers, current squad status

### FootballData Schedule Requirements

The current FootballData integration should be expanded from standings to fixtures.

Provider details:

- top-five league codes already exist in `apps/api/app/services/standings.py`
- app season key: `2026_2027`
- FootballData season query year: `2026`
- initial source: FootballData competition matches endpoint
- first target leagues: Premier League, LaLiga, Bundesliga, Serie A, Ligue 1

Needed API behavior:

- fetch scheduled matches for a league/season
- normalize provider team names to local PlayBack90 names
- expose kickoff time, UTC date, home team, away team, matchday, status, provider fixture id, and venue if available
- merge upcoming provider fixtures with completed R2 fixtures
- prefer R2 completed fixture data when a provider fixture has already been scraped
- cache provider schedules to avoid repeated external calls
- expose warning metadata when provider schedule data is stale or unavailable

Verified availability on 2026-07-27:

- Premier League `2026`: 380 scheduled matches, first match 2026-08-21, last match 2027-05-30.
- LaLiga `2026`: 380 scheduled matches, first match 2026-08-15, last match 2027-05-30.
- Bundesliga `2026`: 306 scheduled matches, first match 2026-08-28, last match 2027-05-22.
- Serie A `2026`: 380 scheduled matches, first match 2026-08-22, last match 2027-05-30.
- Ligue 1 `2026`: 306 scheduled matches, first match 2026-08-22, last match 2027-05-29.

All returned matches were `SCHEDULED` at verification time.

## API Direction

The existing `opposition.py` service should evolve into a dossier builder.

Fixture hub endpoint direction:

```text
GET /api/leagues/{league}/seasons/{season}/fixture-hub
```

Suggested fixture hub query params:

```text
state=all|completed|upcoming
round={round_id}
```

Suggested fixture item shape:

```json
{
  "fixture_id": "provider-or-r2-id",
  "match_id": "1903350",
  "state": "completed",
  "source": "r2",
  "league": "premier-league",
  "season": "2026_2027",
  "round": "matchday-1",
  "matchday": 1,
  "start_date": "2026-08-15T14:00:00Z",
  "home_team": "Arsenal",
  "away_team": "Chelsea",
  "score": "2-1",
  "file_path": "playback90/event_data/...",
  "post_match_href": "/analysis/...",
  "opposition_href": "/opposition-analysis?..."
}
```

Target endpoint shape:

```text
GET /api/leagues/{league}/seasons/{season}/opposition/{team}/dossier
```

Suggested query params:

```text
sample=last_5|last_10|season
sampleMode=similar_opponents|recent|season
homeAway=all|home|away
asOfMatchId={match_id}
comparisonTeam={team}
fixtureId={fixture_id}
referenceTeam={team}
opponentTeam={team}
```

Suggested top-level payload:

```json
{
  "meta": {},
  "fixtureContext": {},
  "sampleContext": {},
  "referenceProfile": {},
  "summary": {},
  "teamProfile": {},
  "recentForm": {},
  "inPossession": {},
  "chanceCreation": {},
  "outOfPossession": {},
  "transitions": {},
  "setPieces": {},
  "keyPlayers": {},
  "lineups": {},
  "headToHead": {},
  "actionPlan": {}
}
```

## Phase Checklist

### Phase 0 - Product Definition, UX Flow, and Baseline Audit

- [x] Confirm the primary user story: neutral opposition analyst / individual user exploring upcoming fixtures and team profiles.
- [x] Confirm the first report entry point: league map / fixture hub with completed and upcoming matches.
- [x] Define the completed-fixture path into Post Match Analysis.
- [x] Define the upcoming-fixture path into Opposition Analysis.
- [x] Define the fixture card states: completed, upcoming, postponed, cancelled, low-data.
- [x] Define the season selector UX and URL behavior.
- [x] Confirm `2026_2027` as the first upcoming-season schedule target.
- [x] Audit current `opposition.py` metrics and remove placeholder assumptions.
- [x] Define the MVP dossier payload contract.
- [x] Define empty/loading/error states for missing season data.
- [x] Decide default sample window: similar-opponent sample first, previous-season last 10 fallback for early `2026_2027`, then blend current season once 4+ matches exist.
- [x] Decide whether the report is opponent-only or "opponent vs our team" from day one.

#### Phase 0 Working Decisions

These are the current recommended decisions before implementation starts.

- Use the existing `/matches/[league]/[season]` route as the first unified fixture hub instead of creating a separate map experience.
- Keep `/matches/{league}/latest` as a shortcut, but resolve it to the latest season available from either completed R2 data or provider schedule data.
- Extend the current season list behavior so schedule-only seasons such as `2026_2027` can appear even before R2 event files exist.
- Keep completed fixture analysis and upcoming fixture scouting in one fixture rail/map because the user is thinking in calendar terms, not product modules.
- Use `completed` and `upcoming` as the primary fixture states for the MVP. Add `postponed`, `cancelled`, and `unknown` in the data model now, but do not over-design their UI.
- For upcoming fixtures, route to Opposition Analysis with both teams and a selected reference context. The default can use the home team as the reference and the away team as the opponent, but the UI must not imply the user works for that club.
- The fixture hub should default to all matches in the next upcoming round/matchday, matching the existing completed-round browsing mental model.
- If the selected upcoming season has too few completed matches, use previous-season event data for the analytical sample and show the sample season clearly in the report metadata.
- The default analytical sample should be opponent matches against teams similar to the selected reference team. Use previous-season last 10 only as the early-season fallback when the similar-opponent sample is too small.
- Once `2026_2027` has at least 4 completed matches for the opponent, blend current-season matches into the sample and label the blend clearly.
- A confident similar-opponent read requires at least 5 comparable matches.
- MVP similarity uses three families: style, chance profile, and defensive vulnerability.
- Keep the current standalone `/opposition-analysis` page available as a direct team-scouting fallback, but make fixture-driven entry the primary path.

#### Phase 0 Current-State Audit

Relevant current implementation details:

- `apps/web/components/LeagueCoverageMap.tsx` sends league selections to `/matches/{league}/latest`.
- `apps/web/app/matches/[league]/[season]/page.tsx` already has a season switcher, round navigation, `MatchdayExplorer`, and league table panel.
- `apps/web/components/MatchdayExplorer.tsx` currently assumes every fixture is completed and links to Post Match Analysis.
- `apps/api/app/services/r2.py` derives available seasons only from R2 `event_data/{league}/{season}` folders.
- `apps/api/app/services/fixture_rounds.py` builds round/matchday groups from completed R2 fixtures or optional `rounds.json`.
- `apps/api/app/services/standings.py` already contains FootballData top-five league code mapping and season-year parsing.
- `apps/web/app/opposition-analysis/page.tsx` exists, but it currently behaves like a standalone team report rather than a fixture-driven dossier.
- `apps/web/app/layout.tsx` keeps top navigation intentionally minimal: Home and Import Match only. Opposition Analysis should be reached through the fixture hub.

Implications:

- Schedule-only seasons will need to be merged into season discovery before `2026_2027` can appear in the current season selector.
- The fixture model should become state-aware before the frontend can safely show both completed and upcoming matches in the same map/list.
- `MatchdayExplorer` should accept state-specific actions instead of hardcoding Post Match Analysis links.
- The first implementation can reuse most of the existing fixture page layout and avoid a large frontend rewrite.

#### Phase 0 UX Questions

These decisions should be confirmed before Phase 1 and Phase 2 implementation.

- [x] Upcoming fixture cards should open directly into the default home-reference scouting view.
- [ ] Should the fixture hub show only the next upcoming round by default, or next upcoming round plus a small "recently completed" strip above it?
- [x] Minimum similar-opponent sample for a confident report is 5 matches.
- [x] MVP team similarity should include style, chance profile, and defensive vulnerability.
- Should upcoming schedule ingestion be limited to the top five leagues initially, matching FootballData support, or should unsupported leagues still show a manual/import-first empty state?

#### Phase 0 Data Analyst Optimizations

These should guide the MVP so the report is credible and not just visually busy.

- Always show sample size, sample date range, sample season, and source coverage in the report header.
- Separate fixture context from analysis context. Example: fixture is `Premier League 2026/27`, but analysis sample may be `Premier League 2025/26 last 10`.
- Prefer similar-opponent samples for matchup-specific reads, recent weighted metrics for form labels, and full-season context for stability.
- Build team similarity from style, chance profile, and defensive vulnerability rather than table rank.
- MVP style metrics: possession share, directness, PPDA, field tilt, final-third entries, box entries, transition share, and set-piece reliance.
- MVP chance-profile metrics: shots, xG, xG per shot, big chances, box shots, set-piece shot share, and transition shot share.
- MVP defensive-vulnerability metrics: xGA, shots conceded, box entries conceded, final-third entries conceded, half-space receptions conceded, set-piece xGA/shot concessions where available.
- If similar-opponent sample size is low, widen the similarity threshold before falling back to generic recent matches.
- Use low-sample gates before making strong tactical claims. A practical first rule: fewer than 5 similar-opponent matches means fallback/descriptive language; 5-9 matches means moderate confidence; 10+ matches can support stronger trend labels.
- Avoid raw count comparisons without per-match or per-90 normalization.
- Split "what the opponent creates" from "what the opponent concedes" in every relevant section.
- Track home/away because opposition behavior can change materially by venue.
- Keep provider team mapping auditable by returning both local and provider team names in debug/test payloads.
- Cache schedule data separately from event-data analysis so a provider outage does not break completed post-match browsing.
- Build deterministic recommendation bullets from transparent metric rules first, then add AI wording later only as a layer on top.

### Phase 1 - Schedule Data and Fixture Hub Foundation

- [x] Add a FootballData fixtures provider alongside the standings provider.
- [x] Add provider support for `2026_2027` using FootballData season year `2026`.
- [x] Normalize FootballData fixture payloads into PlayBack90 fixture records.
- [x] Map provider team names to local team names.
- [x] Add schedule caching with stale-data metadata.
- [x] Merge upcoming provider fixtures with completed R2 fixtures.
- [x] Mark each fixture as `completed`, `upcoming`, `postponed`, `cancelled`, or `unknown`.
- [x] Build matchday/round grouping for provider schedules.
- [x] Add `/fixture-hub` endpoint for season-aware completed + upcoming fixture browsing.
- [x] Add tests for provider season-year parsing, team-name matching, and fixture-state merging.

Phase 1 implementation notes:

- New backend service: `apps/api/app/services/schedules.py`.
- New API endpoint: `/api/leagues/{league}/seasons/{season}/fixture-hub`.
- `GET /api/leagues/{league}/seasons` now merges R2 completed seasons with provider schedule seasons.
- Frontend API helper/type added: `getFixtureHub()` in `apps/web/lib/api.ts`.
- Real-provider smoke test on 2026-07-27: Premier League `2026_2027` returned 380 upcoming fixtures, selected `matchday-1`, with 10 fixtures in the selected round.
- Promoted/new teams are preserved with provider names when no local PlayBack90 mapping exists yet.
- Schedule cache hardening added after a local provider TLS/certificate failure: successful FootballData fixture responses are persisted to `apps/api/.cache/schedules` by default, and fixture hub falls back to the saved schedule with `is_stale: true` when the provider is unavailable.
- `FOOTBALL_DATA_SCHEDULE_CACHE_DIR` can override the persisted cache path for deployment environments.
- Focused cache validation: `apps/api/tests/test_schedules.py` covers provider failure fallback from the persisted schedule cache.

### Phase 2 - League Map and Fixture Hub Frontend

- [x] Add season selector to the league/map fixture browsing page.
- [x] Include `2026/27` as a selectable season when schedule data exists.
- [x] Add segmented control for `All`, `Completed`, and `Upcoming`.
- [x] Update the map markers to visually distinguish completed and upcoming fixtures.
- [x] Update the fixture rail to group by matchday/date.
- [x] Add completed fixture action: `Open match analysis`.
- [x] Add upcoming fixture action: `Analyse opposition`.
- [x] Route completed fixtures to `/analysis/{matchId}` with R2 `filePath`.
- [x] Route upcoming fixtures to `/opposition-analysis` with fixture, home, away, season, and perspective context.
- [x] Add low-data banner for seasons with schedule data but limited/no event data.
- [x] Validate the hub against at least one 2026/27 FootballData league schedule.

Phase 2 implementation notes:

- `apps/web/app/matches/[league]/[season]/page.tsx` now consumes `getFixtureHub()` instead of separate completed-only round endpoints.
- `MatchdayExplorer` and `CountryFixturesMap` are state-aware and use `fixture_id` for selection.
- Completed fixtures link to Post Match Analysis; upcoming fixtures link to the Opposition Analysis route shell.
- The fixture hub defaults to the next upcoming matchday when a schedule-only season is selected.
- Premier League `2026_2027` smoke test returned `matchday-1`, 380 upcoming fixtures total, and 10 fixtures in the selected round.

### Phase 3 - Opposition Data Foundation

- [x] Build a team-match index for each league/season.
- [x] Add a service that returns all R2 file paths for a selected team.
- [x] Build team style profiles for similarity matching.
- [x] Add reference-team style vector support.
- [x] Add similar-opponent match sampling for the selected opponent.
- [ ] Add fallback sample filtering: last 5, last 10, season, home, away.
- [ ] Add multi-match event loading with caching.
- [x] Normalize match metadata in the foundation response.
- [x] Track sample size and missing-data warnings.
- [x] Add tests for fixture/team matching, style similarity, and sample selection.

Phase 3 implementation notes:

- New backend service: `apps/api/app/services/opposition_foundation.py`.
- New API endpoint: `/api/leagues/{league}/seasons/{season}/opposition/{opponent_team}/foundation`.
- The foundation endpoint accepts `reference_team` and `sample_size`, defaults to a 5-match comparable sample, and returns `similar_teams`, `sample_matches`, `features_used`, warning metadata, and the opponent team-match index.
- Early upcoming-season logic is implemented: if the opponent has fewer than 4 completed rows in the selected season, analysis falls back to the previous season; once 4+ current-season rows exist, the pool blends current and previous seasons.
- Similarity MVP uses available `team_match_stats` columns across style, chance profile, and defensive vulnerability: possession, pass accuracy, PPDA, field tilt, box entries, long balls, through balls, crosses, shots, xG, xG/shot, big chances, xGA, shots against, big chances against, and goals against.
- Comparable-match sampling includes the actual reference team when historical meetings exist, then extends to stylistic peers. If the comparable sample is below the target size, recent opponent matches are appended and a low-sample warning is returned.
- Focused backend validation: `apps/api/tests/test_opposition_foundation.py` covers available-column profile creation, peer ranking, comparable-match sampling, recent fallback warnings, and the API route contract.

### Phase 4 - MVP Dossier API

- [x] Add `/opposition/{team}/dossier` endpoint.
- [x] Accept fixture context: `fixtureId`, `referenceTeam`, `opponentTeam`.
- [x] Return `meta`, `fixtureContext`, `sampleContext`, `referenceProfile`, `summary`, `teamProfile`, `recentForm`, `strengths`, and `weaknesses`.
- [x] Reuse season team/player stats for first-pass percentiles.
- [x] Add recent form with xG, xGA, goals for, goals against, and results.
- [x] Add key players by goals, xG, xA, shots, and minutes.
- [x] Add similar-opponent sample metadata and fallback metadata when `2026_2027` schedule exists but analysis uses previous-season completed matches.
- [x] Replace current static image assets with structured chart-ready JSON where practical.
- [x] Keep existing `/report` endpoint temporarily for backwards compatibility.
- [x] Add API tests for a known R2-backed fixture/team.

Phase 4 implementation notes:

- New backend service: `apps/api/app/services/opposition_dossier.py`.
- New API endpoint: `/api/leagues/{league}/seasons/{season}/opposition/{opponent_team}/dossier`.
- The dossier endpoint accepts fixture-route query params: `referenceTeam`, `fixtureId`, `home`, `away`, and `sampleSize`.
- The MVP dossier returns structured JSON sections for `meta`, `fixtureContext`, `sampleContext`, `referenceProfile`, `summary`, `teamProfile`, `recentForm`, `strengths`, `weaknesses`, and `keyPlayers`.
- Strengths and weaknesses are generated only from evaluative metrics. Neutral style descriptors such as long-ball volume still appear in Team Profile but are not framed as good/bad by default.
- The existing `/report` and PNG asset endpoints remain available while the frontend migrates to the dossier payload.
- Focused backend validation: `apps/api/tests/test_opposition_dossier.py` covers dossier section assembly and the route contract.

### Phase 5 - Frontend MVP Report

- [x] Rework `/opposition-analysis` into a dossier interface.
- [x] Add matchup header when opened from an upcoming fixture.
- [x] Add reference selector: use home team or away team as the style reference.
- [x] Add filters for league, season, team/opponent, sample window, and home/away.
- [x] Build Executive Summary section.
- [x] Build Team Profile section.
- [x] Build Recent Form section.
- [x] Build Strengths and Weaknesses section.
- [x] Build Key Players section.
- [x] Add share/export support for the summary view.
- [x] Add responsive mobile layout.
- [x] Validate with a real Premier League team and at least one non-PL league.
- [x] Rework the page shell into a tabbed report layout matching Post Match Analysis navigation.
- [x] Make `Overview` the first tab and keep the above MVP sections there.
- [x] Add tab URL state with `view=overview|in-possession|out-of-possession|players|action-plan`.
- [x] Add disabled/empty tab states for sections whose backend data is not implemented yet.
- [x] Keep the fixture/reference/sample controls outside the tabs so they apply to the full report.
- [ ] Add a report-level export action and later allow section-specific exports from each tab.

Phase 5 implementation notes:

- `/opposition-analysis` now calls the MVP dossier endpoint and renders a fixture-aware report instead of a placeholder shell.
- Frontend API helper added: `getOppositionDossier()` in `apps/web/lib/api.ts`, with typed dossier, sample-match, metric, recent-form, and key-player structures.
- The first report page includes matchup context, reference/opponent labels, sample confidence, executive bullets, sample metadata, strengths/vulnerabilities, grouped team-profile metrics, recent form, comparable matches, style peers, and key players.
- The page has missing-context and dossier-load error states, so direct URLs without required fixture context fail gracefully.
- CSS was added for the report layout and responsive collapse. Desktop visual QA passed with Chrome headless; mobile CSS was hardened after a narrow-width screenshot showed potential overflow in report text rows.
- The second Phase 5 pass added URL-driven reference switching between home and away teams, sample-size controls for 3/5/10 matches, copy-link support, and summary PNG export using the existing branded share component.
- Validation smoke passed for Premier League and LaLiga `2026_2027` dossier URLs.
- The tab-shell pass added Post Match Analysis-style report tabs, `view` URL state, an `Overview` tab containing the current MVP report, and planned-section empty states for future data tabs.
- The visible tab model was simplified after review: chance creation and attacking set pieces live under `In Possession`; transitions and defensive transition vulnerability live under `Out Of Possession`.

#### Phase 5 Tabbed Page Plan

The first Opposition Analysis page should use the same mental model as Post Match Analysis: one report header, one horizontal tab bar, and a single active section below it. The user should never feel they entered a separate tool from the fixture hub.

Recommended tab order:

- `Overview`: matchup header, report confidence, sample context, executive summary, strengths, vulnerabilities, recent form, comparable matches, style peers, and key players.
- `In Possession`: pass network, buildup routes, progression channels, final-third entries, box entries, chance creation, shot map, shot quality, top creators, top shooters, attacking set pieces, and how to slow their attack.
- `Out Of Possession`: press profile, defensive action map, territory conceded, entries conceded, shots conceded, transition vulnerability, turnover locations, defensive set pieces, and where to attack them.
- `Players`: key-player board, role labels, player contribution cards, minutes/starts, and future availability hooks.
- `Action Plan`: attacking plan, defensive plan, key matchups, set-piece instructions, risk flags, and analyst notes.

First-page layout:

- Top context band: `Opposition Analysis`, fixture date, home vs away, competition/season, and schedule freshness if the fixture hub is using stale provider data.
- Control row: reference toggle, opponent label, sample size selector, sample-season/source badge, copy/share/export actions.
- Tab bar: identical behavior to post-match tabs, preserving fixture/team/sample query params when switching tabs.
- Overview body: compact executive read first, then two-column tactical cards on desktop and a single scan-friendly column on mobile.
- Low-data state: keep tabs visible, but show an honest empty state inside tabs whose backend section is not ready or whose sample is too small.

Implementation sequence for the tab pass:

- Add a `view` search param to `/opposition-analysis`, defaulting to `overview`.
- Define an `OPPOSITION_VIEWS` array in the page similar to Post Match Analysis `VIEWS`.
- Extract the current report body into an `Overview` section component.
- Add placeholder-safe tab containers for future phases, with copy that describes missing data without overpromising.
- Add CSS that reuses existing `.tab-bar` and `.tab-link` patterns where practical, then add only opposition-specific layout rules where needed.
- Validate desktop and mobile screenshots for the tab shell before Phase 6 chart work begins.

### Phase 6 - In-Possession and Chance Creation

- [ ] Aggregate pass network over the selected sample.
- [ ] Aggregate progression routes and channel/zone xT.
- [ ] Aggregate final-third and box entries.
- [ ] Aggregate shot map and shot quality.
- [ ] Add top creators and top shooters.
- [ ] Add tactical notes for how to stop the opponent's attack.
- [ ] Reuse existing visual components where possible.
- [ ] Add export support for attack visuals.

### Phase 7 - Out-of-Possession and Vulnerability

- [ ] Aggregate defensive actions across selected sample.
- [ ] Aggregate PPDA by third.
- [ ] Aggregate final-third entries conceded.
- [ ] Aggregate box entries conceded.
- [ ] Aggregate half-space receptions conceded.
- [ ] Aggregate shots conceded by zone/type.
- [ ] Add tactical notes for where to attack the opponent.
- [ ] Add export support for defensive vulnerability visuals.

### Phase 8 - Transitions and Set Pieces

- [ ] Aggregate counterattacks and regain-to-shot sequences.
- [ ] Aggregate turnovers and shots conceded after turnovers.
- [ ] Add transition threat and transition vulnerability cards.
- [ ] Aggregate attacking corners, free kicks, throw-ins, and goal kicks.
- [ ] Aggregate set-piece shots/goals for and against.
- [ ] Add corner takers, targets, delivery zones, and swing tendencies.
- [ ] Add set-piece defensive weakness notes.
- [ ] Add export support for transition and set-piece sections.

### Phase 9 - Lineups, Shape, and Player Roles

- [ ] Aggregate formation usage across matches.
- [ ] Aggregate recent XI and most common XI.
- [ ] Calculate player starts by position.
- [ ] Calculate substitution patterns.
- [ ] Add likely XI model or rules-based confidence score.
- [ ] Add role labels for key players.
- [ ] Add player cards with role-specific metrics.
- [ ] Add player availability hooks for future external data.

### Phase 10 - Action Plan and Analyst Notes

- [ ] Generate deterministic tactical recommendation bullets.
- [ ] Add attacking plan recommendations.
- [ ] Add defensive plan recommendations.
- [ ] Add key matchup notes.
- [ ] Add set-piece instructions.
- [ ] Add risk flags.
- [ ] Add optional AI deep-dive mode only after deterministic notes are reliable.
- [ ] Add PDF/report export once the interactive dossier is stable.

### Phase 11 - Comparable Matchups and Advanced Context

- [ ] Tag teams by style profile.
- [ ] Find opponent matches against similar styles.
- [ ] Compare opponent output by matchup type.
- [ ] Add home/away and game-state style changes.
- [ ] Add rest-days and schedule congestion if fixture data supports it.
- [ ] Add injuries/suspensions if an external source is chosen.
- [ ] Add opponent-vs-our-team matchup-specific recommendations.

### Phase 12 - Hardening and Beta Readiness

- [ ] Add caching for multi-match dossier responses.
- [ ] Add performance budget for loading and rendering the report.
- [ ] Add analytics events for report views, filters, exports, and section usage.
- [ ] Add error monitoring around data loading and report generation.
- [ ] Add empty states for low-sample teams.
- [ ] Add private-beta feedback prompt on the dossier page.
- [ ] Document known data limitations.
- [ ] Add regression tests around the dossier contract.

## MVP Definition

The first useful release should include:

- fixture-driven Opposition Analysis route shell
- league/season/team/sample filters
- fixture-driven reference team/opponent context
- similar-opponent sample selection
- executive summary
- style fingerprint
- strengths and weaknesses
- recent form
- key players
- basic attack profile
- basic defensive vulnerability profile
- structured API payload
- working low-sample states

This MVP should avoid external injury/suspension data and advanced comparable-match clustering. Basic style similarity should be part of the core dossier because it makes the opposition profile more useful than a generic recent-form report.

## Implementation Notes

- Prefer structured JSON payloads over PNG-only generated assets.
- Reuse existing match-analysis builders wherever possible.
- Keep multi-match aggregation in the API layer, not the frontend.
- Include sample metadata in every section so users can trust the report.
- Treat "what they do" and "what opponents do against them" as separate concepts.
- Avoid hiding low sample sizes behind confident tactical language.
- Keep the old simple report endpoint until the new dossier UI is ready.
