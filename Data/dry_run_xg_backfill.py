"""
Dry-run xG backfill comparisons for existing event parquet files.

This script does not upload or modify any parquet. It reads existing event files,
predicts xG with the selected model version, and writes comparison reports.

Examples:
  apps/api/.venv/bin/python Data/dry_run_xg_backfill.py --league premier-league --season 2025_2026 --limit 5
  apps/api/.venv/bin/python Data/dry_run_xg_backfill.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 10 --run-label top5-leagues-50
  apps/api/.venv/bin/python Data/dry_run_xg_backfill.py --file-key playback90/event_data/premier-league/2025_2026/...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
for path in (str(ROOT), str(API_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.config import settings  # noqa: E402
from app.services.r2 import get_storage_options, make_fs  # noqa: E402
from app.services.xg_model import predict_shot_xg  # noqa: E402
from Data.xg_features import shot_mask  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "xg" / "v2" / "dry_runs"


def _require_r2_config() -> None:
    missing = [
        name
        for name, value in (
            ("R2_ACCOUNT_ID", settings.r2_account_id),
            ("R2_ACCESS_KEY", settings.r2_access_key),
            ("R2_SECRET_KEY", settings.r2_secret_key),
            ("R2_BUCKET", settings.r2_bucket),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing R2 config: {', '.join(missing)}")


def _normalize_key(key: str) -> str:
    key = key.strip()
    if key.startswith("s3://"):
        key = key[5:]
    bucket = f"{settings.r2_bucket}/"
    if not key.startswith(bucket):
        key = f"{bucket}{key.lstrip('/')}"
    return key


def _list_files(league: str, season: str, limit: int | None = None) -> list[str]:
    _require_r2_config()
    fs = make_fs()
    prefix = f"{settings.r2_bucket}/event_data/{league}/{season}/*.parquet"
    files = sorted(fs.glob(prefix))
    if limit is not None:
        files = files[:limit]
    return files


def _parse_league_season(value: str) -> tuple[str, str]:
    if ":" in value:
        league, season = value.split(":", 1)
    elif "/" in value:
        league, season = value.split("/", 1)
    else:
        raise ValueError(f"Expected league-season as league:season, got {value!r}")
    league = league.strip()
    season = season.strip()
    if not league or not season:
        raise ValueError(f"Expected league-season as league:season, got {value!r}")
    return league, season


def _list_files_for_buckets(buckets: list[tuple[str, str]], per_league_limit: int | None) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    for league, season in buckets:
        bucket_files = _list_files(league, season, per_league_limit)
        print(f"Found {len(bucket_files)} files for {league}/{season}", flush=True)
        for key in bucket_files:
            if key not in seen:
                seen.add(key)
                files.append(key)
    return files


def _read_parquet(key: str) -> pd.DataFrame:
    return pd.read_parquet(f"s3://{key}", storage_options=get_storage_options())


def _shot_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    shots = df[shot_mask(df)].copy()
    if {"matchId", "eventId"}.issubset(shots.columns):
        shots = shots.drop_duplicates(subset=["matchId", "eventId"], keep="first")
    return shots


def _team_column(df: pd.DataFrame) -> str:
    if "teamName" in df.columns:
        return "teamName"
    if "team" in df.columns:
        return "team"
    return "teamId"


def _compare_file(key: str, version: str) -> tuple[pd.DataFrame, dict]:
    df = _read_parquet(key)
    old_shots = _shot_rows(df)
    predictions = predict_shot_xg(df, version=version)
    if old_shots.empty or predictions.empty:
        return pd.DataFrame(), {
            "file": key,
            "match_id": None,
            "shots": 0,
            "old_xg": 0.0,
            "new_xg": 0.0,
            "delta_xg": 0.0,
            "status": "no_shots",
        }

    old = old_shots.copy()
    old["old_xG"] = pd.to_numeric(old.get("xG", np.nan), errors="coerce")
    key_cols = ["matchId", "eventId"] if {"matchId", "eventId"}.issubset(old.columns) else ["eventId"]
    prediction_cols = predictions[
        ["matchId", "eventId", "xG", "xg_model_version", "shot_family", "shot_distance", "shot_angle"]
    ].rename(columns={"xG": "new_xG"})
    merged = old.merge(
        prediction_cols,
        on=key_cols,
        how="left",
    )
    merged["old_xG_filled"] = pd.to_numeric(merged["old_xG"], errors="coerce").fillna(0.0)
    merged["new_xG"] = pd.to_numeric(merged["new_xG"], errors="coerce")
    merged["delta_xG"] = merged["new_xG"].fillna(0.0) - merged["old_xG_filled"]
    merged["file"] = key

    team_col = _team_column(merged)
    match_id = str(merged["matchId"].dropna().iloc[0]) if "matchId" in merged.columns and not merged["matchId"].dropna().empty else ""
    summary = {
        "file": key,
        "match_id": match_id,
        "shots": int(len(merged)),
        "old_xg": round(float(merged["old_xG_filled"].sum()), 3),
        "new_xg": round(float(merged["new_xG"].fillna(0).sum()), 3),
        "delta_xg": round(float(merged["delta_xG"].sum()), 3),
        "old_xg_missing": int(merged["old_xG"].isna().sum()),
        "new_xg_missing": int(merged["new_xG"].isna().sum()),
        "teams": [],
        "status": "ok",
    }
    for team, group in merged.groupby(team_col, dropna=False):
        summary["teams"].append(
            {
                "team": str(team),
                "shots": int(len(group)),
                "old_xg": round(float(group["old_xG_filled"].sum()), 3),
                "new_xg": round(float(group["new_xG"].fillna(0).sum()), 3),
                "delta_xg": round(float(group["delta_xG"].sum()), 3),
            }
        )
    return merged, summary


def _compact_shot_report(rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "file",
        "matchId",
        "eventId",
        "minute",
        "second",
        "teamName",
        "playerName",
        "type",
        "shot_family",
        "shot_distance",
        "old_xG",
        "new_xG",
        "delta_xG",
        "xg_model_version",
    ]
    available = [col for col in columns if col in rows.columns]
    out = rows[available].copy()
    for col in ("old_xG", "new_xG", "delta_xG", "shot_distance"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(4)
    return out


def run_dry_run(files: list[str], version: str, output_dir: Path, run_label: str | None = None) -> None:
    if not files:
        raise RuntimeError("No parquet files found for dry run.")
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    shot_reports: list[pd.DataFrame] = []
    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] {key}", flush=True)
        rows, summary = _compare_file(key, version)
        summaries.append(summary)
        if not rows.empty:
            shot_reports.append(_compact_shot_report(rows))
        print(
            f"  shots={summary['shots']} old={summary['old_xg']:.3f} "
            f"new={summary['new_xg']:.3f} delta={summary['delta_xg']:+.3f} "
            f"missing_old={summary.get('old_xg_missing', 0)} missing_new={summary.get('new_xg_missing', 0)}",
            flush=True,
        )

    label = f"_{run_label}" if run_label else ""
    summary_path = output_dir / f"xg_backfill_dry_run_{version}{label}_summary.json"
    summary_csv = output_dir / f"xg_backfill_dry_run_{version}{label}_matches.csv"
    shots_csv = output_dir / f"xg_backfill_dry_run_{version}{label}_shots.csv"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    match_rows = []
    for item in summaries:
        base = {k: v for k, v in item.items() if k != "teams"}
        match_rows.append(base)
    pd.DataFrame(match_rows).to_csv(summary_csv, index=False)
    if shot_reports:
        pd.concat(shot_reports, ignore_index=True).to_csv(shots_csv, index=False)

    ok = [row for row in summaries if row.get("status") == "ok"]
    total_old = sum(float(row.get("old_xg", 0)) for row in ok)
    total_new = sum(float(row.get("new_xg", 0)) for row in ok)
    total_shots = sum(int(row.get("shots", 0)) for row in ok)
    print("\nDry-run totals", flush=True)
    print(f"  files: {len(files)}", flush=True)
    print(f"  shots: {total_shots}", flush=True)
    print(f"  old xG: {total_old:.3f}", flush=True)
    print(f"  new xG: {total_new:.3f}", flush=True)
    print(f"  delta: {total_new - total_old:+.3f}", flush=True)
    print(f"  wrote: {summary_path}", flush=True)
    print(f"  wrote: {summary_csv}", flush=True)
    if shot_reports:
        print(f"  wrote: {shots_csv}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run xG backfill against existing event parquet files.")
    parser.add_argument("--league", default="premier-league", help="League key in R2 event_data.")
    parser.add_argument("--season", default="2025_2026", help="Season key in R2 event_data.")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of files for smoke/dry run.")
    parser.add_argument(
        "--league-season",
        action="append",
        help="League/season bucket as league:season. Can be passed multiple times.",
    )
    parser.add_argument("--per-league-limit", type=int, help="Files to sample per --league-season bucket.")
    parser.add_argument("--run-label", help="Optional label added to output filenames.")
    parser.add_argument("--file-key", action="append", help="Specific R2 key/path to process. Can be passed multiple times.")
    parser.add_argument("--version", default="v2", help="xG model artifact version.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.file_key:
        files = [_normalize_key(key) for key in args.file_key]
    elif args.league_season:
        buckets = [_parse_league_season(value) for value in args.league_season]
        files = _list_files_for_buckets(buckets, args.per_league_limit)
    else:
        files = _list_files(args.league, args.season, args.limit)
    run_dry_run(files, version=args.version, output_dir=args.output_dir, run_label=args.run_label)


if __name__ == "__main__":
    main()
