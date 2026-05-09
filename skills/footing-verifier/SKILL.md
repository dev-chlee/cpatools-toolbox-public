---
name: footing-verifier
published: true
title: 풋팅 (Footing) 검증
description: |
  한국 감사보고서 또는 재무제표 엑셀 파일에 대해 풋팅(Footing) 검증을 수행하는 스킬. 재무상태표(BS), 손익계산서(PL), 자본변동표(CE), 현금흐름표(CF) 및 주석 전체에 대해 합계/소계 수식 검증, 시트간 교차검증(BS↔주석, PL↔주석), 서술 검증(주석 참조 적절성, 항목번호 순서, 당기/전기 연도, 서술 내 수치 일치)을 수행하고, 검증결과요약 시트와 하이퍼링크가 포함된 워크페이퍼(엑셀)를 생성한다. 한국 일반기업회계기준(K-GAAP) 및 K-IFRS 모두 지원하며, 시트명·시트 구조·주석 개수가 다양한 어떤 재무제표 형식에도 적용 가능하다.
  사용 시점: (1) 감사보고서 풋팅 검증 시, (2) 재무제표 합계/소계 자동 검증 시, (3) 주석 참조 적절성 검토 시, (4) 풋팅 워크페이퍼 작성 시, (5) 재무제표 일관성·정합성 검토 시, (6) F/S 검토 절차 자동화 시.
  "풋팅", "footing", "재무제표 검증", "합계 검증", "소계 검증", "감사 풋팅", "풋팅 테스트", "F/S 검증", "재무제표 풋팅", "주석 검증", "재무제표 정합성", "Cross-footing", "재무제표 합계 확인", "감사보고서 검증" 등의 표현이 나오면 반드시 이 스킬을 사용한다. 특히 재무제표 엑셀 파일을 첨부하며 합계 검증·풋팅·소계 일치 여부를 묻는 경우에는 반드시 이 스킬을 트리거한다.
---

# 풋팅 검증 자동화 스킬 (Footing Verifier)

## 이 스킬의 작동 방식

이 스킬은 **규칙 기반 자동화가 아니다**. 회사마다 시트 구조·헤더 위치·소계 패턴·부호 처리가 모두 다르기 때문에, 정규식이나 패턴 매칭으로 일반화하면 반드시 오류가 발생한다.

대신 다음과 같이 작동한다.

| 영역 | 누가 |
|---|---|
| 시트 구조·위계 인식 | **LLM이 시트를 직접 읽고 판단** |
| 어느 셀이 어느 셀들의 합인지 결정 | **LLM이 데이터를 보고 결정** |
| 부호 처리 (차감항목, 음수 소계) | **LLM이 데이터로 검증 후 결정** |
| 서술 적절성 (계정과목과 주석 매핑) | **LLM이 회계 지식으로 판단** |
| 검증 셀 서식, 재계산, 요약시트 생성 | Python 헬퍼 (`scripts/footing_helpers.py`) |

따라서 이 스킬을 사용할 때는 **시트를 직접 한 번씩 읽어보면서 판단**해야 하고, "자동으로 모든 합계를 잡아줘" 같은 단순 함수 호출은 없다.

## 입력 요구사항

### 필수 (이게 없으면 못 함)

- **xlsx 파일 1개**
- **검증할 합계/소계가 있는 시트 1개 이상** (재무제표든 주석이든 형식 무관)

이게 전부다. 시트명·헤더 형식·언어·메타데이터는 어느 것도 필수가 아니다.

### 자동 인식 패턴 (있으면 메타데이터 자동 추출, 없어도 작동)

`analyze_workbook_basic()` 가 다음 패턴이 있으면 추출하고, 없으면 해당 필드만 `None`/빈값으로 두고 진행한다:

