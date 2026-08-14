from __future__ import annotations

import sqlite3

import pandas as pd
import pytest

from db_to_parquet import _selected_match_ids
import data_utils
import dry_run_xgot_backfill
from league_sources import resolve_league_source


def test_mls_uses_canonical_storage_key_and_provider_competition():
    source = resolve_league_source("usa", "mls")
    assert source.key == "mls"
    assert source.provider_competition == "usa-major-league-soccer"


def test_configured_league_rejects_wrong_country():
    with pytest.raises(ValueError):
        resolve_league_source("canada", "mls")


def test_pending_upload_selection_is_scoped_and_limited():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE processed_matches "
        "(matchId TEXT PRIMARY KEY, league TEXT, season TEXT, startDate TEXT, uploaded BOOLEAN)"
    )
    conn.executemany(
        "INSERT INTO processed_matches VALUES (?, ?, ?, ?, ?)",
        [
            ("3", "mls", "2026", "2026-02-23", 0),
            ("1", "mls", "2026", "2026-02-21", 0),
            ("2", "mls", "2026", "2026-02-22", 0),
            ("4", "mls", "2025", "2025-02-22", 0),
            ("5", "premier-league", "2025/2026", "2026-02-22", 0),
            ("6", "mls", "2026", "2026-02-20", 1),
        ],
    )
    assert _selected_match_ids(conn, "mls", "2026", 2) == ["1", "2"]


def test_xgot_dry_run_deduplicates_prediction_keys(monkeypatch):
    events = pd.DataFrame(
        [
            {"matchId": 1, "eventId": 10, "teamId": 1, "type": "Goal", "xGOT": 0.4, "xgot_is_on_target": False},
            {"matchId": 1, "eventId": 10, "teamId": 1, "type": "Goal", "xGOT": 0.4, "xgot_is_on_target": False},
        ]
    )
    predictions = pd.DataFrame(
        [
            {
                "matchId": 1,
                "eventId": 10,
                "xGOT": 0.4,
                "xgot_model_version": "v1",
                "goal_mouth_zone": "low_center",
                "xgot_is_on_target": True,
                "xgot_is_blocked": False,
                "xgot_zero_value": False,
                "xgot_training_eligible": True,
            },
            {
                "matchId": 1,
                "eventId": 10,
                "xGOT": 0.9,
                "xgot_model_version": "v1",
                "goal_mouth_zone": "high_center",
                "xgot_is_on_target": True,
                "xgot_is_blocked": False,
                "xgot_zero_value": False,
                "xgot_training_eligible": True,
            },
        ]
    )
    monkeypatch.setattr(dry_run_xgot_backfill, "_read_parquet", lambda key: events)
    monkeypatch.setattr(dry_run_xgot_backfill, "predict_shot_xgot", lambda df, version: predictions)

    rows, summary = dry_run_xgot_backfill._compare_file("test.parquet", "v1")

    assert len(rows) == 1
    assert summary["shots"] == 1
    assert summary["new_xgot"] == 0.4
    assert summary["delta_xgot"] == 0.0
    assert summary["on_target_shots"] == 1


def test_xt_merge_preserves_canonical_competition_metadata(monkeypatch):
    events = pd.DataFrame(
        [
            {
                "index": 1,
                "qualifiers": "[]",
                "type": "Pass",
                "outcomeType": "Successful",
                "x": 20.0,
                "y": 30.0,
                "endX": 40.0,
                "endY": 30.0,
                "league": "mls",
                "country": "usa",
                "season": "2026",
            }
        ]
    )
    monkeypatch.setattr(
        data_utils.pd,
        "read_csv",
        lambda *args, **kwargs: pd.DataFrame([[0.0, 0.1], [0.2, 0.3]]),
    )

    enriched = data_utils.get_xT_values(events)

    assert enriched.loc[0, "league"] == "mls"
    assert enriched.loc[0, "country"] == "usa"
    assert enriched.loc[0, "season"] == "2026"
    assert not any(column.endswith(("_x", "_y")) for column in enriched.columns)
    assert pd.notna(enriched.loc[0, "xT"])
