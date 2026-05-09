---
name: journal-entry-standardizer
published: true
title: 분개장 헤더 표준화
description: |
  서로 다른 ERP/회계 시스템에서 추출한 분개장(Journal Entry) 파일들을 하나의 표준 스키마로 통합하는 스킬.
  사용 시점: (1) 여러 연도의 분개장을 통합해야 할 때, (2) 서로 다른 형식의 분개장을 표준화해야 할 때,
  (3) 감사/실사 시 분개장 데이터를 정리해야 할 때, (4) 분개 테스트(JET)를 위한 전처리가 필요할 때,
  (5) 회계 데이터를 통합 분석하기 위한 기초 작업이 필요할 때.
  "분개장", "분개", "전표", "journal entry", "JE", "분개장 통합", "분개장 표준화", "분개 테스트",
  "JET", "전표 데이터", "차변", "대변", "계정과목", "COA" 등의 표현이 나오면 이 스킬을 사용한다.
  여러 파일의 헤더가 다르거나 ERP가 바뀌어서 형식이 다른 경우에도 반드시 사용한다.
---

# Journal Entry Standardizer

서로 다른 구조의 분개장 파일들을 하나의 표준 스키마로 통합하고, 5단계 검증을 거쳐 정합성을 보장하는 스킬이다.

## 코드 아키텍처

이 스킬은 **하이브리드 구조**를 따른다:

- **`scripts/je_utils.py`**: 스키마에 의존하지 않는 범용 유틸리티 함수. 어떤 분개장이든 공통으로 사용한다. **수정하지 않고 import하여 사용.**
- **워크플로우별 코드**: Phase 2~4의 매핑·변환·출력·검증 로직은 **프로젝트마다 LLM이 직접 작성**한다. 본 문서의 의사코드를 참고하되, 해당 프로젝트의 스키마와 헤더에 맞게 코드를 생성한다.

### je_utils.py 제공 함수 목록

```python
import sys
sys.path.insert(0, '<스킬경로>/scripts')
from je_utils import *

# 숫자 변환 — 금액 컬럼 처리 시 항상 사용
safe_num(val)            # None/''/'-'/'1,000'/'(500)' → 0/1000.0/-500.0

# 텍스트 변환 — 빈 셀 → 'NULL' 처리
safe_text(val)           # None/'' → 'NULL', 그 외 → str

# 날짜 변환
parse_date(val)          # 다양한 포맷/Excel serial → datetime 또는 None

# 날짜 파생
derive_year(dt)          # datetime → 연도 int
derive_month(dt)         # datetime → 월 int
derive_quarter(dt)       # datetime → 분기 int (1~4)

# 계정코드 파싱
parse_account_code(text) # '[1350000]부가세대급금' → ('1350000', '부가세대급금')
normalize_code(code)     # 정규화: '012345' → '12345', 12345.0 → '12345'

# 헤더 자동 분석
analyze_header(file_path, sheet_name=None, max_preview_rows=5)
# → dict: headers, pattern, has_gubun_col, has_embedded_code, preview_rows, ...

# 엑셀 출력 헬퍼 (서식 상수 + 셀 생성)
FONT_NAME, FONT_SIZE     # '맑은 고딕', 10
AMT_FMT                  # '#,##0;[Red](#,##0);-'
DATE_FMT                 # 'YYYY-MM-DD'
HDR_BG_COLOR             # '4472C4'
make_header_cell(ws, value)                         # 헤더 셀 (파란 배경, 흰 볼드)
make_data_cell(ws, value, is_amount=False, is_date=False)  # 데이터 셀 (서식 적용)
```

### 왜 이런 구조인가

| 범용 유틸 (je_utils.py) | 워크플로우 코드 (LLM 작성) |
|---|---|
| `safe_num('1,000')` → 항상 1000 | 어떤 컬럼이 차변인지는 파일마다 다름 |
| `parse_date('2025-01-01')` → 항상 datetime | 컬럼 매핑 로직은 파일마다 다름 |
| `safe_text(None)` → 항상 'NULL' | 시트 구성·검증 기준은 프로젝트마다 다름 |

