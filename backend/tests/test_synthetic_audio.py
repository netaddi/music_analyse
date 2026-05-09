from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.analyzer.pipeline import analyze_audio_file
from app.storage import load_report


def _write_audio(path: Path, data: np.ndarray, sample_rate: int) -> None:
    sf.write(path, data.astype(np.float32), sample_rate)


def _sine_stereo(sample_rate: int, duration_seconds: float, amplitude: float = 0.35) -> np.ndarray:
    timeline = np.linspace(0.0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    left = amplitude * np.sin(2.0 * np.pi * 220.0 * timeline)
    right = amplitude * np.sin(2.0 * np.pi * 330.0 * timeline)
    return np.column_stack([left, right]).astype(np.float32)


def _analyze(path: Path):
    return analyze_audio_file(path, original_filename=path.name, file_size_bytes=path.stat().st_size)


@pytest.mark.parametrize("suffix", [".wav", ".flac"])
def test_analysis_supports_lossless_formats(tmp_path: Path, suffix: str) -> None:
    sample_rate = 48000
    audio = _sine_stereo(sample_rate, 3.0)
    audio_path = tmp_path / f"tone{suffix}"
    _write_audio(audio_path, audio, sample_rate)

    report = _analyze(audio_path)

    assert report.technical_info.extension == suffix
    assert report.technical_info.channels == 2
    assert report.summary.overall_score > 0
    assert len(report.categories) == 10


def test_analysis_supports_mp3_via_ffmpeg(tmp_path: Path) -> None:
    sample_rate = 44100
    audio = _sine_stereo(sample_rate, 2.5)
    wav_path = tmp_path / "tone.wav"
    mp3_path = tmp_path / "tone.mp3"
    _write_audio(wav_path, audio, sample_rate)

    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(wav_path), str(mp3_path)],
        check=True,
    )

    report = _analyze(mp3_path)

    assert report.technical_info.extension == ".mp3"
    assert report.summary.overall_score > 0
    assert report.metrics["integrated_lufs"] < 0


def test_detects_phase_and_clipping_risks(tmp_path: Path) -> None:
    sample_rate = 48000
    timeline = np.linspace(0.0, 2.0, int(sample_rate * 2.0), endpoint=False)

    inverted = 0.4 * np.sin(2.0 * np.pi * 440.0 * timeline)
    phase_audio = np.column_stack([inverted, -inverted]).astype(np.float32)
    phase_path = tmp_path / "phase.wav"
    _write_audio(phase_path, phase_audio, sample_rate)

    clip_source = 1.25 * np.sin(2.0 * np.pi * 80.0 * timeline)
    clipped = np.clip(np.column_stack([clip_source, clip_source]), -1.0, 1.0).astype(np.float32)
    clip_path = tmp_path / "clip.wav"
    _write_audio(clip_path, clipped, sample_rate)

    phase_report = _analyze(phase_path)
    clip_report = _analyze(clip_path)

    phase_category = next(category for category in phase_report.categories if category.slug == "phase")
    clipping_category = next(category for category in clip_report.categories if category.slug == "clipping")

    assert phase_report.metrics["correlation"] <= -0.95
    assert phase_category.score < 60
    assert clip_report.metrics["sample_clipping_count"] > 0
    assert clipping_category.score < 75


def test_detects_dc_offset(tmp_path: Path) -> None:
    sample_rate = 48000
    audio = _sine_stereo(sample_rate, 2.0) + 0.05
    audio_path = tmp_path / "dc.wav"
    _write_audio(audio_path, audio, sample_rate)

    report = _analyze(audio_path)
    hygiene = next(category for category in report.categories if category.slug == "technical_hygiene")

    assert abs(report.metrics["dc_offset"]) >= 0.04
    assert hygiene.score < 90


def test_loudness_chart_values_are_finite_with_silence_edges(tmp_path: Path) -> None:
    sample_rate = 48000
    silence = np.zeros((sample_rate * 2, 2), dtype=np.float32)
    tone = _sine_stereo(sample_rate, 2.0)
    audio = np.vstack([silence, tone, silence])
    audio_path = tmp_path / "silence-edges.wav"
    _write_audio(audio_path, audio, sample_rate)

    report = _analyze(audio_path)

    loudness_values = [
        value
        for series in report.charts["loudness"].series
        for value in series.values
    ]
    assert loudness_values
    assert all(math.isfinite(value) for value in loudness_values)


def test_load_report_repairs_null_chart_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample_rate = 48000
    audio_path = tmp_path / "repair.wav"
    _write_audio(audio_path, _sine_stereo(sample_rate, 2.0), sample_rate)
    report = _analyze(audio_path)

    payload = report.model_dump(mode="json")
    payload["charts"]["loudness"]["series"][0]["values"][0] = None

    report_path = tmp_path / f"{report.report_id}.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    monkeypatch.setattr("app.storage.report_path", lambda report_id: report_path)

    repaired_report = load_report(report.report_id)

    assert repaired_report is not None
    assert repaired_report.charts["loudness"].series[0].values[0] == 0.0