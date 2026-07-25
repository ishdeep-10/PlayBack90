"""AI analyst insight generation backed by the Claude API."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

import pandas as pd

from app.config import settings

logger = logging.getLogger(__name__)

_INSIGHT_CACHE: dict[tuple[str, ...], str] = {}
_INSIGHT_CACHE_MAX_ITEMS = 128
_PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are a professional football (soccer) performance analyst writing short post-match notes.
You are given a structured JSON digest of ONE view of a single match. Rules:
- Cite ONLY numbers and players that appear in the digest. Never invent players, stats, or events.
- Write 3 to 5 punchy bullet points (each starting with "- "), tactical and specific, like a scout's debrief.
- Lead each bullet with the key fact; keep each under 30 words.
- Mention concrete numbers (xG, counts, percentages) whenever available.
- No introduction, no conclusion, no headers — bullets only."""


def _prune(value: Any, list_limit: int = 12, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        drop_keys = {"deliveries", "heatmap", "actions", "shot_rows", "edges", "nodes"}
        return {
            key: _prune(item, list_limit, depth + 1)
            for key, item in value.items()
            if key not in drop_keys
        }
    if isinstance(value, list):
        return [_prune(item, list_limit, depth + 1) for item in value[:list_limit]]
    if isinstance(value, float):
        return round(value, 3)
    return value


def build_view_digest(df: pd.DataFrame, view_id: str, team: str | None, file_path: str | None) -> dict[str, Any]:
    """Compact, numbers-only digest of the current view for the model."""
    from app.services.matches import build_match_dynamics, build_team_summaries
    from app.services.views.duels_transitions import build_duels_transitions_view
    from app.services.views.defensive_actions import build_defensive_actions_view
    from app.services.views.pass_network import build_channel_analysis, build_combination_play, build_pass_network
    from app.services.views.set_pieces import build_set_pieces_view
    from app.services.views.shots import build_shots_sca_view

    digest: dict[str, Any] = {
        "view": view_id,
        "focus_team": team,
        "teams": [summary.model_dump() for summary in build_team_summaries(df)],
    }

    if view_id == "match-dynamics":
        dynamics = build_match_dynamics(df)
        momentum = dynamics.get("xt_momentum") or []
        digest["team_summary"] = dynamics.get("team_summary_rows")
        digest["goals"] = [row for row in (dynamics.get("xg_markers") or []) if str(row.get("event_type")) == "goal"]
        digest["xt_momentum_sampled"] = momentum[:: max(1, len(momentum) // 18)]
        digest["attack_flanks"] = dynamics.get("attack_flanks")
    elif view_id == "shots":
        shots = build_shots_sca_view(df)
        digest["team_totals"] = shots.get("team_totals")
        digest["top_players"] = (shots.get("player_summary") or [])[:8]
        shot_rows = shots.get("shot_rows") or []
        if team:
            shot_rows = [row for row in shot_rows if str(row.get("team")) == team] or shot_rows
        digest["shots"] = [
            {key: row.get(key) for key in ("minute", "player", "xg", "result", "situation")}
            for row in shot_rows[:20]
        ]
    elif view_id == "in-possession":
        network = build_pass_network(df, team=team)
        digest["third_kpis"] = network.get("third_kpis")
        digest["centralization_index"] = network.get("centralization_index")
        digest["top_pairs"] = (build_combination_play(df, team=team).get("pairs") or [])[:6]
        digest["channels"] = build_channel_analysis(df, team=team).get("channels")
    elif view_id == "out-of-possession":
        defensive = build_defensive_actions_view(df, team=team)
        digest["defensive"] = _prune({key: value for key, value in defensive.items() if key not in {"zones"}})
        digest["top_zones"] = (defensive.get("zones") or [])[:8]
    elif view_id == "duels-transitions":
        duels = build_duels_transitions_view(df)
        digest["duels"] = _prune(duels, list_limit=8)
    elif view_id == "player-analysis":
        from app.services.views.player_analysis import build_player_analysis_view

        analysis = build_player_analysis_view(df, team=team)
        digest["players"] = (analysis.get("players") or [])[:14]

    if view_id in {"match-dynamics", "in-possession"}:
        digest["set_pieces"] = {
            key: {metric: value for metric, value in stats.items() if metric != "deliveries"}
            for key, stats in (build_set_pieces_view(df, team=team).get("types") or {}).items()
        }

    return _prune(digest, list_limit=20)


def insights_available() -> bool:
    return bool(settings.anthropic_api_key)


def stream_insights(digest: dict[str, Any], cache_key: tuple[str, ...]) -> Iterator[str]:
    cached = _INSIGHT_CACHE.get(cache_key)
    if cached:
        yield cached
        return

    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    collected: list[str] = []
    with client.messages.stream(
        model=settings.ai_model,
        max_tokens=600,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"Match view digest:\n```json\n{json.dumps(digest, default=str)}\n```\nWrite the analyst bullets.",
        }],
    ) as stream:
        for text in stream.text_stream:
            collected.append(text)
            yield text

    final = "".join(collected)
    if final:
        if len(_INSIGHT_CACHE) >= _INSIGHT_CACHE_MAX_ITEMS:
            _INSIGHT_CACHE.pop(next(iter(_INSIGHT_CACHE)), None)
        _INSIGHT_CACHE[cache_key] = final


def make_cache_key(file_path: str | None, view_id: str, team: str | None) -> tuple[str, ...]:
    return (_PROMPT_VERSION, str(file_path or ""), view_id, str(team or ""))
