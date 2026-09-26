"""보관소 경로 해석.

원본은 허브(cpa-skills)의 templates/skill/cpa_storage.py 다. 스킬 저장소에서는 고치지 않는다 —
허브 `hub.py check` 가 사본이 원본과 같은지 대조한다.

실자료와 산출물은 저장소 밖 보관소에 둔다:
    <루트>/<스킬 폴더명>/{input,work,output,logs}/
자리를 정하는 순서: 실행 옵션 > 환경변수 CPA_SKILLS_STORAGE(루트) > ~/cpa-skills-data
쓰려는 곳이 git 저장소 안이면 거부한다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ENV = "CPA_SKILLS_STORAGE"
SLOTS = ("input", "work", "output", "logs")


class StorageError(RuntimeError):
    """쓰려는 곳이 git 저장소 안이다."""


def storage_root() -> Path:
    env = os.environ.get(ENV, "").strip()
    return Path(env).expanduser() if env else Path.home() / "cpa-skills-data"


def git_repo_of(path: str | os.PathLike) -> Path | None:
    """path 가 들어 있는 git 저장소 루트. 없으면 None."""
    p = Path(path).expanduser().resolve()
    for d in (p, *p.parents):
        if (d / ".git").exists():
            return d
    return None


def guard(path: str | os.PathLike) -> Path:
    """쓰려는 경로를 돌려준다. git 저장소 안이면 StorageError."""
    p = Path(path).expanduser()
    repo = git_repo_of(p)
    if repo is not None:
        raise StorageError(
            f"git 저장소 안에는 쓰지 않는다: {p} (저장소 {repo}). "
            f"실행 옵션으로 저장소 밖 경로를 주거나 환경변수 {ENV} 를 보관소 루트로 설정한다."
        )
    return p


def slot(skill: str, name: str, override: str | os.PathLike | None = None) -> Path:
    """스킬 보관소의 한 칸(input·work·output·logs). 옵션으로 준 경로가 있으면 그것을 쓴다.

    input 이 아닌 칸은 쓰는 자리라 git 저장소 안이면 거부한다. 없는 칸은 만든다
    (옵션으로 준 input 은 만들지 않는다 — 오타를 빈 폴더로 가리지 않게).
    """
    if name not in SLOTS:
        raise ValueError(f"보관소 칸은 {', '.join(SLOTS)} 중 하나다: {name}")
    p = Path(override).expanduser() if override else storage_root() / skill / name
    if name != "input":
        guard(p)
    if name != "input" or not override:
        p.mkdir(parents=True, exist_ok=True)
    print(f"[보관소] {name}: {p}", file=sys.stderr)
    return p
