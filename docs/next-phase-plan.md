# Next-phase plan: leagues, season analysis, security, payments, social, dashboard

Written 2026-10-29. Builds on `dribble360-handoff.md`, `dribble360-licence.md`, `competition-expansion-plan.md` and
`deployment-handoff.md`. Nothing here is built yet; tick items off and add dates as they land.

## Decisions (2026-10-29)

| # | Question | Answer |
|---|---|---|
| 1 | Seller location, data cost | India. Dribble Pro is **$149/month** |
| 2 | Free tier | **3 full match analyses per month**. Season analysis is **not** in the free tier |
| 3 | Where the weekly sync runs | **Manually from this laptop** for now |
| 4 | League scope | No qualifying rounds. Every other competition Dribble offers (Conference League included; see section 2) |
| 5 | Social posting | **Manual** for now (generate, review, post by hand) |
| 6 | Cups | **Include the cups listed** (League Cup, DFB Pokal, Coppa Italia, Copa del Rey, super cups; FA Cup, EFL Trophy and Taça de Portugal were not confirmed, so they stay out until asked) |
| 7 | Payment provider | **Razorpay** (not a Merchant of Record: see section 4) |
| 8 | Dribble credit in social posts | **Posts do not mention Dribble** (the in-app footer and PDF credit stay) |
| 9 | Manual-sync risk, fixed-cost figures | **Optimise later** |

## Licence constraints that shape everything

- Paid subscriber access to visuals and derived metrics is covered (Pro plan, confirmed in writing 2026-10-28).
- No raw data out: no CSV/JSON/row export, no API or feed of the data, no event rows in PDFs. Do not build a "Pro API" tier.
- Credit is "Data by Dribble (dribble360.com)". No Dribble logo, never name Opta.
- Public X posts of visuals are not explicitly covered by the licence record. Decision 8: posts do not mention Dribble.
  Never name Opta or use the Dribble logo. Posting is outward-facing: confirm each batch before it goes out. A short
  email to Dribble (first person, "I") confirming public posting of visuals is still the safe route; not sent.
- Dribble can change price with 30 days' notice. Keep margin.

## Order of work

| Step | Work | Notes |
|---|---|---|
| 0 | Foundations (started 2026-10-29, see section 8) | Backup of `Data/playback90.db` (hardening item 5); CI green (git push is blocked for this login); Sentry DSN; retry a larger Lightsail size (1 GB box also runs Firefox for PNGs); enable AWS Cost Explorer |
| 1 | Phase 2 leagues, season analysis, social routine (manual) | What users pay for and what brings them in |
| 2 | Security hardening, legal pages, admin paperwork | Start the provider KYC and legal paperwork now, in parallel: it has lead time |
| 3 | Paywall as a beta with existing users | Needs steps 0 to 2 |
| 4 | Dashboard | v0 (uptime, costs, data freshness) early; full version after launch |

Sync stays manual from this laptop. Risk: it is a single point of failure for data freshness once users pay. Revisit
(scheduled job on a larger host) after launch; it needs enough memory for the 12 GB-scan events pull.

## 1. Season analysis (paid feature)

Pre-render, do not port to web charts.

- A step after each sync runs the `social-media/pb90` visuals per competition and uploads PNGs to R2:
  `season_visuals/{league}/{season}/{name}.png` plus a `manifest.json` (title, group, description, updated-at).
- New Season page in the web app: a gallery with group filters (the groups in `social-media/PLOTS.md`: Team scatter,
  Pitch maps, Player scatter, Tables ...), served through the API with a subscription check. Images only, no data.
- Why: no server compute on the small box, identical to the social content, and images are the safest form under
  the licence.
- First batch (about 12 league-level visuals): xPoints table, PPDA scatters, team directness, xG by game state,
  xG home vs away, open play vs set piece, turnover and SCA maps, player leaderboards, over/under performers.
- Second batch: per-club visuals (team vs league pizza, team shot map, pass network, rolling xG, final-third entries).
- Port only the two or three most used to interactive charts later.
- Every image carries "playback90.com · Data by Dribble (dribble360.com)".
- Needs: `pb90` league slugs extended past the six it knows (competition registry), and a check that `pb90` reads the
  same data the app serves.

## 2. More competitions

Follow `competition-expansion-plan.md`. Scope per decision 4:

- Phase 2: Eredivisie, Primeira Liga, Süper Lig, Belgian First Division A, Saudi League, Brazil Série A (about 745 matches).
- Conference League (294 matches, 160 clubs needing ids): in scope.
- Phase 3 cups (confirmed in scope): League Cup, DFB Pokal, Coppa Italia, Copa del Rey, super cups. Needs the cup rules first (penalties
  label on the match page, stage labels, no league table, extra-time test on a real match).
