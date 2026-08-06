from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from app.services import season_stats as ss
from app.services import r2


STYLE_FEATURES = [
    "possession_pct",
    "pass_accuracy",
    "ppda",
    "field_tilt_pct",
    "box_entries",
    "long_balls",
    "through_balls",
    "crosses",
]

CHANCE_FEATURES = [
    "shots",
    "shots_on_target",
    "xG",
    "xG_per_shot",
    "big_chances",
]

VULNERABILITY_FEATURES = [
    "xG_against",
    "shots_against",
    "big_chances_against",
    "goals_against",
]

PROFILE_FEATURES = STYLE_FEATURES + CHANCE_FEATURES + VULNERABILITY_FEATURES
LOW_SAMPLE_WARNING = (
    "Comparable-match sample is below the preferred threshold, so use this as directional scouting context."
)


def previous_season_key(season: str) -> str | None:
    parts = str(season).replace("/", "_").split("_")
    if len(parts) != 2:
        return None
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return f"{start - 1}_{end - 1}"


def _clean_team(value: Any) -> str:
    return str(value or "").strip()


def _team_mask(series: pd.Series, team: str) -> pd.Series:
    wanted = _clean_team(team).casefold()
    return series.astype(str).str.strip().str.casefold().eq(wanted)


def _numeric_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    available = [column for column in columns if column in df.columns]
    numeric = pd.DataFrame(index=df.index)
    for column in available:
        numeric[column] = pd.to_numeric(df[column], errors="coerce")
    return numeric


def _prepare_team_match_stats(df: pd.DataFrame, season: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    prepared = df.copy()
    prepared["sampleSeason"] = season
    if "date" in prepared.columns:
        prepared["date"] = prepared["date"].astype(str).str[:10]
    else:
        prepared["date"] = ""
    for column in {"teamName", "opponentName", "homeAway", "matchId"}:
        if column not in prepared.columns:
            prepared[column] = ""
        prepared[column] = prepared[column].astype(str).fillna("").str.strip()
    for column in PROFILE_FEATURES + ["goals", "goals_against"]:
        if column in prepared.columns:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)
    return prepared


@lru_cache(maxsize=48)
def _load_prepared_team_stats(league: str, season: str) -> pd.DataFrame:
    return _prepare_team_match_stats(ss.load_team_season_stats(league, season), season)


def load_analysis_pool(league: str, season: str, opponent_team: str) -> tuple[pd.DataFrame, str, list[str]]:
    current = _load_prepared_team_stats(league, season)
    previous = previous_season_key(season)
    previous_df = _load_prepared_team_stats(league, previous) if previous else pd.DataFrame()

    current_opponent_rows = (
        current[_team_mask(current["teamName"], opponent_team)] if not current.empty and "teamName" in current.columns else pd.DataFrame()
    )
    if len(current_opponent_rows) >= 4:
        frames = [frame for frame in (current, previous_df) if not frame.empty]
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), "current_plus_previous", [season, previous] if previous else [season]

    if not previous_df.empty:
        return previous_df, "previous_season", [previous] if previous else []

    return current, "current_season", [season]


def build_team_match_index(league: str, season: str, team: str) -> dict[str, Any]:
    fixtures = r2.list_all_fixtures(league, season)
    rows = [
        {
            "match_id": str(fixture.get("match_id", "")),
            "date": str(fixture.get("start_date_label", "")),
            "home_team": str(fixture.get("home_team", "")),
            "away_team": str(fixture.get("away_team", "")),
            "file_path": str(fixture.get("file_path", "")),
            "score": str(fixture.get("score", "")),
        }
        for fixture in fixtures
        if _clean_team(fixture.get("home_team")).casefold() == _clean_team(team).casefold()
        or _clean_team(fixture.get("away_team")).casefold() == _clean_team(team).casefold()
    ]
    return {"team": team, "matches": rows, "match_count": len(rows)}


