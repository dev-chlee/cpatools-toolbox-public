#!/usr/bin/env python3
"""스킬 런타임 venv 준비 (전 스킬 공통 템플릿, OS-aware).

정책:
- venv 는 소스 트리 밖에 둔다: ``$MY_SKILLS_VENV_ROOT/<skill>``
  기본값: Windows = ``D:/00_Infra/venvs/my-skills`` · 그 외(WSL/Linux) = ``/opt/data/venvs/my-skills``
  (``<skill>`` 는 폴더명에서 ``skill-`` 접두사를 뗀 이름)
- 설치 우선순위: ``requirements.lock`` > ``pyproject.toml`` (-e) > ``requirements.txt``
- 소스 트리 내부 ``.venv`` 는 호환용일 뿐 기본 생성하지 않는다.

사용:
    python scripts/setup_venv.py            # 외부 venv 생성 + 의존성 설치
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


def _venv_root() -> Path:
    env = os.environ.get("MY_SKILLS_VENV_ROOT")
    if env:
        return Path(env)
    if os.name == "nt":
        return Path("D:/00_Infra/venvs/my-skills")
    return Path("/opt/data/venvs/my-skills")


def _python_in(venv_dir: Path) -> Path:
    # OS-aware: Windows = Scripts/python.exe, Linux/WSL = bin/python
    return venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _run(cmd: list[str], cwd: Path) -> None:
    if subprocess.run(cmd, cwd=str(cwd)).returncode != 0:
        raise SystemExit(1)


def main() -> int:
    skill_root = Path(__file__).resolve().parents[1]
    skill_name = skill_root.name
    if skill_name.startswith("skill-"):
        skill_name = skill_name[len("skill-"):]

    ap = argparse.ArgumentParser(description=f"Setup runtime venv for {skill_root.name}")
    ap.add_argument("--venv", default=str(_venv_root() / skill_name),
                    help="venv 디렉토리 경로")
    ap.add_argument("--recreate", action="store_true", help="삭제 후 재생성")
    args = ap.parse_args()
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

    if (skill_root / "requirements.lock").exists():
        pip_install("-r", "requirements.lock")
    elif (skill_root / "pyproject.toml").exists():
        pip_install("-e", str(skill_root))
    elif (skill_root / "requirements.txt").exists():
        pip_install("-r", "requirements.txt")
    else:
        print("[WARN] 의존성 파일 없음 — 빈 venv 만 생성")

    print(f"[OK] venv ready: {venv_dir}")
    print(f"[OK] python: {py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
