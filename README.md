# Mix Analysis Console

Mix Analysis Console is a single-repo web tool for analyzing mix and mastering quality from uploaded `mp3`, `wav`, and `flac` files. The backend is implemented with FastAPI and serves a static browser UI directly, so there is no separate Node build step in this version.

## Features

- Upload `mp3`, `wav`, and `flac` files through the browser.
- Queue and process analysis jobs asynchronously.
- Retain uploaded source files by default under `data/uploads`.
- Inspect loudness, dynamics, clipping risk, stereo image, phase, spectral balance, low end, high-end harshness, noise, and technical hygiene.
- Review chart data for waveform, loudness, spectrum bands, and stereo correlation.
- Run the same analysis pipeline from the command line.

## Local Setup

System packages required on Debian-like systems:

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3.13-venv python3-dev build-essential ffmpeg ripgrep libsndfile1
```

Create the environment and install the backend in editable mode:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ./backend[dev]
```

Start the local service:

```bash
. .venv/bin/activate
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8018
```

Open the browser at `http://127.0.0.1:8018`.

## Command-Line Usage

Run the analyzer directly against a local file:

```bash
. .venv/bin/activate
python scripts/analyze_file.py /path/to/file.wav --output data/report.json
```

Uploads received through the web UI are kept by default in `data/uploads`. Set `DELETE_UPLOAD_AFTER_ANALYSIS=true` if you want the server to clean them up after each job.

## Tests

Run the backend tests:

```bash
. .venv/bin/activate
cd backend
pytest tests -q
```

Or use the helper script:

```bash
./scripts/sample_test.sh
```

## Docker Deployment

Build and run with Docker Compose:

```bash
cd deploy
docker compose up -d --build
```

The service is exposed on port `8018`.

## Systemd Deployment

When Docker is unavailable on the target VM, install and run the app directly with systemd:

```bash
sudo install -m 0644 deploy/music-analysis.service /etc/systemd/system/music-analysis.service
sudo systemctl daemon-reload
sudo systemctl enable --now music-analysis.service
```

Check service status:

```bash
systemctl status music-analysis.service
curl http://127.0.0.1:8018/healthz
```

## Known Limits

- Genre-specific thresholds are not implemented yet.
- Source separation is intentionally out of scope for the current release.
- Job state is stored in memory, while completed reports are persisted as JSON.
- The real-audio directory referenced in the planning document was not available in the current Linux workspace, so validation here uses synthetic and generated samples instead.
- Remote VM deployment assets are included, but the VM itself was not reachable from this session for a live rollout.
