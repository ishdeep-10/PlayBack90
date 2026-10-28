"""Give every club in the chosen Dribble360 competitions a numeric team id and a name the app can show.

The app keys on numeric teamIds (WhoScored's) and names them from TEAM_DICT. `crosswalk_teams.csv` covers the ~140
top-5/MLS clubs; this covers the rest:

  1. already in crosswalk_teams.csv           -> keep that id
  2. same name as an existing TEAM_DICT club  -> reuse that WhoScored id (keeps history and legacy R2 keys continuous)
  3. otherwise                                -> mint a stable id from the Dribble360 id (md5 into 10M..278M, above every WhoScored id)

Output (merged into the existing file, so ids never change between runs):
  Data/dribble360/team_registry.csv     d360_team_id, numeric_id, name, country_id, source
  apps/api/app/team_registry.json       {numeric_id: name} for clubs missing from TEAM_DICT (read by app.domain)

Run:  apps/api/.venv/bin/python Data/dribble360/build_team_registry.py <billing-project-id> [--league champions-league ...]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
import warnings
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "apps" / "api"))

from build_crosswalk import LEAGUES  # noqa: E402
from app.domain import TEAM_DICT as _APP_TEAM_DICT  # noqa: E402

DATASET = "dribble360.football_pro"
REGISTRY_CSV = HERE / "team_registry.csv"
REGISTRY_JSON = HERE.parents[1] / "apps" / "api" / "app" / "team_registry.json"
MINT_BASE = 10_000_000
# app.domain also loads our own team_registry.json; only genuine WhoScored ids count as legacy.
TEAM_DICT = {tid: name for tid, name in _APP_TEAM_DICT.items() if tid < MINT_BASE}
DEFAULT_LEAGUES = ["champions-league", "europa-league"]


# Spelling differences between Dribble360 and TEAM_DICT that name folding cannot bridge (checked by hand).
LEGACY_ALIASES = {"Slavia Praha": 349, "Bodø / Glimt": 439}


def fold(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name).translate(str.maketrans({"ø": "o", "Ø": "O"}))).encode("ascii", "ignore").decode().lower()
    return " ".join(text.replace(".", " ").replace("-", " ").split())


def mint_id(d360_id: str) -> int:
    return MINT_BASE + int(hashlib.md5(d360_id.encode()).hexdigest()[:7], 16)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--league", action="append", choices=list(LEAGUES), help="repeatable; default Champions + Europa League")
    ap.add_argument("--since", default="2026-01-01")
    args = ap.parse_args()
    ids = ",".join(repr(LEAGUES[k]) for k in (args.league or DEFAULT_LEAGUES))

    client = bigquery.Client(project=args.project)
    sql = f"""
        SELECT DISTINCT t.id AS d360_team_id, t.name, t.short_name, t.country_id
        FROM `{DATASET}.teams` t JOIN `{DATASET}.team_matches` tm ON tm.team_id = t.id
        JOIN `{DATASET}.matches` m ON m.id = tm.match_id JOIN `{DATASET}.seasons` s ON s.id = m.season_id
        WHERE s.league_id IN ({ids}) AND s.start_date >= DATE '{args.since}'
    """
    clubs = client.query(sql, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=int(2e9))).to_dataframe()

    crosswalk = pd.read_csv(HERE / "crosswalk_teams.csv", dtype={"ws_team_id": int, "d360_team_id": str})
    cross_id = dict(zip(crosswalk.d360_team_id, crosswalk.ws_team_id))
    legacy_by_name: dict[str, list[int]] = {}
    for tid, name in TEAM_DICT.items():
        legacy_by_name.setdefault(fold(name), []).append(tid)
    taken = set(TEAM_DICT) | set(cross_id.values())

    existing = pd.read_csv(REGISTRY_CSV, dtype={"d360_team_id": str}) if REGISTRY_CSV.exists() else pd.DataFrame(
        columns=["d360_team_id", "numeric_id", "name", "country_id", "source"])
    rows = {r.d360_team_id: r._asdict() for r in existing.itertuples(index=False)}
    ambiguous = []
    for c in clubs.itertuples(index=False):
        if c.d360_team_id in rows:
            continue
        if c.d360_team_id in cross_id:
            numeric, source = int(cross_id[c.d360_team_id]), "crosswalk"
        else:
            hits = ([LEGACY_ALIASES[c.name]] if c.name in LEGACY_ALIASES
                    else legacy_by_name.get(fold(c.name), []) or legacy_by_name.get(fold(c.short_name), []))
            if len(hits) == 1:
                numeric, source = hits[0], "team_dict"
            else:
                if len(hits) > 1:
                    ambiguous.append((c.name, hits))
                numeric, source = mint_id(c.d360_team_id), "minted"
        rows[c.d360_team_id] = {"d360_team_id": c.d360_team_id, "numeric_id": numeric, "name": c.name,
                                "country_id": c.country_id, "source": source}
    registry = pd.DataFrame(rows.values())
    dup = registry[registry.numeric_id.duplicated(keep=False)]
    if not dup.empty:
        sys.exit(f"numeric id collision, refusing to write:\n{dup.to_string()}")
    registry.to_csv(REGISTRY_CSV, index=False)

    names = {str(int(r.numeric_id)): r.name for r in registry.itertuples() if int(r.numeric_id) not in TEAM_DICT}
    REGISTRY_JSON.write_text(json.dumps(names, ensure_ascii=False, indent=0, sort_keys=True))
    print(f"{len(clubs)} clubs in {args.league or DEFAULT_LEAGUES}; registry now {len(registry)} rows")
    print(registry.source.value_counts().to_string())
    print(f"{len(names)} names written for the API -> {REGISTRY_JSON}")
    for name, hits in ambiguous:
        print(f"  ambiguous legacy name {name!r}: {hits} (minted instead)")


if __name__ == "__main__":
    main()
