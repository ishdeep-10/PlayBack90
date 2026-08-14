# Remote Match Ingestion Automation Plan

## Status

- **Target:** DigitalOcean Basic Droplet ($6/month, 1 GB RAM, 1 vCPU, 25 GB SSD)
- **Storage of record:** Cloudflare R2
- **Analytics database:** Remains on the local development device
- **Leagues:** Premier League, La Liga, Bundesliga, Serie A, Ligue 1, and MLS
- **Initial pilot:** MLS only
- **Event-data availability assumption:** First attempt three hours after scheduled kickoff
- **Implementation progress (2026-08-14):** Phases 1–3 implemented locally, including deadline-aware sleep, sequential execution, host locking, and soft-batch restarts; native systemd deployment package complete; DigitalOcean/Linux capacity spike still pending

## Goals

1. Capture newly completed matches without requiring the local development device to be online.
2. Upload fully processed and enriched match Parquet files directly to R2.
3. Avoid migrating or maintaining the historical analytics SQLite database on the Droplet.
4. Schedule work from known fixture kickoff times rather than continually scraping league pages.
5. Run safely within a 1 GB server by processing exactly one match at a time.
6. Make every operation idempotent, retryable, observable, and recoverable.

## Non-goals

- Hosting the web application or API on this Droplet.
- Keeping historical event data on the Droplet.
- Running multiple Firefox instances concurrently.
- Generating every historical season summary after every match.
- Replacing the local analytics database in the first release.

## Scheduling Decision

### Do not poll every 15 minutes continuously

A 15-minute dispatcher is simple and would consume very little CPU when no matches are due. It would not materially change the monthly price of an always-on Droplet. However, it is not the most efficient operational design because fixture kickoff times are already known.

The selected design is a **schedule-aware coordinator**:

1. Synchronize fixture schedules every six hours.
2. Store all kickoff times in UTC.
3. Calculate `due_at = kickoff_utc + 3 hours` for each fixture.
4. Build groups of fixtures whose `due_at` values fall within a configurable 30-minute window.
5. Sleep until the next group, retry, schedule refresh, or watchdog deadline.
6. Wake once, process the group sequentially, and calculate the next wake time.

The coordinator itself remains lightweight while sleeping. Firefox is started only when a match is actually due.

### Why not run only on weekends?

Weekend-only cron expressions would miss:

- Midweek league rounds
- Postponed and rescheduled fixtures
- Holiday schedules
- MLS matches played outside the main European weekend window
- Source retries after delayed publication

Schedule-aware execution naturally benefits from weekend clustering without encoding assumptions about days of the week.

### Match grouping

Fixtures will be sorted by `due_at`. A group contains due times within 30 minutes of the first fixture in that group. Its planned start is five minutes after the latest `due_at` in the group.

Example:

| Kickoff (UTC) | Due at | Group run |
| --- | --- | --- |
| 15:00 | 18:00 | 18:20 |
| 15:10 | 18:10 | 18:20 |
| 15:15 | 18:15 | 18:20 |
| 16:00 | 19:00 | Separate group |

Grouping reduces repeated league discovery work while preserving the three-hour publication delay.

### Safety watchdog

The coordinator will wake at least once every two hours, even when no scheduled job is present. The watchdog performs only inexpensive local-state checks and catches:

- A missed one-shot wakeup
- A coordinator restart
- A stale schedule cache
- A retry that should have run
- An overdue fixture introduced by a schedule change

A nightly reconciliation additionally compares completed official fixtures with R2 objects.

## System Architecture

```text
Official schedules
Football-Data / MLS Stats API
          |
          v
Schedule-aware coordinator
          |
          +---- sleep until next due group
          |
          v
Discover provider match URLs once per due league
          |
          v
Process matches sequentially
Firefox -> preprocessing -> enrichment -> Parquet
          |
          v
Temporary R2 upload -> verification -> final R2 key
          |
          v
Operational state + notification
```

### Sources of truth

