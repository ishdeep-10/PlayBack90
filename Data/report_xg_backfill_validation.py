"""Summarize xG v2 backfill reports into a compact validation report.

Examples:
  apps/api/.venv/bin/python Data/report_xg_backfill_validation.py \
    --matches models/xg/v2/backfills/xg_backfill_v2_all-final-scan_matches.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "models" / "xg" / "v2" / "backfills" / "xg_backfill_validation_report.md"


def _round(value: float, digits: int = 3) -> float:
    return round(float(value), digits)


def _league_from_file(file_value: object) -> str:
    parts = str(file_value).split("/")
    try:
        return parts[parts.index("event_data") + 1]
    except (ValueError, IndexError):
        return "unknown"


def build_report(matches_path: Path, output_path: Path) -> dict:
    if not matches_path.exists():
        raise FileNotFoundError(f"Backfill matches CSV not found: {matches_path}")

    df = pd.read_csv(matches_path)
    if df.empty:
        raise RuntimeError(f"Backfill matches CSV is empty: {matches_path}")

    df["league"] = df["file"].map(_league_from_file)
    for column in ("shots", "old_xg", "new_xg", "delta_xg", "new_xg_missing", "changed_rows"):
        df[column] = pd.to_numeric(df.get(column, 0), errors="coerce").fillna(0)

    status_counts = df["status"].fillna("unknown").value_counts().to_dict() if "status" in df.columns else {}
    totals = {
        "source": str(matches_path),
        "files": int(len(df)),
        "shots": int(df["shots"].sum()),
        "old_xg": _round(df["old_xg"].sum()),
        "new_xg": _round(df["new_xg"].sum()),
        "delta_xg": _round(df["delta_xg"].sum()),
        "missing_new_xg": int(df["new_xg_missing"].sum()),
        "changed_rows": int(df["changed_rows"].sum()),
        "status_counts": {str(key): int(value) for key, value in status_counts.items()},
    }

    by_league = (
        df.groupby("league", dropna=False)
        .agg(
            files=("file", "count"),
            shots=("shots", "sum"),
            old_xg=("old_xg", "sum"),
            new_xg=("new_xg", "sum"),
            delta_xg=("delta_xg", "sum"),
            missing_new_xg=("new_xg_missing", "sum"),
        )
        .reset_index()
        .sort_values("league")
    )
    league_rows = [
        {
            "league": str(row.league),
            "files": int(row.files),
            "shots": int(row.shots),
            "old_xg": _round(row.old_xg),
            "new_xg": _round(row.new_xg),
            "delta_xg": _round(row.delta_xg),
            "missing_new_xg": int(row.missing_new_xg),
        }
        for row in by_league.itertuples(index=False)
    ]

    report = {"totals": totals, "by_league": league_rows}

    lines = [
        "# xG Backfill Validation",
        "",
        f"Source: `{matches_path}`",
        "",
        "## Totals",
        "",
        f"- Files: {totals['files']}",
        f"- Shots: {totals['shots']}",
        f"- Old xG: {totals['old_xg']:.3f}",
        f"- New xG: {totals['new_xg']:.3f}",
        f"- Delta xG: {totals['delta_xg']:+.3f}",
        f"- Missing new xG: {totals['missing_new_xg']}",
        f"- Changed rows: {totals['changed_rows']}",
        f"- Status counts: {totals['status_counts']}",
        "",
        "## By League",
        "",
        "| League | Files | Shots | Old xG | New xG | Delta | Missing new xG |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in league_rows:
        lines.append(
            f"| {row['league']} | {row['files']} | {row['shots']} | {row['old_xg']:.3f} | "
            f"{row['new_xg']:.3f} | {row['delta_xg']:+.3f} | {row['missing_new_xg']} |"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_path.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an xG backfill validation report.")
    parser.add_argument("--matches", type=Path, required=True, help="Backfill *_matches.csv file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Markdown output path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(args.matches, args.output)
    print(json.dumps(report["totals"], indent=2))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.json')}")


if __name__ == "__main__":
    main()
