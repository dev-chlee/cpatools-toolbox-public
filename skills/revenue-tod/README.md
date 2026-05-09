# revenue-tod

매출 테스트(Test of Detail) 자동화 Claude Skill — PDF·엑셀 원장에서 매출 항목을 추출·표본추출·검증.

## 언제 쓰나
- 감사 매출 표본 검증 (TOD)
- 매출원장 PDF + 세금계산서 + 입금증빙 매칭
- 표본 추출 → 검증 워크페이퍼 자동 생성

## 의존성
- Python ≥ 3.10
- `openpyxl` ≥ 3.1
- `pdfplumber` ≥ 0.10

```bash
pip install -r skills/revenue-tod/requirements.txt
```

## 사용법

### Claude Code에서
매출원장 + 증빙 PDF를 첨부하고 "TOD 진행해줘". SKILL.md 절차에 따라 LLM이 항목 추출 → 표본 선정 → 매칭 → 워크페이퍼 출력.

### 엔진 직접 호출 (CLI)
```bash
python skills/revenue-tod/scripts/tod_engine.py <input_pdf_or_xlsx>
python skills/revenue-tod/scripts/tod_workpaper.py <samples.json> <output.xlsx>
```

## 예시
```python
import sys; sys.path.insert(0, 'skills/revenue-tod/scripts')
import tod_engine, tod_workpaper

records = tod_engine.extract('매출원장.pdf')
samples = tod_engine.sample(records, n=30, seed=42)
tod_workpaper.write(samples, 'tod_workpaper.xlsx')
```

## 자세한 사용법
[`SKILL.md`](./SKILL.md) — 추출 로직, 표본 추출 기준, 매칭 룰, 워크페이퍼 포맷.

## 라이선스
MIT
