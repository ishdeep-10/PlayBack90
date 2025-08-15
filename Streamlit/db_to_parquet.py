import os
import re
import sqlite3
import pandas as pd
import boto3
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load env variables
load_dotenv()

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
KEEP_WEEKS = int(os.getenv("KEEP_WEEKS", 8))  # default to 8 weeks

# ===== STEP 1: Connect to SQLite =====
conn = sqlite3.connect("playback90.db")
df = pd.read_sql_query("SELECT * FROM event_data WHERE league != 'premier-league'", conn)
conn.close()

# Parse dates
df["startDate"] = pd.to_datetime(df["startDate"], errors="coerce")

# ===== STEP 2: Enforce fixed schema to prevent PyArrow merge errors =====
string_cols = ["league", "season", "matchId", "teamName", "h_a", "ftScore", "teamId"]
for col in string_cols:
    if col in df.columns:
        df[col] = df[col].astype(str).fillna("")

# ===== STEP 3: Create R2 client =====
ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY
)

# ===== STEP 4: Upload Parquet files partitioned by league/season/startDate_matchId =====
for (league, season, matchId), sub_df in df.groupby(["league", "season", "matchId"]):
    # --- Skip if matchId or startDate is missing ---
    if pd.isna(matchId) or str(matchId).lower() == "nan":
        continue
    if sub_df["startDate"].isna().all():
        continue

    # Use first non-null startDate
    start_date_val = sub_df["startDate"].dropna().iloc[0]
    start_date_str = start_date_val.strftime("%Y-%m-%d")

    # Force string types
    for col in string_cols:
        if col in sub_df.columns:
            sub_df[col] = sub_df[col].astype(str).fillna("")

    # Identify home and away teams
    #home_team = sub_df.loc[sub_df["h_a"] == "h", "teamName"].iloc[0] if not sub_df.loc[sub_df["h_a"] == "h", "teamName"].empty else "Unknown"
    #away_team = sub_df.loc[sub_df["h_a"] == "a", "teamName"].iloc[0] if not sub_df.loc[sub_df["h_a"] == "a", "teamName"].empty else "Unknown"
    home_team_id = sub_df.loc[sub_df["h_a"] == "h", "teamId"].dropna().iloc[0] if not sub_df.loc[sub_df["h_a"] == "h", "teamId"].dropna().empty else "Unknown"
    away_team_id = sub_df.loc[sub_df["h_a"] == "a", "teamId"].dropna().iloc[0] if not sub_df.loc[sub_df["h_a"] == "a", "teamId"].dropna().empty else "Unknown"
    ft_score = sub_df["ftScore"].dropna().iloc[0] if not sub_df["ftScore"].dropna().empty else "NA"

    # Clean values for S3 keys
    def clean(val):
        return re.sub(r"[^A-Za-z0-9_-]", "_", str(val))

    try:
        matchId_val = float(matchId)
        if matchId_val.is_integer():
            matchId_str = str(int(matchId_val))
        else:
            matchId_str = str(matchId)
    except ValueError:
        matchId_str = str(matchId)

    matchId_str = clean(matchId_str)
    league_str = clean(league)
    season_str = clean(season)
    home_team_str = home_team_id
    away_team_str = away_team_id
    ft_score_str = clean(ft_score)

    # Include startDate, matchId, home, away, ftScore in filename
    key = f"event_data/{league_str}/{season_str}/{start_date_str}_{matchId_str}_{home_team_str}_vs_{away_team_str}_{ft_score_str}.parquet"

    # Write parquet to memory and upload
    buffer = io.BytesIO()
    sub_df.to_parquet(buffer, index=False)
    buffer.seek(0)

    s3.upload_fileobj(buffer, R2_BUCKET, key)
    print(f"Uploaded {key} to R2")

# ===== STEP 5: Cleanup old files =====
cutoff_date = datetime.utcnow() - timedelta(weeks=KEEP_WEEKS)
objects = s3.list_objects_v2(Bucket=R2_BUCKET, Prefix="event_data/")
files = objects.get("Contents", [])

for obj in files:
    last_modified = obj["LastModified"].replace(tzinfo=None)
    if last_modified < cutoff_date:
        print(f"Deleting {obj['Key']} (Last modified: {last_modified})")
        s3.delete_object(Bucket=R2_BUCKET, Key=obj["Key"])