검증된 변환 함수를 매번 재작성하면 버그가 유입될 수 있다. 반면 컬럼 매핑·엑셀 출력 구조·검증 로직은 스키마에 종속되므로 코드로 고정하면 유연성이 떨어진다. 따라서 **변하지 않는 것은 코드로, 변하는 것은 의사코드로** 관리한다.

---

## 워크플로우

### Phase 1: 탐색 및 준비

#### 1-1. 입력 파일 스캔

사용자에게 다음을 확인한다:
- **분개장 파일 위치**: 폴더 경로 또는 파일 목록
- **표준 스키마 파일**: 사용자가 제공하는 통합 대상 헤더 템플릿 (없으면 기본 스키마 사용)
- **COA 파일**: 계정과목표 (있으면 매핑에 사용, 없으면 스킵)

각 파일에 대해 다음을 수집한다:
```
- 파일명, 파일 크기, 시트명
- 헤더 행 위치 (1행일 수도, 2행일 수도, SUBTOTAL 행 뒤일 수도 있음)
- 컬럼 수, 데이터 행 수
- 처음 5행의 샘플 데이터
```

파일이 열리지 않는 경우(손상, 암호화, 비표준 형식) 즉시 사용자에게 보고한다.

#### 1-2. 헤더 분석 및 구조 분류

`analyze_header()`를 사용하여 각 파일의 구조를 자동 감지한다:

```python
# Phase 1-2 의사코드
for file in source_files:
    info = analyze_header(file['path'], file.get('sheet'))
    # info['pattern']  → 'single_row' / 'multi_row' / 'subtotal_prefix'
    # info['has_gubun_col'] → True면 차대분리형
    # info['has_embedded_code'] → True면 [코드]계정명 형식
    # info['headers'] → 컬럼명 리스트
    # info['preview_rows'] → 첫 5행 샘플
```

**일반적인 분개장 헤더 패턴들:**

| 패턴 | 특징 | 예시 |
|---|---|---|
| 단일행 헤더 | 1행에 모든 컬럼명 | 승인일/승인번호/차변금액/... |
| 다중행 헤더 | 2~3행에 걸쳐 그룹+상세 | 전표승인정보(년/월/일/번호) |
| SUBTOTAL 선행 | 합계행 뒤에 헤더 | Row0=SUBTOTAL, Row1=헤더 |
| 차대분리형 | 차변/대변이 별도 행 | 구분 컬럼으로 차변/대변 구분 |
| 차대통합형 | 한 행에 차변+대변 | 차변금액/차변계정/대변계정/대변금액 |
| 코드내장형 | 계정과목에 코드 포함 | [1350000]부가세대급금 |

파일마다 어떤 패턴인지 분류한 뒤, 사용자에게 분석 결과를 보고한다.

#### 1-3. 헤더 분류: 필수 vs 선택

통합 스키마의 헤더는 **필수헤더**와 **선택헤더** 두 계층으로 나뉜다.

**필수헤더 (7개)** — 분개장의 본질적 구성요소. 반드시 매핑되어야 한다:

| # | 필수헤더 | 설명 | 매핑 유형 |
|---|---------|------|----------|
| 1 | 전표일자 | 전표의 승인일/기표일 | 직접매핑 |
| 2 | 전표번호 | 1개 분개 Entry를 식별하는 고유값 | 직접매핑 또는 **합성** (아래 참조) |
| 3 | 계정명 | 계정과목 명칭 | 직접매핑 (코드 내장 시 파싱) |
| 4 | 차변금액 | 차변 금액 | 직접매핑 |
| 5 | 대변금액 | 대변 금액 | 직접매핑 |
| 6 | 적요 | 거래 설명/메모 | 직접매핑 |
| 7 | 거래처명 | 거래 상대방 명칭 | 직접매핑 |

