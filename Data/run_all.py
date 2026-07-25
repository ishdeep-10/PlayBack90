import subprocess
import requests
import sys
import os

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_discord_notification(webhook_url, message):
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL is not set; skipping Discord notification.")
        return

    data = {"content": message}
    try:
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Discord notification: {e}")

jobs = [
    #("england", "premier-league", "2025/2026"),
    #("spain", "laliga", "2025/2026"),
    #("italy", "serie-a", "2025/2026"),
    #("germany", "bundesliga", "2025/2026"),
    #("france", "ligue-1", "2025/2026"),
    ("international", "fifa-world-cup", "2026")
    #("europe", "champions-league", "2025/2026")
    #("england" , "league-one", "2024/2025")
]

success = True
summary = []
try:
    for country, league, season in jobs:
        print(f"Extracting: {country}, {league}, {season}")
        result = subprocess.run(
            ["python", "extract_opta_data.py", country, league, season,"auto"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            success = False
            summary.append(f"❌ {league} ({country}, {season}): FAILED\nError: {result.stderr}")
        else:
            # Parse number of matches processed from stdout
            lines = result.stdout.splitlines()
            processed_line = next((l for l in lines if "Number of matches to process:" in l), None)
            if processed_line:
                summary.append(f"✅ {league} ({country}, {season}): {processed_line.split(':')[-1].strip()} matches processed")
            else:
                summary.append(f"✅ {league} ({country}, {season}): Success (matches processed unknown)")

    # Run db_to_parquet
    print("Uploading to R2...")
    result = subprocess.run(["python", "db_to_parquet.py"], capture_output=True, text=True)
    if result.returncode != 0:
        success = False
        summary.append(f"❌ db_to_parquet.py: FAILED\nError: {result.stderr}")
    else:
        summary.append("✅ db_to_parquet.py: Success")

    # Generate season summary stats and upload to R2.
    # ORDER MATTERS: run after db_to_parquet AND after any model backfills
    # (backfill_{xg,xa,xgot,xpass,epv}_to_r2.py) — the default --source hybrid
    # overlays enriched R2 event parquets onto the full SQLite match list, so
    # running it before backfills drops those metrics from the season files.
    #print("Generating season stats...")
    #result = subprocess.run(["python", "generate_season_stats.py"], capture_output=True, text=True)
    #if result.returncode != 0:
    #    success = False
    #    summary.append(f"❌ generate_season_stats.py: FAILED\nError: {result.stderr}")
    #else:
    #    summary.append("✅ generate_season_stats.py: Success")

except Exception as e:
    success = False
    summary.append(f"❌ Pipeline crashed: {e}")

# Send Discord notification
if success:
    msg = "✅ **Pipeline Success!**\n" + "\n".join(summary)
else:
    msg = "❌ **Pipeline Failed!**\n" + "\n".join(summary)

print("Discord message length:", len(msg))
print("Discord message content:", msg)
send_discord_notification(DISCORD_WEBHOOK_URL, msg)