- Qualifying rounds: excluded. Rule: league phase onward for UEFA, proper rounds only for domestic cups.
- Not confirmed: FA Cup, EFL Trophy and Taça de Portugal (skipped for qualifying rounds and 699 clubs). Out unless asked.
- Schedules for leagues not on football-data: vendor `matches` table (date only).
- Cost: BigQuery is flat (about 12.3 GB per pull); R2 stays under 2 GB for everything.

## 3. Security

Scraping cannot be made impossible; make it expensive and detectable. Already in place: Clerk login wall, per-user
rate limit (240/min, 4,000/h), `/terms` forbids scraping.

1. Send less data: aggregate server-side, drop endpoints that return more rows than a chart needs (open item in the
   licence doc), no enumeration or list endpoints for raw rows.
2. Stop mass sign-ups: Cloudflare Turnstile on sign-up, required email verification, disposable-email blocklist,
   sign-ups per IP limit.
3. Daily cap on distinct matches per account, with an alert on unusual patterns (per-minute limits miss slow scraping).
4. Cloudflare edge: Bot Fight Mode, WAF rate-limit rules.
5. Close the origin: Lightsail firewall to Cloudflare IP ranges only (known gap, hardening item 3); restrict SSH source.
6. Account sharing: Clerk session/device limits on paid accounts.
7. Terms: clause allowing suspension without refund for scraping or sharing; log per-user match access.
8. Hygiene: security headers and CSP, Dependabot and `pip-audit`, scoped R2 tokens, key rotation, verified payment
   webhooks, account-deletion flow, cookie-consent banner for PostHog, review `_auth_is_ready()` quirk.

### Legal pages and footer (benchmark: fbplot.com)

Exist: `/privacy`, `/terms`, footer with data credit. Add: pricing and subscription terms, refund and cancellation
policy, cookies, acceptable use (no scraping, no resale), contact/support, about and data sources, status link.
Have a lawyer read the lot before charging. Open points already in the licence doc: refund wording, liability cap,
governing law (India).

## 4. Payments

### Tiers

| Tier | Contents |
|---|---|
| Free | League tables and match summaries, **3 full match analyses per month**, watermarked PNGs, no season analysis |
| Pro | Unlimited matches, full Season page, all competitions, unwatermarked PNGs, PDF quota (about 20/month) |
| Later (optional) | Creator/Club: higher PDF quota, commercial use of visuals with credit |

Gate by value, not by match count alone: the 3-match allowance is the free hook, season analysis is the paid anchor.
Count a "match" as a distinct match opened in full analysis (re-opening the same match is free). Existing users
(about 100): grandfather or discount during a beta.

### Break-even (Dribble Pro $149/month)

Assumed fixed costs about **$190/month**: $149 Dribble + about $40 for a larger server, snapshots, domain and tools
(replace with real figures once known). Provider fee assumed about 5% + $0.50 per charge (typical for a Merchant of
Record; verify with the chosen provider).

| Pro price/month | Net per subscriber | Subscribers to break even |
|---|---|---|
| $9 | $8.05 | 24 |
| $12 | $10.90 | 18 |
| $15 | $13.75 | 14 |

Yearly plans improve cash flow and churn. Consider regional pricing for India. Revisit if Dribble changes its price.

### Provider and admin (India)

- Provider: **Razorpay** (decision 7). It is a payment gateway, not a Merchant of Record: GST on Indian sales and the
  treatment of foreign customers stay with you, so the accountant matters more. **Verify before building:** that
  recurring subscriptions work for international cards on this account (needs international payments enabled and
  approved), the fee for international cards (the break-even table below assumed about 5% + $0.50, replace it), the
  currency options, and the settlement route.
- Paperwork to sort with an accountant: business structure (a sole proprietorship may be enough to start), PAN, bank
  account able to receive foreign currency, GST position and the export-of-services treatment, foreign inward
  remittance paperwork, invoicing.
- Also: business email (support@ and billing@), refund policy, updated terms, pricing page, subscription management
  (provider portal or Clerk billing), webhook handling, entitlement stored per Clerk user.

## 5. Social media (manual, from this laptop)

Routine after each sync:
1. Run the weekly set from `PLOTS.md` > Weekly: Shot, Miss, Save and Play of the Week, plus the xPoints table and one
   team scatter. Add one or two post-match visuals (shot map, dot grid, pass network) for the biggest matches.
2. Draft captions (Claude can draft from the figures; check every number).
3. Review, then post by hand. Each post: watermark and UTM link to playback90.com. No mention of Dribble, no Opta,
   no Dribble logo (decision 8).
4. Log each post (date, visual, impressions, clicks, sign-ups) in a sheet for the dashboard.

Automate later (scheduler or X API) once the routine is stable and Dribble has confirmed public use.

