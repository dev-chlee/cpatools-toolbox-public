# 주석 참조 적절성 검증 규칙

이 문서는 한국 감사보고서에서 **계정과목 ↔ 적절한 주석번호** 매핑과 자기참조 등 서술 검증 규칙을 정리한다.

## 1. 매핑 테이블 (주제 기반)

회사마다 주석 번호가 다를 수 있으므로, **주석 번호가 아니라 주석 주제(제목)**를 기준으로 매핑해야 한다. 아래는 표준 K-GAAP 감사보고서 기준이다.

### BS 자산 항목

| 계정과목 | 적절한 주석 주제 | 표준 주석번호 (참고) |
|---|---|---|
| 매출채권 | 매출채권 양도/할인, 특수관계자 | 3, 16 |
| 대손충당금 | 매출채권 양도/할인 | 3 |
| 단기대여금 | 특수관계자 (있을 시) | 16 |
| 선급법인세 | 법인세 | 11 |
| 재고자산 | (별도 주석 없으면 미참조) | - |
| 장기금융상품 | 우발채무 (담보로 제공된 경우) | 12 |
| 장기대여금 | 특수관계자 | 16 |
| 지분법적용투자주식 | 지분법적용투자주식 | 7 |
| 매도가능증권 | 매도가능증권 | 8 |
| 단기매매증권 | 단기매매증권 | 8 |
| 유형자산 | 유형자산, 우발채무(담보) | 4, 12 |
| 무형자산 | 무형자산 | 5 |
| 임차보증금 | 우발채무(담보) | 12 |

### BS 부채 항목

| 계정과목 | 적절한 주석 주제 | 표준 주석번호 (참고) |
|---|---|---|
| 매입채무 | 특수관계자 | 16 |
| 단기차입금 | 차입금, 우발채무(담보) | 9, 12 |
| 유동성장기차입금 | 차입금, 우발채무(담보) | 9, 12 |
| 장기차입금 | 차입금, 우발채무(담보) | 9, 12 |
| 사채 | 사채 (별도 주석) | (회사별) |
| 퇴직급여충당부채 | 퇴직급여 | 10 |
| 퇴직연금운용자산 | 퇴직급여 | 10 |
| 충당부채 | 충당부채/우발채무 | 12 |

### BS 자본 항목

| 계정과목 | 적절한 주석 주제 |
|---|---|
| 자본금 | 회사의 개요(주주현황), 자본금 및 자본잉여금 |
| 자본잉여금 | 자본금 및 자본잉여금 |
| 자본조정 (자기주식 등) | 자본금 및 자본잉여금 |
| 기타포괄손익누계액 | 포괄손익계산서, 지분법적용투자주식 |
| 지분법자본변동 | 지분법적용투자주식 |
| 이익잉여금 | 이익잉여금 |

### PL 항목

| 계정과목 | 적절한 주석 주제 |
|---|---|
| 매출액 | 특수관계자 (있을 시) |
| 매출원가 | 특수관계자 (있을 시) |
| 경상연구개발비 | 무형자산 (개발비 회계처리 관련) |
| 퇴직급여 | 퇴직급여 |
| 감가상각비 | 유형자산 |
| 무형자산상각비 | 무형자산 |
| 대손상각비 | 매출채권 등 |
| 법인세비용 | 법인세 |
| 당기순이익 | 포괄손익계산서, 이익잉여금 |
| 지분법손익 | 지분법적용투자주식 |
| 외화환산손익 | (회계정책 주석에서 다룸, 별도 참조 보통 없음) |

## 2. 매핑 동적 구성 알고리즘

