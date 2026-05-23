---
name: sync-test-2026-05-23
title: Sync Test (2026-05-23)
description: |
  cpatools-toolbox v2 mirror 자동 sync 흐름 end-to-end 검증용 테스트 skill.
  회계실무 무관, 자동화 검증 후 폐기 예정.
category: utility
tags: [test, automation]
published: true
stabilizedAt: 2026-05-23
version: 0.0.1
---

# Sync Test Skill

cpatools-toolbox (private SSOT) → cpatools-toolbox-public (mirror) → cpatools.co.kr 자동 sync 흐름 검증용.

이 skill은 회계 실무와 무관하며, 자동화 검증 완료 후 `published: false` 토글 + 폴더 삭제 예정.

## 검증 목표

1. `published: true` skill이 SSOT main push 직후 자동으로 mirror에 push되는가
2. `catalog.json` 에 새 entry가 정확한 메타로 추가되는가
3. allowlist가 작동해 위험 파일이 차단되는가 (해당 사항 없음, 이 skill엔 안전한 파일만)
4. POST.md frontmatter `published: true`가 있으면 사이트 회고록 페이지가 자동 생성되는가
5. Vercel deploy hook이 호출돼 cpatools.co.kr 가 갱신되는가
6. `published: true → false` 토글 시 deletion guard 통과 + mirror에서 폴더 자동 삭제되는가

## 폐기 절차

검증 완료 후:
1. SKILL.md frontmatter `published: false` 변경 + main push → mirror에서 자동 삭제 검증
2. SSOT에서도 `git rm -r skills/sync-test-2026-05-23/` + commit + push (선택)
