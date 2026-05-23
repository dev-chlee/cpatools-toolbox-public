---
name: rename-verify-2026-05-24
title: Rename Verify (2026-05-24)
description: |
  cpatools-toolbox → my-skills GitHub 리포 rename 후 자동 sync 흐름 정상 작동 검증용.
  검증 통과 시 즉시 published: false 토글 + 폴더 삭제 예정.
category: utility
tags: [test, rename]
published: true
stabilizedAt: 2026-05-24
version: 0.0.1
---

# Rename Verify

GitHub 리포 이름이 `cpatools-toolbox`에서 `my-skills`로 바뀐 후 자동 sync workflow가 정상 작동하는지 검증.

## 통과 기준

1. `git push origin main` 직후 workflow 자동 실행 (새 URL에서)
2. mirror(cpatools-toolbox-public)에 폴더 추가
3. catalog.json items += 1
4. Vercel deploy hook 호출
