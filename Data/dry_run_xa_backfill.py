"""
Dry-run xA backfill comparisons for existing event parquet files.

This script does not upload or modify any parquet. It reads existing event
files, predicts provider-style xA with the selected model version, and writes
comparison reports for review before production backfill.

Examples:
  apps/api/.venv/bin/python Data/dry_run_xa_backfill.py --league premier-league --season 2025_2026 --limit 5
  apps/api/.venv/bin/python Data/dry_run_xa_backfill.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 10 --run-label top5-leagues-50
  apps/api/.venv/bin/python Data/dry_run_xa_backfill.py --file-key playback90/event_data/premier-league/2025_2026/...
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
from app.services.xa_model import predict_pass_xa  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "xa" / "v1" / "dry_runs"


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


def _completed_pass_rows(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if "type" not in df.columns or "outcomeType" not in df.columns:
        return df.iloc[0:0].copy()
    return df[
        df["type"].astype(str).eq("Pass")
        & df["outcomeType"].astype(str).str.lower().eq("successful")
    ].copy()


def _team_column(df: pd.DataFrame) -> str:
    if "teamName" in df.columns:
        return "teamName"
    if "team" in df.columns:
        return "team"
    return "teamId"


def _prediction_columns(predictions: pd.DataFrame) -> list[str]:
    preferred = [
        "matchId",
        "eventId",
        "xA",
        "xa_model_version",
        "xa_pass_type",
        "xa_play_pattern",
        "xa_is_direct_shot_assist",
        "xa_target_event_id",
        "xa_target_xg",
    ]
    return [column for column in preferred if column in predictions.columns]


def _compare_file(key: str, version: str) -> tuple[pd.DataFrame, dict]:
    df = _read_parquet(key)
    old_passes = _completed_pass_rows(df)
    predictions = predict_pass_xa(df, version=version)
    if old_passes.empty or predictions.empty:
        return pd.DataFrame(), {
            "file": key,
            "match_id": None,
            "completed_passes": 0,
            "old_xa": 0.0,
            "new_xa": 0.0,
            "delta_xa": 0.0,
            "status": "no_completed_passes",
        }

    key_cols = ["matchId", "eventId"] if {"matchId", "eventId"}.issubset(old_passes.columns) else ["eventId"]
    prediction_cols = _prediction_columns(predictions)
    prediction_rows = predictions[prediction_cols].rename(columns={"xA": "new_xA"}).copy()
    prediction_rows = prediction_rows.drop_duplicates(subset=key_cols, keep="first")

    old = old_passes.copy()
    old["old_xA"] = pd.to_numeric(old.get("xA", np.nan), errors="coerce")
    merged = old.merge(prediction_rows, on=key_cols, how="left")
    merged["old_xA_filled"] = pd.to_numeric(merged["old_xA"], errors="coerce").fillna(0.0)
    merged["new_xA"] = pd.to_numeric(merged["new_xA"], errors="coerce")
    merged["delta_xA"] = merged["new_xA"].fillna(0.0) - merged["old_xA_filled"]
    merged["file"] = key

    team_col = _team_column(merged)
    match_id = str(merged["matchId"].dropna().iloc[0]) if "matchId" in merged.columns and not merged["matchId"].dropna().empty else ""
    summary = {
        "file": key,
        "match_id": match_id,
        "completed_passes": int(len(merged)),
        "old_xa": round(float(merged["old_xA_filled"].sum()), 3),
        "new_xa": round(float(merged["new_xA"].fillna(0).sum()), 3),
        "delta_xa": round(float(merged["delta_xA"].sum()), 3),
        "old_xa_missing": int(merged["old_xA"].isna().sum()),
        "new_xa_missing": int(merged["new_xA"].isna().sum()),
        "direct_shot_assist_passes": int(
            pd.Series(merged.get("xa_is_direct_shot_assist", False)).fillna(False).astype(bool).sum()
        ),
        "teams": [],
        "status": "ok",
    }
    for team, group in merged.groupby(team_col, dropna=False):
        summary["teams"].append(
            {
                "team": str(team),
                "completed_passes": int(len(group)),
                "old_xa": round(float(group["old_xA_filled"].sum()), 3),
                "new_xa": round(float(group["new_xA"].fillna(0).sum()), 3),
                "delta_xa": round(float(group["delta_xA"].sum()), 3),
                "direct_shot_assist_passes": int(
                    group.get("xa_is_direct_shot_assist", pd.Series(False, index=group.index)).fillna(False).astype(bool).sum()
                ),
            }
        )
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
        "type",
        "outcomeType",
        "xa_pass_type",
        "xa_play_pattern",
        "xa_is_direct_shot_assist",
        "xa_target_xg",
        "old_xA",
        "new_xA",
        "delta_xA",
        "xa_model_version",
    ]
    available = [column for column in columns if column in rows.columns]
    out = rows[available].copy()
    for column in ("xa_target_xg", "old_xA", "new_xA", "delta_xA"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").round(4)
    return out


def run_dry_run(files: list[str], version: str, output_dir: Path, run_label: str | None = None) -> None:
    if not files:
        raise RuntimeError("No parquet files found for dry run.")
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[dict] = []
    pass_reports: list[pd.DataFrame] = []
    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] {key}", flush=True)
        rows, summary = _compare_file(key, version)
        summaries.append(summary)
        if not rows.empty:
            pass_reports.append(_compact_pass_report(rows))
        print(
            f"  completed_passes={summary['completed_passes']} old={summary['old_xa']:.3f} "
            f"new={summary['new_xa']:.3f} delta={summary['delta_xa']:+.3f} "
            f"shot_assist_passes={summary.get('direct_shot_assist_passes', 0)} "
            f"missing_old={summary.get('old_xa_missing', 0)} missing_new={summary.get('new_xa_missing', 0)}",
            flush=True,
        )

    label = f"_{run_label}" if run_label else ""
    summary_path = output_dir / f"xa_backfill_dry_run_{version}{label}_summary.json"
    summary_csv = output_dir / f"xa_backfill_dry_run_{version}{label}_matches.csv"
    passes_csv = output_dir / f"xa_backfill_dry_run_{version}{label}_passes.csv"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    match_rows = []
    for item in summaries:
        base = {key: value for key, value in item.items() if key != "teams"}
        match_rows.append(base)
    pd.DataFrame(match_rows).to_csv(summary_csv, index=False)
    if pass_reports:
        pd.concat(pass_reports, ignore_index=True).to_csv(passes_csv, index=False)

    ok = [row for row in summaries if row.get("status") == "ok"]
    total_old = sum(float(row.get("old_xa", 0)) for row in ok)
    total_new = sum(float(row.get("new_xa", 0)) for row in ok)
    total_passes = sum(int(row.get("completed_passes", 0)) for row in ok)
    total_shot_assists = sum(int(row.get("direct_shot_assist_passes", 0)) for row in ok)
    print("\nDry-run totals", flush=True)
    print(f"  files: {len(files)}", flush=True)
    print(f"  completed passes: {total_passes}", flush=True)
    print(f"  direct shot-assist passes: {total_shot_assists}", flush=True)
    print(f"  old xA: {total_old:.3f}", flush=True)
    print(f"  new xA: {total_new:.3f}", flush=True)
    print(f"  delta: {total_new - total_old:+.3f}", flush=True)
    print(f"  wrote: {summary_path}", flush=True)
    print(f"  wrote: {summary_csv}", flush=True)
    if pass_reports:
        print(f"  wrote: {passes_csv}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run xA backfill against existing event parquet files.")
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
    parser.add_argument("--version", default="v1", help="xA model artifact version.")
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
        print(f"Found {len(files)} files for {args.league}/{args.season}", flush=True)
    run_dry_run(files, args.version, args.output_dir, args.run_label)


if __name__ == "__main__":
    main()