**전표번호 합성 로직 (중요):**

전표번호는 하나의 분개 Entry(차변+대변 묶음)를 식별하는 핵심 키다. 그런데 실무에서는 원본에 전표번호가 아예 없거나, 있더라도 유일한 식별자가 되지 못하는 경우가 빈번하다. 이때 LLM은 다음 절차를 따른다:

1. **전표번호 후보 탐색**: 원본 헤더에서 "전표번호", "승인번호", "번호", "No", "Document Number" 등 전표 식별자로 보이는 컬럼을 찾는다.
2. **유일성 검증**: 후보 컬럼의 값이 전표 단위로 유일한지 확인한다. 같은 번호 내 차변합계 = 대변합계가 성립하면 유효한 전표번호다.
3. **합성이 필요한 경우**: 적절한 전표번호 컬럼이 없으면, 다른 필드를 조합하여 합성 전표번호를 생성한다.

```python
# 전표번호 합성 의사코드
from collections import Counter

def synthesize_slip_numbers(rows, date_key):
    """rows: list of dict (이미 변환된 행)"""
    date_counter = Counter()
    for r in rows:
        dt = r.get(date_key)
        dt_str = dt.strftime('%Y%m%d') if dt else 'NODATE'
        date_counter[dt_str] += 1
        seq = date_counter[dt_str]
        if not r.get('전표번호') or r['전표번호'] == 'NULL':
            r['전표번호'] = f"{dt_str}-{seq:05d}"
    return rows
```

4. **사용자 확인**: 합성 로직을 적용하기 전에 반드시 사용자에게 "원본에 전표번호가 없어 [전표일자+순번]으로 합성하겠습니다" 등의 안내를 하고 승인을 받는다.

**선택헤더** — 원본에 존재하지만 필수가 아닌 모든 컬럼. 대표적인 예시:

| 선택헤더 | 빈도 |
|----------|------|
| 계정코드 | 높음 — 코드가 계정명에 내장되어 있거나 별도 컬럼 |
| 거래처코드 | 높음 |
| 프로젝트코드/명 | 중간 |
| 작성부서코드/명 | 중간 |
| 작성일 | 중간 — 전표일자와 다른 경우 |
| 사용부서코드/명 | 낮음 |
| 작성자/사원 | 낮음 |
| 전표유형 | 낮음 |
| 사업장 | 낮음 |

**자동 파생 컬럼** — 원본에서 매핑하는 것이 아니라, 스킬이 직접 계산/파싱하여 채우는 컬럼. 사용자 선택 없이 항상 포함:

| 파생 컬럼 | 산출 방식 | 비고 |
|-----------|-----------|------|
| 연 | 전표일자에서 연도 추출 (`derive_year(dt)`) | 정수형 |
| 월 | 전표일자에서 월 추출 (`derive_month(dt)`) | 정수형 |
| 분기 | 전표일자에서 산출 (`derive_quarter(dt)`) | 정수형 (1~4) |
| 차변-대변 | 파이썬에서 `safe_num(차변) - safe_num(대변)` 계산하여 값 입력 | 원본에 해당 컬럼이 있어도 무시하고 직접 계산 |
| 대분류/중분류/소분류 | COA 매핑 (COA 제공 시) | 텍스트 |

#### 1-4. 표준 스키마 확정 (Human-in-the-Loop)

사용자가 별도 스키마 파일을 제공하면 그것을 우선 사용한다. 제공하지 않은 경우 아래 절차를 따른다:

**Step A: 필수헤더 매핑 제안**

각 원본 파일의 헤더를 분석하여, 필수헤더 7개에 대한 매핑 안을 파일별로 테이블 형태로 제시한다:

