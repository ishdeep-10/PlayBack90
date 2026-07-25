"""Build the canonical shot-level dataset for xGOT model training.

Examples:
  apps/api/.venv/bin/python Data/build_xgot_training_data.py
  apps/api/.venv/bin/python Data/build_xgot_training_data.py --league premier-league --season 2025/2026 --limit-matches 50
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from xgot_features import build_xgot_feature_table, training_frame
from xgot_features import build_xgot_feature_table_from_shots


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "Data" / "playback90.db"
DEFAULT_SOURCE_SHOTS = ROOT / "models" / "data" / "xg_training_shots.parquet"
DEFAULT_OUTPUT = ROOT / "models" / "data" / "xgot_training_shots.parquet"
DEFAULT_REPORT = ROOT / "models" / "data" / "xgot_training_audit.json"


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
    if where:
        where.append("matchId IS NOT NULL")
    else:
        where = ["matchId IS NOT NULL"]

    limit_clause = ""
    if limit_matches:
        limit_clause = " LIMIT ? OFFSET ?"
        params.extend([limit_matches, match_offset])

    query = f"SELECT DISTINCT matchId FROM event_data WHERE {' AND '.join(where)} ORDER BY matchId{limit_clause}"
    with sqlite3.connect(db_path) as conn:
        return [row[0] for row in conn.execute(query, params).fetchall()]


def _read_match_events(db_path: Path, match_id: object) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        return pd.read_sql_query("SELECT * FROM event_data WHERE matchId = ?", conn, params=[match_id])


def _count_by(df: pd.DataFrame, column: str) -> dict[str, int]:
    if column not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df[column].fillna("unknown").value_counts().sort_index().items()}


def _numeric_summary(df: pd.DataFrame, column: str) -> dict[str, float | int | None]:
    if column not in df.columns:
        return {"non_null": 0, "missing": int(len(df)), "min": None, "max": None, "mean": None}
    values = pd.to_numeric(df[column], errors="coerce")
    non_null = values.dropna()
    return {
        "non_null": int(non_null.size),
        "missing": int(values.isna().sum()),
        "min": round(float(non_null.min()), 4) if not non_null.empty else None,
        "max": round(float(non_null.max()), 4) if not non_null.empty else None,
        "mean": round(float(non_null.mean()), 4) if not non_null.empty else None,
    }


def _audit(shots: pd.DataFrame, model_training: pd.DataFrame) -> dict:
    if shots.empty:
        return {"shots": 0, "training_shots": 0}

    on_target = shots["xgot_is_on_target"].astype(bool)
    blocked = shots["xgot_is_blocked"].astype(bool)
    zero_value = shots["xgot_zero_value"].astype(bool)
    eligible = shots["xgot_training_eligible"].astype(bool)
    goals = pd.to_numeric(shots.get("isGoal", 0), errors="coerce").fillna(0).astype(int)
    xg = pd.to_numeric(shots.get("xG"), errors="coerce")

    report = {
        "shots": int(len(shots)),
        "model_training_shots": int(len(model_training)),
        "goals": int(goals.sum()),
        "goal_rate": round(float(goals.mean()), 4),
        "on_target_shots": int(on_target.sum()),
        "on_target_goal_rate": round(float(goals[on_target].mean()), 4) if on_target.any() else 0.0,
        "blocked_shots": int(blocked.sum()),
        "zero_value_shots": int(zero_value.sum()),
        "training_eligible_shots": int(eligible.sum()),
        "training_goals": int(pd.to_numeric(model_training.get("xgot_model_target", 0), errors="coerce").fillna(0).sum()),
        "missing_goal_mouth_y": int(pd.to_numeric(shots.get("goal_mouth_y"), errors="coerce").isna().sum()),
        "missing_goal_mouth_z": int(pd.to_numeric(shots.get("goal_mouth_z"), errors="coerce").isna().sum()),
        "missing_xg": int(xg.isna().sum()),
        "xg_total": round(float(xg.fillna(0).sum()), 3),
        "goal_mouth_y": _numeric_summary(shots, "goal_mouth_y"),
        "goal_mouth_z": _numeric_summary(shots, "goal_mouth_z"),
        "eligible_goal_mouth_y": _numeric_summary(shots[eligible], "goal_mouth_y"),
        "eligible_goal_mouth_z": _numeric_summary(shots[eligible], "goal_mouth_z"),
        "by_league": _count_by(shots, "league"),
        "by_season": _count_by(shots, "season"),
        "by_type": _count_by(shots, "type"),
        "by_shot_family": _count_by(shots, "shot_family"),
        "by_body_part": _count_by(shots, "body_part"),
        "by_goal_mouth_zone": _count_by(shots[eligible], "goal_mouth_zone"),
        "eligible_by_type": _count_by(shots[eligible], "type"),
        "zero_value_by_type": _count_by(shots[zero_value], "type"),
    }
    return report


def _build_for_match_ids(db_path: Path, match_ids: list[object]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(match_ids)
    for idx, match_id in enumerate(match_ids, start=1):
        events = _read_match_events(db_path, match_id)
        shots = build_xgot_feature_table(events)
        if not shots.empty:
            frames.append(shots)
        if idx == 1 or idx == total or idx % 25 == 0:
            print(f"[{idx}/{total}] processed match {match_id} -> {len(shots)} shot rows", flush=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_training_data(
    db_path: Path = DEFAULT_DB,
    source_shots: Path | None = DEFAULT_SOURCE_SHOTS,
    output: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    league: str | None = None,
    season: str | None = None,
    limit_matches: int | None = None,
    match_offset: int = 0,
) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    if league is None and season is None and limit_matches is None and source_shots and source_shots.exists():
        print(f"Building xGOT training data from canonical xG shot table: {source_shots}", flush=True)
        source = pd.read_parquet(source_shots)
        shots = build_xgot_feature_table_from_shots(source)
    elif league is None and season is None and limit_matches is None:
        frames: list[pd.DataFrame] = []
        groups = _league_season_groups(db_path)
        print(f"Building xGOT training data across {len(groups)} league/season groups", flush=True)
        for group_idx, (group_league, group_season, match_count) in enumerate(groups, start=1):
            print(f"=== [{group_idx}/{len(groups)}] {group_league} {group_season} ({match_count} matches) ===", flush=True)
            match_ids = _match_ids(db_path, group_league, group_season, None)
            group_shots = _build_for_match_ids(db_path, match_ids)
            if not group_shots.empty:
                frames.append(group_shots)
        shots = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        match_ids = _match_ids(db_path, league, season, limit_matches, match_offset)
        if not match_ids:
            raise RuntimeError("No matches found for the requested filters.")
        print(f"Found {len(match_ids):,} matches for the requested filters", flush=True)
        shots = _build_for_match_ids(db_path, match_ids)

    if shots.empty:
        raise RuntimeError("No shot rows were found.")

    model_training = training_frame(shots, include_penalties=True)
    report = _audit(shots, model_training)

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    shots.to_parquet(output, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {len(shots):,} shot rows to {output}", flush=True)
    print(f"Wrote audit report to {report_path}", flush=True)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return shots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical xGOT training shot table.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to playback90 SQLite database.")
    parser.add_argument(
        "--source-shots",
        type=Path,
        default=DEFAULT_SOURCE_SHOTS,
        help="Optional canonical xG shot parquet to reuse for full builds.",
    )
    parser.add_argument("--from-db", action="store_true", help="Ignore --source-shots and rebuild shot rows from SQLite.")
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
        source_shots=None if args.from_db else args.source_shots,
        output=args.output,
        report_path=args.report,
        league=args.league,
        season=args.season,
        limit_matches=args.limit_matches,
        match_offset=args.match_offset,
    )


if __name__ == "__main__":
    main()
