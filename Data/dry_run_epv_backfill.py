"""Dry-run EPV scoring for existing event parquet files.

The script reads event files, applies the active EPV grid in memory, and writes
comparison summaries. It does not upload or modify any parquet.

Examples:
  apps/api/.venv/bin/python Data/dry_run_epv_backfill.py --league premier-league --season 2025_2026 --limit 5
  apps/api/.venv/bin/python Data/dry_run_epv_backfill.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 5 --run-label top5-smoke
  apps/api/.venv/bin/python Data/dry_run_epv_backfill.py --file-key playback90/event_data/premier-league/2025_2026/...
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
for path in (str(ROOT), str(API_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from app.config import settings  # noqa: E402
from app.services.epv_model import apply_epv_values, epv_quality_summary  # noqa: E402
from app.services.r2 import get_storage_options, make_fs  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "epv" / "v1" / "dry_runs"


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


def _list_files(league: str, season: str, limit: int | None = None) -> list[str]:
    _require_r2_config()
    fs = make_fs()
    files = sorted(fs.glob(f"{settings.r2_bucket}/event_data/{league}/{season}/*.parquet"))
    return files[:limit] if limit is not None else files


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


def _team_column(df: pd.DataFrame) -> str:
    if "teamName" in df.columns:
        return "teamName"
    if "team" in df.columns:
        return "team"
    return "teamId"


def _summarize_file(key: str, df: pd.DataFrame, updated: pd.DataFrame) -> dict[str, object]:
    summary = epv_quality_summary(updated)
    summary["file"] = key
    summary["match_id"] = (
        str(updated["matchId"].dropna().iloc[0])
        if "matchId" in updated.columns and not updated["matchId"].dropna().empty
        else ""
    )
    old_epv = pd.to_numeric(df.get("epv_added", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0)
    new_epv = pd.to_numeric(updated.get("epv_added", pd.Series(0.0, index=updated.index)), errors="coerce").fillna(0.0)
    eligible = updated.get("epv_action_eligible", pd.Series(False, index=updated.index)).fillna(False).astype(bool)
    summary["old_epv_added_total"] = round(float(old_epv[eligible].sum()), 6)
    summary["new_epv_added_total"] = round(float(new_epv[eligible].sum()), 6)
    summary["delta_epv_added_total"] = round(float(new_epv[eligible].sum() - old_epv[eligible].sum()), 6)
    summary["teams"] = []
    team_col = _team_column(updated)
    if team_col in updated.columns:
        for team, group in updated[eligible].groupby(team_col, dropna=False):
            values = pd.to_numeric(group.get("epv_added"), errors="coerce").fillna(0.0)
            summary["teams"].append(
                {
                    "team": str(team),
                    "eligible_actions": int(len(group)),
                    "epv_added": round(float(values.sum()), 6),
                    "positive_epv": round(float(values[values > 0].sum()), 6),
                    "negative_epv": round(float(values[values < 0].sum()), 6),
                }
            )
    return summary


def _compact_action_report(updated: pd.DataFrame, file_key: str) -> pd.DataFrame:
    eligible = updated.get("epv_action_eligible", pd.Series(False, index=updated.index)).fillna(False).astype(bool)
    actions = updated[eligible].copy()
    actions["file"] = file_key
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
        "x",
        "y",
        "endX",
        "endY",
        "epv_start",
        "epv_end",
        "epv_added",
        "epv_model_version",
        "epv_grid_version",
    ]
    out = actions[[column for column in columns if column in actions.columns]].copy()
    for column in ("epv_start", "epv_end", "epv_added"):
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce").round(6)
    return out


def run_dry_run(files: list[str], version: str, output_dir: Path, run_label: str | None = None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    action_reports: list[pd.DataFrame] = []
    for index, key in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] Scoring {key}", flush=True)
        df = _read_parquet(key)
        updated = apply_epv_values(df, version=version, force=True)
        summaries.append(_summarize_file(key, df, updated))
        action_reports.append(_compact_action_report(updated, key))

    label = run_label or "epv-dry-run"
    summary_path = output_dir / f"{label}_summary.json"
    actions_path = output_dir / f"{label}_actions.csv"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    pd.concat(action_reports, ignore_index=True).to_csv(actions_path, index=False)
    total_eligible = sum(int(item.get("eligible_actions", 0)) for item in summaries)
    total_missing = sum(int(item.get("missing_epv", 0)) for item in summaries)
    total_epv = sum(float(item.get("new_epv_added_total", 0.0)) for item in summaries)
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {actions_path}", flush=True)
    print(f"Eligible actions: {total_eligible} | missing EPV: {total_missing} | EPV added: {total_epv:.6f}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run EPV scoring for R2 event parquet files.")
    parser.add_argument("--league")
    parser.add_argument("--season")
    parser.add_argument("--league-season", action="append", default=[])
    parser.add_argument("--per-league-limit", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--file-key", action="append", default=[])
    parser.add_argument("--version", default="v1")
    parser.add_argument("--run-label")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    files: list[str] = [_normalize_key(key) for key in args.file_key]
    if args.league and args.season:
        files.extend(_list_files(args.league, args.season, args.limit))
    if args.league_season:
        files.extend(_list_files_for_buckets([_parse_league_season(value) for value in args.league_season], args.per_league_limit))
    if args.limit is not None and not (args.league and args.season):
        files = files[: args.limit]
    files = list(dict.fromkeys(files))
    if not files:
        raise SystemExit("No files selected. Provide --file-key, --league/--season, or --league-season.")

    run_dry_run(files, version=args.version, output_dir=args.output_dir, run_label=args.run_label)


if __name__ == "__main__":
    main()
