"""Pass network and in-possession view builders."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from app.services.matches import (
    _available_game_state_options,
    _bool_series,
    _coerce_numeric,
    _filter_score_state,
    _filter_time_range,
    _normalize_time_range_to_window,
    _prepared_in_possession_frames,
    _safe_float,
    _safe_int,
    _time_bounds_for_state,
    _time_range_option,
    _window_scoped_events,
)
from app.services.views.common import _progressive_action_mask


def _player_initials(name: str) -> str:
    parts = str(name or "").strip().split()
    return "".join(f"{part[0].upper()}." for part in parts if part)


def _pass_network_windows(df: pd.DataFrame, team: str) -> list[dict[str, Any]]:
    if df.empty or "teamName" not in df.columns or "type" not in df.columns:
        return [{"value": "0", "label": "Starting 11", "minute_start": 0, "minute_end": 90}]
    sub_minutes = (
        _coerce_numeric(df[(df["teamName"] == team) & (df["type"] == "SubstitutionOn")].get("minute", pd.Series(dtype=float)))
        .dropna()
        .astype(int)
    )
    sub_minutes = sorted({minute for minute in sub_minutes if 0 <= minute < 90})
    windows: list[dict[str, Any]] = []
    starts = [0] + sub_minutes
    ends = sub_minutes + [90]
    for index, (start, end) in enumerate(zip(starts, ends)):
        if start >= end:
            continue
        windows.append(
            {
                "value": str(index),
                "label": "Starting 11" if index == 0 else f"Sub Window {index}",
                "minute_start": int(start),
                "minute_end": int(end),
            }
        )
    if not windows:
        return [{"value": "0", "label": "Starting 11", "minute_start": 0, "minute_end": 90}]

    merged_windows: list[dict[str, Any]] = []
    index = 0
    min_window_minutes = 10
    while index < len(windows):
        window = dict(windows[index])
        window["source_window_count"] = 1
        duration = int(window["minute_end"]) - int(window["minute_start"])
        if duration < min_window_minutes and index + 1 < len(windows):
            next_window = windows[index + 1]
            window["minute_end"] = int(next_window["minute_end"])
            window["source_window_count"] = int(window.get("source_window_count", 1)) + 1
            index += 2
        elif duration < min_window_minutes and merged_windows:
            merged_windows[-1]["minute_end"] = int(window["minute_end"])
            merged_windows[-1]["source_window_count"] = int(merged_windows[-1].get("source_window_count", 1)) + 1
            index += 1
            continue
        else:
            index += 1
        merged_windows.append(window)

    for index, window in enumerate(merged_windows):
        window["value"] = str(index)
        window["label"] = "Starting 11" if index == 0 and int(window["minute_start"]) == 0 else f"Sub Window {index}"
        window["is_merged"] = int(window.get("source_window_count", 1)) > 1
    return merged_windows


def _players_introduced_in_window(
    df: pd.DataFrame,
    team: str,
    minute_start: int,
    minute_end: int,
) -> set[int]:
    if minute_start <= 0 or df.empty or "teamName" not in df.columns or "type" not in df.columns or "playerId" not in df.columns:
        return set()
    team_events = df[df["teamName"] == team]
    minutes = _coerce_numeric(team_events.get("minute", pd.Series(0, index=team_events.index))).fillna(-1)
    introduced = team_events[
        (team_events["type"] == "SubstitutionOn")
        & (minutes >= minute_start)
        & (minutes < minute_end)
    ]["playerId"]
    return {int(player_id) for player_id in pd.to_numeric(introduced, errors="coerce").dropna().tolist()}


def _players_part_window(
    df: pd.DataFrame,
    team: str,
    minute_start: int,
    minute_end: int,
) -> set[int]:
    if df.empty or "teamName" not in df.columns or "type" not in df.columns or "playerId" not in df.columns:
        return set()
    team_events = df[df["teamName"] == team]
    minutes = _coerce_numeric(team_events.get("minute", pd.Series(0, index=team_events.index))).fillna(-1)
    part_window = team_events[
        team_events["type"].isin(["SubstitutionOn", "SubstitutionOff"])
        & (minutes > minute_start)
        & (minutes < minute_end)
    ]["playerId"]
    return {int(player_id) for player_id in pd.to_numeric(part_window, errors="coerce").dropna().tolist()}


def _infer_attacking_right(df: pd.DataFrame, team: str) -> bool:
    if df.empty or "teamName" not in df.columns:
        return True
    team_events = df[df["teamName"] == team]
    samples: list[pd.Series] = []
    if "type" in team_events.columns and "x" in team_events.columns:
        shots = team_events[team_events["type"].astype(str).str.contains("Shot|Goal", case=False, na=False)]
        if not shots.empty:
            samples.append(_coerce_numeric(shots["x"]))
    if "endX" in team_events.columns:
        passes = team_events[team_events["type"].astype(str).eq("Pass")] if "type" in team_events.columns else team_events
        if not passes.empty:
            samples.append(_coerce_numeric(passes["endX"]))
    if not samples:
        return True
    sample = pd.concat(samples).dropna()
    return bool(sample.empty or sample.median() >= 52.5)


def _progressive_pass_mask(passes: pd.DataFrame) -> pd.Series:
    if passes.empty:
        return pd.Series(False, index=passes.index)
    return _progressive_action_mask(passes)


def _filter_passes_for_window(
    match_df: pd.DataFrame,
    passes_df: pd.DataFrame,
    team: str,
    minute_start: int,
    minute_end: int,
) -> pd.DataFrame:
    if passes_df.empty:
        return passes_df

    team_events = match_df[match_df["teamName"] == team] if "teamName" in match_df.columns else match_df.iloc[0:0]
    starters = set(team_events[_bool_series(team_events, "isFirstEleven")]["playerId"].dropna().tolist()) if "playerId" in team_events.columns else set()
    valid_players: set[Any] = set()
    if starters:
        subs_on = set(
            team_events[
                (team_events["type"] == "SubstitutionOn")
                & (_coerce_numeric(team_events.get("minute", pd.Series(0, index=team_events.index))) < minute_end)
            ]["playerId"]
            .dropna()
            .tolist()
        ) if "playerId" in team_events.columns and "type" in team_events.columns else set()
        subs_off = set(
            team_events[
                (team_events["type"] == "SubstitutionOff")
                & (_coerce_numeric(team_events.get("minute", pd.Series(0, index=team_events.index))) < minute_start)
            ]["playerId"]
            .dropna()
            .tolist()
        ) if "playerId" in team_events.columns and "type" in team_events.columns else set()
        valid_players = (starters | subs_on) - subs_off

    minute = _coerce_numeric(passes_df.get("minute", pd.Series(0, index=passes_df.index))).fillna(-1)
    filtered = passes_df[
        (passes_df["teamName"] == team)
        & (minute >= minute_start)
        & (minute < minute_end)
    ].copy()
    if len(valid_players) > 1:
        filtered = filtered[
            filtered["playerId"].isin(valid_players)
            & filtered["receiver"].isin(valid_players)
        ].copy()
    return filtered


THIRD_BOUNDS = {"defensive": (0.0, 35.0), "middle": (35.0, 70.0), "final": (70.0, 105.01)}
THIRD_LABELS = {"defensive": "Ball Retention (Def. 3rd)", "middle": "Buildup (Mid 3rd)", "final": "Final Third"}


def _normalize_third(third: str | None) -> str:
    value = str(third or "all").strip().lower()
    return value if value in THIRD_BOUNDS else "all"


def _filter_by_third(frame: pd.DataFrame, third: str) -> pd.DataFrame:
    if third == "all" or frame.empty or "x" not in frame.columns:
        return frame
    low, high = THIRD_BOUNDS[third]
    start_x = _coerce_numeric(frame["x"]).fillna(-1)
    return frame[(start_x >= low) & (start_x < high)]


def _third_kpis(passes: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if passes.empty or "x" not in passes.columns:
        return rows
    outcome = passes.get("outcomeType", pd.Series("", index=passes.index)).astype(str).str.lower()
    xt = _coerce_numeric(passes.get("xT", pd.Series(0, index=passes.index))).fillna(0.0)
    progressive = _progressive_pass_mask(passes)
    start_x = _coerce_numeric(passes["x"]).fillna(-1)
    for key, (low, high) in THIRD_BOUNDS.items():
        in_third = (start_x >= low) & (start_x < high)
        attempted = int(in_third.sum())
        completed = int((in_third & outcome.eq("successful")).sum())
        rows.append({
            "third": key,
            "label": THIRD_LABELS[key],
            "passes": attempted,
            "completed": completed,
            "completion_pct": round(100.0 * completed / attempted, 1) if attempted else 0.0,
            "xt": round(float(xt[in_third & outcome.eq("successful")].sum()), 2),
            "progressive": int((in_third & progressive & outcome.eq("successful")).sum()),
        })
    return rows


def build_pass_network(
    df: pd.DataFrame,
    team: str | None = None,
    sub_window: str | int | None = "0",
    score_state: str | None = "all",
    time_range: str | None = "all",
    third: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {"team": team or "", "nodes": [], "edges": [], "heatmap": [], "windows": [], "centralization_index": 0.0}

    enriched_df, passes_df = _prepared_in_possession_frames(df)
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])
    team_events = enriched_df[enriched_df["teamName"] == selected_team].copy()
    windows = _pass_network_windows(enriched_df, selected_team)
    try:
        window_index = int(sub_window if sub_window is not None else 0)
    except (TypeError, ValueError):
        window_index = 0
    window = windows[window_index] if 0 <= window_index < len(windows) else windows[0]
    scoped_team_events = _window_scoped_events(team_events, window)
    bounds_start, bounds_end = _time_bounds_for_state(scoped_team_events, window, score_state)
    effective_time_window = {**window, "minute_start": bounds_start, "minute_end": bounds_end}
    normalized_time_range = _normalize_time_range_to_window(time_range, effective_time_window)
    controls_payload = {
        "score_state": score_state or "all",
        "time_range": normalized_time_range,
        "game_state_options": _available_game_state_options(scoped_team_events),
        "time_range_options": _time_range_option(
            bounds_start,
            bounds_end,
            f"{bounds_start}'-{bounds_end}'",
        ),
    }
    introduced_player_ids = _players_introduced_in_window(
        enriched_df,
        selected_team,
        int(window["minute_start"]),
        int(window["minute_end"]),
    )
    part_window_player_ids = _players_part_window(
        enriched_df,
        selected_team,
        int(window["minute_start"]),
        int(window["minute_end"]),
    ) if bool(window.get("is_merged")) else set()

    passes_df = _filter_score_state(passes_df, score_state)
    passes_df = _filter_time_range(passes_df, normalized_time_range)
    filtered = _filter_passes_for_window(
        enriched_df,
        passes_df,
        selected_team,
        int(window["minute_start"]),
        int(window["minute_end"]),
    )
    selected_third = _normalize_third(third)
    controls_payload["third"] = selected_third
    controls_payload["third_kpis"] = _third_kpis(filtered)
    filtered = _filter_by_third(filtered, selected_third)
    if filtered.empty:
        return {"team": selected_team, "nodes": [], "edges": [], "heatmap": [], "windows": windows, "window": window, "centralization_index": 0.0, **controls_payload}

    filtered["playerId"] = pd.to_numeric(filtered["playerId"], errors="coerce")
    filtered["receiver"] = pd.to_numeric(filtered["receiver"], errors="coerce")
    filtered = filtered.dropna(subset=["playerId", "receiver"])
    filtered = filtered[(filtered["playerId"] > 0) & (filtered["receiver"] > 0)].copy()
    filtered = filtered[filtered["outcomeType"].astype(str).str.lower().eq("successful")].copy()
    if filtered.empty:
        return {"team": selected_team, "nodes": [], "edges": [], "heatmap": [], "windows": windows, "window": window, "centralization_index": 0.0, **controls_payload}
    filtered["is_progressive"] = _progressive_pass_mask(filtered)
    event_minute = _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(-1)
    event_type = enriched_df.get("type", pd.Series("", index=enriched_df.index)).astype(str)
    event_outcome = enriched_df.get("outcomeType", pd.Series("", index=enriched_df.index)).astype(str).str.lower()
    take_on_types = {"TakeOn", "GoodSkill"}
    action_scope = (
        (enriched_df.get("teamName", pd.Series("", index=enriched_df.index)).astype(str) == selected_team)
        & (event_minute >= int(window["minute_start"]))
        & (event_minute < int(window["minute_end"]))
        & event_type.isin(["Carry", *take_on_types])
    )
    action_events = enriched_df[action_scope].copy()
    action_events = _filter_score_state(action_events, score_state)
    action_events = _filter_time_range(action_events, normalized_time_range)
    action_events = _filter_by_third(action_events, selected_third)
    if not action_events.empty:
        action_event_type = action_events.get("type", pd.Series("", index=action_events.index)).astype(str)
        action_event_outcome = action_events.get("outcomeType", pd.Series("", index=action_events.index)).astype(str).str.lower()
        action_success = action_event_type.eq("Carry") | action_event_outcome.eq("successful") | action_event_outcome.eq("nan") | action_events.get("outcomeType", pd.Series(index=action_events.index)).isna()
        action_events = action_events[action_success].copy()
        action_events["is_progressive"] = _progressive_action_mask(action_events)
    carries_by_player = action_events[action_events.get("type", pd.Series("", index=action_events.index)).astype(str).eq("Carry")].groupby("playerId").size() if not action_events.empty else pd.Series(dtype=int)
    progressive_carries_by_player = action_events[
        action_events.get("type", pd.Series("", index=action_events.index)).astype(str).eq("Carry")
        & action_events.get("is_progressive", pd.Series(False, index=action_events.index)).astype(bool)
    ].groupby("playerId").size() if not action_events.empty else pd.Series(dtype=int)
    take_ons_by_player = action_events[action_events.get("type", pd.Series("", index=action_events.index)).astype(str).isin(take_on_types)].groupby("playerId").size() if not action_events.empty else pd.Series(dtype=int)
    progressive_by_player = filtered[filtered["is_progressive"]].groupby("playerId").size()
    progressive_received_by_player = filtered[filtered["is_progressive"]].groupby("receiver").size()
    pass_distance = (
        ((_coerce_numeric(filtered["endX"]) - _coerce_numeric(filtered["x"])) ** 2)
        + ((_coerce_numeric(filtered["endY"]) - _coerce_numeric(filtered["y"])) ** 2)
    ) ** 0.5
    avg_pass_distance_by_player = filtered.assign(pass_distance=pass_distance).groupby("playerId")["pass_distance"].mean()

    made_locs = (
        filtered.groupby("playerId")
        .agg(
            play_x=("x", "median"),
            play_y=("y", "median"),
            passes_made=("playerId", "count"),
            player=("playerName", "first"),
            is_first_eleven=("isFirstEleven", "first"),
        )
    )
    received_locs = (
        filtered.groupby("receiver")
        .agg(
            receive_x=("endX", "median"),
            receive_y=("endY", "median"),
            passes_received=("receiver", "count"),
            receiver_name=("receiverName", "first"),
        )
    )
    average_locs = made_locs.merge(received_locs, left_index=True, right_index=True, how="outer")
    average_locs["player"] = average_locs["player"].fillna(average_locs["receiver_name"])
    average_locs["passes_made"] = average_locs["passes_made"].fillna(0).astype(int)
    average_locs["passes_received"] = average_locs["passes_received"].fillna(0).astype(int)
    average_locs["play_x"] = _coerce_numeric(average_locs["play_x"])
    average_locs["play_y"] = _coerce_numeric(average_locs["play_y"])
    average_locs["receive_x"] = _coerce_numeric(average_locs["receive_x"])
    average_locs["receive_y"] = _coerce_numeric(average_locs["receive_y"])
    average_locs["x"] = average_locs[["play_x", "receive_x"]].mean(axis=1)
    average_locs["y"] = average_locs[["play_y", "receive_y"]].mean(axis=1)
    average_locs["count"] = average_locs["passes_made"] + average_locs["passes_received"]
    average_locs["is_first_eleven"] = average_locs["is_first_eleven"].fillna(False)
    average_locs["progressive_passes_made"] = average_locs.index.map(progressive_by_player).fillna(0).astype(int)
    average_locs["progressive_passes_received"] = average_locs.index.map(progressive_received_by_player).fillna(0).astype(int)
    average_locs["avg_pass_distance"] = average_locs.index.map(avg_pass_distance_by_player).fillna(0)
    average_locs["carries"] = average_locs.index.map(carries_by_player).fillna(0).astype(int)
    average_locs["progressive_carries"] = average_locs.index.map(progressive_carries_by_player).fillna(0).astype(int)
    average_locs["take_ons"] = average_locs.index.map(take_ons_by_player).fillna(0).astype(int)

    max_count = max(1, int(average_locs["count"].max()))
    max_progressive_passes = max(1, int(average_locs["progressive_passes_made"].max()))
    nodes = []
    for player_id, row in average_locs.iterrows():
        nodes.append(
            {
                "player_id": int(player_id),
                "player": str(row["player"]),
                "label": _player_initials(str(row["player"])),
                "x": round(_safe_float(row["x"]), 2),
                "y": round(_safe_float(row["y"]), 2),
                "play_x": round(_safe_float(row["play_x"] if not pd.isna(row["play_x"]) else row["x"]), 2),
                "play_y": round(_safe_float(row["play_y"] if not pd.isna(row["play_y"]) else row["y"]), 2),
                "receive_x": round(_safe_float(row["receive_x"] if not pd.isna(row["receive_x"]) else row["x"]), 2),
                "receive_y": round(_safe_float(row["receive_y"] if not pd.isna(row["receive_y"]) else row["y"]), 2),
                "count": int(row["count"]),
                "passes_made": int(row["passes_made"]),
                "passes_received": int(row["passes_received"]),
                "progressive_passes_made": int(row["progressive_passes_made"]),
                "progressive_passes_received": int(row["progressive_passes_received"]),
                "carries": int(row["carries"]),
                "progressive_carries": int(row["progressive_carries"]),
                "take_ons": int(row["take_ons"]),
                "progressive_intensity": round(int(row["progressive_passes_made"]) / max_progressive_passes, 4),
                "avg_pass_distance": round(_safe_float(row["avg_pass_distance"]), 1),
                "size": round(18 + (int(row["count"]) / max_count) * 38, 2),
                "is_first_eleven": bool(row["is_first_eleven"]),
                "introduced_in_window": int(player_id) in introduced_player_ids,
                "part_window_player": int(player_id) in part_window_player_ids,
            }
        )

    directed_passes = filtered[["index", "playerId", "receiver", "x", "y", "endX", "endY", "xT", "is_progressive"]].copy()
    directed_passes["xT"] = _coerce_numeric(directed_passes["xT"]).fillna(0.0)
    pair_counts = (
        directed_passes.groupby(["playerId", "receiver"])
        .agg(
            pass_count=("index", "count"),
            connection_source_x=("x", "median"),
            connection_source_y=("y", "median"),
            connection_target_x=("endX", "median"),
            connection_target_y=("endY", "median"),
            total_xt=("xT", "sum"),
            avg_xt=("xT", "mean"),
            progressive_count=("is_progressive", "sum"),
        )
        .reset_index()
    )
    pair_counts = pair_counts.merge(average_locs, left_on="playerId", right_index=True).merge(
        average_locs,
        left_on="receiver",
        right_index=True,
        suffixes=("", "_end"),
    )
    pair_counts = pair_counts[pair_counts["playerId"] != pair_counts["receiver"]].copy()
    max_pair_count = max(1, int(pair_counts["pass_count"].max())) if not pair_counts.empty else 1
    max_pair_xt = max(0.001, float(pair_counts["total_xt"].clip(lower=0).max())) if not pair_counts.empty else 0.001
    max_pair_progressive = max(1, int(pair_counts["progressive_count"].max())) if not pair_counts.empty else 1
    edges = []
    for _, row in pair_counts.iterrows():
        edges.append(
            {
                "source_id": int(row["playerId"]),
                "target_id": int(row["receiver"]),
                "x0": round(_safe_float(row["x"]), 2),
                "y0": round(_safe_float(row["y"]), 2),
                "x1": round(_safe_float(row["x_end"]), 2),
                "y1": round(_safe_float(row["y_end"]), 2),
                "connection_source_x": round(_safe_float(row["connection_source_x"]), 2),
                "connection_source_y": round(_safe_float(row["connection_source_y"]), 2),
                "connection_target_x": round(_safe_float(row["connection_target_x"]), 2),
                "connection_target_y": round(_safe_float(row["connection_target_y"]), 2),
                "pass_count": int(row["pass_count"]),
                "total_xt": round(_safe_float(row["total_xt"]), 4),
                "avg_xt": round(_safe_float(row["avg_xt"]), 4),
                "xt_intensity": round(max(0.0, _safe_float(row["total_xt"])) / max_pair_xt, 4),
                "progressive_count": int(row["progressive_count"]),
                "progressive_intensity": round(int(row["progressive_count"]) / max_pair_progressive, 4),
                "width": round(0.8 + (int(row["pass_count"]) / max_pair_count) * 4.6, 2),
            }
        )

    positive_xt = filtered[_coerce_numeric(filtered.get("xT", pd.Series(0, index=filtered.index))).fillna(0) > 0].copy()
    heatmap = []
    heat_points = []
    if not positive_xt.empty:
        for _, row in positive_xt.iterrows():
            heat_points.append(
                {
                    "x": round(_safe_float(row.get("x")), 2),
                    "y": round(_safe_float(row.get("y")), 2),
                    "xT": round(_safe_float(row.get("xT")), 4),
                }
            )
        x_bins = pd.cut(_coerce_numeric(positive_xt["x"]).fillna(0), bins=14, labels=False, include_lowest=True)
        y_bins = pd.cut(_coerce_numeric(positive_xt["y"]).fillna(0), bins=10, labels=False, include_lowest=True)
        heat = positive_xt.assign(x_bin=x_bins, y_bin=y_bins).groupby(["x_bin", "y_bin"]).size().reset_index(name="count")
        for _, row in heat.iterrows():
            if pd.isna(row["x_bin"]) or pd.isna(row["y_bin"]):
                continue
            heatmap.append(
                {
                    "x": round((int(row["x_bin"]) + 0.5) * (105 / 14), 2),
                    "y": round((int(row["y_bin"]) + 0.5) * (68 / 10), 2),
                    "count": int(row["count"]),
                }
            )

    player_passes_count = filtered["playerId"].value_counts()
    total_passes = int(player_passes_count.sum())
    max_passes = int(player_passes_count.max()) if not player_passes_count.empty else 0
    denominator = total_passes * 10
    centralization_index = sum(max_passes - player_passes_count) / denominator if denominator else 0.0

    return {
        "team": selected_team,
        **controls_payload,
        "merged_window_note": (
            "This merged sub-window spans a substitution, so square nodes mark players who only appeared for part of the selected interval."
            if bool(window.get("is_merged")) and len(nodes) > 11 and part_window_player_ids
            else ""
        ),
        "nodes": nodes,
        "edges": edges,
        "heatmap": heatmap,
        "heat_points": heat_points,
        "windows": windows,
        "window": window,
        "centralization_index": round(float(centralization_index), 3),
        "total_passes": total_passes,
    }


def build_in_possession_actions_view(
    df: pd.DataFrame,
    team: str | None = None,
    sub_window: str | int | None = "0",
    score_state: str | None = "all",
    time_range: str | None = "all",
    third: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {"team": team or "", "actions": []}

    enriched_df, passes_df = _prepared_in_possession_frames(df)
    if "index" not in enriched_df.columns:
        enriched_df["index"] = range(len(enriched_df))
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])
    team_events = enriched_df[enriched_df["teamName"] == selected_team].copy()
    windows = _pass_network_windows(enriched_df, selected_team)
    minute_values = _coerce_numeric(team_events.get("minute", pd.Series(0, index=team_events.index))).fillna(-1)
    full_time = int(max(90, minute_values[minute_values >= 0].max())) if not minute_values[minute_values >= 0].empty else 90
    full_match_scope = str(sub_window or "").lower() in {"all", "full", "full-match", "full_match"}
    if full_match_scope:
        window = {
            "value": "all",
            "label": "Full match",
            "minute_start": 0,
            "minute_end": full_time,
            "source_window_count": len(windows),
            "is_merged": True,
        }
    else:
        try:
            window_index = int(sub_window if sub_window is not None else 0)
        except (TypeError, ValueError):
            window_index = 0
        window = windows[window_index] if 0 <= window_index < len(windows) else windows[0]
    scoped_team_events = _window_scoped_events(team_events, window)
    bounds_start, bounds_end = _time_bounds_for_state(scoped_team_events, window, score_state)
    effective_time_window = {**window, "minute_start": bounds_start, "minute_end": bounds_end}
    normalized_time_range = _normalize_time_range_to_window(time_range, effective_time_window)

    minute = _coerce_numeric(enriched_df.get("minute", pd.Series(0, index=enriched_df.index))).fillna(-1)
    event_type = enriched_df.get("type", pd.Series("", index=enriched_df.index)).astype(str)
    outcome = enriched_df.get("outcomeType", pd.Series("", index=enriched_df.index)).astype(str).str.lower()
    take_on_types = {"TakeOn", "GoodSkill"}
    action_mask = event_type.isin(["Pass", "Carry", *take_on_types]) & (enriched_df["teamName"].astype(str) == selected_team)
    action_mask = action_mask & (minute >= int(window["minute_start"])) & (minute < int(window["minute_end"]))
    actions_df = enriched_df[action_mask].copy()
    actions_df = _filter_score_state(actions_df, score_state)
    actions_df = _filter_time_range(actions_df, normalized_time_range)
    actions_df = _filter_by_third(actions_df, _normalize_third(third))
    if actions_df.empty:
        return {"team": selected_team, "actions": [], "time_range": normalized_time_range, "window": window}

    actions_df["is_progressive"] = _progressive_action_mask(actions_df)
    sort_cols = [col for col in ("minute", "second", "index") if col in enriched_df.columns]
    ordered_events = enriched_df.sort_values(sort_cols).reset_index(drop=True)
    event_positions = {int(row_index): pos for pos, row_index in enumerate(ordered_events["index"].tolist())}

    def _next_context(row: pd.Series) -> dict[str, Any]:
        row_index = _safe_int(row.get("index"))
        position = event_positions.get(row_index)
        if position is None:
            return {}
        next_events = ordered_events.iloc[position + 1 : position + 12]
        meaningful = next_events[
            next_events.get("type", pd.Series("", index=next_events.index)).astype(str).str.len().gt(0)
            & next_events.get("teamName", pd.Series("", index=next_events.index)).astype(str).str.len().gt(0)
        ].head(3)
        context: dict[str, Any] = {}
        for offset, (_, next_row) in enumerate(meaningful.iterrows(), start=1):
            prefix = f"next_{offset}"
            context[f"{prefix}_team"] = str(next_row.get("teamName", ""))
            context[f"{prefix}_player"] = str(next_row.get("playerName", ""))
            context[f"{prefix}_type"] = str(next_row.get("type", ""))
            context[f"{prefix}_minute"] = _safe_int(next_row.get("minute"))
            context[f"{prefix}_second"] = _safe_int(next_row.get("second"))
            context[f"{prefix}_x"] = _safe_float(next_row.get("x"))
            context[f"{prefix}_y"] = _safe_float(next_row.get("y"))
            context[f"{prefix}_end_x"] = _safe_float(next_row.get("endX"))
            context[f"{prefix}_end_y"] = _safe_float(next_row.get("endY"))
        context["next_team_retained"] = bool(str(context.get("next_1_team", "")) == str(row.get("teamName", "")))
        return context

    rows: list[dict[str, Any]] = []
    for _, row in actions_df.sort_values([col for col in ("minute", "second", "index") if col in actions_df.columns]).iterrows():
        start_x = _safe_float(row.get("x"))
        start_y = _safe_float(row.get("y"))
        raw_end_x = row.get("endX")
        raw_end_y = row.get("endY")
        end_x = start_x if pd.isna(raw_end_x) else _safe_float(raw_end_x)
        end_y = start_y if pd.isna(raw_end_y) else _safe_float(raw_end_y)
        raw_type = str(row.get("type", ""))
        display_type = "TakeOn" if raw_type in take_on_types else raw_type
        action = {
            "id": str(row.get("index", "")),
            "minute": _safe_int(row.get("minute")),
            "second": _safe_int(row.get("second")),
            "team": str(row.get("teamName", "")),
            "player": str(row.get("playerName", "")),
            "player_id": _safe_int(row.get("playerId")),
            "type": display_type,
            "outcome": str(row.get("outcomeType", "")),
            "is_successful": bool(
                str(row.get("type", "")) == "Carry"
                or str(row.get("outcomeType", "")).lower() in {"successful", "nan", ""}
                or pd.isna(row.get("outcomeType"))
            ),
            "x": start_x,
            "y": start_y,
            "end_x": end_x,
            "end_y": end_y,
            "xT": round(_safe_float(row.get("xT")), 4),
            "xA": round(_safe_float(row.get("xA")), 4),
            "epv_added": round(_safe_float(row.get("epv_added")), 4),
            "epv_start": round(_safe_float(row.get("epv_start")), 4),
            "epv_end": round(_safe_float(row.get("epv_end")), 4),
            "is_progressive": bool(row.get("is_progressive", False)),
            "sequence_id": str(row.get("sequence_id", row.get("sequenceId", ""))),
            "game_state": str(row.get("team_score_state", "level")),
            "game_state_label": str(row.get("team_score_state_label", "Level")),
            "score_before": str(row.get("score_before", "0-0")),
        }
        action.update(_next_context(row))
        rows.append(action)

    return {
        "team": selected_team,
        "actions": rows,
        "time_range": normalized_time_range,
        "window": window,
    }


def build_in_possession_player_metrics(
    df: pd.DataFrame,
    team: str | None = None,
    sub_window: str | int | None = "0",
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {"team": team or "", "rows": [], "windows": [], "window": None}

    enriched_df, passes_df = _prepared_in_possession_frames(df)
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])
    full_team_df = enriched_df[enriched_df["teamName"] == selected_team].copy()
    if full_team_df.empty or "playerName" not in full_team_df.columns:
        return {"team": selected_team, "rows": [], "windows": [], "window": None}

    minute = _coerce_numeric(full_team_df.get("minute", pd.Series(0, index=full_team_df.index))).fillna(-1)
    full_time = int(max(90, minute[minute >= 0].max())) if not minute[minute >= 0].empty else 90
    windows = _pass_network_windows(enriched_df, selected_team)
    full_match_scope = str(sub_window or "").lower() in {"all", "full", "full-match", "full_match"}
    if full_match_scope:
        window = {
            "value": "all",
            "label": "Full match",
            "minute_start": 0,
            "minute_end": full_time,
            "source_window_count": len(windows),
            "is_merged": True,
        }
    else:
        try:
            window_index = int(sub_window if sub_window is not None else 0)
        except (TypeError, ValueError):
            window_index = 0
        window = windows[window_index] if 0 <= window_index < len(windows) else windows[0]
    window_team_df = full_team_df.copy() if full_match_scope else _window_scoped_events(full_team_df, window)
    bounds_start, bounds_end = _time_bounds_for_state(window_team_df, window, score_state)
    effective_time_window = {**window, "minute_start": bounds_start, "minute_end": bounds_end}
    normalized_time_range = _normalize_time_range_to_window(time_range, effective_time_window)
    scoped = _filter_score_state(window_team_df, score_state)
    scoped = _filter_time_range(scoped, normalized_time_range)

    player_status: dict[str, dict[str, Any]] = {}
    for player, player_df in full_team_df.groupby("playerName"):
        if not player or (isinstance(player, float) and math.isnan(player)):
            continue
        player_name = str(player)
        player_minutes = _coerce_numeric(player_df.get("minute", pd.Series(0, index=player_df.index))).fillna(-1)
        player_types = player_df.get("type", pd.Series("", index=player_df.index)).astype(str)
        is_starter = bool(_bool_series(player_df, "isFirstEleven").any()) if "isFirstEleven" in player_df.columns else False
        sub_on_minutes = player_minutes[player_types.eq("SubstitutionOn") & (player_minutes >= 0)]
        sub_off_minutes = player_minutes[player_types.eq("SubstitutionOff") & (player_minutes >= 0)]
        if not sub_on_minutes.empty:
            start_minute = int(sub_on_minutes.min())
        else:
            start_minute = 0
        off_after_start = sub_off_minutes[sub_off_minutes >= start_minute]
        end_minute = int(off_after_start.min()) if not off_after_start.empty else full_time
        minutes_played = max(0, min(full_time, end_minute) - min(full_time, start_minute))
        player_status[player_name] = {
            "is_substitute": bool(not sub_on_minutes.empty),
            "minutes_played": int(minutes_played),
        }

    team_passes = passes_df[passes_df["teamName"] == selected_team].copy()
    team_passes = _filter_score_state(team_passes, score_state)
    team_passes = _filter_time_range(team_passes, normalized_time_range)
    successful_passes = team_passes[team_passes["outcomeType"].astype(str).str.lower().eq("successful")].copy()
    received_counts = successful_passes.dropna(subset=["receiverName"])["receiverName"].astype(str).value_counts()

    rows: list[dict[str, Any]] = []
    metric_players = set(full_team_df["playerName"].dropna().astype(str).tolist())
    for player_name in sorted(metric_players):
        player_df = scoped[scoped["playerName"].astype(str).eq(player_name)].copy()
        if not player_name:
            continue
        types = player_df.get("type", pd.Series("", index=player_df.index)).astype(str)
        passes = player_df[types.eq("Pass")].copy()
        completed = passes["outcomeType"].astype(str).str.lower().eq("successful") if "outcomeType" in passes.columns else pd.Series(True, index=passes.index)
        completed_passes = passes[completed].copy()
        pass_attempts = int(len(passes))
        pass_completed = int(len(completed_passes))
        pass_accuracy = round((pass_completed / pass_attempts) * 100, 1) if pass_attempts else 0.0

        if not completed_passes.empty:
            pass_distance = (
                ((_coerce_numeric(completed_passes["endX"]) - _coerce_numeric(completed_passes["x"])) ** 2)
                + ((_coerce_numeric(completed_passes["endY"]) - _coerce_numeric(completed_passes["y"])) ** 2)
            ) ** 0.5
            avg_pass_distance = round(float(pass_distance.mean()), 1)
        else:
            avg_pass_distance = 0.0

        progressive_passes = int(_progressive_action_mask(completed_passes).sum())
        progressive_passes_received = int(successful_passes[
            successful_passes["receiverName"].astype(str).eq(player_name)
            & _progressive_action_mask(successful_passes)
        ].shape[0]) if not successful_passes.empty else 0
        final_third_passes = int((_coerce_numeric(completed_passes.get("endX", pd.Series(0, index=completed_passes.index))).fillna(0) > 75).sum())
        box_passes = int((
            (_coerce_numeric(completed_passes.get("endX", pd.Series(0, index=completed_passes.index))).fillna(0) >= 88.5)
            & (_coerce_numeric(completed_passes.get("endY", pd.Series(0, index=completed_passes.index))).fillna(0).between(13.6, 54.4))
        ).sum())

        key_passes = 0
        if "passKey" in passes.columns:
            key_passes = int(_bool_series(passes, "passKey").sum())
        elif "qualifiers" in passes.columns:
            key_passes = int(passes["qualifiers"].astype(str).str.contains("KeyPass|ShotAssist|BigChanceCreated", case=False, na=False).sum())

        carries = player_df[types.eq("Carry")].copy()
        progressive_carries = int(_progressive_action_mask(carries).sum())
        take_ons = player_df[types.isin(["TakeOn", "GoodSkill"])].copy()
        take_on_outcomes = take_ons.get("outcomeType", pd.Series("", index=take_ons.index)).astype(str).str.lower() if not take_ons.empty else pd.Series(dtype=str)
        take_ons_won = int((take_on_outcomes.eq("successful") | take_on_outcomes.eq("nan") | take_on_outcomes.eq("")).sum()) if not take_ons.empty else 0
        touches = int(_bool_series(player_df, "isTouch").sum()) if "isTouch" in player_df.columns else int(types.isin(["Pass", "BallTouch", "TakeOn", "GoodSkill"]).sum())
        turnovers = int((_coerce_numeric(player_df.get("turnover", pd.Series(0, index=player_df.index))).fillna(0) + _coerce_numeric(player_df.get("dispossessed", pd.Series(0, index=player_df.index))).fillna(0)).sum())
        xt_total = float(_coerce_numeric(player_df[types.isin(["Pass", "Carry"])].get("xT", pd.Series(0, index=player_df.index))).fillna(0).sum())
        epv_total = float(_coerce_numeric(player_df[types.isin(["Pass", "Carry"])].get("epv_added", pd.Series(0, index=player_df.index))).fillna(0).sum())
        xa_total = float(_coerce_numeric(passes.get("xA", pd.Series(0, index=passes.index))).fillna(0).sum())
        passes_received = int(received_counts.get(player_name, 0))
        status = player_status.get(player_name, {"is_substitute": False, "minutes_played": 0})

        rows.append(
            {
                "player": player_name,
                "team": selected_team,
                "minutes_played": int(status["minutes_played"]),
                "is_substitute": bool(status["is_substitute"]),
                "touches": touches,
                "passes_attempted": pass_attempts,
                "passes_completed": pass_completed,
                "pass_accuracy": pass_accuracy,
                "passes_received": passes_received,
                "avg_pass_distance": avg_pass_distance,
                "progressive_passes": progressive_passes,
                "progressive_passes_received": progressive_passes_received,
                "final_third_passes": final_third_passes,
                "box_passes": box_passes,
                "key_passes": key_passes,
                "xA": round(xa_total, 3),
                "xT": round(xt_total, 3),
                "epv_added": round(epv_total, 3),
                "carries": int(len(carries)),
                "progressive_carries": progressive_carries,
                "take_ons_won": take_ons_won,
                "turnovers": turnovers,
            }
        )

    rows.sort(key=lambda row: (row["minutes_played"], row["passes_attempted"], row["touches"], row["xT"]), reverse=True)
    return {
        "team": selected_team,
        "score_state": score_state or "all",
        "time_range": normalized_time_range,
        "game_state_options": _available_game_state_options(window_team_df),
        "time_range_options": _time_range_option(
            bounds_start,
            bounds_end,
            f"{bounds_start}'-{bounds_end}'",
        ),
        "rows": rows,
        "windows": windows,
        "window": window,
    }


CHANNEL_BOUNDS: list[tuple[str, float, float]] = [
    ("right_wing", 0.0, 13.6),
    ("right_half_space", 13.6, 27.2),
    ("central", 27.2, 40.8),
    ("left_half_space", 40.8, 54.4),
    ("left_wing", 54.4, 68.01),
]

CHANNEL_LABELS = {
    "right_wing": "Right Wing",
    "right_half_space": "Right Half-Space",
    "central": "Central Corridor",
    "left_half_space": "Left Half-Space",
    "left_wing": "Left Wing",
}

# Juego de Posición grid (mplsoccer uefa positional lines).
ZONE_X_BOUNDS: list[float] = [0.0, 16.5, 34.5, 52.5, 70.5, 88.5, 105.01]
ZONE_Y_LANES: list[tuple[str, str, float, float]] = [
    ("right_wing", "RW", 0.0, 13.84),
    ("right_half_space", "RHS", 13.84, 24.84),
    ("central", "C", 24.84, 43.16),
    ("left_half_space", "LHS", 43.16, 54.16),
    ("left_wing", "LW", 54.16, 68.01),
]


def build_channel_analysis(
    df: pd.DataFrame,
    team: str | None = None,
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    """Per-channel (wings / half-spaces / center) in-possession profile for a team."""
    if df.empty or "teamName" not in df.columns:
        return {"team": team or "", "channels": [], "zones": [], "channels_received": [], "zones_received": []}

    enriched_df, _ = _prepared_in_possession_frames(df)
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])
    events = enriched_df[enriched_df["teamName"] == selected_team].copy()
    events = _filter_score_state(events, score_state)
    events = _filter_time_range(events, time_range)
    if events.empty:
        return {"team": selected_team, "channels": [], "zones": [], "channels_received": [], "zones_received": []}

    event_type = events.get("type", pd.Series("", index=events.index)).astype(str)
    outcome = events.get("outcomeType", pd.Series("", index=events.index)).astype(str).str.lower()
    y = _coerce_numeric(events.get("y", pd.Series(-1, index=events.index))).fillna(-1)
    end_x = _coerce_numeric(events.get("endX", pd.Series(-1, index=events.index))).fillna(-1)
    end_y = _coerce_numeric(events.get("endY", pd.Series(-1, index=events.index))).fillna(-1)
    xt = _coerce_numeric(events.get("xT", pd.Series(0, index=events.index))).fillna(0.0)
    # Open play only: drop set-piece deliveries (the restart event itself). Play
    # that continues after the restart still counts.
    qualifiers = events.get("qualifiers", pd.Series("", index=events.index)).astype(str)
    set_piece_delivery = qualifiers.str.contains(
        "CornerTaken|FreekickTaken|IndirectFreekickTaken|ThrowIn|GoalKick|KeeperThrow|KickOff",
        case=False,
        na=False,
    )
    on_ball = event_type.isin(["Pass", "Carry", "TakeOn", "GoodSkill"]) & ~set_piece_delivery
    is_pass = event_type.eq("Pass")
    successful = outcome.eq("successful") | outcome.eq("nan") | events.get("outcomeType", pd.Series(index=events.index)).isna()
    progressive = _progressive_action_mask(events)

    x = _coerce_numeric(events.get("x", pd.Series(-1, index=events.index))).fillna(-1)
    player_names = events.get("playerName", pd.Series("", index=events.index)).astype(str)

    def area_extras(mask: pd.Series) -> dict[str, Any]:
        """Progressive flow vector + top xT contributor for a channel/zone mask."""
        scope = mask & successful
        extras: dict[str, Any] = {
            "flow_dx": 0.0,
            "flow_dy": 0.0,
            "flow_count": 0,
            "top_player": "",
            "top_player_xt": 0.0,
        }
        prog_scope = scope & progressive
        if bool(prog_scope.any()):
            extras["flow_dx"] = round(float((end_x[prog_scope] - x[prog_scope]).mean()), 2)
            extras["flow_dy"] = round(float((end_y[prog_scope] - y[prog_scope]).mean()), 2)
            extras["flow_count"] = int(prog_scope.sum())
        gained_by_action = xt[scope].clip(lower=0)
        if float(gained_by_action.sum()) > 0:
            by_player = gained_by_action.groupby(player_names[scope]).sum().sort_values(ascending=False)
            top_name = str(by_player.index[0])
            if top_name and top_name.lower() != "nan":
                extras["top_player"] = top_name
                extras["top_player_xt"] = round(float(by_player.iloc[0]), 3)
        return extras

    def metric_rows(ax: pd.Series, ay: pd.Series) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Channel + zone rows where actions are assigned by (ax, ay) — pass the
        start coordinates for the origin view, end coordinates for destination."""
        channel_rows: list[dict[str, Any]] = []
        total_gained = 0.0
        for key, low, high in CHANNEL_BOUNDS:
            in_channel = (ay >= low) & (ay < high) & on_ball
            entries = successful & (end_x >= 70) & (end_y >= low) & (end_y < high) & on_ball
            values = xt[in_channel & successful]
            gained = float(values.clip(lower=0).sum())
            lost = float(values.clip(upper=0).sum())
            total_gained += gained
            channel_rows.append({
                "channel": key,
                "label": CHANNEL_LABELS[key],
                "y_start": low,
                "y_end": min(high, 68.0),
                "touches": int(in_channel.sum()),
                "passes": int((in_channel & is_pass).sum()),
                "passes_completed": int((in_channel & is_pass & successful).sum()),
                "progressive_actions": int((in_channel & progressive & successful).sum()),
                "xt": round(gained + lost, 3),
                "xt_gained": round(gained, 3),
                "xt_lost": round(lost, 3),
                "final_third_entries": int(entries.sum()),
                **area_extras(in_channel),
            })
        for row in channel_rows:
            row["xt_share"] = round(row["xt_gained"] / total_gained, 3) if total_gained > 0 else 0.0

        zone_rows: list[dict[str, Any]] = []
        zone_total_gained = 0.0
        box_lane_names = {
            "right_half_space": ("Box Right", "Box R"),
            "central": ("Box Centre", "Box C"),
            "left_half_space": ("Box Left", "Box L"),
        }
        last_column = len(ZONE_X_BOUNDS) - 2
        for lane_key, lane_short, lane_low, lane_high in ZONE_Y_LANES:
            cells: list[tuple[str, str, str, float, float]] = []
            for column in range(len(ZONE_X_BOUNDS) - 1):
                x_low, x_high = ZONE_X_BOUNDS[column], ZONE_X_BOUNDS[column + 1]
                if column == last_column and lane_key in box_lane_names:
                    # Everything dangerous funnels into the box — split the box
                    # lanes at the six-yard line so danger differentiates there.
                    long_name, short_name = box_lane_names[lane_key]
                    cells.append((f"{lane_key}_box_entry", f"{short_name} · Entry", f"{long_name} · Entry", 88.5, 99.5))
                    cells.append((f"{lane_key}_box_6yd", f"{short_name} · 6yd", f"{long_name} · Six-Yard", 99.5, 105.01))
                else:
                    cells.append((
                        f"{lane_key}_z{column + 1}",
                        f"{lane_short} · Z{column + 1}",
                        f"{CHANNEL_LABELS[lane_key]} · Zone {column + 1}",
                        x_low,
                        x_high,
                    ))
            for zone_id, label, long_label, x_low, x_high in cells:
                in_zone = (ay >= lane_low) & (ay < lane_high) & (ax >= x_low) & (ax < x_high) & on_ball
                values = xt[in_zone & successful]
                gained = float(values.clip(lower=0).sum())
                lost = float(values.clip(upper=0).sum())
                zone_total_gained += gained
                zone_rows.append({
                    "zone": zone_id,
                    "label": label,
                    "long_label": long_label,
                    "x_start": x_low,
                    "x_end": min(x_high, 105.0),
                    "y_start": lane_low,
                    "y_end": min(lane_high, 68.0),
                    "touches": int(in_zone.sum()),
                    "passes": int((in_zone & is_pass).sum()),
                    "passes_completed": int((in_zone & is_pass & successful).sum()),
                    "progressive_actions": int((in_zone & progressive & successful).sum()),
                    "xt": round(gained + lost, 3),
                    "xt_gained": round(gained, 3),
                    "xt_lost": round(lost, 3),
                    **area_extras(in_zone),
                })
        for row in zone_rows:
            row["xt_share"] = round(row["xt_gained"] / zone_total_gained, 3) if zone_total_gained > 0 else 0.0
        return channel_rows, zone_rows

    channels, zones = metric_rows(x, y)
    channels_received, zones_received = metric_rows(end_x, end_y)

    return {
        "team": selected_team,
        "channels": channels,
        "zones": zones,
        "channels_received": channels_received,
        "zones_received": zones_received,
        "score_state": score_state or "all",
        "time_range": time_range or "all",
    }


