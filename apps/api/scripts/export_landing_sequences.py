"""One-off curation tool for the landing-page pitch replays.

Dumps candidate event sequences from a match parquet as JSON shaped like
LandingSequenceEvent (apps/web/lib/landing.ts), ready to paste into
apps/web/lib/landing-sequences.ts. Not a runtime dependency of the API.

Usage (from apps/api, with R2 env configured):
    python scripts/export_landing_sequences.py <filePath> [--mode epv|duels|player] [--player NAME]

Examples:
    python scripts/export_landing_sequences.py \
        "playback90/event_data/premier-league/2025_2026/2026-05-24_1903353_162_vs_13_1___2.parquet" \
        --mode epv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from app.services.r2 import load_match_dataframe  # noqa: E402

EVENT_FIELDS = [
    "minute", "second", "team", "player", "type", "outcome",
    "x", "y", "end_x", "end_y", "xg", "xgot", "xa", "xt", "epv_added",
]


def _clean(row: pd.Series) -> dict:
    out = {}
    for field in EVENT_FIELDS:
        value = row.get(field)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        if field in ("minute", "second"):
            out[field] = int(value)
        elif isinstance(value, float):
            out[field] = round(value, 3)
        else:
            out[field] = value
    return out


def best_epv_chain(df: pd.DataFrame, length: int = 8) -> pd.DataFrame:
    """Sliding window with the highest summed epv_added, kept in event order."""
    if "epv_added" not in df.columns:
        raise SystemExit("no epv_added column in this parquet")
    df = df.reset_index(drop=True)
    epv = pd.to_numeric(df["epv_added"], errors="coerce").fillna(0)
    rolling = epv.rolling(length).sum()
    end = int(rolling.idxmax())
    return df.iloc[max(end - length + 1, 0) : end + 1]


def duel_cluster(df: pd.DataFrame, window_s: int = 30) -> pd.DataFrame:
    """Densest 30-second cluster of duel-ish events."""
    duel_types = {"AerialDuel", "Tackle", "TakeOn", "BallRecovery", "Challenge"}
    duels = df[df["type"].isin(duel_types)].copy()
    if duels.empty:
        raise SystemExit("no duel events found")
    duels["t"] = duels["minute"] * 60 + duels["second"]
    best_start, best_count = 0, 0
    for t in duels["t"]:
        count = ((duels["t"] >= t) & (duels["t"] < t + window_s)).sum()
        if count > best_count:
            best_start, best_count = t, count
    mask = (df["minute"] * 60 + df["second"] >= best_start) & (
        df["minute"] * 60 + df["second"] < best_start + window_s
    )
    return df[mask & df["type"].isin(duel_types | {"Pass"})]


def player_actions(df: pd.DataFrame, player: str, limit: int = 8) -> pd.DataFrame:
    actions = df[df["player"] == player]
    if actions.empty:
        raise SystemExit(f"no events for player {player!r}")
    interesting = actions[actions["type"] != "Pass"]
    picked = pd.concat([interesting, actions]).drop_duplicates().head(limit)
    return picked.sort_values(["minute", "second"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path")
    parser.add_argument("--mode", choices=["epv", "duels", "player"], default="epv")
    parser.add_argument("--player")
    parser.add_argument("--length", type=int, default=8)
    args = parser.parse_args()

    df = load_match_dataframe(args.file_path)
    if args.mode == "epv":
        picked = best_epv_chain(df, args.length)
    elif args.mode == "duels":
        picked = duel_cluster(df)
    else:
        if not args.player:
            raise SystemExit("--player is required with --mode player")
        picked = player_actions(df, args.player, args.length)

    events = [_clean(row) for _, row in picked.iterrows()]
    print(json.dumps(events, indent=2))


if __name__ == "__main__":
    main()
