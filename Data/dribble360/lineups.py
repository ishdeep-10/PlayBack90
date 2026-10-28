"""Rebuild the lineup / formation / substitution qualifiers that BigQuery Pro does not ship.

The Pro `match_events` table has TEAM_SET_UP, FORMATION_CHANGE and PLAYER_ON/OFF events but no qualifiers, so
`build_lineups` (apps/api/app/services/views/match_summary.py) finds nothing. This fills the qualifiers in on the
existing rows of the processed frame:

* starters  = players with minutes who were not subbed on (`player_matches.mins_played`)
* formation = best fit of the starters' average touch positions to the known Opta slot layouts
* subs      = the Off/On row pair keeps its event ids; the sub inherits the replaced player's slot
* FORMATION_CHANGE rows are left empty (re-fitting the shape on a short window is too noisy)

Not recoverable from Pro: shirt numbers, unused substitutes, the feed's own formation id (this is an estimate).
"""
from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "apps" / "api"))

from app.services.views.match_summary import FORMATION_SLOT_POSITIONS, _POS  # noqa: E402

CANDIDATES = {fid: slots for fid, slots in FORMATION_SLOT_POSITIONS.items() if len(slots) == 11}
# Share of true starting formations among 1,650 team-matches (2025/26 WhoScored lineups); rare shapes get a floor.
# Touch locations barely identify a shape (best fit ~32% exact, 77% of players on the right line), so the prior matters.
PRIOR = {8: .33, 17: .15, 4: .14, 2: .08, 12: .06, 7: .05, 10: .04, 13: .04, 11: .03, 5: .01, 18: .015, 6: .005, 9: .005, 15: .005, 3: .005}
PRIOR_WEIGHT = 0.3
Y_WEIGHT = 1.0
HISTORY_WEIGHT = 1.0   # penalty when a player is put on a line he has rarely started on (tuned: role lines 77% -> 92%)
_HISTORY: dict | None = None


def fold(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c)).lower().strip()


def history() -> dict:
    global _HISTORY
    if _HISTORY is None:
        path = HERE / "position_history.json"
        _HISTORY = json.loads(path.read_text()) if path.exists() else {}
    return _HISTORY
GROUP_CODE = {"GK": 1, "RB": 2, "LB": 2, "CB": 2, "RCB": 2, "LCB": 2, "RWB": 2, "LWB": 2}
GROUP_CODE.update({p: 3 for p in ("RDM", "CDM", "LDM", "RCM", "CM", "LCM", "RM", "LM", "RAM", "CAM", "LAM")})
GROUP_CODE.update({p: 4 for p in ("RW", "LW", "RF", "LF", "ST")})
MIN_TOUCHES = 4


def numeric_player_id(d360_id: str) -> int:
    """Stable 32-bit integer id; the app's contract (and build_lineups) expects numeric player ids."""
    return int(hashlib.md5(str(d360_id).encode()).hexdigest()[:8], 16)


def _norm(a: np.ndarray) -> np.ndarray:
    span = a.max(axis=0) - a.min(axis=0)
    span[span == 0] = 1.0
    return (a - a.min(axis=0)) / span


def estimate_formation(avg_xy: dict, line_prob: dict | None = None) -> tuple[int, dict]:
    """avg_xy: {player: (x, y)} for the 10 outfielders -> (formation_id, {player: slot 2..11}).
    line_prob: {player: {2: p_def, 3: p_mid, 4: p_fwd}} from past starts; players with no history are unconstrained."""
    players = list(avg_xy)
    probs = np.array([[ (line_prob or {}).get(p, {}).get(c, 0.0) for c in (2, 3, 4)] for p in players])
    known = probs.sum(axis=1) > 0
    pts = _norm(np.array([avg_xy[p] for p in players], dtype=float))
    weight = np.array([1.0, Y_WEIGHT])
    best = (np.inf, None, None)
    for fid, slots in CANDIDATES.items():
        if fid not in PRIOR:
            continue
        slot_ids = [s for s in range(2, 12)]
        ref = _norm(np.array([_POS[slots[s]] for s in slot_ids], dtype=float))
        cost = (((pts[:, None, :] - ref[None, :, :]) * weight) ** 2).sum(axis=2)
        slot_group = np.array([GROUP_CODE[slots[s]] - 2 for s in slot_ids])
        cost = cost + HISTORY_WEIGHT * np.where(known[:, None], 1.0 - probs[:, slot_group], 0.0)
        rows, cols = linear_sum_assignment(cost)
        total = cost[rows, cols].sum() - PRIOR_WEIGHT * np.log(PRIOR[fid])
        if total < best[0]:
            best = (total, fid, {players[r]: slot_ids[c] for r, c in zip(rows, cols)})
    return best[1], best[2]


def _quals(items: list[tuple[str, str]]) -> str:
    return repr([{"type": k, "value": v} for k, v in items])