def build_combination_play(
    df: pd.DataFrame,
    team: str | None = None,
    score_state: str | None = "all",
    time_range: str | None = "all",
) -> dict[str, Any]:
    """Pass pairs, one-twos, and passing triangles within possessions."""
    empty = {"team": team or "", "pairs": [], "one_twos": [], "triangles": []}
    if df.empty or "teamName" not in df.columns:
        return empty

    enriched_df, passes_df = _prepared_in_possession_frames(df)
    selected_team = team or str(enriched_df["teamName"].dropna().iloc[0])

    passes = passes_df[passes_df["teamName"] == selected_team].copy()
    passes = _filter_score_state(passes, score_state)
    passes = _filter_time_range(passes, time_range)
    if passes.empty:
        return {**empty, "team": selected_team}

    passes["playerId"] = pd.to_numeric(passes.get("playerId"), errors="coerce")
    passes["receiver"] = pd.to_numeric(passes.get("receiver"), errors="coerce")
    outcome = passes.get("outcomeType", pd.Series("", index=passes.index)).astype(str).str.lower()
    completed = passes[outcome.eq("successful")].dropna(subset=["playerId", "receiver"]).copy()
    if completed.empty:
        return {**empty, "team": selected_team}
    completed = completed[completed["playerId"] != completed["receiver"]]

    id_to_name: dict[float, str] = (
        enriched_df.dropna(subset=["playerId"])
        .assign(playerId=lambda d: pd.to_numeric(d["playerId"], errors="coerce"))
        .groupby("playerId")["playerName"].first()
        .to_dict()
    )

    def name_of(player_id: Any) -> str:
        return str(id_to_name.get(player_id, "")).strip() or f"#{int(player_id)}"

    completed["xT"] = _coerce_numeric(completed.get("xT", pd.Series(0, index=completed.index))).fillna(0.0)

    # ── Directed pass pairs ─────────────────────────────────────────────────
    pair_groups = completed.groupby(["playerId", "receiver"]).agg(
        count=("playerId", "size"),
        xt=("xT", "sum"),
        avg_x=("x", "median"),
        avg_y=("y", "median"),
        avg_end_x=("endX", "median"),
        avg_end_y=("endY", "median"),
    ).reset_index().sort_values("count", ascending=False)
    pairs = [
        {
            "from": name_of(row.playerId),
            "to": name_of(row.receiver),
            "count": int(row.count),
            "xt": round(float(row.xt), 3),
            "avg_x": round(float(row.avg_x), 1),
            "avg_y": round(float(row.avg_y), 1),
            "avg_end_x": round(float(row.avg_end_x), 1),
            "avg_end_y": round(float(row.avg_end_y), 1),
        }
        for row in pair_groups.head(12).itertuples()
    ]

    # ── One-twos and triangles (sequence scans within possessions) ─────────
    if "possession_id" not in completed.columns:
        completed["possession_id"] = -1
    minute = _coerce_numeric(completed.get("minute", pd.Series(0, index=completed.index))).fillna(0.0)
    second = _coerce_numeric(completed.get("second", pd.Series(0, index=completed.index))).fillna(0.0)
    completed["t_abs"] = minute * 60.0 + second
    sort_cols = [col for col in ("possession_id", "t_abs", "index") if col in completed.columns]
    ordered = completed.sort_values(sort_cols)

    one_twos: list[dict[str, Any]] = []
    triangle_counts: dict[tuple[str, ...], int] = {}
    prev_rows: list[Any] = []
    prev_possession = None
    for row in ordered.itertuples():
        possession = getattr(row, "possession_id", -1)
        if possession != prev_possession:
            prev_rows = []
            prev_possession = possession
        if prev_rows:
            p1 = prev_rows[-1]
            # one-two: A -> B then B -> A quickly, with territorial gain
            if (
                p1.receiver == row.playerId
                and p1.playerId == row.receiver
                and (row.t_abs - p1.t_abs) <= 8.0
                and float(row.endX) > float(p1.x) + 5.0
            ):
                one_twos.append({
                    "player_a": name_of(p1.playerId),
                    "player_b": name_of(p1.receiver),
                    "minute": int(p1.t_abs // 60),
                    "x": round(float(p1.x), 1),
                    "y": round(float(p1.y), 1),
                    "mid_x": round(float(p1.endX), 1),
                    "mid_y": round(float(p1.endY), 1),
                    "end_x": round(float(row.endX), 1),
                    "end_y": round(float(row.endY), 1),
                    "gain": round(float(row.endX) - float(p1.x), 1),
                })
        if len(prev_rows) >= 2:
            p1, p2 = prev_rows[-2], prev_rows[-1]
            chain_ok = p1.receiver == p2.playerId and p2.receiver == row.playerId
            names = {name_of(p1.playerId), name_of(p2.playerId), name_of(row.playerId)}
            if chain_ok and len(names) == 3 and (row.t_abs - p1.t_abs) <= 20.0:
                key = tuple(sorted(names))
                triangle_counts[key] = triangle_counts.get(key, 0) + 1
        prev_rows.append(row)

    triangles = [
        {"players": list(players), "count": count}
        for players, count in sorted(triangle_counts.items(), key=lambda item: -item[1])[:6]
        if count >= 2
    ]

    return {
        "team": selected_team,
        "pairs": pairs,
        "one_twos": sorted(one_twos, key=lambda item: -item["gain"])[:15],
        "triangles": triangles,
        "score_state": score_state or "all",
        "time_range": time_range or "all",
    }
