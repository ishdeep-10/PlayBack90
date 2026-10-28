"""Weekly sync: Dribble360 (BigQuery Pro) -> PlayBack90 event frames for the current season.

One metadata query lists played matches, one events pull fetches every NEW match (match_events is ~12 GB per
scan whatever the filter, so never run this per match). Each match goes through normalize -> contract ->
data_preprocessing and is written as parquet in the R2 layout under --out. Nothing is uploaded unless
--upload is passed together with an explicit --r2-prefix.

Run (API venv has xgboost/sklearn; google-cloud-bigquery and pyarrow must be importable):
    apps/api/.venv/bin/python Data/dribble360/sync_current_season.py <billing-project-id> --dry-run
    apps/api/.venv/bin/python Data/dribble360/sync_current_season.py <billing-project-id>
    apps/api/.venv/bin/python Data/dribble360/sync_current_season.py <billing-project-id> --upload --r2-prefix staging
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from build_crosswalk import LEAGUES  # noqa: E402
from r2_match_store import R2MatchStore, build_event_object_key  # noqa: E402
from process_match import card_types_for, load_team_map, process_match  # noqa: E402

DATASET = "dribble360.football_pro"
SEASON_START = "2026-08-01"  # Europe 2026/27 only
TOP_FIVE = ["premier-league", "laliga", "serie-a", "bundesliga", "ligue-1"]
DEFAULT_LEAGUES = TOP_FIVE  # the weekly default; add others with --league (MLS also needs --since 2026-01-01)
MAX_META_BYTES = int(2e9)
MAX_EVENT_BYTES = int(15e9)
STATE_FILE = "synced_matches.json"


def list_played(client: bigquery.Client, league_keys: list[str], since: str = SEASON_START) -> pd.DataFrame:
    ids = ",".join(repr(LEAGUES[k]) for k in league_keys)
    key_of = {v: k for k, v in LEAGUES.items()}
    sql = f"""
        SELECT m.id AS match_id, CAST(m.date AS STRING) AS date, s.name AS season, l.id AS league_id,
               m.home_score, m.away_score,
               th.team_id AS home_team_id, ta.team_id AS away_team_id
        FROM `{DATASET}.matches` m
        JOIN `{DATASET}.seasons` s ON s.id = m.season_id
        JOIN `{DATASET}.leagues` l ON l.id = s.league_id
        JOIN `{DATASET}.team_matches` th ON th.match_id = m.id AND th.side = 'HOME'
        JOIN `{DATASET}.team_matches` ta ON ta.match_id = m.id AND ta.side = 'AWAY'
        WHERE m.status = 'PLAYED' AND s.start_date >= DATE '{since}' AND l.id IN ({ids})
    """
    df = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=MAX_META_BYTES)).to_dataframe()
    df["league"] = df.league_id.map(key_of)
    return df


def fetch(client: bigquery.Client, ids: list[str]) -> dict[str, pd.DataFrame]:
    in_list = ",".join(repr(i) for i in ids)
    queries = {
        "events": f"SELECT * FROM `{DATASET}.match_events` WHERE match_id IN ({in_list})",
        "player_matches": f"SELECT * FROM `{DATASET}.player_matches` WHERE match_id IN ({in_list})",
        "players": f"SELECT DISTINCT p.* FROM `{DATASET}.players` p JOIN `{DATASET}.player_matches` pm "
                   f"ON pm.player_id = p.id WHERE pm.match_id IN ({in_list})",
    }
    out = {}
    for name, sql in queries.items():
        cfg = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_EVENT_BYTES)
        out[name] = client.query(sql, job_config=cfg).to_dataframe()
        print(f"  fetched {name}: {len(out[name])} rows")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", help="billing project id (sandbox project, never one with billing linked)")
    ap.add_argument("--league", action="append", choices=list(LEAGUES), help="repeatable; default top 5")
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--dry-run", action="store_true", help="list new matches and the events scan size, then stop")
    ap.add_argument("--upload", action="store_true", help="also upload to R2 (needs --r2-prefix)")
    ap.add_argument("--r2-prefix", help="R2 key prefix, e.g. 'staging'")
    ap.add_argument("--live", action="store_true", help="with --upload and no --r2-prefix: write to the bucket root the app reads")
    ap.add_argument("--since", default=SEASON_START, help="include seasons that started on/after this date (2025-08-01 adds 2025/26)")
    ap.add_argument("--refetch", action="store_true", help="ignore the cached BigQuery pull in out/_fetch")
    ap.add_argument("--overwrite", action="store_true", help="with --upload-local: replace objects that already exist")
    ap.add_argument("--upload-local", action="store_true", help="upload the parquet files already in --out (no BigQuery) and stop")
    args = ap.parse_args()
    if (args.upload or args.upload_local) and not (args.r2_prefix or args.live):
        ap.error("uploading needs --r2-prefix, or --live for the bucket root the API reads")
    if args.upload_local:
        store = R2MatchStore.from_env(key_prefix=args.r2_prefix)
        counts: dict[str, int] = {}
        for path in sorted(args.out.glob("event_data/*/*/*.parquet")):
            frame = pd.read_parquet(path)
            if args.overwrite:
                store.client.delete_object(Bucket=store.bucket, Key=build_event_object_key(
                    frame, frame["league"].iloc[0], frame["season"].iloc[0], str(frame["matchId"].iloc[0]),
                    key_prefix=args.r2_prefix))
            res = store.upload_match(frame, league=frame["league"].iloc[0], season=frame["season"].iloc[0],
                                     match_id=str(frame["matchId"].iloc[0]))
            counts[res.status] = counts.get(res.status, 0) + 1
        print(f"upload from {args.out}: {counts}")
        return

    args.out.mkdir(parents=True, exist_ok=True)
    state_path = args.out / STATE_FILE
    done = set(json.loads(state_path.read_text())) if state_path.exists() else set()

    client = bigquery.Client(project=args.project)
    played = list_played(client, args.league or DEFAULT_LEAGUES, args.since)
    new = played[~played.match_id.isin(done)]
    print(f"{len(played)} played matches this season, {len(done)} already synced, {len(new)} new")
    if new.empty:
        return

    team_map = load_team_map()
    unknown = sorted((set(new.home_team_id) | set(new.away_team_id)) - set(team_map))
    if unknown:
        names = client.query(
            f"SELECT id, name FROM `{DATASET}.teams` WHERE id IN ({','.join(repr(u) for u in unknown)})"
        ).to_dataframe()
        names.to_csv(args.out / "missing_teams.csv", index=False)
        print(f"{len(unknown)} teams have no legacy numeric id -> {args.out / 'missing_teams.csv'}; "
              "their matches are skipped until crosswalk_teams.csv gets rows for them")
        new = new[new.home_team_id.isin(team_map) & new.away_team_id.isin(team_map)]
    if new.empty:
        return

    ids = new.match_id.tolist()
    if args.dry_run:
        sql = f"SELECT * FROM `{DATASET}.match_events` WHERE match_id IN ({','.join(repr(i) for i in ids)})"
        est = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True)).total_bytes_processed
        print(f"dry run: events scan ~{est / 1e9:.1f} GB for {len(ids)} matches")
        print(new[["league", "season", "date", "match_id"]].to_string(index=False))
        return

    cache_dir = args.out / "_fetch"
    cached = None
    if all((cache_dir / f"{n}.parquet").exists() for n in ("events", "player_matches", "players")) and not args.refetch:
        cached = {n: pd.read_parquet(cache_dir / f"{n}.parquet") for n in ("events", "player_matches", "players")}
        if not set(ids) <= set(cached["events"].match_id):
            cached = None  # the cache does not cover every match we need now
    if cached is not None:
        data = cached
        print(f"  reusing cached BigQuery pull in {cache_dir} (no scan)")
    else:
        data = fetch(client, ids)
        cache_dir.mkdir(exist_ok=True)
        for n, frame_ in data.items():
            frame_.to_parquet(cache_dir / f"{n}.parquet", index=False)
    ev = data["events"]
    present = set(ev.match_id)
    pm = data["player_matches"]
    pl = data["players"].set_index("id")
    names = pl.known_name.fillna(pl["name"]).to_dict()

    store = None
    if args.upload:
        store = R2MatchStore.from_env(key_prefix=args.r2_prefix)

    failures = []
    for m in new.itertuples():
        if m.match_id not in present:
            print(f"  {m.date} {m.match_id}: no events published yet, will retry next run")
            continue
        try:
            gks = set(pm[(pm.match_id == m.match_id) & pm.saves.notna()].player_id)
            frame = process_match(
                ev[ev.match_id == m.match_id], match_id=m.match_id, league=m.league, season=m.season, date=m.date,
                home_team_id=m.home_team_id, away_team_id=m.away_team_id,
                home_score=int(m.home_score), away_score=int(m.away_score),
                players=names, goalkeeper_ids=gks, team_numeric=team_map,
                card_types=card_types_for(pm, m.match_id),
                player_minutes=dict(zip(pm[pm.match_id == m.match_id].player_id,
                                        pm[pm.match_id == m.match_id].mins_played.fillna(0))))
            for note in frame.attrs.get("lineup_warnings", []):
                print(f"  {m.date} {m.match_id}: {note}")
            key = build_event_object_key(frame, m.league, m.season, m.match_id)
            path = args.out / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(R2MatchStore._parquet_bytes(frame))  # same serialization as the R2 upload
            if store is not None:
                res = store.upload_match(frame, league=m.league, season=m.season, match_id=m.match_id)
                print(f"  {key}: {res.status}")
            else:
                print(f"  {key}: written locally")
            done.add(m.match_id)
        except Exception as exc:  # keep going; one bad match must not block the week
            failures.append((m.match_id, repr(exc)))
            print(f"  {m.date} {m.match_id}: FAILED {exc!r}")
    state_path.write_text(json.dumps(sorted(done)))
    if failures:
        (args.out / "failures.json").write_text(json.dumps(failures, indent=1))
        print(f"{len(failures)} failures -> {args.out / 'failures.json'}")


if __name__ == "__main__":
    main()
