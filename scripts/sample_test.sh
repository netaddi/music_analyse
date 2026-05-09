#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"
. .venv/bin/activate

if [[ $# -eq 0 ]]; then
  cd backend
  pytest tests -q
  exit 0
fi

mkdir -p data/reports

for audio_file in "$@"; do
  if [[ ! -f "$audio_file" ]]; then
    echo "Missing file: $audio_file" >&2
    exit 1
  fi

  output_name="$(basename "${audio_file%.*}").json"
  python scripts/analyze_file.py "$audio_file" --output "data/reports/$output_name"
  echo "Wrote data/reports/$output_name"
done
