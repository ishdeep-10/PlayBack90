"""Effect of a geometry-based big-chance stand-in on xG (real model, 19 matches, 483 shots)."""
import pickle, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import data_utils  # noqa: E402

frames = pickle.loads((HERE / "cache" / "processed_frames.pkl").read_bytes())
apples = pd.read_pickle(HERE / "cache" / "xg_apples.pkl")
tf = lambda s: s.fillna(False).astype(str).isin(["1", "1.0", "True", "true"])  # noqa: E731
ref = {(r.match, i): r.ws_model_now for r in apples[apples.variant == "as built"].itertuples() for i in [0]}
RULES = {"dist<=14m & lateral<=8m": (14, 8), "dist<=11m & lateral<=10m": (11, 10), "dist<=9m & lateral<=6m": (9, 6)}
out = []
for wid, f in frames.items():
    base = apples[(apples.variant == "as built") & (apples.match == wid)].ws_model_now.to_numpy()
    for name, (dist, lat) in RULES.items():
        df = f.copy()
        shot = tf(df.isShot)
        near = (np.hypot(105 - df.x, 34 - df.y) <= dist) & ((df.y - 34).abs() <= lat) & shot
        df["bigChanceScored"] = (near & (df.type == "Goal")).astype(float)
        df["bigChanceMissed"] = (near & (df.type != "Goal")).astype(float)
        res = data_utils.get_xG_values(df)
        s = res[tf(res.isShot)]
        out.append(pd.DataFrame({"rule": name, "match": wid, "ours": pd.to_numeric(s.xG).to_numpy(), "ws": base[:len(s)] if len(base) == len(s) else np.nan}))
d = pd.concat(out).dropna()
print(f"{'rule':28}{'shots':>6}{'WS+model':>10}{'D360':>8}{'corr':>7}{'MAE':>8}{'sum err':>9}")
for name, g in d.groupby("rule"):
    print(f"{name:28}{len(g):6}{g.ws.sum():10.1f}{g.ours.sum():8.1f}{np.corrcoef(g.ws, g.ours)[0, 1]:7.3f}{(g.ws - g.ours).abs().mean():8.3f}{g.ours.sum() / g.ws.sum() - 1:9.1%}")
