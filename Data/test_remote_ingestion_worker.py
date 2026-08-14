from __future__ import annotations

from io import BytesIO

from botocore.exceptions import ClientError
import pandas as pd
import pytest

from ingestion_worker import match_id_from_url, run_match_worker
from r2_match_store import R2MatchStore, build_event_object_key
from worker_validation import MatchValidationError, validate_processed_match


def processed_match(match_id: str = "123456") -> pd.DataFrame:
    rows = []
    for index in range(60):
        home = index % 2 == 0
        rows.append(
            {
                "matchId": match_id,
                "eventId": index + 1,
                "teamId": "111" if home else "222",
                "teamName": "Inter Miami CF" if home else "Orlando City",
                "h_a": "h" if home else "a",
                "startDate": "2026-08-15T23:30:00Z",
                "period": "FirstHalf" if index < 30 else "SecondHalf",
                "type": "Pass",
                "ftScore": "2 : 1",
                "league": "Major League Soccer",
                "season": "2026",
                "cardType": "Yellow" if index == 4 else False,
                "xT": 0.1,
                "epv_added": 0.01,
                "xA": 0.0,
                "xPass": 0.8,
                "xG": 0.0,
                "xGOT": 0.0,
            }
        )
    return pd.DataFrame(rows)


class FakePaginator:
    def __init__(self, client):
        self.client = client

    def paginate(self, *, Bucket, Prefix):
        return [
            {
                "Contents": [
                    {"Key": key}
                    for key in sorted(self.client.objects)
                    if key.startswith(Prefix)
                ]
            }
        ]


class FakeR2Client:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator(self)

    def head_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError(
                {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "HeadObject",
            )
        item = self.objects[Key]
        return {"ContentLength": len(item["body"]), "Metadata": item["metadata"]}

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
        self.objects[Key] = {"body": bytes(Body), "metadata": dict(Metadata)}

    def copy_object(
        self,
        *,
        Bucket,
        Key,
        CopySource,
        Metadata,
        MetadataDirective,
        ContentType,
    ):
        source = self.objects[CopySource["Key"]]
        self.objects[Key] = {"body": source["body"], "metadata": dict(Metadata)}

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)
        self.objects.pop(Key, None)


def test_build_event_key_preserves_existing_r2_convention():
    key = build_event_object_key(processed_match(), "mls", "2026", "123456")

    assert key == "event_data/mls/2026/2026-08-15_123456_111_vs_222_2___1.parquet"


def test_validation_rejects_incomplete_match_coverage():
    frame = processed_match().query("period == 'FirstHalf'")

    with pytest.raises(MatchValidationError, match="both regulation halves"):
        validate_processed_match(frame, minimum_event_rows=20)


def test_validation_rejects_missing_enrichment_columns():
    frame = processed_match().drop(columns=["xPass"])

    with pytest.raises(MatchValidationError, match="missing enrichment columns: xPass"):
        validate_processed_match(frame)


def test_r2_upload_is_atomic_verified_and_idempotent():
    client = FakeR2Client()
    store = R2MatchStore(client, "playback90", key_prefix="ingestion-test")
    frame = processed_match()

    first = store.upload_match(frame, league="mls", season="2026", match_id="123456")
    second = store.upload_match(frame, league="mls", season="2026", match_id="123456")

    assert first.status == "uploaded"
    assert second.status == "already_exists"
    assert first.key == "ingestion-test/event_data/mls/2026/2026-08-15_123456_111_vs_222_2___1.parquet"
    assert first.sha256
    assert client.objects[first.key]["metadata"]["sha256"] == first.sha256
    assert client.deleted and not any("_ingestion_tmp" in key for key in client.objects)


def test_worker_canonicalizes_metadata_and_does_not_need_sqlite():
    client = FakeR2Client()
    store = R2MatchStore(client, "playback90", key_prefix="ingestion-test")

    result = run_match_worker(
        url="https://www.whoscored.com/Matches/123456/Live/usa-mls-miami-orlando",
        league="mls",
        season="2026",
        expected_home="Inter Miami",
        expected_away="Orlando City",
        key_prefix="ingestion-test",
        scraper=lambda url, **kwargs: processed_match(),
        store=store,
    )

    assert result.status == "uploaded"
    assert result.validation is not None
    assert result.validation.home_team == "Inter Miami CF"
    assert result.validation.metric_coverage["xPass"] == 60
    uploaded = pd.read_parquet(BytesIO(client.objects[result.key]["body"]))
    assert set(uploaded["league"]) == {"mls"}
    assert set(uploaded["season"]) == {"2026"}


def test_worker_skips_scrape_when_match_id_is_already_in_r2():
    client = FakeR2Client()
    existing_key = "event_data/mls/2026/2026-08-15_123456_111_vs_222_2___1.parquet"
    client.objects[existing_key] = {"body": b"existing", "metadata": {}}
    store = R2MatchStore(client, "playback90")
    called = False

    def scraper(url, **kwargs):
        nonlocal called
        called = True
        return processed_match()

    result = run_match_worker(
        url="https://www.whoscored.com/Matches/123456/Live/usa-mls-miami-orlando",
        league="mls",
        season="2026",
        scraper=scraper,
        store=store,
    )

    assert result.status == "already_exists"
    assert result.key == existing_key
    assert called is False


def test_match_id_is_parsed_case_insensitively():
    assert match_id_from_url("https://example.com/Matches/98765/Live/test") == "98765"
    assert match_id_from_url("https://example.com/no-match") is None