def build_team_style_profiles(team_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if team_df.empty or "teamName" not in team_df.columns:
        return pd.DataFrame(), []

    numeric = _numeric_frame(team_df, PROFILE_FEATURES)
    available = [column for column in PROFILE_FEATURES if column in numeric.columns and numeric[column].notna().any()]
    if not available:
        return pd.DataFrame(), []

    profile = team_df[["teamName"]].join(numeric[available])
    profile = profile.groupby("teamName", sort=False)[available].mean().reset_index()
    profile["matches"] = team_df.groupby("teamName", sort=False)["matchId"].count().reindex(profile["teamName"]).fillna(0).astype(int).to_numpy()
    return profile, available


def _distance_table(profile_df: pd.DataFrame, reference_team: str, features: list[str]) -> pd.DataFrame:
    if profile_df.empty or not features:
        return pd.DataFrame()

    ref_rows = profile_df[_team_mask(profile_df["teamName"], reference_team)]
    if ref_rows.empty:
        return pd.DataFrame()

    values = profile_df[features].apply(pd.to_numeric, errors="coerce")
    means = values.mean(axis=0)
    stds = values.std(axis=0).replace(0, 1).fillna(1)
    z_values = (values.fillna(means) - means) / stds
    ref_vector = z_values.loc[ref_rows.index[0]]
    distances = ((z_values - ref_vector) ** 2).sum(axis=1) ** 0.5

    table = profile_df[["teamName", "matches"]].copy()
    table["distance"] = distances.round(4)
    table["similarity"] = (100 / (1 + distances)).round(1)
    return table.sort_values(["distance", "teamName"]).reset_index(drop=True)


def similar_teams(
    team_df: pd.DataFrame,
    reference_team: str,
    limit: int = 8,
    exclude_teams: list[str] | None = None,
) -> list[dict[str, Any]]:
    profile_df, features = build_team_style_profiles(team_df)
    distances = _distance_table(profile_df, reference_team, features)
    if distances.empty:
        return []
    excluded = {_clean_team(reference_team).casefold()}
    excluded.update(_clean_team(team).casefold() for team in (exclude_teams or []))
    peers = distances[~distances["teamName"].astype(str).str.strip().str.casefold().isin(excluded)].head(limit)
    return [
        {
            "team": str(row["teamName"]),
            "similarity": float(row["similarity"]),
            "distance": float(row["distance"]),
            "matches": int(row["matches"]),
        }
        for _, row in peers.iterrows()
    ]


def _sample_match_row(row: pd.Series, sample_reason: str) -> dict[str, Any]:
    goals = int(float(row.get("goals", 0) or 0))
    goals_against = int(float(row.get("goals_against", 0) or 0))
    result = "W" if goals > goals_against else ("D" if goals == goals_against else "L")
    return {
        "match_id": str(row.get("matchId", "")),
        "date": str(row.get("date", "")),
        "season": str(row.get("sampleSeason", "")),
        "team": str(row.get("teamName", "")),
        "opponent": str(row.get("opponentName", "")),
        "home_away": str(row.get("homeAway", "")),
        "result": result,
        "score": f"{goals}-{goals_against}",
        "xg": round(float(row.get("xG", 0) or 0), 2),
        "xga": round(float(row.get("xG_against", 0) or 0), 2),
        "shots": int(float(row.get("shots", 0) or 0)),
        "shots_against": int(float(row.get("shots_against", 0) or 0)),
        "possession_pct": round(float(row.get("possession_pct", 0) or 0), 2),
        "ppda": round(float(row.get("ppda", 0) or 0), 2),
        "sample_reason": sample_reason,
    }


def select_similar_opponent_matches(
    team_df: pd.DataFrame,
    opponent_team: str,
    reference_team: str,
    sample_size: int = 5,
) -> dict[str, Any]:
    if team_df.empty or "teamName" not in team_df.columns:
        return {"matches": [], "similar_teams": [], "sample_size": sample_size, "warnings": ["Season stats are not available."]}

    profile_df, features = build_team_style_profiles(team_df)
    distances = _distance_table(profile_df, reference_team, features)
    similar = similar_teams(team_df, reference_team, limit=8, exclude_teams=[opponent_team])
    if distances.empty:
        comparable_names = {_clean_team(reference_team).casefold()}
        warnings = ["Reference-team profile is not available; using direct opponent history first."]
    else:
        excluded = {_clean_team(opponent_team).casefold()}
        comparable_names = {_clean_team(reference_team).casefold()}
        for _, row in distances.iterrows():
            team_name = _clean_team(row["teamName"])
            if team_name.casefold() in excluded or team_name.casefold() == _clean_team(reference_team).casefold():
                continue
            comparable_names.add(team_name.casefold())
            if len(comparable_names) >= 9:
                break
        warnings = []

    opponent_rows = team_df[_team_mask(team_df["teamName"], opponent_team)].copy()
    if opponent_rows.empty:
        return {
            "matches": [],
            "similar_teams": similar,
            "sample_size": sample_size,
            "warnings": [f"No completed team-match rows found for {opponent_team}."],
        }

    opponent_rows = opponent_rows.sort_values(["date", "matchId"], ascending=False)
    comparable_rows = opponent_rows[opponent_rows["opponentName"].astype(str).str.strip().str.casefold().isin(comparable_names)]
    picked = comparable_rows.head(sample_size).copy()
    matches = [_sample_match_row(row, "similar_opponent") for _, row in picked.iterrows()]

    if len(matches) < sample_size:
        picked_ids = {item["match_id"] for item in matches}
        fallback = opponent_rows[~opponent_rows["matchId"].astype(str).isin(picked_ids)].head(sample_size - len(matches))
        matches.extend(_sample_match_row(row, "recent_fallback") for _, row in fallback.iterrows())

    if len([item for item in matches if item["sample_reason"] == "similar_opponent"]) < sample_size:
        warnings.append(LOW_SAMPLE_WARNING)

    return {
        "matches": matches,
        "similar_teams": similar,
        "sample_size": sample_size,
        "features_used": features,
        "warnings": warnings,
    }


def build_opposition_foundation(
    league: str,
    season: str,
    opponent_team: str,
    reference_team: str,
    sample_size: int = 5,
) -> dict[str, Any]:
    pool, pool_strategy, pool_seasons = load_analysis_pool(league, season, opponent_team)
    sample = select_similar_opponent_matches(pool, opponent_team, reference_team, sample_size=sample_size)

    return {
        "league": league,
        "season": season,
        "reference_team": reference_team,
        "opponent_team": opponent_team,
        "sample_size": sample_size,
        "sample_strategy": "similar_opponent_profile",
        "pool_strategy": pool_strategy,
        "pool_seasons": [season_value for season_value in pool_seasons if season_value],
        "features_used": sample.get("features_used", []),
        "similar_teams": sample.get("similar_teams", []),
        "sample_matches": sample.get("matches", []),
        "warnings": sample.get("warnings", []),
        "team_match_index": build_team_match_index(league, season, opponent_team),
    }
