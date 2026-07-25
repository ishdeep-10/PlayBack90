"""Background match-report generation with optional AI narrative page."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ReportJob:
    job_id: str
    status: str = "queued"  # queued | running | completed | failed
    message: str | None = None
    pdf_bytes: bytes | None = None
    filename: str = "match-report.pdf"


class ReportJobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, ReportJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1)

    def create(self) -> ReportJob:
        job = ReportJob(job_id=str(uuid.uuid4()))
        with self._lock:
            self._jobs[job.job_id] = job
            if len(self._jobs) > 24:
                for key, existing in list(self._jobs.items()):
                    if existing.status in {"completed", "failed"} and len(self._jobs) > 24:
                        self._jobs.pop(key, None)
        return job

    def get(self, job_id: str) -> ReportJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            for key, value in changes.items():
                setattr(job, key, value)

    def submit(self, job_id: str, file_path: str) -> None:
        self._executor.submit(self._run, job_id, file_path)

    def _run(self, job_id: str, file_path: str) -> None:
        self.update(job_id, status="running", message="Rendering report pages…")
        try:
            from app.services.matches import get_match_by_file
            from app.services.visuals import build_match_report_pdf

            df, context = get_match_by_file(file_path)
            if df.empty:
                raise ValueError("match data not found")

            narrative = self._build_narrative(df, file_path)
            pdf_bytes = build_match_report_pdf(df, context, narrative=narrative)
            filename = f"{context.home_team}-vs-{context.away_team}-report.pdf".replace(" ", "-")
            self.update(job_id, status="completed", pdf_bytes=pdf_bytes, filename=filename, message="Report ready")
        except Exception as exc:
            logger.warning("report job %s failed", job_id, exc_info=True)
            self.update(job_id, status="failed", message=str(exc)[:200])

    def _build_narrative(self, df, file_path: str) -> str | None:
        """Optional AI match narrative; skipped silently when no API key."""
        try:
            from app.services import ai_analyst

            if not ai_analyst.insights_available():
                return None
            digest = ai_analyst.build_view_digest(df, "match-dynamics", None, file_path)
            cache_key = ai_analyst.make_cache_key(file_path, "report-narrative", None)
            return "".join(ai_analyst.stream_insights(digest, cache_key))
        except Exception:
            logger.warning("AI narrative generation failed; continuing without it", exc_info=True)
            return None


report_job_store = ReportJobStore()
