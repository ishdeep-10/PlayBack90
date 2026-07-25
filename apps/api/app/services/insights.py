"""Deterministic, data-derived insights for every analysis view.

No external API required: each view gets 3-5 templated bullets computed from
the same builders that power the visuals, so the baseline is identical for
every match.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


def _fmt(value: Any, digits: int = 2) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number == int(number) and digits != 0:
        return str(int(number))
    return f"{number:.{digits}f}"


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%".replace(".0%", "%")
    except (TypeError, ValueError):
        return str(value)


# ── match dynamics ────────────────────────────────────────────────────────────

def _match_dynamics_insights(df: pd.DataFrame) -> list[str]:
    from app.services.matches import build_match_dynamics

    dynamics = build_match_dynamics(df)
    rows = dynamics.get("team_summary_rows") or []
    if len(rows) < 2:
        return []
    a, b = rows[0], rows[1]
    bullets: list[str] = []

    # xG battle vs scoreline
    xg_leader, xg_trailer = (a, b) if float(a.get("xg", 0)) >= float(b.get("xg", 0)) else (b, a)
    diff = float(xg_leader.get("xg", 0)) - float(xg_trailer.get("xg", 0))
    # Scoreline from the xG leader's perspective so the sentence reads naturally.
    scoreline = f"{xg_leader.get('goals', 0)}-{xg_trailer.get('goals', 0)}"
    if diff >= 0.75:
        bullets.append(
            f"{xg_leader['team']} created the better chances — {_fmt(xg_leader['xg'])} xG to "
            f"{_fmt(xg_trailer['xg'])} — against a {scoreline} scoreline."
        )
    else:
        bullets.append(
            f"An even chance-creation battle: {a['team']} {_fmt(a['xg'])} xG vs {b['team']} "
            f"{_fmt(b['xg'])} xG in a {scoreline} game."
        )

    # Finishing over/under performance
    for row in rows:
        delta = float(row.get("goals", 0)) - float(row.get("xg", 0))
        if delta <= -1.0:
            bullets.append(
                f"{row['team']} underperformed their chances by {_fmt(abs(delta), 1)} goals "
                f"({row.get('goals', 0)} scored from {_fmt(row.get('xg', 0))} xG)."
            )
            break
        if delta >= 1.0:
            bullets.append(
                f"{row['team']} were clinical, scoring {row.get('goals', 0)} from just "
                f"{_fmt(row.get('xg', 0))} xG (+{_fmt(delta, 1)} above expected)."
            )
            break

    # Possession vs threat
    poss_leader = a if float(a.get("possession_pct", 0)) >= float(b.get("possession_pct", 0)) else b
    other = b if poss_leader is a else a
    if float(poss_leader.get("possession_pct", 0)) >= 58:
        if float(poss_leader.get("xg", 0)) < float(other.get("xg", 0)):
            bullets.append(
                f"{poss_leader['team']} dominated the ball ({_pct(poss_leader.get('possession_pct'))} possession, "
                f"{poss_leader.get('completed_passes', 0)} completed passes) but {other['team']} still created more "
                f"({_fmt(other.get('xg', 0))} vs {_fmt(poss_leader.get('xg', 0))} xG)."
            )
        else:
            bullets.append(
                f"{poss_leader['team']} controlled the game: {_pct(poss_leader.get('possession_pct'))} possession "
                f"converted into {_fmt(poss_leader.get('xg', 0))} xG and "
                f"{poss_leader.get('final_third_entries', 0)} final-third entries."
            )

    # Pressing intensity (lower PPDA = more aggressive)
    try:
        presser = a if float(a.get("ppda", 99)) <= float(b.get("ppda", 99)) else b
        passive = b if presser is a else a
        if float(passive.get("ppda", 0)) - float(presser.get("ppda", 0)) >= 2:
            bullets.append(
                f"{presser['team']} pressed far more aggressively — PPDA {_fmt(presser.get('ppda'), 1)} vs "
                f"{_fmt(passive.get('ppda'), 1)} (fewer opponent passes allowed per defensive action)."
            )
    except (TypeError, ValueError):
        pass

    # Strongest flank
    flanks = dynamics.get("attack_flanks") or []
    if flanks:
        top = max(flanks, key=lambda f: float(f.get("total_xg", 0) or 0))
        if float(top.get("total_xg", 0)) > 0:
            flank = str(top.get("flank", "")).lower()
            route = "through the middle" if flank in {"center", "centre"} else f"down the {flank}"
            bullets.append(
                f"The most dangerous route was {top['team']} attacking {route}: "
                f"{top.get('num_attacks', 0)} attacks worth {_fmt(top.get('total_xg'))} xG."
            )

    return bullets[:5]


# ── shots & sca ───────────────────────────────────────────────────────────────

def _shots_insights(df: pd.DataFrame, team: str | None) -> list[str]:
    from app.services.matches import build_shots_sca_view

    view = build_shots_sca_view(df)
    totals = view.get("team_totals") or []
    shot_rows = view.get("shot_rows") or []
    bullets: list[str] = []

    for row in totals:
        shots = int(row.get("shots", 0) or 0)
        if not shots:
            continue
        xg_per_shot = float(row.get("xg", 0)) / shots
        quality = "high-quality looks" if xg_per_shot >= 0.12 else "mostly low-value attempts"
        bullets.append(
            f"{row['team']}: {shots} shots, {row.get('shots_on_target', 0)} on target, "
            f"{_fmt(row.get('xg'))} xG ({_fmt(xg_per_shot, 2)} xG/shot — {quality})."
        )

    best_chance_player: str | None = None
    real_shots = [s for s in shot_rows if not bool(s.get("own_goal"))]
    if real_shots:
        best = max(real_shots, key=lambda s: float(s.get("xg", 0) or 0))
        best_chance_player = str(best.get("player") or "")
        outcome = "scored" if str(best.get("type")) == "Goal" else "missed"
        bullets.append(
            f"Biggest chance of the match: {best.get('player', 'Unknown')} ({best.get('team', '')}) "
            f"with a {_fmt(best.get('xg'))} xG opportunity on {int(float(best.get('minute', 0) or 0))}' — {outcome}."
        )

        big = [s for s in real_shots if float(s.get("xg", 0) or 0) > 0.35]
        if big:
            converted = sum(1 for s in big if str(s.get("type")) == "Goal")
            bullets.append(
                f"{len(big)} big chance{'s' if len(big) != 1 else ''} (xG > 0.35) in the match, "
                f"{converted} converted."
            )

    players = [p for p in (view.get("player_summary") or []) if str(p.get("playerName")) != best_chance_player]
    if players:
        top = max(players, key=lambda p: (float(p.get("Total xG", 0) or 0), int(p.get("Total Shots", 0) or 0)))
        top_shots = int(top.get("Total Shots", 0) or 0)
        if float(top.get("Total xG", 0) or 0) > 0:
            bullets.append(
                f"{top.get('playerName')} also carried threat: "
                f"{top_shots} shot{'s' if top_shots != 1 else ''} worth {_fmt(top.get('Total xG'))} xG "
                f"and {_fmt(top.get('Total xGOT'))} xGOT."
            )

    return bullets[:5]


# ── in possession ─────────────────────────────────────────────────────────────

def _in_possession_insights(df: pd.DataFrame, team: str | None) -> list[str]:
    from app.services.views.pass_network import build_channel_analysis, build_combination_play, build_pass_network

    network = build_pass_network(df, team=team)
    selected = network.get("team") or team or ""
    bullets: list[str] = []

    kpis = network.get("third_kpis") or []
    if kpis:
        final = next((k for k in kpis if k.get("third") == "final"), None)
        best_xt = max(kpis, key=lambda k: float(k.get("xt", 0) or 0))
        if final:
            bullets.append(
                f"{selected} completed {_pct(final.get('completion_pct'))} of {final.get('passes', 0)} "
                f"final-third passes, generating {_fmt(final.get('xt'))} xT there."
            )
        if best_xt and best_xt is not final:
            bullets.append(
                f"Most threat was built in the {str(best_xt.get('label', '')).lower()} zone "
                f"({_fmt(best_xt.get('xt'))} xT, {best_xt.get('progressive', 0)} progressive passes)."
            )

    channels = (build_channel_analysis(df, team=team) or {}).get("channels") or []
    if channels:
        top_channel = max(channels, key=lambda c: float(c.get("xt", 0) or 0))
        share = float(top_channel.get("xt_share", 0) or 0) * 100
        bullets.append(
            f"{selected}'s main avenue was the {str(top_channel.get('label', '')).lower()} — "
            f"{_fmt(top_channel.get('xt'))} xT ({_fmt(share, 0)}% of channel threat) and "
            f"{top_channel.get('final_third_entries', 0)} final-third entries."
        )

    pairs = (build_combination_play(df, team=team) or {}).get("pairs") or []
    if pairs:
        top_pair = pairs[0]
        bullets.append(
            f"Most-used combination: {top_pair.get('from')} → {top_pair.get('to')} "
            f"({top_pair.get('count', 0)} passes)."
        )

    central = float(network.get("centralization_index", 0) or 0)
    if central >= 0.15:
        bullets.append(
            f"A high centralization index ({_fmt(central, 2)}) shows the buildup flowed heavily through one hub player."
        )
    elif central > 0:
        bullets.append(
            f"A low centralization index ({_fmt(central, 2)}) points to well-distributed buildup rather than reliance on one player."
        )

    return bullets[:5]


# ── out of possession ─────────────────────────────────────────────────────────

def _out_of_possession_insights(df: pd.DataFrame, team: str | None) -> list[str]:
    from app.services.views.defensive_actions import build_defensive_actions_view

    view = build_defensive_actions_view(df, team=team)
    selected = view.get("team") or team or ""
    bullets: list[str] = []

    totals = view.get("team_totals") or []
    focus = next((t for t in totals if t.get("team") == selected), None)
    if focus:
        bullets.append(
            f"{selected} made {focus.get('total', 0)} defensive actions — {focus.get('tackles', 0)} tackles, "
            f"{focus.get('interceptions', 0)} interceptions, {focus.get('recoveries', 0)} recoveries."
        )
    if len(totals) >= 2:
        other = next((t for t in totals if t.get("team") != selected), None)
        if focus and other:
            busier = focus if int(focus.get("total", 0)) >= int(other.get("total", 0)) else other
            quieter = other if busier is focus else focus
            if int(busier.get("total", 0)) - int(quieter.get("total", 0)) >= 15:
                bullets.append(
                    f"{busier['team']} did far more defending overall ({busier.get('total', 0)} vs "
                    f"{quieter.get('total', 0)} actions) — a sign of sustained pressure against them."
                )

    players = view.get("player_summary") or []
    if players:
        top = players[0]
        bullets.append(
            f"{top.get('player')} was the defensive workhorse: {top.get('total', 0)} actions "
            f"({top.get('tackles', 0)} tackles, {top.get('recoveries', 0)} recoveries)."
        )
        thirds = {
            "defensive third": sum(int(p.get("defensive_third", 0) or 0) for p in players),
            "middle third": sum(int(p.get("middle_third", 0) or 0) for p in players),
            "attacking third": sum(int(p.get("attacking_third", 0) or 0) for p in players),
        }
        total_actions = sum(thirds.values())
        if total_actions:
            zone, count = max(thirds.items(), key=lambda item: item[1])
            bullets.append(
                f"Most of {selected}'s defending happened in the {zone} "
                f"({count} of {total_actions} actions, {_fmt(count / total_actions * 100, 0)}%)."
            )

    return bullets[:5]


# ── duels & transitions ───────────────────────────────────────────────────────

def _duels_insights(df: pd.DataFrame) -> list[str]:
    from app.services.views.duels_transitions import build_duels_transitions_view

    view = build_duels_transitions_view(df, team="both")
    bullets: list[str] = []

    summary = view.get("team_summary") or []
    if len(summary) >= 2:
        a, b = summary[0], summary[1]
        winner = a if float(a.get("duel_win_pct", 0)) >= float(b.get("duel_win_pct", 0)) else b
        loser = b if winner is a else a
        bullets.append(
            f"{winner['team']} edged the duels: {_pct(winner.get('duel_win_pct'))} won "
            f"({winner.get('duels_won', 0)}/{winner.get('duels', 0)}) vs {_pct(loser.get('duel_win_pct'))} "
            f"for {loser['team']}."
        )
        for row in summary:
            transitions = int(row.get("transitions", 0) or 0)
            if transitions:
                to_attack = int(row.get("transitions_to_attack", 0) or 0)
                bullets.append(
                    f"{row['team']} turned {to_attack} of {transitions} transitions into attacks "
                    f"({_fmt(to_attack / transitions * 100, 0)}%)."
                )

    players = view.get("player_summary") or []
    if players:
        top = players[0]
        bullets.append(
            f"Top duelist: {top.get('player')} with {top.get('duels_won', 0)} duels won "
            f"({_pct(top.get('duel_win_pct'))} success)."
        )

    return bullets[:5]


# ── player analysis ───────────────────────────────────────────────────────────

def _player_analysis_insights(df: pd.DataFrame, team: str | None) -> list[str]:
    from app.services.views.player_analysis import build_player_analysis_view

    view = build_player_analysis_view(df, team=team)
    players = view.get("players") or []
    selected = view.get("team") or team or ""
    if not players:
        return []
    bullets: list[str] = []

    most_touches = max(players, key=lambda p: int(p.get("touches", 0) or 0))
    bullets.append(
        f"{most_touches.get('player')} saw the most of the ball for {selected}: "
        f"{most_touches.get('touches', 0)} touches across {most_touches.get('minutes', 0)} minutes."
    )

    most_ip = max(players, key=lambda p: int(p.get("in_possession", 0) or 0))
    if most_ip is not most_touches:
        bullets.append(
            f"{most_ip.get('player')} led in-possession involvement with {most_ip.get('in_possession', 0)} actions."
        )

    most_oop = max(players, key=lambda p: int(p.get("out_of_possession", 0) or 0))
    bullets.append(
        f"Defensively, {most_oop.get('player')} topped the charts with "
        f"{most_oop.get('out_of_possession', 0)} out-of-possession actions."
    )

    most_shots = max(players, key=lambda p: int(p.get("shots", 0) or 0))
    if int(most_shots.get("shots", 0) or 0) > 0:
        bullets.append(
            f"{most_shots.get('player')} was the biggest goal threat with {most_shots.get('shots', 0)} shots."
        )

    most_duels = max(players, key=lambda p: int(p.get("duels", 0) or 0))
    if int(most_duels.get("duels", 0) or 0) > 0 and most_duels is not most_oop:
        bullets.append(
            f"{most_duels.get('player')} was in the thick of the battle with {most_duels.get('duels', 0)} duels."
        )

    return bullets[:5]


# ── entry point ───────────────────────────────────────────────────────────────

def build_deterministic_insights(df: pd.DataFrame, view_id: str, team: str | None) -> list[str]:
    try:
        if view_id == "match-dynamics":
            return _match_dynamics_insights(df)
        if view_id == "shots":
            return _shots_insights(df, team)
        if view_id == "in-possession":
            return _in_possession_insights(df, team)
        if view_id == "out-of-possession":
            return _out_of_possession_insights(df, team)
        if view_id == "duels-transitions":
            return _duels_insights(df)
        if view_id == "player-analysis":
            return _player_analysis_insights(df, team)
    except Exception:
        logger.exception("Deterministic insight generation failed for view %s", view_id)
    return []