```python
def build_dynamic_mapping(note_titles):
    """
    note_titles: dict like {'4': '유형자산', '5': '무형자산', '9': '차입금', ...}
    """
    mapping = {}
    
    # 주석 제목으로부터 역매핑 구축
    title_to_num = {v: k for k, v in note_titles.items()}
    
    def find_note(keyword):
        """키워드를 포함하는 주석 번호들 반환"""
        return [num for num, title in note_titles.items() if keyword in title]
    
    # 표준 매핑 적용
    rules = [
        ('매출채권', ['매출채권', '특수관계자']),
        ('단기차입금', ['차입금', '우발채무', '약정']),
        ('장기차입금', ['차입금', '우발채무', '약정']),
        ('유동성장기차입금', ['차입금', '우발채무', '약정']),
        ('유형자산', ['유형자산', '우발채무', '약정']),
        ('무형자산', ['무형자산']),
        ('지분법적용투자주식', ['지분법']),
        ('매도가능증권', ['매도가능증권', '유가증권']),
        ('퇴직급여충당부채', ['퇴직급여']),
        ('퇴직연금운용자산', ['퇴직급여']),
        ('자본금', ['자본금', '회사의 개요']),
        ('자본잉여금', ['자본금', '자본잉여금']),
        ('이익잉여금', ['이익잉여금']),
        ('지분법자본변동', ['지분법']),
        ('당기순이익', ['포괄손익', '이익잉여금']),
        ('법인세', ['법인세']),
        ('경상연구개발비', ['무형자산']),
    ]
    
    for account, keywords in rules:
        valid_notes = set()
        for kw in keywords:
            valid_notes.update(find_note(kw))
        if valid_notes:
            mapping[account] = sorted(valid_notes)
    
    return mapping
```

## 3. 주석 참조 추출 정규식

```python
import re

# (주석 N), (주석 N, M), (주석 N 참조), (주석 N, M 참조)
ref_pattern = re.compile(r'\(주석\s*([\d,\s]+)(?:\s*참조)?\)')

# (주 N), (주 N, M) ← 짧은 형태도 있음
short_ref_pattern = re.compile(r'\(주\s*(\d+(?:\s*,\s*\d+)*)\)')

# 셀 텍스트에서 모든 주석 참조 추출
def extract_refs(text):
    refs = []
    for match in ref_pattern.findall(text):
        nums = [n.strip() for n in match.split(',') if n.strip()]
        refs.extend(nums)
    return refs
```

## 4. 자기참조 검출

주석 N 시트 안에서 `(주석 N 참조)`가 있으면 자기참조 의심. 단, 같은 주석 내 다른 항목 참조는 정상이므로 다음 케이스만 오류로 간주:

- 주석 시트의 첫 데이터 셀(B7~B10 부근)에서 자기 번호 참조
- 표 헤더 셀에서 자기 번호 참조

```python
def detect_self_reference(wb, note_num):
    ws = wb[note_num]
    for row in ws.iter_rows(values_only=False):
        for cell in row:
            if isinstance(cell.value, str) and '주석' in cell.value:
                refs = extract_refs(cell.value)
                if note_num in refs:
                    return cell.coordinate, cell.value
    return None
```

## 5. 항목번호 순서 검증

주석 시트의 B열에서 항목번호 패턴 `(\d+)`을 추출하여 순서 검증.

```python
import re

def check_item_order(ws):
    pattern = re.compile(r'^\((\d+)\)')
    items = []
    for row in range(1, ws.max_row + 1):
        val = ws[f'B{row}'].value
        if isinstance(val, str):
            m = pattern.match(val)
            if m:
                items.append({
                    'cell': f'B{row}',
                    'num': int(m.group(1)),
                    'text': val[:60]
                })
    
    actual = [i['num'] for i in items]
    expected = list(range(1, len(items) + 1))
    
    errors = []
    if actual != expected:
        for i, item in enumerate(items):
            if item['num'] != i + 1:
                errors.append({
                    'cell': item['cell'],
                    'actual_num': item['num'],
                    'expected_num': i + 1,
                    'text': item['text'],
                })
    return errors
```

**주의**: 주석 16같이 항목이 (1) 현황 → (2) 거래내용 → (3) 채권채무 → (4) 자금거래 → (5) 지급보증으로 이어져야 하는데, 작성자가 (3)을 빠뜨리고 [1, 2, 2, 3, 5] 같은 순서로 잘못 매기는 경우가 흔하다.

## 6. 당기/전기 연도 일관성 규칙

### 핵심 규칙

**당기 회계연도 종료일의 다음 해**에 정기주주총회가 개최되어야 한다.

```
예: 제7(당)기 2025-12-31 종료
    → 정기주주총회: 2026년 (보통 3월~5월)
    → 이익잉여금처분 예정일: 2026년 4월 28일 (보통)
    → 전기(제6기) 처분확정일: 2025년 3월 31일 (전기 정기주총)
```

