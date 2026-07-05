---
name: land-price-query
title: 공시지가 조회
description: >
  부동산공시가격알리미(realtyprice.kr)에서 개별공시지가를 조회하고, 조회 결과 스크린샷(PNG)과 감사 워크페이퍼(엑셀)를
  자동 생성하는 스킬. 사용 시점: (1) 개별공시지가 조회가 필요할 때, (2) 토지 공시지가를 확인해야 할 때,
  (3) 부동산 공시가격 조회 결과를 감사 워크페이퍼로 정리할 때, (4) realtyprice.kr에서 지가를 검색할 때.
  "공시지가", "개별공시지가", "지가조회", "realtyprice", "부동산공시가격", "토지 공시가격", "땅값 조회",
  "토지 시세" 등의 표현이 나오면 이 스킬을 사용한다.
  토지 관련 감사절차에서 공시지가 확인이 필요한 맥락에서도 반드시 트리거한다.
  토지가 포함된 재무제표 감사, 자산실사, 담보물건 검토 등에서 공시지가를 조회할 때도 이 스킬을 사용한다.
category: audit
tags: [감사, 공시지가, 부동산, 토지]
version: 0.2.0
---

# 개별공시지가 조회 및 감사 워크페이퍼 생성

## 개요

이 스킬은 **부동산공시가격 알리미**(realtyprice.kr)의 개별공시지가를 조회하고, 결과를
**스크린샷 이미지(PNG)** 와 **감사 워크페이퍼(엑셀)** 로 자동 생성한다.

외부회계감사 시 토지의 공시지가 확인은 자산 실재성·평가 검증에 필수 절차다. 이 스킬은 조회부터
워크페이퍼 작성까지의 반복 작업을 자동화한다.

**실행 환경 = 로컬 전용(Windows 기본).** 사용자 PC(Claude Code)에서 완결된다. weasyprint·poppler·
특정 OS 폰트 절대경로에 의존하지 않는다. 역할 분리:
- **조회 데이터** = 표준 라이브러리 `urllib` 로 사이트 내부 API 직접 호출(빠르고 정확, 무인증).
- **스크린샷** = **Playwright(headless Chromium)** 로 realtyprice **실제 웹페이지**를 조작·캡처
  (재현물이 아니라 진짜 사이트 화면 — 감사 증빙).

## 전체 워크플로우

```
[입력: 토지 목록]
  → [query_api.py: realtyprice 내부 API 조회 (urllib, 무인증) → 데이터]
  → [render_screenshots.py: Playwright 로 실제 웹페이지 조회결과 화면 캡처 → PNG]
  → [create_excel.py: openpyxl 워크페이퍼(요약 + 물건별 상세 + 실제 스크린샷 임베드)]
  → [출력 저장]
```

세 스크립트는 `scripts/` 에 있다. LLM(스킬 구동자)은 아래 함수들을 순서대로 호출·조립하면 된다.

---

## 실행 환경 & 최초 준비 (스킬 구동 LLM 용)

이 스킬은 **사용자 로컬 PC(Claude Code, Windows 기본)** 에서 실행한다. 사용자는 보통 개발 지식이
없으므로, **구동 LLM 이 준비 단계를 대신 수행**한다.

**최초 1회 준비(LLM 이 확인·실행)**:
1. 의존성 설치 — 스킬 폴더에서 `python scripts/setup_venv.py` (스킬-로컬 `.venv` 생성 + 설치).
   또는 기존 환경에 `pip install -r requirements.lock`.
2. 스크린샷용 Chromium — `python -m playwright install chromium` (~130MB, 1회).
3. **인터프리터 주의**: `setup_venv.py` 로 만든 `.venv` 를 쓸 경우, 이후 모든 실행은 그 venv 의
   파이썬으로 한다 — Windows `\.venv\Scripts\python.exe ...`, Linux/macOS `.venv/bin/python ...`.
   맨 `python` 은 시스템 파이썬을 잡아 `ModuleNotFoundError` 가 날 수 있다(전역 설치라면 맨 `python` 무방).

실패 시 각 스크립트는 한국어로 원인·다음 행동을 안내한다(예: Chromium 미설치 → 설치 명령 제시).

---

## Step 1: 입력 파싱

토지 목록은 두 방식으로 받는다.

### A) 엑셀 파일 입력
업로드된 엑셀에서 토지 정보를 파싱한다:
- 소재지 (시/도, 시/군/구, 읍/면/동 — 한 셀 또는 분리)
- 지번 (본번, 부번 — 한 셀 또는 분리)
- 지번유형 (일반/산 — 명시 없으면 '일반')

