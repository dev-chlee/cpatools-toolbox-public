# scripts 맵 — revenue-tod (v0.5.1)

경계: **문서 내용을 읽어 해석하는 판단 = LLM. 그 밖(그릇·룩업·롤업·산술) = 결정형.**
금액 정합만은 "식별=LLM, 최종확정=Python 재계산"으로 authority를 결정형에 둔다.

```
sample.xlsx + mapping.json ─(범용 샘플 추출)──────────────┐
                                                         ▼
                     preflight_alignment (샘플당 증빙 폴더 준비 점검)
                                                         ▼
                     build_evidence_bundle  ──►  thin bundle (raw text + sample + profile spec)
                                                         ▼
                     prompt_builder / llm_runner  ──►  판정 프롬프트 (모델 호출 없음)
                                                         ▼
                     [현재 Claude/Codex 대화가 원문 읽고 판정]  ──►  verdicts.json (+ 금액 reconcile 값)
                                                         ▼
                     llm_schema: 스키마검증 → 산술 재검증(reconcile) → criticality 롤업
                                                         ▼
                     tod_workpaper  ──►  워크페이퍼.xlsx
```

## 결정형 코어 (남은 것 전부)

| 파일 | 역할 | 분류 |
|---|---|---|
| `tod_engine.py` | mapping 기반 샘플 추출·파일 열거·텍스트 아티팩트 로드·**중첩 증빙 로더**·파일명 잠정분류(`classify_file`)·`build_evidence_bundle`(thin)·CLI | 그릇 |
| `incoterms.py` | Incoterms **정책표**(그룹·위험이전 고정 룩업) | 룩업 |
| `llm_schema.py` | verdict 스키마검증 · 인용문과 실제 OCR 본문 일치 검증 · **`reconcile_amounts`(금액 산술 재검증=authority)** · criticality 롤업 | 검증·롤업·산술 |
| `tod_workpaper.py` | results JSON → 엑셀(Summary + 프로파일별 상세시트) | 렌더 |
| `profiles.py` | **순수 명세 데이터** — PROFILES/CHECK_LABELS/CHECK_QUESTIONS/CHECK_RECONCILE/select_profile/get_profile_spec (판단 안 함) | 명세 |
| `prompt_builder.py` | thin bundle → 판정 프롬프트(원칙 + incoterms 정책표). 모델 호출 없음 | 배관 |
| `llm_runner.py` | 현재 대화의 검토 자료·판정 파일을 JSONL/JSON으로 변환 | 배관 |

## LLM 이 하는 것
- 각 프로파일 체크 판정(거래처 동일성·금액 필드 식별·날짜 의미·증빙 정합·Incoterms 충족) + 근거 인용.
- 금액 체크는 식별한 값을 `checks[cid].reconcile.claimed_value` 에 담는다 → Python이 샘플과 재계산 대조.
- 판단 루브릭의 SSOT 는 `SKILL.md`(prompt_builder 는 그 간결 echo).

## 현재 공개 설계 (v0.5.1)

- 샘플 엑셀 구조는 소스 수정 없이 `mapping.json`으로 지정한다.
- 현재 Claude/Codex가 OCR 원문을 읽고 모든 체크의 판정과 근거 인용을 작성한다.
- Python은 판정 스키마·인용 원문·금액을 검증하고 보수적으로 롤업한다.
- 런타임 외부 패키지는 Excel 입출력을 위한 `openpyxl` 하나다.
