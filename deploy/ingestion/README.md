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

Set the four R2 values. Leave these pilot settings unchanged initially:

```text
PLAYBACK90_LEAGUE_SEASONS=mls:2026
PLAYBACK90_R2_KEY_PREFIX=ingestion-test
```

`FOOTBALL_DATA_API_KEY` can remain unset during the MLS-only pilot. It becomes required before enabling the five European leagues.

To receive a Discord message for every successful ingestion and every failed
attempt, create a webhook for the destination channel and set it without quotes:

```text
PLAYBACK90_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

The webhook is optional. Discord delivery errors are written to the service
journal without changing match state or triggering an ingestion retry.

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

Do not enable automation if this fails because the source blocks the Droplet IP, Firefox cannot start, model validation fails, or peak memory approaches the 950 MiB hard limit.

## Start the isolated MLS pilot

```bash
sudo systemctl enable --now playback90-ingestion
sudo systemctl status playback90-ingestion --no-pager
sudo journalctl -u playback90-ingestion -f
```

The service keeps no browser open while sleeping. It wakes for a due fixture/retry, schedule refresh, or two-hour watchdog. It processes matches sequentially and exits after claiming eight; systemd starts a clean process after 15 seconds to continue the queue.

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