```
예시 — 3개 파일의 필수헤더 매핑 제안:

| 필수헤더   | 2021년 분개장 (iCUBE)     | 2024년 분개장 (더존)         |
|-----------|--------------------------|----------------------------|
| 전표일자   | B열(일자)                 | A열(승인일)                 |
| 전표번호   | C열(전표번호)             | B열(승인번호)               |
| 계정명    | F열(계정과목)              | D열(차변계정과목) → 파싱     |
| 차변금액   | G열(차변)                 | C열(차변금액)               |
| 대변금액   | H열(대변)                 | F열(대변금액)               |
| 적요      | J열(적요)                 | G열(적요)                   |
| 거래처명   | I열(거래처)               | I열(거래처명)               |
```

이 매핑 안을 사용자에게 보여주고 **승인 또는 수정**을 요청한다. 사용자가 "OK" 또는 수정사항을 주면 확정한다. 승인 없이 변환을 진행하지 않는다.

**Step B: 선택헤더 포함 여부 질문**

필수헤더 매핑이 확정되면, 원본 파일에 존재하지만 필수헤더에 매핑되지 않은 나머지 컬럼들을 **번호가 매겨진 목록**으로 보여주고, 사용자가 번호로 선택할 수 있게 한다:

```
예시:
필수헤더 외에 다음 컬럼들이 원본에 존재합니다.
포함할 항목의 번호를 선택해주세요 (예: "1,2,3" 또는 "전체" 또는 "없음"):

 1. 계정코드 (2021: E열, 2024: AC열)
 2. 거래처코드 (2024: H열)
 3. 프로젝트코드/명 (2021: S열, 2024: L~M열)
 4. 작성부서코드/명 (2021: M열, 2024: N~O열)
 5. 작성일 (2024: J열)
 6. 전표유형 (2024: Y열)
 7. 사업장 (2024: U열)

※ "전체 포함"을 선택하면 가능한 모든 컬럼을 포함합니다.
```

사용자가 선택한 선택헤더를 최종 스키마에 추가한다.

**Step C: 최종 스키마 확정**

필수헤더 + 선택헤더 + 자동파생 컬럼을 조합하여 최종 스키마를 확정하고, 확정된 컬럼 목록을 사용자에게 한번 더 보여준다.

---

### Phase 2: 매핑 및 변환

#### 2-1. 컬럼 매핑 실행

Phase 1에서 사용자 승인을 받은 매핑을 기반으로 변환을 수행한다. 매핑 추론의 우선순위:

1. **정확 일치**: 헤더명이 필수/선택 컬럼명과 동일하거나 거의 동일
2. **유사 일치**: "승인일자" → "전표일자", "금액(차변)" → "차변금액" 등 의미적 동의어
3. **위치+내용 추론**: 날짜 형식 컬럼 → 전표일자/작성일, 숫자 컬럼 → 금액 등
4. **패턴 참조**: `references/common_erp_patterns.md`의 ERP별 패턴 참고

매핑에 확신이 없는 컬럼이 있으면 해당 컬럼만 사용자에게 재확인한다.

#### 2-2. 데이터 변환 — 의사코드

변환 코드는 파일마다 구조가 다르므로 LLM이 직접 작성한다. 아래 의사코드를 참고하여 해당 프로젝트에 맞는 코드를 생성한다.

**행 변환 패턴 (차대통합형):**
```python
# 원본의 한 행 → 통합 스키마의 한 행
def transform_row_unified(vals, col_map, source_label, coa_fn=None):
    """
    vals: 원본 행의 값 리스트
    col_map: {'전표일자': 0, '차변금액': 3, ...} 컬럼 인덱스 매핑
    """
    dt = parse_date(vals[col_map['전표일자']])

    # 코드 내장형 처리
    acct_text = vals[col_map.get('계정과목')]
    acct_code, acct_name = parse_account_code(acct_text)
    # 별도 코드 컬럼이 있으면 우선 사용
    if '계정코드' in col_map:
        acct_code = normalize_code(vals[col_map['계정코드']]) or acct_code

    debit = safe_num(vals[col_map['차변금액']])
    credit = safe_num(vals[col_map['대변금액']])

    row = {
        # 필수헤더
        '전표일자': dt,
        '전표번호': safe_text(vals[col_map.get('전표번호')]),
        '계정명':   safe_text(acct_name),
        '차변금액': debit,
        '대변금액': credit,
        '적요':     safe_text(vals[col_map.get('적요')]),
        '거래처명': safe_text(vals[col_map.get('거래처명')]),

        # 자동파생
        '연':       derive_year(dt),
        '월':       derive_month(dt),
        '분기':     derive_quarter(dt),
        '차변-대변': debit - credit,   # ← 항상 직접 계산
        '계정코드': safe_text(acct_code),

        # COA 매핑
        # coa_fn(code) → (big, mid, small) 또는 (None, None, None)
    }

    # 선택헤더 추가
    for key, idx in col_map.items():
        if key not in row and key not in ('_skip',):
            row[key] = safe_text(vals[idx])

    row['_source_label'] = source_label
    return row
```

