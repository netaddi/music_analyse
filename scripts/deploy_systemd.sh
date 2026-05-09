#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="music-analysis.service"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

sudo install -m 0644 "$REPO_ROOT/deploy/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now music-analysis.service
sudo systemctl status --no-pager music-analysis.service