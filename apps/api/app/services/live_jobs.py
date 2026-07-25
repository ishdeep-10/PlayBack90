from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.schemas import LiveScrapeJobResponse
from app.services.matches import derive_match_context


LIVE_JOB_TTL_SECONDS = 60 * 60
LIVE_JOB_MAX_ITEMS = 24


@dataclass
class JobState:
    job_id: str
    status: str = "queued"
    message: str | None = None
    error: str | None = None
    match_id: str | None = None
    data: pd.DataFrame | None = None
    context: dict[str, Any] | None = field(default=None)
    created_at: float = 0.0
    updated_at: float = 0.0


class LiveScrapeJobStore:
    def __init__(self, ttl_seconds: int = LIVE_JOB_TTL_SECONDS) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._ttl_seconds = ttl_seconds

    def _prune_locked(self) -> None:
        now = time.monotonic()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.updated_at > self._ttl_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        if len(self._jobs) <= LIVE_JOB_MAX_ITEMS:
            return
        oldest = sorted(self._jobs, key=lambda item: self._jobs[item].updated_at)
        for job_id in oldest[: len(self._jobs) - LIVE_JOB_MAX_ITEMS]:
            self._jobs.pop(job_id, None)

    def create_job(self, url: str) -> JobState:
        job_id = str(uuid.uuid4())
        now = time.monotonic()
        job = JobState(job_id=job_id, message=f"Queued scrape for {url}", created_at=now, updated_at=now)
        with self._lock:
            self._prune_locked()
            self._jobs[job_id] = job
        return job

    def update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.monotonic()

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            self._prune_locked()
            return self._jobs.get(job_id)

    def submit(self, job_id: str, fn, *args, **kwargs) -> None:
        self._executor.submit(fn, job_id, *args, **kwargs)

    def to_response(self, job_id: str) -> LiveScrapeJobResponse:
        job = self.get_job(job_id)
        if not job:
            raise KeyError(job_id)

        context = None
        if job.data is not None and not job.data.empty:
            context = derive_match_context(job.data, file_path=None, source="live")

        return LiveScrapeJobResponse(
            job_id=job.job_id,
            status=job.status,  # type: ignore[arg-type]
            message=job.message,
            match_id=job.match_id,
            context=context,
            error=job.error,
        )


job_store = LiveScrapeJobStore()
