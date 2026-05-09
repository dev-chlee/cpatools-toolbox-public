---
name: land-price-query
published: true
title: 공시지가 조회
description: >
  부동산공시가격알리미(realtyprice.kr)에서 개별공시지가를 조회하고, 조회 결과 스크린샷(PNG)과 감사 워크페이퍼(엑셀)를
  자동 생성하는 스킬. 사용 시점: (1) 개별공시지가 조회가 필요할 때, (2) 토지 공시지가를 확인해야 할 때,
  (3) 부동산 공시가격 조회 결과를 감사 워크페이퍼로 정리할 때, (4) realtyprice.kr에서 지가를 검색할 때.
  "공시지가", "개별공시지가", "지가조회", "realtyprice", "부동산공시가격", "토지 공시가격", "땅값 조회",
  "토지 시세" 등의 표현이 나오면 이 스킬을 사용한다.
  토지 관련 감사절차에서 공시지가 확인이 필요한 맥락에서도 반드시 트리거한다.
  토지가 포함된 재무제표 감사, 자산실사, 담보물건 검토 등에서 공시지가를 조회할 때도 이 스킬을 사용한다.
---

# 개별공시지가 조회 및 감사 워크페이퍼 생성

## 개요

이 스킬은 Chrome 브라우저를 통해 **부동산공시가격 알리미**(realtyprice.kr)에서 개별공시지가를 조회하고,
조회 결과를 **스크린샷 이미지(PNG)**와 **감사 워크페이퍼(엑셀 파일)**로 자동 생성한다.

외부회계감사 시 토지의 공시지가 확인은 자산 실재성·평가 검증에 필수적인 절차이다.
이 스킬은 조회부터 워크페이퍼 작성까지의 반복 작업을 자동화하여 감사 효율성을 높인다.

## 전체 워크플로우

```
[입력: 토지 목록] → [Chrome으로 realtyprice.kr 조회] → [결과 데이터 수집]
  → [스크린샷 이미지 렌더링 (weasyprint)] → [엑셀 워크페이퍼 생성 (openpyxl)] → [출력 저장]
```

---

## Step 1: 입력 파싱

토지 목록은 두 가지 방식으로 받을 수 있다.

### A) 엑셀 파일 입력
사용자가 업로드한 엑셀에서 토지 정보를 파싱한다:
- 소재지 (시/도, 시/군/구, 읍/면/동이 하나의 셀 또는 분리된 셀)
- 지번 (본번, 부번이 하나의 셀 또는 분리된 셀)
- 지번 유형 (일반/산 — 별도 명시 없으면 '일반')

컬럼명이 정확히 일치하지 않을 수 있으므로 유사 컬럼명을 매칭한다.
(예: "토지소재지", "주소", "소재지(도로명)" 등)

### B) 대화 중 직접 입력
사용자가 채팅으로 "경기도 OO시 OO구 OO동 X-X" 같은 형식으로 알려줄 수 있다.
자연어 주소를 파싱하여 시/도, 시/군/구, 읍/면/동, 본번, 부번을 분리한다.

### 필수 확인 사항
조회 전에 아래 정보를 확보한다 (없으면 사용자에게 확인):
- **감사대상회사명** (워크페이퍼에 기재)
- **감사기준일** (예: 2025.12.31)
- **토지 목록**: 각 물건별 시/도, 시/군/구, 읍/면/동, 지번유형, 본번, 부번

---

## Step 2: Chrome 브라우저로 공시지가 조회

### 사이트 정보
- URL: `https://www.realtyprice.kr/notice/gsindividual/search.htm`
- 조회 방식: 텍스트검색 > 지번 검색

### 조회 절차

각 토지 물건에 대해 다음을 수행한다.

#### 2-1. 탭 준비 및 사이트 접속
```
tabs_context_mcp(createIfEmpty=true) → 탭 ID 확인
navigate(url, tabId) → realtyprice.kr 접속
wait 2초 → 페이지 로드 대기
```