## 6. Dashboard

One private `/admin` page (Clerk role-restricted) fed by a nightly collector that writes a small metrics table.

| Section | Source |
|---|---|
| Health | UptimeRobot, Sentry, server CPU/memory/disk, API latency, 429 rate |
| Costs | AWS Cost Explorer, Cloudflare, Dribble plan ($149, manual), BigQuery bytes against the 1 TiB cap |
| Revenue | Payment provider API: MRR, churn, refunds |
| Users and usage | Clerk, PostHog |
| Data | R2 size, matches loaded vs played per competition, hours from final whistle to live |
| Social | The manual post log |

## 7. KPIs

- North star: matches analysed per week by paying users.
- Acquisition: visitors by source, X link clicks, sign-up conversion, followers.
- Activation: share of new sign-ups who open a full match analysis within 24 hours.
- Retention: day-7 and day-30 return, weekly and monthly active users.
- Revenue: MRR, free-to-paid conversion, churn, ARPU, refunds, LTV.
- Unit economics: gross margin (revenue - Dribble - infra - fees), cost per active user, subscribers to break even.
- Free-tier: share of free users who hit the 3-match limit, and conversion after hitting it.
- Reliability: uptime, p95 latency, error rate, PNG/PDF failure rate.
- Data freshness: hours from final whistle to live, coverage per competition.
- Abuse: blocked/429 requests, flagged accounts, sign-up spikes.
- Content: impressions, engagement, sign-ups per post.

## Open items

- Real fixed-cost figure (server upgrade, tools) to replace the $190 assumption.
- Pro price decision and yearly discount.
- Razorpay: international-card subscriptions, fees, settlement (verify).
- FA Cup / EFL Trophy / Taça de Portugal in or out.
- Optional email to Dribble confirming public social posting of visuals.
- Lawyer review of terms, privacy and refund wording.

## 8. Foundations status (2026-10-29)

- CI: **green**. `gh run list` shows the last runs on main succeeding (latest 2026-10-29). The note in
  `deployment-handoff.md` item 4 about CI never running is stale; pushes go through the `ishdeep-10` GitHub login
  (the `ishdeep-score` login has no push access). Local checks: API 75 tests pass, web `tsc` clean.
- Sentry: code wired, **no DSN set** (`SENTRY_DSN` and `NEXT_PUBLIC_SENTRY_DSN` empty). **Skipped for now by choice, to
  be added later; do it before the paywall launches** (create a free Sentry account with a Next.js and a Python project,
  set the DSNs on the server and in the web build, redeploy; checklist item 1 in `deployment-handoff.md`).
- Backup of `Data/playback90.db` (6.6 GB, legacy WhoScored data, last written 2026-10-20): **decided not needed for
  now** (2026-10-29). Revisit if that data becomes needed again. The laptop disk is 94% full (24 GB free).
- Lightsail: stays `micro_3_1` (1 GB, $7) **until it causes problems** (decision 2026-10-29). Options if needed: small $12 (2 GB), medium $24 (4 GB, 80 GB disk), large $44 (8 GB).
  Resizing means a snapshot and a new instance, then moving the static IP: a few minutes of downtime.
- AWS Cost Explorer: **enabled and returning data** (checked 2026-10-30 with `aws ce get-cost-and-usage`).
  Gross usage (all Lightsail, plus pennies of S3): Aug $2.70 (from the 6th), Sep $3.08, Oct $2.93 to the 30th;
  forecast for the rest of the period about $3.23. Credits applied: the same amounts, so net spend is $0.
  About $8.71 of credits used so far. The credit balance and expiry are not visible to the deploy IAM user: read them
  in the console (Billing > Credits). Unexplained: Lightsail bills about $3/month, not the $7 list price of micro_3_1.
  The `playback90-monthly` budget ($30) tracks net spend, which credits keep at $0, so it will not warn while credits
  last; add a gross-usage budget that excludes credits.

## 9. Order change and dashboard v0 (2026-10-30)

- Budget `playback90-gross-usage` created: $10/month, credits excluded, emails at 80% actual and 100% forecast.
- New order: **dashboard v0 first**, then **season analysis**, then **Phase 2 leagues**, then cups.
- Dashboard v0 design: `scripts/collect_metrics.py` runs from the laptop (it holds the AWS CLI, R2, Clerk and BigQuery
  access; the server has none) and writes `cache/admin_metrics.json`: AWS gross/credits/net by month and budgets, R2
  size by prefix, Clerk users (production instance: `CLERK_SECRET_KEY_PROD`; the unsuffixed key is Development),
  `/health` status and latency, BigQuery bytes billed this month against the 1 TiB cap. Next: an admin-only API route
  (`ADMIN_EMAILS`) serving the snapshot from R2, and a `/admin` page. Uploading the snapshot to R2 is a deliberate step.
