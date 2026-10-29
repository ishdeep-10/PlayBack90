"""Page-by-page audit: run every page's view builder on 25 random matches that exist in BOTH the old WhoScored
backup (Data/dribble360/cache/pre-dribble360-backup) and the rebuilt frames (Data/dribble360/out), then print where
the leaf values differ (counts that vanish, sums that move more than 15%, new nulls).

Run from apps/api:   .venv/bin/python ../../Data/dribble360/audit_pages.py        (about 5 minutes)
Expected differences: goal_mouth_* (not in the Pro feed, pages hide them), hashed player ids, EPV/xPass populated
(the backup predates the model backfills). Anything else is worth a look. Last run 2026-10-29: no errors; open
differences are progressive passes/carries (-15 to -18%), transitions_to_attack (-27%), box entries (-14%).
"""
import re, sys, glob, warnings, traceback, json, time
from pathlib import Path
warnings.filterwarnings("ignore")
import pandas as pd, numpy as np, pyarrow.parquet as pq
from collections import defaultdict
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))
from app.services.matches import (build_match_summary_view, build_match_dynamics, build_player_stats, build_team_summaries,
    build_event_timeline, build_shots_sca_view, _normalize_team_names)
from app.services.views.defensive_actions import build_defensive_actions_view
from app.services.views.duels_transitions import build_duels_transitions_view
from app.services.views.entries import build_territory_entries
from app.services.views.pass_network import build_channel_analysis, build_in_possession_actions_view, build_in_possession_player_metrics, build_pass_network
from app.services.views.player_analysis import build_player_analysis_view
from app.services.views.goalkeeper import build_goalkeeper_view
from app.services.views.set_pieces import build_set_pieces_view
R = str(Path(__file__).resolve().parent) + "/"
rd = lambda p: _normalize_team_names(pq.read_table(p).to_pandas(ignore_metadata=True))
key = lambda f: tuple(re.match(r"(\d{4}-\d{2}-\d{2})_.+?_(\d+)_vs_(\d+)_", f.split("/")[-1]).groups())
old = {key(f): f for f in glob.glob(R + "cache/pre-dribble360-backup/event_data/*/2026_2027/*.parquet")}
new = {key(f): f for f in glob.glob(R + "out/event_data/*/2026_2027/*.parquet")}
common = sorted(set(old) & set(new)); rng = np.random.default_rng(7); picks = [common[i] for i in sorted(rng.choice(len(common), 25, replace=False))]
VIEWS = {
 "match-summary": lambda df, t: build_match_summary_view(df),
 "match-dynamics": lambda df, t: build_match_dynamics(df),
 "team-stats": lambda df, t: {"rows": [r.model_dump() for r in build_team_summaries(df)]},
 "player-stats": lambda df, t: {"rows": build_player_stats(df, team=t)},
 "pass-network": lambda df, t: build_pass_network(df, team=t, sub_window=None, score_state=None, time_range=None, third=None),
 "in-possession-player-metrics": lambda df, t: build_in_possession_player_metrics(df, team=t, sub_window=None, score_state=None, time_range=None),
 "in-possession-actions": lambda df, t: build_in_possession_actions_view(df, team=t, sub_window=None, score_state=None, time_range=None, third=None),
 "territory-entries": lambda df, t: build_territory_entries(df, team=t, time_range=None),
 "channel-analysis": lambda df, t: build_channel_analysis(df, team=t, score_state=None, time_range=None),
 "set-pieces": lambda df, t: build_set_pieces_view(df, team=t, score_state=None, time_range=None),
 "defensive-actions": lambda df, t: build_defensive_actions_view(df, team=t, score_state=None, time_range=None),
 "duels-transitions": lambda df, t: build_duels_transitions_view(df, team=t, duel_type=None, transition_type=None, score_state=None, time_range=None),
 "player-analysis": lambda df, t: build_player_analysis_view(df, team=t, score_state=None, time_range=None),
 "goalkeeper": lambda df, t: build_goalkeeper_view(df, team=t),
 "event-timeline": lambda df, t: {"points": build_event_timeline(df, team=t)},
 "shots-sca": lambda df, t: build_shots_sca_view(df),
}
def to_py(o):
    if hasattr(o, "model_dump"): return o.model_dump()
    return o
def walk(o, path, out):
    o = to_py(o)
    if isinstance(o, dict):
        for k, v in o.items(): walk(v, path + "." + str(k), out)
    elif isinstance(o, (list, tuple, np.ndarray)):
        out[path + "[]#len"].append(len(o))
        for v in list(o)[:400]: walk(v, path + "[]", out)
    elif isinstance(o, (bool, np.bool_)): out[path + "#true"].append(int(o))
    elif isinstance(o, (int, float, np.integer, np.floating)):
        if isinstance(o, float) and np.isnan(o): out[path + "#null"].append(1)
        else: out[path + "#num"].append(float(o))
    elif o is None: out[path + "#null"].append(1)
    elif isinstance(o, str): out[path + "#str" + ("" if o.strip() else "_empty")].append(1)
agg = {s: {v: defaultdict(list) for v in VIEWS} for s in ("old", "new")}; errs = {s: defaultdict(list) for s in ("old", "new")}
t0 = time.time()
for n, k in enumerate(picks):
    for src, files in (("old", old), ("new", new)):
        df = rd(files[k]); teams = [t for t in df.teamName.dropna().unique() if t][:2]
        for v, fn in VIEWS.items():
            for t in ([None] if v in ("match-summary", "match-dynamics", "team-stats", "shots-sca") else teams[:1]):
                try: walk(fn(df, t), v, agg[src][v])
                except Exception as e: errs[src][v].append(repr(e)[:120])
    print(f"fixture {n+1}/25 done {time.time()-t0:.0f}s", flush=True)
print("\n=== ERRORS (view: old/new count) ===")
for v in VIEWS: 
    if errs["old"][v] or errs["new"][v]: print(f"{v}: old {len(errs['old'][v])} new {len(errs['new'][v])}", (errs['new'][v] or errs['old'][v])[:1])
print("\n=== DIFFERENCES (per view; leaf path, old vs new) ===")
for v in VIEWS:
    rows = []
    for p in set(agg["old"][v]) | set(agg["new"][v]):
        a, b = agg["old"][v].get(p, []), agg["new"][v].get(p, [])
        if p.endswith("#num"):
            sa, sb = float(np.sum(a)), float(np.sum(b)); na, nb = len(a), len(b)
            nz_a, nz_b = int(np.count_nonzero(a)), int(np.count_nonzero(b))
            if (nz_a > 8 and (nz_b < 0.5 * nz_a)) or (nz_a > 8 and abs(sb - sa) > 0.15 * max(abs(sa), 1e-9) and abs(sb - sa) > 5): rows.append((p, f"nonzero {nz_a}->{nz_b}  sum {sa:.1f}->{sb:.1f}"))
            elif nz_a <= 8 and nz_b > 20: rows.append((p, f"nonzero {nz_a}->{nz_b}  sum {sa:.1f}->{sb:.1f}"))
        elif p.endswith("#len"):
            sa, sb = sum(a), sum(b)
            if sa > 20 and (sb < 0.8 * sa or sb > 1.25 * sa): rows.append((p, f"items {sa}->{sb}"))
        elif p.endswith("#null") or p.endswith("#str_empty"):
            if (len(b) > 2 * len(a) + 20) : rows.append((p, f"{p.split('#')[1]} {len(a)}->{len(b)}"))
    if rows:
        print(f"\n[{v}]")
        for p, m in sorted(rows)[:14]: print(f"  {p.replace(v,'',1):70} {m}")
