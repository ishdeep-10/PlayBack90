"""Safely remove explicitly retired leagues from SQLite and Cloudflare R2.

Dry-run is the default. Applying requires both ``--apply`` and an exact
confirmation string. An audit manifest and a full SQLite backup are created
before any deletion, and retained SQLite/R2 data is verified afterward.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv


DATA_DIR = Path(__file__).resolve().parent
ROOT_DIR = DATA_DIR.parent
DB_PATH = DATA_DIR / "playback90.db"
REPORT_DIR = DATA_DIR / "cleanup_reports"
BACKUP_DIR = DATA_DIR / "database_backups"
TABLES = ("event_data", "processed_matches", "known_matches")
DEFAULT_LEAGUES = ("league-one", "champions-league", "fifa-world-cup")


def _load_r2_client():
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(DATA_DIR / ".env")
    required = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing R2 configuration: {', '.join(missing)}")
    endpoint = f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"],
    )
    return client, os.environ["R2_BUCKET"]


def _is_target_r2_key(key: str, leagues: set[str]) -> bool:
    parts = key.split("/")
    if len(parts) >= 2 and parts[0] in {"event_data", "season_stats"}:
        return parts[1] in leagues
    # Model backups preserve the original event_data/{league}/{season}/ path.
    return any(
        parts[index] == "event_data" and parts[index + 1] in leagues
        for index in range(len(parts) - 1)
    )


def _sqlite_inventory(db_path: Path) -> dict[str, Any]:
    inventory: dict[str, Any] = {}
    with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        for table in TABLES:
            rows = conn.execute(
                f"SELECT league, country, season, COUNT(*) FROM {table} "
                "GROUP BY league, country, season ORDER BY league, season"
            ).fetchall()
            inventory[table] = [
                {"league": row[0], "country": row[1], "season": row[2], "rows": row[3]}
                for row in rows
            ]
    return inventory


def _r2_inventory(client, bucket: str, leagues: set[str]):
    target: list[dict[str, Any]] = []
    retained: dict[str, tuple[int, str]] = {}
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            record = {
                "key": key,
                "size": int(obj["Size"]),
                "etag": str(obj.get("ETag", "")),
                "last_modified": obj["LastModified"].isoformat(),
            }
            if _is_target_r2_key(key, leagues):
                target.append(record)
            else:
                retained[key] = (record["size"], record["etag"])
    return sorted(target, key=lambda item: item["key"]), retained


def _summarize_r2(objects: list[dict[str, Any]]) -> dict[str, Any]:
    prefixes: dict[str, dict[str, int]] = defaultdict(lambda: {"objects": 0, "bytes": 0})
    for obj in objects:
        parts = obj["key"].split("/")
        prefix = "/".join(parts[:3]) if len(parts) >= 3 else obj["key"]
        prefixes[prefix]["objects"] += 1
        prefixes[prefix]["bytes"] += obj["size"]
    return {
        "objects": len(objects),
        "bytes": sum(item["size"] for item in objects),
        "by_prefix": dict(sorted(prefixes.items())),
    }


def _backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
        src.backup(dst, pages=10_000)
    with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if result != "ok":
        raise RuntimeError(f"Backup integrity check failed: {result}")


def _delete_and_compact_sqlite(db_path: Path, leagues: set[str], run_id: str) -> None:
    placeholders = ",".join("?" for _ in leagues)
    params = tuple(sorted(leagues))
    with sqlite3.connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for table in TABLES:
            conn.execute(f"DELETE FROM {table} WHERE league IN ({placeholders})", params)
        conn.commit()

    compact_path = db_path.with_name(f"{db_path.stem}.compact-{run_id}{db_path.suffix}")
    if compact_path.exists():
        compact_path.unlink()
    try:
        with sqlite3.connect(db_path) as conn:
            escaped = str(compact_path).replace("'", "''")
            conn.execute(f"VACUUM INTO '{escaped}'")
        with sqlite3.connect(f"file:{compact_path}?mode=ro", uri=True) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"Compacted database integrity check failed: {result}")
        os.replace(compact_path, db_path)
    finally:
        if compact_path.exists():
            compact_path.unlink()


def _delete_r2(client, bucket: str, objects: list[dict[str, Any]]) -> None:
    for start in range(0, len(objects), 1000):
        batch = objects[start : start + 1000]
        response = client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": item["key"]} for item in batch], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if errors:
            raise RuntimeError(f"R2 deletion returned errors: {errors}")


def _retained_sqlite_counts(inventory: dict[str, Any], leagues: set[str]) -> dict[str, int]:
    return {
        table: sum(row["rows"] for row in rows if row["league"] not in leagues)
        for table, rows in inventory.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", action="append", dest="leagues")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", help="Required with --apply; exact value is DELETE-RETIRED-LEAGUES")
    args = parser.parse_args()

    leagues = set(args.leagues or DEFAULT_LEAGUES)
    if args.apply and args.confirm != "DELETE-RETIRED-LEAGUES":
        raise SystemExit("--apply requires --confirm DELETE-RETIRED-LEAGUES")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    client, bucket = _load_r2_client()
    sqlite_before = _sqlite_inventory(DB_PATH)
    r2_targets, r2_retained_before = _r2_inventory(client, bucket, leagues)
    manifest = {
        "run_id": run_id,
        "mode": "apply" if args.apply else "dry-run",
        "leagues": sorted(leagues),
        "database": str(DB_PATH),
        "sqlite_before": sqlite_before,
        "r2_targets": r2_targets,
        "r2_summary": _summarize_r2(r2_targets),
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = REPORT_DIR / f"retired_leagues_{run_id}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"manifest": str(manifest_path), **manifest["r2_summary"]}, indent=2))
    if not args.apply:
        print("Dry run complete. No data was changed.")
        return

    backup_path = BACKUP_DIR / f"playback90-before-retired-leagues-{run_id}.sqlite3"
    print(f"Creating SQLite backup: {backup_path}", flush=True)
    _backup_sqlite(DB_PATH, backup_path)

    retained_sqlite_before = _retained_sqlite_counts(sqlite_before, leagues)
    print("Deleting and compacting SQLite data...", flush=True)
    _delete_and_compact_sqlite(DB_PATH, leagues, run_id)
    sqlite_after = _sqlite_inventory(DB_PATH)
    retained_sqlite_after = _retained_sqlite_counts(sqlite_after, leagues)
    if retained_sqlite_after != retained_sqlite_before:
        raise RuntimeError("Retained SQLite row counts changed; R2 deletion was not attempted.")
    for table, rows in sqlite_after.items():
        if any(row["league"] in leagues for row in rows):
            raise RuntimeError(f"Target data remains in SQLite table {table}; R2 deletion was not attempted.")

    print(f"Deleting {len(r2_targets)} manifest-listed R2 objects...", flush=True)
    _delete_r2(client, bucket, r2_targets)
    remaining_targets, r2_retained_after = _r2_inventory(client, bucket, leagues)
    if remaining_targets:
        raise RuntimeError(f"{len(remaining_targets)} target R2 objects remain")
    if r2_retained_after != r2_retained_before:
        raise RuntimeError("Retained R2 inventory changed during cleanup")

    manifest.update(
        {
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "backup": str(backup_path),
            "sqlite_after": sqlite_after,
            "database_bytes_after": DB_PATH.stat().st_size,
            "verified": True,
        }
    )
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "complete",
        "manifest": str(manifest_path),
        "backup": str(backup_path),
        "database_bytes_after": DB_PATH.stat().st_size,
        "deleted_r2_objects": len(r2_targets),
        "deleted_r2_bytes": manifest["r2_summary"]["bytes"],
    }, indent=2))


if __name__ == "__main__":
    main()
