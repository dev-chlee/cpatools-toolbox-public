# registry-mortgage-analysis

부동산등기부등본 PDF에서 근저당·소유권·압류·가압류 등을 추출·분석하는 Claude Skill.

## 언제 쓰나
- 다수 부동산의 등기부등본 batch 분석
- 근저당권 채권최고액 합산, 우선순위 정렬
- 권리관계 변동 이력 워크페이퍼 생성
- 담보·소유 관계 감사 검증

## 의존성
- Python ≥ 3.10
- 표준 라이브러리만 사용 (외부 패키지 없음)

PDF는 LLM(Claude) 또는 외부 OCR/추출 도구로 텍스트화한 결과를 입력으로 받음.

## 사용법

### Claude Code에서
등기부등본 PDF를 첨부하고 "근저당 분석해줘". SKILL.md 절차에 따라 LLM이 PDF 직접 읽고 권리관계 추출 + 헬퍼 스크립트로 워크페이퍼 생성.

### 워크페이퍼 생성 (CLI)
```bash
python skills/registry-mortgage-analysis/scripts/parse_registry_pdfs.py \
  --input parsed_records.json --output workpaper.json
python skills/registry-mortgage-analysis/scripts/generate_workpaper.py \
  --input workpaper.json --output workpaper.xlsx
```

## 예시
```python
import sys; sys.path.insert(0, 'skills/registry-mortgage-analysis/scripts')
import parse_registry_pdfs as parser
import generate_workpaper as gen

records = parser.parse(extracted_text)   # LLM이 추출한 텍스트
gen.write(records, 'workpaper.xlsx')
```

## 자세한 사용법
[`SKILL.md`](./SKILL.md) — 입력 포맷, 권리관계 추출 로직, 출력 워크페이퍼 구성.

## 라이선스
MIT
