#!/usr/bin/env python3
"""공시지가 스킬의 가벼운 기본 환경과 선택 기능 설치.

정책:
- venv 위치는 각 사용자가 결정한다 (스킬은 강제하지 않음).
  기본값: 스킬 폴더 내 ``.venv``. 다른 위치는 ``--venv <경로>`` 로 지정.
- 기본은 openpyxl만 설치. 이미지 삽입·자동 캡처는 명시적 선택.
- 선택한 구성의 lock 파일이 있으면 사용하고, 없으면 공개용 txt 사용.

사용:
    python scripts/setup_venv.py            # 조회 + 엑셀
    python scripts/setup_venv.py --with-images   # 이미지 삽입 추가
    python scripts/setup_venv.py --with-capture  # 이미지 + 캡처 + headless shell
    python scripts/setup_venv.py --recreate # 재생성
    python scripts/setup_venv.py --venv <경로>
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _default_venv_dir(skill_root: Path) -> Path:
    # venv 위치는 사용자 책임. 기본은 스킬-로컬 .venv; 다른 위치는 --venv 로 지정.
    return skill_root / ".venv"


def _python_in(venv_dir: Path) -> Path:
    # OS-aware: Windows = Scripts/python.exe, Linux/WSL = bin/python
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(cmd: list[str], cwd: Path) -> None:
    if subprocess.run(cmd, cwd=str(cwd)).returncode != 0:
        raise SystemExit(1)


def _requirements_file(skill_root: Path, with_images=False, with_capture=False) -> Path:
    stem = 'requirements-capture' if with_capture else ('requirements-images' if with_images else 'requirements')
    for suffix in ('.lock', '.txt'):
        path = skill_root / (stem + suffix)
        if path.is_file():
            return path
    raise FileNotFoundError(f'설치 목록 없음: {stem}.lock 또는 {stem}.txt')


def main(argv=None) -> int:
    skill_root = Path(__file__).resolve().parents[1]

    ap = argparse.ArgumentParser(description='공시지가 기본 환경 설치 (조회 + 엑셀)')
    ap.add_argument("--venv", default=str(_default_venv_dir(skill_root)),
                    help="venv 디렉토리 경로 (기본: 스킬 폴더 .venv)")
    ap.add_argument("--recreate", action="store_true", help="삭제 후 재생성")
    ap.add_argument('--with-images', action='store_true', help='Pillow 추가: 기존 이미지 엑셀 삽입')
    ap.add_argument('--with-capture', action='store_true', help='이미지 삽입 + Playwright·headless shell 추가')
    args = ap.parse_args(argv)
    requirements = _requirements_file(skill_root, args.with_images, args.with_capture)
    venv_dir = Path(args.venv).expanduser()

    if args.recreate and venv_dir.exists():
        shutil.rmtree(venv_dir)
    if not venv_dir.exists():
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        if shutil.which("uv"):
            _run(["uv", "venv", str(venv_dir), "--python", sys.executable], skill_root)
        else:
            _run([sys.executable, "-m", "venv", str(venv_dir)], skill_root)

    py = _python_in(venv_dir)
    if not py.exists():
        print(f"[ERROR] venv python not found: {py}", file=sys.stderr)
        return 1

    use_uv = bool(shutil.which("uv"))

    def pip_install(*pargs: str) -> None:
        if use_uv:
            _run(["uv", "pip", "install", "--python", str(py), *pargs], skill_root)
        else:
            _run([str(py), "-m", "pip", "install", *pargs], skill_root)

    pip_install('-r', str(requirements))
    if args.with_capture:
        _run([str(py), '-m', 'playwright', 'install', '--only-shell', 'chromium'], skill_root)

    print(f"[OK] venv ready: {venv_dir}")
    print(f"[OK] python: {py}")
    if not args.with_capture:
        print('[OK] 브라우저 설치 생략. 자동 캡처가 필요하면 --with-capture를 사용하세요.')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
