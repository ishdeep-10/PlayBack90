"""Our per-team xG totals (several big-chance treatments) vs Dribble360's own team expected_goals."""
import pickle, sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
import pyarrow.parquet as pq
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import data_utils  # noqa: E402
from process_match import load_team_map  # noqa: E402

frames = pickle.loads((HERE / "cache" / "processed_frames.pkl").read_bytes())
tm = pq.read_table(HERE / "cache" / "team_matches.parquet", columns=["match_id", "team_id", "expected_goals"]).to_pandas(ignore_metadata=True)
vendor = {(r.match_id, r.team_id): r.expected_goals for r in tm.itertuples()}
num2d = {v: k for k, v in load_team_map().items()}
parity = pd.read_csv(HERE / "parity_matches.csv", dtype=str).set_index("ws_match_id")
tf = lambda s: s.fillna(False).astype(str).isin(["1", "1.0", "True", "true"])  # noqa: E731
apples = pd.read_pickle(HERE / "cache" / "xg_apples.pkl")


def treat(df, how, ws_flags):
    df = df.copy()
    shot = tf(df.isShot)
    if how == "none":
        return df
    if how == "proxy 11m/10m":
        near = (np.hypot(105 - df.x, 34 - df.y) <= 11) & ((df.y - 34).abs() <= 10) & shot
        df["bigChanceScored"] = (near & (df.type == "Goal")).astype(float)
        df["bigChanceMissed"] = (near & (df.type != "Goal")).astype(float)
    return df


rows = []
for wid, f in frames.items():
    d3 = parity.loc[wid].d360_match_id
    for how in ("none", "proxy 11m/10m"):
        out = data_utils.get_xG_values(treat(f, how, None))
        s = out[tf(out.isShot)]
        for team, g in s.groupby("teamId"):
            v = vendor.get((d3, num2d.get(int(team))))
            rows.append({"how": how, "match": wid, "team": int(team), "ours": pd.to_numeric(g.xG).sum(), "vendor": v})
d = pd.DataFrame(rows).dropna()
print(f"{'treatment':16}{'team-matches':>13}{'vendor xG':>11}{'ours':>8}{'corr':>7}{'MAE/team':>10}{'bias':>8}")
for how, g in d.groupby("how"):
    print(f"{how:16}{len(g):13}{g.vendor.sum():11.1f}{g.ours.sum():8.1f}{np.corrcoef(g.vendor, g.ours)[0, 1]:7.3f}{(g.vendor - g.ours).abs().mean():10.3f}{g.ours.sum() / g.vendor.sum() - 1:8.1%}")
# the existing WhoScored-based pipeline for reference: current model on WhoScored data vs vendor
ref = []
for wid in frames:
    d3 = parity.loc[wid].d360_match_id
    a = apples[(apples.variant == "as built") & (apples.match == wid)]
    ref.append((wid, a.ws_model_now.sum(), sum(v for (m, t), v in vendor.items() if m == d3 and v == v)))
r = pd.DataFrame(ref, columns=["m", "ws_model", "vendor"])
print(f"\nmatch totals, current model on WhoScored data: {r.ws_model.sum():.1f} vs vendor {r.vendor.sum():.1f} (corr {np.corrcoef(r.ws_model, r.vendor)[0,1]:.3f})")
