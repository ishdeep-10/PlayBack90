from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "apps" / "api"
DATA_DIR = ROOT / "Data"

for path in (str(API_DIR), str(DATA_DIR)):
    if path not in sys.path:
        sys.path.append(path)

from app.config import settings  # noqa: E402
from app.domain import TEAM_DICT  # noqa: E402
from app.services.r2 import get_storage_options, make_fs  # noqa: E402

SCALE_X = 1.05
SCALE_Y = 0.68


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


def _to_raw_opta_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    raw = df.copy()
    for col in ("x", "endX", "blockedX"):
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce") / SCALE_X
    for col in ("y", "endY", "blockedY", "goalMouthY"):
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce") / SCALE_Y
    return raw


def _scale_pitch_coordinates(df: pd.DataFrame) -> pd.DataFrame:
    scaled = df.copy()
    for col in ("x", "endX", "blockedX"):
        if col in scaled.columns:
            scaled[col] = pd.to_numeric(scaled[col], errors="coerce") * SCALE_X
    for col in ("y", "endY", "blockedY", "goalMouthY"):
        if col in scaled.columns:
            scaled[col] = pd.to_numeric(scaled[col], errors="coerce") * SCALE_Y
    return scaled


def _drop_generated_carries(df: pd.DataFrame) -> pd.DataFrame:
    if "type" not in df.columns:
        return df.copy()
    return df[df["type"].astype(str) != "Carry"].copy()


def _team_name_from_id(team_id: object) -> str:
    numeric_id = pd.to_numeric(team_id, errors="coerce")
    if not pd.isna(numeric_id) and int(numeric_id) in TEAM_DICT:
        return TEAM_DICT[int(numeric_id)]
    return ""


def _normalize_team_names(df: pd.DataFrame) -> pd.DataFrame:
    if "teamId" not in df.columns:
        return df
    normalized = df.copy()
    mapped = normalized["teamId"].map(_team_name_from_id)
    if "teamName" not in normalized.columns:
        normalized["teamName"] = mapped
        return normalized
    existing = normalized["teamName"].fillna("").astype(str).str.strip()
    normalized["teamName"] = existing.where(existing.ne("") & existing.ne("None"), mapped)
    return normalized