**행 변환 패턴 (차대분리형):**
```python
# 구분 컬럼이 있는 경우: 한 행에 차변 또는 대변 중 하나만 있음
def transform_row_split(vals, col_map, source_label, **kw):
    gubun = str(vals[col_map['구분']]).strip()
    amount = safe_num(vals[col_map['금액']])

    if '차' in gubun:
        debit, credit = amount, 0
    elif '대' in gubun:
        debit, credit = 0, amount
    else:
        debit, credit = 0, 0

    # 이후 row dict 조립은 통합형과 동일
    # ...
```

**공통 변환 규칙 (LLM이 코드 작성 시 반드시 적용):**

| 항목 | 규칙 | 사용 함수 |
|------|------|-----------|
| 날짜 | datetime 또는 문자열 → datetime | `parse_date()` |
| 금액 | 콤마 문자열/None/'-' → float, 빈 값 → 0 | `safe_num()` |
| 텍스트 | None/빈 문자열 → 'NULL' | `safe_text()` |
| 차변-대변 | 항상 `safe_num(차변) - safe_num(대변)` 직접 계산. 원본 "잔액" 무시 | 산술 연산 |
| 연/월/분기 | 전표일자에서 파생 | `derive_year/month/quarter()` |
| 계정코드 내장 | `[코드]명칭` → 분리 | `parse_account_code()` |
| 계정코드 정규화 | 앞자리 0 제거, float→int→str | `normalize_code()` |

#### 2-3. 데이터 필터링

다음 행은 통합 대상에서 제외한다:
- 헤더/부제목 행
- SUBTOTAL/소계/합계 행
- 날짜도 없고 금액도 0인 빈 행
- 완전히 비어있는 행

```python
# 필터링 의사코드
def is_valid_data_row(vals, date_col_idx, amount_col_indices):
    """통합 대상 행인지 판단"""
    if all(v is None for v in vals):
        return False
    # 합계행 감지
    for v in vals:
        s = str(v).upper() if v else ''
        if s in ('SUBTOTAL', '합계', '소계', '총계'):
            return False
    # 날짜 없고 금액도 0이면 스킵
    dt = parse_date(vals[date_col_idx])
    amounts = sum(abs(safe_num(vals[i])) for i in amount_col_indices)
    if dt is None and amounts == 0:
        return False
    return True
```

제외된 행 수를 기록해둔다 (검증 시 원본 총 행수와의 차이를 설명하는 데 사용).

#### 2-4. COA 매핑

COA 파일이 제공된 경우, 계정코드를 기준으로 대분류/중분류/소분류를 매핑한다.

