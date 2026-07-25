from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.schemas import ImportJobResponse
from app.services.matches import derive_match_context


IMPORT_JOB_TTL_SECONDS = 60 * 60
IMPORT_JOB_MAX_ITEMS = 24


@dataclass
class ImportJobState:
    job_id: str
    provider: str
    status: str = "queued"
    message: str | None = None
    error: str | None = None
    match_id: str | None = None
    data: pd.DataFrame | None = None
    created_at: float = 0.0
    updated_at: float = 0.0


class ImportJobStore:
    def __init__(self, ttl_seconds: int = IMPORT_JOB_TTL_SECONDS) -> None:
        self._jobs: dict[str, ImportJobState] = {}
        self._lock = threading.Lock()
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
        if len(self._jobs) <= IMPORT_JOB_MAX_ITEMS:
            return
        oldest = sorted(self._jobs, key=lambda item: self._jobs[item].updated_at)
        for job_id in oldest[: len(self._jobs) - IMPORT_JOB_MAX_ITEMS]:
            self._jobs.pop(job_id, None)

    def create(self, provider: str) -> ImportJobState:
        now = time.monotonic()
        job = ImportJobState(
            job_id=str(uuid.uuid4()),
            provider=provider,
            message=f"Queued {provider} import",
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._prune_locked()
            self._jobs[job.job_id] = job
        return job

    def update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            self._prune_locked()
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = time.monotonic()

    def get(self, job_id: str) -> ImportJobState | None:
        with self._lock:
            self._prune_locked()
            return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def to_response(self, job_id: str) -> ImportJobResponse:
        job = self.get(job_id)
        if not job:
            raise KeyError(job_id)

        context = None
        if job.data is not None and not job.data.empty:
            context = derive_match_context(job.data, file_path=None, source="import")

        return ImportJobResponse(
            job_id=job.job_id,
            provider=job.provider,
            status=job.status,  # type: ignore[arg-type]
            message=job.message,
            match_id=job.match_id,
            context=context,
            error=job.error,
        )


import_job_store = ImportJobStore()
