# Changelog — footing-verifier

## 0.2.0 (2026-05-08)

### Improved
- `analyze_workbook_basic` 메타 추출 정규식 4단계 폴백 도입.
  - period_current 누락률 89.6% → 6.5% (-93%, 77개 회귀 기준)
  - company 누락률 13.0% → 1.3% (-89%)
  - `_extract_company` / `_extract_periods` / `_extract_unit` 헬퍼로 분리

### Fixed
- 라벨 셀(`회사명: ___`) 형태에서 회사명 잘못 추출되는 케이스
- 날짜 표기 변종 (점·하이픈·슬래시) 미인식

## 0.1.0 (2026-05-04)

### Initial release
- BS / PL / CE / CF / 주석 풋팅 검증
- 시트간 교차검증 (BS↔주석, PL↔주석)
- 서술 검증 4종: 주석 참조 적절성, 항목번호 순서, 당기/전기 연도, 서술 내 수치 일치
- 검증결과요약 시트 + 하이퍼링크 자동 생성
- LibreOffice 재계산 통합 (선택, `--no-soffice`로 우회)
- 배치 검증 인프라 (`tests/batch_runner.py`) — N개 파일 L1 robustness
- L2 정확성 매핑 템플릿 (`tests/mappings/_template.py`)