- First readings (2026-10-30): 251 Clerk users, 33 signed in during the last 30 days; R2 1.18 GB of 10 GB
  (`backups/` 0.72 GB, `event_data` 0.30 GB, `season_stats` 0.16 GB); `/health` 200 in about 0.45 s; AWS gross about $3/month.
- BigQuery reading needs `gcloud auth login` (session expired); the other sources work without it.
- Not yet in the dashboard: revenue (nothing live), PostHog usage (needs a personal API key), Cloudflare traffic
  (needs an API token), server CPU/memory/disk.

### Dashboard v0 build status (2026-10-30)

- Built locally, **not deployed, snapshot not uploaded**: `GET /api/admin/metrics` (`apps/api/app/main.py`, 404 to
  anyone not in `ADMIN_USER_IDS` / `ADMIN_EMAILS`; reads `admin/metrics.json` from the R2 bucket), `/admin` page
  (`apps/web/app/admin/page.tsx`), client types in `apps/web/lib/api.ts`, two tests (API suite 77 pass, web `tsc` clean).
- To go live: set `ADMIN_USER_IDS` on the server (your Clerk production user id), upload the snapshot
  (`admin/metrics.json` in the R2 bucket), deploy API and web (runbook in `deployment-handoff.md`).
- Refresh routine: run `scripts/collect_metrics.py`, then upload the file. An upload helper is still to do.
- Data coverage added to the dashboard (2026-10-30): per competition, matches loaded to R2 and the latest match date
  (works now); and, once `gcloud auth login` is done, matches played/upcoming at Dribble and the latest played date,
  so "not loaded" matches show up. Metadata query only (about 0 GB scanned).
- Finding: Champions League (first match 2026-07-07) and Europa League (2026-07-09) in R2 include qualifying-round
  matches. Decision 4 says no qualifiers: decide whether to remove them from R2 and filter them in the sync.
- **Deployed 2026-10-30:** API and web with `/admin`; `ADMIN_USER_IDS` set on the server; snapshot uploaded to R2.
  Refresh = run `scripts/collect_metrics.py`, then upload `cache/admin_metrics.json` to `admin/metrics.json`.

## 10. Season analysis: finding before building (2026-10-30)

- `social-media/pb90` reads `Data/playback90.db`, the **old WhoScored database** (6.6 GB, last written 2026-10-20),
  not the Dribble frames the app now serves. Its 2026/27 data stops at 2026-10-19 (70 matches in the Premier League
  vs 80 in R2). A paid Season page built from it would disagree with the rest of the app and would rest on the
  previous data source, so it must not be used.
- The Dribble per-match frames (`Data/dribble360/out/event_data/{league}/2026_2027/*.parquet`, same files as R2) have
  148 columns against 276 in the DB. Missing: about 176 derived flag columns (shotOpenPlay, shotSetPiece, shotHead,
  passForward, passLeft/Right, tackleWon, interceptionAll, ballRecovery, dribbleWon, keeper save zones, ...).
  The raw `type`, `outcomeType`, `qualifiers`, `situation`, `bodyPart`, `setPieceType` columns are present, so the
  flags can be derived. `matchId` and `teamId` are strings (vendor hashes), pb90 casts them to int.
- Approach: add a Dribble source to `pb90/data.py` (an adapter that builds the same cache from the frames and derives
  the legacy flags and integer ids), then run the batch-1 visuals one at a time and compare each against a known
  number. Port to the new contract directly only where an adapter column would be misleading.

### Season analysis progress (2026-10-30)

- Done, local only: `social-media/pb90` now reads the Dribble frames by default (`PB90_SOURCE=dribble`, files from
  `Data/dribble360/out/event_data`, override with `PB90_EVENTS_DIR`; `PB90_SOURCE=db` keeps the retired WhoScored DB).
  New `pb90/d360.py` maps ids to integers, names teams from the app registry, and derives the legacy flag columns the
  visuals use. Cache per league-season is `.cache/events/*__d360.parquet`, built in about 8 s for the Premier League.
- Checked on the Premier League: derived counts per match match the old database closely (tackles 18.2 vs 17.8,
  interceptions 17.6 vs 17.2, dribbles 14.6 vs 14.2, shots 27.4 vs 27.6, keeper saves 5.8 vs 5.7, offsides 3.8 vs 3.9).
  Known differences: ball recoveries 79 vs 93 per match (Dribble logs fewer), `q_fastbreak` does not exist in the feed
  (unused), defensive duels are approximated as tackles plus challenges. Points computed from the raw frames equal the
  xPoints table's actual points.