컬럼명이 정확히 일치하지 않을 수 있으므로 유사 컬럼명("토지소재지", "주소", "소재지(도로명)" 등)을 매칭한다.

### B) 대화 중 직접 입력
"서울특별시 중구 충무로1가 24-2" 같은 자연어 주소를 시/도, 시/군/구, 읍/면/동, 본번, 부번으로 분리한다.

### 필수 확인 사항
조회 전 아래를 확보한다(없으면 사용자에게 확인):
- **감사대상회사명** (워크페이퍼 기재)
- **감사기준일** (예: 2025.12.31)
- **토지 목록**: 물건별 시/도, 시/군/구, 읍/면/동, 지번유형, 본번, 부번

---

## Step 2: API 로 공시지가 조회

브라우저 없이 realtyprice.kr 내부 AJAX 엔드포인트를 직접 호출한다(공개·무인증 GET). 캐스케이드
지역코드 조회(시도→시군구→읍면동)와 지번 조회를 `query_api.py`가 캡슐화한다.

### 사이트/엔드포인트 (참고 — 직접 다룰 필요 없음)
- 세션 쿠키: `GET /notice/gsindividual/search.htm`
- 지역코드: `GET /notice/bjd/searchBjdApi.bjd` (gubun = `''`/`sgg`/`eub`)
- 조회: `GET /notice/search/gsiSearchListApi.search`

### 조회 (권장 — 편의 함수)

```python
import sys
sys.path.insert(0, "<skill_path>/scripts")
from query_api import lookup

res = lookup("서울특별시", "중구", "충무로1가", 24, 2)   # (시도, 시군구, 동, 본번, 부번, 지번유형='일반')
# res = {
#   "addr": "서울특별시 중구 충무로1가 24-2",
#   "sido","sigungu","dong","jibun":"24-2","jibun_type":"일반",
#   "total_records": 37,
#   "rows": [ {"base_year":"2026","gakuka_w":"188,400,000","notice_ymd":"20260123",
#              "base_md":"01월01일","jibun":"24-2번지","addr":...}, ... ],  # 최신연도부터
#   "price_latest": 188400000, "latest_year": "2026",
# }
```

- **지역명 매칭**: `lookup`이 시/도→시/군/구→읍/면/동 목록을 API로 받아 이름 매칭한다(정확 일치 우선,
  유일한 부분 일치 폴백). 후보가 여럿이거나 없으면 `LandPriceError`에 선택지를 담아 던진다.
- **지번유형(san)**: `일반`(기본)·`산`·`가지번` 등. 함수 인자 `jibun_type`으로 전달.
- **본번/부번**: 정수로 넘기면 내부에서 4자리 0패딩 처리. 부번 없으면 생략(0).

### 배치 조회 (CLI)

```bash
python scripts/query_api.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 --bun1 24 --bun2 2
# 또는 stdin 배치:
echo '{"properties":[{"sido":"서울특별시","sigungu":"중구","dong":"충무로1가","bun1":24,"bun2":2}]}' \
  | python scripts/query_api.py
```

### 저수준 함수 (분구 등 수동 매칭이 필요할 때)
`open_session()`, `list_sido(opener)`, `list_sigungu(opener, sido_code)`,
`list_eub(opener, sido_code, sgg_code)`, `resolve_region(...)`, `query_price(...)` 를 직접 조합한다.

### 행정구역 변경 주의
행정구역이 바뀌면 사용자 입력 주소와 실제 목록이 다를 수 있다(분구·통합). `lookup`이 후보 다수/없음을
`LandPriceError`로 알리면, `list_eub()`로 실제 읍/면/동 목록을 확인해 올바른 구/동을 재선택한다.
(예: OO시 분구 → 'OO신구' 로 조회)

---

## Step 3: 실제 웹페이지 스크린샷 (Playwright)

realtyprice **실제 페이지**를 headless Chromium 으로 열어, 캐스케이드 드롭다운을 선택하고 지번을 입력해
사이트 조회를 실행한 뒤 결과 화면을 그대로 캡처한다. **재현물이 아니라 진짜 사이트 DOM 스크린샷**이다.

```python
from render_screenshots import capture

capture("서울특별시", "중구", "충무로1가", 24, 2, "./output/01_충무로1가_24-2.png")
# 시그니처: capture(sido, sigungu, dong, bun1, bun2=0, output_path=..., jibun_type="일반",
#                   full_page=True, headless=True, timeout=30000, scale=2)
```

