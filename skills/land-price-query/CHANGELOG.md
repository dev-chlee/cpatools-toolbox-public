# Changelog — land-price-query

## 0.1.1 (2026-05-08)

### Added
- `tests/test_unit.py` — 모듈 import sanity, `create_workpaper` 호출 가능성, 한글 폰트 경로 상수 점검 (4건)

## 0.1.0 (2026-05-04)

### Initial release
- realtyprice.kr 개별공시지가 자동 조회 (Chrome 브라우저 자동화)
- 캐스케이드 드롭다운 (시도 → 시군구 → 읍면동) 자동 입력
- 행정구역 변경 (분구·통합) 대응
- 검색 결과 → HTML 재구성 → weasyprint → PNG 스크린샷
- 한글 폰트(DroidSansFallback.ttf) 안전 경로 사용
- 감사 워크페이퍼 엑셀 자동 생성 (요약 + 물건별 상세 + 이미지 임베드)
- 다수 물건 순차 조회 + 진행상황 보고
