from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS, settings
from app.jobs import JobManager
from app.schemas import AnalysisReport, AnalyzeAcceptedResponse, JobState
from app.storage import ensure_storage_dirs, load_report

job_manager = JobManager()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        job_manager.shutdown()


app = FastAPI(title="Music Analysis", version="0.1.0", lifespan=lifespan)

ensure_storage_dirs()
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeAcceptedResponse, status_code=202)
async def analyze(file: UploadFile = File(...)) -> AnalyzeAcceptedResponse:
    safe_filename = Path(file.filename or "upload").name or "upload"
    suffix = Path(safe_filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload mp3, wav, or flac.")

    content_type = (file.content_type or "application/octet-stream").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported content type: {content_type}")

    destination = settings.upload_dir / f"{uuid4().hex}{suffix}"
    total_size = 0
    try:
        with destination.open("wb") as stream:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)
                if total_size > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file exceeds the configured size limit.")
                stream.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    job = job_manager.create_job(safe_filename)
    job_manager.submit(job.job_id, destination, safe_filename, total_size)
    return AnalyzeAcceptedResponse(job_id=job.job_id, status=job.status, stage=job.stage)


@app.get("/api/jobs/{job_id}", response_model=JobState)
def get_job(job_id: str) -> JobState:
    job = job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/reports/{report_id}", response_model=AnalysisReport)
def get_report(report_id: str) -> AnalysisReport:
    report = load_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/api/reports/{report_id}/json", response_model=AnalysisReport)
def get_report_json(report_id: str) -> AnalysisReport:
    return get_report(report_id)

