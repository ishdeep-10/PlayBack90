"""Collect the numbers for the owner dashboard into one JSON snapshot.

Runs from the dev laptop (it has the AWS CLI, R2 keys, Clerk key and BigQuery access; the server has none of these).
Each section is independent: a failing source is recorded as {"error": ...} and the rest still run.

    apps/api/.venv/bin/python scripts/collect_metrics.py                 # writes cache/admin_metrics.json
    apps/api/.venv/bin/python scripts/collect_metrics.py --out other.json

Uploading the snapshot to R2 (for the /admin page) is a separate, explicit step: see docs/next-phase-plan.md.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import boto3
import requests

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://playback90.com"
BQ_PROJECT = "playback90-505308"
BQ_CAP_BYTES = 1024**4  # sandbox: 1 TiB / month
DRIBBLE_MONTHLY_USD = 149.0  # fixed data cost, not read from any API


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if m:
            env[m.group(1)] = m.group(2).strip("\"'")
    return env


def aws_json(*args: str):
    out = subprocess.run(["aws", *args, "--output", "json"], capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError(out.stderr.strip().splitlines()[-1] if out.stderr.strip() else "aws failed")
    return json.loads(out.stdout)


def collect_aws() -> dict:
    today = date.today()
    start = date(today.year - (today.month <= 5), (today.month - 6) % 12 + 1, 1)  # about six months back
    res = aws_json(
        "ce", "get-cost-and-usage", "--time-period", f"Start={start},End={today + timedelta(days=1)}",
        "--granularity", "MONTHLY", "--metrics", "UnblendedCost",
        "--group-by", "Type=DIMENSION,Key=RECORD_TYPE",
    )
    months = []
    for row in res["ResultsByTime"]:
        by_type = {g["Keys"][0]: float(g["Metrics"]["UnblendedCost"]["Amount"]) for g in row["Groups"]}
        usage = by_type.get("Usage", 0.0)
        credit = abs(by_type.get("Credit", 0.0))
        months.append({"month": row["TimePeriod"]["Start"][:7], "gross_usd": round(usage, 2),
                       "credits_used_usd": round(credit, 2), "net_usd": round(max(usage - credit, 0.0), 2)})
    account = aws_json("sts", "get-caller-identity")["Account"]
    budgets = [
        {"name": b["BudgetName"], "limit_usd": float(b["BudgetLimit"]["Amount"]),
         "actual_usd": float(b["CalculatedSpend"]["ActualSpend"]["Amount"]),
         "forecast_usd": float(b["CalculatedSpend"].get("ForecastedSpend", {}).get("Amount", 0))}
        for b in aws_json("budgets", "describe-budgets", "--account-id", account)["Budgets"]
    ]
    return {"months": months, "credits_used_total_usd": round(sum(m["credits_used_usd"] for m in months), 2),
            "budgets": budgets,
            "note": "Credit balance and expiry are only in the console (Billing > Credits)."}


def collect_r2(env: dict[str, str]) -> dict:
    s3 = boto3.client(
        "s3", endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=env["R2_ACCESS_KEY"], aws_secret_access_key=env["R2_SECRET_KEY"], region_name="auto",
    )
    size: dict[str, int] = defaultdict(int)
    files: dict[str, int] = defaultdict(int)
    area_size: dict[str, int] = defaultdict(int)     # first path segment: event_data, season_stats, season_agg, backups, ...
    area_files: dict[str, int] = defaultdict(int)
    newest: dict[str, datetime] = {}
    matches: dict[tuple[str, str], list[str]] = defaultdict(list)  # (league, season) -> match dates
    agg_keys: set[str] = set()
    total = 0
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=env["R2_BUCKET"]):
        for o in page.get("Contents", []):
            parts = o["Key"].split("/")
            key = "/".join(parts[:3]) if parts[0] == "playback90" and len(parts) > 3 else "/".join(parts[:2])
            size[key] += o["Size"]
            files[key] += 1
            area_size[parts[0]] += o["Size"]
            area_files[parts[0]] += 1
            total += o["Size"]
            if parts[0] == "season_agg" and len(parts) > 3:
                agg_keys.add(o["Key"])
            if key not in newest or o["LastModified"] > newest[key]:
                newest[key] = o["LastModified"]
            if len(parts) == 4 and parts[0] == "event_data" and re.match(r"\d{4}-\d{2}-\d{2}_", parts[3]):
                matches[(parts[1], parts[2])].append(parts[3][:10])
    prefixes = [{"prefix": k, "mb": round(v / 1e6, 1), "files": files[k], "last_modified": newest[k].isoformat()}
                for k, v in sorted(size.items())]
    coverage = [{"league": lg, "season": se, "matches": len(d), "first_match": min(d), "latest_match": max(d)}
                for (lg, se), d in sorted(matches.items())]
    # Season analysis builds: what each season_agg folder was made from, so a stale build shows next to the loaded matches.
    season_analysis = []
    for pref in sorted({"/".join(o.split("/")[:3]) for o in agg_keys}):
        try:
            tm = json.loads(s3.get_object(Bucket=env["R2_BUCKET"], Key=f"{pref}/team_metrics.json")["Body"].read())
            pm = json.loads(s3.get_object(Bucket=env["R2_BUCKET"], Key=f"{pref}/player_metrics.json")["Body"].read())
        except Exception:
            continue
        players = pm.get("players", [])
        _, lg, se = pref.split("/")
        season_analysis.append({"league": lg, "season": se, "matches": tm.get("matches", 0), "built_at": tm.get("generated_at", ""),
                                "players": len(players), "players_with_age": sum(1 for p in players if p.get("age") is not None)})
    free_gb = 10.0                         # Cloudflare R2 free tier; beyond it storage is $0.015 per GB-month
    total_gb = total / 1e9
    areas = [{"area": a, "mb": round(v / 1e6, 1), "files": area_files[a]} for a, v in sorted(area_size.items(), key=lambda kv: -kv[1])]
    return {"total_gb": round(total_gb, 3), "free_tier_gb": free_gb, "objects": sum(area_files.values()), "areas": areas,
            "est_monthly_usd": round(max(0.0, total_gb - free_gb) * 0.015, 2), "prefixes": prefixes, "coverage": coverage, "season_analysis": season_analysis}


def collect_clerk(env: dict[str, str]) -> dict:
    # The unsuffixed key in .env is the Development instance (local dev); production users live behind the _PROD key.
    headers = {"Authorization": f"Bearer {env['CLERK_SECRET_KEY_PROD']}"}
    total = requests.get("https://api.clerk.com/v1/users/count", headers=headers, timeout=20).json()["total_count"]
    created: list[int] = []
    active_30d = 0
    cutoff_ms = int((time.time() - 30 * 86400) * 1000)
    offset = 0
    while True:
        batch = requests.get("https://api.clerk.com/v1/users", headers=headers, timeout=30,
                             params={"limit": 500, "offset": offset, "order_by": "-created_at"}).json()
        if not isinstance(batch, list) or not batch:
            break
        for u in batch:
            created.append(u["created_at"])
            if max(u.get("last_sign_in_at") or 0, u.get("last_active_at") or 0) >= cutoff_ms:
                active_30d += 1
        offset += len(batch)
        if len(batch) < 500:
            break
    weekly: dict[str, int] = defaultdict(int)
    for ms in created:
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
        weekly[(d - timedelta(days=d.weekday())).isoformat()] += 1
    return {"total_users": total, "signed_in_last_30d": active_30d,
            "signups_per_week": [{"week": w, "signups": n} for w, n in sorted(weekly.items())[-12:]]}


def collect_site() -> dict:
    t0 = time.time()
    r = requests.get(f"{SITE}/health", timeout=20)
    return {"health_status": r.status_code, "health_ms": round((time.time() - t0) * 1000),
            "health": r.json() if r.headers.get("content-type", "").startswith("application/json") else None}


def bq_json(sql: str, max_bytes: int = 100_000_000) -> list[dict]:
    errors = []
    for region in ("us", "eu"):
        out = subprocess.run(["bq", f"--project_id={BQ_PROJECT}", "query", "--use_legacy_sql=false", "--format=json",
                              f"--maximum_bytes_billed={max_bytes}", sql.format(r=region)],
                             capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            return json.loads(out.stdout)
        errors.append(f"{region}: {out.stderr.strip().splitlines()[-1] if out.stderr.strip() else 'failed'}")
    raise RuntimeError("; ".join(errors))


def collect_vendor_competitions() -> list[dict]:
    """What Dribble holds for the current seasons (metadata tables only, about 0 GB scanned)."""
    rows = bq_json(
        "SELECT l.id AS league_id, l.name AS league, s.name AS season, "
        "COUNTIF(m.status='PLAYED') AS played, COUNTIF(m.status='FIXTURE') AS upcoming, "
        "CAST(MAX(IF(m.status='PLAYED', m.date, NULL)) AS STRING) AS latest_played "
        "FROM `dribble360.football_pro.matches` m JOIN `dribble360.football_pro.seasons` s ON s.id = m.season_id "
        "JOIN `dribble360.football_pro.leagues` l ON l.id = s.league_id "
        "WHERE s.start_date >= DATE '2026-01-01' GROUP BY 1, 2, 3 ORDER BY played DESC",
        max_bytes=2_000_000_000,
    )
    sys.path.insert(0, str(ROOT / "Data" / "dribble360"))
    from build_crosswalk import LEAGUES  # league key <-> vendor id, the same map the sync uses

    key_of = {v: k for k, v in LEAGUES.items()}
    return [{**r, "key": key_of.get(r["league_id"]), "played": int(r["played"]), "upcoming": int(r["upcoming"])}
            for r in rows]


def collect_bigquery() -> dict:
    sql = ("SELECT IFNULL(SUM(total_bytes_billed),0) AS b, COUNT(*) AS n FROM `region-{r}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT "
           "WHERE creation_time >= TIMESTAMP_TRUNC(CURRENT_TIMESTAMP(), MONTH) AND job_type='QUERY'")
    errors = []
    for region in ("us", "eu"):
        out = subprocess.run(["bq", f"--project_id={BQ_PROJECT}", "query", "--use_legacy_sql=false", "--format=json",
                              "--maximum_bytes_billed=100000000", sql.format(r=region)],
                             capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            row = json.loads(out.stdout)[0]
            used = int(row["b"])
            return {"month_bytes_billed_gb": round(used / 1e9, 1), "month_queries": int(row["n"]),
                    "cap_tib": 1, "cap_used_pct": round(100 * used / BQ_CAP_BYTES, 1),
                    "competitions": safe(collect_vendor_competitions)}
        errors.append(f"{region}: {out.stderr.strip().splitlines()[-1] if out.stderr.strip() else 'failed'}")
    raise RuntimeError("; ".join(errors))


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception as exc:  # one broken source must not hide the others
        return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "cache" / "admin_metrics.json"))
    args = ap.parse_args()
    env = load_env()
    snap = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixed_costs_usd_month": {"dribble_pro": DRIBBLE_MONTHLY_USD},
        "aws": safe(collect_aws),
        "r2": safe(collect_r2, env),
        "users": safe(collect_clerk, env),
        "site": safe(collect_site),
        "bigquery": safe(collect_bigquery),
        "revenue": {"status": "not live yet"},
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Daily history of storage and users (kept locally, last 120 days) so the dashboard can show growth.
    hist_file = out.parent / "admin_history.json"
    try:
        history = json.loads(hist_file.read_text()) if hist_file.exists() else []
    except ValueError:
        history = []
    today = date.today().isoformat()
    entry = {"date": today}
    if "error" not in snap["r2"]:
        entry.update({"r2_gb": snap["r2"]["total_gb"], "objects": snap["r2"]["objects"]})
    if "error" not in snap["users"]:
        entry["users"] = snap["users"]["total_users"]
    history = [h for h in history if h.get("date") != today] + [entry]
    history = history[-120:]
    hist_file.write_text(json.dumps(history))
    snap["history"] = history
    out.write_text(json.dumps(snap, indent=2))
    print(f"wrote {out}")
    for k, v in snap.items():
        if isinstance(v, dict) and "error" in v:
            print(f"  {k}: {v['error']}")


if __name__ == "__main__":
    main()
