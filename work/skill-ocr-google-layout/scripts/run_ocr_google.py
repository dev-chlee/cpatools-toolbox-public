#!/usr/bin/env python3
"""Standalone runner for skill-ocr-google-layout.

Prefers uv runtime from pyproject. Falls back to local virtualenv.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run standalone OCR (Google Layout Parser)")
    parser.add_argument("--file", "-f", nargs="+", help="PDF file path(s)")
    parser.add_argument("--dir", "-d", help="Directory containing PDFs")
    parser.add_argument("--gcs", "-g", help="GCS URI (gs://bucket/path)")
    parser.add_argument("--batch", "-b", help="Batch input GCS prefix")
    parser.add_argument("--batch-output", help="Batch output GCS prefix")
    parser.add_argument("--output", "-o", help="결과 폴더 (기본: 보관소 output)")
    parser.add_argument("--format", choices=["html", "md", "both"], default="both")
    parser.add_argument("--embed-images", action="store_true")
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--cache", default=None)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--no-parallel", action="store_true")
    parser.add_argument(
        "--save-response",
        action="store_true",
        help="검증 결과와 관계없이 원응답을 <base>_response.json 으로 남긴다 (src.main 에 전달)",
    )
    return parser


def _validate_inputs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not any([args.file, args.dir, args.gcs, args.batch]):
        parser.error("One of --file, --dir, --gcs, or --batch must be specified.")

    if args.file:
        for f in args.file:
            if not Path(f).exists():
                parser.error(f"File not found: {f}")

    if args.dir and not Path(args.dir).is_dir():
        parser.error(f"Directory not found: {args.dir}")

    if args.batch and not args.batch_output:
        parser.error("--batch-output is required when --batch is used.")


def _runtime_command() -> list[str]:
    # Prefer uv runtime from pyproject; fall back to a skill-local .venv,
    # else the current interpreter.
    if shutil.which("uv") and (SKILL_ROOT / "pyproject.toml").exists():
        return ["uv", "run", "python", "-m", "src.main"]

    # OS-aware skill-local venv (Windows = Scripts/python.exe, else bin/python).
    venv_python = SKILL_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv_python.exists():
        return [str(venv_python), "-m", "src.main"]

    return [sys.executable, "-m", "src.main"]


def _forwarded_cli_args(args: argparse.Namespace) -> list[str]:
    # 하위 실행은 스킬 루트에서 돌므로 로컬 경로는 호출 위치 기준 절대경로로 넘긴다.
    cli: list[str] = []

    if args.file:
        cli.extend(["--file", *map(os.path.abspath, args.file)])
    if args.dir:
        cli.extend(["--dir", os.path.abspath(args.dir)])
    if args.gcs:
        cli.extend(["--gcs", args.gcs])
    if args.batch:
        cli.extend(["--batch", args.batch, "--batch-output", args.batch_output])

    if args.output:
        cli.extend(["--output", os.path.abspath(args.output)])
    cli.extend(["--format", args.format, "--max-workers", str(args.max_workers)])

    if args.embed_images:
        cli.append("--embed-images")
    if args.chunk_size is not None:
        cli.extend(["--chunk-size", str(args.chunk_size)])
    if args.cache:
        cli.extend(["--cache", os.path.abspath(args.cache)])
    if args.no_parallel:
        cli.append("--no-parallel")
    if args.save_response:
        cli.append("--save-response")

    return cli


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_inputs(args, parser)

    if not (SKILL_ROOT / "src" / "main.py").exists():
        parser.error(f"Invalid skill layout. src/main.py not found: {SKILL_ROOT}")

    if not (SKILL_ROOT / ".env").exists():
        print("[WARN] .env not found in skill root. Set GCP env vars or create .env (see SKILL.md ## 설정).", file=sys.stderr)

    cmd = _runtime_command() + _forwarded_cli_args(args)

    try:
        completed = subprocess.run(cmd, cwd=str(SKILL_ROOT), check=False)
        return completed.returncode
    except FileNotFoundError as e:
        print(f"[ERROR] Runtime not available: {e}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
