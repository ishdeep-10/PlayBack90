import pandas as pd
import s3fs
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")
ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Storage options for pandas
storage_options = {
    "key": R2_ACCESS_KEY,
    "secret": R2_SECRET_KEY,
    "client_kwargs": {"endpoint_url": ENDPOINT_URL},
}

# Initialize S3 filesystem
fs = s3fs.S3FileSystem(
    key=R2_ACCESS_KEY,
    secret=R2_SECRET_KEY,
    client_kwargs={"endpoint_url": ENDPOINT_URL},
)

# Object path in bucket
file_path = f"{R2_BUCKET}/event_data/premier-league/2024_25/1821330.parquet"

# Check and read file
if fs.exists(file_path):
    df = pd.read_parquet(f"s3://{file_path}", storage_options=storage_options)
    print("Column types:\n", df.dtypes)
    print("\nFirst 5 rows:\n", df.head())
else:
    print("File does not exist:", file_path)