### 검증 절차

1. BS B6에서 당기 결산일 추출 (예: "제 7(당) 기 2025년 12월 31일 현재")
2. 기준 연도 + 1 = 정기주총 연도
3. 다음 셀들 검증:
   - 주석14 처분예정일 (보통 C21): 정기주총 연도와 일치 여부
   - 주석14 전기 처분확정일 (보통 E21): 기준연도와 일치 여부
   - 주석20 재무제표 확정일: 정기주총 연도와 일치 여부
   - 주석21 보고기간 후 사건 일자: 정기주총 연도 또는 그 이후

```python
def check_period_consistency(wb):
    import re
    bs = wb['BS']
    # B6에서 연도 추출
    text = bs['B6'].value or ''
    m = re.search(r'(\d{4})년\s*\d+월\s*\d+일', text)
    if not m:
        return [{'error': 'BS 결산일 추출 실패'}]
    
    closing_year = int(m.group(1))
    expected_agm_year = closing_year + 1
    
    findings = []
    
    # 주석20 확정일
    if '20' in wb.sheetnames:
        for row in wb['20'].iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and '주주총회' in cell.value:
                    years = re.findall(r'(\d{4})년', cell.value)
                    for y in years:
                        if int(y) != expected_agm_year:
                            findings.append({
                                'sheet': '20', 'cell': cell.coordinate,
                                'actual_year': int(y),
                                'expected_year': expected_agm_year,
                                'text': cell.value,
                            })
    return findings
```

## 7. 서술 내 수치 일치 검증

서술에 등장하는 숫자(특히 "X천원", "X백만원")를 추출하여 표의 수치와 비교한다.

### 자주 검증해야 하는 패턴

```python
patterns = [
    # "752,426천원" → 천원 단위
    re.compile(r'([\d,]+)천원'),
    # "10,000백만원" → 백만원 단위
    re.compile(r'([\d,]+)백만원'),
    # "10,000원" → 원 단위
    re.compile(r'([\d,]+)원'),
    # "5,811,076천원입니다(단위: 천원)"
    re.compile(r'([\d,]+)\s*(?:천원|백만원|원)\s*입니다'),
]
```

### 천원 단위 반올림 허용 차이

```python
def values_match(narrative_value, table_value, unit='천원'):
    """서술값과 표 값의 일치 여부 (반올림 허용)"""
    if unit == '천원':
        # 표 값을 천원으로 환산하고 반올림
        table_in_thousand = round(table_value / 1000)
        return narrative_value == table_in_thousand
    elif unit == '백만원':
        table_in_million = round(table_value / 1_000_000)
        return narrative_value == table_in_million
    else:
        return narrative_value == table_value
```

## 8. 흔한 서술 오류 5종

이 스킬이 가장 자주 발견하는 서술 오류 5가지:

1. **부적절 주석 참조**: BS/PL의 계정과목 옆에 잘못된 주석 번호 표기 (예: 단기차입금에 "주석8" 표기)
2. **항목번호 중복/누락**: 주석 내 (1), (2), (3) 순서가 (1), (2), (2), (3)으로 중복 또는 (1), (2), (4)로 누락
3. **당기/전기 연도 오기**: "재무제표 확정일" 또는 "처분예정일"이 결산일+1년이 아닌 결산연도로 잘못 표기
4. **자기참조**: 주석 N 안에서 (주석 N 참조)로 자기 자신을 참조
5. **서술-표 수치 불일치**: 서술의 천원 단위 수치가 표 합계와 불일치 (반올림 차이 초과)

## 9. 우선순위 및 강도

서술 오류는 **풋팅 오류만큼 critical하지는 않지만**, 감사보고서의 신뢰성을 떨어뜨리므로 모두 검출 후 정정 권고 대상으로 보고해야 한다.

| 오류 유형 | 심각도 | 자동 검출 가능성 |
|---|---|---|
| 주석 참조 적절성 | 중 | 매핑 테이블 기반 가능 |
| 항목번호 순서 | 저 (가독성) | 정규식 기반 100% |
| 당기/전기 연도 | 고 (법적 효력 영향) | 정규식 기반 100% |
| 자기참조 | 저 | 정규식 기반 100% |
| 서술-표 수치 일치 | 중 | 패턴 추출 + 매칭 |