- **Fixture expectation:** Official schedule provider
- **Successful match capture:** Final R2 object exists and passes verification
- **Retries and diagnostics:** Small worker-state database on the Droplet
- **Historical analytics:** Local SQLite database

The worker-state database is not a copy of the analytics database. It contains only fixture IDs, scheduling timestamps, attempts, errors, and R2 keys. It should remain small and can be reconstructed from schedules and R2.

## Match State Model

Each fixture moves through the following states:

```text
scheduled
   -> due
   -> resolving_source
   -> scraping
   -> validating
   -> enriching
   -> uploading
   -> uploaded

Any transient state may move to retry_scheduled.
An unrecoverable or exhausted fixture moves to needs_attention.
```

Suggested state fields:

- League and season
- Official provider fixture ID
- Provider status
- Home and away team names
- Kickoff UTC
- Due time UTC
- WhoScored match ID and URL
- Current ingestion status
- Attempt count
- Next retry time
- Final R2 object key
- Last error category and message
- Created, updated, and uploaded timestamps

## Per-match Pipeline

1. Confirm the fixture is due and not cancelled or postponed.
2. Check R2 for an existing final object.
3. Resolve the corresponding WhoScored match URL.
4. Start headless Firefox with geckodriver.
5. Scrape the match using the existing single-match path.
6. Quit Firefox in a `finally` block.
7. Validate match identity, teams, score, periods, and event coverage.
8. Apply preprocessing and current enrichment models:
   - Carries
   - xT
   - EPV
   - xA
   - xPass
   - xG
   - xGOT
9. Write one temporary Parquet file.
10. Upload to a temporary R2 object key.
11. Read object metadata or content back to verify the upload.
12. Promote it to the canonical R2 key.
13. Remove temporary local and R2 objects.
14. Mark the match uploaded and emit a notification.

Only the verified canonical R2 object makes a match complete.

## Retry Policy

| Failed attempt | Retry delay |
| --- | --- |
| 1 | 1 hour |
| 2 | 3 hours |
| 3 | 6 hours |
| 4 | 12 hours |
| 5 | 24 hours |
| Later attempts | Once daily, up to 72 hours after the first attempt |

Retryable failures include:

- Match data not yet published
- Provider page temporarily unavailable
- Firefox or WebDriver timeout
- Incomplete event payload
- Schedule/source mapping not yet available
- R2 request or verification failure

Cancelled fixtures are closed without scraping. Postponed fixtures return to `scheduled` when a new kickoff arrives.

## $6 Droplet Resource Controls

- Process one match at a time.
- Allow exactly one Firefox process.
- Start a fresh Firefox instance per match to release memory reliably.
- Configure 2 GB of swap.
- Keep no more than one temporary Parquet file on disk.
- Use a soft batch limit of eight matches before restarting the worker process.
- Resume remaining matches automatically after restart.
- Set a per-match timeout of 15 minutes initially.
- Rotate and cap logs.
- Alert at 80% RAM pressure, 70% disk usage, or repeated swap thrashing.
- Run no public web service; restrict inbound access to SSH through the firewall.

If the one-week pilot repeatedly exceeds these limits, resize to the 2 GB Droplet instead of weakening validation or running unstable jobs.

## Implementation Phases

### Phase 0 — Source and capacity spike

**Objective:** Prove the two external assumptions before building the full system.

- [ ] Run Firefox and geckodriver on a Linux environment matching the Droplet.
- [ ] Verify that a DigitalOcean datacenter IP can access the event source.
- [x] Scrape one known completed MLS match locally (Chrome fallback on macOS).
- [x] Measure local Python peak RAM and runtime as an initial baseline (344 MB RSS, 19.7 seconds; Linux cgroup measurement remains pending).
- [ ] Confirm current model artifacts load within the 1 GB limit.
- [x] Confirm R2 credentials can list, upload, verify, promote, and clean up a temporary test object.

**Exit gate:** One match is enriched and uploaded to a test R2 prefix without exceeding the target memory envelope.

### Phase 1 — Stateless direct-to-R2 match worker

**Objective:** Remove the analytics SQLite dependency from remote ingestion.

