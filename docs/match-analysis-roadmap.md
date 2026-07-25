# Match Analysis — Roadmap & Iteration Log

## Context for new sessions (read this first)

**Stack & dev environment**
- FastAPI backend `apps/api` (run: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000`; **no --reload — restart after backend changes**). Next.js 15 frontend `apps/web` on :3000 (`npx tsc --noEmit` from `apps/web` for typechecks).
- Match event data lives in R2 parquet (`playback90/event_data/{league}/{season}/...`); raw source DB is `Data/playback90.db` (sqlite). Aggregates in `season_stats/{league}/{season}/`.
- Test fixture used throughout: PL match 1903350 (`playback90/event_data/premier-league/2025_2026/2026-05-24_1903350_184_vs_161_1___1.parquet`, Burnley 1-1 Wolves).
- Browser verification: headless-Chrome puppeteer scripts in `/tmp/pbtest/` (may be wiped; pattern = `puppeteer-core` + `executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`, screenshot + click `.png-download-button`, inspect `.png-preview-overlay`).
- Coordinates: events are team-relative, x∈[0,105] toward the attack, y∈[0,68] with **y=0 on the attacking team's right touchline** (SVG rendering must flip: `svgY = 68 − y` for a left→right team).

**Key files (current architecture)**
- `apps/web/app/analysis/[matchId]/page.tsx` — server page, 6 tabs, wires all sections; wraps content in `ShareExportProvider` (match metadata for exports).
- `apps/web/components/DownloadPngButton.tsx` — the entire branded Share/PNG system: 16:9 canvas (3200×1800), header/chips/footnote/footer, multi-chart grid (`maxCharts`, `chartsPerRow`, `chartGroupSelector`), per-chart labels/subtitles, structured `chartPanels` (metric chips + legends + breakdown tables), SVG capture, preview modal. Most-touched file of iteration 2.
- `apps/web/components/{LineupsPanel,TeamComparisonPanel,MatchDynamicsPlotly,PlayerAnalysisSection,AiInsightCard,PlayerAvatar}.tsx`, `apps/web/lib/{theme,images}.ts`.
- `apps/api/app/services/views/match_summary.py` — stat breakdowns, per-third series, lineups/phases (formation-id map adapted from kloppy).
- `apps/api/app/services/{insights,ai_analyst,player_images}.py`; image proxy + insights endpoints in `apps/api/app/main.py`.
- `Data/generate_season_stats.py` (season aggregates → R2), `Data/build_player_image_map.py` (SoccerWiki squad scrape → `player_images_map.json`).

**State:** everything below is shipped and browser-verified. No known open bugs as of 2026-07-14; next work = whatever the user raises.

---

## Iteration 1 (phases 0–3) — shipped

Audit + rebuild of the 6-tab match analysis page (Match Dynamics, Shots & SCA, In Possession, Out of Possession, Duels & Transitions, Player Analysis). All phases 0–3 were implemented:

- **Phase 0 (cleanup):** dead code removed, shared `lib/{theme,pitch,teamColors}.ts`, normalized-dataframe cache in the API, zone-threshold fix (0–105 scale), typed `AnalysisViewFilters`, `matches.py` split into `services/views/*`.
- **Phase 1 (UX/perf):** `next/link` tabs, URL-driven filter state, shared plotly loader, `ViewState` skeleton/error cards, mobile scroll wrappers, a11y pass.
- **Phase 2 (features):** player avatars (SoccerWiki), PNG download button, glossary popovers, per-third In Possession filters, half-space channel analysis, combination play, set pieces (In Possession sub-section), player season history, AI insight cards, player comparison (season-stats based).
- **Phase 3:** kit colors, GK panel, mirrored shot map, OG share images, async report v2, team form strips.

As-built deviations: shots block stayed in `matches.py` (import cycle; re-exported via `views/shots.py`); set pieces live inside In Possession; player comparison shipped as season-stats comparison + deep links.

---

## Iteration 2 — feature bugs & improvements (in progress, started 2026-07-10)

### 1. Form strips only showed for Premier League — ✅ FIXED
- **Root cause:** `season_stats/{league}/{season}/*.parquet` existed in R2 only for `premier-league`. The frontend/API path was league-agnostic all along; `Data/generate_season_stats.py` had only ever been run for the PL.
- **Fix:** ran the generator for laliga, bundesliga, serie-a, ligue-1, champions-league, fifa-world-cup and refreshed premier-league (also activates player Season Context deep links in those leagues).
- Second bug found while backfilling: World Cup rows have NULL `teamName` in the raw DB for most national sides — the generator now backfills names from `app.domain.TEAM_DICT` (same as the API) before aggregating.
- Verified: team-form returns 5 matches for all 7 leagues (spot-checked Barcelona, Bayern, Inter, Marseille, Real Madrid, Brazil).

### 2. "AI Analyst" → "Insights", no API key required — ✅ DONE
- New `apps/api/app/services/insights.py`: `build_deterministic_insights(df, view_id, team)` — rule-based bullets computed from the same view builders that power each tab. Same baseline logic for every match:
  - **match-dynamics:** xG battle vs scoreline, finishing over/under-performance (±1 goal vs xG), possession vs threat contrast, PPDA pressing gap (≥2), most dangerous flank.
  - **shots:** per-team volume/quality (xG/shot ≥0.12 = "high-quality looks"), biggest chance (player/minute/outcome), big chances (xG>0.35) converted, secondary xG threat.
  - **in-possession:** final-third completion + xT, most productive third, top xT channel (half-spaces), most-used pass pair, centralization read (≥0.15 = hub-reliant).
  - **out-of-possession:** action counts (tackles/interceptions/recoveries), workload imbalance between teams (≥15 actions), top defender, dominant defending third.
  - **duels-transitions:** duel win % head-to-head (both teams), transition-to-attack conversion, top duelist.
  - **player-analysis:** most touches, in-possession leader, defensive leader, top shot taker, top duelist.
- Endpoint `POST /analysis/ai/insights?view=X&mode=baseline|ai`: deterministic by default (instant, no key); `mode=ai` streams Claude only when `ANTHROPIC_API_KEY` is set. Response carries `X-AI-Available` header.
- Frontend `AiInsightCard.tsx`: renamed to **Insights**, auto-loads on tab/team change, optional "✦ AI deep dive" button only when the key is configured. 503 path removed.
- Also fixed latent bug: `build_view_digest` called `build_shots_sca_view(df, team=...)` which doesn't accept `team` → shots insights would 500.

### 3. Match Summary (Match Dynamics tab) — ✅ DONE
- **3.1 Fonts unified** — new `CHART_FONT_FAMILY` (`Space Grotesk` first, matching h1–h3) exported from `apps/web/lib/theme.ts` and used by every Plotly component; `.team-summary-label/.team-summary-value` and embedded-pitch SVG text now use `var(--font-display)`.
- **3.2 Clickable stat breakdowns** — backend `build_stat_breakdowns()` in `apps/api/app/services/views/match_summary.py` (goals → scorer/minute/xG/pen/OG; xG → open play/set piece/penalty/non-pen/halves; shots → on/off/blocked/woodwork/halves; possession & pass accuracy → per third; big chances → event list; PPDA → halves; turnovers/corners/xT → thirds+sides+source). Frontend: new client `TeamComparisonPanel.tsx` (replaces the server-rendered block in page.tsx) with accordion sub-panels.
- **3.3 Per-third dropdowns** — backend `build_thirds_series()` (15' windows × team × third: possession share, pass accuracy, zonal PPDA, turnovers; thirds are team-relative, opponent coordinates mirrored). Frontend: `ThirdSelect` on all four line charts, default "All thirds".
- **3.4 Footnotes** — one-line interpretation (`.chart-footnote`) under every Match Summary visual; the third-filtered charts update their footnote with the active third.
- **3.5 Marker clipping fixed** — `cliponaxis: false` on line/marker traces in `MatchDynamicsPlotly`.
- **3.6 Lineups & Substitutions** — backend `build_lineups()` parses `FormationSet` qualifiers (InvolvedPlayers/TeamPlayerFormation/JerseyNumber/PlayerPosition/TeamFormation/CaptainPlayerId) with the Opta formation-id→name map + per-formation slot→position coordinates (adapted from kloppy); subs paired via `RelatedEventId`. Frontend `LineupsPanel.tsx`: single pitch, home left / away mirrored, jersey dots + names, captain ringed gold, formation tags, per-team sub lists, toggle Formation ⇄ Avg positions (mean touch location).

### 4. PNG download → branded share image with preview — ✅ DONE
- `DownloadPngButton.tsx` rewritten: captures the Plotly chart, composes a branded canvas (PB90 logo + "PLAYBACK90 · MATCH ANALYSIS" eyebrow, visual title, team logos + `Home score Away · League · date` line, active-filter chips, divider, chart, "Generated with PlayBack90" footer) and opens a **preview modal** with Cancel / Download.
- Match metadata flows via new `ShareExportContext.tsx` (provider wraps the analysis page in page.tsx: names, score, league, date from file path, logo URLs, kit colors).
- Call sites pass `title` and active `filters` (e.g. the selected pitch third on the Match Summary line charts, selected team on shots/network/defensive exports).

### 5. Player images mismatch — ✅ DONE (team-aware mapping)
- SoccerWiki player export has no club field, so name-only matching could return the wrong person's photo.
- New one-time build script `Data/build_player_image_map.py`: matches every club in `app.domain.TEAM_DICT` to its SoccerWiki club id (token matching + alias table), scrapes each club's squad page once (squad pid == PlayerData ID), and writes `player_images_map.json` (~124 clubs, ~5.4k players: team → normalized player name → image URL). Re-run after transfer windows.
- `player_images.py` resolution order: team squad map (exact name → unique surname → token subset) → global index. Global index improvements: ambiguous duplicate full names are dropped instead of guessing, reversed name order ("Hee-Chan Hwang" ⇄ "Hwang Hee-Chan") is tried.
- `GET /api/players/images` accepts optional `team`; `PlayerAvatar.tsx` batches requests per team and passes it (PlayerAnalysisSection selected players, GoalkeeperPanel).
- National teams (World Cup) have no SoccerWiki squads — they fall back to the global name index / initials avatar.

### Iteration 2.1 — polish round (2026-07-10) — ✅ DONE
1. **Lineups panel v2** (`LineupsPanel.tsx`): moved above Team Comparison; compact markers with proxied player headshots + "LastName (No.)" labels; pitch restyled to match the app's chart surfaces (no green turf); Avg-positions mode shows one team at a time (home default, team switch) with a **Voronoi overlay** (half-plane clipping, no new deps) tinting each player's covered zone.
2. **Team colors everywhere**: `InPossessionNetworkSection` was overriding real kit colors with hardcoded green/blue (`staticMatchTeamColor`) — removed; pass network/heatmap now use `teamColors` like the other tabs.
3. **Share/PNG export v2** (`DownloadPngButton.tsx`):
   - Cleaner layout — title left, PB90 logo top-right (wordmark removed), roomier header/footer.
   - Captures multiple charts (`maxCharts`) into a side-by-side grid — Shots & SCA exports pitch + goal-mouth as 1×2.
   - SVG panels supported (serializes the SVG, inlines computed styles + external images) — Lineups, GK, shot map, channels, combination, set pieces all export.
   - New `GET /api/players/image-proxy` (allow-listed to soccerwiki/github CDNs) so headshots/logos don't taint the canvas.
   - Player Analysis export includes the selected players' headshots next to the title (`titleImages` resolved lazily from the avatar cache).
   - Button restyled as an animated gradient "✦ Share" pill and placed on every visual across all tabs.

### Iteration 2.2 — lineups orientation + match phases (2026-07-10) — ✅ DONE
- **Left/right inversion fixed**: event data has y=0 on the attacking team's right touchline while SVG y grows downward, so a team attacking left→right must render `svgY = 68 − y` (mirrored back for the away side). Applied to formation markers, avg positions and the Voronoi points.
- **Match phases**: `build_lineups()` now builds a phase timeline — the match is split at every substitution group and `FormationChange`; per phase and team it returns the on-pitch XI (slot transfer from `SubstitutionOn`'s `FormationSlot` qualifier / the outgoing player's slot, formation updates from `FormationChange`), the active formation name, and **average touch positions computed within that phase only** (expanded-minute clock; labels mapped back to regular match minutes).
- Frontend: phase chips on the Lineups panel drive both modes — formation view shows both teams' actual XI/formation for the phase; avg-positions view shows the selected team's phase XI with phase-scoped Voronoi, so substitutes appear in the phases they played.

### Iteration 2.3 — per-team phases + away orientation (2026-07-10) — ✅ DONE
- **Per-team phase chips**: phases now split at each team's *own* subs/formation changes (`build_lineups` returns `phases: {team: [...]}`); formation view shows one labeled chip row per team, avg view shows the selected team's row. Timeline replay is chronological (formation changes and subs interleaved); if a sub carries no slot info, the incoming player takes any free slot so the XI never drops below 11.
- **Always 11 on the pitch**: players with zero touches in a short phase previously vanished from the avg view — they now fall back to their formation-slot coordinates (noted in the footnote).
- **Away attack direction**: avg positions render home left→right (`x, 68−y`) and away right→left (`105−x, y`), matching the formation view's mirroring; the pitch tag shows the attack arrow.

### Iteration 2.4 — comparison highlights, image markers, export polish (2026-07-11) — ✅ DONE
- **Breakdown highlighting**: expanded stat sub-panels now mark the better side per metric row in green (lower wins for PPDA/turnovers), matching the main table's convention.
- **Image markers on Match Dynamics** (`lib/images.ts` helpers): goals on xG Flow and xT Momentum render circular player headshots ringed in the team color (composed via canvas from proxied data URLs — export-safe; star fallback when no image); substitutions use a green/red arrow icon, bookings yellow/red card icons (inline SVG data URLs). Hover targets kept via invisible scatter markers.
- **Attacks by Flanks** got a Share button; SVG capture now supports multiple SVGs per scope (1×2 grid, same as multi-plot capture).
- **Exports include the visual's footnote**: the card's `.chart-footnote` text is wrapped and rendered between the chart and the export footer.

### Iteration 2.5 — player-analysis export completeness (2026-07-11) — ✅ DONE
- `DownloadPngButton` gained `chartLabels` (caption above each chart in the grid), lazy `filters` (resolved at click time), and `statLines` (extra text block under the charts, wrapped).
- Player Analysis export now reads the live panel DOM at click time: each pitch's selected view title (plus the active stat filter, e.g. "In possession · Passes"), the current team/game-state filter chips, and every pitch's stat counters ("In possession: Passes 53/63 · Carries 22 · …"); the stats-table rows are serialized too when that toggle is on.
- Follow-up: the sub-stat detail panels (e.g. pass Direction/Type/Length/Height when "Passes" is active), any checked panel checkboxes, and the active pass-subtype legend selection are serialized into the export as well; preview modal enlarged (min(1360px, 96vw), image up to 76vh).
- Layout follow-up: exports now mirror the in-app arrangement — each pitch column gets its own sub-panel and `chartSubtitles` puts the checked options as a small subtitle under each pitch title; the full-width `statLines` block is reserved for the stats table.
- Panel look & legends: new structured `chartPanels` prop renders **metric chips** (rounded label/value chips, active stat highlighted in accent) and titled breakdown groups per column, plus each pitch's **legend** (line/circle/square swatches with the live colors read from the DOM legend elements) — replacing the plain-text lines.
- **Social-ready 16:9 frame**: every export is now composed on a fixed 1600×900 (rendered 3200×1800) canvas with 44px margins on all sides — charts are scaled to fit evenly distributed columns within the remaining vertical budget (header, per-column panels, footnote and footer all measured first), headshots/title enlarged, brand logo sized up and aligned with the title row, header separated by a divider, footer pinned to the bottom margin.
- Panel compaction: chips shrunk, group titles moved inline beside their chips, legend tightened — roughly halves the panel block so the pitches claim the reclaimed height.
- Final polish round: chip/legend text re-enlarged for legibility; header headshot drawn in a **team-color ringed circle** (like the lineups markers) and bumped to 72px, brand logo 72px, team crests 34px, title 36px. All chart columns share one fixed height budget so pitches render equal-sized under every pitch-type combination (short-panel columns simply keep a little whitespace).
- Equal-pitch layout: per-column panels keep only the counter chips; **titled breakdown groups render as a mini table under their own pitch column** (alternating row backgrounds, row-title column, wrapped label/value cells), and **legends stack vertically in the right-hand space beside each pitch** — so long legends (Out of possession) no longer shrink their pitch and all pitches render at the same size.
- Shots + SCA export fix: capture is grouped per pitch panel (`chartGroupSelector`), so the goal-mouth map and half-pitch shotmap stack vertically into one column image; the SCA actions table is serialized into the pitch's mini table (clock as row title, action→outcome and shot→xG cells, capped at 5 rows with an overflow row).
- Stacked columns render their legend inline below the counters (full column width for the two shot maps); single-plot columns keep the vertical right-hand legend.
- New in-app legend on the Touches pitch when "Receives" is active (`.player-analysis-touch-legend`): solid team-color line = progressive receive, dashed = other receive — picked up by the export automatically.
- **Multi-player comparison exports**: the grid supports rows (`chartsPerRow`); each compared player's three pitches render as their own labeled row ("Player — Heatmap …"), with per-row stat panels; detail tables are skipped in comparison mode to fit the 16:9 frame. Verified the shared template (header/chips/footnote/footer, 3200×1800) renders correctly for every tab's Share button (dynamics charts, lineups SVG, shots 1×2, network, defensive zones, duels zone map).

### Iteration 2.6 — lineup phase slot integrity (2026-07-11) — ✅ DONE
- **Bug:** in substitution phases, players could stack on one formation slot while another sat empty, and reshuffled players kept stale positions. Root cause: a `SubstitutionOn`'s `FormationSlot` qualifier reflects the pre-reshuffle numbering, but WhoScored often emits a simultaneous `FormationChange` whose `TeamPlayerFormation` is the authoritative post-sub mapping (e.g. Brighton 59': sub says Veltman→slot 11, the change actually puts him at RB slot 2 and moves two others). Our replay applied the formation event first and let the stale sub slot overwrite it.
- **Fix in `build_lineups`:** at equal minutes subs now apply *before* formation events (the full formation mapping wins), every slot write is sequence-tracked, and a normalization pass resolves any remaining slot collisions (most recent assignee keeps the slot, earlier occupants move to free slots) so each phase always has 11 players on 11 distinct slots.
- Verified: a 15-match PL scan had 46 corrupt phases before the fix, 0 after; Brighton fixture visually confirmed in the browser.

### Iteration 2.7 — Shots & SCA fixes (2026-07-11) — ✅ DONE
- **Self-SCA on headed goals fixed** (`_shot_leadup_events`): a headed/duelled shot pairs the shooter's own duel event (e.g. Aerial) with the shot at the same moment — that artifact is now excluded (shooter's defensive-action events within 0.05 min of their shot dropped; shooter also filtered out of the direct-assist set). Verified: all headers in fixture 1903350 now show only genuine leadups.
- **Shots count as SCA (rebounds)**: preceding shot events (`Goal/MissedShots/SavedShot/ShotOnPost`, exempt from the "successful outcome" filter) are eligible leadup actions; new `_sca_category` bucket **"SCA Shots"** in the player summary + table breakdown. Verified: Krejci's 34' missed header credits SCA on Bueno's follow-up.
- **Avatars**: `PlayerAvatar` added to the shot side panel (shooter 46px in title, SCA players 28px in `.shot-sca-event-body`) and to the summary table player column (26px, `.shot-player-cell`), resolved with the shot's `shooting_team`.
- **Export fixed**: Shots & SCA share now uses `chartGroupSelector=".shots-plotly-shell"` so goal-mouth + pitch stack **vertically** into one column.
- **Export side table** (`DownloadPngButton` gained `sideTable?: () => SideTable` + lazy `title`): a bordered table panel on the right of the charts (chart area shrinks by 430px). Row kinds: `header` (section title + divider), label/value (value right-aligned, wraps when long), and **avatar rows** (`image`/`label`/`value`/`sub`: ringed headshot, bold name, right-aligned value, muted sub-line, zebra backgrounds); `large: true` scales fonts/spacing ×1.35.
- Shots export wiring: **no selection** → "{team} · Match totals" in large mode (Shots/Goals/SOT/xG/SCA/SCA xT/Assists/xA) + "Top shot takers" section (top 3 by shots, headshots from the avatar cache, xG/goals/on-target sub-line); **shot selected** → same large mode; title becomes "Shots & SCA — {player}" with the shooter's ringed headshot (via `data-player`/`data-team` attrs on `.shot-detail-panel`), shot facts as label/value rows, and each SCA as an avatar table row (headshot read from the in-app panel's `img.player-avatar`, tag right-aligned, time · action · xT sub-line).
- **Rebound assist voiding** (`_shot_leadup_events`): if another shot occurred between the assist pass and the shot (rebound), any `is_assist` credited before that intervening shot is cleared (xA zeroed) — rebound goals carry no assist.

### Iteration 2.8 — In Possession tab (2026-07-12) — ✅ DONE
- **Network node headshots** (`PassNetworkPlotly`): circular team-color-ringed player images rendered as plotly `layout.images` on top of the node markers (initials fallback when no image); sized/dimmed per selection/profile state. Images come from the shared `PlayerAvatar` cache — new exports `prefetchPlayerImages`/`subscribePlayerImages` warm it for all nodes, then `circularImageDataUrl` composes export-safe data URLs.
- **Network share**: `DownloadPngButton` gained `profileCards?: () => ProfileCard[]` — the In Possession Profile cards (name/score/meter/description) are read from the DOM at click time and drawn in a 3-per-row card grid under the pitch (chart budget accounts for it). With a node selected: title becomes "Passing Network — {player}" + ringed headshot, and the side table carries the rail stats (passes made/received, avg distance, prog, xT in/out, prog rate) plus "Top connections" as avatar rows.
- **Rail panel**: selected-player header now shows the player's avatar (also warms the cache for exports).
- **In Possession table**: 24px `PlayerAvatar` next to every player name (`.player-cell`).
- **Channels & Half-Spaces**: `build_channel_analysis` now also returns `zones` — the Juego de Posición 6×5 grid (mplsoccer uefa positional bounds x 0/16.5/34.5/52.5/70.5/88.5/105, y 0/13.84/24.84/43.16/54.16/68) with per-zone passes/prog/xT/share. Frontend toggle "Vertical channels ⇄ Half-space grid": grid SVG colored by zone xT share with % labels (≥3%), and a named-zone table (Zone/Passes/Prog/xT/Share, sticky header, scrollable) replacing the stat list. Share button exports the active mode with a matching side table and dynamic title.
- **Channels/zones are open-play only + net xT** (follow-up): set-piece deliveries (`CornerTaken/FreekickTaken/IndirectFreekickTaken/ThrowIn/GoalKick/KeeperThrow/KickOff` qualifiers) are excluded from on-ball actions — validated on the fixture where throw-ins alone were inflating LW·Z6 by ~0.30 xT. xT is no longer clipped at 0: payload carries `xt` (net), `xt_gained`, `xt_lost`; share = share of gained. Net-negative zones render red (shaded on the same magnitude scale as gains), the zone table gained ▲/▼/Net columns (losses in red), and exports show `net (▲gained ▼lost) · share`.
- **Channels/zones context follow-ups**: (1) **perspective toggle** "Created from ⇄ Arrives in" — backend returns `channels_received`/`zones_received` where actions are assigned by end coordinates (destination view surfaces receiving hot-spots, e.g. the box C·Z6 at 0.85 net xT invisible in origin view); (2) **flow arrows** — per-zone mean start→end vector of successful progressive actions (`flow_dx/dy/count`), drawn at zone centers in grid mode (needs ≥2 progressive actions); (3) **top contributor** — per channel/zone the player with the most positive xT (`top_player`, `top_player_xt`): avatar+name column in the zone table, avatar line in the channel list, and export side-table rows become avatar rows (headshot · zone · net/share · "Top: player · +xT").
- **Box sub-zones + table height** (follow-up): the three box lanes at x 88.5–105 are split at the six-yard line into Entry (88.5–99.5) and Six-Yard (99.5–105) cells — 33 zones total — so the destination view differentiates danger inside the box instead of one blob (fixture: Box Centre Entry 0.42 / Six-Yard 0.42 vs Box Right 0.07). Zone table now stretches to the full pitch-SVG height (`height: 0; min-height: 100%` grid trick, scrolls internally; capped again on the single-column breakpoint).

### Iteration 2.9 — combination overlay on the pass network (2026-07-12) — ✅ DONE
- New opt-in overlay in `PassNetworkPlotly` (off by default): "Top pass pairs" and "Passing triangles" buttons beside "Progressive actions". Computed client-side from the displayed network edges (no extra API calls, respects all active filters/windows): pairs = both directions of a link combined, top 5 by volume, drawn as thick team-color links with rank badges (`#1 · 23`); triangles = trios connected on all three sides (pair volume ≥3, relaxed to ≥1 if none), top 3 by combined volume, drawn as translucent filled triangles with rank/volume labels. Involved nodes get the gold ring + full opacity; everything else (edges, nodes, headshots) dims — same pattern as profile highlighting. Explanatory note shown while active; overlay is part of the plotly chart so Share exports it automatically.
- **CombinationPlayPanel removed** (component, its `.comb-*` CSS, and the `combination-play` API endpoint) — the overlay covers the visual story. `build_combination_play` itself stays: the insights/AI digest still uses it for the most-used pass pair bullet.

### Iteration 2.10 — corners rebuilt in Set Pieces (2026-07-12) — ✅ DONE
- **Corner view is now a plotly vertical half-pitch** (same geometry as the shots half-pitch: plotX = 68−y, plotY = x, y-range [50, 105.8]) replacing the SVG full pitch — other set-piece types keep the SVG map (now `.setpiece-pitch-svg`; the old `.comb-pitch-svg` CSS died with CombinationPlayPanel).
- **Delivery rendering**: heatmap (`histogram2dcontour`) of delivery end points + plotly **annotation arrows** (thin, arrowheaded — replacing the bold SVG lines) + end markers with hover (minute, taker, target, outcome). Colors: green led-to-goal, gold led-to-shot, team color completed, faded lost.
- **Corners won**: backend adds `types.corner.won` from the paired `CornerAwarded` (Successful) events — winning player + where it was won. Blue diamond markers on the pitch (attacking half only) + "Corners won by" card with avatars + a "Corners won" stat tile.
- **Takers & targets**: backend adds per-delivery `receiver` (first same-team touch within the follow window) and `led_to_goal`. Frontend aggregates two avatar tables: Corner takers (taken/cmp/into box/shots/goals) and Delivery targets (targeted/led to shot).
- **Export**: dynamic title ("Set Pieces — Corners"), side table with takers/targets/won-by avatar rows; plotly capture picks the half-pitch automatically. Verified in browser incl. free-kick SVG fallback.
- **Shot/goal attribution fixed**: the old 6-event/20s follow window tagged unrelated open-play shots as set-piece outcomes (false green "corner goals") and missed second-phase ones. Shots now must carry the matching `situation` tag (corner → FromCorner, free kick → SetPiece/DirectFreekick, throw-in → ThrowinSetPiece; goal kicks stay window-only) and each shot is attributed to the **most recent** delivery of that type within a per-type time cap (corner/FK 40s, throw-in 25s, GK 20s) — one delivery per shot, no double counting across consecutive corners. Validated on 68 matches vs situation-tag ground truth (single remaining diff is a data artifact: keeper credited a FromCorner goal 7' after the last corner).
- **Swing curves**: no Inswinger/Outswinger qualifier exists in the data, so swing is inferred from the kicking foot (`RightFoot`/`LeftFoot` qualifiers, ~80% of corners) × corner side — right-footer from the left corner = inswinger. Deliveries render as quadratic-bezier flight paths bowing toward goal (inswinger) or away (outswinger); unknown foot stays a straight arrow; arrowheads kept via a short tip annotation. Control point + sampled arc are clamped inside the pitch (corners start on the byline, so an unclamped goalward bow exits the field). Backend adds `swing` per corner delivery.
- **End-locations view (Opta-style)**: "Deliveries ⇄ End locations" toggle in the corner view. 14-zone mirrored map (corners normalized so the taker is always on the front-post/left side): wide + post channels, six-yard width split into thirds × two goalmouth depth rows + penalty-spot band, and three edge-of-box cells; zones shaded by share of corner endings with % labels and FRONT/BACK POST captions.
- **Green-arrow color bug fixed**: lost corners rendered goal-green because `deliveryColor` returned a pre-faded `rgba()` string that was re-wrapped in `theme.colorWithAlpha` (hex-only parser → green fallback). Colors are now plain hex with alpha applied exactly once. **Gotcha for future work: never pass an rgba() string back into `colorWithAlpha`.**

### Iteration 2.11 — other dead balls (free kicks / throw-ins / goal kicks) (2026-07-13) — ✅ DONE
- Low-frequency dead balls get **context segmentation** instead of richer geometry: count-labeled filter chips per type — free kicks All/Own-half restarts/Attacking half/Into the box; throw-ins by third **plus Short/Long throws (long = flight distance ≥ 20m ≈ top ~30% of PL throw-ins)**; goal kicks Short (own half)/Long (past halfway). Filters drive the pitch, both tables, and the export side table (filter name appended to its title).
- SVG map replaced by `DeliveryPitchPlotly`: full horizontal plotly pitch (`horizontalPitchShapes`), end-point heatmap, annotation arrows + hover markers with the same color grammar as corners (green goal / gold shot / team completed / faded lost).
- Takers & targets tables (avatars) and the export side table now render for **all** set-piece types — the backend `receiver` was already generic. Corners keep their extra views (swing curves, end zones, won-by).

### Iteration 2.12 — Entries & Penetration panel (2026-07-13) — ✅ DONE
- New backend view `territory-entries` (`services/views/entries.py`, endpoint `territory-entries`): successful open-play passes/carries crossing into the **final third**, into the **penalty box**, and out of the **own third** (build-up exits). Per entry: method (`ground_pass`/`carry`/`cross` [Cross qualifier]/`long_ball` [Longball or long Chipped]/`cutback` [byline-wide start x≥94, pulled back into the box]), entry channel (wing/half-space/centre lanes at the receiving end), and `led_to_shot`/`led_to_goal` via **same-possession** attribution (`_with_match_dynamics_possessions` possession ids). Plus `sequence` stats: passes per shot-ending possession, passes per possession, direct-attack share (≤4 passes).
- New `EntriesPenetrationPanel` (In Possession tab, between Channels and Set Pieces): scope toggle Final third/Penalty box/Build-up exits with counts; method filter chips; full-pitch plotly arrows colored by method (thicker = led to shot, green marker = goal); right column: **Penetration profile vs opponent** (per-method share bars, both teams fetched), Entry channels bars, Sequence style card (Patient/Direct tag). Top entry players table with avatars + main method.
- Export: dynamic title + side table (method shares w/ opponent, channels, top players as avatar rows, sequence lines).
- **Export legends**: Set Pieces and Entries exports mirror their HTML legends into `chartPanels` legends (lazy, view/filter-aware) — HTML legends are invisible to the canvas exporter, so any new panel with a DOM legend must do the same.

### Iteration 2.13 — Out of Possession tab (2026-07-13) — ✅ DONE
- Defensive actions table: 24px `PlayerAvatar` per row.
- GoalkeeperPanel trimmed to shot-stopping + sweeping (saves/on-target, save rate, goals prevented, xGOT faced, goals conceded, claims & pickups, sweeping actions) — the distribution pass map and pass stats were removed as off-topic for this tab (they also referenced the deleted `.comb-pitch-svg` CSS).
- New **DefensiveVulnerabilityPanel** ("Where {team} was breached", between the defensive section and the GK panel): reuses `territory-entries` for the *opponent*, coordinates rotated 180° so the defended goal is on the left (attacks arrive right→left, defending team's own left/right). Scope toggle Final third conceded / Box conceded. Red arrows/✕ = entries that became shots/goals in the same possession; contained entries keep method colors. Side cards: **Lanes breached · stop rate** (bar = share of breaches, red segment = became shots), **How the opponent came** (method mix), **Biggest threats** (opponent players w/ avatars from the opponent's squad map). Summary line names the most-exposed lane + contained-%. Export: side table + legend chartPanels.

### Iteration 2.14 — OOP polish + time filters + export fixes (2026-07-14) — ✅ DONE

**OOP tab fixes:**
- **GoalkeeperPanel fully removed** from Out of Possession tab (import + JSX deleted from `OutOfPossessionSection.tsx`); to be reintroduced later in Player Analysis.
- **nan player row bug fixed** (`defensive_actions.py`): `action_df` is filtered before `groupby("player")` to exclude rows where playerName stringified to `""`, `"nan"`, or `"none"`.
- **Defensive Vulnerability — "Half-space receives" scope**: backend `build_territory_entries` now returns a `receptions` list (final-third pass receptions with receiver lookup via next-event scan, passer, channel, in_box, led_to_shot/goal). Frontend `DefensiveVulnerabilityPanel` adds a third scope toggle; receptions are filtered to only `left_hs`/`right_hs` channels after mirroring. Markers are rendered at 0.28 alpha (very transparent) and arrows at 0.65 alpha so the pass lines dominate and dots mark the receipt point.
- **In-app legend** added to `DefensiveVulnerabilityPanel` below the pitch (`entries-method-legend` class): method colors for the active scope (or "Pass received" for the receives scope) plus "Became a shot" and "Goal conceded" swatches. `buildChartPanels` updated to match dynamically for the export.

**Juego de Posición grid overlay:**
- `EntriesPenetrationPanel` (`EntriesPitch`) and `DefensiveVulnerabilityPanel` (`BreachPitch`) both now pass `{ zoneLines: true }` to `horizontalPitchShapes`, drawing the JdP x/y bounds over the pitch in both In Possession and OOP tabs where team actions are plotted.

**Time-range filters:**
- **territory-entries endpoint**: `build_territory_entries` accepts `time_range` param; filters events before processing via `_filter_time_range`; echoes `time_range` in the response. Cache key updated.
- **EntriesPenetrationPanel** (In Possession): added `loadView(range)` and three preset buttons (Full / 1st H / 2nd H) in the toolbar. Both own-team and opponent fetches are re-issued together with the same range.
- **DefensiveVulnerabilityPanel** (OOP): added `fetchPayload(range)` and matching Full / 1st H / 2nd H buttons in the panel header.
- **1st H / 2nd H added to existing sliders**: `OutOfPossessionSection`, `InPossessionNetworkSection` — inserted between "Full" and "Open 15" in their `time-range-presets` rows. `DuelsTransitionsSection` — was missing the presets block entirely; added Full / 1st H / 2nd H / Open 15 / Close 15 before the Apply button.

**Export image empty-space fix (`captureAspect`):**
- Root cause: Plotly's `scaleanchor: "x"` + `constrain: "domain"` on pitch charts forces the data area to the pitch aspect ratio (108×71 units). With a fixed `height: 470`, roughly 22% of the captured image's vertical space is blank `plot_bgcolor` bands above and below the pitch. When scaled into the 16:9 export canvas this whitespace is visible.
- Fix: `DownloadPngButton` gains a `captureAspect?: number` prop. When set, capture height = `Math.round(clientWidth × captureAspect)` instead of `clientHeight` — both the `capturePlot` helper and the inline single-chart path are updated. For pitch visuals the correct value is `71/108` (y_range / x_range of the plotly axes), which sizes the image so the inner area exactly matches the pitch, eliminating the empty bands.
- Applied to: `EntriesPenetrationPanel`, `DefensiveVulnerabilityPanel` (always), and `SetPiecesPanel` (only when `!isCorner` — corner charts use a partial-pitch geometry and were already fine).

### Iteration 3.0 — Season baselines: match vs season comparison (2026-07-17) — ✅ DONE

**Backend — `season-baseline` view:**
- New `apps/api/app/services/season_baseline.py`: joins this match's values against the team's/player's per-match season rows from `season_stats/{league}/{season}/*.parquet` (current match excluded via matchId normalization — season parquets store `"1903353.0"`). Match values are computed with the *same definitions as the generator* (event-share possession, opp-passes/def-actions PPDA, xG>0.35 big chances) so match-vs-season is apples-to-apples. 900s TTL cache over the season loaders (they had none).
- Per metric payload: `matchValue, seasonAvg/median, p25/p75, min/max, delta, zScore, pctOfOwnMatches, gameRank, leaguePercentile, last5Avg`; players additionally per-90 fields + `leaguePercentilePer90` (league pool = players with ≥450 season mins). Small-sample rules: team baseline hidden <4 matches; player league percentiles need ≥450 season mins; per-90 match values need ≥20 match mins (`lowSample` flag).
- Dispatcher: `season-baseline` view_id in `main.py`, cache key `season-baseline-v2`, `kind="message"` for live matches. Reuses `_percentile` from `opposition.py`.
- Key-pass definition fixed: `passKey` flag (Opta) instead of `xA>0` — model-backfilled xA exists on every pass in R2 parquets, so `xA>0` counted all passes.

**Frontend — comparison idiom (three tiers):**
- `components/season/`: `baselineTypes.ts`, `SeasonDeltaChip` (▲/▼/· vs season avg, green/red/muted by z-score band ±0.25σ, glyph so meaning isn't color-alone), `DistributionStrip` (SVG min–max line, p25–p75 band, median tick, last-5 hollow tick, match dot + "Nth best of M matches" caption), `PlayerPercentileRadar` (Plotly barpolar pizza, league percentiles per-90 grouped Attacking/Possession/Defending, low-sample gated, game-rank narrative line).
- **TeamComparisonPanel**: chips beside each stat value; expanded rows show side-by-side DistributionStrips ("Season range"). **MatchDynamicsPlotly**: dashed season-avg reference lines on Possession + PPDA charts (whole-pitch third filter only; PPDA y-range extended to include the refs). **InPossessionMetricsTable** + **OutOfPossessionSection** table: per-90 delta chips (payload-driven — new metrics light up automatically). **PlayerAnalysisSection**: "Season context" radar for the primary selected player.
- Page fetches `season-baseline` alongside the active view for match-dynamics / in-possession / out-of-possession / player-analysis (r2 source only). CSS: `.season-chip`, `.season-strip*`, `.season-radar*` in globals.css near the `.team-summary-compare` block.

**Pipeline — generator reworked to a hybrid source (fixes metric divergence):**
- **Key discovery:** R2 `event_data/` is only a partial archive (~31 of 380 PL matches, no champions-league at all); SQLite is the complete archive but lacks the backfilled model metrics and has duplicated-event corruption in several matches (e.g. a Palace 36-goal row, 18k events for one match).
- `Data/generate_season_stats.py` gains `--source {hybrid,r2,sqlite}` (default **hybrid**): iterates the full SQLite match list, but per match uses the *enriched* R2 event parquet when one exists — so backfilled xG v2 / xA / xGOT / xpass / EPV flow into season stats for enriched matches without losing season coverage. `_dedupe_events` (eventId+teamId) fixes the SQLite duplicated-event corruption; matchIds are normalized (SQLite REAL → "1903350.0").
- New team columns: `xGOT, xGOT_against, xT, epv_added, prog_passes, prog_carries, box_entries, field_tilt_pct, possessions, passes_completed, xpass_exp_completed`. New player columns: `xGOT, epv_added, touches, carries, prog_carries, npxG, passes_completed, xpass_exp_completed`. All guarded by `if col in df.columns` so SQLite mode still works. Provenance columns: `source, generated_at, schema_version` (=2).
- `_backfill_team_names` also maps string-"None"/numeric teamName via TEAM_DICT (R2 parquets serialize NULL as "None"; was producing a phantom `None` team aggregating 47 WC matches).
- Pitch constants match `views/entries.py` (final third x≥70, box 88.5/13.84–54.16). `possessions` = consecutive-touch-run chains (cruder than Opta's merged definition; consistent across matches).

### Operational notes
- Season stats must be regenerated (`Data/generate_season_stats.py`) whenever new matches are scraped, per league (FIFA World Cup uses season `2026`, others `2025/2026`). **Run it AFTER model backfills** — the default `--source hybrid` overlays enriched R2 event parquets onto the full SQLite match list; bump the `season-baseline-v*` cache key in `main.py` if row definitions change (`SCHEMA_VERSION`).
- Player image map (`player_images_map.json`) should be rebuilt after transfer windows: `python Data/build_player_image_map.py`.
- API runs without `--reload`; restart after backend changes.
- Verified 2026-07-10 (headless Chrome): all 6 tabs on PL + La Liga matches — insights auto-load, form strips, stat breakdowns, third filters, lineups/avg-positions toggle, branded PNG preview, no console/page errors.
