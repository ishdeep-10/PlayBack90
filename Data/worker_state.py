"""Small operational SQLite state store for the remote ingestion worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
from typing import Iterable

from worker_schedule import ScheduledIngestion, utc_datetime


ACTIVE_PROVIDER_STATES = {"completed", "live", "upcoming", "unknown"}
RETRY_DELAYS = (
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
    timedelta(hours=12),
    timedelta(hours=24),
)


@dataclass(frozen=True)
class WorkerFixture:
    fixture_id: str
    provider_fixture_id: str
    league: str
    season: str
    home_team: str
    away_team: str
    kickoff_utc: datetime
    due_at: datetime
    provider_state: str
    status: str
    attempt_count: int
    next_retry_at: datetime | None
    source_match_id: str | None
    source_url: str | None
    r2_key: str | None
    last_error: str | None

    def as_scheduled_ingestion(self) -> ScheduledIngestion:
        return ScheduledIngestion(
            fixture_id=self.fixture_id,
            provider_fixture_id=self.provider_fixture_id,
            league=self.league,
            season=self.season,
            home_team=self.home_team,
            away_team=self.away_team,
            kickoff_utc=self.kickoff_utc,
            due_at=self.next_retry_at if self.status == "retry_scheduled" and self.next_retry_at else self.due_at,
            provider_state=self.provider_state,
        )


def _iso(value: datetime) -> str:
    return utc_datetime(value).isoformat()


def _optional_datetime(value: object) -> datetime | None:
    return utc_datetime(str(value)) if value else None


class WorkerStateStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_fixtures (
                    fixture_id TEXT PRIMARY KEY,
                    provider_fixture_id TEXT NOT NULL,
                    league TEXT NOT NULL,
                    season TEXT NOT NULL,
                    home_team TEXT NOT NULL,
                    away_team TEXT NOT NULL,
                    kickoff_utc TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    provider_state TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'scheduled',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    source_match_id TEXT,
                    source_url TEXT,
                    r2_key TEXT,
                    last_error TEXT,
                    claim_expires_at TEXT,
                    schedule_seen_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_worker_due ON worker_fixtures(status, due_at, next_retry_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_worker_league_season ON worker_fixtures(league, season)"
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> WorkerFixture:
        return WorkerFixture(
            fixture_id=str(row["fixture_id"]),
            provider_fixture_id=str(row["provider_fixture_id"]),
            league=str(row["league"]),
            season=str(row["season"]),
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
            kickoff_utc=utc_datetime(row["kickoff_utc"]),
            due_at=utc_datetime(row["due_at"]),
            provider_state=str(row["provider_state"]),
            status=str(row["status"]),
            attempt_count=int(row["attempt_count"]),
            next_retry_at=_optional_datetime(row["next_retry_at"]),
            source_match_id=row["source_match_id"],
            source_url=row["source_url"],
            r2_key=row["r2_key"],
            last_error=row["last_error"],
        )

    def upsert_schedule(
        self,
        fixtures: Iterable[ScheduledIngestion],
        *,
        seen_at: datetime | None = None,
    ) -> int:
        observed = utc_datetime(seen_at or datetime.now(timezone.utc))
        count = 0
        with self._connect() as connection:
            for fixture in fixtures:
                existing = connection.execute(
                    "SELECT kickoff_utc, status FROM worker_fixtures WHERE fixture_id = ?",
                    (fixture.fixture_id,),
                ).fetchone()
                kickoff_changed = bool(
                    existing and utc_datetime(existing["kickoff_utc"]) != fixture.kickoff_utc
                )
                current_status = str(existing["status"]) if existing else "scheduled"
                if current_status == "uploaded":
                    status = "uploaded"
                elif fixture.provider_state in {"cancelled", "postponed"}:
                    status = fixture.provider_state
                elif kickoff_changed or current_status in {"cancelled", "postponed"}:
                    status = "scheduled"
                else:
                    status = current_status
                clear_retry = (
                    kickoff_changed
                    or current_status in {"cancelled", "postponed"}
                    or status in {"cancelled", "postponed"}
                )
                connection.execute(
                    """
                    INSERT INTO worker_fixtures (
                        fixture_id, provider_fixture_id, league, season, home_team, away_team,
                        kickoff_utc, due_at, provider_state, status, schedule_seen_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fixture_id) DO UPDATE SET
                        provider_fixture_id=excluded.provider_fixture_id,
                        league=excluded.league,
                        season=excluded.season,
                        home_team=excluded.home_team,
                        away_team=excluded.away_team,
                        kickoff_utc=excluded.kickoff_utc,
                        due_at=excluded.due_at,
                        provider_state=excluded.provider_state,
                        status=excluded.status,
                        next_retry_at=CASE WHEN ? THEN NULL ELSE worker_fixtures.next_retry_at END,
                        last_error=CASE WHEN ? THEN NULL ELSE worker_fixtures.last_error END,
                        schedule_seen_at=excluded.schedule_seen_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        fixture.fixture_id,
                        fixture.provider_fixture_id,
                        fixture.league,
                        fixture.season,
                        fixture.home_team,
                        fixture.away_team,
                        _iso(fixture.kickoff_utc),
                        _iso(fixture.due_at),
                        fixture.provider_state,
                        status,
                        _iso(observed),
                        _iso(observed),
                        int(clear_retry),
                        int(clear_retry),
                    ),
                )
                count += 1
        return count

    def list_plannable(
        self,
        *,
        earliest: datetime,
        latest: datetime,
    ) -> list[WorkerFixture]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM worker_fixtures
                WHERE provider_state IN ('completed', 'live', 'upcoming', 'unknown')
                  AND status IN ('scheduled', 'retry_scheduled')
                  AND CASE WHEN status = 'retry_scheduled' THEN next_retry_at ELSE due_at END BETWEEN ? AND ?
                ORDER BY CASE WHEN status = 'retry_scheduled' THEN next_retry_at ELSE due_at END, fixture_id
                """,
                (_iso(earliest), _iso(latest)),
            ).fetchall()
        return [self._row(row) for row in rows]

    def claim_due(
        self,
        *,
        now: datetime | None = None,
        limit: int = 8,
        lease: timedelta = timedelta(minutes=30),
        earliest: datetime | None = None,
    ) -> list[WorkerFixture]:
        if limit <= 0:
            raise ValueError("claim limit must be greater than zero")
        current = utc_datetime(now or datetime.now(timezone.utc))
        expires = current + lease
        earliest_iso = _iso(earliest) if earliest is not None else None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE worker_fixtures
                SET status = 'retry_scheduled', next_retry_at = COALESCE(next_retry_at, due_at),
                    claim_expires_at = NULL, updated_at = ?
                WHERE status = 'claimed' AND claim_expires_at <= ?
                """,
                (_iso(current), _iso(current)),
            )
            rows = connection.execute(
                """
                SELECT * FROM worker_fixtures
                WHERE provider_state IN ('completed', 'live', 'upcoming', 'unknown')
                  AND status IN ('scheduled', 'retry_scheduled')
                  AND (? IS NULL OR CASE WHEN status = 'retry_scheduled' THEN next_retry_at ELSE due_at END >= ?)
                  AND CASE WHEN status = 'retry_scheduled' THEN next_retry_at ELSE due_at END <= ?
                ORDER BY CASE WHEN status = 'retry_scheduled' THEN next_retry_at ELSE due_at END, fixture_id
                LIMIT ?
                """,
                (earliest_iso, earliest_iso, _iso(current), limit),
            ).fetchall()
            fixture_ids = [str(row["fixture_id"]) for row in rows]
            if fixture_ids:
                placeholders = ",".join("?" for _ in fixture_ids)
                connection.execute(
                    f"UPDATE worker_fixtures SET status='claimed', claim_expires_at=?, updated_at=? WHERE fixture_id IN ({placeholders})",
                    (_iso(expires), _iso(current), *fixture_ids),
                )
            connection.commit()
            claimed = connection.execute(
                f"SELECT * FROM worker_fixtures WHERE fixture_id IN ({','.join('?' for _ in fixture_ids)})"
                if fixture_ids else "SELECT * FROM worker_fixtures WHERE 0",
                fixture_ids,
            ).fetchall()
        return sorted((self._row(row) for row in claimed), key=lambda item: (item.due_at, item.fixture_id))

    def claim_selected(
        self,
        fixture_ids: Iterable[str],
        *,
        now: datetime | None = None,
        lease: timedelta = timedelta(minutes=30),
    ) -> list[WorkerFixture]:
        """Claim explicit non-terminal fixtures for a controlled manual retry."""

        requested = tuple(dict.fromkeys(str(value) for value in fixture_ids if str(value)))
        if not requested:
            return []
        current = utc_datetime(now or datetime.now(timezone.utc))
        expires = current + lease
        placeholders = ",".join("?" for _ in requested)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                f"""
                SELECT * FROM worker_fixtures
                WHERE fixture_id IN ({placeholders})
                  AND provider_state IN ('completed', 'live', 'upcoming', 'unknown')
                  AND status IN ('scheduled', 'retry_scheduled', 'needs_attention')
                ORDER BY due_at, fixture_id
                """,
                requested,
            ).fetchall()
            claimed_ids = [str(row["fixture_id"]) for row in rows]
            if claimed_ids:
                claimed_placeholders = ",".join("?" for _ in claimed_ids)
                connection.execute(
                    f"UPDATE worker_fixtures SET status='claimed', claim_expires_at=?, updated_at=? "
                    f"WHERE fixture_id IN ({claimed_placeholders})",
                    (_iso(expires), _iso(current), *claimed_ids),
                )
            connection.commit()
            claimed = connection.execute(
                f"SELECT * FROM worker_fixtures WHERE fixture_id IN ({','.join('?' for _ in claimed_ids)})"
                if claimed_ids else "SELECT * FROM worker_fixtures WHERE 0",
                claimed_ids,
            ).fetchall()
        return sorted((self._row(row) for row in claimed), key=lambda item: (item.due_at, item.fixture_id))

    def mark_uploaded(
        self,
        fixture_id: str,
        *,
        r2_key: str,
        source_match_id: str,
        source_url: str,
        now: datetime | None = None,
    ) -> None:
        current = utc_datetime(now or datetime.now(timezone.utc))
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE worker_fixtures SET
                    status='uploaded', r2_key=?, source_match_id=?, source_url=?,
                    next_retry_at=NULL, last_error=NULL, claim_expires_at=NULL, updated_at=?
                WHERE fixture_id=?
                """,
                (r2_key, source_match_id, source_url, _iso(current), fixture_id),
            )

    def schedule_retry(
        self,
        fixture_id: str,
        error: str,
        *,
        now: datetime | None = None,
    ) -> datetime:
        current = utc_datetime(now or datetime.now(timezone.utc))
        with self._connect() as connection:
            row = connection.execute(
                "SELECT attempt_count FROM worker_fixtures WHERE fixture_id=?",
                (fixture_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown worker fixture: {fixture_id}")
            attempt = int(row["attempt_count"]) + 1
            delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
            retry_at = current + delay
            status = "needs_attention" if attempt > len(RETRY_DELAYS) + 3 else "retry_scheduled"
            connection.execute(
                """
                UPDATE worker_fixtures SET
                    status=?, attempt_count=?, next_retry_at=?, last_error=?,
                    claim_expires_at=NULL, updated_at=?
                WHERE fixture_id=?
                """,
                (status, attempt, _iso(retry_at), error[:2000], _iso(current), fixture_id),
            )
        return retry_at

    def next_action_at(self, *, earliest: datetime | None = None) -> datetime | None:
        earliest_iso = _iso(earliest) if earliest is not None else None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT MIN(action_at) AS action_at
                FROM (
                    SELECT CASE
                        WHEN status='retry_scheduled' THEN next_retry_at
                        ELSE due_at
                    END AS action_at
                    FROM worker_fixtures
                    WHERE provider_state IN ('completed', 'live', 'upcoming', 'unknown')
                      AND status IN ('scheduled', 'retry_scheduled')
                )
                WHERE ? IS NULL OR action_at >= ?
                """,
                (earliest_iso, earliest_iso),
            ).fetchone()
        return _optional_datetime(row["action_at"] if row else None)

    def get(self, fixture_id: str) -> WorkerFixture | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM worker_fixtures WHERE fixture_id=?", (fixture_id,)
            ).fetchone()
        return self._row(row) if row else None
