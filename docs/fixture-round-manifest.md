# Fixture round manifest

Round metadata can be bundled with the API:

```text
apps/api/app/data/fixture_rounds/{league}/{season}.json
```

Hosted seasons may alternatively include an authoritative `rounds.json` file
beside their match parquet files:

```text
event_data/{league}/{season}/rounds.json
```

Bundled metadata takes precedence, followed by the R2 manifest. The manifest is
the source of truth for matchweek and tournament-stage labels:

```json
{
  "version": 1,
  "rounds": [
    {
      "id": "matchweek-1",
      "label": "Matchweek 1",
      "stage": "Regular season",
      "order": 1,
      "match_ids": ["1901001", "1901002"]
    },
    {
      "id": "quarter-final",
      "label": "Quarter-final",
      "stage": "Knockout stage",
      "order": 2,
      "match_ids": ["1902001"]
    }
  ]
}
```

Every currently hosted match must occur exactly once in the manifest. The
manifest may retain assignments for matches whose parquet files have been
deleted. A missing, malformed, partial, or duplicate manifest falls back to
inferred rounds so that matches are never hidden. API responses expose
`metadata_source` as either `manifest` or `inferred`.

Inferred rounds are intended only for existing seasons without provider metadata.
They group fixtures chronologically, limit a round to four calendar days, and do
not allow the same team to appear twice in one round.

Round manifests must be generated or updated before event-data retention runs.
Deleting parquet files must not delete `rounds.json`, because season-wide round
numbers and postponed-match assignments cannot be reconstructed reliably from
the remaining dates.