| 항목 | 인식 패턴 | 없으면 |
|---|---|---|
| 회사명 | "주식회사", "(주)", "Inc", "Co.", "Ltd", "Corp" 포함 셀 (재무제표 시트 첫 15행) | 요약시트 타이틀이 `'회사명 미상'`로 표시 |
| 기수(당/전기) | `제 N(당\|전) 기 YYYY년 MM월 DD일` 정규식 | 타이틀의 기수/결산일이 `'?'` |
| 단위 | "단위" + "원"/"천원"/"백만원" | 타이틀의 단위가 `'?'`, **교차검증 시 단위 환산은 LLM이 수동 처리** |
| 재무제표 시트명 | `BS`/`B/S`/`PL`/`P/L`/`CE`/`CF`/`IS` 또는 `재무상태표`/`손익계산서`/`자본변동표`/`현금흐름표` 포함 | 어느 시트가 BS/PL인지 자동 판정 못 함 → **LLM이 시트 내용 보고 직접 결정** |
| 주석 시트명 | `^(?:주석\s*)?(\d+)$` (예: `1`, `주석1`, `주석 4`) | 주석 시트 자동 분류 못 함 → **LLM이 직접 판단** |
| 주석 제목 | 주석 시트 B열(또는 A열) 첫 15행에 `N. 제목` 형식 | `note_titles` 비어 있음 → 주석 참조 적절성 검증 시 LLM이 시트 내용 보고 추론 |

### 메타데이터 부재가 영향을 주는 기능 (정확히)

| 기능 | 메타데이터 의존도 | 없을 때 동작 |
|---|---|---|
| Phase 1~6 (풋팅 본업) | 없음 | 정상 작동 |
| Phase 7-1 (주석 참조 적절성) | `note_titles` 있으면 도움 | 없어도 LLM이 시트 직접 보고 판단 |
| Phase 7-2 (항목번호 순서) | 없음 | 정상 작동 |
| **Phase 7-3 (당기/전기 연도)** | **`period_current.closing_year` 필요** | **이 검증 항목 1개만 스킵, 나머지 검증은 진행** |
| Phase 7-4 (서술 내 수치 일치) | 없음 | 정상 작동 |
| Phase 8 (요약시트 생성) | 타이틀 모양에만 영향 | 정상 작동 (타이틀에 빈값 표시) |

### 비표준 입력 처리 가이드

- **시트명이 `Sheet1`, `Tab2` 같이 무의미해도** OK — LLM이 내용 읽고 BS/PL/주석 분류
- **영문 감사보고서**도 OK — 회계 위계만 파악하면 됨
- **주석 없이 BS만 있는 파일**도 OK — Section 1 풋팅만 수행, Section 1-2(교차)·Section 2~5(서술) 자동 스킵
- **단일 시트 파일**도 OK — 그 시트 내부 합계만 검증

→ 즉, "**xlsx에 합계 있으면 일단 시작 가능**"이 원칙. 메타데이터 자동 추출 실패는 작업 중단 사유가 아니다.

## 핵심 원칙

1. **원본 셀 절대 수정 금지**. 검증 수식은 항상 빈 열/행에 작성한다.
2. **검증 수식은 차이 산출**: `=표시된합계 - 계산된합계` 형태. 정상이면 0, 오류면 차이값.
3. **하드코딩 금지**: 모든 검증은 엑셀 수식으로 작성하여 원본 변경 시 자동 재계산.
4. **사전분석이 가장 중요**: 검증 수식을 쓰기 전에 **반드시 Python으로 모든 합계를 직접 계산해서 차이를 확인한다.** 사전분석으로 잘못된 합계를 미리 발견하고, 검증 수식 작성 단계에서는 정확하게 매핑된 수식만 작성한다.
5. **LibreOffice 재계산은 필수**: openpyxl은 수식만 저장하므로, 저장 후 반드시 `recalc_and_verify()`로 평가하고 #VALUE! 오류를 처리한다.

## 워크플로우

### Phase 1: 환경 파악

> **경로 표기 규칙**: 아래 예시의 `<workdir>`(작업용 임시 디렉토리)와 `<output_dir>`(최종 산출물 위치)는 호출자가 결정하는 플레이스홀더다. 실행 환경마다 다음을 사용한다:
> - **claude.ai 샌드박스**: `<workdir>` = `/home/claude`, `<output_dir>` = `/mnt/user-data/outputs`
> - **로컬/배포 환경**: `tempfile.mkdtemp(prefix='footing_')` 또는 사용자 지정 디렉토리. `<output_dir>`는 호출자가 인자로 전달.

