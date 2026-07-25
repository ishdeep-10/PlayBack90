"""Build the canonical completed-pass dataset for xA model training.

Examples:
  apps/api/.venv/bin/python Data/build_xa_training_data.py
  apps/api/.venv/bin/python Data/build_xa_training_data.py --league premier-league --season 2025/2026 --limit-matches 50
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

import pandas as pd

from xa_features import build_pass_feature_table, training_frame


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "Data" / "playback90.db"
DEFAULT_OUTPUT = ROOT / "models" / "data" / "xa_training_passes.parquet"
DEFAULT_REPORT = ROOT / "models" / "data" / "xa_training_audit.json"


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


def _match_ids(
    db_path: Path,
    league: str | None,
    season: str | None,
    limit_matches: int | None,
    match_offset: int = 0,
) -> list[object]:
    where = []
    params: list[object] = []
    if league:
        where.append("league = ?")
        params.append(league)
    if season:
        where.append("season = ?")
        params.append(season)
    where.append("matchId IS NOT NULL")

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


def _audit(passes: pd.DataFrame, model_training: pd.DataFrame, duplicate_rows_removed: int = 0) -> dict:
    if passes.empty:
        return {"completed_passes": 0, "training_passes": 0}

    target = pd.to_numeric(passes.get("xa_model_target", 0), errors="coerce").fillna(0)
    direct_shot_assist = pd.to_numeric(passes.get("xa_is_direct_shot_assist", 0), errors="coerce").fillna(0)
    linked_xg = pd.to_numeric(passes.get("xa_target_xg"), errors="coerce")
    existing_xa = pd.to_numeric(passes.get("xA"), errors="coerce") if "xA" in passes.columns else pd.Series(dtype=float)

    report = {
        "completed_passes": int(len(passes)),
        "training_passes": int(len(model_training)),
        "assist_targets": int(target.sum()),
        "assist_rate": round(float(target.mean()), 5),
        "direct_shot_assist_passes": int(direct_shot_assist.sum()),
        "direct_shot_assist_rate": round(float(direct_shot_assist.mean()), 5),
        "linked_shot_xg_total_for_future_xag": round(float(linked_xg.fillna(0).sum()), 3),
        "linked_shot_xg": _numeric_summary(passes, "xa_target_xg"),
        "missing_xy": int(passes[["x", "y", "endX", "endY"]].isna().any(axis=1).sum()),
        "impossible_xy": int(
            (
                (passes["x"] < 0)
                | (passes["x"] > 105)
                | (passes["endX"] < 0)
                | (passes["endX"] > 105)
                | (passes["y"] < 0)
                | (passes["y"] > 68)
                | (passes["endY"] < 0)
                | (passes["endY"] > 68)
            ).sum()
        ),
        "duplicate_match_event_ids": int(
            passes.duplicated(subset=[col for col in ("matchId", "eventId") if col in passes.columns]).sum()
        ),
        "duplicate_rows_removed": int(duplicate_rows_removed),
        "existing_xa_missing": int(existing_xa.isna().sum()) if not existing_xa.empty else int(len(passes)),
        "existing_xa_total": round(float(existing_xa.fillna(0).sum()), 3) if not existing_xa.empty else 0.0,
        "by_league": _count_by(passes, "league"),
        "by_season": _count_by(passes, "season"),
        "by_pass_type": _count_by(passes, "pass_type"),
        "by_play_pattern": _count_by(passes, "play_pattern"),
        "by_pass_direction": _count_by(passes, "pass_direction"),
        "assist_targets_by_pass_type": _count_by(passes[passes["xa_model_target"].astype(int).eq(1)], "pass_type"),
        "assist_targets_by_play_pattern": _count_by(passes[passes["xa_model_target"].astype(int).eq(1)], "play_pattern"),
        "shot_assists_by_pass_type": _count_by(passes[passes["xa_is_direct_shot_assist"].astype(int).eq(1)], "pass_type"),
        "shot_assists_by_play_pattern": _count_by(passes[passes["xa_is_direct_shot_assist"].astype(int).eq(1)], "play_pattern"),
    }
    return report


def _dedupe_passes(passes: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    subset = [column for column in ("matchId", "eventId") if column in passes.columns]
    if len(subset) < 2:
        return passes, 0
    duplicate_mask = passes.duplicated(subset=subset, keep="first")
    duplicate_count = int(duplicate_mask.sum())
    if duplicate_count == 0:
        return passes, 0
    return passes.loc[~duplicate_mask].copy(), duplicate_count


def _build_for_match_ids(db_path: Path, match_ids: list[object]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    total = len(match_ids)
    for idx, match_id in enumerate(match_ids, start=1):
        events = _read_match_events(db_path, match_id)
        passes = build_pass_feature_table(events)
        if not passes.empty:
            frames.append(passes)
        if idx == 1 or idx == total or idx % 25 == 0:
            print(f"[{idx}/{total}] processed match {match_id} -> {len(passes)} completed pass rows", flush=True)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_training_data(
    db_path: Path = DEFAULT_DB,
    output: Path = DEFAULT_OUTPUT,
    report_path: Path = DEFAULT_REPORT,
    league: str | None = None,
    season: str | None = None,
    limit_matches: int | None = None,
    match_offset: int = 0,
) -> pd.DataFrame:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    if league is None and season is None and limit_matches is None:
        frames: list[pd.DataFrame] = []
        groups = _league_season_groups(db_path)
        print(f"Building xA training data across {len(groups)} league/season groups", flush=True)
        for group_idx, (group_league, group_season, match_count) in enumerate(groups, start=1):
            print(f"=== [{group_idx}/{len(groups)}] {group_league} {group_season} ({match_count} matches) ===", flush=True)
            match_ids = _match_ids(db_path, group_league, group_season, None)
            group_passes = _build_for_match_ids(db_path, match_ids)
            if not group_passes.empty:
                frames.append(group_passes)
        passes = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    else:
        match_ids = _match_ids(db_path, league, season, limit_matches, match_offset)
        if not match_ids:
            raise RuntimeError("No matches found for the requested filters.")
        print(f"Found {len(match_ids):,} matches for the requested filters", flush=True)
        passes = _build_for_match_ids(db_path, match_ids)

    if passes.empty:
        raise RuntimeError("No completed pass rows were found.")

    passes, duplicate_rows_removed = _dedupe_passes(passes)
    model_training = training_frame(passes)
    report = _audit(passes, model_training, duplicate_rows_removed=duplicate_rows_removed)

    output.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    passes.to_parquet(output, index=False)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote {len(passes):,} completed pass rows to {output}", flush=True)
    print(f"Wrote audit report to {report_path}", flush=True)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return passes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build canonical xA completed-pass training table.")
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
