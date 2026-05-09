# journal-entry-standardizer

이종 ERP/엑셀 분개장을 단일 표준 스키마로 변환하는 Claude Skill.

## 언제 쓰나
- 다년간 분개장(연도별 ERP 변경, 양식 다양) 통합
- DOUZONE / SAP / Oracle EBS / 이카운트 / 수동 엑셀 등 다양한 형태를 표준 컬럼으로 매핑
- 검증 단계: 차변·대변 일치, 전표 균형, 누락·중복 점검
- 감사·결산 분석을 위한 사전 정규화

## 의존성
- Python ≥ 3.10
- `openpyxl` ≥ 3.1 (xlsx 입출력)
- 핵심 유틸(`je_utils.py`)은 표준 라이브러리만 사용

```bash
pip install -r skills/journal-entry-standardizer/requirements.txt
```

## 사용법

### Claude Code에서
분개장 xlsx 파일들을 첨부하고 "표준 분개장으로 통합해줘". SKILL.md의 Phase 1(헤더 분석) → Phase 2(변환) → Phase 4(검증) 절차에 따라 LLM이 의사코드대로 작성.

### E2E 테스트 (회귀 검증)
```bash
JE_TEST_BASE=/path/to/your/audit/data \
  python skills/journal-entry-standardizer/tests/test_e2e.py
```

환경변수 `JE_TEST_BASE` 안에 본인 분개장 데이터 폴더 지정. `tests/test_e2e.py`의 `SOURCE_FILES` dict를 본인 명명에 맞게 수정.

## 예시

```python
import sys; sys.path.insert(0, 'skills/journal-entry-standardizer/scripts')
from je_utils import (
    safe_num, parse_date, derive_year, derive_month, derive_quarter,
    parse_account_code, normalize_code, analyze_header
)

info = analyze_header('2024년 분개장.xlsx')
# {'header_row': 2, 'columns': {...}, 'pattern': 'single_row', ...}
```

## 자세한 옵션·패턴
- [`SKILL.md`](./SKILL.md) — Phase별 의사코드, 표준 스키마, 검증 룰
- [`references/common_erp_patterns.md`](./references/common_erp_patterns.md) — ERP별 헤더 패턴

## 라이선스
MIT
