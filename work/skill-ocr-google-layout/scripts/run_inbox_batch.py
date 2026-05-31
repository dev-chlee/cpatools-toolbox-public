#!/usr/bin/env python3
"""Inbox batch runner for OCR2 (file-wise folder mode).

Workflow:
1) Scan all PDFs recursively under inbox.
2) Create one batch folder under output root:
     YYYY-MM-DD-HHMM_<대표파일명> (KST)
3) Process each PDF independently:
   - create per-file folder under batch dir
   - run OCR output into that folder
   - move source PDF into the same folder on success
   - keep source PDF in inbox on failure
4) Remove empty folders left in inbox.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
RUNNER = SKILL_ROOT / "scripts" / "run_ocr_google.py"
DEFAULT_WORK_ROOT = "/opt/data/_external/gd/hermes-mount/work"


def _work_root() -> str:
    return os.getenv("WORK_ROOT", DEFAULT_WORK_ROOT)


def _default_inbox() -> str:
    return os.getenv("OCR_INBOX_DIR") or os.path.join(_work_root(), "02_ocr", "_inbox")


def _default_output_root() -> str:
    return os.getenv("OCR_OUTPUT_ROOT") or os.path.join(_work_root(), "02_ocr")


def _apply_env_defaults(inbox_dir: str, output_root: str) -> None:
    os.environ.setdefault("WORK_ROOT", DEFAULT_WORK_ROOT)
    os.environ.setdefault("OCR_INBOX_DIR", inbox_dir)
    os.environ.setdefault("OCR_OUTPUT_ROOT", output_root)
    os.environ.setdefault("AGENT_CREDENTIALS_DIR", "/opt/data/credentials")


def _safe_name(name: str, max_len: int = 80) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣._-]", "_", name).strip("._-")
    if not s:
        s = "batch"
    return s[:max_len]


def _collect_pdfs(inbox_dir: str) -> list[str]:
    paths: list[str] = []
    for root, _dirs, files in os.walk(inbox_dir):
        for f in files:
            if f.lower().endswith(".pdf"):
                paths.append(os.path.join(root, f))
    return sorted(paths, key=lambda p: p.lower())


def _build_batch_dir(output_root: str, rep_file: str) -> str:
    kst = timezone(timedelta(hours=9))
    ts = datetime.now(kst).strftime("%Y-%m-%d-%H%M")
    rep = _safe_name(os.path.splitext(rep_file)[0])
    base = os.path.join(output_root, f"{ts}_{rep}")

    batch_dir = base
    i = 2
    while os.path.exists(batch_dir):
        batch_dir = f"{base}_{i}"
        i += 1

    os.makedirs(batch_dir, exist_ok=True)
    return batch_dir


def _unique_dir(parent: str, preferred_name: str) -> str:
    base = os.path.join(parent, preferred_name)
    target = base
    i = 2
    while os.path.exists(target):
        target = f"{base}_{i}"
        i += 1
    os.makedirs(target, exist_ok=False)
    return target


def _move_file_with_dedup(src_file: str, dst_dir: str) -> str:
    filename = os.path.basename(src_file)
    dst = os.path.join(dst_dir, filename)
    if not os.path.exists(dst):
        shutil.move(src_file, dst)
        return dst

    stem, ext = os.path.splitext(filename)
    i = 2
    while True:
        candidate = os.path.join(dst_dir, f"{stem}_{i}{ext}")
        if not os.path.exists(candidate):
            shutil.move(src_file, candidate)
            return candidate
        i += 1


def _run_single_pdf(
    pdf_path: str,
    output_dir: str,
    fmt: str,
    embed_images: bool,
    max_workers: int,
) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(RUNNER),
        "--file",
        pdf_path,
        "--output",
        output_dir,
        "--format",
        fmt,
        "--max-workers",
        str(max_workers),
    ]
    if embed_images:
        cmd.append("--embed-images")

    return subprocess.run(
        cmd,
        cwd=str(SKILL_ROOT),
        check=False,
        text=True,
        capture_output=True,
    )


def _cleanup_empty_dirs(inbox_dir: str) -> None:
    for root, dirs, _files in os.walk(inbox_dir, topdown=False):
        for d in dirs:
            p = os.path.join(root, d)
            try:
                if not os.listdir(p):
                    os.rmdir(p)
            except OSError:
                pass


def run(inbox_dir: str, output_root: str, fmt: str, embed_images: bool, max_workers: int) -> dict:
    _apply_env_defaults(inbox_dir, output_root)
    if not os.path.isdir(inbox_dir):
        raise FileNotFoundError(f"inbox not found: {inbox_dir}")
    if not RUNNER.exists():
        raise FileNotFoundError(f"runner not found: {RUNNER}")
    os.makedirs(output_root, exist_ok=True)

    pdfs = _collect_pdfs(inbox_dir)
    if not pdfs:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "batch_dir": None,
            "file_moved": 0,
        }

    batch_dir = _build_batch_dir(output_root, os.path.basename(pdfs[0]))

    total = len(pdfs)
    success = 0
    failed = 0

    for pdf_path in pdfs:
        stem = _safe_name(os.path.splitext(os.path.basename(pdf_path))[0])
        file_dir = _unique_dir(batch_dir, stem)

        completed = _run_single_pdf(pdf_path, file_dir, fmt, embed_images, max_workers)
        if completed.returncode == 0:
            _move_file_with_dedup(pdf_path, file_dir)
            success += 1
            continue

        failed += 1
        err_preview = (completed.stderr or completed.stdout or "").strip().splitlines()
        if err_preview:
            print(f"[ERROR] file={pdf_path} rc={completed.returncode} msg={err_preview[-1]}")
        else:
            print(f"[ERROR] file={pdf_path} rc={completed.returncode}")

        try:
            if os.path.isdir(file_dir) and not os.listdir(file_dir):
                os.rmdir(file_dir)
        except OSError:
            pass

    _cleanup_empty_dirs(inbox_dir)

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "batch_dir": batch_dir,
        "file_moved": success,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCR2 inbox batch")
    parser.add_argument(
        "--inbox",
        default=_default_inbox(),
        help="Inbox root (default: OCR_INBOX_DIR or WORK_ROOT/02_ocr/_inbox)",
    )
    parser.add_argument(
        "--output-root",
        default=_default_output_root(),
        help="Output root for timestamped batch folders (default: OCR_OUTPUT_ROOT or WORK_ROOT/02_ocr)",
    )
    parser.add_argument("--format", choices=["html", "md", "both"], default="both")
    parser.add_argument("--embed-images", action="store_true")
    parser.add_argument("--max-workers", type=int, default=4)
    args = parser.parse_args()

    result = run(args.inbox, args.output_root, args.format, args.embed_images, args.max_workers)
    if result["total"] == 0:
        print("NO_FILES")
        return

    print(
        "DONE "
        f"total={result['total']} success={result['success']} failed={result['failed']} "
        f"file_moved={result['file_moved']} batch={result['batch_dir']}"
    )


if __name__ == "__main__":
    main()
