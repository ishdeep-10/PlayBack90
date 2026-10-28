"""Read-only discovery of the Dribble360 BigQuery dataset.

Usage: python bq_discover.py <billing-project-id>

Every query is dry-run first and skipped if it would scan more than MAX_GB,
so a mistake can't run up query costs.
"""
import sys

from google.cloud import bigquery

DATASET = "dribble360.football_pro"
SAMPLE_MATCH_ID = "56sqj49wua0241sbk71k9rdhw"  # Crystal Palace vs Arsenal, 2026-05-24
MAX_GB = 5.0

client = bigquery.Client(project=sys.argv[1])


def run(title, sql):
    est = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
    gb = est / 1e9
    print(f"\n=== {title}  (scan ~{gb:.3f} GB)")
    if gb > MAX_GB:
        print(f"  skipped: exceeds {MAX_GB} GB cap")
        return None
    # Server-side hard cap: BigQuery fails the job instead of billing past it.
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=int(MAX_GB * 1e9))
    df = client.query(sql, job_config=cfg).to_dataframe()
    print(df.to_string(max_rows=60, max_colwidth=60))
    return df


run("tables", f"SELECT table_name, table_type FROM `{DATASET}.INFORMATION_SCHEMA.TABLES` ORDER BY 1")
run("match_events columns", f"""
    SELECT column_name, data_type FROM `{DATASET}.INFORMATION_SCHEMA.COLUMNS`
    WHERE table_name = 'match_events' ORDER BY ordinal_position""")
run("sample match events by type", f"""
    SELECT type, outcome, COUNT(*) n FROM `{DATASET}.match_events`
    WHERE match_id = '{SAMPLE_MATCH_ID}' GROUP BY 1, 2 ORDER BY n DESC""")
