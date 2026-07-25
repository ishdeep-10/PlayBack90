"""
Build the canonical shot-level dataset for xG model training.

Examples:
  python Data/build_xg_training_data.py
  python Data/build_xg_training_data.py --league premier-league --season 2025/2026
  python Data/build_xg_training_data.py --limit-matches 50 --output models/data/xg_training_sample.parquet
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from xg_features import PENALTY_XG, build_shot_feature_table, training_frame


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "Data" / "playback90.db"
DEFAULT_OUTPUT = ROOT / "models" / "data" / "xg_training_shots.parquet"
DEFAULT_REPORT = ROOT / "models" / "data" / "xg_training_audit.json"


def _league_season_groups(db_path: Path) -> list[tuple[str, str, int]]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT league, season, COUNT(DISTINCT matchId)
            FROM event_data
            GROUP BY league, season
            ORDER BY league, season
            """
        ).fetchall()
    return [(str(league), str(season), int(count)) for league, season, count in rows]


def _match_ids(db_path: Path, league: str | None, season: str | None, limit_matches: int | None, match_offset: int = 0) -> list[object]:
    where = []
    params: list[object] = []
    if league:
        where.append("league = ?")
        params.append(league)
    if season:
        where.append("season = ?")
        params.append(season)
    event_where = f"WHERE {' AND '.join(where)}" if where else ""
    limit_clause = ""
    if limit_matches:
        limit_clause = " LIMIT ? OFFSET ?"
        params.extend([limit_matches, match_offset])
    if where:
        event_where = f"{event_where} AND matchId IS NOT NULL"
    else:
        event_where = "WHERE matchId IS NOT NULL"
    query = f"SELECT DISTINCT matchId FROM event_data {event_where} ORDER BY matchId{limit_clause}"
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute(query, params).fetchall()]


def _read_match_events(db_path: Path, match_id: object) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM event_data WHERE matchId = ?", conn, params=[match_id])


def _read_events(db_path: Path, league: str | None, season: str | None, limit_matches: int | None, match_offset: int = 0) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    where = []
    params: list[object] = []
    if league:
        where.append("league = ?")
        params.append(league)
    if season:
        where.append("season = ?")
        params.append(season)

    match_limit_clause = ""
    if limit_matches:
        match_where = f"WHERE {' AND '.join(where)}" if where else ""
        match_limit_clause = (
            "matchId IN ("
            f"SELECT DISTINCT matchId FROM event_data {match_where} "
            "ORDER BY matchId LIMIT ? OFFSET ?"
            ")"
        )
        params_for_events = params + [limit_matches, match_offset]
        event_where = f"WHERE {match_limit_clause}"
    else:
        params_for_events = params
        event_where = f"WHERE {' AND '.join(where)}" if where else ""

    query = f"SELECT * FROM event_data {event_where}"
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query(query, conn, params=params_for_events)


def _audit(shots: pd.DataFrame, model_training: pd.DataFrame) -> dict:
    if shots.empty:
        return {"shots": 0, "training_shots": 0}

    missing_xy = int(shots[["x", "y"]].isna().any(axis=1).sum())
    impossible_xy = int(((shots["x"] < 0) | (shots["x"] > 105) | (shots["y"] < 0) | (shots["y"] > 68)).sum())
    duplicates = int(shots.duplicated(subset=[col for col in ("matchId", "eventId") if col in shots.columns]).sum())
    goals = int(shots["isGoal"].sum())
    penalties = int((shots["shot_family"] == "penalty").sum())
    deep_or_implausible = int(
        (
            (pd.to_numeric(shots["x"], errors="coerce") < 52.5)
            | (pd.to_numeric(shots["shot_distance"], errors="coerce") > 60)
        ).sum()
    )

    def count_by(column: str) -> dict:
        if column not in shots.columns:
            return {}
        return {str(k): int(v) for k, v in shots[column].fillna("unknown").value_counts().sort_index().items()}

    report = {
        "shots": int(len(shots)),
        "training_shots_excluding_fixed_penalties": int(len(model_training)),
        "goals": goals,
        "goal_rate": round(goals / max(1, len(shots)), 4),
        "penalties_fixed_value": PENALTY_XG,
        "penalties": penalties,
        "deep_or_implausible_shots_excluded_from_training": deep_or_implausible,
        "missing_xy": missing_xy,
        "impossible_xy": impossible_xy,
        "duplicate_match_event_ids": duplicates,
        "by_league": count_by("league"),
        "by_season": count_by("season"),
        "by_shot_family": count_by("shot_family"),
        "by_body_part": count_by("body_part"),
        "by_situation": count_by("situation_clean"),
        "by_type": count_by("type"),
    }
    if "xG" in shots.columns:
        existing_xg = pd.to_numeric(shots["xG"], errors="coerce")
        report["existing_xg_missing"] = int(existing_xg.isna().sum())
        report["existing_xg_total"] = round(float(existing_xg.fillna(0).sum()), 3)
    return report


