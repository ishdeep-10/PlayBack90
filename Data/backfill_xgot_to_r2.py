"""Apply the active xGOT model to existing event parquet files in R2.

The script is guarded by default: without ``--apply`` it only reports what would
change. When applying, it first copies each source parquet to a backup key and
then uploads the updated event dataframe back to the original key.

Examples:
  apps/api/.venv/bin/python -u Data/backfill_xgot_to_r2.py --league premier-league --season 2025_2026 --limit 1
  apps/api/.venv/bin/python -u Data/backfill_xgot_to_r2.py --league premier-league --season 2025_2026 --limit 1 --apply
  apps/api/.venv/bin/python -u Data/backfill_xgot_to_r2.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 5 --apply
  apps/api/.venv/bin/python -u Data/backfill_xgot_to_r2.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --batch-size 100 --batch-index 0 --skip-complete --apply
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
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
from app.services.xgot_model import apply_shot_xgot, predict_shot_xgot  # noqa: E402
from Data.xg_features import own_goal_mask, shot_mask  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "xgot" / "v1" / "backfills"


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


def _unbucket_key(key: str) -> str:
    bucket = f"{settings.r2_bucket}/"
    return key[len(bucket) :] if key.startswith(bucket) else key


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


def _apply_batch_window(files: list[str], batch_size: int | None, batch_index: int) -> list[str]:
    if batch_size is None:
        return files
    if batch_size <= 0:
        raise ValueError("--batch-size must be greater than 0")
    if batch_index < 0:
        raise ValueError("--batch-index must be 0 or greater")
    start = batch_index * batch_size
    end = start + batch_size
    print(f"Using batch window {batch_index}: files {start + 1}-{min(end, len(files))} of {len(files)}", flush=True)
    return files[start:end]


def _read_parquet(key: str) -> pd.DataFrame:
    return pd.read_parquet(f"s3://{key}", storage_options=get_storage_options())


def _jsonify_nested_value(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _normalize_object_columns_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in normalized.columns:
        if normalized[col].dtype != "object":
            continue
        has_nested_values = normalized[col].map(lambda value: isinstance(value, (dict, list))).any()
        if has_nested_values:
            normalized[col] = normalized[col].map(_jsonify_nested_value)
            continue

        non_null = normalized[col].dropna()
        if non_null.empty:
            continue
        numeric_values = pd.to_numeric(non_null, errors="coerce")
        if numeric_values.notna().all():
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
    return normalized


def _write_parquet_to_r2(df: pd.DataFrame, key: str) -> None:
    buffer = io.BytesIO()
    _normalize_object_columns_for_parquet(df).to_parquet(buffer, index=False)
    buffer.seek(0)
    fs = make_fs()
    with fs.open(key, "wb") as handle:
        handle.write(buffer.getvalue())


def _backup_key(source_key: str, run_id: str) -> str:
    source_without_bucket = _unbucket_key(source_key)
    return f"{settings.r2_bucket}/backups/xgot/{run_id}/{source_without_bucket}"


def _copy_to_backup(source_key: str, backup_key: str) -> None:
    fs = make_fs()
    with fs.open(source_key, "rb") as source, fs.open(backup_key, "wb") as backup:
        backup.write(source.read())


def _summarize_file(df: pd.DataFrame, updated: pd.DataFrame, key: str, version: str) -> dict[str, object]:
    eligible = shot_mask(df)
    own_goals = own_goal_mask(df)
    old_xgot = pd.to_numeric(df.get("xGOT", pd.Series(np.nan, index=df.index)), errors="coerce")
    new_xgot = pd.to_numeric(updated.get("xGOT", pd.Series(np.nan, index=updated.index)), errors="coerce")
    changed = ~(old_xgot.fillna(-999999).round(8).eq(new_xgot.fillna(-999999).round(8)))
    current_version = (
        updated.get("xgot_model_version", pd.Series("", index=updated.index)).fillna("").astype(str)
        if "xgot_model_version" in updated.columns
        else pd.Series("", index=updated.index)
    )
    match_id = ""
    if "matchId" in updated.columns and not updated["matchId"].dropna().empty:
        match_id = str(updated["matchId"].dropna().iloc[0])
    prediction_rows = predict_shot_xgot(df, version=version)
    on_target = int(prediction_rows.get("xgot_is_on_target", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    blocked = int(prediction_rows.get("xgot_is_blocked", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    model_rows = int(prediction_rows.get("xgot_training_eligible", pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
    return {
        "file": key,
        "match_id": match_id,
        "shots": int(eligible.sum()),
        "own_goals_cleared": int(own_goals.sum()),
        "prediction_rows": int(len(prediction_rows)),
        "on_target_shots": on_target,
        "blocked_shots": blocked,
        "model_rows": model_rows,
        "old_xgot": round(float(old_xgot[eligible].fillna(0).sum()), 3),
        "new_xgot": round(float(new_xgot[eligible].fillna(0).sum()), 3),
        "delta_xgot": round(float(new_xgot[eligible].fillna(0).sum() - old_xgot[eligible].fillna(0).sum()), 3),
        "changed_rows": int(changed.sum()),
        "versioned_rows": int(current_version.eq(version).sum()),
        "new_xgot_missing": int(new_xgot[eligible].isna().sum()),
    }


def _is_complete(summary: dict[str, object], version: str) -> bool:
    model_rows = int(summary.get("shots", 0)) + int(summary.get("own_goals_cleared", 0))
    return (
        int(summary.get("new_xgot_missing", 0)) == 0
        and int(summary.get("changed_rows", 0)) == 0
        and int(summary.get("versioned_rows", 0)) >= model_rows
    )


def backfill(
    files: list[str],
    version: str,
    output_dir: Path,
    run_label: str | None,
    apply: bool,
    force: bool,
    skip_complete: bool,
) -> None:
    if not files:
        raise RuntimeError("No parquet files found for xGOT backfill.")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    summaries: list[dict[str, object]] = []
    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] {key}", flush=True)
        df = _read_parquet(key)
        updated = apply_shot_xgot(df, version=version, force=force)
        summary = _summarize_file(df, updated, key, version)
        summary["status"] = "planned"
        if skip_complete and _is_complete(summary, version):
            summary["status"] = "skipped_complete"
            summaries.append(summary)
            print(
                f"  shots={summary['shots']} old={summary['old_xgot']:.3f} "
                f"new={summary['new_xgot']:.3f} delta={summary['delta_xgot']:+.3f} "
                f"changed_rows={summary['changed_rows']} missing_new={summary['new_xgot_missing']} "
                f"status={summary['status']}",
                flush=True,
            )
            continue
        if apply:
            backup_key = _backup_key(key, run_id)
            _copy_to_backup(key, backup_key)
            _write_parquet_to_r2(updated, key)
            summary["status"] = "applied"
            summary["backup_key"] = backup_key
        summaries.append(summary)
        print(
            f"  shots={summary['shots']} old={summary['old_xgot']:.3f} "
            f"new={summary['new_xgot']:.3f} delta={summary['delta_xgot']:+.3f} "
            f"changed_rows={summary['changed_rows']} missing_new={summary['new_xgot_missing']} "
            f"status={summary['status']}",
            flush=True,
        )

    label = f"_{run_id}" if run_id else ""
    report_json = output_dir / f"xgot_backfill_{version}{label}_summary.json"
    report_csv = output_dir / f"xgot_backfill_{version}{label}_matches.csv"
    report_json.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    pd.DataFrame(summaries).to_csv(report_csv, index=False)

    total_old = sum(float(row.get("old_xgot", 0)) for row in summaries)
    total_new = sum(float(row.get("new_xgot", 0)) for row in summaries)
    total_shots = sum(int(row.get("shots", 0)) for row in summaries)
    print("\nBackfill totals", flush=True)
    print(f"  mode: {'apply' if apply else 'plan'}", flush=True)
    print(f"  files: {len(files)}", flush=True)
    print(f"  applied files: {sum(1 for row in summaries if row.get('status') == 'applied')}", flush=True)
    print(f"  skipped complete: {sum(1 for row in summaries if row.get('status') == 'skipped_complete')}", flush=True)
    print(f"  shots: {total_shots}", flush=True)
    print(f"  old xGOT: {total_old:.3f}", flush=True)
    print(f"  new xGOT: {total_new:.3f}", flush=True)
    print(f"  delta: {total_new - total_old:+.3f}", flush=True)
    print(f"  wrote: {report_json}", flush=True)
    print(f"  wrote: {report_csv}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill v1 xGOT values into R2 event parquet files.")
    parser.add_argument("--league", default="premier-league", help="League key in R2 event_data.")
    parser.add_argument("--season", default="2025_2026", help="Season key in R2 event_data.")
    parser.add_argument("--limit", type=int, default=5, help="Limit number of files for smoke/dry run.")
    parser.add_argument(
        "--league-season",
        action="append",
        help="League/season bucket as league:season. Can be passed multiple times.",
    )
    parser.add_argument("--per-league-limit", type=int, help="Files to sample per --league-season bucket.")
    parser.add_argument("--batch-size", type=int, help="Only process one batch of the selected files.")
    parser.add_argument("--batch-index", type=int, default=0, help="Zero-based batch index when --batch-size is set.")
    parser.add_argument("--run-label", help="Optional label added to output report and backup keys.")
    parser.add_argument("--file-key", action="append", help="Specific R2 key/path to process. Can be passed multiple times.")
    parser.add_argument("--version", default="v1", help="xGOT model artifact version.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="Upload changed parquet files to R2. Omit for plan mode.")
    parser.add_argument("--force", action="store_true", help="Recompute rows already stamped with this model version.")
    parser.add_argument("--skip-complete", action="store_true", help="Skip files already complete for this model version.")
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
    files = _apply_batch_window(files, args.batch_size, args.batch_index)
    backfill(files, args.version, args.output_dir, args.run_label, args.apply, args.force, args.skip_complete)


if __name__ == "__main__":
    main()