- **지역코드 해석**: `capture` 내부에서 `query_api` 로 시/도·시/군/구·읍/면/동 코드를 얻어(사이트 select 의
  option value 와 동일) 실제 드롭다운을 선택한다. 지역 매칭 실패 시 `query_api.LandPriceError`.
- **full_page**: `True`(기본)=검색폼+총건수+결과 테이블 전체(증빙에 권장), `False`=결과영역(`#contents`) 크롭.
- **한글**: Chromium 이 OS 시스템 폰트로 렌더 → Windows 는 맑은 고딕 기본. 별도 폰트 설정 불필요.
- 조회 실행은 사이트 함수 `goPage(1)` 를 그대로 호출한다(검색 버튼과 동일 경로). 결과 렌더를 대기한 뒤 캡처.

### 배치 (CLI)
```bash
python scripts/render_screenshots.py --sido 서울특별시 --sigungu 중구 --dong 충무로1가 \
    --bun1 24 --bun2 2 --out ./output/01_충무로1가_24-2.png
# stdin 배치:
python scripts/render_screenshots.py < properties.json
# {"properties":[{"filename":"01_..png","sido":..,"sigungu":..,"dong":..,
#                 "bun1":24,"bun2":2,"jibun_type":"일반"}], "output_dir":"./output", "full_page":true}
```

> **Chromium 설치(1회)**: `python -m playwright install chromium` (~130MB). 미설치 시 캡처 단계에서
> 한국어로 설치 명령을 안내하며 실패한다 — 설치 후 재시도. (조회 데이터(Step 2)는 Chromium 없이도 동작한다.)

---

## Step 4: 엑셀 워크페이퍼 생성

`scripts/create_excel.py` 의 `create_workpaper(data)` 를 호출한다.

```python
from create_excel import create_workpaper

data = {
    "output_path": "./output/WP_공시지가_조회결과.xlsx",
    "img_dir": "./output",                     # 스크린샷 PNG 가 있는 폴더
    "company_name": "(주)OO",
    "audit_date": "2025.12.31",
    "query_date": "2026.03.24",
    "auditor_name": "홍길동 (공인회계사)",
    "properties": [{
        "seq": 1,
        "sido": "서울특별시", "sigungu": "중구", "dong": "충무로1가", "jibun": "24-2",
        "sheet_name": "충무로1가 24-2",
        "img_file": "01_충무로1가_24-2.png",   # img_dir 내 파일명
        "location_full": "서울특별시 중구 충무로1가 24-2",
        "price_latest": "188,400,000 원/㎡",
        "total_records": 37,
        "data": [
            # [년도(int), 소재지, 지번, 개별공시지가(int), 기준일자, 공시일자]
            [2026, "서울특별시 중구 충무로1가 24-2", "24-2번지", 188400000, "01월01일", "20260123"],
            # ... rows(최신연도부터). query_api rows 에서 gakuka_w 콤마 제거해 int 로.
        ],
    }],
    "notes": ["개별공시지가는 매년 1월 1일 기준으로 산정되며, 2026년분은 2026.01.23에 공시되었습니다."],
}
create_workpaper(data)
```

- `img_file` 이 `img_dir` 에 존재하면 물건 시트에 임베드된다(없으면 조용히 건너뜀 — Step 3 를 먼저 실행).
- 셀 자동 줄바꿈(wrap)은 꺼져 있다.

### 워크북 구조
**시트 1: 요약** — 감사정보(회사·기준일·수행일·수행자) + ① 조회 신청 내역 ② 조회처 ③ 스크린샷 안내
④ 결과 요약표(물건별 최신 공시지가·기준일·공시일·과거 건수).
**시트 2~N: 물건별 상세** — 소재지, 최신 공시지가(빨강 강조), 총 건수, 연도별 추이(최근 6개년), 캡처 이미지.

