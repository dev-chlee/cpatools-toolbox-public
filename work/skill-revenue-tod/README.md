# revenue-tod


매출 Test of Details(TOD) 자동화 Claude·Codex Skill — 감사 샘플(전표)을 외부 증빙으로 대사해 검증 워크페이퍼를 생성한다.

## 개념

샘플리스트의 한 행 = 장부에 기록된 매출(=회계전표)이며 **검증 대상**이다. TOD 는 그 전표를
외부 증빙(Invoice·BL·세금계산서·계약서…)으로 입증하는 절차다. 회계전표는 증빙이 아니라
대상이므로 증빙 목록에 포함하지 않는다.

이 스킬은 OCR을 제공하지 않는다. 원문 PDF/이미지(스캔 포함)는 **사용자가 미리 텍스트
(`.txt/.md/.json`)로 변환**해 각 샘플 폴더에 넣는다.

## 아키텍처 (v0.5.1 — 범용 mapping + 대화형 판단)

경계: **문서 내용을 읽어 해석하는 판단 = LLM. 그 밖(그릇·룩업·롤업·산술) = 결정형.**

```
Python : 파일 로드·분류 → thin bundle(raw text + 샘플 + 프로파일 명세)
LLM    : 원문을 읽고 체크별 판정(거래처·금액필드·날짜의미·정합성) + 근거 인용
Python : 스키마 검증 → 금액 산술 재검증(reconcile) → criticality 롤업 → 워크페이퍼 렌더
```

- Python 은 금액을 **추출·추측하지 않는다.** LLM 이 원문에서 올바른 금액 필드를 식별하고,
  Python 은 그 값을 샘플과 **재계산 대조**(authority)한다 — 문서 어딘가에 같은 숫자가 있다는
  이유만으로 Pass 하지 않는다.

매출유형별 **검증 프로파일**을 적용한다 (코드 수정 없이 프로파일 추가로 확장):

| 프로파일 | 증빙 구성 | 검증(샘플↔증빙) |
|---|---|---|
| **해외매출** (`overseas`) | Invoice·PO·BL/AWB·POD(D조건) | 주문·빌링·인도·Incoterms·도착·금액·증빙세트 정합 |
| **국내매출** (`domestic`) | 세금계산서·거래명세서·구매주문서 | 세금계산서·거래명세서·금액 종합·증빙세트 정합 |
| **용역매출** (`service`) | 세금계산서·계약서 (물류증빙 없음) | 세금계산서·계약서(거래처/금액/기간)·금액 종합·증빙세트 정합 |

Incoterms 는 규칙/LLM 경계를 분리한다. `scripts/incoterms.py` 가 그룹·위험이전 지점을 고정 조회하고,
LLM 은 제출 증빙이 그 지점을 입증하는지만 판단한다.

| Group | 조건 | 위험이전 |
|---|---|---|
| E / F / C | EXW / FCA·FAS·FOB / CFR·CIF·CPT·CIP | 출발지 |
| D | DAP·DPU·DDP (DAT=legacy) | 도착지 |

판단 루브릭(중계무역 CI vs 매입 INV/PL, 국내 공급가액=공급대가÷1.1, party 역할, 날짜 의미 등)의
SSOT 는 [`SKILL.md`](./SKILL.md) 이다.

## 언제 쓰나
- 감사 매출 표본 검증 (TOD)
- 매출 증빙(세금계산서·Invoice·BL·계약서) 분류·대사
- 표본 → 검증 워크페이퍼(엑셀) 자동 생성

## 의존성
- Python ≥ 3.10, `openpyxl` ≥ 3.1

런타임 외부 패키지는 `openpyxl` 하나다.

```bash
python scripts/setup_venv.py             # 선택: .venv 생성 + 설치
pip install -r requirements.txt          # 공개본 직접 설치
```

## 사용법

### Claude / Codex에서
샘플리스트(엑셀)와 증빙 폴더(샘플당 1폴더, 판독문은 TXT·MD·JSON)를 주고
"매출 TOD 전수 실행해줘"라고 요청한다. Claude/Codex는 명확한 매핑과 알려진 매출유형은
스스로 처리하고, 필수 열이나 매출유형을 신뢰성 있게 정할 수 없을 때만 질문한다.
`SKILL.md` 절차에 따라 샘플 추출 → 프로파일 선택 → **증빙 원문을 읽어 verdict 작성** →
Python 검증·재계산·롤업 → 워크페이퍼 생성 → 건수·시트 재검증까지 완료한다.

### CLI (직접 호출)
```bash
# 1) Claude/Codex가 엑셀 구조를 확인해 mapping.json 작성 후 판단 재료 생성
python scripts/tod_engine.py <sample.xlsx> --mapping mapping.json --evidence <증빙폴더> --bundles-out bundles.json

# 2) 현재 Claude/Codex가 bundles.json 원문을 읽고 verdicts.json 작성
# 아래 명령은 검토 자료와 대화 판정을 JSONL로 보관할 때만 사용하는 로컬 변환
python scripts/llm_runner.py bundles.json --prompts-out prompts.jsonl
python scripts/llm_runner.py bundles.json --responses responses.jsonl --verdicts-out verdicts.json

# 3) verdict JSON 검증·산술재검증·롤업 → 결과 JSON
python scripts/tod_engine.py <sample.xlsx> --mapping mapping.json --evidence <증빙폴더> --verdicts verdicts.json --out results.json

# 4) 결과 JSON → 엑셀 워크페이퍼 (Summary + 프로파일별 상세)
python scripts/tod_workpaper.py results.json 매출TOD_워크페이퍼.xlsx "회사명" "감사기간"
```

> Claude/Codex가 샘플리스트의 시트·행·열을 확인해 `mapping.json`을 작성한다.
> 범용 mapping 형식은 `references/sample-mapping.md`를 따른다. 증빙은 샘플당 폴더 1개
> (폴더명=샘플 folder)로 정리한다(얼라인=사용자 책임); 스킬은 flat 파일과
> `<샘플>/<문서폴더>/<doc>.md` 중첩 구조를 모두 로드한다.

## 설정

| 변수 | 의미 | 기본값 |
|---|---|---|
| `CPA_SKILLS_STORAGE` | 보관소 루트. 증빙은 `<루트>/skill-revenue-tod/input/evidence`(`--evidence`), 결과는 `.../output/`(`--out`) | `~/cpa-skills-data` |

실자료와 산출물은 저장소 밖 보관소에 둔다. git 저장소 안 경로에는 쓰지 않는다. 자세한 표는 `SKILL.md` 「설정」.

샘플 mapping은 클라이언트 자료마다 달라 CLI의 `--mapping`으로 명시한다. 비어 있지 않은 통합문서에서 생략하면 엔진이 오류로 종료한다.

우선순위: CLI flag > env > 기본값. `.env` 자동 로드는 없다.

## 검증 범위

개발 검증은 분류·얼라인·중첩 로더·범용 mapping·프로파일 명세·판정 스키마·원문 인용·
금액 재계산·롤업·엑셀 재개봉을 포함한다. 공개 배포 파일에는 테스트와 실제 자료를 포함하지 않는다.

## 자세한 사용법
[`SKILL.md`](./SKILL.md) — 프로파일 구동 워크플로, 판단 루브릭, verdict/reconcile 계약, 워크페이퍼 포맷.

## 라이선스
MIT
