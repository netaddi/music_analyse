#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyse an audio file and print a structured JSON report.")
    parser.add_argument("file", type=Path, help="Path to an mp3, wav, or flac file")
    parser.add_argument("--output", type=Path, help="Optional file to write the JSON report to")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.file.exists():
        parser.error(f"File not found: {args.file}")

    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from app.analyzer.pipeline import analyze_audio_file

    report = analyze_audio_file(
        args.file,
        original_filename=args.file.name,
        file_size_bytes=args.file.stat().st_size,
    )
    payload = report.model_dump_json(indent=2)

    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
