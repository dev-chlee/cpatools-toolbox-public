# Changelog — registry-mortgage-analysis

## 0.1.1 (2026-05-08)

### Added
- `tests/test_unit.py` — `find_summary_section`, `parse_unique_id`, `parse_property_type`, `parse_location` 단위 테스트 13건

### Fixed
- `requirements.txt` — stdlib-only 표기 정정. 실제로 `pdfplumber>=0.10`, `openpyxl>=3.1` 의존

## 0.1.0 (2026-05-04)

### Initial release
- 부동산등기부등본 PDF 일괄 파싱 (pdfplumber)
- 표제부·갑구·을구·하단 요약 구조화
- 현행 근저당 추출 (말소 항목 제외, 하단 요약 기준)
- 공동담보목록 번호 정밀 파싱 (담보추가 케이스 처리)
- 공동담보 그룹핑 → 순 담보금액 산출
- 4시트 워크페이퍼 자동 생성 (근저당 상세 / 부동산 종합표 / 요약 / 담보금액 분석)
- 가압류·압류 현존 여부 감지 (하단 요약 기준)
- 회사명 키워드로 피감사회사 소유 여부 자동 판정
