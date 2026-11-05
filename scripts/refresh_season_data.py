"""One command to refresh everything the Season analysis and league tables read, after a sync.

    apps/api/.venv/bin/python scripts/refresh_season_data.py                       # build everything locally, upload nothing
    apps/api/.venv/bin/python scripts/refresh_season_data.py --upload              # ... then upload to R2
    apps/api/.venv/bin/python scripts/refresh_season_data.py --league laliga --upload

Steps (each can be skipped):
  1. export   social-media/tools/export_season_aggregates.py -> Data/dribble360/out/season_agg/   (team, player, zone, slice files)
  2. stats    Data/generate_season_stats.py --dry-run -> Data/season_stats/                       (league-table columns, xPts)
  3. upload   season_agg/ and season_stats/ -> R2, then the owner-dashboard snapshot              (only with --upload)

R2 uploads overwrite files and are outward-facing, so nothing is uploaded unless --upload is given. --prune also deletes
R2 files under season_agg/ for the chosen competitions that this run did not produce (players who left the data, etc.).
Deploys are separate (docs/deployment-handoff.md): the website reads whatever is in R2 once this has uploaded.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import boto3

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from collect_metrics import load_env  # noqa: E402

# (league key, season folder in R2 / season_stats, season label for pb90)
COMPETITIONS = [
    ("premier-league", "2026_2027", "2026/2027"), ("laliga", "2026_2027", "2026/2027"), ("serie-a", "2026_2027", "2026/2027"),
    ("ligue-1", "2026_2027", "2026/2027"), ("bundesliga", "2026_2027", "2026/2027"), ("mls", "2026", "2026"),
    ("champions-league", "2026_2027", "2026/2027"), ("europa-league", "2026_2027", "2026/2027"),
]
NOTEBOOK_PY = Path(os.environ.get("PB90_PYTHON", Path.home() / ".local/pipx/venvs/notebook/bin/python"))
API_PY = ROOT / "apps" / "api" / ".venv" / "bin" / "python"
AGG = ROOT / "Data" / "dribble360" / "out" / "season_agg"
STATS = ROOT / "Data" / "season_stats"


def step(title: str) -> float:
    print(f"\n== {title}", flush=True)
    return time.time()


def run(cmd: list[str], cwd: Path, env_extra: dict[str, str] | None = None) -> None:
    env = {**os.environ, **(env_extra or {})}
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def r2_client(env: dict[str, str]):
    return boto3.client("s3", endpoint_url=f"https://{env['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
                        aws_access_key_id=env["R2_ACCESS_KEY"], aws_secret_access_key=env["R2_SECRET_KEY"], region_name="auto")


def upload_all(comps: list[tuple[str, str, str]], prune: bool, stats: bool = True) -> None:
    env = load_env()
    s3, bucket = r2_client(env), env["R2_BUCKET"]
    jobs: list[tuple[Path, str]] = []
    for lg, season_dir, _ in comps:
        for f in (STATS / lg / season_dir).glob("*.parquet") if stats else ():
            jobs.append((f, f"season_stats/{lg}/{season_dir}/{f.name}"))
        for f in (AGG / lg / season_dir).rglob("*.json"):
            jobs.append((f, "season_agg/" + f.relative_to(AGG).as_posix()))
    if not jobs:
        sys.exit("Nothing to upload: no files were built.")

    def up(job):
        f, key = job
        s3.upload_file(str(f), bucket, key, ExtraArgs={"ContentType": "application/json" if key.endswith(".json") else "application/octet-stream"})

    with ThreadPoolExecutor(12) as ex:
        list(ex.map(up, jobs))
    print(f"uploaded {len(jobs)} files ({sum(f.stat().st_size for f, _ in jobs) / 1e6:.0f} MB)")

    if prune:
        keep = {k for _, k in jobs}
        stale: list[str] = []
        for lg, season_dir, _ in comps:
            prefix = f"season_agg/{lg}/{season_dir}/"
            for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
                stale += [o["Key"] for o in page.get("Contents", []) if o["Key"] not in keep]
        for i in range(0, len(stale), 500):
            s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in stale[i:i + 500]], "Quiet": True})
        print(f"pruned {len(stale)} stale files under season_agg/")


def dashboard_snapshot(upload: bool) -> None:
    run([str(API_PY), "scripts/collect_metrics.py"], ROOT, {"AWS_DEFAULT_REGION": "ap-south-1"})
    if upload:
        env = load_env()
        r2_client(env).upload_file(str(ROOT / "cache" / "admin_metrics.json"), env["R2_BUCKET"], "admin/metrics.json",
                                   ExtraArgs={"ContentType": "application/json"})
        print("dashboard snapshot uploaded")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--league", action="append", help="repeatable; default: all eight competitions")
    ap.add_argument("--skip-export", action="store_true", help="reuse the season_agg files already built")
    ap.add_argument("--skip-stats", action="store_true", help="reuse the season_stats files already built")
    ap.add_argument("--skip-dashboard", action="store_true", help="do not rebuild the owner-dashboard snapshot")
    ap.add_argument("--upload", action="store_true", help="upload to R2 (default: build locally only)")
    ap.add_argument("--prune", action="store_true", help="with --upload, delete season_agg files this run did not produce")
    ap.add_argument("--season-dir", help="a past season folder to upload instead of the current one, e.g. 2025_2026 (use with --skip-export --skip-stats)")
    args = ap.parse_args()

    wanted = args.league or [c[0] for c in COMPETITIONS]
    comps = [c for c in COMPETITIONS if c[0] in wanted]
    if args.season_dir:
        if not (args.skip_export and args.skip_stats):
            sys.exit("--season-dir only uploads files already built: add --skip-export --skip-stats.")
        comps = [(lg, args.season_dir, label) for lg, _, label in comps]
    unknown = set(wanted) - {c[0] for c in comps}
    if unknown:
        sys.exit(f"Unknown competition(s): {sorted(unknown)}. Known: {[c[0] for c in COMPETITIONS]}")
    if not NOTEBOOK_PY.exists() and not args.skip_export:
        sys.exit(f"pb90 python not found at {NOTEBOOK_PY} (set PB90_PYTHON).")
    t0 = time.time()

    if not args.skip_export:
        t = step("1/3 export season figures (pb90)")
        flags = [x for lg, _, _ in comps for x in ("--league", lg)]
        run([str(NOTEBOOK_PY), "tools/export_season_aggregates.py", *flags], ROOT / "social-media", {"PYTHONPATH": "."})
        print(f"   done in {time.time() - t:.0f}s")

    if not args.skip_stats:
        t = step("2/3 season stats for the league tables (xPts, form)")
        for lg, season_dir, _ in comps:
            run([str(API_PY), "generate_season_stats.py", "--source", "r2", "--season", season_dir, "--league", lg, "--dry-run"],
                ROOT / "Data", {"AWS_DEFAULT_REGION": "auto"})
        print(f"   done in {time.time() - t:.0f}s")

    step("3/3 " + ("upload to R2" if args.upload else "upload skipped (add --upload to push to R2)"))
    if args.upload:
        upload_all(comps, args.prune, stats=not args.season_dir)  # a past season uploads season_agg only
    if not args.skip_dashboard:
        dashboard_snapshot(args.upload)
    print(f"\nFinished in {time.time() - t0:.0f}s." + ("" if args.upload else " Nothing was uploaded."))
    if args.upload:
        print("R2 is updated; the site reads it directly (no deploy needed unless code changed).")


if __name__ == "__main__":
    main()
