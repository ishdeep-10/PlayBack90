# PlayBack90 Remote Ingestion Worker

This package installs the schedule-aware worker directly on a small Debian Droplet. It does not run the API, frontend, Redis, or the historical analytics database.

## Create the Droplet only after the deployment commit is pushed

Use these DigitalOcean Control Panel settings:

| Setting | Selection |
| --- | --- |
| Region | Bangalore `BLR1` (use Singapore `SGP1` only if BLR1 has no $6 capacity) |
| Image | Debian 13 x64 |
| Droplet type | Basic, Regular CPU |
| Size | 1 GiB RAM, 1 vCPU, 25 GiB SSD, 1,000 GiB transfer — $6/month |
| Authentication | SSH key; do not use password authentication |
| Networking | Public IPv4 on, default VPC, IPv6 on |
| Monitoring | Improved Metrics and Monitoring on (free) |
| Backups | Off for the pilot; R2 is the data source of record and worker state is reconstructible |
| Hostname | `playback90-ingestion-01` |
| Tag | `playback90-ingestion` |
| Extra storage/database | None |

If you want a whole-server recovery image, weekly backups add 20% to the Droplet price, making the expected total $7.20/month rather than $6.

Create a DigitalOcean Cloud Firewall for the `playback90-ingestion` tag:

- Inbound: SSH TCP 22 from your current public IP only.
- Outbound: allow all TCP, UDP, and ICMP so the worker can reach official schedules, WhoScored, GitHub package downloads, and Cloudflare R2.
- No HTTP or HTTPS inbound rule is needed; this server exposes no web service.

## Install

SSH to the server and place a clean repository checkout at `/opt/playback90`. For a private GitHub repository, use a read-only deploy key rather than a personal password or broad access token.

```bash
sudo git clone YOUR_REPOSITORY_SSH_URL /opt/playback90
cd /opt/playback90
sudo sh deploy/ingestion/setup-droplet.sh
```

The setup script installs Firefox ESR, pinned geckodriver 0.37.1, CPU-only XGBoost, a dedicated Python virtual environment, a locked-down `playback90` system user, 2 GiB swap, and the systemd unit. Python packages install without a persistent pip download cache, and Firefox profiles stay inside the worker's protected state directory. It intentionally does not start the worker before secrets are configured.

## Configure secrets

Edit the protected environment file:

```bash
sudo editor /etc/playback90/ingestion.env
```

Set the four R2 values. As of the MLS + La Liga rollout, both leagues run together:

```text
PLAYBACK90_LEAGUE_SEASONS=mls:2026,laliga:2026/2027
PLAYBACK90_INGESTION_DELAY_HOURS=2.5
PLAYBACK90_R2_KEY_PREFIX=
```

Leave `PLAYBACK90_R2_KEY_PREFIX` empty to publish directly to the real production
prefix — that is what this deployment has always actually used in practice.
Only set it to something like `ingestion-test` temporarily while smoke-testing
a brand new Droplet (see "Validate before enabling automation" below), then
clear it again before starting the real service.

`FOOTBALL_DATA_API_KEY` is **required** once any European league (La Liga, and
later Premier League/Bundesliga/Serie A/Ligue 1) is enabled — `worker_schedule.py`
syncs those leagues' official fixtures from football-data.org. It was optional
only during the original MLS-only pilot.

To receive a Discord message for every successful ingestion and every failed
attempt, create a webhook for the destination channel and set it without quotes:

