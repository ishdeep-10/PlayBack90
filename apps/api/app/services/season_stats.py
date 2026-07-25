from __future__ import annotations

from io import BytesIO
from functools import lru_cache
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

from app.services.r2 import make_fs, get_storage_options

matplotlib.use("Agg")


# ── R2 loaders ────────────────────────────────────────────────────────────────

def _r2_parquet_path(bucket: str, league: str, season: str, filename: str) -> str:
    season_key = season.replace("/", "_")
    return f"{bucket}/season_stats/{league}/{season_key}/{filename}"


def load_team_season_stats(league: str, season: str) -> pd.DataFrame:
    from app.config import settings
    fs = make_fs()
    path = _r2_parquet_path(settings.r2_bucket, league, season, "team_match_stats.parquet")
    if not fs.exists(path):
        return pd.DataFrame()
    return pd.read_parquet(f"s3://{path}", storage_options=get_storage_options())


def load_player_season_stats(league: str, season: str) -> pd.DataFrame:
    from app.config import settings
    fs = make_fs()
    path = _r2_parquet_path(settings.r2_bucket, league, season, "player_match_stats.parquet")
    if not fs.exists(path):
        return pd.DataFrame()
    return pd.read_parquet(f"s3://{path}", storage_options=get_storage_options())


# ── League table ──────────────────────────────────────────────────────────────