1. 입력 파일을 작업본으로 복사: `shutil.copy(input_path, f'{workdir}/footing_test.xlsx')`
2. `analyze_workbook_basic(wb)` 호출하여 기본 정보 추출:
   - 시트 인벤토리 (이름, 행수, 열수)
   - 회사명, 기수, 결산일, 단위 (있을 때만)
   - 주석 시트 목록 (숫자 시트명 또는 '주석N' 패턴; 패턴 안 맞으면 빈 리스트)
   - 주석 번호 → 제목 매핑 (본문에서 추출; 없으면 빈 dict)
3. 추출된 기본 정보를 사용자에게 한 번 보여주고 진행.
   - **메타데이터(회사명/기수/단위)가 비어 있어도 정상**이다 — `상위 입력 요구사항` 섹션 참조. 빈 채로 다음 Phase로 넘어간다.
   - **시트 분류가 모호한 경우만** 사용자 확인 (예: 시트명이 `Sheet1, Sheet2`처럼 무의미해서 어느 게 BS인지 본문 봐도 애매할 때).

```python
import sys; sys.path.insert(0, '<skill_path>/scripts')
from footing_helpers import analyze_workbook_basic, dump_sheet_text
from openpyxl import load_workbook

wb = load_workbook('<workdir>/footing_test.xlsx')
info = analyze_workbook_basic(wb)
print(f"회사: {info['company']}")
print(f"기수: 제{info['period_current']['fiscal_year']}기")
print(f"결산일: {info['period_current']['closing_date']}")
print(f"단위: {info['unit']}")
print(f"주석: {info['note_titles']}")
```

### Phase 2: 시트 구조 직접 분석 (LLM이 수행)

**이 단계가 핵심**이다. 자동화하지 말고 LLM이 직접 시트를 읽는다.

각 재무제표/주석 시트에 대해 `dump_sheet_text(wb, sheet_name)`로 셀 내용을 출력한 후, **LLM이 직접 다음을 식별**한다:

- **위계 (Hierarchy)**: 어느 행이 총계인가, 대분류인가, 소계인가, 개별항목인가?
- **합계 매핑**: 각 소계셀(예: `D12 당좌자산`)이 어느 셀들의 합인가? (`SUM(C13:C23)`)
- **상위 합계**: 각 대분류셀(예: `D11 유동자산`)이 어느 소계들의 합인가? (`D12 + D24`)
- **부호 처리**: 어느 항목이 음수로 표시되어 있고, 그 부호가 합계 계산에 어떻게 반영되는가?

#### 한국 K-GAAP BS의 전형적 위계 (참고용, 회사마다 다름)

```
자     산
I. 유동자산                    ← 대분류 = (1) + (2)
  (1) 당좌자산                 ← 소계 = 개별항목 합
    현금및현금성자산
    매출채권
      대손충당금               ← 차감항목 (음수 표시)
    ...
  (2) 재고자산                 ← 소계
    제품
      평가충당금               ← 차감항목 (음수 표시)
    ...
II. 비유동자산                 ← 대분류 = (1) + (2) + (3) + (3)
  (1) 투자자산
  (2) 유형자산
    토지
    건물
      감가상각누계액           ← 차감항목 (음수 표시)
      국고보조금               ← 차감항목 (음수 표시)
  (3) 무형자산
  (3) 기타비유동자산           ← 같은 (3) 두 번 나오는 경우 흔함
자  산  총  계                 ← 총계 = I + II
부      채
I. 유동부채
II. 비유동부채
   퇴직연금운용자산            ← BS상 음수 표시 (퇴직급여충당부채 차감)
부  채  총  계
자      본
I. 자본금
II. 자본잉여금
III. 자본조정
IV. 기타포괄손익누계액
V. 이익잉여금
자  본  총  계                 ← I + II + III + IV + V
부채및자본총계                 ← 부채총계 + 자본총계
```

**대차균형**: 자산총계 = 부채및자본총계. 가장 중요한 검증.

회사마다 항목 위치가 다르므로 위 구조는 **참고용**이다. 반드시 시트를 직접 읽어 확인한다. 자세한 한국 감사보고서 표준 패턴은 `references/korean_audit_patterns.md` 참조.

### Phase 3: 사전 검증 (Pre-flight Check)

