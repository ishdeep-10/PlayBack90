"""Re-check the vendor's derived flags against WhoScored on the 19 parity matches. Run after every Dribble360 republish
and before trusting a new snapshot (it found, on 2026-10-29, that `is_assist` is really a SHOT assist).

Pulls the full events/player_matches of the 19 parity matches (one 12 GB-scan query each, cached in
cache/parity_new_*.parquet; pass --refetch after a republish), runs them through the real pipeline
(process_match) and prints precision / recall against the stored WhoScored values, joined on (teamId, eventId):

  * raw vendor flags:  is_assist (as a key-pass source), is_big_chance on shots
  * our final fields:  passKey, assist (goal assist), bigChanceCreated, big chance on shots

Reference numbers (2026-10-29 snapshot): is_assist as key pass P1.00/R0.93; is_big_chance on shots 82/82 exact;
our passKey P0.96/R0.92, assist P0.90/R0.93, bigChanceCreated P0.91/R0.90. If these drop, the vendor changed
something: look at normalize._derive_pass_fields before rebuilding.

Run (needs google-cloud-bigquery importable, e.g. PYTHONPATH to a venv that has it):
    apps/api/.venv/bin/python Data/dribble360/validate_vendor_flags.py <billing-project-id> [--refetch]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import warnings
from pathlib import Path

import pandas as pd

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from process_match import load_team_map, process_match  # noqa: E402

DATASET = "dribble360.football_pro"
CACHE = HERE / "cache"
SHOTS_WS = ("Goal", "MissedShots", "SavedShot", "ShotOnPost")


def truthy(series: pd.Series) -> pd.Series:
    return series.astype(object).map(lambda v: str(v) in ("1", "1.0", "True", "true")).astype(bool)


def pull(project: str, ids: list[str], refetch: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    ev_path, pm_path = CACHE / "parity_new_events.parquet", CACHE / "parity_new_player_matches.parquet"
    if ev_path.exists() and pm_path.exists() and not refetch:
        return pd.read_parquet(ev_path), pd.read_parquet(pm_path)
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    in_list = ",".join(repr(i) for i in ids)
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=int(15e9))
    CACHE.mkdir(exist_ok=True)
    out = []
    for name, path in (("match_events", ev_path), ("player_matches", pm_path)):
        df = client.query(f"SELECT * FROM `{DATASET}.{name}` WHERE match_id IN ({in_list})", job_config=cfg).to_dataframe()
        df.to_parquet(path)
        out.append(df)
    return out[0], out[1]


def report(name: str, predicted: pd.Series, truth: pd.Series) -> None:
    tp = (predicted & truth).sum()
    print(f"{name:42} flagged={predicted.sum():4} whoscored={truth.sum():4} "
          f"precision={tp / max(predicted.sum(), 1):.2f} recall={tp / max(truth.sum(), 1):.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--refetch", action="store_true", help="ignore the cached pull (use after a vendor republish)")
    args = ap.parse_args()

    parity = pd.read_csv(HERE / "parity_matches.csv", dtype=str)
    xwalk = pd.read_csv(HERE / "crosswalk_matches.csv", dtype=str).set_index("ws_match_id")
    team_map = load_team_map()
    events, _ = pull(args.project, list(parity.d360_match_id), args.refetch)
    con = sqlite3.connect(f"file:{HERE.parent / 'playback90.db'}?mode=ro", uri=True)

    rows = []
    for _, m in parity.iterrows():
        x = xwalk.loc[m.ws_match_id]
        raw = events[events.match_id == m.d360_match_id]
        frame = process_match(
            raw, match_id=m.d360_match_id, league=m.league, season=m.season, date=m.date,
            home_team_id=x.d360_home_team_id, away_team_id=x.d360_away_team_id, home_score=0, away_score=0,
            players={}, goalkeeper_ids=set(), team_numeric=team_map, card_types={})
        vendor = raw.assign(teamId=raw.team_id.map(team_map).astype(float), eventId=raw.event_id.astype(float))[
            ["teamId", "eventId", "is_assist", "is_big_chance"]].rename(
            columns={"is_assist": "v_assist", "is_big_chance": "v_bigchance"})
        frame = frame.assign(teamId=frame.teamId.astype(float), eventId=frame.eventId.astype(float)).merge(
            vendor, on=["teamId", "eventId"], how="left")
        ws = pd.read_sql_query(
            "select teamId,eventId,type as ws_type,passKey,assist,bigChanceCreated,bigChanceScored,bigChanceMissed "
            "from event_data where CAST(matchId AS INTEGER)=? and eventId is not null", con,
            params=(int(m.ws_match_id),))
        ws = ws.assign(teamId=ws.teamId.astype(float), eventId=ws.eventId.astype(float))
        rows.append(frame.merge(ws, on=["teamId", "eventId"], suffixes=("", "_ws")))
    j = pd.concat(rows)

    ws_bigchance_shot = (truthy(j.bigChanceScored_ws) | truthy(j.bigChanceMissed_ws)) & j.ws_type.isin(SHOTS_WS)
    print(f"{len(j)} events joined across {len(parity)} matches\n")
    print("-- raw vendor flags")
    report("is_assist  vs WhoScored passKey (key pass)", truthy(j.v_assist), truthy(j.passKey_ws))
    report("is_assist  vs WhoScored assist (goal assist)", truthy(j.v_assist), truthy(j.assist_ws))
    report("is_big_chance on shots vs WhoScored", truthy(j.v_bigchance) & j.ws_type.isin(SHOTS_WS), ws_bigchance_shot)
    print("\n-- our final fields")
    report("passKey", truthy(j.passKey), truthy(j.passKey_ws))
    report("assist (goal assist)", truthy(j.assist), truthy(j.assist_ws))
    report("bigChanceCreated", truthy(j.bigChanceCreated), truthy(j.bigChanceCreated_ws))
    report("big chance on shots (bigChanceScored/Missed)",
           (truthy(j.bigChanceScored) | truthy(j.bigChanceMissed)) & j.isShot.astype(bool), ws_bigchance_shot)


if __name__ == "__main__":
    main()
