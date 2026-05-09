# footing-verifier

한국 감사보고서·재무제표(xlsx)에 대해 풋팅(Footing) 검증을 자동화하는 Claude Skill.

## 언제 쓰나
- 감사·검토 보고서의 합계/소계 정합 검증
- 재무제표 4종(BS·PL·CE·CF) 풋팅 + 시트간 균형식
- 주석 표 합계, 주석 참조 적절성, 서술 내 수치 일치
- 검증 결과 요약 시트 + 하이퍼링크 워크페이퍼 자동 생성

## 의존성
- Python ≥ 3.10
- `openpyxl` ≥ 3.1
- (외부) **LibreOffice** ≥ 7.0 — 수식 재계산용. `--no-soffice` 옵션으로 skip 가능

```bash
pip install -r skills/footing-verifier/requirements.txt
```

## 사용법

### Claude Code에서
xlsx 파일을 첨부하고 "풋팅 검증해줘"라고 요청. SKILL.md의 Phase 1~8 절차에 따라 LLM이 시트 직접 분석 + Python 헬퍼로 검증 셀 작성·재계산·요약시트 출력.

### 다중 파일 견고성 회귀(L1)
```powershell
python skills/footing-verifier/tests/batch_runner.py <input_dir>
# 출력: skills/footing-verifier/output/<timestamp>/
#   summary.md, results.csv, results.json, results.xlsx
```

## 예시

```python
import sys; sys.path.insert(0, 'skills/footing-verifier/scripts')
from footing_helpers import (
    analyze_workbook_basic, dump_sheet_text,
    add_check, add_header, recalc_and_verify, build_summary_sheet
)
from openpyxl import load_workbook

wb = load_workbook('audit.xlsx')
info = analyze_workbook_basic(wb)            # 메타 자동 추출
ws = wb['재무상태표']
log = []
add_check(ws, log, 'BS 자산총계', 'H13', '=D13-(D8+D11)', '당기')
wb.save('audit_workpaper.xlsx')
recalc_and_verify('audit_workpaper.xlsx')    # LibreOffice 재계산
build_summary_sheet('audit_workpaper.xlsx', log, [], info)
```

## 자세한 사용법·edge case
[`SKILL.md`](./SKILL.md) — Phase 1~8 전체 절차, 비표준 입력 처리, 부호 처리, 서술 검증.

## 라이선스
MIT