```python
# COA 매핑 의사코드
def build_coa_mapper(coa_dict):
    """coa_dict: {code_str: {'name':..., 'big':..., 'mid':..., 'small':...}}"""
    def lookup(code):
        code = normalize_code(code)
        if not code:
            return None, None, None

        # 1단계: 직접 매칭
        if code in coa_dict:
            c = coa_dict[code]
            return c['big'], c['mid'], c['small']

        # 2단계: 자릿수 보정 (5자리→7자리)
        padded = code.ljust(7, '0')
        if padded in coa_dict:
            c = coa_dict[padded]
            return c['big'], c['mid'], c['small']

        # 3단계: 접두어 매칭 (유일 매칭만)
        matches = [k for k in coa_dict if k.startswith(code)]
        if len(matches) == 1:
            c = coa_dict[matches[0]]
            return c['big'], c['mid'], c['small']

        # 4단계: 코드 범위 분류 (최종 폴백)
        # 1xxx=자산, 2xxx=부채, 3xxx=자본, 4xxx=매출/원가,
        # 5xxx=매출원가, 8xxx=판관비, 9xxx=영업외손익
        first = code[0] if code else ''
        range_map = {'1':'자산','2':'부채','3':'자본','4':'매출/매출원가',
                     '5':'매출원가','8':'판관비','9':'영업외손익'}
        return range_map.get(first, None), None, None

    return lookup
```

각 단계에서 보정된 코드 수를 기록한다.

---

### Phase 3: 엑셀 출력

#### 3-1. 통합 파일 생성

openpyxl의 `write_only` 모드를 사용하여 대용량 데이터도 효율적으로 저장한다. `je_utils.py`의 셀 생성 헬퍼를 활용한다.

```python
# Phase 3 의사코드
from openpyxl import Workbook
from je_utils import make_header_cell, make_data_cell, AMT_FMT, safe_num

wb = Workbook(write_only=True)

# 금액 컬럼 판별용 집합 (프로젝트마다 달라질 수 있음)
AMOUNT_COLS = {'차변금액', '대변금액', '차변-대변'}
DATE_COLS = {'전표일자', '작성일'}

# --- 시트 1: 통합파일 ---
ws = wb.create_sheet('통합파일')
ws.append([make_header_cell(ws, h) for h in schema_columns])

for row_dict in all_rows:
    cells = []
    for col in schema_columns:
        val = row_dict.get(col)
        cells.append(make_data_cell(ws, val,
                     is_amount=(col in AMOUNT_COLS),
                     is_date=(col in DATE_COLS)))
    ws.append(cells)

# --- 시트 2: 계정목록 ---
# 통합 데이터에서 (계정코드, 계정명) UNIQUE 집계
# 계정코드 내림차순(숫자 큰 것이 위)
# 컬럼: 계정코드 | 계정명 | 건수 | 차변합계 | 대변합계 [| 대분류 | 중분류 | 소분류]
ws_acct = wb.create_sheet('계정목록')
acct_agg = {}  # {code: {name, count, debit_sum, credit_sum, big, mid, small}}
for r in all_rows:
    code = r.get('계정코드', 'NULL')
    # 집계 로직...
# 계정코드 내림차순 정렬
for code in sorted(acct_agg.keys(), key=lambda c: -int(c) if c.isdigit() else 0):
    # 행 출력...

# --- 시트 3: COA (제공 시) ---
# COA 원본 데이터 출력

# --- 시트 4: 검증결과 ---
# Phase 4 검증 결과를 기록

wb.save(output_path)
```

**서식 (je_utils.py에 정의된 상수 사용):**
- 폰트: 맑은 고딕 10pt — `FONT_NAME`, `FONT_SIZE`
- 헤더: 파란 배경 + 흰색 볼드 — `make_header_cell()`
- 금액 컬럼: `#,##0;[빨강](#,##0);-` — `AMT_FMT`, `make_data_cell(is_amount=True)`
- 날짜 컬럼: `YYYY-MM-DD` — `DATE_FMT`, `make_data_cell(is_date=True)`

#### 3-2. 파일명 규칙

프로젝트 헌법(CLAUDE.md)이 있으면 그 타임스탬프 규칙을 따른다.
없으면 `분개장_통합_YYYYMMDD_HHmm.xlsx` 형식을 사용한다.

---

### Phase 4: 5단계 검증

통합이 완료되면 반드시 아래 5단계 검증을 수행한다. **모든 단계를 통과해야** 최종 파일로 확정된다. 실패 시 원인을 분석하고 수정 후 재검증한다.

