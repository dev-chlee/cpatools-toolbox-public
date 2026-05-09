# Changelog — revenue-tod

## 0.1.1 (2026-05-08)

### Added
- `tests/test_unit.py` — 파일 분류 우선순위·금액·날짜·문자열 매칭·Incoterms 단위 테스트 37건

## 0.1.0 (2026-05-04)

### Initial release
- 매출 Test of Details(TOD) 자동화
- 파일 분류 우선순위: 세금계산서 → 거래명세서 → POD → BL → CI → PO → INV/PL → OTHER
- 해외매출 6테스트: PO 주문 / Invoice 빌링 / 선적서류 인도 / Incoterms / POD 도착 / 금액 대조
- 국내매출 3테스트: 세금계산서 / 거래명세서 / 금액 종합 대조
- pdfplumber 텍스트 추출 + 거래처명 부분매칭 (법인격 변형 포함)
- Incoterms 자동 감지 (DAP/DDP/EXW/FOB/CIF 등)
- 3시트 워크페이퍼 자동 생성 (Summary / 해외매출 상세 / 국내매출 상세)
- Pass/Exception/Fail 색상 분류
