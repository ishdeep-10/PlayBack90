"""Fetch Dribble360 data for the parity matches in ONE pass and cache it as parquet.

Usage: python fetch_parity_data.py <billing-project-id>
The match_events table is ~12 GB per scan whatever the filter, so never loop per match.
"""
import sys
import warnings
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
CACHE.mkdir(exist_ok=True)
D = "dribble360.football_pro"
MAX_BYTES = int(15e9)

ids = pd.read_csv(HERE / "parity_matches.csv", dtype=str)["d360_match_id"].tolist()
in_list = ",".join(repr(i) for i in ids)
client = bigquery.Client(project=sys.argv[1])

QUERIES = {
    "events": f"SELECT * FROM `{D}.match_events` WHERE match_id IN ({in_list})",
    "team_matches": f"SELECT * FROM `{D}.team_matches` WHERE match_id IN ({in_list})",
    "player_matches": f"SELECT * FROM `{D}.player_matches` WHERE match_id IN ({in_list})",
    "matches": f"SELECT * FROM `{D}.matches` WHERE id IN ({in_list})",
    "teams": f"SELECT DISTINCT t.* FROM `{D}.teams` t JOIN `{D}.team_matches` tm ON tm.team_id = t.id WHERE tm.match_id IN ({in_list})",
    "players": f"SELECT DISTINCT p.* FROM `{D}.players` p JOIN `{D}.player_matches` pm ON pm.player_id = p.id WHERE pm.match_id IN ({in_list})",
}
for name, sql in QUERIES.items():
    est = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    df = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES)).to_dataframe()
    df.to_parquet(CACHE / f"{name}.parquet", index=False)
    print(f"{name:15} scan ~{est / 1e9:5.2f} GB  rows {len(df)}")