검증 코드는 프로젝트의 스키마(컬럼명, 원본 구조)에 따라 LLM이 직접 작성한다. 아래 의사코드를 참고한다.

#### 검증 1: 행 수 검증

```python
# 의사코드
def verify_row_counts(integrated_counts, original_counts):
    """
    integrated_counts: {source_label: row_count}
    original_counts: {source_label: row_count}  ← 동일 필터링 적용한 카운트
    """
    all_pass = True
    for label in all_labels:
        diff = original_counts[label] - integrated_counts[label]
        if diff != 0:
            all_pass = False
            # 차이 원인 기록
    return all_pass, details
```

핵심: 원본에서도 통합과 동일한 필터링 로직(빈 행, 합계행 제외)을 적용하여 카운트한다. 단순히 `max_row`를 쓰면 합계행이 포함되어 불일치가 발생한다.

#### 검증 2: 차대 합계 검증

```python
# 의사코드
def verify_debit_credit_totals(integrated_totals, original_totals):
    """Both: {label: {'debit': float, 'credit': float}}"""
    for label in all_labels:
        d_diff = original_totals[label]['debit'] - integrated_totals[label]['debit']
        c_diff = original_totals[label]['credit'] - integrated_totals[label]['credit']
        # abs(diff) < 1 이면 PASS (부동소수점 허용)
```

핵심: 원본을 다시 읽되, 검증1과 동일한 필터링을 적용한 데이터 행만 합산한다.

#### 검증 3: 차대 균형 검증

```python
# 의사코드
def verify_voucher_balance(rows, date_key, slip_key):
    """전표 단위(일자+번호)로 그룹핑하여 차변합=대변합 확인"""
    vouchers = {}  # {(date, slip_no): {debit_sum, credit_sum}}
    for r in rows:
        key = (r[date_key], r[slip_key])
        # 합산...
    imbalanced = [v for v in vouchers if abs(v.debit - v.credit) >= 1]
    return len(imbalanced) == 0, details
```

참고: 원본 데이터 자체에 불균형 전표가 있을 수 있다 (수정분개, 이월 등). 이 경우 스킬의 문제가 아니므로 "원본 불균형"으로 분류한다.

#### 검증 4: COA 매핑 검증

```python
# 의사코드
def verify_coa_mapping(rows, code_key, class_key):
    """계정코드 보유 행 중 대분류가 채워진 비율"""
    with_code = [r for r in rows if r[code_key] != 'NULL']
    mapped = [r for r in with_code if r[class_key] != 'NULL']
    rate = len(mapped) / len(with_code) * 100
    # 100% → PASS, 미달 → 미매핑 코드 목록 출력
```

#### 검증 5: 샘플 검증

```python
# 의사코드
import random
random.seed(42)

def verify_samples(integrated_by_source, original_by_source,
                   debit_col_map, credit_col_map, n=10):
    """각 원본에서 10건 랜덤 추출, 원본↔통합 1:1 금액 대조"""
    for label in all_labels:
        indices = random.sample(range(len(integrated_by_source[label])), n)
        for idx in indices:
            i_row = integrated_by_source[label][idx]
            o_row = original_by_source[label][idx]
            # safe_num으로 비교
            # abs(차이) < 1 이면 PASS
```

#### 검증 반복

하나라도 FAIL이면:
1. 실패 원인을 분석
2. 변환 로직 수정
3. 통합 재실행
4. 5단계 재검증

ALL PASS가 될 때까지 반복한다.

---

### Phase 5: 결과 보고

최종 보고에 포함할 내용:
- 통합 파일 링크
- 연도별 행 수, 차대합계
- 전표 수, 고유 계정코드 수
- 5단계 검증 결과 (PASS/FAIL)
- 특이사항 (손상 파일, 미매핑 코드, 원본 불균형 전표 등)

---

## 엣지 케이스

