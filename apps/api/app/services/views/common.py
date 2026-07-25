"""Helpers shared by multiple analysis view modules.

Imports only from app.services.matches (never from sibling view modules).
"""

from __future__ import annotations

import pandas as pd

from app.services.matches import (
    _bool_series,
    _coerce_numeric,
)


GROUND_DUEL_TYPES = {"TakeOn", "GoodSkill", "ShieldBallOpp", "Foul", "Tackle", "Challenge"}


def _duel_mask(df: pd.DataFrame, duel_type: str | None = "Total") -> pd.Series:
    if df.empty or "type" not in df.columns:
        return pd.Series(False, index=df.index)
    event_type = df["type"].astype(str)
    aerial = _bool_series(df, "duelAerialWon") | _bool_series(df, "duelAerialLost") | event_type.eq("Aerial")
    ground = event_type.isin(GROUND_DUEL_TYPES)
    normalized = str(duel_type or "Total")
    if normalized in {"Ground", "Ground Duels", "Offensive", "Defensive"}:
        return ground
    if normalized in {"Aerial", "Aerial Duels"}:
        return aerial
    return ground | aerial


def _row_successful(row: pd.Series) -> bool:
    outcome = str(row.get("outcomeType", "")).strip().lower()
    return outcome in {"successful", "nan", ""}


def _progressive_action_mask(events: pd.DataFrame) -> pd.Series:
    if events.empty:
        return pd.Series(False, index=events.index)
    x = _coerce_numeric(events.get("x", pd.Series(0, index=events.index))).fillna(0)
    y = _coerce_numeric(events.get("y", pd.Series(0, index=events.index))).fillna(0)
    end_x = _coerce_numeric(events.get("endX", pd.Series(0, index=events.index))).fillna(x)
    end_y = _coerce_numeric(events.get("endY", pd.Series(0, index=events.index))).fillna(y)
    start_distance = ((105 - x) ** 2 + (34 - y) ** 2) ** 0.5
    end_distance = ((105 - end_x) ** 2 + (34 - end_y) ** 2) ** 0.5
    distance_gain = start_distance - end_distance
    own_half_start = x < 52.5
    own_half_end = end_x < 52.5
    opponent_half_start = x >= 52.5
    opponent_half_end = end_x >= 52.5
    return (
        (own_half_start & own_half_end & (distance_gain >= 30))
        | ((own_half_start != own_half_end) & (distance_gain >= 15))
        | (opponent_half_start & opponent_half_end & (distance_gain >= 10))
    )