- [x] Extract a reusable single-match worker from the existing scraper.
- [x] Accept explicit league, season, fixture metadata, and match URL inputs.
- [x] Preserve canonical competition metadata during preprocessing.
- [x] Add match-level quality and enrichment-coverage validation.
- [x] Write and upload one Parquet without inserting historical events into SQLite.
- [x] Add temporary-key upload and verification.
- [x] Make an existing final R2 object an idempotent no-op before Firefox starts.
- [x] Produce a structured JSON result for every run.

**Exit gate:** Running the same match twice creates one verified R2 object and no duplicate data.

### Phase 2 — Schedule synchronization and due queue

**Objective:** Convert official schedules into reliable execution times.

- [x] Reuse Football-Data for the five European leagues.
- [x] Reuse the official MLS Stats API for MLS.
- [x] Normalize kickoff times to UTC.
- [x] Calculate three-hour due times.
- [x] Persist schedule snapshots and operational state.
- [x] Handle kickoff changes, postponements, and cancellations when rebuilding the plan.
- [x] Implement the 30-minute grouping algorithm.
- [x] Add dry-run output showing the next seven days of planned ingestion groups.

**Exit gate:** The dry-run queue accurately reflects known fixtures and automatically changes when a kickoff is updated.

### Phase 3 — Schedule-aware coordinator

**Objective:** Execute only when meaningful work is due.

- [x] Implement a lightweight coordinator managed by systemd.
- [x] Calculate the next wake from fixture groups, retries, schedule refreshes, and watchdog deadlines.
- [x] Sleep without starting Firefox.
- [x] Resolve provider URLs once per due league/season batch.
- [x] Process claimed matches sequentially.
- [x] Enforce a single-process lock.
- [x] Restart after the soft batch limit and resume the queue.
- [x] Reconstruct the next wake after a process or server restart.

**Exit gate:** A simulated week runs the expected groups with no fixed 15-minute source polling and no overlapping workers.

### Phase 4 — Failure handling and observability

**Objective:** Make unattended execution diagnosable and recoverable.

- [x] Implement the retry schedule, error categories, and terminal attention state.
- [ ] Add nightly official-fixture-to-R2 reconciliation.
- [ ] Add structured local logs with rotation.
- [ ] Add Discord success, retry, and failure summaries.
- [ ] Add a daily health summary including next run, queue depth, disk, RAM, and swap.
- [ ] Enable DigitalOcean monitoring and billing alerts.
- [ ] Ensure secrets are loaded from a protected environment file and never logged.

**Exit gate:** Simulated source, WebDriver, validation, and R2 failures retry correctly and produce actionable notifications.

### Phase 5 — Server packaging

**Objective:** Produce a reproducible native deployment for the 1 GB Droplet without Docker overhead.

- [x] Create a worker-only pinned Python requirements set.
- [x] Include Firefox ESR and pinned compatible geckodriver 0.37.1.
- [x] Include only required Python packages and repository model artifacts.
- [x] Add systemd memory, process, and writable-path limits.
- [x] Add a systemd service definition and restart policy.
- [x] Add a setup script for swap, service user, directories, and runtime dependencies.
- [x] Add a deployment and rollback runbook.

**Exit gate:** A fresh Linux host can be configured and run the dry-run queue from documented commands.

### Phase 6 — MLS production pilot

**Objective:** Validate the complete system with one active league.

- [ ] Provision the $6 Droplet.
- [ ] Enable MLS schedule synchronization only.
- [ ] Run against a test R2 prefix for the first completed match.
- [ ] Promote to the production MLS prefix after validation.
- [ ] Operate for one full week, including a weekend match group.
- [ ] Review success rate, publication delays, retries, peak memory, swap, and batch duration.
- [ ] Confirm the nightly reconciliation finds no unexplained gaps.

**Exit gate:** One week of MLS fixtures is captured without manual intervention or duplicate objects.

### Phase 7 — Six-league rollout

**Objective:** Extend the proven worker without increasing concurrency.