**검증 수식을 쓰기 전에**, LLM이 직접 Python으로 각 합계를 미리 계산해서 차이를 확인한다.

```python
# 예: BS 당좌자산 사전검증
ws = wb['BS']
expected = ws['D12'].value
calculated = sum(ws[f'C{r}'].value or 0 for r in range(13, 24))
diff = expected - calculated
print(f"당좌자산: 표시={expected:,}, 계산={calculated:,}, 차이={diff:,}")
```

이 단계의 목적:
- 수식을 쓰기 전에 **잘못된 위계 매핑** 발견
- **부호 처리 오류** 발견 (차감항목인데 양수로 더한 경우 등)
- **데이터 타입 문제** 발견 (텍스트 셀 등)
- 수동 검증으로 실제 오류와 단순 매핑 실수를 구분

차이가 발견되면 위계 매핑을 다시 확인한 후 진행한다. 사전 검증에서 모든 항목이 0으로 나와야 검증 수식 작성으로 넘어간다.

### Phase 4: 검증 수식 작성

`add_check()` 헬퍼를 사용하여 빈 열에 검증 수식을 작성한다. 검증 수식은 항상 **차이 산출** 형태.

```python
from footing_helpers import add_check, add_header

log = []  # 검증 로그 누적

# BS 검증 헤더
ws = wb['BS']
add_header(ws, 'G9', '검증(당기)')
add_header(ws, 'H9', '검증(전기)')

# 각 검증 수식을 LLM이 위계 분석 결과대로 작성
add_check(ws, log, 'BS 당좌자산 당기',
          'G12', '=D12-SUM(C13:C23)', '당기', 'Section1')
add_check(ws, log, 'BS 당좌자산 전기',
          'H12', '=F12-SUM(E13:E23)', '전기', 'Section1')

add_check(ws, log, 'BS 재고자산 당기',
          'G24', '=D24-SUM(C25:C31)', '당기', 'Section1')
# (이하 모든 소계, 대분류, 총계 항목)

add_check(ws, log, 'BS 유동자산 당기',
          'G11', '=D11-(D12+D24)', '당기', 'Section1')

add_check(ws, log, 'BS 대차균형 당기',
          'G98', '=D68-D97', '당기', 'Section1')

# CF의 부호반대 소계 (수익차감, 투자유출액, 재무유출액)는 +SUM 사용
ws_cf = wb['CF']
add_check(ws_cf, log, 'CF 수익차감 당기 (부호반대)',
          'G22', '=C22+SUM(C23:C27)', '당기', 'Section1')
```

#### 시트간 교차검증

주석의 합계와 BS/PL의 잔액이 일치하는지 검증. `Section1_Cross` 섹션 사용.

```python
from footing_helpers import sheet_ref

# 주석4 유형자산 합계 vs BS 유형자산
add_check(ws_note4, log, '주석4 vs BS 당기 유형자산',
          'L23', '=H23-BS!D39', '당기', 'Section1_Cross')

# 숫자 시트명 참조 시 sheet_ref()로 따옴표 자동 처리
add_check(ws_note19, log, '주석19 차입금 vs 주석9',
          'H21', f"=C21-{sheet_ref('9', 'C46')}", '-', 'Section1_Cross')
# 결과: =C21-'9'!C46
```

#### 주석 시트 검증

주석 시트는 합계행 위치와 컬럼 구성이 모두 다르므로, **각 주석을 직접 읽고** 검증 수식 작성.

전형적인 변동표 (유형자산, 무형자산, 퇴직급여 등)는 다음 패턴:
- **행 검증**: 마지막 컬럼 = 앞 컬럼들의 합 (`=H{row}-SUM(C{row}:G{row})`)
- **열 검증**: 합계 행 = 데이터 행들의 합 (`=C{합계행}-SUM(C{시작}:C{끝})`)

#### 데이터 타입 문제 처리

주식수("4,995,017주"), 지분율("76.48%") 같은 텍스트 셀은 SUM 연산 시 #VALUE! 오류 발생. 이런 경우 검증 제외하고 안내 텍스트로 대체:

```python
from footing_helpers import disable_check_with_note
disable_check_with_note(ws, 'F24', '주식수=텍스트(검증제외)')
```

