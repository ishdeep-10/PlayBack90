"""Apply the active xPass model to existing event parquet files in R2.

The script is guarded by default: without ``--apply`` it only reports what would
change. When applying, it first copies each source parquet to a backup key and
then uploads the updated event dataframe back to the original key.

Examples:
  apps/api/.venv/bin/python -u Data/backfill_xpass_to_r2.py --league premier-league --season 2025_2026 --limit 1
  apps/api/.venv/bin/python -u Data/backfill_xpass_to_r2.py --league premier-league --season 2025_2026 --limit 1 --apply
  apps/api/.venv/bin/python -u Data/backfill_xpass_to_r2.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --per-league-limit 5 --apply
  apps/api/.venv/bin/python -u Data/backfill_xpass_to_r2.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --batch-size 50 --batch-index 0 --skip-complete --apply
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
from app.services.xpass_model import apply_pass_xpass  # noqa: E402


DEFAULT_OUTPUT_DIR = ROOT / "models" / "xpass" / "v1" / "backfills"


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


def _attempted_pass_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty or "type" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["type"].astype(str).eq("Pass")


def _completed_pass_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty or "type" not in df.columns or "outcomeType" not in df.columns:
        return pd.Series(False, index=df.index)
    return df["type"].astype(str).eq("Pass") & df["outcomeType"].astype(str).str.lower().eq("successful")


def _jsonify_nested_value(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _normalize_object_columns_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for column in normalized.columns:
        if normalized[column].dtype != "object":
            continue
        has_nested_values = normalized[column].map(lambda value: isinstance(value, (dict, list))).any()
        if has_nested_values:
            normalized[column] = normalized[column].map(_jsonify_nested_value)
            continue
        non_null = normalized[column].dropna()
        if non_null.empty:
            continue
        numeric_values = pd.to_numeric(non_null, errors="coerce")
        if numeric_values.notna().all():
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
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
    return f"{settings.r2_bucket}/backups/xpass/{run_id}/{source_without_bucket}"


def _copy_to_backup(source_key: str, backup_key: str) -> None:
    fs = make_fs()
    with fs.open(source_key, "rb") as source, fs.open(backup_key, "wb") as backup:
        backup.write(source.read())


def _summarize_file(df: pd.DataFrame, updated: pd.DataFrame, key: str, version: str) -> dict[str, object]:
    attempted = _attempted_pass_mask(df)
    completed = _completed_pass_mask(updated)
    old_xpass = pd.to_numeric(df.get("xPass", pd.Series(np.nan, index=df.index)), errors="coerce")
    new_xpass = pd.to_numeric(updated.get("xPass", pd.Series(np.nan, index=updated.index)), errors="coerce")
    changed = ~(old_xpass.fillna(-999999).round(8).eq(new_xpass.fillna(-999999).round(8)))
    current_version = (
        updated.get("xpass_model_version", pd.Series("", index=updated.index)).fillna("").astype(str)
        if "xpass_model_version" in updated.columns
        else pd.Series("", index=updated.index)
    )
    match_id = ""
    if "matchId" in updated.columns and not updated["matchId"].dropna().empty:
        match_id = str(updated["matchId"].dropna().iloc[0])
    new_total = float(new_xpass[attempted].fillna(0).sum())
    completed_total = int(completed.sum())
    return {
        "file": key,
        "match_id": match_id,
        "attempted_passes": int(attempted.sum()),
        "completed_passes": completed_total,
        "old_xpass": round(float(old_xpass[attempted].fillna(0).sum()), 3),
        "new_xpass": round(new_total, 3),
        "delta_xpass": round(float(new_xpass[attempted].fillna(0).sum() - old_xpass[attempted].fillna(0).sum()), 3),
        "passes_above_expected": round(completed_total - new_total, 3),
        "changed_rows": int((changed & attempted).sum()),
        "versioned_rows": int((current_version.eq(version) & attempted).sum()),
        "new_xpass_missing": int(new_xpass[attempted].isna().sum()),
    }


def _is_complete(summary: dict[str, object]) -> bool:
    attempted = int(summary.get("attempted_passes", 0))
    return (
        int(summary.get("new_xpass_missing", 0)) == 0
        and int(summary.get("changed_rows", 0)) == 0
        and int(summary.get("versioned_rows", 0)) >= attempted
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
        raise RuntimeError("No parquet files found for xPass backfill.")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    summaries: list[dict[str, object]] = []
    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] {key}", flush=True)
        try:
            df = _read_parquet(key)
            updated = apply_pass_xpass(df, version=version, force=force)
            summary = _summarize_file(df, updated, key, version)
        except Exception as exc:
            summary = {
                "file": key,
                "match_id": "",
                "attempted_passes": 0,
                "completed_passes": 0,
                "old_xpass": 0.0,
                "new_xpass": 0.0,
                "delta_xpass": 0.0,
                "passes_above_expected": 0.0,
                "changed_rows": 0,
                "versioned_rows": 0,
                "new_xpass_missing": 0,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"  failed: {summary['error']}", flush=True)
            summaries.append(summary)
            continue
        summary["status"] = "planned"
        if skip_complete and _is_complete(summary):
            summary["status"] = "skipped_complete"
            print(
                f"  skipped complete attempted={summary['attempted_passes']} new={summary['new_xpass']:.3f}",
                flush=True,
            )
            summaries.append(summary)
            continue
        if apply:
            backup = _backup_key(key, run_id)
            _copy_to_backup(key, backup)
            _write_parquet_to_r2(updated, key)
            summary["status"] = "applied"
            summary["backup_key"] = backup
            print(
                f"  applied attempted={summary['attempted_passes']} completed={summary['completed_passes']} "
                f"new={summary['new_xpass']:.3f} +/-exp={summary['passes_above_expected']:+.3f} "
                f"changed_rows={summary['changed_rows']} missing_new={summary['new_xpass_missing']}",
                flush=True,
            )
        else:
            print(
                f"  planned attempted={summary['attempted_passes']} completed={summary['completed_passes']} "
                f"new={summary['new_xpass']:.3f} +/-exp={summary['passes_above_expected']:+.3f} "
                f"changed_rows={summary['changed_rows']} missing_new={summary['new_xpass_missing']}",
                flush=True,
            )
        summaries.append(summary)

    label = f"_{run_label}" if run_label else ""
    report_json = output_dir / f"xpass_backfill_{version}{label}_summary.json"
    report_csv = output_dir / f"xpass_backfill_{version}{label}_matches.csv"
    report_json.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    pd.DataFrame(summaries).to_csv(report_csv, index=False)

    active = [row for row in summaries if row.get("status") != "skipped_complete"]
    total_completed = sum(int(row.get("completed_passes", 0)) for row in active)
    total_expected = sum(float(row.get("new_xpass", 0)) for row in active)
    print("\nBackfill summary", flush=True)
    print(f"  mode: {'apply' if apply else 'plan'}", flush=True)
    print(f"  files: {len(files)}", flush=True)
    print(f"  active files: {len(active)}", flush=True)
    print(f"  attempted passes: {sum(int(row.get('attempted_passes', 0)) for row in active)}", flush=True)
    print(f"  completed passes: {total_completed}", flush=True)
    print(f"  new xPass: {total_expected:.3f}", flush=True)
    print(f"  passes +/- expected: {total_completed - total_expected:+.3f}", flush=True)
    print(f"  wrote: {report_json}", flush=True)
    print(f"  wrote: {report_csv}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill xPass onto event parquet files in R2.")
    parser.add_argument("--league", default="premier-league", help="League key in R2 event_data.")
    parser.add_argument("--season", default="2025_2026", help="Season key in R2 event_data.")
    parser.add_argument("--limit", type=int, help="Limit number of files.")
    parser.add_argument("--league-season", action="append", help="League/season bucket as league:season.")
    parser.add_argument("--per-league-limit", type=int, help="Files to sample per --league-season bucket.")
    parser.add_argument("--file-key", action="append", help="Specific R2 key/path to process.")
    parser.add_argument("--batch-size", type=int, help="Process only this many files by batch index.")
    parser.add_argument("--batch-index", type=int, default=0, help="Zero-based batch index when --batch-size is set.")
    parser.add_argument("--run-label", help="Optional label for reports and backup namespace.")
    parser.add_argument("--version", default="v1", help="xPass model artifact version.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--apply", action="store_true", help="Upload updated parquets after backing up originals.")
    parser.add_argument("--force", action="store_true", help="Overwrite rows already stamped with the selected model version.")
    parser.add_argument("--skip-complete", action="store_true", help="Skip files already fully stamped with the selected version.")
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
    files = _apply_batch_window(files, args.batch_size, args.batch_index)
    backfill(files, args.version, args.output_dir, args.run_label, args.apply, args.force, args.skip_complete)


if __name__ == "__main__":
    main()