#### 2-2. 폼 요소 식별
```
read_page(tabId, filter="interactive") → 폼 요소 ref ID 확인
```

페이지의 폼 요소는 다음 순서로 나타난다 (ref ID는 매 로드마다 변하므로 패턴으로 찾는다):

| 순서 | 요소 | 식별 방법 |
|------|------|-----------|
| 1 | 시/도 선택 | 첫 번째 combobox (옵션에 "서울특별시", "경기도" 등 포함) |
| 2 | 시/군/구 선택 | 두 번째 combobox (시/도 선택 후 옵션이 채워짐) |
| 3 | 읍/면/동 선택 | 세 번째 combobox (시/군/구 선택 후 옵션이 채워짐) |
| 4 | 지번유형 선택 | 네 번째 combobox (옵션: "일반", "산", "가지번" 등) |
| 5 | 본번 입력 | 첫 번째 textbox (type="text") |
| 6 | 부번 입력 | 두 번째 textbox (type="text") |
| 7 | 검색 버튼 | textbox(type="image") 또는 화면의 "검색" 버튼 |

#### 2-3. 캐스케이드 드롭다운 입력

드롭다운은 캐스케이드 방식이다: 상위 드롭다운을 선택하면 하위 드롭다운의 옵션이 서버에서 다시 로드된다.
따라서 **각 단계마다 대기 → 옵션 확인 → 선택**의 패턴을 반복해야 한다.

```
① form_input(시도_ref, value="41")      ← 경기도 코드
   sleep 2초                              ← 시/군/구 옵션 갱신 대기
   read_page(시군구_ref)                  ← 새 옵션 목록 확인

② form_input(시군구_ref, value="XXXXX")  ← OO구 코드
   sleep 2초                              ← 읍/면/동 옵션 갱신 대기
   read_page(읍면동_ref)                  ← 새 옵션 목록 확인

③ form_input(읍면동_ref, value="XXXXX")  ← OO동 코드
```

각 드롭다운의 option value 값은 read_page에서 확인한다.
사용자가 입력한 행정구역명과 드롭다운 옵션의 텍스트를 매칭하여 해당 value를 선택한다.

#### 2-4. 지번 입력 및 검색

```
form_input(지번유형_ref, value="1")     ← "일반" (산이면 "2")
form_input(본번_ref, value="792")
form_input(부번_ref, value="2")         ← 부번이 없으면 생략
```

**검색 버튼 클릭**: 검색 버튼은 `type="image"`인 input이므로, `form_input`이 아닌 **`left_click`으로 클릭**해야 한다.
스크린샷으로 버튼 위치를 확인하거나, read_page에서 찾은 ref를 이용해 `left_click(ref=검색_ref)`로 클릭한다.

```
screenshot → 검색 버튼 위치 확인
left_click(ref=검색_ref) 또는 left_click(coordinate=[x, y])
wait 3초 → 검색 결과 로드 대기
screenshot → 결과 확인
```

#### 2-5. 결과 데이터 수집

`read_page(tabId, filter="all", max_chars=80000)`으로 전체 페이지를 읽어 테이블 데이터를 추출한다.

수집할 정보:
- **총 건수**: "38개" 같은 텍스트 (generic 요소)
- **열람지역**: "경기도 OO시 OO구 OO동 X-X" (generic 요소)
- **테이블 데이터**: table 내 generic 요소들에서 연도, 소재지, 지번, 공시지가, 기준일자, 공시일자를 순서대로 추출

테이블 데이터는 6개씩 묶으면 한 행이 된다:
```
[년도, 토지소재지, 지번, 공시지가(원/㎡), 기준일자, 공시일자]
```

### 행정구역 변경 주의사항

행정구역이 바뀌면 사용자가 입력한 주소와 드롭다운 옵션이 다를 수 있다.
항상 read_page로 실제 드롭다운 옵션을 확인하고, 유사한 항목을 매칭한다.

