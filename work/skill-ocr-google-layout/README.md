# ocr-google-layout

GCP **Document AI Layout Parser** 기반 PDF OCR 스킬. `inbox/` 폴더의 PDF를 배치 처리해
표·레이아웃 구조를 보존한 **HTML / Markdown** 으로 변환한다(스캔 문서·표 인식에 강함).

- 배치: `inbox/` 의 PDF를 파일 단위 독립 처리(한 건 실패가 전체를 막지 않음)
- 출력: `YYYY-MM-DD-HHMM_대표파일명/` (KST) 폴더에 `*.html` / `*.md`
- 15p 초과 대용량은 GCS 버킷 경유 batch 로 자동 처리

## 최초 설정 (GCP 필요)
이 스킬은 **GCP 프로젝트 + Document AI Layout Parser 프로세서 + 서비스 계정**이 필요하다.
개발 지식이 없어도 **AI(Claude)가 함께 설정**할 수 있도록 [`references/gcp-onboarding.md`](./references/gcp-onboarding.md)
에 단계별(명령어 포함) 온보딩 가이드가 있다 — Claude 에게 "이 스킬 온보딩 해줘"라고 하면 된다.

## 사용법·설정
운영 규칙·CLI·환경변수는 [`SKILL.md`](./SKILL.md) 참조(단일 기준). 문제 해결은
[`references/troubleshooting.md`](./references/troubleshooting.md).

## 라이선스
MIT