def attach_lineups(df: pd.DataFrame, minutes: dict, goalkeeper_ids: set) -> tuple[pd.DataFrame, list[str]]:
    """Returns (frame with numeric playerId + lineup qualifiers, warnings)."""
    df = df.copy()
    warnings: list[str] = []
    df["d360_player_id"] = df["playerId"]
    has_player = df["playerId"].notna()
    df["playerId"] = df["playerId"].map(lambda v: float(numeric_player_id(v)) if pd.notna(v) else np.nan)
    pid_of = dict(zip(df.loc[has_player, "d360_player_id"], df.loc[has_player, "playerId"]))
    clock = pd.to_numeric(df["expandedMinute"], errors="coerce")
    df["qualifiers"] = df["qualifiers"].astype(object)

    hist = history()
    name_of = dict(zip(df.loc[has_player, "d360_player_id"], df.loc[has_player, "playerName"]))
    line_prob = {}
    for pid_, nm_ in name_of.items():
        counts = hist.get(fold(nm_))
        if counts:
            total = sum(counts.values())
            line_prob[pid_] = {int(k): v / total for k, v in counts.items()}
    touches = df[df.isTouch.astype(bool) & has_player & df.x.notna()]
    for team_id, tdf in df.groupby("teamId", sort=False):
        on_rows = tdf[tdf.type == "SubstitutionOn"].sort_values("eventId")
        off_rows = tdf[tdf.type == "SubstitutionOff"].sort_values("eventId")
        subbed_on = set(on_rows.d360_player_id.dropna())
        team_players = set(tdf.d360_player_id.dropna())
        starters = [p for p in team_players if minutes.get(p, 0) and minutes[p] > 0 and p not in subbed_on]
        set_up = tdf[tdf.type == "FormationSet"]
        if set_up.empty or len(starters) != 11:
            warnings.append(f"team {team_id}: {len(starters)} starters, lineup skipped")
            continue
        team_touch = touches[touches.teamId == team_id]

        def avg_of(players, start, end):
            w = team_touch[(clock.loc[team_touch.index] >= start) & (clock.loc[team_touch.index] < end)
                           & team_touch.d360_player_id.isin(players)]
            g = w.groupby("d360_player_id").agg(x=("x", "mean"), y=("y", "mean"), n=("x", "size"))
            return g

        def fit(xi, start, end):
            gk = [p for p in xi if p in goalkeeper_ids]
            allavg = avg_of(xi, start, end)
            whole = avg_of(xi, 0, 1e9)
            if not gk:
                gk = [whole.loc[[p for p in xi if p in whole.index]].x.idxmin()]
            outfield = [p for p in xi if p != gk[0]]
            if len(outfield) != 10:
                return None
            avg = {}
            for p in outfield:
                src = allavg if p in allavg.index and allavg.at[p, "n"] >= MIN_TOUCHES else whole
                if p not in src.index:
                    return None
                avg[p] = (src.at[p, "x"], src.at[p, "y"])
            fid, slots = estimate_formation(avg, line_prob)
            slots[gk[0]] = 1
            return fid, slots

        subs_times = sorted(clock.loc[on_rows.index])
        first_change_times = sorted(clock.loc[tdf[tdf.type == "FormationChange"].index])
        horizon = min([t for t in subs_times + first_change_times if t >= 30] + [60.0])
        initial = fit(starters, 0, horizon)
        if initial is None:
            warnings.append(f"team {team_id}: could not fit formation")
            continue
        fid, slot_of = initial
        code_of = lambda fid_, slot: GROUP_CODE.get(CANDIDATES[fid_][slot], 3)

        bench = [p for p in subbed_on if p in pid_of]
        involved = sorted(starters, key=lambda p: slot_of[p]) + sorted(bench)
        slots_list = [slot_of[p] for p in sorted(starters, key=lambda p: slot_of[p])] + [0] * len(bench)
        codes = [code_of(fid, slot_of[p]) for p in sorted(starters, key=lambda p: slot_of[p])] + [5] * len(bench)
        df.at[set_up.index[0], "qualifiers"] = _quals([
            ("InvolvedPlayers", ",".join(str(int(pid_of[p])) for p in involved)),
            ("PlayerPosition", ", ".join(map(str, codes))),
            ("TeamFormation", str(fid)),
            ("TeamPlayerFormation", ", ".join(map(str, slots_list))),
            ("FormationEstimated", "1"),
        ])

        # replay substitutions and shape changes chronologically, tracking who holds which slot
        current = dict(slot_of)
        off_stack = []
        events = [(clock.at[i], 0, r.eventId, i, r.type)
                  for i, r in tdf[tdf.type.isin(["SubstitutionOff", "SubstitutionOn"])].iterrows()]
        for t, _, event_id, i, kind in sorted(events, key=lambda e: (e[0], e[1], e[2])):
            if kind == "SubstitutionOff":
                off_stack.append((df.at[i, "d360_player_id"], event_id))
            elif kind == "SubstitutionOn":
                if not off_stack:
                    continue
                off_p, off_event = off_stack.pop(0)
                slot = current.pop(off_p, 0)
                on_p = df.at[i, "d360_player_id"]
                current[on_p] = slot
                df.at[i, "qualifiers"] = _quals([("RelatedEventId", str(int(off_event))), ("FormationSlot", str(slot))])
            # FORMATION_CHANGE rows stay empty: a shape re-fit on a short window is too noisy to trust
    return df, warnings
