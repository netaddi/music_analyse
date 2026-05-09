from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _get_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    project_root: Path
    backend_root: Path
    data_dir: Path
    upload_dir: Path
    report_dir: Path
    static_dir: Path
    max_upload_bytes: int
    report_points: int
    target_lufs: float
    recommended_true_peak_dbtp: float
    delete_upload_after_analysis: bool
    worker_count: int


def load_settings() -> Settings:
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    data_dir = Path(os.getenv("MUSIC_ANALYSIS_DATA_DIR", project_root / "data"))

    return Settings(
        project_root=project_root,
        backend_root=backend_root,
        data_dir=data_dir,
        upload_dir=data_dir / "uploads",
        report_dir=data_dir / "reports",
        static_dir=backend_root / "app" / "static",
        max_upload_bytes=int(os.getenv("MAX_UPLOAD_BYTES", str(300 * 1024 * 1024))),
        report_points=int(os.getenv("CHART_MAX_POINTS", "1200")),
        target_lufs=float(os.getenv("TARGET_LUFS", "-14.0")),
        recommended_true_peak_dbtp=float(os.getenv("RECOMMENDED_TRUE_PEAK_DBTP", "-1.0")),
        delete_upload_after_analysis=_get_bool("DELETE_UPLOAD_AFTER_ANALYSIS", False),
        worker_count=int(os.getenv("ANALYSIS_WORKERS", "2")),
    )


settings = load_settings()

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac"}
ALLOWED_CONTENT_TYPES = {
    "audio/flac",
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/wave",
    "audio/x-flac",
    "audio/x-wav",
    "application/octet-stream",
}