대표적인 사례:
- **OO시 2025년 분구**: OO시가 4개 구(분구 사례)로 분구됨.
  예: OO면 → 'OO신구'(XXXXX), OO읍 → 'OO신구'(XXXXX)
- 사용자가 "OO시 OO면"이라고 입력해도, 드롭다운에서 'OO신구'를 선택해야 한다.
- 정확한 매칭이 안 되면, 읍/면/동 이름을 기준으로 적절한 구를 찾는다.

---

## Step 3: 스크린샷 이미지 렌더링

Chrome 브라우저의 save_to_disk 스크린샷은 Cowork 내부 저장소에만 보관되어 파일로 직접 접근이 불가능하다.
따라서 조회 결과를 **HTML로 재구성**한 뒤 **weasyprint**로 렌더링하여 PNG 이미지를 생성한다.

### 렌더링 파이프라인
```
[조회 데이터 JSON] → [HTML 생성] → [weasyprint → PDF] → [pdftoppm → PNG]
```

### 번들 스크립트 사용

`scripts/render_screenshots.py`에 렌더링 함수가 준비되어 있다.

```python
import sys
sys.path.insert(0, "<skill_path>/scripts")
from render_screenshots import generate_screenshot

prop = {
    "sido_options": [{"text": "경기도", "selected": True}, ...],
    "sigungu_options": [{"text": "OO구", "selected": True}, ...],
    "dong_options": [{"text": "OO동", "selected": True}, ...],
    "jibun_type": "일반",
    "jibun_main": "792",
    "jibun_sub": "2",
    "total_count": "38",
    "area_text": "경기도 OO시 OO구 OO동 X-X",
    "rows": [
        {"year": "2025", "location": "경기도 OO시 OO구 OO동 X-X",
         "jibun": "X-X번지", "price": "1,234,567 원/㎡",
         "base_date": "01월01일", "announce_date": "20250430"},
        ...
    ]
}
result = generate_screenshot(prop, "/path/to/output.png")
```

### 한글 폰트 (핵심)

VM에 기본 한글 폰트가 없어 한글이 깨지는 문제가 발생한다. 반드시 아래 경로의 폰트를 사용한다:
```
/usr/share/fonts-droid-fallback/truetype/DroidSansFallback.ttf  (11,172 한글 음절 포함)
```

**주의**: `/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf`는 이름이 비슷하지만 한글 3글자만
포함하므로 절대 사용하지 않는다. 경로가 매우 유사하니 혼동하지 않도록 한다.

CSS에서 한글과 영문을 각각 다른 폰트가 담당하도록 폰트 스택을 구성한다:
```css
@font-face {
    font-family: 'KoreanFont';
    src: url('file:///usr/share/fonts-droid-fallback/truetype/DroidSansFallback.ttf') format('truetype');
}
* { font-family: 'KoreanFont', 'DejaVu Sans', sans-serif !important; }
```
- `KoreanFont`: 한글 담당
- `DejaVu Sans`: 영문, 숫자, 특수문자 담당

### weasyprint 설치 확인
```bash
pip install weasyprint --break-system-packages
```
pdftoppm은 poppler-utils에 포함되어 있으며 대부분 기본 설치되어 있다.

---

## Step 4: 엑셀 워크페이퍼 생성

### 번들 스크립트 사용

`scripts/create_excel.py`에 워크페이퍼 생성 함수가 준비되어 있다.

```python
from create_excel import create_workpaper

data = {
    "output_path": "/path/to/WP_공시지가_조회결과.xlsx",
    "img_dir": "/path/to/images",
    "company_name": "(주)삼성전자",
    "audit_date": "2025.12.31",
    "query_date": "2026.03.24",
    "auditor_name": "홍길동 (공인회계사)",
    "properties": [{
        "seq": 1,
        "sido": "경기도",
        "sigungu": "OO시 OO구",
        "dong": "OO동",
        "jibun": "X-X",
        "sheet_name": "OO동 X-X",
        "img_file": "01_OO동_X-X.png",
        "location_full": "경기도 OO시 OO구 OO동 X-X",
        "price_2025": "1,234,567 원/㎡",
        "total_records": 38,
        "data": [
            [2025, "경기도 OO시 OO구 OO동 X-X", "X-X번지", 1234567, "01월01일", "20250430"],
            ...
        ]
    }],
    "notes": [
        "개별공시지가는 매년 1월 1일 기준으로 산정되며, 2025년분은 2025.04.30에 공시되었습니다."
    ]
}
create_workpaper(data)
```

