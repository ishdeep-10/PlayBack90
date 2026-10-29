"""Checks on the rebuilt frames in Data/dribble360/out BEFORE uploading to R2: match counts per competition, goals /
shots / assists / key passes / xG per league (assists per goal should sit around 0.6-0.8 and xG per goal near 1.0),
aerial Defensive tags, shootout kicks not counted as shots, second-half clock offset, and that every team id has a
name in the app.

Run:  apps/api/.venv/bin/python Data/dribble360/precheck_upload.py
"""
import sys, glob, collections
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "apps" / "api"))
import pandas as pd, numpy as np
from app.domain import TEAM_DICT
O=str(HERE / 'out' / 'event_data') + '/'
tot=collections.Counter(); ids=set(); rows=[]
for f in glob.glob(O+'*/*/*.parquet'):
    lg=f.split('/event_data/')[1].split('/')[0]
    d=pd.read_parquet(f,columns=['teamId','type','isGoal','isShot','assist','passKey','bigChanceCreated','period','expandedMinute','minute','xG','qualifiers','playerName','matchId'])
    tot[lg]+=1; ids|=set(pd.to_numeric(d.teamId,errors='coerce').dropna().astype(int))
    tf=lambda s:s.astype(object).map(lambda v:str(v) in('1','1.0','True','true'))
    rows.append(dict(lg=lg,goals=int(tf(d.isGoal).sum()),shots=int(tf(d.isShot).sum()),assists=int(tf(d.assist).sum()),keypass=int(tf(d.passKey).sum()),bcc=int(tf(d.bigChanceCreated).sum()),
      xg=float(pd.to_numeric(d.xG,errors='coerce').sum()),aer=int((d.type=='Aerial').sum()),aerDef=int(d.qualifiers.astype(str).str.contains('Defensive').sum()),
      shootout=int((d.period=='PenaltyShootout').sum()),shotsShootoutBug=int(((d.period=='PenaltyShootout')&tf(d.isShot)).sum()),
      clk=float(d.loc[d.period=='SecondHalf','expandedMinute'].min()-d.loc[d.period=='FirstHalf','expandedMinute'].max()),
      names=int(d.playerName.isna().sum())))
print(dict(tot), sum(tot.values()))
r=pd.DataFrame(rows).groupby('lg').agg(goals=('goals','sum'),shots=('shots','sum'),assists=('assists','sum'),keypass=('keypass','sum'),bcc=('bcc','sum'),xg=('xg','sum'),aer=('aer','sum'),aerDef=('aerDef','sum'),shootBug=('shotsShootoutBug','sum'),clk_min=('clk','min'),clk_max=('clk','max'))
r['assist/goal']=(r.assists/r.goals).round(2); r['xg/goal']=(r.xg/r.goals).round(2); print(r.round(1).to_string())
print('team ids',len(ids),'missing names',sorted(i for i in ids if i not in TEAM_DICT)[:10])
