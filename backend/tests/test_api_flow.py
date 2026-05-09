from __future__ import annotations

import io
import time

import numpy as np
import soundfile as sf
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.storage import report_path


def _make_wav_bytes(sample_rate: int = 48000, duration_seconds: float = 2.0) -> bytes:
    timeline = np.linspace(0.0, duration_seconds, int(sample_rate * duration_seconds), endpoint=False)
    left = 0.35 * np.sin(2.0 * np.pi * 220.0 * timeline)
    right = 0.28 * np.sin(2.0 * np.pi * 330.0 * timeline)
    stereo = np.column_stack([left, right]).astype(np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, stereo, sample_rate, format="WAV")
    return buffer.getvalue()


def test_api_upload_flow_completes() -> None:
    client = TestClient(app)
    wav_bytes = _make_wav_bytes()
    existing_uploads = {path.name for path in settings.upload_dir.glob("*")}

    response = client.post(
        "/api/analyze",
        files={"file": ("nested/path/integration.wav", wav_bytes, "audio/wav")},
    )

    assert response.status_code == 202
    job_id = response.json()["job_id"]

    report_id = None
    for _ in range(60):
        poll_response = client.get(f"/api/jobs/{job_id}")
        assert poll_response.status_code == 200
        payload = poll_response.json()
        if payload["status"] == "completed":
            report_id = payload["report_id"]
            break
        assert payload["status"] != "failed", payload.get("error")
        time.sleep(0.1)

    assert report_id is not None

    report_response = client.get(f"/api/reports/{report_id}")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["summary"]["overall_score"] > 0
    assert report["technical_info"]["extension"] == ".wav"
    assert report["technical_info"]["original_filename"] == "integration.wav"
    assert "waveform" in report["charts"]

    new_uploads = [path for path in settings.upload_dir.glob("*") if path.name not in existing_uploads]
    assert len(new_uploads) == 1
    assert new_uploads[0].suffix == ".wav"

    new_uploads[0].unlink(missing_ok=True)
    report_path(report_id).unlink(missing_ok=True)
