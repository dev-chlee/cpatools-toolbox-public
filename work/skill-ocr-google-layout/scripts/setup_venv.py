#!/usr/bin/env python3
"""Prepare runtime for skill-ocr-google-layout.

Policy:
- Default venv lives outside the skill source tree:
  /opt/data/venvs/my-skills/ocr-google-layout
- Source-tree .venv is compatibility-only and should not be created by default.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> None:
    completed = subprocess.run(cmd, cwd=str(cwd), check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def _default_venv() -> Path:
    root = Path(os.environ.get("MY_SKILLS_VENV_ROOT", "/opt/data/venvs/my-skills"))
    return root / "ocr-google-layout"


def _setup_with_venv(skill_root: Path, venv_dir: Path, recreate: bool) -> None:
    if recreate and venv_dir.exists():
        shutil.rmtree(venv_dir)

    if not venv_dir.exists():
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        # Prefer uv because the base Python in this container may not have ensurepip.
        if shutil.which("uv"):
            _run(["uv", "venv", str(venv_dir), "--python", sys.executable], cwd=skill_root)
        else:
            _run([sys.executable, "-m", "venv", str(venv_dir)], cwd=skill_root)

    python_bin = venv_dir / "bin" / "python"
    if not python_bin.exists():
        print(f"[ERROR] Python executable not found in venv: {python_bin}", file=sys.stderr)
        raise SystemExit(1)

    if shutil.which("uv"):
        if (skill_root / "pyproject.toml").exists():
            _run(["uv", "pip", "install", "--python", str(python_bin), "-e", str(skill_root)], cwd=skill_root)
        elif (skill_root / "requirements.txt").exists():
            _run(["uv", "pip", "install", "--python", str(python_bin), "-r", "requirements.txt"], cwd=skill_root)
    else:
        _run([str(python_bin), "-m", "pip", "install", "-U", "pip"], cwd=skill_root)
        if (skill_root / "pyproject.toml").exists():
            _run([str(python_bin), "-m", "pip", "install", "-e", "."], cwd=skill_root)
        elif (skill_root / "requirements.txt").exists():
            _run([str(python_bin), "-m", "pip", "install", "-r", "requirements.txt"], cwd=skill_root)
        else:
            print("[WARN] No pyproject.toml or requirements.txt found; venv created only.")

    print(f"[OK] venv ready: {venv_dir}")
    print(f"[OK] run with: {python_bin} -m src.main --help")


def main() -> int:
    parser = argparse.ArgumentParser(description="Setup runtime for skill-ocr-google-layout")
    parser.add_argument("--venv", default=str(_default_venv()), help="Virtualenv directory path")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate environment")
    args = parser.parse_args()

    skill_root = Path(__file__).resolve().parents[1]
    _setup_with_venv(skill_root, Path(args.venv).expanduser(), args.recreate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
