# Changelog — dsd-to-xlsx

## 0.2.1 (2026-05-08)

### Added
- `dsd_to_xlsx_pipeline/tests/test_unit.py` — top-level API · 서브패키지 import · 버전 형식 · VerifyReport 자료구조 · CLI 진입점 sanity 5건

## 0.2.0 (2026-05-04)

### Initial public release
- DSD (DART 감사·검토보고서 포맷) → xlsx 단방향 변환
- ZIP + XML 파싱 (lxml), CP949 한글 파일명 자동 디코딩
- 재무제표 4종 + 주석 N개 + 숨김 메타시트 5종 (`_STRUCTURE`/`_META`/`_EXTRACTIONS`/`_ACODES`/`_CELLMAP`) 자동 생성
- 자동 검증 (`verify`): 재무제표 누락·주석 번호 빠짐·빈 시트·메타데이터 추출
- CLI: `dsd2xlsx`, `dsd2xlsx --batch`, `dsd2xlsx --verify`
- examples/: convert_one, convert_batch, verify_xlsx, test_self
- pip 일반 설치 + 단독 실행(install 없이) 모두 지원
