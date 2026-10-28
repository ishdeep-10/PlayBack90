"""Build position_history.json: how often each player started in defence / midfield / attack, from the local
WhoScored lineups (top-5 leagues). lineups.py uses it to keep estimated roles sensible (a striker is not a centre-mid).

Run: python3 Data/dribble360/build_position_history.py
"""
import ast
import json
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)


def fold(name: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(name)) if not unicodedata.combining(c)).lower().strip()


names = {int(i): n for i, n in con.execute(
    "select distinct playerId, playerName from event_data where playerName is not null and playerId is not null")}
hist = defaultdict(Counter)
for (raw,) in con.execute("select qualifiers from event_data where type='FormationSet' and league!='mls'"):
    q = {d["type"]: d["value"] for d in ast.literal_eval(raw) if isinstance(d, dict)}
    try:
        ids = [int(v) for v in q["InvolvedPlayers"].split(",")]
        slots = [int(v) for v in q["TeamPlayerFormation"].replace(" ", "").split(",")]
        codes = [int(v) for v in q["PlayerPosition"].replace(" ", "").split(",")]
    except (KeyError, ValueError):
        continue
    for pid, slot, code in zip(ids, slots, codes):
        if slot > 0 and code in (2, 3, 4) and pid in names:
            hist[fold(names[pid])][str(code)] += 1
(HERE / "position_history.json").write_text(json.dumps(hist, separators=(",", ":")))
print(f"{len(hist)} players -> position_history.json")
