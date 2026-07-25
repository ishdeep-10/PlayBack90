"""
Dry-run xPass backfill comparisons for existing event parquet files.

This script does not upload or modify any parquet. It reads existing event
files, predicts xPass with the selected model version, and writes comparison
reports for review before production backfill.

Examples:
  apps/api/.venv/bin/python Data/dry_run_xpass_backfill.py --league premier-league --season 2025_2026 --limit 5
  apps/api/.venv/bin/python Data/dry_run_xpass_backfill.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 10 --run-label top5-leagues-50
  apps/api/.venv/bin/python Data/dry_run_xpass_backfill.py --file-key playback90/event_data/premier-league/2025_2026/...
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
from app.services.xpass_model import predict_pass_xpass  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "xpass" / "v1" / "dry_runs"


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


def _attempted_pass_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "type" not in df.columns:
        return df.iloc[0:0].copy()
    return df[df["type"].astype(str).eq("Pass")].copy()


def _team_column(df: pd.DataFrame) -> str:
    if "teamName" in df.columns:
        return "teamName"
    if "team" in df.columns:
        return "team"
    return "teamId"


def _compare_file(key: str, version: str) -> tuple[pd.DataFrame, dict[str, object]]:
    df = _read_parquet(key)
    old_passes = _attempted_pass_rows(df)
    predictions = predict_pass_xpass(df, version=version)
    if old_passes.empty or predictions.empty:
        return pd.DataFrame(), {
            "file": key,
            "match_id": None,
            "attempted_passes": 0,
            "completed_passes": 0,
            "old_xpass": 0.0,
            "new_xpass": 0.0,
            "delta_xpass": 0.0,
            "status": "no_attempted_passes",
        }

    key_cols = ["matchId", "eventId"] if {"matchId", "eventId"}.issubset(old_passes.columns) else ["eventId"]
    prediction_cols = [
        column
        for column in (
            "matchId",
            "eventId",
            "xPass",
            "xpass_model_version",
            "xpass_pass_type",
            "xpass_play_pattern",
            "xpass_pass_direction",
            "xpass_completed",
        )
        if column in predictions.columns
    ]
    prediction_rows = predictions[prediction_cols].rename(columns={"xPass": "new_xPass"}).copy()
    prediction_rows = prediction_rows.drop_duplicates(subset=key_cols, keep="first")

    old = old_passes.copy()
    old["old_xPass"] = pd.to_numeric(old.get("xPass", np.nan), errors="coerce")
    old["completed_flag"] = old["outcomeType"].astype(str).str.lower().eq("successful").astype(int)
    merged = old.merge(prediction_rows, on=key_cols, how="left")
    merged["old_xPass_filled"] = pd.to_numeric(merged["old_xPass"], errors="coerce").fillna(0.0)
    merged["new_xPass"] = pd.to_numeric(merged["new_xPass"], errors="coerce")
    merged["delta_xPass"] = merged["new_xPass"].fillna(0.0) - merged["old_xPass_filled"]
    merged["file"] = key

    team_col = _team_column(merged)
    match_id = str(merged["matchId"].dropna().iloc[0]) if "matchId" in merged.columns and not merged["matchId"].dropna().empty else ""
    summary: dict[str, object] = {
        "file": key,
        "match_id": match_id,
        "attempted_passes": int(len(merged)),
        "completed_passes": int(merged["completed_flag"].sum()),
        "old_xpass": round(float(merged["old_xPass_filled"].sum()), 3),
        "new_xpass": round(float(merged["new_xPass"].fillna(0).sum()), 3),
        "delta_xpass": round(float(merged["delta_xPass"].sum()), 3),
        "old_xpass_missing": int(merged["old_xPass"].isna().sum()),
        "new_xpass_missing": int(merged["new_xPass"].isna().sum()),
        "passes_above_expected": round(float(merged["completed_flag"].sum() - merged["new_xPass"].fillna(0).sum()), 3),
        "teams": [],
        "status": "ok",
    }
    teams: list[dict[str, object]] = []
    for team, group in merged.groupby(team_col, dropna=False):
        completed = int(group["completed_flag"].sum())
        expected = float(group["new_xPass"].fillna(0).sum())
        teams.append(
            {
                "team": str(team),
                "attempted_passes": int(len(group)),
                "completed_passes": completed,
                "new_xpass": round(expected, 3),
                "passes_above_expected": round(completed - expected, 3),
            }
        )
    summary["teams"] = teams
    return merged, summary


def _compact_pass_report(rows: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "file",
        "matchId",
        "eventId",
        "minute",
        "second",
        "teamName",
        "playerName",
        "outcomeType",
        "xpass_pass_type",
        "xpass_play_pattern",
        "xpass_pass_direction",
        "old_xPass",
        "new_xPass",
        "delta_xPass",
        "xpass_model_version",
    ]
    out = rows[[column for column in columns if column in rows.columns]].copy()
    for column in ("old_xPass", "new_xPass", "delta_xPass"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").round(4)
    return out


def run_dry_run(files: list[str], version: str, output_dir: Path, run_label: str | None = None) -> None:
    if not files:
        raise RuntimeError("No parquet files found for dry run.")
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict[str, object]] = []
    pass_reports: list[pd.DataFrame] = []
    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] {key}", flush=True)
        rows, summary = _compare_file(key, version)
        summaries.append(summary)
        if not rows.empty:
            pass_reports.append(_compact_pass_report(rows))
        print(
            f"  attempted={summary['attempted_passes']} completed={summary['completed_passes']} "
            f"old={summary['old_xpass']:.3f} new={summary['new_xpass']:.3f} "
            f"+/-exp={summary.get('passes_above_expected', 0):+.3f} "
            f"missing_old={summary.get('old_xpass_missing', 0)} missing_new={summary.get('new_xpass_missing', 0)}",
            flush=True,
        )

    label = f"_{run_label}" if run_label else ""
    summary_path = output_dir / f"xpass_backfill_dry_run_{version}{label}_summary.json"
    summary_csv = output_dir / f"xpass_backfill_dry_run_{version}{label}_matches.csv"
    passes_csv = output_dir / f"xpass_backfill_dry_run_{version}{label}_passes.csv"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    pd.DataFrame([{key: value for key, value in item.items() if key != "teams"} for item in summaries]).to_csv(
        summary_csv, index=False
    )
    if pass_reports:
        pd.concat(pass_reports, ignore_index=True).to_csv(passes_csv, index=False)

    ok = [row for row in summaries if row.get("status") == "ok"]
    total_expected = sum(float(row.get("new_xpass", 0)) for row in ok)
    total_completed = sum(int(row.get("completed_passes", 0)) for row in ok)
    print("\nDry-run totals", flush=True)
    print(f"  files: {len(files)}", flush=True)
    print(f"  attempted passes: {sum(int(row.get('attempted_passes', 0)) for row in ok)}", flush=True)
    print(f"  completed passes: {total_completed}", flush=True)
    print(f"  new xPass: {total_expected:.3f}", flush=True)
    print(f"  passes +/- expected: {total_completed - total_expected:+.3f}", flush=True)
    print(f"  wrote: {summary_path}", flush=True)
    print(f"  wrote: {summary_csv}", flush=True)
    if pass_reports:
        print(f"  wrote: {passes_csv}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run xPass backfill against existing event parquet files.")
    parser.add_argument("--league", default="premier-league", help="League key in R2 event_data.")
    parser.add_argument("--season", default="2025_2026", help="Season key in R2 event_data.")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of files for smoke/dry run.")
    parser.add_argument("--league-season", action="append", help="League/season bucket as league:season.")
    parser.add_argument("--per-league-limit", type=int, help="Files to sample per --league-season bucket.")
    parser.add_argument("--run-label", help="Optional label added to output filenames.")
    parser.add_argument("--file-key", action="append", help="Specific R2 key/path to process.")
    parser.add_argument("--version", default="v1", help="xPass model artifact version.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.file_key:
        files = [_normalize_key(key) for key in args.file_key]
    elif args.league_season:
        files = _list_files_for_buckets([_parse_league_season(value) for value in args.league_season], args.per_league_limit)
    else:
        files = _list_files(args.league, args.season, args.limit)
        print(f"Found {len(files)} files for {args.league}/{args.season}", flush=True)
    run_dry_run(files, args.version, args.output_dir, args.run_label)


if __name__ == "__main__":
    main()
