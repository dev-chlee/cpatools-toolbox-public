# Changelog — land-price-query

## 0.4.2 (2026-09-25)

### Changed
- `README.md` 머리의 저장소 운영 안내 줄을 뺀다(공개본에서는 맞지 않는 말이다).

## 0.4.1 (2026-09-25)

### Changed
- `AGENTS.md` 「공개 상태」에서 공개 여부 단정을 빼고, 공개는 허브가 정한다고 적는다.
- `.gitignore` 에 Orca 작업 폴더 `.orca/` 를 더하고, 머리 주석에서 이 PC 경로를 뺀다.
- 예시 규칙을 다듬는다: 고객·실제 소유자와 이어지는 이름·주소는 쓰지 않고, 널리 알려진 공시 필지는 조회 예시로 쓴다.

## 0.4.0 (2026-09-25)

### Changed — 기본 출력 경로를 저장소 밖 보관소로
- 허브 틀 `cpa_storage.py` 사본으로 경로 해석: JSON `output_dir`·CLI `--out` > `CPA_SKILLS_STORAGE` > `~/cpa-skills-data`
  아래 `skill-land-price-query/output`. 옛 기본값(호출 CWD 기준 `./output`)과 환경변수 `OUTPUT_DIR` 제거.
- `render_screenshots.py`(`capture`·CLI)와 `create_excel.py`(`create_workpaper`·CLI)가 git 저장소 안 출력 경로를
  거부한다(CLI 종료코드 2).
- 테스트 22건(보관소 경로 2건 추가, `tests/conftest.py` 로 실제 보관소 격리).

## 0.2.0 (2026-07-06)

### Changed — Windows 네이티브 포팅 (Cowork MCP·weasyprint·poppler 제거)
- **조회 데이터**: Chrome 브라우저 자동화(Cowork MCP) → 표준 라이브러리 `urllib` 로 realtyprice.kr 내부 API
  직접 호출(`query_api.py` 신규). 캐스케이드 지역코드 조회 + 지번 조회 + 지역명 매칭 캡슐화. 무인증 GET, 빠름.
- **스크린샷**: `weasyprint` + `pdftoppm`(poppler) + Linux 폰트 절대경로 → **Playwright(headless Chromium)**
  로 realtyprice **실제 웹페이지**를 조작·캡처하도록 재작성(`render_screenshots.py`). 재현물이 아니라 진짜
  사이트 DOM 스크린샷(감사 증빙). 한글은 OS 시스템 폰트(Windows 맑은 고딕)로 렌더.
- **엑셀**: 셀 자동 줄바꿈(wrap_text) 제거, 헤더 명시 개행 정리, 임베드 이미지 원본 비율 유지(세로 긴 캡처 대응).
- **의존성**: `weasyprint` 제거, `pillow`·`playwright` 추가. lock 재컴파일. (Chromium: `python -m playwright install chromium`)
- **문서/테스트**: SKILL.md·README 재작성(크로스플랫폼), 테스트를 pytest 로 정비(9건) + API/시그니처 단위 테스트.
- frontmatter: `category`/`tags`/`version` 추가.

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
