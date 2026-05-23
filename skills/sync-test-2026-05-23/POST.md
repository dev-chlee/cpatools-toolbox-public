---
published: true
publishedAt: 2026-05-23
featured: false
---

# 3-repo 자동 sync 완성 — 첫 검증 회고

cpatools-toolbox (private SSOT) → cpatools-toolbox-public (mirror) → cpatools.co.kr 흐름이 처음으로 end-to-end 가동되는 순간을 위한 검증 글입니다.

## 동작 원리 요약

1. SSOT 의 `main` 브랜치에 push가 발생한다
2. GitHub Actions가 `sync-public-mirror.yml` workflow를 실행한다
3. `published: true` 표시된 skill만 staging에 모은다 (allowlist 적용, 위험 파일 차단)
4. `catalog.json` 을 생성한다 (schemaVersion: 1, sourceSha 포함)
5. mirror 리포의 트리를 통째로 교체 (deletion guard로 안전 점검)
6. Vercel deploy hook이 호출되어 cpatools.co.kr 가 1~3분 내 갱신된다

## 의도된 성질

- **단방향 복사**: mirror에서 SSOT로의 역동기화는 없다. mirror는 SSOT의 snapshot view일 뿐이다.
- **publish는 one-way door**: 한 번 mirror에 push된 콘텐츠는 git history에 영구 보존된다. `published: false`로 되돌려도 history 자체는 지워지지 않는다.
- **회고록 본문 게이트**: 이 POST.md 파일에 `published: true`가 있어야 사이트 회고록 페이지가 자동 생성된다.

## 검증 결과

이 글이 [cpatools.co.kr/tools/sync-test-2026-05-23](https://www.cpatools.co.kr/tools/sync-test-2026-05-23)에 자동 노출된다면 검증 성공.
