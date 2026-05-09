from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np


class AudioDecodeError(RuntimeError):
    """Raised when probing or decoding an audio file fails."""


def _run_command(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


def probe_audio(file_path: Path) -> dict[str, Any]:
    result = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-print_format",
            "json",
            str(file_path),
        ]
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise AudioDecodeError(f"ffprobe failed for {file_path.name}: {stderr}")

    payload = json.loads(result.stdout.decode("utf-8", errors="replace"))
    streams = payload.get("streams") or []
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if audio_stream is None:
        raise AudioDecodeError(f"No audio stream found in {file_path.name}")

    format_info = payload.get("format") or {}
    sample_rate = int(audio_stream.get("sample_rate") or 0)
    channels = int(audio_stream.get("channels") or 1)

    if sample_rate <= 0:
        raise AudioDecodeError(f"Invalid sample rate reported for {file_path.name}")

    bit_rate_raw = audio_stream.get("bit_rate") or format_info.get("bit_rate")
    bits_per_sample_raw = audio_stream.get("bits_per_raw_sample") or audio_stream.get("bits_per_sample")

    return {
        "format_name": str(format_info.get("format_name") or file_path.suffix.lstrip(".")),
        "codec_name": str(audio_stream.get("codec_name") or "unknown"),
        "codec_long_name": audio_stream.get("codec_long_name"),
        "sample_rate": sample_rate,
        "channels": channels,
        "duration_seconds": float(audio_stream.get("duration") or format_info.get("duration") or 0.0),
        "bit_rate_kbps": float(bit_rate_raw) / 1000.0 if bit_rate_raw else None,
        "bits_per_sample": int(bits_per_sample_raw) if bits_per_sample_raw not in (None, "0", 0) else None,
        "channel_layout": audio_stream.get("channel_layout"),
    }


def decode_audio(file_path: Path, channels: int) -> np.ndarray:
    result = _run_command(
        [
            "ffmpeg",
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(file_path),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "-acodec",
            "pcm_f32le",
            "-",
        ]
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise AudioDecodeError(f"ffmpeg decode failed for {file_path.name}: {stderr}")

    pcm = np.frombuffer(result.stdout, dtype=np.float32).copy()
    if pcm.size == 0:
        raise AudioDecodeError(f"Decoded audio for {file_path.name} is empty")

    remainder = pcm.size % channels
    if remainder:
        pcm = pcm[: pcm.size - remainder]

    samples = pcm.reshape(-1, channels)
    samples = np.nan_to_num(samples, copy=False)
    return samples