- [ ] Enable one European league at a time.
- [ ] Validate team and fixture matching for each league.
- [ ] Measure Saturday/Sunday queue depth and completion time.
- [ ] Keep all matches sequential even when multiple leagues overlap.
- [ ] Tune only group width, retry timing, and batch restart limits.
- [ ] Add a league-level circuit breaker so one failing source mapping does not block other leagues.

**Exit gate:** All six leagues reconcile against official completed fixtures and remain within the server resource limits.

### Phase 8 — Weekly local analytics synchronization

**Objective:** Keep the local analytics database and R2 summaries current without duplicate scraping.

- [ ] Build an R2-to-SQLite synchronization command.
- [ ] Import only R2 match IDs absent from local SQLite.
- [ ] Verify imported schemas and row counts.
- [ ] Regenerate affected league-season summaries locally.
- [ ] Upload refreshed summaries to R2.
- [ ] Produce a weekly reconciliation report.
- [ ] Document recovery when the local device misses one or more weeks.

**Exit gate:** The weekly command imports new remote matches idempotently and refreshes all affected summaries.

## Proposed Repository Layout

```text
Data/
  ingestion_worker.py
  provider_match_resolver.py
  worker_coordinator.py
  worker_executor.py
  worker_schedule.py
  worker_state.py
  worker_validation.py
  r2_match_store.py
  sync_r2_to_sqlite.py

deploy/ingestion/
  requirements.txt
  run-worker.sh
  setup-droplet.sh
  playback90-ingestion.service
  playback90-ingestion.env.example
  README.md
```

## Coordinator Commands

Planning is read-only with respect to R2 and does not start Firefox:

```bash
apps/api/.venv/bin/python Data/worker_coordinator.py \
  --league-season mls:2026
```

The MLS pilot claims at most eight due fixtures, resolves their provider URLs once, and processes them sequentially into an isolated R2 prefix:

```bash
apps/api/.venv/bin/python Data/worker_coordinator.py \
  --league-season mls:2026 \
  --execute-due \
  --batch-limit 8 \
  --key-prefix ingestion-test
```

Additional leagues are supplied by repeating `--league-season`. Provider timestamps must include an offset; every kickoff, due time, retry, lease, and wake deadline is persisted in UTC.

## Test Strategy

### Unit tests

- Due-time calculation across time zones and daylight-saving changes
- Fixture grouping boundaries
- Retry scheduling
- State transitions
- R2 key generation
- Existing-object idempotency
- Postponement and cancellation handling

### Integration tests

- Schedule provider normalization
- One known match scrape
- Enrichment schema validation
- Temporary upload, verification, and promotion
- Coordinator restart and queue recovery
- R2-to-SQLite synchronization

### Operational acceptance tests

- Peak group of at least 15 scheduled fixtures
- Firefox timeout and cleanup
- Source returns incomplete payload
- R2 unavailable during upload
- Server restart during a group
- Schedule changes after a job was queued
- Repeated execution produces no duplicate final objects

## Success Metrics

- At least 98% of normally published matches uploaded within six hours of kickoff.
- 100% of uploaded objects pass schema and identity validation.
- No duplicate canonical R2 objects.
- No overlapping Firefox processes.
- No unexplained completed-fixture gaps after nightly reconciliation.
- Peak normal RAM below 850 MB, with swap used only during short bursts.
- Less than 70% of the 25 GB disk consumed.
- Weekly local synchronization is repeatable and idempotent.

## Cost Boundary

The planned baseline is one always-on $6 Droplet. No DigitalOcean database, volume, load balancer, or backup product is required. Cloudflare R2 remains the durable data store. If the Droplet must be resized, the first fallback is the 2 GB Basic Droplet; the architecture and scheduling model remain unchanged.

## First Implementation Milestone

Implement Phases 0 and 1 together:

1. Create the worker-only direct-to-R2 path.
2. Run it locally for one known MLS match against a test prefix.
3. Capture runtime and memory measurements.
4. Confirm a second run is an idempotent no-op.

Scheduling automation should begin only after this per-match boundary is proven reliable.
