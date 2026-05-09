#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE_TARGET="${1:-wangyin@192.168.2.10}"
REMOTE_DIR="${2:-~/music-analysis}"

ssh "$REMOTE_TARGET" "mkdir -p '$REMOTE_DIR'"

rsync -az \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'data' \
  "$REPO_ROOT/" "$REMOTE_TARGET:$REMOTE_DIR/"

ssh "$REMOTE_TARGET" "cd '$REMOTE_DIR/deploy' && docker compose up -d --build"
