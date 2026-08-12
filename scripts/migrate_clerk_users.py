"""One-off migration: import users exported from a Clerk Development instance
into the Production instance via the CreateUser Backend API, preserving
password hashes so users keep their existing password.

Usage:
    CLERK_SECRET_KEY_PROD=sk_live_... python scripts/migrate_clerk_users.py path/to/export.csv
"""

from __future__ import annotations

import csv
import os
import sys
import time

import httpx

CLERK_API_BASE = "https://api.clerk.com/v1"


def _split(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def migrate(csv_path: str, secret_key: str) -> None:
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    print(f"Found {len(rows)} users to migrate")

    created, skipped, failed = 0, 0, 0

    with httpx.Client(timeout=30) as client:
        for i, row in enumerate(rows, start=1):
            email_addresses = _split(row.get("verified_email_addresses", ""))
            if not email_addresses:
                email_addresses = _split(row.get("unverified_email_addresses", ""))
            if not email_addresses:
                print(f"[{i}/{len(rows)}] SKIP (no email): {row.get('id')}")
                skipped += 1
                continue

            payload: dict = {
                "email_address": email_addresses,
                "skip_password_checks": True,
                "skip_password_requirement": True,
            }
            if row.get("first_name"):
                payload["first_name"] = row["first_name"]
            if row.get("last_name"):
                payload["last_name"] = row["last_name"]
            if row.get("username"):
                payload["username"] = row["username"]
            if row.get("password_digest") and row.get("password_hasher"):
                payload["password_digest"] = row["password_digest"]
                payload["password_hasher"] = row["password_hasher"]

            resp = client.post(f"{CLERK_API_BASE}/users", headers=headers, json=payload)

            if resp.status_code in (200, 201):
                print(f"[{i}/{len(rows)}] OK: {email_addresses[0]}")
                created += 1
            elif resp.status_code == 422 and "already exists" in resp.text.lower():
                print(f"[{i}/{len(rows)}] SKIP (already exists): {email_addresses[0]}")
                skipped += 1
            else:
                print(f"[{i}/{len(rows)}] FAILED ({resp.status_code}): {email_addresses[0]} -> {resp.text}")
                failed += 1

            # Stay comfortably under Clerk's rate limit for this endpoint.
            time.sleep(0.5)

    print(f"\nDone. created={created} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/migrate_clerk_users.py path/to/export.csv")
        sys.exit(1)

    secret_key = os.environ.get("CLERK_SECRET_KEY_PROD")
    if not secret_key:
        print("Set CLERK_SECRET_KEY_PROD in the environment before running.")
        sys.exit(1)

    migrate(sys.argv[1], secret_key)
