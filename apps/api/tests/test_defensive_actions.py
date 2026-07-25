import pandas as pd

from app.services.views.defensive_actions import build_defensive_actions_view


def test_defensive_transitions_pair_losses_with_counterpress_and_later_regains():
    events = pd.DataFrame(
        [
            {
                "teamName": "Alpha",
                "playerName": "Lost Ball",
                "minute": 10,
                "second": 0,
                "period": "FirstHalf",
                "type": "Turnover",
                "outcomeType": "Unsuccessful",
                "x": 58,
                "y": 32,
            },
            {
                "teamName": "Beta",
                "playerName": "Carrier",
                "minute": 10,
                "second": 1,
                "period": "FirstHalf",
                "type": "Carry",
                "outcomeType": "Successful",
                "x": 47,
                "y": 32,
            },
            {
                "teamName": "Alpha",
                "playerName": "Presser",
                "minute": 10,
                "second": 2,
                "period": "FirstHalf",
                "type": "Challenge",
                "outcomeType": "Unsuccessful",
                "x": 50,
                "y": 31,
            },
            {
                "teamName": "Alpha",
                "playerName": "Regainer",
                "minute": 10,
                "second": 4,
                "period": "FirstHalf",
                "type": "Interception",
                "outcomeType": "Successful",
                "x": 52,
                "y": 31,
            },
            {
                "teamName": "Alpha",
                "playerName": "Lost Ball",
                "minute": 20,
                "second": 0,
                "period": "FirstHalf",
                "type": "Dispossessed",
                "outcomeType": "Unsuccessful",
                "x": 72,
                "y": 20,
            },
            {
                "teamName": "Beta",
                "playerName": "Carrier",
                "minute": 20,
                "second": 1,
                "period": "FirstHalf",
                "type": "Carry",
                "outcomeType": "Successful",
                "x": 33,
                "y": 48,
            },
            {
                "teamName": "Alpha",
                "playerName": "Regainer",
                "minute": 20,
                "second": 12,
                "period": "FirstHalf",
                "type": "BallRecovery",
                "outcomeType": "Successful",
                "x": 39,
                "y": 45,
            },
        ]
    )

    payload = build_defensive_actions_view(events, team="Alpha")
    summary = payload["transition_summary"]

    assert summary["opportunities"] == 2
    assert summary["counterpress_actions"] == 2
    assert summary["counterpress_regains"] == 1
    assert summary["counterpress_success_pct"] == 50.0
    assert summary["avg_recovery_seconds"] == 8.0
    assert summary["median_recovery_seconds"] == 8.0
    assert summary["within_5_seconds"] == 1
    assert summary["within_15_seconds"] == 2

    interception = next(row for row in payload["actions"] if row["type"] == "Interception")
    later_recovery = next(row for row in payload["actions"] if row["type"] == "BallRecovery")
    assert interception["counterpress_regain"] is True
    assert interception["recovery_seconds"] == 4.0
    assert later_recovery["is_transition_regain"] is True
    assert later_recovery["counterpress_regain"] is False