- 21 batch-1 visuals run and render on the Premier League (xPoints, directness, game state, home/away xG, open play vs set
  piece, PPDA x3, tempo, turnover and SCA maps, counters, crossing, central defence, offsides, continuity, over/under
  performers, leaderboard, xT pass vs carry, centre-backs, full-backs, team vs league pizza).
- Known gotchas: default team arguments use old names ('Man City'); the Dribble registry may name clubs differently, so
  the render job must pass explicit team names. Visuals needing last season (`*_change`, `role_change_map`) cannot run:
  only 2026/27 exists.
- Not done: other leagues and MLS (season label '2026'), the batch render job, R2 upload of the PNGs plus manifest, the
  API route and the Season page, and gating it to paying users (no entitlement system yet).

### Season analysis, local build (2026-10-30)

- `social-media/tools/render_season.py` renders 26 league-level visuals per competition (top five and MLS: 156 images, 0
  failures, about 4 minutes, MLS cache about 50 s) to `Data/dribble360/out/season_visuals/{league}/{season}/` with a
  `manifest.json` each. Not uploaded. Champions League and Europa League are not rendered yet (league-phase and
  qualifier rules).
- API: `GET /api/season-visuals`, `/api/season-visuals/{league}/{season}`, `.../{name}.png` (reads the local folder in
  development, R2 `season_visuals/` otherwise; `SEASON_VISUALS_DIR` overrides). With auth on it is admin-only until
  subscriptions exist (`_require_season_access` in `apps/api/app/main.py`).
- Web: `/season-analysis` (league chips, visuals grouped by type); images go through a proxy route that adds the user's token.
- Local check: API on port 8010 (port 8000 was in use), web on 3010 with Clerk off.
  `cd apps/api && .venv/bin/uvicorn app.main:app --port 8010`, then in `apps/web`:
  `API_BASE_URL=http://localhost:8010/api NEXT_PUBLIC_API_BASE_URL=http://localhost:8010/api NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY= npx next dev -p 3010`.
- Not done: nav link, R2 upload, deploy, team and player visuals, UEFA competitions, paywall wiring.

### Season analysis rework (2026-10-30, second pass, local only)

Owner feedback applied:
1. **xPoints moved to the league table** (match-analysis schedule page, `FixturesLeagueTable`): new columns xPts, Delta
   (points minus xPts), xG, xGA and Last 5 (W/D/L chips). They show only when the league has the data, and are hidden on
   mobile like the other detail columns. xPoints removed from Season analysis.
   - `Data/generate_season_stats.py` now writes `xP` per team-match (exact expected points from both sides' shot-by-shot
     xG, no simulation). `build_league_table` sums it and builds the last five results; `merge_local_analytics` copies
     them onto the official (football-data) rows. Needs `season_stats` regenerated **and uploaded** before production shows
     them; in development the API reads a dry-run output in `Data/season_stats/` first (`_local_stats_path`).
2. **Team scatter explorer**: one chart, any two metrics from dropdowns plus an optional third (Z) that switches to a 3D
   Plotly scatter (`scatter3d` registered in `lib/plotly.ts`) and a highlight-team dropdown. 25 metrics (everything in
   `pb90.metrics.TEAM_METRICS`; the two counter-attack metrics are dropped because the feed has no fast-break marker;
   crossing xG needed key-pass to shot linking, now derived in `pb90/d360.py`).
3. **xG by game state removed** for now.
4. **Crests and design**: every crest is scaled to the same visual area from its real aspect ratio and sits on the same
   light badge; chart font and colours come from `lib/theme.ts` (same as the post-match charts); controls reuse the app's
   `.select` and card styles.
5. **Reference from the league page**: the page the globe opens (`/matches/{league}/{season}`) shows a "Season
   analysis" link for people who can open it.
6. **No PNGs anywhere in Season analysis**: gallery, proxy route, PNG routes and the render script are deleted. Data flow:
   `social-media/tools/export_season_aggregates.py` writes `Data/dribble360/out/season_agg/{league}/{season}/team_metrics.json`
   (aggregates only), the API serves `GET /api/season-analysis` and `/api/season-analysis/{league}/{season}/team-metrics`
   (local folder in development, R2 `season_agg/` otherwise; admin-only while auth is on), the page draws it with Plotly.
- Not built yet: the other interactive visuals from the v1 list (player leaderboard and scatter, team vs league radar,
  rolling xG and most-improved, turnover and SCA zone grids, over/under performers).
- Not done: upload of `season_agg/` and regenerated `season_stats/` to R2, deploy.

### Season analysis, third pass (2026-10-30, local only)

- xPts, Delta, xG, xGA, Last 5 now show for the top five leagues, Champions League and Europa League (the earlier run only
  had the Bundesliga because season stats were still generating). MLS: its `season_stats` dry run was still running when
  this was written; MLS has no xG source in the official table, so it shows Last 5 only until it finishes.