### 손상된 파일
openpyxl로 열리지 않는 파일은 사용자에게 즉시 보고한다. 원본이 다른 경로에 있을 수 있으니 확인을 요청한다.

### 2행 이상 헤더
Row 0이 그룹 헤더(예: '전표승인정보'), Row 1이 상세 헤더(예: '년/월/일/번호')인 경우, 상세 헤더를 기준으로 매핑한다. 그룹 헤더는 컨텍스트로만 참고한다.

### SUBTOTAL 선행행
일부 ERP는 데이터 앞에 SUBTOTAL 행을 넣는다. 이 행은 스킵하고 그 다음 행을 헤더로 인식한다.

### 동일 파일의 복수 버전
같은 연도에 여러 버전이 있으면(예: `2024년 분개장.xlsx`, `2024년 분개장_0331.xlsx`) 사용자에게 어떤 파일을 쓸지 확인한다.

### 월별 시트 구조
일부 파일은 월별 시트(01월, 02월, ...)와 통합 시트를 모두 가진다. 통합 시트가 있으면 그것을 사용하고, 없으면 월별 시트를 합산한다. 단, 중복 주의.

**주의**: `analyze_header()`는 기본적으로 첫 번째 시트를 읽는다. 그러나 첫 번째 시트가 '월별' 요약 시트이고 실제 데이터가 다른 시트에 있는 경우가 있다. 시트 목록을 반드시 확인하고, 데이터가 가장 많은 시트를 선택한다. 실전 사례: 첫 시트('월별')는 15행 요약, 실제 데이터는 '2023년' 시트에 8만 행 이상.

### 월별 소계행이 데이터 사이에 산재하는 경우
일부 ERP 출력은 데이터 중간에 월별 소계행(예: '23년1월 | 합계 | ... | 27,126,240,196')이 삽입되어 있다. 이 행들은 `parse_date()`가 None을 반환하므로 필터링되지만, 승인일이 아닌 작성일 컬럼에 날짜가 아닌 문자열('23년1월')이 들어있으므로 날짜 파싱 대상 컬럼을 정확히 지정해야 한다.

### 전표번호 부재
원본에 전표번호/승인번호 컬럼이 아예 없거나, 있어도 모든 행이 동일한 값(예: 전부 "1")인 경우가 실무에서 흔하다. 이때:

1. 먼저 원본의 다른 컬럼 조합으로 전표를 식별할 수 있는지 탐색한다 (작성번호, 입력순번, 라인번호 등)
2. 차변행과 대변행이 교대로 나타나는 패턴이면, 연속 행의 차변합=대변합이 되는 지점까지를 하나의 전표로 묶을 수 있다
3. 어떤 방법으로도 전표 경계를 식별할 수 없으면, `전표일자-행순번` 형태로 합성하되, 검증3(차대균형)은 "전표번호 합성으로 인해 전표 단위 검증 불가"로 스킵 처리한다
4. **합성 로직은 반드시 사용자 승인 후 적용한다**

### 차변-대변 컬럼이 원본에 있는 경우
원본에 "잔액", "차변-대변", "Net Amount" 등의 컬럼이 있더라도, 통합 파일에서는 이를 무시하고 파이썬에서 `차변금액 - 대변금액`을 직접 계산하여 값으로 입력한다. 원본의 계산 오류가 전파되는 것을 방지하기 위함이다.

---

## 성능 고려사항

- **대용량 파일**: `read_only=True`, `data_only=True` 모드로 읽기
- **엑셀 쓰기**: `write_only=True` 모드 사용 (30만행 이상 시 필수)
- **메모리**: 연도별로 순차 처리하여 메모리 피크를 관리
- **pickle 중간 저장**: 변환 결과를 pickle로 저장해두면 엑셀 재생성 시 파싱을 반복하지 않아도 됨

---

## 참고 자료

- `references/common_erp_patterns.md`: 한국 주요 ERP별 분개장 헤더 패턴 (DOUZONE, SAP, Oracle, ecount 등)