### Phase 5: 재계산 + 오류 처리

```python
from footing_helpers import recalc_and_verify

# 워크북 저장 후 재계산
wb.save('<workdir>/footing_verified.xlsx')
result = recalc_and_verify('<workdir>/footing_verified.xlsx')
print(result)  # {'status': 'success' or 'errors_found', 'total_errors': N, ...}
```

- `success`: 모든 수식이 정상 계산됨
- `errors_found`: #VALUE!, #REF! 등이 있음. `error_summary`에서 위치 확인.

`recalc_and_verify()`는 **요약시트의 수식 텍스트 표시 문제(`=`로 시작하는 텍스트)는 자동 처리**하지만, 진짜 수식 오류는 LLM이 직접 분석해서 수정해야 한다. 흔한 케이스:
- 잘못된 시트 참조: 숫자 시트명 따옴표 누락 → `sheet_ref()` 사용
- 텍스트 셀 SUM: `disable_check_with_note()`로 처리
- 잘못된 셀 범위: 위계 분석 다시 확인

### Phase 6: 검증 결과 확인

재계산 후, 각 검증 셀의 값이 0인지 직접 확인한다.

```python
from openpyxl import load_workbook
wb_d = load_workbook('<workdir>/footing_verified.xlsx', data_only=True)

errors = []
for entry in log:
    val = wb_d[entry['sheet']][entry['cell']].value
    if isinstance(val, (int, float)) and val != 0:
        errors.append({**entry, 'diff': val})

print(f"풋팅 오류: {len(errors)}건")
for e in errors:
    print(f"  {e['sheet']}!{e['cell']} {e['name']}: 차이={e['diff']:,}")
```

차이가 0이 아닌 항목이 있으면:
1. 위계 매핑이 틀렸는지 다시 확인 (Phase 2~3 재검토)
2. 진짜 풋팅 오류인지 (작성자가 합계를 잘못 입력) → 그대로 보고
3. 부호 처리 실수인지 → 수식 수정

### Phase 7: 서술 검증 (Narrative Verification)

LLM이 회계 지식으로 다음 4영역을 직접 검증한다.

#### 7-1. 주석 참조 적절성

각 셀에서 `(주석 N, M 참조)` 패턴을 추출하고, 계정과목과 매핑이 맞는지 LLM이 회계 지식으로 판단.

```python
import re
ref_pattern = re.compile(r'\(주석\s*([\d,\s]+)(?:\s*참조)?\)')

for sheet_name in wb.sheetnames:
    ws = wb[sheet_name]
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if not isinstance(cell.value, str) or '주석' not in cell.value:
                continue
            matches = ref_pattern.findall(cell.value)
            if not matches:
                continue
            # LLM이 회계 지식으로 적절성 판단:
            # - 계정과목명에서 어떤 주석이 적절한지 추론
            # - 예: "단기차입금(주석8,12)" → 주석8은 매도가능증권, 부적절
            #       정정안: "단기차입금(주석9,12)" (주석9=차입금)
```

매핑은 회사마다 다르고 주석 번호도 다르므로 **하드코딩 매핑 테이블에 의존하지 말 것**. `info['note_titles']`(Phase 1에서 추출)를 보고 LLM이 추론한다.

자세한 적절성 매핑 가이드는 `references/reference_check_rules.md` 참조.

#### 7-2. 항목번호 순서

각 주석 시트의 B열에서 `(\d+)` 패턴으로 항목번호 추출. 회계정책 같은 트리 구조 주석은 검증 제외.

```python
import re
item_pattern = re.compile(r'^\((\d+)\)')

# 주의: 회계정책(주석2 등)은 (1)~(15) 안에 다시 (1)~(N)이 있는 트리 구조.
# 그런 경우 검증 스킵 (LLM이 주석 제목으로 판단)
SKIP_KEYWORDS = ['회계정책', '작성기준', '유의적']

for note_num, note_title in info['note_titles'].items():
    if any(kw in note_title for kw in SKIP_KEYWORDS):
        continue
    
    ws = wb[note_num]
    items = []
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=2).value
        if isinstance(v, str):
            m = item_pattern.match(v.strip())
            if m:
                items.append({'row': r, 'num': int(m.group(1)), 'text': v[:60]})
    
    nums = [i['num'] for i in items]
    expected = list(range(1, len(items) + 1))
    if nums != expected:
        # 주석16 [1,2,2,3,5] 같은 케이스 - 정정안 제시
        ...
```