### 스타일
타이틀 남색(#1A5276)/흰글자, 헤더 연파랑(#D6E4F0), 최신연도 노랑(#FFFFDD), URL 파랑, 비고 회색 이탤릭.

---

## Step 5: 출력 저장

저장 루트는 config 우선순위로 결정한다:
1. 호출자가 출력 경로(JSON `output_dir`/`output_path`)를 지정 → 그 경로.
2. 환경변수 `OUTPUT_DIR` → 그 하위.
3. 없으면 기본: 호출 CWD 기준 `./output`.

산출물은 KST 타임스탬프 폴더(`YYYY-MM-DD-HHMM_공시지가조회`)에 정리한다. **이 폴더 생성은 스크립트가
자동으로 하지 않는다** — 구동 LLM 이 경로를 만들고 `output_dir`/`output_path` 로 넘긴다:
```
<출력루트>/YYYY-MM-DD-HHMM_공시지가조회/
├── WP_공시지가_조회결과.xlsx
├── 01_[동명]_[지번].png
├── 02_[동명]_[지번].png
└── ...
```
파일명: 이미지 `{순번:02d}_{읍면동}_{지번}.png`, 엑셀 `WP_공시지가_조회결과.xlsx`.

> 산출물(client 데이터)을 스킬 소스 트리 안에 쓰지 않는다. 트리 밖으로 빼려면 `OUTPUT_DIR` env 또는
> 호출자 JSON 경로로 외부 경로를 지정한다.

---

## 설정

우선순위: **JSON 지정 > 환경변수 > 기본값**. 환경변수는 `os.getenv` 로만 읽으며 `.env` 는
자동 로드하지 않는다(`.env.example` 은 참고용 템플릿; 값은 셸 env 로 전달).

| 변수 | 의미 | 필수 | 기본값 |
|---|---|---|---|
| OUTPUT_DIR | `render_screenshots.py` 스크린샷 출력 경로 | ✗ | ./output (호출 CWD 기준) |

- `render_screenshots.py`: 출력 경로는 JSON `output_dir` → `OUTPUT_DIR` env → `./output` 순.
- `create_excel.py`: 출력 경로는 JSON `output_path` **(필수 키)**. env/기본값 폴백 없음.
- 비밀값 없음 — 경로/플래그 전용.

### 외부 전제 (preflight)
- **Python deps**: `pip install -r requirements.lock` (또는 `requirements.txt`). 핵심: `openpyxl`, `pillow`, `playwright`.
  - Windows 표준 venv: `python scripts/setup_venv.py` (스킬-로컬 `.venv` 생성 + 의존성 설치).
- **Chromium(스크린샷 전용)**: `python -m playwright install chromium` (~130MB, 1회). weasyprint·poppler/pdftoppm 은
  더 이상 쓰지 않는다(과거 버전에서 제거). 조회 데이터(Step 2)는 Chromium 없이도 동작한다.
- **한글 폰트**: Chromium 이 OS 시스템 폰트로 렌더 → Windows 는 맑은 고딕 기본이라 추가 설치 불필요.
- **자격증명**: 없음(비밀값·API 키 없음).
- **network**: realtyprice.kr 로의 HTTPS 아웃바운드만 필요(조회 API + 스크린샷 페이지 로드).

---

## 에러 처리

### 지역 매칭 실패 / 결과 없음 (`LandPriceError`)
- `lookup`이 시/도·시/군/구·읍/면/동 매칭에 실패하면 예외 메시지에 **선택지 목록**을 담아 던진다 →
  그 목록에서 올바른 명칭을 골라 재조회한다.
- 행정구역 변경(분구·통합) 가능성을 먼저 의심한다. `list_eub(opener, sido, sgg)` 로 실제 동 목록을 확인.
- 지번은 맞는데 결과가 없으면 **지번유형(일반/산)** 과 **본번/부번** 을 재확인한다.

### 다수 물건 조회
- 물건마다 `lookup` 을 호출하고 결과를 즉시 변수/리스트에 저장해 중간 결과를 잃지 않는다.
- 배치 CLI(`query_api.py` stdin) 는 물건별 실패를 `{"error":...}` 로 담아 계속 진행한다(한 건 실패가 전체를 막지 않음).
- 5건 이상이면 진행상황을 사용자에게 알린다.

### 스크린샷 캡처 실패
- **Chromium 미설치**: `python -m playwright install chromium` 실행 후 재시도.
- **결과 렌더 타임아웃**: 네트워크 지연/사이트 변경 가능. `capture(..., timeout=60000)` 로 늘리거나,
  `headless=False` 로 실제 브라우저를 띄워 어느 단계에서 막히는지 확인한다.
- **네트워크 오류**: 회사 방화벽/프록시로 realtyprice.kr 접속이 막히면 조회·스크린샷 모두 실패한다.
  한국어 안내가 나오면 인터넷 연결·프록시를 확인한다.
- Chromium 설치가 끝내 불가하면 조회 데이터(Step 2)만으로 워크페이퍼를 만들 수 있다(이미지 없이).
