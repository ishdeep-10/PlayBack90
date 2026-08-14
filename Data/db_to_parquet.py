"""Upload selected, not-yet-uploaded SQLite matches to Cloudflare R2.

This command never applies retention or deletes objects. Retention is an
explicit, separately reviewed operation handled by cleanup tooling.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sqlite3
from pathlib import Path

import boto3
import pandas as pd
from dotenv import load_dotenv


DATA_DIR = Path(__file__).resolve().parent
ROOT_DIR = DATA_DIR.parent
DB_PATH = DATA_DIR / "playback90.db"


def _clean(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))


def _match_id_text(value: object) -> str:
    try:
        numeric = float(value)
        return str(int(numeric)) if numeric.is_integer() else str(value)
    except (TypeError, ValueError):
        return str(value)


def _load_config() -> tuple[object, str]:
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


def _selected_match_ids(
    conn: sqlite3.Connection,
    league: str | None,
    season: str | None,
    limit: int | None,
) -> list[str]:
    where = ["uploaded = 0"]
    params: list[object] = []
    if league:
        where.append("league = ?")
        params.append(league)
    if season:
        where.append("season = ?")
        params.append(season)
    query = "SELECT matchId FROM processed_matches WHERE " + " AND ".join(where)
    query += " ORDER BY startDate, matchId"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    return [str(row[0]) for row in conn.execute(query, params)]


def _read_match(conn: sqlite3.Connection, match_id: str) -> pd.DataFrame:
    # event_data historically stores matchId as REAL while processed_matches
    # stores TEXT. Numeric comparison handles both representations safely.
    try:
        lookup: object = float(match_id)
    except ValueError:
        lookup = match_id
    return pd.read_sql_query("SELECT * FROM event_data WHERE matchId = ?", conn, params=(lookup,))


def _object_key(df: pd.DataFrame, league: str, season: str, match_id: str) -> str:
    dates = pd.to_datetime(df["startDate"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("match has no valid startDate")
    home_ids = df.loc[df["h_a"].astype(str) == "h", "teamId"].dropna()
    away_ids = df.loc[df["h_a"].astype(str) == "a", "teamId"].dropna()
    if home_ids.empty or away_ids.empty:
        raise ValueError("match has no resolvable home/away team IDs")
    scores = df["ftScore"].dropna()
    score = scores.iloc[0] if not scores.empty else "NA"
    filename = "_".join(
        (
            dates.iloc[0].strftime("%Y-%m-%d"),
            _clean(_match_id_text(match_id)),
            _clean(home_ids.iloc[0]),
            "vs",
            _clean(away_ids.iloc[0]),
            _clean(score),
        )
    )
    return f"event_data/{_clean(league)}/{_clean(season)}/{filename}.parquet"


def upload_pending(
    *,
    league: str | None = None,
    season: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> list[str]:
    if limit is not None and limit <= 0:
        raise ValueError("limit must be greater than zero")
    client, bucket = _load_config()
    uploaded: list[str] = []
    with sqlite3.connect(DB_PATH) as conn:
        match_ids = _selected_match_ids(conn, league, season, limit)
        if not match_ids:
            print("No matches to process.")
            return []
        print(f"Selected {len(match_ids)} pending matches.")
        for match_id in match_ids:
            df = _read_match(conn, match_id)
            if df.empty:
                raise RuntimeError(f"No event rows found for pending match {match_id}")
            match_league = str(df["league"].iloc[0])
            match_season = str(df["season"].iloc[0])
            key = _object_key(df, match_league, match_season, match_id)
            if dry_run:
                print(f"Would upload {key}")
                continue

            string_cols = ("league", "season", "matchId", "teamName", "h_a", "ftScore", "teamId")
            for column in string_cols:
                if column in df.columns:
                    df[column] = df[column].fillna("").astype(str)
            buffer = io.BytesIO()
            df.to_parquet(buffer, index=False)
            buffer.seek(0)
            client.upload_fileobj(buffer, bucket, key)
            conn.execute("UPDATE processed_matches SET uploaded = 1 WHERE matchId = ?", (match_id,))
            conn.commit()
            uploaded.append(key)
            print(f"Uploaded {key}")
    return uploaded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", help="Only upload this canonical league key")
    parser.add_argument("--season", help="Only upload this database season label")
    parser.add_argument("--limit", type=int, help="Maximum matches to upload")
    parser.add_argument("--dry-run", action="store_true", help="Print selected object keys without uploading")
    args = parser.parse_args()
    upload_pending(league=args.league, season=args.season, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
