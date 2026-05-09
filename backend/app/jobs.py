from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.analyzer.pipeline import AudioDecodeError, analyze_audio_file
from app.config import settings
from app.schemas import JobState
from app.storage import save_report


class JobManager:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=settings.worker_count, thread_name_prefix="analysis")
        self._jobs: dict[str, JobState] = {}
        self._lock = Lock()

    def create_job(self, original_filename: str) -> JobState:
        timestamp = datetime.now(timezone.utc)
        job = JobState(
            job_id=uuid4().hex,
            status="queued",
            stage="Queued",
            original_filename=original_filename,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> JobState | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job is not None else None

    def submit(self, job_id: str, file_path: Path, original_filename: str, file_size_bytes: int) -> None:
        self._executor.submit(self._run_job, job_id, file_path, original_filename, file_size_bytes)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs[job_id]
            payload = job.model_dump()
            payload.update(changes)
            payload["updated_at"] = datetime.now(timezone.utc)
            self._jobs[job_id] = JobState(**payload)

    def _run_job(self, job_id: str, file_path: Path, original_filename: str, file_size_bytes: int) -> None:
        def progress(stage: str) -> None:
            self._update(job_id, status="running", stage=stage)

        try:
            self._update(job_id, status="running", stage="Preparing analysis")
            report = analyze_audio_file(
                file_path,
                original_filename=original_filename,
                file_size_bytes=file_size_bytes,
                progress_callback=progress,
            )
            save_report(report)
            self._update(
                job_id,
                status="completed",
                stage="Completed",
                report_id=report.report_id,
                report_url=f"/api/reports/{report.report_id}",
            )
        except AudioDecodeError as exc:
            self._update(job_id, status="failed", stage="Failed", error=str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch for background jobs.
            self._update(job_id, status="failed", stage="Failed", error=f"Unexpected analysis failure: {exc}")
        finally:
            if settings.delete_upload_after_analysis and file_path.exists():
                file_path.unlink(missing_ok=True)
