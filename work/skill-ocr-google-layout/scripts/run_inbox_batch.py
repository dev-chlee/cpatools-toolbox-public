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
   - exit code 3 with a "*_verify_failed.json" report in the result folder
     (OCR 결과 검증 실패): count as failed, keep source PDF in inbox,
     keep the result folder and rename it with suffix "_검증실패".
     Exit code 3 without the report is treated as a general failure.
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
sys.path.insert(0, str(SKILL_ROOT))
from src import cpa_storage  # noqa: E402

RUNNER = SKILL_ROOT / "scripts" / "run_ocr_google.py"
SKILL = "skill-ocr-google-layout"
# run_ocr_google.py(src/main.py) 가 OCR 결과 검증 실패 때 돌려주는 종료 코드.
# 하위 프로세스 경계를 넘는 계약이라 공유 모듈 없이 여기서 고정한다.
VERIFY_FAILED_EXIT_CODE = 3
VERIFY_FAILED_SUFFIX = "_검증실패"


def default_inbox() -> str:
    """받은 PDF 폴더 기본값: 보관소 input/inbox."""
    return str(cpa_storage.slot(SKILL, "input") / "inbox")


def default_output_root() -> str:
    """배치 결과 폴더 기본값: 보관소 output."""
    return str(cpa_storage.slot(SKILL, "output"))


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


def _unique_path(parent: str, preferred_name: str) -> str:
    base = os.path.join(parent, preferred_name)
    target = base
    i = 2
    while os.path.exists(target):
        target = f"{base}_{i}"
        i += 1
    return target


def _unique_dir(parent: str, preferred_name: str) -> str:
    target = _unique_path(parent, preferred_name)
    os.makedirs(target, exist_ok=False)
    return target


def _rename_verify_failed_dir(file_dir: str) -> str:
    """검증 실패 폴더 이름 끝에 '_검증실패' 를 붙인다. 겹치면 _2, _3 … 를 붙인다."""
    parent = os.path.dirname(file_dir)
    name = os.path.basename(file_dir) + VERIFY_FAILED_SUFFIX
    target = _unique_path(parent, name)
    os.rename(file_dir, target)
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
    save_response: bool = False,
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
    if save_response:
        cmd.append("--save-response")

    # 하위 실행 출력은 UTF-8 로 고정해 읽는다. 콘솔 기본 인코딩(예: cp949)으로 읽으면 한글 메시지가
    # 깨지거나 읽기 스레드가 예외로 죽어 실패 사유가 빠진다. 읽을 수 없는 바이트는 \xNN 으로 남긴다.
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        cmd,
        cwd=str(SKILL_ROOT),
        check=False,
        capture_output=True,
        env=env,
        encoding="utf-8",
        errors="backslashreplace",
    )


def _print_safe(line: str) -> None:
    """현재 표준출력 인코딩으로 표시할 수 없는 문자를 \\xNN 같은 표기로 바꿔 찍는다.

    하위 실행 메시지 한 줄 때문에 일괄 처리 전체가 멈추지 않게 하기 위해서다.
    """
    encoding = getattr(sys.stdout, "encoding", None)
    if encoding:
        line = line.encode(encoding, errors="backslashreplace").decode(encoding)
    print(line)


def _cleanup_empty_dirs(inbox_dir: str) -> None:
    for root, dirs, _files in os.walk(inbox_dir, topdown=False):
        for d in dirs:
            p = os.path.join(root, d)
            try:
                if not os.listdir(p):
                    os.rmdir(p)
            except OSError:
                pass


def run(
    inbox_dir: str,
    output_root: str,
    fmt: str,
    embed_images: bool,
    max_workers: int,
    save_response: bool = False,
) -> dict:
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
            "verify_failed": 0,
        }

    batch_dir = _build_batch_dir(output_root, os.path.basename(pdfs[0]))

    total = len(pdfs)
    success = 0
    failed = 0
    verify_failed = 0

    for pdf_path in pdfs:
        stem = _safe_name(os.path.splitext(os.path.basename(pdf_path))[0])
        file_dir = _unique_dir(batch_dir, stem)

        completed = _run_single_pdf(
            pdf_path, file_dir, fmt, embed_images, max_workers, save_response=save_response
        )
        if completed.returncode == 0:
            _move_file_with_dedup(pdf_path, file_dir)
            success += 1
            continue

        failed += 1
        err_preview = (completed.stderr or completed.stdout or "").strip().splitlines()

        # 종료 코드 3만으로는 검증 실패라고 보지 않는다. Windows 에서는 네이티브 라이브러리의
        # 비정상 종료도 3으로 끝날 수 있다. 누락 목록 파일이 실제로 있을 때만 검증 실패로 센다.
        has_report = os.path.isdir(file_dir) and any(Path(file_dir).glob("*_verify_failed.json"))
        if completed.returncode == VERIFY_FAILED_EXIT_CODE and has_report:
            # 검증 실패: 원본은 inbox 에 두고, 결과 폴더는 지우지 않고 이름만 바꾼다.
            verify_failed += 1
            try:
                kept_dir = _rename_verify_failed_dir(file_dir)
                where = f"결과 폴더={kept_dir}"
            except OSError as exc:
                where = f"결과 폴더={file_dir} (이름 변경 실패: {exc})"
            detail = f" 상세={err_preview[-1]}" if err_preview else ""
            _print_safe(
                f"[ERROR] file={pdf_path} rc={completed.returncode} "
                f"msg=OCR 결과 검증 실패 - 원본은 inbox 에 남겨 둡니다. {where}{detail}"
            )
            continue

        note = ""
        if completed.returncode == VERIFY_FAILED_EXIT_CODE:
            note = " (종료 코드 3이지만 누락 목록 파일이 없어 일반 실패로 처리)"
        if err_preview:
            _print_safe(
                f"[ERROR] file={pdf_path} rc={completed.returncode}{note} msg={err_preview[-1]}"
            )
        else:
            _print_safe(f"[ERROR] file={pdf_path} rc={completed.returncode}{note}")

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
        "verify_failed": verify_failed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OCR2 inbox batch")
    parser.add_argument("--inbox", help="받은 PDF 폴더 (기본: 보관소 input/inbox)")
    parser.add_argument(
        "--output-root", help="시각별 배치 폴더를 만들 결과 루트 (기본: 보관소 output)"
    )
    parser.add_argument("--format", choices=["html", "md", "both"], default="both")
    parser.add_argument("--embed-images", action="store_true")
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--save-response",
        action="store_true",
        help="파일마다 run_ocr_google.py 에 --save-response 를 넘겨 원응답을 저장한다 (기본 꺼짐)",
    )
    args = parser.parse_args()
    # 하위 실행은 스킬 루트에서 돌므로 경로를 호출 위치 기준 절대경로로 넘긴다.
    try:
        inbox = os.path.abspath(args.inbox or default_inbox())
        output_root = os.path.abspath(
            cpa_storage.guard(args.output_root) if args.output_root else default_output_root()
        )
    except cpa_storage.StorageError as exc:
        parser.error(str(exc))

    result = run(
        inbox,
        output_root,
        args.format,
        args.embed_images,
        args.max_workers,
        save_response=args.save_response,
    )
    if result["total"] == 0:
        print("NO_FILES")
        return

    _print_safe(
        "DONE "
        f"total={result['total']} success={result['success']} failed={result['failed']} "
        f"file_moved={result['file_moved']} batch={result['batch_dir']} "
        f"verify_failed={result['verify_failed']}"
    )


if __name__ == "__main__":
    main()
