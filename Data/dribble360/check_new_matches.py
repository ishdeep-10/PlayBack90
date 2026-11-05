"""Daily BigQuery check: what the vendor has that our database does not, and when BigQuery last refreshed.

Metadata only (a few MB billed, never the 12 GB events table). Reports:
  1. the exact time each Dribble360 table was last modified (the vendor's refresh time, UTC)
  2. PLAYED matches in BigQuery that are not in out/synced_matches.json (the sync will pick these up)
  3. past-dated matches still marked FIXTURE in BigQuery and not synced (the vendor has not caught up)
and appends one row per run to out/bq_check_log.csv so the refresh history builds up.

Run: PYTHONPATH=~/.d360-bq apps/api/.venv/bin/python -W ignore Data/dribble360/check_new_matches.py playback90-505308
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_crosswalk import LEAGUES  # noqa: E402
from sync_current_season import DATASET, LEAGUE_PHASE_START, MAX_META_BYTES, STATE_FILE  # noqa: E402

CHECKED = ["mls", "premier-league", "laliga", "serie-a", "bundesliga", "ligue-1", "champions-league", "europa-league"]
TABLES = ["matches", "team_matches", "match_events"]


def team_names() -> dict[str, str]:
    names: dict[str, str] = {}
    for fname, id_col, name_col in (("team_registry.csv", "d360_team_id", "name"), ("crosswalk_teams.csv", "d360_team_id", "d360_name")):
        path = HERE / fname
        if path.exists():
            names.update(pd.read_csv(path, dtype=str).set_index(id_col)[name_col].dropna().to_dict())
    return names


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="billing project id (the sandbox, never one with billing linked)")
    ap.add_argument("--league", action="append", choices=list(LEAGUES), help="repeatable; default all eight competitions")
    ap.add_argument("--since", default="2026-01-01", help="seasons that started on/after this date (MLS needs 2026-01-01)")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    args = ap.parse_args()
    leagues = args.league or CHECKED
    now = datetime.now(timezone.utc)

    client = bigquery.Client(project=args.project)
    print(f"BigQuery check at {now:%Y-%m-%d %H:%M:%S} UTC")
    print("\nVendor refresh (table last modified, UTC):")
    modified = {}
    for t in TABLES:
        tb = client.get_table(f"{DATASET}.{t}")
        modified[t] = tb.modified
        print(f"  {t:<13} {tb.modified:%Y-%m-%d %H:%M:%S}  ({(now - tb.modified).total_seconds() / 3600:.1f} h ago)")

    ids = ",".join(repr(LEAGUES[k]) for k in leagues)
    key_of = {v: k for k, v in LEAGUES.items()}
    sql = f"""
        SELECT m.id AS match_id, CAST(m.date AS STRING) AS date, m.status, m.home_score, m.away_score, l.id AS league_id,
               th.team_id AS home_team_id, ta.team_id AS away_team_id
        FROM `{DATASET}.matches` m
        JOIN `{DATASET}.seasons` s ON s.id = m.season_id
        JOIN `{DATASET}.leagues` l ON l.id = s.league_id
        JOIN `{DATASET}.team_matches` th ON th.match_id = m.id AND th.side = 'HOME'
        JOIN `{DATASET}.team_matches` ta ON ta.match_id = m.id AND ta.side = 'AWAY'
        WHERE s.start_date >= DATE '{args.since}' AND l.id IN ({ids}) AND m.date <= DATE '{now:%Y-%m-%d}'
    """
    df = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_META_BYTES)).to_dataframe()
    df["league"] = df.league_id.map(key_of)
    df = df[~(df.league.isin(LEAGUE_PHASE_START) & (df.date < df.league.map(LEAGUE_PHASE_START).fillna("")))]

    state = args.out / STATE_FILE
    done = set(json.loads(state.read_text())) if state.exists() else set()
    names = team_names()
    df["fixture"] = df.home_team_id.map(lambda i: names.get(i, i[:8])) + " v " + df.away_team_id.map(lambda i: names.get(i, i[:8]))
    todo = df[~df.match_id.isin(done)].sort_values(["league", "date"])

    new = todo[todo.status == "PLAYED"]
    overdue = todo[(todo.status != "PLAYED") & (todo.date < f"{now:%Y-%m-%d}")]
    today = todo[(todo.status != "PLAYED") & (todo.date == f"{now:%Y-%m-%d}")]
    played_all = df[df.status == "PLAYED"]
    print(f"\nIn BigQuery as PLAYED: {len(played_all)}. In our database (synced): {len(done)}.")

    def show(title: str, rows: pd.DataFrame, score: bool) -> None:
        print(f"\n{title}: {len(rows)}")
        for r in rows.itertuples():
            sc = f"  {r.home_score}-{r.away_score}" if score else ""
            print(f"  {r.league:<17} {r.date}  {r.fixture}{sc}  [{r.match_id}]")

    show("New in BigQuery, not in our database (sync will take these)", new, True)
    show("Past-dated but still FIXTURE in BigQuery (vendor has not marked them played)", overdue, False)
    show("Kick-off today, not played yet", today, False)

    log = args.out / "bq_check_log.csv"
    args.out.mkdir(parents=True, exist_ok=True)
    prev = None
    if log.exists():
        rows = list(csv.DictReader(log.open()))
        prev = rows[-1]["matches_modified_utc"] if rows else None
    cur = f"{modified['matches']:%Y-%m-%d %H:%M:%S}"
    with log.open("a", newline="") as f:
        w = csv.writer(f)
        if not log.stat().st_size:
            w.writerow(["checked_utc", "matches_modified_utc", "team_matches_modified_utc", "match_events_modified_utc",
                        "played_in_bq", "synced", "new", "overdue_fixture"])
        w.writerow([f"{now:%Y-%m-%d %H:%M:%S}", cur, f"{modified['team_matches']:%Y-%m-%d %H:%M:%S}",
                    f"{modified['match_events']:%Y-%m-%d %H:%M:%S}", len(played_all), len(done), len(new), len(overdue)])
    if prev:
        print(f"\nVendor refresh since last check ({prev}): {'YES, updated' if prev != cur else 'no change'}")
    print(f"Logged to {log}")


if __name__ == "__main__":
    main()