def insert_ball_carries_for_backfill(
    events_df: pd.DataFrame,
    min_carry_length: float = 3.0,
    max_carry_length: float = 60.0,
    min_carry_duration: float = 1.0,
    max_carry_duration: float = 10.0,
) -> pd.DataFrame:
    match_events = events_df.reset_index(drop=True)
    match_carries = pd.DataFrame()

    for idx, match_event in match_events.iterrows():
        if idx >= len(match_events) - 1:
            continue

        prev_evt_team = match_event["teamId"]
        next_evt_idx = idx + 1
        init_next_evt = match_events.loc[next_evt_idx]
        take_ons = 0
        incorrect_next_evt = True

        while incorrect_next_evt and next_evt_idx < len(match_events):
            next_evt = match_events.loc[next_evt_idx]
            if next_evt["type"] == "TakeOn" and next_evt["outcomeType"] == "Successful":
                take_ons += 1
                incorrect_next_evt = True
            elif (
                (next_evt["type"] == "TakeOn" and next_evt["outcomeType"] == "Unsuccessful")
                or (next_evt["teamId"] != prev_evt_team and next_evt["type"] == "Challenge" and next_evt["outcomeType"] == "Unsuccessful")
                or (next_evt["type"] == "Foul")
            ):
                incorrect_next_evt = True
            else:
                incorrect_next_evt = False
            next_evt_idx += 1

        same_team = prev_evt_team == next_evt["teamId"]
        not_ball_touch = match_event["type"] != "BallTouch"
        possession_change = prev_evt_team != next_evt["teamId"]
        prev_unsuccessful_movement = (
            match_event["type"] in ["Pass", "Carry", "TakeOn", "GoodSkill", "Clearance"]
            and match_event["outcomeType"] == "Unsuccessful"
        )
        next_controlled_movement = (
            next_evt["type"] in ["Pass", "Carry", "TakeOn", "GoodSkill"]
            and next_evt["outcomeType"] == "Successful"
        )
        valid_possession_change_carry = possession_change and prev_unsuccessful_movement and next_controlled_movement

        prev_end_x = match_event["endX"]
        prev_end_y = match_event["endY"]
        prev_end_x_num = pd.to_numeric(prev_end_x, errors="coerce")
        prev_end_y_num = pd.to_numeric(prev_end_y, errors="coerce")
        no_clear_end_point = pd.isna(prev_end_x_num) or pd.isna(prev_end_y_num)
        if not no_clear_end_point:
            no_clear_end_point = (
                float(prev_end_x_num) == 0
                and float(prev_end_y_num) == 0
                and match_event["type"] in ["Tackle", "Challenge", "BallRecovery", "Interception", "Aerial", "Foul"]
            )
        if same_team and no_clear_end_point:
            prev_end_x = match_event["x"]
            prev_end_y = match_event["y"]
        if valid_possession_change_carry:
            prev_end_x = 100 - prev_end_x
            prev_end_y = 100 - prev_end_y

        dx = 105 * (prev_end_x - next_evt["x"]) / 100
        dy = 68 * (prev_end_y - next_evt["y"]) / 100
        far_enough = dx**2 + dy**2 >= min_carry_length**2
        not_too_far = dx**2 + dy**2 <= max_carry_length**2
        dt = 60 * (next_evt["cumulative_mins"] - match_event["cumulative_mins"])
        min_time = dt >= min_carry_duration
        same_phase = dt < max_carry_duration
        same_period = match_event["period"] == next_evt["period"]

        valid_carry = (
            (same_team or valid_possession_change_carry)
            and not_ball_touch
            and far_enough
            and not_too_far
            and min_time
            and same_phase
            and same_period
        )

        if not valid_carry:
            continue

        prev = match_event
        nex = next_evt
        carry = pd.DataFrame()
        carry.loc[0, "eventId"] = prev["eventId"] + 0.5
        carry["minute"] = np.floor(((init_next_evt["minute"] * 60 + init_next_evt["second"]) + (prev["minute"] * 60 + prev["second"])) / (2 * 60))
        carry["second"] = (((init_next_evt["minute"] * 60 + init_next_evt["second"]) + (prev["minute"] * 60 + prev["second"])) / 2) - (carry["minute"] * 60)
        carry["teamId"] = nex["teamId"]
        carry["matchId"] = prev["matchId"]
        carry["x"] = prev_end_x
        carry["y"] = prev_end_y
        carry["expandedMinute"] = np.floor(((init_next_evt["expandedMinute"] * 60 + init_next_evt["second"]) + (prev["expandedMinute"] * 60 + prev["second"])) / (2 * 60))
        carry["period"] = nex["period"]
        carry["type"] = "Carry"
        carry["outcomeType"] = "Successful"
        carry["qualifiers"] = {"type": {"value": 999, "displayName": "takeOns"}, "value": str(take_ons)}
        carry["satisfiedEventsTypes"] = [[]]
        carry["isTouch"] = True
        carry["playerId"] = nex["playerId"]
        carry["endX"] = nex["x"]
        carry["endY"] = nex["y"]
        carry["blockedX"] = np.nan
        carry["blockedY"] = np.nan
        carry["goalMouthZ"] = np.nan
        carry["goalMouthY"] = np.nan
        carry["isShot"] = np.nan
        carry["relatedEventId"] = nex["eventId"]
        carry["relatedPlayerId"] = np.nan
        carry["isGoal"] = np.nan
        carry["cardType"] = np.nan
        carry["isOwnGoal"] = np.nan
        carry["cumulative_mins"] = (prev["cumulative_mins"] + init_next_evt["cumulative_mins"]) / 2
        carry["playerName"] = nex["playerName"]
        if "teamName" in match_events.columns:
            carry["teamName"] = nex["teamName"]
        match_carries = pd.concat([match_carries, carry], ignore_index=True, sort=False)

    match_events_and_carries = pd.concat([match_carries, match_events], ignore_index=True, sort=False)
    return match_events_and_carries.sort_values(["period", "cumulative_mins"]).reset_index(drop=True)


def _recompute_carry_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if {"x", "y", "endX", "endY", "type"}.issubset(out.columns):
        x = pd.to_numeric(out["x"], errors="coerce")
        y = pd.to_numeric(out["y"], errors="coerce")
        end_x = pd.to_numeric(out["endX"], errors="coerce")
        end_y = pd.to_numeric(out["endY"], errors="coerce")
        if "prog_pass" in out.columns:
            out["prog_pass"] = np.where(
                out["type"].astype(str).eq("Pass"),
                np.sqrt((105 - x) ** 2 + (34 - y) ** 2) - np.sqrt((105 - end_x) ** 2 + (34 - end_y) ** 2),
                0,
            )
        if "prog_carry" in out.columns:
            out["prog_carry"] = np.where(
                out["type"].astype(str).eq("Carry"),
                np.sqrt((105 - x) ** 2 + (34 - y) ** 2) - np.sqrt((105 - end_x) ** 2 + (34 - end_y) ** 2),
                0,
            )
        if "pass_or_carry_angle" in out.columns:
            out["pass_or_carry_angle"] = np.degrees(np.arctan2(end_y - y, end_x - x))
    return out