def build_league_table(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty or "teamName" not in df.columns:
        return []

    df = df.copy()
    df["goals"] = pd.to_numeric(df["goals"], errors="coerce").fillna(0)
    df["goals_against"] = pd.to_numeric(df["goals_against"], errors="coerce").fillna(0)
    df["xG"] = pd.to_numeric(df["xG"], errors="coerce").fillna(0)
    df["xG_against"] = pd.to_numeric(df["xG_against"], errors="coerce").fillna(0)
    df["W"] = (df["goals"] > df["goals_against"]).astype(int)
    df["D"] = (df["goals"] == df["goals_against"]).astype(int)
    df["L"] = (df["goals"] < df["goals_against"]).astype(int)
    df["pts"] = df["W"] * 3 + df["D"]

    table = (
        df.groupby("teamName", sort=False)
        .agg(
            played=("matchId", "count"),
            won=("W", "sum"),
            drawn=("D", "sum"),
            lost=("L", "sum"),
            gf=("goals", "sum"),
            ga=("goals_against", "sum"),
            pts=("pts", "sum"),
            xg=("xG", "sum"),
            xga=("xG_against", "sum"),
        )
        .reset_index()
    )

    table["gd"] = table["gf"] - table["ga"]
    table["xgd"] = (table["xg"] - table["xga"]).round(2)
    table["xg"] = table["xg"].round(2)
    table["xga"] = table["xga"].round(2)
    table = table.sort_values(["pts", "gd", "gf"], ascending=False).reset_index(drop=True)
    table.index += 1
    table = table.reset_index().rename(columns={"index": "rank"})
    table = table.rename(columns={"teamName": "team"})
    return table.to_dict(orient="records")


# ── Team form ─────────────────────────────────────────────────────────────────

def build_team_form(df: pd.DataFrame, team: str, window: int = 5) -> dict[str, Any]:
    if df.empty or "teamName" not in df.columns:
        return {"team": team, "window": window, "matches": []}

    team_df = df[df["teamName"] == team].copy()
    if team_df.empty:
        return {"team": team, "window": window, "matches": []}

    for col in ("goals", "goals_against", "xG", "xG_against"):
        team_df[col] = pd.to_numeric(team_df[col], errors="coerce").fillna(0)

    team_df = team_df.sort_values("date", ascending=False)
    if window > 0:
        team_df = team_df.head(window)
    team_df = team_df.sort_values("date")

    matches = []
    for _, row in team_df.iterrows():
        gf = int(row["goals"])
        ga = int(row["goals_against"])
        result = "W" if gf > ga else ("D" if gf == ga else "L")
        matches.append({
            "date": str(row.get("date", "")),
            "opponent": str(row.get("opponentName", "")),
            "result": result,
            "goals_for": gf,
            "goals_against": ga,
            "xg_for": round(float(row["xG"]), 2),
            "xg_against": round(float(row["xG_against"]), 2),
            "score": f"{gf}–{ga}",
        })

    return {"team": team, "window": window, "matches": matches}


# ── Player leaderboard ────────────────────────────────────────────────────────

SORTABLE_METRICS = {
    "goals", "xG", "shots", "shots_on_target", "big_chances", "xG_per_shot",
    "key_passes", "xA", "crosses", "through_balls", "prog_passes", "xT",
    "tackles", "interceptions", "clearances", "fouls_committed",
    "aerial_duels_total", "aerial_duels_won", "dribbles_attempted", "dribbles_won",
    "yellow_cards", "red_cards",
}


def build_player_leaderboard(
    df: pd.DataFrame,
    sort_by: str = "xG",
    min_mins: int = 0,
) -> list[dict[str, Any]]:
    if df.empty or "playerName" not in df.columns:
        return []

    sort_col = sort_by if sort_by in SORTABLE_METRICS else "xG"

    agg_cols = {col: "sum" for col in SORTABLE_METRICS if col in df.columns}
    agg_cols["mins_played"] = "sum"
    agg_cols["teamName"] = "first"
    agg_cols["matchId"] = "count"

    agg = df.groupby("playerName", sort=False).agg(agg_cols).reset_index()
    agg = agg.rename(columns={"matchId": "matches_played"})

    if min_mins > 0 and "mins_played" in agg.columns:
        agg = agg[agg["mins_played"] >= min_mins]

    # Per-90 versions of counting stats
    if "mins_played" in agg.columns:
        per90_cols = ["goals", "xG", "shots", "key_passes", "xA", "tackles", "xT"]
        for col in per90_cols:
            if col in agg.columns:
                agg[f"{col}_p90"] = (agg[col] / agg["mins_played"].clip(lower=1) * 90).round(2)

    if sort_col in agg.columns:
        agg = agg.sort_values(sort_col, ascending=False)

    for col in agg.select_dtypes(include="number").columns:
        agg[col] = agg[col].round(2)

    agg = agg.rename(columns={"playerName": "player", "teamName": "team"})
    return agg.head(50).to_dict(orient="records")


# ── Season matplotlib assets ──────────────────────────────────────────────────

def build_season_asset(
    team_df: pd.DataFrame,
    player_df: pd.DataFrame,
    asset_id: str,
    team: str | None = None,
    **kwargs: Any,
) -> bytes:
    background = "#07131f"
    text_color = "white"
    accent = "#67e8f9"

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor(background)
    ax.set_facecolor(background)
    ax.tick_params(colors=text_color)
    ax.spines[:].set_visible(False)
    ax.title.set_color(text_color)
    ax.xaxis.label.set_color(text_color)
    ax.yaxis.label.set_color(text_color)

    if asset_id == "xg-scatter" and not team_df.empty:
        table = pd.DataFrame(build_league_table(team_df))
        if not table.empty:
            ax.scatter(table["xg"], table["xga"], color=accent, s=80, zorder=3)
            for _, row in table.iterrows():
                ax.annotate(
                    str(row["team"])[:12],
                    (float(row["xg"]), float(row["xga"])),
                    fontsize=8,
                    color=text_color,
                    textcoords="offset points",
                    xytext=(6, 4),
                )
            max_val = max(table["xg"].max(), table["xga"].max()) * 1.05
            ax.plot([0, max_val], [0, max_val], "--", color="white", alpha=0.3, linewidth=1)
            ax.set_xlabel("xG For", color=text_color)
            ax.set_ylabel("xG Against", color=text_color)
            ax.set_title("xG For vs xG Against", color=text_color, pad=14)

    elif asset_id == "team-form-chart" and team and not team_df.empty:
        form = build_team_form(team_df, team, window=10)
        matches = form["matches"]
        if matches:
            labels = [f"{m['opponent'][:8]}\n{m['score']}" for m in matches]
            xg_for = [m["xg_for"] for m in matches]
            xg_against = [m["xg_against"] for m in matches]
            x = range(len(labels))
            ax.bar([i - 0.2 for i in x], xg_for, width=0.4, color=accent, alpha=0.85, label="xG For")
            ax.bar([i + 0.2 for i in x], xg_against, width=0.4, color="#f87171", alpha=0.85, label="xG Against")
            ax.set_xticks(list(x))
            ax.set_xticklabels(labels, fontsize=8, color=text_color)
            ax.set_ylabel("xG", color=text_color)
            ax.set_title(f"{team} — Form xG (last {len(matches)} matches)", color=text_color, pad=14)
            legend = ax.legend(facecolor=background, labelcolor=text_color, framealpha=0.6)
            for text in legend.get_texts():
                text.set_color(text_color)

    else:
        ax.text(0.5, 0.5, f"{asset_id} — no data available", ha="center", va="center",
                color=text_color, fontsize=14, transform=ax.transAxes)

    buf = BytesIO()
    plt.tight_layout()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()
