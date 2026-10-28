"""Apples-to-apples xG: run the CURRENT model on the WhoScored frame and on the Dribble360 frame.

Run:  apps/api/.venv/bin/python Data/dribble360/xg_apples.py
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

frames = pickle.loads((HERE / "cache" / "processed_frames.pkl").read_bytes())
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)
SH = {"Goal", "MissedShots", "SavedShot", "ShotOnPost"}
tf = lambda s: s.fillna(False).astype(str).isin(["1", "1.0", "True", "true"])  # noqa: E731

rows = []
for wid, ours in frames.items():
    ws = pd.read_sql_query("select * from event_data where CAST(matchId AS INTEGER)=?", con, params=(int(wid),))
    ws_re = data_utils.get_xG_values(ws.copy())                     # current model on WhoScored data
    w = ws_re[ws_re.type.isin(SH)]
    wmap = {(float(t), float(e)): (x, o) for t, e, x, o in zip(w.teamId, w.eventId, w.xG, ws[ws.type.isin(SH)].xG)}
    keys = pd.Series(list(zip(ours.teamId.astype(float), ours.eventId.astype(float))), index=ours.index)
    bc = {(float(t), float(e)): (tf(pd.Series([a])).iloc[0], tf(pd.Series([b])).iloc[0])
          for t, e, a, b in zip(ws.teamId, ws.eventId, ws.bigChanceScored, ws.bigChanceMissed)}
    variants = {"as built": ours.copy()}
    o2 = ours.copy()
    o2["bigChanceScored"] = keys.map(lambda k: bc.get(k, (False, False))[0]).where(tf(o2.isShot), o2.bigChanceScored)
    o2["bigChanceMissed"] = keys.map(lambda k: bc.get(k, (False, False))[1]).where(tf(o2.isShot), o2.bigChanceMissed)
    variants["with true big-chance flags"] = o2
    for name, df in variants.items():
        out = data_utils.get_xG_values(df)
        s = out[tf(out.isShot)]
        for r in s.itertuples():
            k = (float(r.teamId), float(r.eventId))
            if k in wmap:
                rows.append({"variant": name, "match": wid, "ours": float(r.xG), "ws_model_now": float(wmap[k][0]),
                             "ws_stored": wmap[k][1], "type": r.type})
d = pd.DataFrame(rows)
d.to_pickle(HERE / "cache" / "xg_apples.pkl")
print(f"{'variant':30}{'shots':>7}{'WS+model':>10}{'D360':>9}{'corr':>8}{'MAE':>8}{'sum err':>9}")
for name, g in d.groupby("variant"):
    print(f"{name:30}{len(g):7}{g.ws_model_now.sum():10.1f}{g.ours.sum():9.1f}{np.corrcoef(g.ws_model_now, g.ours)[0, 1]:8.3f}"
          f"{(g.ws_model_now - g.ours).abs().mean():8.3f}{g.ours.sum() / g.ws_model_now.sum() - 1:9.1%}")
g = d[d.variant == "as built"].dropna(subset=["ws_stored"])
print(f"\nstored WhoScored xG vs current model on same WhoScored data ({len(g)} shots with stored xG): "
      f"stored {g.ws_stored.sum():.1f} vs recomputed {g.ws_model_now.sum():.1f}, corr {np.corrcoef(g.ws_stored, g.ws_model_now)[0, 1]:.3f}")
