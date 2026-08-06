from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any
import json
import logging
import unicodedata

from app.services import r2
from app.services import season_stats as ss
from app.services.opposition_foundation import _team_mask
from app.services.views.match_summary import build_lineups

logger = logging.getLogger(__name__)


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _name_key(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", _clean(value))
    ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
    alpha_numeric_name = "".join(char if char.isalnum() else " " for char in ascii_name)
    return " ".join(alpha_numeric_name.casefold().split())


def _match_team_name(teams: list[str], wanted: str) -> str | None:
    wanted_key = _name_key(wanted)
    for team in teams:
        if _name_key(team) == wanted_key:
            return team
    for team in teams:
        if wanted_key and (wanted_key in _name_key(team) or _name_key(team) in wanted_key):
            return team
    return None


def _fixture_path_index(league: str, seasons: list[str]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for season in seasons:
        try:
            fixtures = r2.list_all_fixtures(league, season)
        except Exception:
            logger.exception("Failed to list fixtures for lineup context", extra={"league": league, "season": season})
            continue
        for fixture in fixtures:
            match_id = _clean(fixture.get("match_id"))
            if match_id and match_id not in index:
                index[match_id] = fixture
    return index


def _player_row(player: dict[str, Any], *, match_date: str, started: bool) -> dict[str, Any]:
    return {
        "player_id": player.get("player_id"),
        "player": _clean(player.get("player")),
        "position": _clean(player.get("position")),
        "jersey": player.get("jersey"),
        "x": player.get("x"),
        "y": player.get("y"),
        "last_seen": match_date,
        "started": started,
    }


def _json_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [row for row in parsed if isinstance(row, dict)] if isinstance(parsed, list) else []


def _history_match_row(row: dict[str, Any], *, started: bool = True) -> dict[str, Any]:
    match_date = _clean(row.get("date"))
    starters = [_player_row(player, match_date=match_date, started=True) for player in _json_rows(row.get("starters_json"))]
    bench = [_player_row(player, match_date=match_date, started=False) for player in _json_rows(row.get("bench_json"))]
    return {
        "match_id": _clean(row.get("matchId")),
        "date": match_date,
        "opponent": _clean(row.get("opponentName")),
        "home_away": _clean(row.get("homeAway")),
        "formation": _clean(row.get("formation")) or "Unknown",
        "starters": [player for player in starters if _clean(player.get("player"))],
        "bench": [player for player in bench if _clean(player.get("player"))],
        "substitutions": _json_rows(row.get("substitutions_json")),
        "phases": _json_rows(row.get("phase_lineups_json")),
    }


def _load_team_history_rows(league: str, seasons: list[str], opponent_team: str) -> dict[str, dict[str, Any]]:
    rows_by_match: dict[str, dict[str, Any]] = {}
    for season in seasons:
        try:
            history = ss.load_team_history(league, season)
        except Exception:
            logger.exception("Failed to load team history", extra={"league": league, "season": season})
            continue
        if history.empty or "teamName" not in history.columns or "matchId" not in history.columns:
            continue
        team_rows = history[_team_mask(history["teamName"], opponent_team)].copy()
        if team_rows.empty:
            continue
        if "date" in team_rows.columns:
            team_rows = team_rows.sort_values(["date", "matchId"], ascending=False)
        for _, row in team_rows.iterrows():
            payload = row.to_dict()
            match_id = _clean(payload.get("matchId"))
            if match_id and match_id not in rows_by_match:
                rows_by_match[match_id] = payload
    return rows_by_match


def build_lineup_context(
    league: str,
    sample_matches: list[dict[str, Any]],
    *,
    opponent_team: str,
    pool_seasons: list[str],
    team_context: dict[str, Any] | None = None,
    latest_matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    lineup_source_matches = list(latest_matches or []) + [
        match for match in sample_matches if str(match.get("match_id")) not in {str(item.get("match_id")) for item in latest_matches or []}
    ]
    if not lineup_source_matches:
        return {
            "available": False,
            "source": "event-data",
            "warning": "No sample matches were selected, so lineup context cannot be built yet.",
            "team": opponent_team,
            "latest_match": None,
            "matches": [],
            "formation_usage": [],
            "player_usage": [],
            "availability_signals": {},
        }

    history_index = _load_team_history_rows(league, pool_seasons, opponent_team)
    path_index = _fixture_path_index(league, pool_seasons)
    sample_ids = {str(match.get("match_id")) for match in sample_matches}
    latest_ids = {str(match.get("match_id")) for match in latest_matches or []}
    formation_counts: Counter[str] = Counter()
    player_usage: dict[str, dict[str, Any]] = {}
    latest_match: dict[str, Any] | None = None
    recent_matches: list[dict[str, Any]] = []
    warnings: list[str] = []

    for sample in lineup_source_matches:
        match_id = _clean(sample.get("match_id"))
        if match_id in history_index:
            match_row = _history_match_row(history_index[match_id])
        else:
            fixture = path_index.get(match_id)
            file_path = _clean((fixture or {}).get("file_path"))
            if not file_path:
                warnings.append(f"No team history or event file found for sample match {match_id}.")
                continue
            try:
                df = r2.load_match_dataframe(file_path)
            except Exception:
                logger.exception("Failed to load match dataframe for lineup context", extra={"file_path": file_path})
                warnings.append(f"Could not load event data for sample match {match_id}.")
                continue
            if df.empty or "teamName" not in df.columns:
                warnings.append(f"No usable event data found for sample match {match_id}.")
                continue

            teams = [_clean(team) for team in df["teamName"].dropna().unique().tolist()]
            event_team = _match_team_name(teams, opponent_team)
            if not event_team:
                warnings.append(f"Opponent lineup was not found in event data for sample match {match_id}.")
                continue

            lineup_payload = build_lineups(df, teams)
            lineup = (lineup_payload.get("teams") or {}).get(event_team)
            if not lineup:
                warnings.append(f"Formation rows were not available for sample match {match_id}.")
                continue

            formation = _clean(lineup.get("formation")) or "Unknown"
            match_date = _clean(sample.get("date"))
            starters = [_player_row(player, match_date=match_date, started=True) for player in lineup.get("starters", []) if _clean(player.get("player"))]
            bench = [_player_row(player, match_date=match_date, started=False) for player in lineup.get("bench", []) if _clean(player.get("player"))]
            match_row = {
                "match_id": match_id,
                "date": match_date,
                "opponent": _clean(sample.get("opponent")),
                "home_away": _clean(sample.get("home_away")),
                "formation": formation,
                "starters": starters,
                "bench": bench,
            }
        formation = _clean(match_row.get("formation")) or "Unknown"
        starters = match_row.get("starters", [])
        bench = match_row.get("bench", [])
        if match_id in latest_ids and latest_match is None:
            latest_match = match_row
        if match_id in sample_ids:
            formation_counts[formation] += 1
            recent_matches.append(match_row)
            for row in starters + bench:
                key = _name_key(row["player"])
                if not key:
                    continue
                usage = player_usage.setdefault(
                    key,
                    {
                        "player": row["player"],
                        "positions": Counter(),
                        "starts": 0,
                        "bench": 0,
                        "appearances": 0,
                        "last_seen": row["last_seen"],
                    },
                )
                if row["position"]:
                    usage["positions"][row["position"]] += 1
                if row["started"]:
                    usage["starts"] += 1
                else:
                    usage["bench"] += 1
                usage["appearances"] += 1
                if row["last_seen"] > usage["last_seen"]:
                    usage["last_seen"] = row["last_seen"]

    player_rows = []
    for usage in player_usage.values():
        positions = usage.pop("positions")
        usage["primary_position"] = positions.most_common(1)[0][0] if positions else ""
        player_rows.append(usage)
    player_rows.sort(key=lambda row: (int(row["starts"]), int(row["appearances"]), row["last_seen"]), reverse=True)

    current_squad = (
        (((team_context or {}).get("teams") or {}).get("opponent") or {})
        .get("squad_changes", {})
        .get("current_squad", [])
    )
    current_by_key = {_name_key(player.get("name")): player for player in current_squad if isinstance(player, dict) and player.get("name")}
    used_keys = set(player_usage.keys())
    used_not_registered = [row for row in player_rows if _name_key(row["player"]) not in current_by_key][:12]
    registered_not_recent = [player for key, player in current_by_key.items() if key not in used_keys][:12]
    total_matches = len(recent_matches)

    return {
        "available": bool(recent_matches or latest_match),
        "source": "event-data",
        "warning": warnings[0] if warnings and not recent_matches else None,
        "team": opponent_team,
        "sample_match_count": total_matches,
        "latest_match": latest_match or (recent_matches[0] if recent_matches else None),
        "formation_usage": [
            {"formation": formation, "count": count, "pct": round(100 * count / max(1, total_matches), 1)}
            for formation, count in formation_counts.most_common()
        ],
        "matches": recent_matches,
        "player_usage": player_rows[:24],
        "availability_signals": {
            "recently_used_not_current_squad": used_not_registered,
            "current_squad_not_recently_used": registered_not_recent,
            "note": "Upcoming matchday availability is unknown until lineups are released. These signals compare recent event-data lineups and benches with the current FootballData season squad.",
        },
        "warnings": warnings[:5],
    }
