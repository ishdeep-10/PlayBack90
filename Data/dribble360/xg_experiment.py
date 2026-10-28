"""Which missing input explains the xG gap? Re-run the real xG model on the processed Dribble360
frames, swapping in WhoScored's true values for one input at a time ("oracle" variants).

Run:  apps/api/.venv/bin/python Data/dribble360/xg_experiment.py
"""
import pickle
import sqlite3
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import data_utils  # noqa: E402
from process_match import card_types_for, load_team_map, process_match  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

CACHE = HERE / "cache"
PICKLE = CACHE / "processed_frames.pkl"


def rd(name, cols=None):
    return pq.read_table(CACHE / name, columns=cols).to_pandas(ignore_metadata=True)


def processed_frames():
    if PICKLE.exists():
        return pickle.loads(PICKLE.read_bytes())
    ev, pmx = rd("events.parquet"), rd("player_matches.parquet")
    pl = rd("players.parquet", ["id", "name", "known_name"]).set_index("id")
    names = pl.known_name.fillna(pl.name).to_dict()
    d3 = rd("matches.parquet", ["id", "home_score", "away_score"]).set_index("id")
    team_map = load_team_map()
    parity = pd.read_csv(HERE / "parity_matches.csv", dtype=str)
    xw = pd.read_csv(HERE / "crosswalk_matches.csv", dtype=str).set_index("ws_match_id")
    frames = {}
    for _, m in parity.iterrows():
        x = xw.loc[m.ws_match_id]
        gks = set(pmx[(pmx.match_id == m.d360_match_id) & pmx.saves.notna()].player_id)
        frames[m.ws_match_id] = process_match(
            ev[ev.match_id == m.d360_match_id], match_id=m.d360_match_id, league=m.league, season=m.season, date=m.date,
            home_team_id=x.d360_home_team_id, away_team_id=x.d360_away_team_id,
            home_score=int(d3.loc[m.d360_match_id].home_score), away_score=int(d3.loc[m.d360_match_id].away_score),
            players=names, goalkeeper_ids=gks, team_numeric=team_map, card_types=card_types_for(pmx, m.d360_match_id))
    PICKLE.write_bytes(pickle.dumps(frames))
    return frames


def tf(s):
    return s.fillna(False).astype(str).isin(["1", "1.0", "True", "true"])


frames = processed_frames()
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)
SHOTS = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
WS_ORACLE = ["bigChanceScored", "bigChanceMissed", "bigChanceCreated", "shotCounter", "situation"]

variants = {
    "baseline (as built)": [],
    "oracle big chance": ["bigChanceScored", "bigChanceMissed"],
    "oracle counter-attack": ["shotCounter"],
    "oracle situation (direct FK etc.)": ["situation"],
    "oracle all three": ["bigChanceScored", "bigChanceMissed", "shotCounter", "situation"],
}
rows = {name: [] for name in variants}
for ws_id, ours in frames.items():
    ws = pd.read_sql_query(
        "select eventId,teamId,type,xG,bigChanceScored,bigChanceMissed,bigChanceCreated,shotCounter,situation "
        "from event_data where CAST(matchId AS INTEGER)=? and eventId is not null", con, params=(int(ws_id),))
    ws = ws[ws.type.isin(SHOTS)]
    ws["k"] = list(zip(ws.teamId.astype(float), ws.eventId.astype(float)))
    wsd = {k: r for k, r in zip(ws.k, ws.to_dict("records"))}
    for name, cols in variants.items():
        df = ours.copy()
        keys = list(zip(df.teamId.astype(float), df.eventId.astype(float)))
        for c in cols:
            df[c] = pd.Series(keys, index=df.index).map({k: v[c] for k, v in wsd.items()}).where(tf(df.isShot), df[c])
        out = data_utils.get_xG_values(df)
        s = out[tf(out.isShot)]
        s_keys = list(zip(s.teamId.astype(float), s.eventId.astype(float)))
        rows[name].append(pd.DataFrame({"ours": pd.to_numeric(s.xG, errors="coerce").to_numpy(),
                                        "ws": [wsd.get(k, {}).get("xG", np.nan) for k in s_keys],
                                        "match": ws_id, "type": s.type.to_numpy()}))

print(f"{'variant':36}{'shots':>7}{'xG ws':>9}{'xG ours':>9}{'corr':>8}{'MAE':>8}{'sum err':>9}")
for name, parts in rows.items():
    d = pd.concat(parts).dropna()
    d["ws"] = pd.to_numeric(d.ws, errors="coerce")
    d = d.dropna()
    print(f"{name:36}{len(d):7}{d.ws.sum():9.1f}{d.ours.sum():9.1f}{np.corrcoef(d.ws, d.ours)[0, 1]:8.3f}"
          f"{(d.ws - d.ours).abs().mean():8.3f}{(d.ours.sum() / d.ws.sum() - 1):9.1%}")
