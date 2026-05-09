# Deployment Notes

This project ships as a single FastAPI service that also serves the browser UI from static files. The default port is `8018`.

## Local Docker Deployment

From the repository root:

```bash
cd deploy
docker compose up -d --build
```

The service binds to `0.0.0.0:8018` inside the container and maps to host port `8018`.

## Debian VM Deployment

Expected VM target from the development plan:

- Host: `192.168.2.10`
- User: `wangyin`
- Port: `8018`

Recommended deployment flow:

1. Install Docker and the Compose plugin on the VM.
2. Copy the repository to the VM.
3. Run `docker compose up -d --build` from `deploy/`.
4. Check `curl http://127.0.0.1:8018/healthz` on the VM.
5. Open `http://192.168.2.10:8018` from another machine on the LAN.

## Optional Push Script

The repository includes `scripts/deploy_vm.sh` as a convenience wrapper around `rsync` and `docker compose`. It expects SSH connectivity to the VM and does not embed credentials.

## Systemd Fallback

If Docker is not installed on the VM, use the checked-in unit file:

```bash
sudo install -m 0644 deploy/music-analysis.service /etc/systemd/system/music-analysis.service
sudo systemctl daemon-reload
sudo systemctl enable --now music-analysis.service
```

The service uses the repository-local virtual environment and binds to `0.0.0.0:8018`.

## Runtime Storage

- Upload cache: `data/uploads`
- Reports: `data/reports`

Both directories are mounted as a volume in the Docker Compose configuration.
The checked-in deployment defaults keep uploaded source files. Set `DELETE_UPLOAD_AFTER_ANALYSIS=true` in the runtime environment if you want uploads removed after processing.
