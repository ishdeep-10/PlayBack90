"""Dribble360 -> WhoScored-shaped event frame (the shape produced by main.createEventsDF).

Dribble360 and WhoScored are the same Opta feed: event ids, coordinates (0-100 %) and minutes are
identical, so this is mostly a rename plus re-deriving the fields Pro does not ship
(period, shot situation / on-target / blocked, key passes).

Known Pro-table quirks handled here:
  * Until the vendor's corrected snapshot (promised for 2026-10-28 23:00 UTC), `pass_angle_rad` holds the pass
    length in metres and `pass_length_m` is empty; afterwards `pass_length_m` is the length and `pass_angle_rad`
    the real angle. We detect which layout we got from `pass_length_m` being populated.
  * `event_id` is only unique per team -> key is (team_id, event_id); `id` is not chronological.
  * `is_big_chance` was mis-populated (vendor-confirmed) until that same snapshot; it is only trusted when the
    corrected layout is detected, otherwise a location stand-in is used (see to_contract).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Dribble360 type -> WhoScored displayName. Types absent here (OUT, DELETED_EVENT, ...) are dropped.
TYPE_MAP = {
    "PASS": "Pass", "BALL_RECOVERY": "BallRecovery", "BALL_TOUCH": "BallTouch", "AERIAL": "Aerial",
    "FOUL": "Foul", "CLEARANCE": "Clearance", "TACKLE": "Tackle", "TAKE_ON": "TakeOn",
    "DISPOSSESSED": "Dispossessed", "INTERCEPTION": "Interception", "BLOCKED_PASS": "BlockedPass",
    "CORNER_AWARDED": "CornerAwarded", "CHALLENGE": "Challenge", "ATTEMPT_SAVED": "SavedShot",
    "SAVE": "Save", "KEEPER_PICK_UP": "KeeperPickup", "PLAYER_OFF": "SubstitutionOff",
    "PLAYER_ON": "SubstitutionOn", "MISS": "MissedShots", "END": "End", "CARD": "Card",
    "START": "Start", "OFFSIDE_PASS": "OffsidePass", "OFFSIDE_PROVOKED": "OffsideProvoked",
    "FORMATION_CHANGE": "FormationChange", "GOAL": "Goal", "TEAM_SET_UP": "FormationSet",
    "ERROR": "Error", "KEEPER_SWEEPER": "KeeperSweeper", "SHIELD_BALL_OPP": "ShieldBallOpp",
    "CLAIM": "Claim", "PUNCH": "Punch", "POST": "ShotOnPost", "PENALTY_FACED": "PenaltyFaced",
    "GOOD_SKILL": "GoodSkill", "CHANCE_MISSED": "ChanceMissed", "SMOTHER": "Smother",
    "CROSS_NOT_CLAIMED": "CrossNotClaimed",
}
PERIOD_NAME = {1: "FirstHalf", 2: "SecondHalf", 3: "FirstPeriodOfExtraTime", 4: "SecondPeriodOfExtraTime",
               5: "PenaltyShootout", 14: "PostGame", 16: "PreMatch"}
SHOT_TYPES = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
BODY = {"head": "Head", "left_foot": "LeftFoot", "right_foot": "RightFoot", "other": "OtherBodyPart"}
NOT_TOUCH = {"FormationSet", "FormationChange", "SubstitutionOn", "SubstitutionOff", "Start", "End"}


def derive_period(events: pd.DataFrame) -> pd.Series:
    """Period number per row, from each team's own START/END markers ordered by that team's event_id.

    Ordering by the global `id` is wrong: late-logged events get high ids. A team's `event_id`
    is chronological within the team. END markers at 0:00 are the post-game markers.
    """
    out = pd.Series(16, index=events.index, dtype=int)
    for _, g in events.groupby("team_id"):
        g = g.sort_values("event_id")
        starts = list(g[g.type == "START"].event_id)
        period = pd.Series(16, index=g.index)
        for k, event_id in enumerate(starts, 1):
            period[g.event_id >= event_id] = k
        out[g.index] = period
    out[(events.type == "END") & (events.time_min == 0)] = 14

    # Late-logged events get large event_ids and land in the wrong period. Cap the ordering with
    # time rules (regular time): 2H cannot start before 45:00; 1H cannot run past its END marker.
    t = events.time_min * 60 + events.time_sec
    first_end = events.loc[(events.type == "END") & (events.time_min > 0), "time_min"].min()
    end1 = (events.loc[(events.type == "END") & (events.time_min == first_end), "time_min"].min() * 60
            + events.loc[(events.type == "END") & (events.time_min == first_end), "time_sec"].max()) if pd.notna(first_end) else np.inf
    out[(t < 2700) & out.between(2, 4)] = 1
    out[(t > end1) & (out == 1)] = 2
    # Same for extra time: ET1 cannot start before 90:00, ET2 before 105:00, the shootout before 120:00.
    out[(t < 5400) & (out == 3)] = 2
    out[(t < 6300) & (out == 4)] = 3
    out[(t < 7200) & (out == 5)] = 4
    # Half-time substitutions are logged at 45:00 ahead of the 1H END marker's stoppage time, so they land in the
    # first half. A stoppage-time sub can never be at exactly 45:00 while the half runs on, so treat them as 2H.
    half_time_sub = events.type.isin(["PLAYER_ON", "PLAYER_OFF"]) & (t == 2700) & (end1 > 2700)
    out[half_time_sub & (out == 1)] = 2
    return out


def _expanded_minute(df: pd.DataFrame) -> pd.Series:
    """WhoScored clock: later periods carry the stoppage time already played (2H starts at 45 + added time).
    expandedMinute = minute + shift, where shift for the 2H is (last 1H minute - 44), and extra time adds the 2H
    overrun (last 2H minute - 90) and, for the second extra-time period, the ET1 overrun (last ET1 minute - 105).
    The extra-time shifts follow the same convention but are not verified against WhoScored (no ET matches locally)."""
    def last(period: int) -> float:
        v = df.loc[df.period_n == period, "time_min"].max()
        return v if pd.notna(v) else np.nan
    shift_2h = max(last(1) - 44, 0) if pd.notna(last(1)) else 0
    over_2h = max(last(2) - 90, 0) if pd.notna(last(2)) else 0
    over_et1 = max(last(3) - 105, 0) if pd.notna(last(3)) else 0
    shift = df.period_n.map({2: shift_2h, 3: shift_2h + over_2h, 4: shift_2h + over_2h + over_et1}).fillna(0)
    return df.time_min.astype(float) + shift


def _chrono(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["period_n", "time_min", "time_sec", "event_id"], kind="stable")


def normalize_match(events: pd.DataFrame, *, home_team_id: str, away_team_id: str,
                    match_id: str, players: pd.DataFrame | None = None,
                    goalkeeper_ids: set[str] | None = None) -> pd.DataFrame:
    """Normalize one match. `players` maps id -> name; `goalkeeper_ids` marks GK player ids."""
    df = events.copy()
    fixed_snapshot = bool(df["pass_length_m"].notna().any()) if "pass_length_m" in df.columns else False
    df["period_n"] = derive_period(df)
    df["type_ws"] = df["type"].map(TYPE_MAP)
    dropped = df[df.type_ws.isna()]
    df = df[df.type_ws.notna()].copy()
    df = _chrono(df).reset_index(drop=True)

    out = pd.DataFrame({
        "eventId": df.event_id.astype(float),
        "matchId": match_id,
        "minute": df.time_min.astype(float),
        "second": df.time_sec.astype(float),
        "expandedMinute": _expanded_minute(df),
        "teamId": df.team_id,
        "h_a": np.where(df.team_id == home_team_id, "h", np.where(df.team_id == away_team_id, "a", None)),
        "playerId": df.player_id,
        "type": df.type_ws,
        "outcomeType": np.where(df.outcome.fillna(False).astype(bool), "Successful", "Unsuccessful"),
        "period": df.period_n.map(PERIOD_NAME),
        "x": df.x, "y": df.y, "endX": df.end_x, "endY": df.end_y,
        "isTouch": ~df.type_ws.isin(NOT_TOUCH),
        "isShot": df.type_ws.isin(SHOT_TYPES),
        "isGoal": df.type_ws == "Goal",
        # Max-only fields; left empty so downstream code sees "not available", not zeros.
        "goalMouthY": np.nan, "goalMouthZ": np.nan, "blockedX": np.nan, "blockedY": np.nan,
        "passLengthM": df.pass_length_m if fixed_snapshot else df.pass_angle_rad,  # see module docstring
        "vendorBigChance": df.is_big_chance.fillna(False).astype(bool) if fixed_snapshot else False,
        "snapshotFixed": fixed_snapshot,
        "shotBodyType": df.body_part.map(BODY).where(df.type_ws.isin(SHOT_TYPES)),
        "bodyPart": df.body_part.map(BODY),
        "setPieceType": df.set_piece_type,
        "isThroughBall": df.is_through_ball.fillna(False).astype(bool),
        "isSwitchOfPlay": df.is_switch_of_play.fillna(False).astype(bool),
        "assist": df.is_assist.fillna(False).astype(bool),
        "intentionalAssist": df.is_intentional_assist.fillna(False).astype(bool),
        "d360_event_id": df.event_id, "d360_id": df.id,
    })
    if players is not None:
        out["playerName"] = out.playerId.map(players)
    # Shootout kicks are not shots: they would add ~0.78 xG each and extra goals to the match totals.
    kick = (out.period == "PenaltyShootout") & out.type.isin(SHOT_TYPES)
    out.loc[kick, "type"] = "Shootout" + out.loc[kick, "type"]
    out.loc[kick, ["isShot", "isGoal"]] = False
    out = _derive_shot_fields(out, goalkeeper_ids or set())
    out = _derive_pass_fields(out)
    out.attrs["dropped_types"] = dropped["type"].value_counts().to_dict()
    return out


def _derive_shot_fields(out: pd.DataFrame, gk_ids: set[str]) -> pd.DataFrame:
    t = out.minute * 60 + out.second
    out["shotOnTarget"] = False
    out["shotBlocked"] = False
    out["shotOnPost"] = out.type == "ShotOnPost"
    saves = out[(out.type == "Save") & out.playerId.isin(gk_ids)]
    for i in out.index[out.type == "SavedShot"]:
        near = saves[(saves.teamId != out.at[i, "teamId"]) & ((t[saves.index] - t[i]).abs() <= 3)]
        out.at[i, "shotOnTarget" if len(near) else "shotBlocked"] = True
    out.loc[out.type == "Goal", "shotOnTarget"] = True

    # shot situation from the same team's recent set-piece pass (corner / free kick)
    situation = pd.Series(None, index=out.index, dtype=object)
    shots = out.index[out.isShot]
    for i in shots:
        prior = out[(out.teamId == out.at[i, "teamId"]) & (out.type == "Pass") & out.setPieceType.notna()
                    & (t <= t[i]) & (t[i] - t <= 12) & (out.period == out.at[i, "period"])]
        if len(prior):
            kind = prior.iloc[-1].setPieceType
            situation[i] = {"corner": "FromCorner", "free_kick": "SetPiece"}.get(kind, "OpenPlay")
        else:
            situation[i] = "OpenPlay"
    out["situation"] = situation
    return out


ASSIST_WINDOW_S = 8   # tuned against WhoScored on the 19 parity matches (see docs/dribble360-migration-plan.md)


def _derive_pass_fields(out: pd.DataFrame) -> pd.DataFrame:
    """passKey = successful pass whose next same-team action is a shot by a different player."""
    out["passKey"] = False
    out["keyShotIdx"] = np.nan
    t = out.minute * 60 + out.second
    for i in out.index[out.isShot]:
        prior = out[(out.index < i) & (out.teamId == out.at[i, "teamId"]) & (out.type == "Pass")
                    & (out.outcomeType == "Successful") & (out.playerId != out.at[i, "playerId"])
                    & (t[i] - t <= 5) & (out.period == out.at[i, "period"])]
        if len(prior):
            out.at[prior.index[-1], "passKey"] = True
            out.at[prior.index[-1], "keyShotIdx"] = i
    if not out.snapshotFixed.any():
        # vendor `is_assist` was mis-populated before the corrected snapshot: an assist is the key pass of a goal
        out["assist"] = False
        out["intentionalAssist"] = False
        linked = out.keyShotIdx.dropna().astype(int)
        scored = out.loc[linked.values, "type"].eq("Goal").to_numpy()
        out.loc[linked.index[scored], "assist"] = True
    else:
        # The corrected snapshot's `is_assist` still flags every pass that leads to a shot (about 20x the real assists,
        # all real assists included). Keep a flagged pass only when the same team's next shot, by someone else,
        # within ASSIST_WINDOW_S in the same period is a goal.
        flagged = out.index[out.assist | out.intentionalAssist]
        for i in flagged:
            nxt = out[(out.index > i) & out.isShot & (out.teamId == out.at[i, "teamId"])
                      & (out.period == out.at[i, "period"]) & (t - t[i] <= ASSIST_WINDOW_S)
                      & (out.playerId != out.at[i, "playerId"])]
            if nxt.empty or nxt.iloc[0].type != "Goal":
                out.at[i, "assist"] = False
                out.at[i, "intentionalAssist"] = False
    dx = (out.endX - out.x) * 1.05
    dy = (out.endY - out.y) * 0.68
    out["passAngle"] = np.arctan2(dy, dx)  # Pro ships no real angle; computed from coordinates
    return out


# --------------------------------------------------------------------------------------------
# Contract builder: everything the API reads from a stored event frame (79 columns, of which the
# flags below are derived from type/outcome). Rules were inferred from the stored WhoScored data
# on the 19 parity matches; `situation`-style heuristics are measured in compare_contract.py.
# --------------------------------------------------------------------------------------------
TOUCH_TYPES = {"BallTouch", "BlockedPass", "Claim", "Clearance", "Dispossessed", "Goal", "GoodSkill",
               "Interception", "MissedShots", "OffsidePass", "Pass", "Punch", "Save", "SavedShot",
               "ShotOnPost", "Smother", "Tackle", "TakeOn"}
PENALTY_X = (88.0, 91.0)      # penalty spot is ~11 m out: 89.5 % of pitch length
PENALTY_Y = 50.0
LONG_BALL_M = 32.0            # tuned against stored WhoScored flags, see compare_contract.py
CROSS_Y_WIDE = 24.0           # |y-50| >= 26 -> wide channel
CROSS_X_MIN, CROSS_END_X, CROSS_END_Y = 62.0, 83.0, (20.0, 80.0)


def _is_penalty(x, y):
    return (PENALTY_X[0] <= x <= PENALTY_X[1]) and abs(y - PENALTY_Y) <= 3.0


BIG_CHANCE_MAX_DIST_M = 11.0     # stand-in for the broken vendor flag, see docs/dribble360-migration-plan.md
BIG_CHANCE_MAX_LATERAL_M = 10.0


def to_contract(norm: pd.DataFrame, *, meta: dict, team_numeric: dict, card_types: dict | None = None,
                big_chance: str = "auto") -> pd.DataFrame:
    """`big_chance`: 'auto' (vendor flag when the corrected snapshot is detected, else the geometry stand-in),
    'proxy' (always the stand-in) or 'vendor' (always the vendor flag)."""
    """Add the remaining stored-frame columns. `team_numeric` maps Dribble360 team_id -> legacy numeric id."""
    df = norm.copy()
    ok = df.outcomeType == "Successful"
    is_pass = df.type == "Pass"
    sp = df.setPieceType.fillna("")

    df["isTouch"] = df.type.isin(TOUCH_TYPES) | ((df.type == "Foul") & ok)
    df["touches"] = df.isTouch
    df["turnover"] = (df.type == "BallTouch") & ~ok
    df["dispossessed"] = df.type == "Dispossessed"
    df["cornerAwarded"] = df.type == "CornerAwarded"
    df["foulGiven"] = (df.type == "Foul") & ok
    df["foulCommitted"] = (df.type == "Foul") & ~ok
    df["throwIn"] = is_pass & (sp == "throw_in")
    df["passCorner"] = is_pass & (sp == "corner")
    df["passFreekick"] = is_pass & (sp == "free_kick")
    df["duelAerialWon"] = (df.type == "Aerial") & ok
    df["duelAerialLost"] = (df.type == "Aerial") & ~ok

    # penalties: location based (Pro has no penalty qualifier)
    shot = df.isShot
    clock = (df.minute * 60 + df.second).to_numpy()
    spot = np.array([_is_penalty(x, y) for x, y in zip(df.x, df.y)], dtype=bool)
    isolated = np.array([
        not ((df.teamId.to_numpy() == df.teamId.iat[i]) & (np.arange(len(df)) < i) & (clock[i] - clock <= 8)
             & (df.period.to_numpy() == df.period.iat[i])).any()
        for i in range(len(df))
    ])
    pen = shot & spot & isolated
    df["penaltyScored"] = pen & (df.type == "Goal")
    df["penaltyMissed"] = pen & (df.type != "Goal")
    df.loc[pen, "situation"] = None
    df["shotOffTarget"] = df.type.isin(["MissedShots", "ShotOnPost"])
    df["shotCounter"] = False       # fast-break flag: not available on Pro
    df["goalOwn"] = False           # own goals: not identifiable on Pro
    df["isOwnGoal"] = False

    # pass families
    length = df.passLengthM
    wide = (df.y - 50).abs() >= (50 - CROSS_Y_WIDE)
    cross = (is_pass & ~(sp != "") & wide & (df.x >= CROSS_X_MIN) & (df.endX >= CROSS_END_X)
             & df.endY.between(*CROSS_END_Y)) | (is_pass & (sp == "corner"))
    long_ball = is_pass & (length >= LONG_BALL_M) & ~df.throwIn
    through = is_pass & df.isThroughBall
    df["passCrossAccurate"], df["passCrossInaccurate"] = cross & ok, cross & ~ok
    df["passLongBallAccurate"], df["passLongBallInaccurate"] = long_ball & ok, long_ball & ~ok
    df["passThroughBallAccurate"], df["passThroughBallInaccurate"] = through & ok, through & ~ok
    df["passThroughBallInacurate"] = df["passThroughBallInaccurate"]  # stored frame carries this typo'd twin
    df["passChipped"] = False       # not available on Pro

    # key passes / assists, split by delivery type
    key = df.passKey
    ast = df.assist & is_pass
    for prefix, mask in (("keyPass", key), ("assist", ast)):
        df[f"{prefix}Cross"] = mask & cross & (sp != "corner")
        df[f"{prefix}Corner"] = mask & (sp == "corner")
        df[f"{prefix}Throughball"] = mask & through
        df[f"{prefix}Freekick"] = mask & (sp == "free_kick")
        df[f"{prefix}Throwin"] = mask & (sp == "throw_in")

    # big chances: the Pro flag is unusable (vendor-confirmed bug). The xG model takes it as an input and
    # the whole xG gap vs the WhoScored build came from this field (see xg_apples.py), so use a simple
    # location stand-in: a shot within 11 m of goal and 10 m of the centre line. Measured against the
    # vendor's own team xG this lands within ~4% (corr 0.84), as close as the WhoScored build (0.75).
    for col in ("bigChanceCreated", "bigChanceMissed", "bigChanceScored"):
        df[col] = False
    if big_chance == "auto":
        big_chance = "vendor" if df.snapshotFixed.any() else "proxy"
    if big_chance in ("proxy", "vendor"):
        if big_chance == "vendor":
            near = shot & df.vendorBigChance
        else:
            dist = np.hypot((100 - df.x) * 1.05, (50 - df.y) * 0.68)
            lateral = (df.y - 50).abs() * 0.68
            near = shot & (dist <= BIG_CHANCE_MAX_DIST_M) & (lateral <= BIG_CHANCE_MAX_LATERAL_M)
        df["bigChanceScored"] = near & (df.type == "Goal")
        df["bigChanceMissed"] = near & (df.type != "Goal")
        linked = df.keyShotIdx.dropna().astype(int)
        df.loc[linked.index, "bigChanceCreated"] = near.reindex(linked.values).to_numpy()

    # cards: Pro has no card type; infer from the player's season-of-match totals
    card_types = card_types or {}
    ctype = pd.Series(0, index=df.index, dtype=object)
    seen: dict[str, int] = {}
    for i in df.index[df.type == "Card"]:
        pid = df.at[i, "playerId"]
        seen[pid] = seen.get(pid, 0) + 1
        ctype[i] = card_types.get((pid, seen[pid]), "Yellow")
    df["cardType"] = ctype

    # metadata the stored frame carries on every row
    df["teamId"] = df.teamId.map(team_numeric)
    for key_, value in meta.items():
        df[key_] = value
    df["id"] = np.arange(len(df))
    df["relatedEventId"] = np.nan
    df["relatedPlayerId"] = np.nan
    df["satisfiedEventsTypes"] = [[] for _ in range(len(df))]
    quals = []
    # Opta qualifier names the API looks for (set_pieces, entries, pass_network, season_baseline, UI): the Pro table
    # ships no qualifiers, so rebuild them from the flags we do have.
    for r in df.itertuples():
        q = []
        for flag, name in (("passKey", "KeyPass"), ("passKey", "ShotAssist"), ("assist", "IntentionalGoalAssist"),
                           ("bigChanceCreated", "BigChanceCreated"),
                           ("passCorner", "CornerTaken"), ("passCorner", "FromCorner"),
                           ("passFreekick", "FreekickTaken"),
                           ("throwIn", "ThrowIn"), ("throwIn", "ThrowinSetPiece"),
                           ("isThroughBall", "Throughball"), ("isSwitchOfPlay", "SwitchOfPlay"),
                           ("penaltyScored", "Penalty"), ("penaltyMissed", "Penalty")):
            if getattr(r, flag):
                q.append({"type": name, "value": None})
        if r.type == "Pass" and r.setPieceType == "goal_kick":
            q.append({"type": "GoalKick", "value": None})
        if r.passLongBallAccurate or r.passLongBallInaccurate:
            q.append({"type": "Longball", "value": None})
        if r.passCrossAccurate or r.passCrossInaccurate:
            q.append({"type": "Cross", "value": None})
        if r.type == "Aerial":
            # Opta tags each duel Defensive/Offensive; Pro drops it. Matches WhoScored on 99.9% of 31k aerials
            # (Defensive = in the player's own half, up to the centre circle).
            q.append({"type": "Defensive" if r.x <= 52.5 else "Offensive", "value": None})
        if r.shotBodyType:
            q.append({"type": r.shotBodyType, "value": None})
        elif r.type == "Pass" and isinstance(r.bodyPart, str):
            q.append({"type": r.bodyPart, "value": None})   # RightFoot / LeftFoot / Head: used for corner swing
        quals.append(q)
    df["qualifiers"] = quals
    return df