- UEFA: `LEAGUE_PHASE_START` (2026-09-01) in `Data/generate_season_stats.py` and `social-media/pb90/config.py` keeps
  qualifying and play-off rounds out of the stats, tables, team scatter and player scatter (36 clubs, 54 matches in the
  Champions League). R2 still holds the qualifier files and the fixtures list still shows them; removing them from R2 is a
  separate delete that needs the owner's go-ahead.
- Season analysis page: league logos (light tiles) instead of names, animated hero (CSS only, respects reduced motion),
  Teams / Players view tabs. Player scatter explorer: any two metrics (+ optional Z for 3D), per 90 or total, minimum
  minutes, position chips, team filter, highlight a player, names-on-chart slider. Data: `player_metrics.json` per
  competition from `social-media/tools/export_season_aggregates.py`, served by
  `GET /api/season-analysis/{league}/{season}/player-metrics` (about 140 KB gzipped for a league) and fetched in the
  browser only when the Players view opens, cached per visit.
- Crests: Champions League clubs from football-data (`Data/dribble360/build_uefa_crests.py` writes
  `apps/api/app/uefa_crests.json`). Europa League clubs have no free crest source yet and show a monogram badge.
- Not done: upload to R2 (`season_agg/`, `season_stats/`), deploy, further interactive visuals (radar, rolling xG, zone grids).

### Season analysis, fourth pass: remaining visuals (2026-10-30, local only)

- Teams view: Team scatter explorer, **Team profile vs the league** (percentile radar for up to four teams, metric presets
  Balanced / Attack / Defence / Style plus any custom set), **Form over time** (rolling xG for and against with a
  window slider, and Most improved: xG difference in the latest N games vs before), **Pitch zones** (turnovers and
  open-play shot-creating actions conceded on a 6-band x 5-lane grid; share, per match or difference vs league average).
- Players view: Player scatter explorer, **Leaderboard** (any metric, per 90 or total, position/team/minutes filters, top N),
  **Over and under performers** (goals vs xG, assists vs xA; open-play, penalties excluded).
- Data: `social-media/tools/export_season_aggregates.py` now also writes `team_matches.json` (per team per match: date,
  opponent, venue, xG for/against, goals) and `zones.json` (cell counts) for all eight competitions. One generic API route,
  `GET /api/season-analysis/{league}/{season}/{team-metrics|player-metrics|team-matches|zones}`, serves them (admin-only
  while auth is on). Browser fetches happen only when a section mounts and are cached per visit (`useSeasonFile`).
- Still to do: upload `season_agg/` and regenerated `season_stats/` to R2, deploy, remove UEFA qualifier files from R2
  (needs go-ahead), Europa League crests, paywall gating.

### Season analysis, fifth pass (2026-10-30, local only)

Owner requests applied before deploy:
1. **Player images**: leaderboard cards (`PlayerAvatar`), and photos on the labelled points of the player scatter (Plotly
   layout images, same app image resolver).
2. **Pitch zones**: 45 actions in grouped dropdowns (shooting, creating, passing, carrying, possession, defending,
   goalkeeping, plus shots conceded, shot-creating actions conceded, offsides). Same masks as the metric table
   (`social-media/pb90/metrics/actions.py`), so the pitch shows the events behind the number.
3. **Pitch view from the scatters**: team scatter "Where does it happen on the pitch?" compares a team with the league
   average or another team (share, per match, or difference); clicking a crest picks the team. Player scatter: click a
   player to see their actions behind the X / Y / Z metrics. Metrics that are ratings (xG, xT) map to their events.
4. **Game state and match time filters** on both scatters (leading / drawing / trailing x six 15-minute periods).
   Export `player_slices.json` / `team_slices.json` hold counts and minutes per cell; the browser re-adds the selection
   and recomputes per 90. Team metrics that are ratios of other events (PPDA, tempo, ...) are disabled under a filter;
   teams with under 45 minutes in the selection are dropped.
5. **Possession-adjusted** per 90 in Values (scatter and leaderboard): value x 50 / possession %, factor in `player_metrics.json`.
6. **Leaderboard** is now player cards (photo, name, team, value); selecting one shows the pitch map of the chosen metric.
7. **UEFA qualifiers removed from R2** (77 files, 21.8 MB; local copies kept) and the sync now skips them.
- New files per competition: `zones.json` (all actions), `player_slices.json` (about 1.2 MB, loaded only when a filter is
  used), `team_slices.json`, `player_actions/{playerId}.json` (about 7 MB per league in total, one file per player, fetched
  one at a time). New API route `GET /api/season-analysis/{league}/{season}/player-actions/{playerId}`.