### 워크북 구조

**시트 1: 요약** — 감사 워크페이퍼의 핵심 시트
1. **조회 신청 내역**: 조회한 토지 목록 (순번, 시/도, 시/군/구, 읍/면/동, 지번)
2. **조회처**: 부동산공시가격 알리미(국토교통부), URL, 조회구분, 가격기준년도
3. **스크린샷 안내**: 각 물건별 시트 및 폴더 내 PNG 파일 참조 안내
4. **결과 요약표**: 물건별 최신 공시지가, 기준일자, 공시일자, 과거 데이터 건수

상단에 감사대상회사, 감사기준일, 조회수행일, 조회수행자 정보를 표시한다.

**시트 2~N: 물건별 상세** (각 토지마다 1시트)
- 소재지, 최신 공시지가(빨간 강조), 총 조회건수
- 연도별 공시지가 추이 테이블 (최근 6개년)
- 조회 결과 캡처 이미지 (PNG 임베드)

### 스타일링
- 타이틀: 남색 배경(#1A5276) + 흰색 글자
- 헤더: 연파란(#D6E4F0)
- 최신 연도 데이터: 노란 하이라이트(#FFFFDD)
- URL: 파란색 폰트
- 비고/주석: 회색 이탤릭

---

## Step 5: 출력 저장

모든 결과물은 CLAUDE.md 규칙에 따라 `_claude/공시지가조회/` 폴더에 저장한다:

```
_claude/공시지가조회/
├── WP_공시지가_조회결과.xlsx      (엑셀 워크페이퍼)
├── 01_[동명]_[지번].png          (1번 물건 스크린샷)
├── 02_[동명]_[지번].png          (2번 물건 스크린샷)
└── ...
```

파일명 규칙:
- 이미지: `{순번:02d}_{읍면동}_{지번}.png` (예: `01_OO동_X-X.png`)
- 엑셀: `WP_공시지가_조회결과.xlsx`

이미 같은 경로에 파일이 있으면, 실행 날짜/시간을 폴더명에 추가하여 구분한다.
(예: `_claude/공시지가조회_20260324/`)

---

## 에러 처리

### 조회 결과 없음
- 행정구역 변경 가능성을 먼저 확인한다 (분구, 통합 등)
- 드롭다운에서 유사한 읍/면/동 이름을 검색한다
- 그래도 못 찾으면 사용자에게 정확한 행정구역 확인을 요청한다

### 검색 버튼이 반응하지 않을 때
- `form_input`으로는 검색이 안 된다. 반드시 `left_click`을 사용한다.
- 스크린샷으로 "검색" 버튼의 좌표를 확인한 후 좌표 클릭을 시도한다.
- 클릭 후 wait 3초 → screenshot으로 결과가 로드되었는지 확인한다.

### 다수 물건 조회 시
- 같은 탭에서 순차 조회한다 (각 물건마다 URL을 다시 navigate)
- 물건별 데이터를 즉시 변수에 저장하여 중간 결과를 잃지 않도록 한다
- 5건 이상일 경우 진행상황을 사용자에게 알린다

### 한글 렌더링 깨짐
- DroidSansFallback.ttf 경로가 정확한지 확인한다
  (올바른 경로: `/usr/share/fonts-droid-fallback/truetype/DroidSansFallback.ttf`)
- CSS에서 `font-family: 'KoreanFont', 'DejaVu Sans', sans-serif` 순서를 지킨다