def rebuild_carries(df: pd.DataFrame) -> pd.DataFrame:
    helper_index_cols = {"level_0", "__index_level_0__"}
    original_columns = [col for col in df.columns if col not in helper_index_cols]
    cleaned = df.drop(columns=[col for col in helper_index_cols if col in df.columns], errors="ignore")
    cleaned = _normalize_team_names(cleaned)
    base = _drop_generated_carries(cleaned)
    raw = _to_raw_opta_coordinates(base)

    if "period" in raw.columns:
        period_to_num = {
            "FirstHalf": 1,
            "SecondHalf": 2,
            "FirstPeriodOfExtraTime": 3,
            "SecondPeriodOfExtraTime": 4,
            "PenaltyShootout": 5,
            "PostGame": 14,
            "PreMatch": 16,
        }
        raw["period"] = raw["period"].map(lambda value: period_to_num.get(value, value))

    rebuilt = insert_ball_carries_for_backfill(raw)

    generated_index_cols = [col for col in ("index", "level_0", "__index_level_0__") if col in rebuilt.columns]
    if generated_index_cols:
        rebuilt = rebuilt.drop(columns=generated_index_cols)
    rebuilt = rebuilt.reset_index(drop=True)
    rebuilt.insert(0, "index", range(1, len(rebuilt) + 1))

    rebuilt = _scale_pitch_coordinates(rebuilt)
    rebuilt = _recompute_carry_columns(rebuilt)

    if "period" in rebuilt.columns:
        period_to_name = {
            1: "FirstHalf",
            2: "SecondHalf",
            3: "FirstPeriodOfExtraTime",
            4: "SecondPeriodOfExtraTime",
            5: "PenaltyShootout",
            14: "PostGame",
            16: "PreMatch",
        }
        rebuilt["period"] = rebuilt["period"].map(lambda value: period_to_name.get(value, value))

    for col in original_columns:
        if col not in rebuilt.columns:
            rebuilt[col] = np.nan
    extra_cols = [col for col in rebuilt.columns if col not in original_columns]
    return rebuilt[original_columns + extra_cols]


def _jsonify_nested_value(value: object) -> object:
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return value


def _normalize_object_columns_for_parquet(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in normalized.columns:
        if normalized[col].dtype != "object":
            continue
        has_nested_values = normalized[col].map(lambda value: isinstance(value, (dict, list))).any()
        if has_nested_values:
            normalized[col] = normalized[col].map(_jsonify_nested_value)
            continue

        non_null = normalized[col].dropna()
        if non_null.empty:
            continue
        numeric_values = pd.to_numeric(non_null, errors="coerce")
        if numeric_values.notna().all():
            normalized[col] = pd.to_numeric(normalized[col], errors="coerce")
    return normalized


def _write_parquet_to_r2(df: pd.DataFrame, key: str) -> None:
    buffer = io.BytesIO()
    _normalize_object_columns_for_parquet(df).to_parquet(buffer, index=False)
    buffer.seek(0)
    fs = make_fs()
    with fs.open(key, "wb") as handle:
        handle.write(buffer.getvalue())


def backfill(prefix: str, apply: bool, limit: int | None = None) -> None:
    _require_r2_config()
    fs = make_fs()
    files = sorted(fs.glob(prefix))
    if limit is not None:
        files = files[:limit]
    if not files:
        print(f"No parquet files found for {prefix}", flush=True)
        return
    print(f"Found {len(files)} parquet files", flush=True)

    for idx, key in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] reading {key}", flush=True)
        df = pd.read_parquet(f"s3://{key}", storage_options=get_storage_options())
        has_helper_columns = any(col in df.columns for col in ("level_0", "__index_level_0__"))
        old_carries = int(df.get("type", pd.Series(dtype=str)).astype(str).eq("Carry").sum())
        rebuilt = rebuild_carries(df)
        new_carries = int(rebuilt.get("type", pd.Series(dtype=str)).astype(str).eq("Carry").sum())
        delta = new_carries - old_carries
        needs_upload = bool(delta or has_helper_columns)
        status = "changed" if needs_upload else "unchanged"
        print(f"{status}: {key} carries {old_carries} -> {new_carries} ({delta:+d})", flush=True)
        if apply and needs_upload:
            _write_parquet_to_r2(rebuilt, key)
            print(f"  uploaded corrected parquet", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill generated carry rows for FIFA World Cup event parquet files.")
    parser.add_argument("--league", default="fifa-world-cup")
    parser.add_argument("--season", default="2026")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N files; useful for smoke tests.")
    parser.add_argument("--apply", action="store_true", help="Upload corrected parquet files back to R2.")
    args = parser.parse_args()

    bucket = settings.r2_bucket
    prefix = f"{bucket}/event_data/{args.league}/{args.season}/*.parquet"
    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"{mode}: {prefix}", flush=True)
    backfill(prefix, apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
