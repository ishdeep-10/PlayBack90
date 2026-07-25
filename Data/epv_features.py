"""Shared Expected Possession Value scoring utilities.

EPV v1 is a deterministic grid-based spatial value model. It assigns start and
end possession-state values to successful ball-progression actions and stores
the action delta as ``epv_added``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0
DEFAULT_GRID_ROWS = 22
DEFAULT_GRID_COLS = 32
DEFAULT_EPV_VERSION = "v1"
DEFAULT_GRID_VERSION = "playback90-grid-v1"
FEATURE_VERSION = "epv-v1"

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EPV_DIR = ROOT / "models" / "epv"


def _series(df: pd.DataFrame, column: str, default: Any = np.nan) -> pd.Series:
    if column in df.columns:
        return df[column]
    return pd.Series(default, index=df.index)


def _num(values: pd.Series | np.ndarray | list[Any], default: float = np.nan) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").fillna(default)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, float) and np.isnan(value):
        return False
    return str(value).strip().lower() in {"1", "1.0", "true", "yes", "y", "successful"}


def _bool_col(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column].map(_truthy).fillna(False).astype(bool)


def build_default_epv_grid(rows: int = DEFAULT_GRID_ROWS, cols: int = DEFAULT_GRID_COLS) -> np.ndarray:
    """Return a smooth left-to-right EPV surface for a 105x68 pitch.

    The surface is deliberately simple and replaceable: it increases toward the
    opponent goal, rewards centrality, and adds a box-zone lift. It gives us a
    stable v1 contract while keeping the grid source explicit.
    """

    x_centers = (np.arange(cols) + 0.5) / cols
    y_centers = (np.arange(rows) + 0.5) / rows
    xx, yy = np.meshgrid(x_centers, y_centers)
    centrality = 1.0 - np.clip(np.abs(yy - 0.5) / 0.5, 0.0, 1.0)
    goal_distance = np.sqrt((1.0 - xx) ** 2 + ((yy - 0.5) * 0.72) ** 2)
    goal_proximity = np.clip(1.0 - goal_distance / 1.24, 0.0, 1.0)
    final_third = np.clip((xx - 0.66) / 0.34, 0.0, 1.0)
    box_zone = ((xx >= (88.5 / PITCH_LENGTH)) & (np.abs(yy - 0.5) <= (20.16 / PITCH_WIDTH))).astype(float)
    six_yard_zone = ((xx >= (99.5 / PITCH_LENGTH)) & (np.abs(yy - 0.5) <= (9.16 / PITCH_WIDTH))).astype(float)

    surface = (
        0.004
        + 0.018 * xx**1.6
        + 0.065 * goal_proximity**3.0
        + 0.030 * final_third * centrality**1.3
        + 0.055 * box_zone * centrality
        + 0.050 * six_yard_zone * centrality
    )
    surface = np.maximum.accumulate(surface, axis=1)
    return np.clip(surface, 0.0, 0.32)


@lru_cache(maxsize=8)
def load_epv_grid(version: str = DEFAULT_EPV_VERSION, artifact_dir: str | None = None) -> tuple[np.ndarray, dict[str, Any]]:
    """Load a versioned EPV grid, falling back to the built-in v1 surface."""

    root = Path(artifact_dir) if artifact_dir else DEFAULT_EPV_DIR
    model_dir = root / version
    grid_path = model_dir / "epv_grid.csv"
    metadata_path = model_dir / "metadata.json"
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    if grid_path.exists():
        grid = np.loadtxt(grid_path, delimiter=",")
        grid_version = str(metadata.get("grid_version") or DEFAULT_GRID_VERSION)
    else:
        grid = build_default_epv_grid()
        grid_version = DEFAULT_GRID_VERSION
        metadata = {
            **metadata,
            "grid_version": grid_version,
            "source": "built-in deterministic spatial surface",
            "grid_rows": int(grid.shape[0]),
            "grid_cols": int(grid.shape[1]),
            "pitch_length": PITCH_LENGTH,
            "pitch_width": PITCH_WIDTH,
        }

    if grid.ndim != 2 or grid.size == 0:
        raise ValueError(f"Invalid EPV grid for version {version!r}: expected a non-empty 2D grid.")
    return grid.astype(float), metadata


def _coordinate_bins(
    x: pd.Series,
    y: pd.Series,
    rows: int,
    cols: int,
    pitch_length: float = PITCH_LENGTH,
    pitch_width: float = PITCH_WIDTH,
) -> tuple[pd.Series, pd.Series]:
    x_num = _num(x)
    y_num = _num(y)
    valid = x_num.between(0, pitch_length) & y_num.between(0, pitch_width)
    x_clipped = x_num.clip(0, np.nextafter(pitch_length, 0))
    y_clipped = y_num.clip(0, np.nextafter(pitch_width, 0))
    x_bin = np.floor(x_clipped / pitch_length * cols).astype("Int64")
    y_bin = np.floor(y_clipped / pitch_width * rows).astype("Int64")
    x_bin = x_bin.where(valid)
    y_bin = y_bin.where(valid)
    return x_bin, y_bin


def _values_at_locations(
    grid: np.ndarray,
    x: pd.Series,
    y: pd.Series,
    pitch_length: float = PITCH_LENGTH,
    pitch_width: float = PITCH_WIDTH,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    rows, cols = grid.shape
    x_bin, y_bin = _coordinate_bins(x, y, rows=rows, cols=cols, pitch_length=pitch_length, pitch_width=pitch_width)
    values = pd.Series(np.nan, index=x.index, dtype=float)
    valid = x_bin.notna() & y_bin.notna()
    if valid.any():
        values.loc[valid] = grid[y_bin.loc[valid].astype(int), x_bin.loc[valid].astype(int)]
    return values, x_bin, y_bin


def get_epv_at_location(
    x: float,
    y: float,
    grid: np.ndarray | None = None,
    version: str = DEFAULT_EPV_VERSION,
    artifact_dir: str | None = None,
    pitch_length: float = PITCH_LENGTH,
    pitch_width: float = PITCH_WIDTH,
) -> float:
    """Return the EPV grid value at one processed pitch location."""

    if grid is None:
        grid, _ = load_epv_grid(version=version, artifact_dir=artifact_dir)
    values, _, _ = _values_at_locations(
        grid,
        pd.Series([x], dtype=float),
        pd.Series([y], dtype=float),
        pitch_length=pitch_length,
        pitch_width=pitch_width,
    )
    value = values.iloc[0]
    return float(value) if pd.notna(value) else float("nan")


def _eligible_action_mask(events: pd.DataFrame) -> pd.Series:
    if events.empty or "type" not in events.columns:
        return pd.Series(False, index=events.index)
    event_type = _series(events, "type", "").fillna("").astype(str)
    outcome = _series(events, "outcomeType", "").fillna("").astype(str).str.lower()
    successful = outcome.eq("successful")
    progressive_types = event_type.isin(["Pass", "Carry"])
    return progressive_types & successful


def build_epv_columns(
    events: pd.DataFrame,
    version: str = DEFAULT_EPV_VERSION,
    artifact_dir: str | None = None,
    force: bool = False,
) -> pd.DataFrame:
    """Return an event dataframe with EPV columns updated."""

    df = events.copy()
    for column in (
        "epv_start",
        "epv_end",
        "epv_added",
        "epv_action_eligible",
        "epv_model_version",
        "epv_grid_version",
        "epv_feature_version",
        "epv_start_zone_x",
        "epv_start_zone_y",
        "epv_end_zone_x",
        "epv_end_zone_y",
    ):
        if column not in df.columns:
            df[column] = np.nan if column.startswith("epv_") and column.endswith(("_start", "_end", "_added")) else None

    if df.empty:
        return df

    required = {"x", "y", "endX", "endY"}
    if not required.issubset(df.columns):
        missing = sorted(required.difference(df.columns))
        raise ValueError(f"Cannot compute EPV without columns: {missing}")

    grid, metadata = load_epv_grid(version=version, artifact_dir=artifact_dir)
    eligible = _eligible_action_mask(df)
    has_end = _num(df["endX"]).notna() & _num(df["endY"]).notna()
    eligible = eligible & has_end

    if not force:
        current_version = _series(df, "epv_model_version", "").fillna("").astype(str)
        eligible = eligible & ~current_version.eq(version)

    start_values, start_x_bin, start_y_bin = _values_at_locations(grid, _num(df["x"]), _num(df["y"]))
    end_values, end_x_bin, end_y_bin = _values_at_locations(grid, _num(df["endX"]), _num(df["endY"]))
    scored = eligible & start_values.notna() & end_values.notna()

    df["epv_action_eligible"] = _eligible_action_mask(df).astype(bool)
    if scored.any():
        df.loc[scored, "epv_start"] = start_values.loc[scored].astype(float)
        df.loc[scored, "epv_end"] = end_values.loc[scored].astype(float)
        df.loc[scored, "epv_added"] = (end_values.loc[scored] - start_values.loc[scored]).astype(float)
        df.loc[scored, "epv_model_version"] = version
        df.loc[scored, "epv_grid_version"] = str(metadata.get("grid_version") or DEFAULT_GRID_VERSION)
        df.loc[scored, "epv_feature_version"] = FEATURE_VERSION
        df.loc[scored, "epv_start_zone_x"] = start_x_bin.loc[scored].astype("Int64")
        df.loc[scored, "epv_start_zone_y"] = start_y_bin.loc[scored].astype("Int64")
        df.loc[scored, "epv_end_zone_x"] = end_x_bin.loc[scored].astype("Int64")
        df.loc[scored, "epv_end_zone_y"] = end_y_bin.loc[scored].astype("Int64")

    for column in ("epv_start", "epv_end", "epv_added"):
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def summarize_epv_quality(events: pd.DataFrame) -> dict[str, Any]:
    """Build a compact QA summary for dry runs and backfills."""

    eligible = _eligible_action_mask(events)
    epv_added = pd.to_numeric(_series(events, "epv_added"), errors="coerce")
    event_type = _series(events, "type", "Unknown").fillna("Unknown").astype(str)
    summary: dict[str, Any] = {
        "rows": int(len(events)),
        "eligible_actions": int(eligible.sum()),
        "scored_actions": int(epv_added[eligible].notna().sum()),
        "missing_epv": int(epv_added[eligible].isna().sum()),
        "epv_added_total": round(float(epv_added[eligible].fillna(0).sum()), 6),
        "epv_added_positive": round(float(epv_added[eligible & (epv_added > 0)].fillna(0).sum()), 6),
        "epv_added_negative": round(float(epv_added[eligible & (epv_added < 0)].fillna(0).sum()), 6),
        "by_action_type": [],
    }
    for action_type, group_index in event_type[eligible].groupby(event_type[eligible]).groups.items():
        group_values = epv_added.loc[group_index]
        summary["by_action_type"].append(
            {
                "type": str(action_type),
                "actions": int(len(group_values)),
                "scored": int(group_values.notna().sum()),
                "epv_added": round(float(group_values.fillna(0).sum()), 6),
                "avg_epv_added": round(float(group_values.fillna(0).mean()), 6) if len(group_values) else 0.0,
            }
        )
    return summary
