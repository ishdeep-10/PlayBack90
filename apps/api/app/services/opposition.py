from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from app.services.r2 import list_fixtures

matplotlib.use("Agg")


# Transitional season-stat baseline for the Phase 0 opposition page.
# The dossier endpoint will replace this with fixture-aware similar-opponent sampling.
_METRICS: list[tuple[str, str, bool]] = [
    ("xG",               "xG / Game",           True),
    ("shot_accuracy",    "Shot Accuracy %",      True),
    ("big_chances",      "Big Chances",          True),
    ("xG_against",       "xGA / Game",           False),
    ("ppda",             "PPDA (pressing)",      False),   # lower = more pressing = good
    ("pass_accuracy",    "Pass Accuracy %",      True),
    ("crosses",          "Crosses",              True),
    ("through_balls",    "Through Balls",        True),
    ("possession_pct",   "Possession %",         True),
    ("big_chances_against", "Big Chances Against", False),
    ("clearances",       "Clearances",           True),
    ("xG_per_shot",      "xG / Shot",            True),
]


def _percentile(series: pd.Series, value: float, higher_is_better: bool) -> float:
    """Return 0-100 percentile rank. For metrics where lower=better, invert."""
    if series.empty:
        return 50.0
    pct = float((series < value).mean() * 100)
    return pct if higher_is_better else 100.0 - pct


def build_opposition_report(
    team_df: pd.DataFrame,
    player_df: pd.DataFrame,
    target_team: str,
    league: str,
    season: str,
) -> dict[str, Any]:
    if team_df.empty or "teamName" not in team_df.columns:
        return {"team": target_team, "strengths": [], "weaknesses": [], "top_players": [], "recent_results": [], "h2h": []}

    # Per-match averages for target team
    t_df = team_df[team_df["teamName"] == target_team].copy()
    if t_df.empty:
        return {"team": target_team, "strengths": [], "weaknesses": [], "top_players": [], "recent_results": [], "h2h": []}

    strengths = []
    weaknesses = []

    for col, label, higher_is_better in _METRICS:
        if col not in team_df.columns:
            continue
        league_series = pd.to_numeric(team_df[col], errors="coerce").dropna()
        team_mean = float(pd.to_numeric(t_df[col], errors="coerce").mean())
        pct = _percentile(league_series, team_mean, higher_is_better)
        entry = {"metric": label, "percentile": round(pct, 1), "value": round(team_mean, 2)}
        if pct >= 70:
            strengths.append(entry)
        elif pct <= 30:
            weaknesses.append(entry)

    # Top players
    top_players: list[dict[str, Any]] = []
    if not player_df.empty and "teamName" in player_df.columns:
        p_df = player_df[player_df["teamName"] == target_team].copy()
        if not p_df.empty:
            for col in ("goals", "xG", "xA"):
                p_df[col] = pd.to_numeric(p_df.get(col, 0), errors="coerce").fillna(0)
            agg = (
                p_df.groupby("playerName", sort=False)
                .agg(goals=("goals", "sum"), xg=("xG", "sum"), xA=("xA", "sum"), mins=("mins_played", "sum"))
                .reset_index()
                .sort_values("xg", ascending=False)
                .head(5)
            )
            for _, row in agg.iterrows():
                top_players.append({
                    "player": str(row["playerName"]),
                    "goals": int(row["goals"]),
                    "xg": round(float(row["xg"]), 2),
                    "xa": round(float(row["xA"]), 2),
                    "mins": int(row["mins"]),
                })

    # Recent completed results for this team. This scans fixture filenames only,
    # so it is fast but intentionally does not claim true head-to-head context.
    recent_results: list[dict[str, Any]] = []
    try:
        all_fixtures = list_fixtures(league, season, limit=200, offset=0)
        for fixture in all_fixtures:
            if fixture.get("home_team") == target_team or fixture.get("away_team") == target_team:
                score_str = str(fixture.get("score", ""))
                # score is formatted like "2-1" after parsing
                parts = score_str.replace("–", "-").split("-")
                if len(parts) == 2:
                    try:
                        home_g, away_g = int(parts[0]), int(parts[1])
                        if fixture.get("home_team") == target_team:
                            gf, ga = home_g, away_g
                            opponent = str(fixture.get("away_team", ""))
                        else:
                            gf, ga = away_g, home_g
                            opponent = str(fixture.get("home_team", ""))
                        result = "W" if gf > ga else ("D" if gf == ga else "L")
                        recent_results.append({
                            "date": str(fixture.get("start_date_label", "")),
                            "opponent": opponent,
                            "result": result,
                            "goals_for": gf,
                            "goals_against": ga,
                            "score": f"{gf}–{ga}",
                        })
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass

    return {
        "team": target_team,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "top_players": top_players,
        "recent_results": recent_results[:10],
        "h2h": recent_results[:10],
    }


def build_opposition_asset(
    team_df: pd.DataFrame,
    player_df: pd.DataFrame,
    target_team: str,
    asset_id: str,
) -> bytes:
    background = "#07131f"
    text_color = "white"
    accent = "#67e8f9"
    danger = "#f87171"

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    ax.tick_params(colors=text_color)
    ax.spines[:].set_visible(False)
    ax.xaxis.label.set_color(text_color)
    ax.yaxis.label.set_color(text_color)

    if asset_id == "radar" and not team_df.empty:
        t_df = team_df[team_df["teamName"] == target_team].copy()
        metrics = [m for m in _METRICS if m[0] in team_df.columns][:8]
        labels = [m[1] for m in metrics]
        league_means = [float(pd.to_numeric(team_df[m[0]], errors="coerce").mean()) for m in metrics]
        team_means = [float(pd.to_numeric(t_df[m[0]], errors="coerce").mean()) if not t_df.empty else 0 for m in metrics]

        x = np.arange(len(labels))
        width = 0.35
        ax.bar(x - width / 2, team_means, width, color=accent, alpha=0.85, label=target_team)
        ax.bar(x + width / 2, league_means, width, color="white", alpha=0.3, label="League avg")
        ax.set_xticks(x)
        ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=9, color=text_color)
        ax.set_title(f"{target_team} vs League Average", color=text_color, pad=14)
        legend = ax.legend(facecolor=background, labelcolor=text_color, framealpha=0.6)
        for text in legend.get_texts():
            text.set_color(text_color)

    elif asset_id == "shot-map" and not team_df.empty:
        t_df = team_df[team_df["teamName"] == target_team].copy()
        # Simple bar chart of shot stats as a placeholder for pitch-based shot map
        stats = {
            "Shots": float(pd.to_numeric(t_df.get("shots", pd.Series([0])), errors="coerce").mean()),
            "On Target": float(pd.to_numeric(t_df.get("shots_on_target", pd.Series([0])), errors="coerce").mean()),
            "xG / Game": float(pd.to_numeric(t_df.get("xG", pd.Series([0])), errors="coerce").mean()),
            "Big Chances": float(pd.to_numeric(t_df.get("big_chances", pd.Series([0])), errors="coerce").mean()),
        }
        ax.barh(list(stats.keys()), list(stats.values()), color=accent, alpha=0.85)
        ax.set_title(f"{target_team} — Attack Profile (per match avg)", color=text_color, pad=14)

    else:
        ax.text(0.5, 0.5, f"{asset_id} not available", ha="center", va="center",
                color=text_color, fontsize=14, transform=ax.transAxes)

    buf = BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
