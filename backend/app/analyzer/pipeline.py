from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.analyzer.decoder import AudioDecodeError, decode_audio, probe_audio
from app.analyzer.metrics import compute_metrics
from app.schemas import AnalysisReport, TechnicalInfo
from app.scoring.scorer import score_analysis

ProgressCallback = Callable[[str], None]


def analyze_audio_file(
    file_path: Path,
    *,
    original_filename: str,
    file_size_bytes: int,
    progress_callback: ProgressCallback | None = None,
) -> AnalysisReport:
    def notify(stage: str) -> None:
        if progress_callback is not None:
            progress_callback(stage)

    notify("Reading metadata")
    metadata = probe_audio(file_path)

    technical_info = TechnicalInfo(
        original_filename=original_filename,
        stored_filename=file_path.name,
        extension=file_path.suffix.lower(),
        format_name=str(metadata["format_name"]),
        codec_name=str(metadata["codec_name"]),
        codec_long_name=metadata.get("codec_long_name"),
        sample_rate=int(metadata["sample_rate"]),
        channels=int(metadata["channels"]),
        duration_seconds=float(metadata["duration_seconds"]),
        bit_rate_kbps=float(metadata["bit_rate_kbps"]) if metadata.get("bit_rate_kbps") is not None else None,
        bits_per_sample=int(metadata["bits_per_sample"]) if metadata.get("bits_per_sample") is not None else None,
        channel_layout=metadata.get("channel_layout"),
        file_size_bytes=file_size_bytes,
    )

    notify("Decoding audio")
    samples = decode_audio(file_path, technical_info.channels)

    notify("Computing metrics")
    metrics, charts = compute_metrics(samples, technical_info)

    notify("Generating report")
    scored = score_analysis(metrics, technical_info)

    return AnalysisReport(
        report_id=uuid4().hex,
        created_at=datetime.now(timezone.utc),
        technical_info=technical_info,
        summary=scored.summary,
        categories=scored.categories,
        recommendations=scored.recommendations,
        charts=charts,
        metrics=metrics,
    )


__all__ = ["AudioDecodeError", "analyze_audio_file"]
