# Test Report

Date: 2026-05-09

## Environment

- Host OS: Linux
- Python: 3.13.5
- ffmpeg: 7.1.3

## Automated Test Results

Command executed:

```bash
. .venv/bin/activate
cd backend
pytest tests -q
```

Observed result:

```text
9 passed in 3.10s
```

Coverage in the automated suite:

- `GET /healthz`
- `POST /api/analyze` plus job polling and report retrieval
- WAV analysis
- FLAC analysis
- MP3 analysis through ffmpeg decode
- Phase-inverted stereo detection
- Clipping detection
- DC offset detection
- Loudness chart finite-value regression coverage
- Saved report repair for legacy `null` chart values

## Manual Smoke Tests

Generated manual test asset:

- `data/manual-tests/manual-tone.wav`

CLI smoke test:

```bash
. .venv/bin/activate
python scripts/analyze_file.py data/manual-tests/manual-tone.wav --output data/manual-tests/manual-report.json
```

Result: completed successfully and wrote `data/manual-tests/manual-report.json`.

Live server smoke tests:

- `curl http://127.0.0.1:8018/healthz` returned `{"status":"ok"}`
- `GET /` returned the HTML document titled `Mix Analysis Console`
- Uploading `data/manual-tests/manual-tone.wav` through the live API completed successfully

Observed live API report summary for the generated sample:

- Overall score: `66.0`
- Risk level: `noticeable technical risk`
- Top issue: `Spectral Balance`

## VM Deployment Validation

Deployment target observed in this session:

- Hostname: `debian-vm`
- VM LAN IP: `192.168.2.10`

Deployment path used:

```bash
./scripts/deploy_systemd.sh
```

Observed runtime state after deployment:

- `systemctl is-enabled music-analysis.service` -> `enabled`
- `systemctl is-active music-analysis.service` -> `active`
- `ss -ltn` shows the service listening on `0.0.0.0:8018`

LAN-address validation:

- `curl --noproxy '*' http://192.168.2.10:8018/healthz` returned `{"status":"ok"}`
- `GET http://192.168.2.10:8018/` returned the HTML page titled `Mix Analysis Console`
- Uploading `data/manual-tests/manual-tone.wav` to `http://192.168.2.10:8018/api/analyze` completed successfully

Observed deployed report summary for the VM-hosted service:

- Job id: `f7543b7f4c7e4f55b0b0536cbd737dca`
- Report id: `0710e01a526846c3962887d006d5d07b`
- Overall score: `66.0`
- Risk level: `noticeable technical risk`
- Top issue: `Spectral Balance`

## Constraints During Validation

- The real-audio path from the development plan, `/Users/xiyang/Music/网易云音乐`, is not present in this Linux environment.
- Because that directory is unavailable here, the executed validation used synthetic and generated samples instead of the planned real library tracks.
- This shell environment exports an HTTP proxy. Requests to `192.168.2.10` required bypassing that proxy via `curl --noproxy '*'` or `httpx.Client(trust_env=False)` during LAN-address validation.
