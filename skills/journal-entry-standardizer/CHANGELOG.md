# Changelog — journal-entry-standardizer

## 0.1.1 (2026-05-08)

### Fixed
- Windows cp949 콘솔에서 한글 출력 깨짐 — `sys.stdout/stderr.reconfigure(encoding='utf-8')` 적용 (test_unit, test_edge_cases)

### Maintenance
- requirements.txt 주석 명확화 (핵심 유틸은 stdlib만, openpyxl은 입출력용)

## 0.1.0 (2026-05-04)

### Initial release
- 다양한 ERP/회계 시스템 분개장을 표준 스키마로 통합
  - DOUZONE / SAP / Oracle / iCUBE / 이카운트 / 수동 엑셀 패턴
- 헤더 자동 분석(`analyze_header`): single_row / multi_row / subtotal_prefix / 차대분리·차대통합
- 필수헤더 7개 + 선택헤더 + 자동파생 컬럼 (연/월/분기/차변-대변)
- 전표번호 자동 합성 (원본 부재 시 `전표일자-순번`)
- 5단계 검증: 행수 / 차대합계 / 전표 차대균형 / COA 매핑 / 샘플 1:1
- COA 매핑 4단계 폴백 (직접 → 자릿수 보정 → 접두어 → 코드 범위)
- 단위 테스트 80건 + 엣지케이스 104건