def build_training_data(
    db_path: Path = DEFAULT_DB,
    output: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    league: str | None = None,
    season: str | None = None,
    limit_matches: int | None = None,
    match_offset: int = 0,
) -> pd.DataFrame:
    if league is None and season is None and limit_matches is None:
        frames: list[pd.DataFrame] = []
        groups = _league_season_groups(db_path)
        print(f"Building xG training data across {len(groups)} league/season groups")
        for group_idx, (group_league, group_season, match_count) in enumerate(groups, start=1):
            print(f"=== [{group_idx}/{len(groups)}] {group_league} {group_season} ({match_count} matches) ===")
            group_match_ids = _match_ids(db_path, group_league, group_season, None)
            group_frames: list[pd.DataFrame] = []
            for idx, match_id in enumerate(group_match_ids, start=1):
                match_events = _read_match_events(db_path, match_id)
                match_shots = build_shot_feature_table(match_events)
                if not match_shots.empty:
                    group_frames.append(match_shots)
                if idx == 1 or idx == len(group_match_ids) or idx % 25 == 0:
                    print(f"[{idx}/{len(group_match_ids)}] processed match {match_id} -> {len(match_shots)} shots")
            if group_frames:
                frames.append(pd.concat(group_frames, ignore_index=True))
        shots = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if shots.empty:
            raise RuntimeError("No shot rows were found.")
        model_training = training_frame(shots, include_penalties=False)
        report = _audit(shots, model_training)
        output.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        shots.to_parquet(output, index=False)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Wrote {len(shots):,} shots to {output}")
        print(f"Wrote audit report to {report_path}")
        print(json.dumps(report, indent=2, sort_keys=True))
        return shots

    match_ids = _match_ids(db_path, league, season, limit_matches, match_offset)
    if not match_ids:
        raise RuntimeError("No matches found for the requested filters.")
    print(f"Found {len(match_ids):,} matches for the requested filters")
    shot_frames: list[pd.DataFrame] = []
    total = len(match_ids)
    for idx, match_id in enumerate(match_ids, start=1):
        match_events = _read_match_events(db_path, match_id)
        match_shots = build_shot_feature_table(match_events)
        if not match_shots.empty:
            shot_frames.append(match_shots)
        if idx == 1 or idx == total or idx % 25 == 0:
            print(f"[{idx}/{total}] processed match {match_id} -> {len(match_shots)} shots")
    shots = pd.concat(shot_frames, ignore_index=True) if shot_frames else pd.DataFrame()
    if shots.empty:
        raise RuntimeError("No shot rows were found for the requested filters.")

    model_training = training_frame(shots, include_penalties=False)
    report = _audit(shots, model_training)

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    shots.to_parquet(output, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {len(shots):,} shots to {output}")
    print(f"Wrote audit report to {report_path}")
    print(json.dumps(report, indent=2, sort_keys=True))
    return shots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical xG training shot table.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to playback90 SQLite database.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output parquet path.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT, help="Output audit JSON path.")
    parser.add_argument("--league", help="Optional league filter, e.g. premier-league.")
    parser.add_argument("--season", help="Optional season filter, e.g. 2025/2026.")
    parser.add_argument("--limit-matches", type=int, help="Optional number of distinct matches to sample.")
    parser.add_argument("--match-offset", type=int, default=0, help="Offset used with --limit-matches for chunked builds.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_training_data(
        db_path=args.db,
        output=args.output,
        report_path=args.report,
        league=args.league,
        season=args.season,
        limit_matches=args.limit_matches,
        match_offset=args.match_offset,
    )


if __name__ == "__main__":
    main()