#### 7-3. 당기/전기 연도 일관성

당기 결산일이 `2025-12-31`이면 정기주주총회는 `2026년`. 다음을 검증:
- 주석20 "재무제표 확정일" 셀의 연도
- 주석14 이익잉여금처분계산서의 "처분예정일" 연도
- 주석21 보고기간 후 사건의 일자

```python
import re
closing_year = info['period_current']['closing_year']  # 예: 2025
expected_agm_year = closing_year + 1  # 2026

# 각 주석에서 연도 추출하여 검증
year_re = re.compile(r'(\d{4})년')
# 주석20에서 '정기주주총회' 일자 확인 - LLM이 직접 셀 확인
```

#### 7-4. 서술 내 수치 일치

서술의 "X천원", "X백만원" 등을 추출하여 표 수치와 비교. 천원 단위 반올림 차이(±999원)는 허용.

```python
# 예: 주석3 "752,426천원" vs 주석12 매출채권할인 합계
narrative_value = 752_426 * 1000  # 천원 → 원
actual = 752_425_789
diff = abs(narrative_value - actual)
# 천원 반올림 범위 (≤999원) 내면 일치로 판정
```

#### 서술 오류 표시

발견한 오류를 셀에 직접 표시:

```python
from footing_helpers import mark_narrative_error

# 발견한 모든 서술 오류를 findings 리스트로 모은다
findings = []
findings.append({
    'type': 'inappropriate_reference',  # Section 2
    'sheet': 'BS',
    'cell': 'B75',
    'current': '단기차입금(주석8,12)',
    'issue': '주석8(매도가능증권)은 단기차입금과 무관',
    'fix': '단기차입금(주석9,12)',
})

# 셀에 직접 표시
for f in findings:
    mark_narrative_error(wb[f['sheet']], f['cell'],
                         f['issue'], f['fix'], f['type'])

wb.save('<workdir>/footing_verified.xlsx')
```

서술 발견사항의 `type` 필드별 Section 매핑:
- `inappropriate_reference` → Section 2
- `item_number` → Section 3
- `period_inconsistency` → Section 4
- `self_reference` → Section 4-2
- `narrative_value_mismatch` → Section 5

### Phase 8: 검증결과요약 시트 생성

```python
from footing_helpers import build_summary_sheet

build_summary_sheet(
    '<workdir>/footing_verified.xlsx',
    log=log,                       # Phase 4에서 누적한 검증 로그
    narrative_findings=findings,   # Phase 7에서 발견한 서술 오류
    info=info,                     # Phase 1의 기본정보
)
```

요약 시트는 다음 구조로 생성됨:
- 타이틀: 회사명 / 기수 / 결산일
- Section 1: 풋팅 검증 (Section1)
- Section 1-2: 시트간 교차검증 (Section1_Cross, 있을 때만)
- Section 2: 주석 참조 적절성 (inappropriate_reference)
- Section 3: 항목번호 순서 (item_number)
- Section 4: 당기/전기 연도 (period_inconsistency)
- Section 4-2: 자기참조 (self_reference)
- Section 5: 서술 내 수치 일치 (narrative_value_mismatch)
- Section 6: 종합 요약

각 행에는 해당 셀로 점프하는 하이퍼링크 포함. 시트명이 숫자면 자동으로 따옴표 처리됨.

### Phase 9: 마무리 재계산 및 출력

요약 시트의 하이퍼링크 수식을 평가하기 위해 한 번 더 재계산:

```python
recalc_and_verify('<workdir>/footing_verified.xlsx')

# 출력 디렉토리로 복사
import shutil
shutil.copy('<workdir>/footing_verified.xlsx',
            '<output_dir>/풋팅테스트_검증결과.xlsx')
```

`present_files` 도구로 결과 파일 제시 + 채팅에 검증 결과 요약 (검증 항목 수, 오류 건수, 핵심 발견사항).

