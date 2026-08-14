"""Atomic, idempotent Cloudflare R2 storage for processed match files."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import boto3
from botocore.exceptions import ClientError
import pandas as pd
from dotenv import load_dotenv


DATA_DIR = Path(__file__).resolve().parent
ROOT_DIR = DATA_DIR.parent


def clean_key_part(value: object) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(value))


def match_id_text(value: object) -> str:
    text = str(value).strip()
    try:
        numeric = float(text)
        return str(int(numeric)) if numeric.is_integer() else text
    except (TypeError, ValueError):
        return text


def _key_root(prefix: str | None) -> str:
    normalized = str(prefix or "").strip().strip("/")
    return f"{normalized}/" if normalized else ""


def build_event_object_key(
    frame: pd.DataFrame,
    league: str,
    season: str,
    match_id: str,
    *,
    key_prefix: str | None = None,
) -> str:
    dates = pd.to_datetime(frame["startDate"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("match has no valid startDate")
    home_ids = frame.loc[frame["h_a"].astype(str).str.lower() == "h", "teamId"].dropna()
    away_ids = frame.loc[frame["h_a"].astype(str).str.lower() == "a", "teamId"].dropna()
    if home_ids.empty or away_ids.empty:
        raise ValueError("match has no resolvable home/away team IDs")
    scores = frame["ftScore"].dropna() if "ftScore" in frame.columns else pd.Series(dtype=object)
    score = scores.iloc[0] if not scores.empty else "NA"
    filename = "_".join(
        (
            dates.iloc[0].strftime("%Y-%m-%d"),
            clean_key_part(match_id_text(match_id)),
            clean_key_part(match_id_text(home_ids.iloc[0])),
            "vs",
            clean_key_part(match_id_text(away_ids.iloc[0])),
            clean_key_part(score),
        )
    )
    return (
        f"{_key_root(key_prefix)}event_data/{clean_key_part(league)}/"
        f"{clean_key_part(season)}/{filename}.parquet"
    )


@dataclass(frozen=True)
class R2UploadResult:
    status: str
    key: str
    bytes: int | None
    sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class R2MatchStore:
    def __init__(self, client: Any, bucket: str, *, key_prefix: str | None = None) -> None:
        self.client = client
        self.bucket = bucket
        self.key_prefix = str(key_prefix or "").strip().strip("/")

    @classmethod
    def from_env(cls, *, key_prefix: str | None = None) -> "R2MatchStore":
        load_dotenv(ROOT_DIR / ".env")
        load_dotenv(DATA_DIR / ".env")
        required = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY", "R2_SECRET_KEY", "R2_BUCKET")
        missing = [name for name in required if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing R2 configuration: {', '.join(missing)}")
        client = boto3.client(
            "s3",
            endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
            region_name="auto",
            aws_access_key_id=os.environ["R2_ACCESS_KEY"],
            aws_secret_access_key=os.environ["R2_SECRET_KEY"],
        )
        return cls(client, os.environ["R2_BUCKET"], key_prefix=key_prefix)

    def _exists(self, key: str) -> dict[str, Any] | None:
        promoted = False
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return None
            raise

    def find_match_key(self, league: str, season: str, match_id: str) -> str | None:
        prefix = (
            f"{_key_root(self.key_prefix)}event_data/{clean_key_part(league)}/"
            f"{clean_key_part(season)}/"
        )
        token = clean_key_part(match_id_text(match_id))
        pattern = re.compile(rf"^\d{{4}}-\d{{2}}-\d{{2}}_{re.escape(token)}_")
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = str(item.get("Key", ""))
                if pattern.match(key.rsplit("/", 1)[-1]):
                    return key
        return None

    @staticmethod
    def _parquet_bytes(frame: pd.DataFrame) -> bytes:
        serializable = frame.copy()
        for column in ("league", "season", "matchId", "teamName", "h_a", "ftScore", "teamId"):
            if column in serializable.columns:
                serializable[column] = serializable[column].fillna("").astype(str)
        # Direct scraper frames have not passed through SQLite's permissive
        # TEXT coercion. Normalize mixed object columns (for example cardType
        # contains both False and "Yellow") so PyArrow gets one stable type.
        object_columns = [
            column for column in serializable.columns
            if serializable[column].dtype == object
        ]
        for column in object_columns:
            values = serializable[column].dropna()
            value_types = {type(value) for value in values}
            has_container = any(
                isinstance(value, (dict, list, tuple, set)) for value in values
            )
            if len(value_types) <= 1 and not has_container:
                continue

            def text_value(value: object) -> object:
                if value is None or (not isinstance(value, (dict, list, tuple, set)) and pd.isna(value)):
                    return None
                if isinstance(value, set):
                    return json.dumps(sorted(value), separators=(",", ":"))
                if isinstance(value, (dict, list, tuple)):
                    return json.dumps(value, separators=(",", ":"), default=str)
                return str(value)

            serializable[column] = serializable[column].map(text_value)
        buffer = io.BytesIO()
        serializable.to_parquet(buffer, index=False)
        return buffer.getvalue()

    def upload_match(
        self,
        frame: pd.DataFrame,
        *,
        league: str,
        season: str,
        match_id: str,
    ) -> R2UploadResult:
        key = build_event_object_key(
            frame, league, season, match_id, key_prefix=self.key_prefix
        )
        existing = self._exists(key)
        if existing is not None:
            return R2UploadResult(
                status="already_exists",
                key=key,
                bytes=existing.get("ContentLength"),
                sha256=(existing.get("Metadata") or {}).get("sha256"),
            )

        payload = self._parquet_bytes(frame)
        digest = hashlib.sha256(payload).hexdigest()
        final_name = key.rsplit("/", 1)[-1]
        temp_key = f"{_key_root(self.key_prefix)}_ingestion_tmp/{uuid4().hex}/{final_name}"
        metadata = {
            "match-id": match_id_text(match_id),
            "league": clean_key_part(league),
            "season": clean_key_part(season),
            "sha256": digest,
        }
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=temp_key,
                Body=payload,
                ContentType="application/vnd.apache.parquet",
                Metadata=metadata,
            )
            temp_head = self.client.head_object(Bucket=self.bucket, Key=temp_key)
            if int(temp_head.get("ContentLength", -1)) != len(payload):
                raise RuntimeError("Temporary R2 upload size verification failed.")
            if (temp_head.get("Metadata") or {}).get("sha256") != digest:
                raise RuntimeError("Temporary R2 upload checksum metadata verification failed.")

            self.client.copy_object(
                Bucket=self.bucket,
                Key=key,
                CopySource={"Bucket": self.bucket, "Key": temp_key},
                Metadata=metadata,
                MetadataDirective="REPLACE",
                ContentType="application/vnd.apache.parquet",
            )
            promoted = True
            final_head = self.client.head_object(Bucket=self.bucket, Key=key)
            if int(final_head.get("ContentLength", -1)) != len(payload):
                raise RuntimeError("Final R2 object size verification failed.")
            if (final_head.get("Metadata") or {}).get("sha256") != digest:
                raise RuntimeError("Final R2 object checksum metadata verification failed.")
        except Exception:
            if promoted:
                try:
                    self.client.delete_object(Bucket=self.bucket, Key=key)
                except Exception:
                    pass
            raise
        finally:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=temp_key)
            except Exception:
                pass

        return R2UploadResult(status="uploaded", key=key, bytes=len(payload), sha256=digest)