- **Licence note**: the per-player action coordinates are event-level data sent to the browser. They are display-only,
  capped at 300 per action, without timestamps or match ids, and the whole Season area is admin-only for now. Before opening
  it to subscribers, confirm with Dribble that per-player season action maps are within "display within the product"
  (the follow-up reply covers charts; bulk delivery of rows needs the addendum). Team pitch grids are aggregates.

### Refresh routine and dashboard storage (2026-10-30)

- `scripts/refresh_season_data.py`: one command for export + season stats + R2 upload + dashboard snapshot (see
  `deployment-handoff.md`). Tested: local build of one league (117 s), and `--upload --prune` of one league plus the snapshot.
- Dashboard (code ready, **web not redeployed yet**): Cloudflare R2 storage as a tile with the share of the 10 GB free tier,
  object count, estimated monthly cost (storage beyond the free tier, $0.015 per GB), 7-day growth (from a local daily
  history in `cache/admin_history.json`, so it needs a week of snapshots), and storage by area (backups, event_data,
  season_stats, season_agg). Requests, bandwidth and operations need a Cloudflare API token, which is not configured.
  Today: 1.25 GB, 7,403 objects, $0.

### Season analysis, sixth pass (2026-10-30, local only, not deployed)

1. **Share button** (the match-analysis one, `DownloadPngButton`) on every Season card: scatters, radar, form, zones,
   leaderboard (photo table), over/under, plus the pitch comparison and a player's pitch maps. Exports carry the active
   filters as chips. Photos and crests are inlined as data URLs through the API image proxy so exports are not blank
   (proxy allow-list extended with `crests.football-data.org` and `media.api-sports.io`: needs the API redeployed).
2. **Open play / set piece filter**: on the team and player scatters, leaderboard, over/under (with game state and match time),
   the pitch zones, the team pitch comparison and the player pitch maps. Definition (`pb90/metrics/actions.py::add_phase`):
   an event is set-piece phase if it is a corner or free-kick delivery, a set-piece or penalty shot, or anything either team
   does within 8 seconds after a delivery in the same half. Throw-ins and goal kicks count as open play. About 9% of events and
   24% of shots are set-piece phase. Slice files now have 36 count cells (phase x state x time bucket) and 18 minute cells.
3. **Metric categories** in every metric dropdown (player: Shooting, Chance creation, Shot-creating actions, Passing, Carrying
   and dribbling, Possession, Defending, Goalkeeping; team: Attack, Defence, Pressing and duels, Style and possession,
   Crossing). Radar chips are grouped the same way.
4. **Age filter**: built (sliders on the player scatter, leaderboard and over/under, shown only when ages exist) but there is
   **no age data**: the Dribble `players` table has `date_of_birth` empty for all 6,125 players, and the SoccerWiki file has
   photos only. The export reads an optional `Data/dribble360/player_birthdates.csv` (`d360_player_id,date_of_birth`) and the
   filter appears as soon as it exists. Sources to choose from: ask Dribble, API-Football squads (key exists, rate limited),
   or a hand-built CSV.
5. **Shot-creating actions**: player metrics (SCA, GCA, SCA by passes, carries, dribbles, defensive actions, shots) as totals
   and per 90 with the same filters and pitch maps; team metrics SCA created and conceded per match (created is also
   re-addable under filters); SCA actions are pitch-zone actions. Definition: either of the two actions before a shot by the
   same team, within 15 seconds, penalties excluded (`pb90/metrics/sca.py`).
- Chips now narrow instead of toggle: with everything selected, clicking one option selects only that option.

### Zone leaders and ages (2026-10-30, local only)

- **Zone leaders map added** to the Players view (the interactive version of `social-media/output/player-maps/zone-leaders-map_*.png`):
  the leader of each of the 29 pitch zones for any of the 48 actions (grouped dropdown, includes the shot-creating actions),
  photo in a coloured frame, surname, value and the leader's own actions as dots (shape = kind of action for SCA). Filters: values
  (per 90, possession-adjusted, total), minimum minutes, minimum actions in a zone, team, open play / set pieces, include
  goalkeepers; Share button. Rule as in the social visual: a player qualifies in a zone with at least the zone median and the minimum.
  Data: `zone_leaders.json` per competition (about 1 MB raw, 200 KB gzipped, loaded only when the visual mounts), served by the generic
  season-analysis route (`zone-leaders`). Game state and match time are not offered here (counts are per zone and phase only).
- **Ages**: the schema PDF could not be read here (no PDF tools), so whether Dribble ever populates `date_of_birth` is unconfirmed: the
  column exists in the `players` table we pull but is empty for all 6,125 players. A direct BigQuery check needs `gcloud auth login`
  (expired). API-Football: the key is only on the production server; a status check from there was blocked by the permission
  prompt, so plan and daily quota are unknown. Squads give age but not birth date; about 200 teams would need about 200 calls.

