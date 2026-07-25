import os
import boto3
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

R2_ACCOUNT_ID = os.getenv("R2_ACCOUNT_ID")
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_BUCKET = os.getenv("R2_BUCKET")

# S3-compatible endpoint
ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Create S3 client
s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY
)

# List and delete all objects in the bucket
while True:
    objects = s3.list_objects_v2(Bucket=R2_BUCKET)
    if "Contents" not in objects:
        print("Bucket is already empty.")
        break

    for obj in objects["Contents"]:
        print(f"Deleting {obj['Key']}")
        s3.delete_object(Bucket=R2_BUCKET, Key=obj["Key"])

    # Handle pagination
    if not objects.get("IsTruncated"):
        break