## 주요 헬퍼 함수 시그니처

`scripts/footing_helpers.py`에서 import:

| 함수 | 역할 |
|---|---|
| `analyze_workbook_basic(wb)` | 기본 메타정보 추출 (회사명, 기수, 단위, 주석 매핑) |
| `dump_sheet_text(wb, sheet_name, max_rows=None)` | 시트 셀 내용을 사람 읽기 좋게 출력 |
| `add_check(ws, log, name, cell, formula, period, section)` | 검증 수식 1건 추가 (노란색 서식 + 로그) |
| `add_header(ws, cell, text)` | 검증 컬럼 헤더 서식 |
| `mark_narrative_error(ws, cell, issue, fix, error_type)` | 서술 오류 셀에 분홍색 + 셀메모 |
| `disable_check_with_note(ws, cell, note_text)` | 검증 불가 셀에 회색 안내 |
| `sheet_ref(sheet_name, cell)` | `BS!D11` 또는 `'9'!C46` 형태 참조 문자열 |
| `hyperlink(sheet_name, cell, display_text)` | `=HYPERLINK` 수식 생성 |
| `recalc_and_verify(path)` | LibreOffice 재계산 + #VALUE! 자동 처리 |
| `build_summary_sheet(path, log, findings, info)` | 검증결과요약 시트 생성 |

## 출력물

```
{원본파일명}_검증결과.xlsx
├── 검증결과요약           ← 맨 앞 (Section 1~6 + 결론), 하이퍼링크 포함
├── BS                     ← 원본 + G/H열 검증수식 (노란색)
├── PL                     ← 원본 + G/H열 검증수식
├── CE                     ← 원본 + 행/열 검증수식
├── CF                     ← 원본 + 검증수식 (부호처리 반영)
├── 1, 2, 3, ..., N        ← 주석 시트 + 빈 열에 검증수식
└── (서술 오류 셀: 분홍색 + 셀메모)
```

## 사용자와의 상호작용

- Phase 1 직후: 추출된 메타정보를 한 번 보여주고 진행
- Phase 2 시트 분석: 위계가 모호하거나 비표준 형식일 때 사용자에게 확인
- Phase 3 사전검증: 차이가 발견되면 사용자에게 보고 후 결정 (위계 재확인 vs 그대로 진행)
- Phase 7 서술 검증: 적절성 판단이 모호한 경우 사용자에게 확인
- Phase 9 출력: 채팅에 검증 결과 요약 표시

## 자주 빠지는 함정

1. **자동화 욕심**: 모든 시트의 위계를 정규식 하나로 처리하려는 시도. 실패한다. 시트마다 개별로 본다.
2. **부호 처리 누락**: 차감항목(감가상각누계액 등)이 음수로 표시된 것을 보지 못하고 SUM에 포함시키지 않는 실수.
3. **CF 음수 소계**: 영업CF의 "수익차감", 투자/재무CF의 "유출액" 소계는 음수로 표시되며 하위 항목은 양수. 검증식은 `=음수셀 + SUM(양수)`.
4. **숫자 시트명 따옴표 누락**: `=주석9!C46` (X), `='9'!C46` (O). `sheet_ref()` 사용.
5. **요약시트 #VALUE!**: D열에 수식 텍스트 표시할 때 `=`로 시작하면 Excel이 수식으로 해석. `recalc_and_verify()`가 자동 처리하지만, 의도치 않은 수식이 들어가지 않도록 주의.
6. **회계정책 주석 false positive**: 항목번호 순서 검증 시, 주석2(회계정책) 같이 트리 구조면 모든 (1)(2)(3)이 매칭되어 잘못 잡힘. 제목으로 스킵 결정.
7. **단위 일관성**: 모든 시트가 같은 단위인지 확인. 주석에서만 천원 단위인 경우 교차검증 시 단위 환산 필요.

## 예시 트리거

- "이 감사보고서 풋팅 검증해줘" + 엑셀 첨부
- "재무제표 합계 다 맞는지 확인"
- "감사보고서 풋팅 워크페이퍼 만들어줘"
- "이 F/S 정합성 검토 부탁"
- "BS, PL, 주석 합계 검증해서 워크페이퍼 만들어"
