import pandas as pd

from app.services.matches import (
    build_event_timeline,
    build_match_summary_view,
    build_player_stats,
    build_shot_details,
    build_shot_player_summary,
    build_shot_events,
)


def _sample_df():
    return pd.DataFrame(
        [
            {
                "matchId": "123",
                "teamName": "Arsenal",
                "playerName": "Player A",
                "minute": 12,
                "type": "Pass",
                "outcomeType": "Successful",
                "isShot": False,
                "isGoal": False,
                "xG": 0.0,
                "period": "FirstHalf",
            },
            {
                "matchId": "123",
                "teamName": "Arsenal",
                "playerName": "Player A",
                "minute": 22,
                "type": "Goal",
                "outcomeType": "Goal",
                "isShot": True,
                "isGoal": True,
                "xG": 0.31,
                "period": "FirstHalf",
                "situation": "Open Play",
                "x": 88,
                "y": 32,
            },
            {
                "matchId": "123",
                "teamName": "Chelsea",
                "playerName": "Player B",
                "minute": 61,
                "type": "SavedShot",
                "outcomeType": "Saved",
                "isShot": True,
                "isGoal": False,
                "xG": 0.14,
                "period": "SecondHalf",
                "situation": "Set Piece",
                "x": 74,
                "y": 54,
            },
        ]
    )


def test_build_player_stats_returns_ranked_rows():
    rows = build_player_stats(_sample_df())
    assert rows[0]["player"] == "Player A"
    assert rows[0]["goals"] == 1


def test_build_shot_events_filters_by_team():
    rows = build_shot_events(_sample_df(), team="Arsenal")
    assert len(rows) == 1
    assert rows[0]["player"] == "Player A"


def test_build_event_timeline_sorts_by_minute():
    timeline = build_event_timeline(_sample_df())
    assert [row["minute"] for row in timeline] == [12, 22, 61]


def test_build_match_summary_view_groups_by_period():
    summary = build_match_summary_view(_sample_df())
    assert summary["summary_cards"]["shots"] == 2
    assert summary["periods"]["FirstHalf"]["goals"] == 1


def test_build_shot_player_summary_returns_aggregates():
    rows = build_shot_player_summary(_sample_df(), team="Arsenal")
    assert len(rows) == 1
    assert rows[0]["playerName"] == "Player A"
    assert rows[0]["Goals"] == 1


def test_build_shot_details_filters_by_player():
    rows = build_shot_details(_sample_df(), player="Player B")
    assert len(rows) == 1
    assert rows[0]["type"] == "SavedShot"