```text
PLAYBACK90_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

The webhook is optional. Discord delivery errors are written to the service
journal without changing match state or triggering an ingestion retry.

## Configure the scrape proxy (needed if WhoScored blocks the Droplet's IP)

DigitalOcean IP ranges are commonly flagged by Cloudflare's bot management —
this deployment hit a hard "Sorry, you have been blocked" WAF response from
WhoScored on its original Droplet IP, independent of any code issue. If the
same thing happens to a new Droplet (check `/var/lib/playback90/discovery-debug/*.html`
after any `provider_discovery` failure — a Cloudflare block page there is the
signature), route scrape traffic through a residential proxy instead of trying
to work around it in code:

1. Sign up at a pay-as-you-go residential proxy provider (we use
   [DataImpulse](https://dataimpulse.com), ~$1/GB, no subscription). Buy the
   smallest bundle — at this project's match volume it lasts months.
2. **Whitelist this Droplet's public IP** in the provider's dashboard (IP-based
   auth, not username/password — see next point for why). Get the IP with
   `curl -s https://api.ipify.org` on the Droplet.
3. Set a **credential-free** proxy URL in `/etc/playback90/ingestion.env`:

   ```text
   PLAYBACK90_SCRAPE_PROXY_URL=socks5://gw.dataimpulse.com:823
   ```

   **Do not put a username/password in this URL.** Firefox's SOCKS5 client has
   never implemented RFC 1929 username/password authentication (a 20+ year old
   gap — see [Mozilla bug 122752](https://bugzilla.mozilla.org/show_bug.cgi?id=122752)),
   so a credentialed SOCKS5 URL fails with a generic `connectionFailure` no
   matter what preferences or extensions are tried. IP whitelisting is the only
   auth method that actually works from Firefox for SOCKS5. `_configure_proxy()`
   in `Data/main.py` raises a clear error immediately if you set one with
   embedded credentials, rather than failing cryptically later.
4. **If you ever recreate the Droplet, its public IP changes, and the proxy
   whitelist must be updated to match** — this is the single easiest step to
   forget, and forgetting it reproduces a connection failure that looks similar
   to (but is not) the original Cloudflare block.

This is opt-in and scoped to only the discovery/scraping Firefox instances
(`Data/main.py` and `Data/extract_opta_data.py`) — R2 uploads, schedule syncs,
and your own SSH session are never routed through it.

## Validate before enabling automation

Confirm the installed binaries:

```bash
firefox-esr --version
geckodriver --version
/opt/playback90/.venv-ingestion/bin/python --version
free -h
swapon --show
```

Run one known completed match through Firefox, preprocessing, every enrichment model, and validation without writing to R2:

```bash
sudo -u playback90 /opt/playback90/.venv-ingestion/bin/python \
  /opt/playback90/Data/ingestion_worker.py \
  --url 'https://1xbet.whoscored.com/matches/1952794/live/usa-major-league-soccer-2026-real-salt-lake-houston-dynamo-fc' \
  --league mls \
  --season 2026 \
  --expected-home 'Real Salt Lake' \
  --expected-away 'Houston Dynamo FC' \
  --dry-run
```

Do not enable automation if this fails because Firefox cannot start, model
validation fails, or peak memory approaches the 950 MiB hard limit. If it
fails because the source blocks the Droplet's IP (check
`/var/lib/playback90/discovery-debug/*.html` for a Cloudflare "Sorry, you have
been blocked" page after a `provider_discovery` failure), see "Configure the
scrape proxy" above rather than treating it as a code problem.

**This one-off manual command runs outside systemd, so it does not exercise
the service's sandboxing** (`PrivateTmp`, `ProtectSystem=strict`, the `/dev/shm`
size below). A command succeeding here does not guarantee it will succeed
under the actual service — we hit exactly this gap once, where every manual
retry succeeded reliably while the real automated service kept failing with
local Firefox/geckodriver connection errors, traced to `/dev/shm` starvation
under the sandbox (see the `TemporaryFileSystem=/dev/shm` line in
`playback90-ingestion.service`). To validate a command under the *real*
sandboxed conditions before trusting it, wrap it in `systemd-run` mirroring
the unit's properties instead:

```bash
systemd-run --pty --wait \
  --uid=playback90 --gid=playback90 \
  --property=PrivateTmp=true \
  --property=ProtectSystem=strict \
  --property=ProtectHome=true \
  --property=ReadWritePaths=/var/lib/playback90 \
  --property=TemporaryFileSystem=/dev/shm:size=512M,mode=1777 \
  --property=MemoryHigh=850M \
  --property=MemoryMax=950M \
  --property=EnvironmentFile=/etc/playback90/ingestion.env \
  --property=WorkingDirectory=/opt/playback90 \
  /opt/playback90/.venv-ingestion/bin/python \
    /opt/playback90/Data/worker_coordinator.py \
    --league-season mls:2026 --league-season laliga:2026/2027 \
    --execute-due --batch-limit 1 --fixture-id SOME_FIXTURE_ID
```

## Start the pilot

```bash
sudo systemctl enable --now playback90-ingestion
sudo systemctl status playback90-ingestion --no-pager
sudo journalctl -u playback90-ingestion -f
```

The service keeps no browser open while sleeping. It wakes for a due fixture/retry, schedule refresh, or two-hour watchdog. The default deployment attempts each match 2.5 hours after kickoff, then applies the five-minute group publication buffer. It processes matches sequentially and restarts itself cleanly (releasing browser/model memory) once it has claimed a cumulative total of eight fixtures across wake cycles — not eight in a single wake, since real due groups are usually much smaller than that and a per-wake check almost never triggered a restart in practice.

To retry one known failed fixture immediately, stop the resident service and run
the coordinator once with its official fixture ID:

```bash
sudo systemctl stop playback90-ingestion
(
  set -a
  . /etc/playback90/ingestion.env
  set +a
  runuser -u playback90 --preserve-environment -- \
    /opt/playback90/.venv-ingestion/bin/python \
    /opt/playback90/Data/worker_coordinator.py \
    --league-season mls:2026 \
    --league-season laliga:2026/2027 \
    --execute-due \
    --batch-limit 1 \
    --fixture-id fd-564634 \
    --source-url https://1xbet.whoscored.com/matches/1993897/live/spain-laliga-2026-2027-deportivo-alaves-getafe
)
sudo systemctl start playback90-ingestion
```

The selected claim refuses uploaded, cancelled, or postponed fixtures, and R2
match-ID checks remain idempotent.

After the first remote object under `ingestion-test/event_data/mls/2026/` is verified, clear `PLAYBACK90_R2_KEY_PREFIX`, restart the service, and capture production objects:

```bash
sudo systemctl restart playback90-ingestion
```

## Operations

```bash
sudo systemctl status playback90-ingestion --no-pager
sudo journalctl -u playback90-ingestion --since today
sudo systemctl restart playback90-ingestion
sudo systemctl stop playback90-ingestion
```

Deploy a later revision with:

```bash
cd /opt/playback90
sudo systemctl stop playback90-ingestion
sudo git pull --ff-only
sudo sh deploy/ingestion/setup-droplet.sh
sudo systemctl start playback90-ingestion
```

The operational state is `/var/lib/playback90/state.db`. Deleting it is unnecessary during normal deployment; if it is ever lost, the worker reconstructs fixture expectations from official schedules and confirms successful captures against R2 through idempotent match IDs.

## If the Droplet is destroyed or paused for a while

WhoScored's completed-match pages don't expire, and R2 is the real source of
truth (not the Droplet's local state DB), so a gap in the Droplet's uptime is
recoverable, not data loss. To catch up whatever the automated worker missed
while it was down, run the local bulk pipeline from your own machine (needs
Firefox installed locally, and the R2 + `FOOTBALL_DATA_API_KEY` values from
`/etc/playback90/ingestion.env`, or wherever you keep them, in your local `.env`):

```bash
cd Data
python run_all.py   # jobs list currently: ("usa", "mls", "2026"), ("spain", "laliga", "2026/2027")
```

This rediscovers every completed match for the configured seasons and uploads
whatever's missing from R2, independent of the Droplet's own retry bookkeeping
— it doesn't touch `/var/lib/playback90/state.db` at all. Update the `jobs`
list in `Data/run_all.py` if the active seasons change. This is also the
fastest way to test whether WhoScored is reachable from a *different* IP
(your own) when diagnosing whether a failure is Droplet-IP-specific.

## Troubleshooting

- **`provider_discovery` failure, unclear why:** check
  `/var/lib/playback90/discovery-debug/<competition>.html` and `.png`, written
  automatically on every discovery failure. A Cloudflare "Sorry, you have been
  blocked" page there means an IP block (see "Configure the scrape proxy"). An
  empty/near-empty page or a login/consent wall means something else rendered
  instead of the real site.
- **Errors like `"Tried to run command without establishing a connection"` or
  `"Failed to decode response from marionette"`:** these are *local*
  geckodriver↔Firefox failures, not network/proxy errors (Marionette is a
  localhost connection). If they only happen through the real systemd service
  and never in a manual one-off command, suspect the sandbox, not the code —
  test with the `systemd-run` wrapper above before changing anything.
- **A specific fixture repeatedly fails with `provider_url_not_found` despite
  the team names looking obviously correct:** this can be discovery quietly
  returning an incomplete candidate list for that one attempt (e.g. a slow
  proxy exit node truncating the tournament page's day-by-day pagination
  early) rather than a real matching bug. Reproducing the exact fixture against
  local discovery output is the fastest way to tell a real bug from a one-off:
  ```bash
  cd Data
  python -c "
  from main import getMatchUrls
  import json
  with open('league_urls_updated.json') as f:
      comp_urls = json.load(f)
  urls = getMatchUrls(comp_urls, 'usa-major-league-soccer', '2026')
  print([u for u in urls if 'team name substring' in str(u).lower()])
  "
  ```
  If it resolves fine here, it's very likely just proxy variance — the
  now-faster retry schedule (`worker_state.py` `RETRY_DELAYS`) should clear it
  within a couple of hours on its own.
- **Testing the proxy connection directly, bypassing Selenium entirely:**
  ```bash
  set -a; . /etc/playback90/ingestion.env; set +a
  curl -sv --max-time 25 --socks5-hostname "${PLAYBACK90_SCRAPE_PROXY_URL#socks5://}" \
    "https://1xbet.whoscored.com/regions/206/tournaments/4/spain-laliga"
  ```
  A normal `301` response with a `set-cookie: __cf_bm=...` header means the
  proxy and target are both fine — if Selenium still fails after that, the
  problem is in Firefox/geckodriver, not connectivity.