### Event visuals and the age answer (2026-10-30, local only)

- **Arrows**: passes and carries are drawn from start to end (arrowhead at the end; carries dotted) on the zone leaders map; the
  player pitch maps already drew arrows but a bug from the phase change (event rows grew from 4 to 5 values) had silently turned them into
  dots; fixed. **Shots** now carry their outcome and xG (player action files: `[x, y, endX, endY, phase, kind, xG]`, kind G goal, S saved,
  M off target, P post, B blocked): shape/colour = outcome, size = xG, with a legend, in the player pitch maps and on the zone leaders map.
- **Zone leaders** default minimum actions per zone lowered for rare actions (shots 2, shots on target 1, goals 1, ...).
- **Ages**: checked directly in BigQuery with the pipeline's credentials (`PYTHONPATH=~/.d360-bq ... google.cloud.bigquery`, application-default
  login): the Dribble `football_pro.players` table has **91,834 rows and 0 with `date_of_birth`, 0 with nationality, 0 with height**. The
  vendor does not populate player bio fields in this dataset, so ages cannot come from Dribble. Note `bq` uses the `gcloud auth login`
  account (no `bigquery.jobs.create` on the sandbox project); the pipeline uses application-default credentials.

### Player ages (2026-10-30, local only)

- Sources (Dribble has none: `players` has 91,834 rows and 0 birth dates, nationalities or heights):
  1. **football-data.org free tier** (`FOOTBALL_DATA_API_KEY`): squads with exact `dateOfBirth` for the Premier League, LaLiga,
     Serie A, Bundesliga, Ligue 1 and Champions League, 6 requests in total. `Data/dribble360/build_player_birthdates.py` matches
     them to our players by club and name (2,333 matched).
  2. **API-Football free plan** (`x-apisports-key`, 100 requests a day, 10 a minute): `players/squads?team=ID` gives a whole-number age
     (team listings for the current season are blocked on the free plan). `Data/dribble360/build_player_ages_apifootball.py` covers MLS
     (700 players, 22 requests) and the Europa League clubs football-data does not cover (254 so far, 40 requests); squads are cached
     in `Data/dribble360/cache/apifootball_squads/`, so re-runs are free. Some Europa League clubs were not found by name (Jagiellonia,
     Besiktas, AZ, Ararat-Armenia, Salzburg, Viktoria Plzen, Ferencvaros): run again with spelling fixes on another day's quota.
- Coverage: Premier League 258 of 263 players with 270+ minutes; MLS 564 of 675. The age sliders on the player scatter, leaderboard and
  over/under are live (`has_age`); tested: oldest = 21 leaves 20 Premier League players.
- Both CSVs and the cache are in `.gitignore` (third-party data). Ages drift: re-run the two scripts once a season (ages are computed
  from the date, so a re-export is enough in between).

### Season analysis, seventh pass (2026-11-01, local only)

1. League logo tabs are larger (68 px tiles, more space, 2 px border) with a line "Select a logo to change the league".
2. Share: every card lists all active selections as chips on the preview and the exported PNG (values mode, extra axis, team,
   positions, age band, highlight, play phase / game state / match time, minimums, top N).
3. Play phase, game state and match time are now one line of three small menus (`SliceFilters`) with a Reset link, on every team and
   player visual that has them.
4. Zone leaders: every photo is the same size (`PHOTO_HALF`), the leaders' own events are no longer plotted, and a **data bug was
   found and fixed**: `pb90.metrics.assign_zones` returns a Series on a fresh index, so assigning it to the events frame by index
   put zones on the wrong rows (a winger showed SCA in his own goal area). The export now uses the values. All competitions re-exported;
   own-box leaders are now goalkeepers and centre-backs, leaders in attacking zones have the higher per-90 values.
5. Age filter is now chips: All ages, U21, U23, U25 (younger than 21, 23, 25 today), on the player scatter, leaderboard, over/under and
   zone leaders.
6. Over and under performers has seven measures: goals vs xG, assists vs xA, goals + assists vs xG + xA, shot conversion vs expected (%),
   key passes turned into assists vs expected (%), completed passes vs xPass, pass completion vs expected (%). Rate measures need
   enough attempts (15 shots, 10 key passes, 150 passes). xGOT based measures (placement, goals vs xGOT) are not possible: the xGOT
   column is all zeros in the Dribble frames (no goal-mouth placement in the feed). xPass is exported per player as `xpass` (total, per 90 and
   in the slices) and is also a scatter / leaderboard metric.

### 2026-11-01 admin page: season-analysis builds
`collect_metrics.py` now reads each `season_agg/{league}/{season}/` build (matches, build time, players with an age) into `r2.season_analysis`; `/admin` shows it in a "Season analysis" table and flags builds that are behind the matches loaded in R2.
