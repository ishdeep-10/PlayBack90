"""Compare rebuilt lineups/formations with the true WhoScored ones on the parity matches.
Run: apps/api/.venv/bin/python Data/dribble360/validate_lineups.py
"""
import ast, pickle, sqlite3, sys, warnings
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
from lineups import attach_lineups, GROUP_CODE, CANDIDATES
from app.services.views.match_summary import build_lineups, FORMATION_ID_NAMES

C = HERE / "cache"
rd = lambda n: pq.read_table(C / n).to_pandas(ignore_metadata=True)
frames = pickle.loads((C / "processed_frames.pkl").read_bytes())
pmx = rd("player_matches.parquet")
parity = pd.read_csv(HERE / "parity_matches.csv", dtype=str).set_index("ws_match_id")
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)
quals = lambda s: {d["type"]: d["value"] for d in ast.literal_eval(s) if isinstance(d, dict)}
res = []
for ws_id, frame in frames.items():
    d3 = parity.at[ws_id, "d360_match_id"]
    pm = pmx[pmx.match_id == d3]
    minutes = dict(zip(pm.player_id, pm.mins_played.fillna(0)))
    gks = set(pm[pm.saves.notna()].player_id)
    out, warns = attach_lineups(frame, minutes, gks)
    teams = list(out.teamName.dropna().unique())[:2]
    mine = build_lineups(out, teams)
    truth = pd.read_sql_query("select teamId,teamName,type,playerId,playerName,qualifiers from event_data where CAST(matchId AS INTEGER)=? and (type='FormationSet' or playerName is not null)", con, params=(int(ws_id),))
    nn = truth.dropna(subset=['playerId', 'playerName'])
    names = dict(zip(nn.playerId.astype(int), nn.playerName))
    for _, r in truth[truth.type == "FormationSet"].iterrows():
        q = quals(r.qualifiers); ids = [int(v) for v in q["InvolvedPlayers"].split(",")]; sl = [int(v.strip()) for v in q["TeamPlayerFormation"].split(",")]
        tf = int(q["TeamFormation"]); t_starters = {names.get(i): s for i, s in zip(ids, sl) if s > 0}
        m = mine["teams"].get(r.teamName)
        if not m: res.append(dict(match=ws_id, team=r.teamName, ok=False, warn=warns)); continue
        m_starters = {p["player"]: p["slot"] for p in m["starters"]}
        same_set = set(m_starters) == set(t_starters)
        pos_t = {n: GROUP_CODE.get(CANDIDATES.get(tf, {}).get(s, ""), 0) for n, s in t_starters.items()}
        pos_m = {p["player"]: GROUP_CODE.get(p["position"], 0) for p in m["starters"]}
        grp = sum(pos_t[n] == pos_m.get(n) for n in pos_t) / 11
        res.append(dict(match=ws_id, team=r.teamName, ok=True, starters_overlap=len(set(m_starters) & set(t_starters)), same_set=same_set,
                        true_f=FORMATION_ID_NAMES.get(tf), my_f=m["formation"], f_exact=FORMATION_ID_NAMES.get(tf) == m["formation"],
                        line_group_agree=grp, n_subs_true=int((truth.type.isin(["SubstitutionOn"])).sum()), warns=len(warns)))
d = pd.DataFrame(res); pd.set_option("display.width", 250)
print(d.drop(columns=["warn"], errors="ignore").to_string())
g = d[d.ok == True]
print(f"\nteams {len(d)}, built {len(g)}; starters exact set {g.same_set.mean():.0%}; avg overlap {g.starters_overlap.mean():.1f}/11; formation exact {g.f_exact.mean():.0%}; role-line agreement {g.line_group_agree.mean():.0%}")
