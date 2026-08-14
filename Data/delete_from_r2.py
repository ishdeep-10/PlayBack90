"""Deprecated: bucket-wide deletion has been intentionally disabled.

Use cleanup_retired_leagues.py, whose dry-run manifest, explicit confirmation,
SQLite backup, prefix scoping, and verification protect retained data.
"""

raise SystemExit(
    "Bucket-wide deletion is disabled. Use cleanup_retired_leagues.py (dry-run first)."
)
