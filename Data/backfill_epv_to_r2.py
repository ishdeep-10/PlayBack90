"""Apply EPV values to existing event parquet files in R2.

Without ``--apply`` this script only reports what would change. When applying,
it backs up each parquet before uploading the updated dataframe.

Examples:
  apps/api/.venv/bin/python -u Data/backfill_epv_to_r2.py --league premier-league --season 2025_2026 --limit 1
  apps/api/.venv/bin/python -u Data/backfill_epv_to_r2.py --league premier-league --season 2025_2026 --limit 1 --apply
  apps/api/.venv/bin/python -u Data/backfill_epv_to_r2.py --league-season premier-league:2025_2026 --league-season laliga:2025_2026 --batch-size 50 --batch-index 0 --skip-complete --apply
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import datetime, timezone
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


DEFAULT_OUTPUT_DIR = ROOT / "models" / "epv" / "v1" / "backfills"


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
    return f"{settings.r2_bucket}/backups/epv/{run_id}/{_unbucket_key(source_key)}"


def _copy_to_backup(source_key: str, backup_key: str) -> None:
    fs = make_fs()
    with fs.open(source_key, "rb") as source, fs.open(backup_key, "wb") as backup:
        backup.write(source.read())


def _summarize_file(key: str, df: pd.DataFrame, updated: pd.DataFrame, version: str) -> dict[str, object]:
    summary = epv_quality_summary(updated)
    summary["file"] = key
    summary["match_id"] = (
        str(updated["matchId"].dropna().iloc[0])
        if "matchId" in updated.columns and not updated["matchId"].dropna().empty
        else ""
    )
    current_version = (
        updated.get("epv_model_version", pd.Series("", index=updated.index)).fillna("").astype(str)
        if "epv_model_version" in updated.columns
        else pd.Series("", index=updated.index)
    )
    eligible = updated.get("epv_action_eligible", pd.Series(False, index=updated.index)).fillna(False).astype(bool)
    old_epv = pd.to_numeric(df.get("epv_added", pd.Series(0.0, index=df.index)), errors="coerce").fillna(0.0)
    new_epv = pd.to_numeric(updated.get("epv_added", pd.Series(0.0, index=updated.index)), errors="coerce").fillna(0.0)
    changed = ~(old_epv.fillna(-999999).round(8).eq(new_epv.fillna(-999999).round(8)))
    summary["old_epv_added_total"] = round(float(old_epv[eligible].sum()), 6)
    summary["new_epv_added_total"] = round(float(new_epv[eligible].sum()), 6)
    summary["delta_epv_added_total"] = round(float(new_epv[eligible].sum() - old_epv[eligible].sum()), 6)
    summary["changed_rows"] = int((changed & eligible).sum())
    summary["versioned_rows"] = int((current_version.eq(version) & eligible).sum())
    return summary


def _is_complete(summary: dict[str, object]) -> bool:
    eligible = int(summary.get("eligible_actions", 0))
    return (
        int(summary.get("missing_epv", 0)) == 0
        and int(summary.get("changed_rows", 0)) == 0
        and int(summary.get("versioned_rows", 0)) >= eligible
    )


def run_backfill(files: list[str], version: str, output_dir: Path, apply: bool, skip_complete: bool, run_label: str | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summaries: list[dict[str, object]] = []
    for index, key in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] Scoring {key}", flush=True)
        df = _read_parquet(key)
        updated = apply_epv_values(df, version=version, force=True)
        summary = _summarize_file(key, df, updated, version)
        if skip_complete and _is_complete(summary):
            summary["status"] = "skipped_complete"
            summaries.append(summary)
            print("  skipped: already complete", flush=True)
            continue
        if apply:
            backup_key = _backup_key(key, run_id)
            _copy_to_backup(key, backup_key)
            _write_parquet_to_r2(updated, key)
            summary["status"] = "updated"
            summary["backup_key"] = backup_key
            print(f"  updated with backup {backup_key}", flush=True)
        else:
            summary["status"] = "planned"
            print("  planned only; pass --apply to write", flush=True)
        summaries.append(summary)

    label = run_label or f"epv_backfill_{run_id}"
    summary_path = output_dir / f"{label}_summary.json"
    summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"Wrote {summary_path}", flush=True)
    print(f"Mode: {'apply' if apply else 'dry-run'}", flush=True)
    print(f"Files: {len(summaries)}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply EPV values to R2 event parquet files.")
    parser.add_argument("--league")
    parser.add_argument("--season")
    parser.add_argument("--league-season", action="append", default=[])
    parser.add_argument("--per-league-limit", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--file-key", action="append", default=[])
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--batch-index", type=int, default=0)
    parser.add_argument("--version", default="v1")
    parser.add_argument("--run-label")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-complete", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    files: list[str] = [_normalize_key(key) for key in args.file_key]
    if args.league and args.season:
        files.extend(_list_files(args.league, args.season, args.limit))
    if args.league_season:
        files.extend(_list_files_for_buckets([_parse_league_season(value) for value in args.league_season], args.per_league_limit))
    if args.limit is not None and not (args.league and args.season):
        files = files[: args.limit]
    files = list(dict.fromkeys(files))
    files = _apply_batch_window(files, args.batch_size, args.batch_index)
    if not files:
        raise SystemExit("No files selected. Provide --file-key, --league/--season, or --league-season.")

    run_backfill(
        files,
        version=args.version,
        output_dir=args.output_dir,
        apply=args.apply,
        skip_complete=args.skip_complete,
        run_label=args.run_label,
    )


if __name__ == "__main__":
    main()
