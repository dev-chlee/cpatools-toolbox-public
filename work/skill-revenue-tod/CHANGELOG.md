# Changelog — revenue-tod

## 0.6.2 (2026-09-25)

### Changed
- `README.md` 머리의 저장소 운영 안내 줄을 뺀다(공개본에서는 맞지 않는 말이다).

## 0.6.1 (2026-09-25)

### Changed
- `AGENTS.md` 「공개 상태」에서 공개 여부 단정을 빼고, 공개는 허브가 정한다고 적는다.
- `.gitignore` 에 Orca 작업 폴더 `.orca/` 를 더하고, 머리 주석에서 이 PC 경로를 뺀다.

## 0.6.0 (2026-09-25)

### Changed
- 기본 경로를 저장소 밖 보관소로 옮김: 증빙 `<보관소>/input/evidence`, 결과 `<보관소>/output/tod_detailed_results.json`.
  `<보관소>` = `CPA_SKILLS_STORAGE/skill-revenue-tod`, 없으면 `~/cpa-skills-data/skill-revenue-tod`.
- 옛 환경변수 `EVIDENCE_DIR`·`OUTPUT_DIR` 를 없앰. 덮어쓰기는 `--evidence`·`--out` 옵션으로만.
- `tod_engine`·`tod_workpaper`·`llm_runner` 가 git 저장소 안 경로에는 쓰지 않는다(종료코드 2).

## 0.5.0 (2026-09-11)

### Changed
- 샘플 엑셀마다 소스 코드를 고치던 어댑터를 제거하고, Claude/Codex가 확인한 JSON mapping으로 여러 시트·하위표를 함께 읽는 범용 추출기로 교체.
- 판정은 외부 모델 연결 없이 현재 Claude/Codex 대화가 증빙 원문을 직접 읽어 작성하도록 실행 계약을 단순화.
- 증빙 폴더 탐색을 `<evidence>/<folder>` 우선 및 하위 트리의 고유 폴더명 탐색으로 일반화.

### Added
- 비어 있지 않은 통합문서에서 mapping 누락·0건 추출·필수값 누락·중복 표본을 명시적으로 실패 처리.
- 판정의 문서 ID·파일명·인용문이 실제 읽힌 OCR 본문과 일치하는지 검증.
- 증빙 없음·빈 폴더·읽을 수 있는 OCR 본문 없음이 최종 결과와 워크페이퍼에 보존되는 evidence gate.
- Excel 출력의 외부 문자열 수식 실행 방지와 출력 상위 디렉터리 자동 생성.
- 해외·국내·용역 3개 프로파일 전체 흐름을 포함한 71개 회귀 테스트.

## 0.2.0 (2026-06-18)

### Changed (아키텍처)
- **프로파일 구동으로 재설계.** 하드코딩된 `analyze_overseas_sample`/`analyze_domestic_sample` 을 단일 `analyze_sample(sample, folder, profile=None)` + 선언형 프로파일 레지스트리(`scripts/profiles.py`)로 통합. 새 매출유형은 `PROFILES` dict 추가로 확장(코드 본체 무수정).
- **회계전표 = 검증 대상**(샘플)으로 모델 정정 — 증빙 목록·분류에서 제외.
- 결과 스키마를 프로파일 제네릭(`profile`/`base`/`checks{id:{label,result,detail}}`)으로 변경. `tod_workpaper.py` 가 프로파일별 상세 시트를 검증 열까지 동적 생성.
- 종합 판정을 체크 criticality 기반으로 통일 — **국내매출도 세금계산서(critical) 부재 시 Fail**(이전엔 Exception).

### Added
- **용역매출 프로파일(`service`)** — 세금계산서·계약서 기반(물류증빙 없음). `check_contract`(거래처·계약금액·용역기간 귀속) 신규.
- 증빙 분류에 **계약서** 타입 추가(세금계산서·거래명세서 다음, 물류서류 앞).
- 프로파일 선택 = 매출유형 컬럼 우선(`TYPE_TO_PROFILE`/`select_profile`) + LLM/`--profile` 보정.
- `tod_engine.py` **CLI 인자화** — `<sample.xlsx> [--evidence] [--out] [--profile]` (flag > env > 기본). Windows cp949 콘솔 utf-8 재설정.
- **얼라인 프리플라이트**(`preflight_alignment`) — 증빙 폴더가 준비 안 된(없음/빈 폴더) 샘플을 검증 전에 식별해 사용자에게 정리를 요청(조용한 Fail 방지). 얼라인은 사용자 책임(샘플당 폴더 1개)임을 SKILL.md Phase 1.5 에 명시.

### Fixed
- `tests/test_unit.py` 를 **pytest 로 전면 변환**(기존 37 케이스 보존 + 프로파일 선택·계약서 분류·라우팅·용역 체크 신규, 총 50 케이스). 이전 자체하네스(top-level `sys.exit`)는 pytest 수집 시 크래시했음.
- README 정정 — 존재하지 않던 API(`extract`/`sample`/`write`) 제거, 실제 CLI·프로파일 반영, 설치경로 host-무관화.

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
