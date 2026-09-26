---
name: revenue-tod
title: 매출테스트 자동화
description: |
  매출 Test of Details (TOD) 감사 절차를 수행하는 스킬. 샘플링된 매출 리스트(엑셀)와 샘플별 OCR 텍스트 증빙 폴더를 입력받아, 매출유형별 검증 프로파일(해외매출/국내매출/용역매출)에 따라 Claude/Codex가 증빙을 직접 판독하고 상세 워크페이퍼(엑셀)를 생성한다.
  사용 시점: (1) 매출 TOD 수행 시, (2) 매출 증빙 검토/대사 시, (3) 수출·중계무역·국내매출·용역매출 증빙 테스트 시, (4) 감사 샘플 증빙 대조 워크페이퍼 작성 시.
  "매출 테스트", "TOD", "증빙 대사", "매출 검증", "워크페이퍼", "샘플 테스트", "용역매출", "해외매출", "국내매출 증빙" 등의 표현이 나오면 반드시 이 스킬을 사용한다.
category: audit
tags: [감사, 매출, TOD, 증빙]
version: 0.6.2
---

# 매출 Test of Details (TOD) 자동화 스킬

## 개요

외부감사 시 매출 샘플에 대한 Test of Details 수행을 지원한다.
샘플링 엑셀과 샘플별 OCR 텍스트 증빙 폴더를 입력받아, 각 증빙을 분류·판독한 뒤 샘플 정보와 교차대사하여 상세 결과를 엑셀 워크페이퍼로 출력한다. 원문 PDF는 문서 목록과 분류 힌트로 보존하지만 본 스킬이 직접 OCR하지 않는다.

**핵심 개념 — 회계전표는 검증 "대상"이다.** 샘플리스트 한 행 = 장부에 기록된 매출(=회계전표)이며, TOD 는 그 전표를 외부 증빙(Invoice·BL·세금계산서·계약서…)으로 입증하는 절차다. 따라서 회계전표는 증빙 목록에 넣지 않고, 증빙으로 전표를 대사한다.

**범위:** 이 스킬은 **샘플(전표) ↔ 증빙 일치 검증(TOD)** 만 한다. 특수관계자거래·이전가격·매출 cutoff·완전성(completeness) 등은 **별도 감사 절차**이며 이 스킬이 판정하지 않는다(아래 "추가 권고 항목"으로 참고만 제시).

## 검증 프로파일 (profiles.py)

매출유형마다 기대 증빙·검증 항목이 다르므로 **검증 프로파일**로 분리한다. 프로파일은 각 체크에 대해 **무엇을 검증(`CHECK_QUESTIONS`)·무엇을 조서화(`CHECK_REPORT`)·무엇을 금액 재검증(`CHECK_RECONCILE`)** 까지 정의하는 **검증 프로그램(audit program)** 이다. `scripts/profiles.py` 의 **순수 명세 데이터**(`PROFILES`·`CHECK_LABELS`·`CHECK_QUESTIONS`·`CHECK_REPORT`·`CHECK_RECONCILE`)로 선언되며 판단 로직은 담지 않는다. **새 유형 추가 = dict 항목 추가**로 코드 본체 수정 없이 확장된다(리포트 규격도 함께 따라옴).

| 프로파일 (`id`) | 증빙 구성 (회계전표 제외) | 검증 체크 (순서) |
|---|---|---|
| 해외매출 (`overseas`) | Invoice·PO·BL/AWB·POD(D조건) | order·billing·shipping·incoterms·pod·amount_inv·evidence_consistency |
| 국내매출 (`domestic`) | 세금계산서·거래명세서·구매주문서 | tax_invoice·trans_stmt·customer_po·amount_cross·evidence_consistency |
| 용역매출 (`service`) | 세금계산서·계약서 (물류증빙 없음) | tax_invoice·contract·amount_cross·evidence_consistency |

- 각 체크는 `criticality`(`critical`/`info`/`optional`) 를 가진다. **`critical` 체크가 Fail → 샘플 종합결과 Fail**; 그 외 Fail/Exception 또는 누적 exception → Exception.
- **프로파일 선택 = 매출유형 컬럼 우선 + LLM 보정**: `profiles.TYPE_TO_PROFILE` 가 샘플의 `type`(국내매출/중계무역/직수출/수출/해외매출/용역매출/용역)을 프로파일로 매핑한다. 매핑 미상이면 `select_profile()` 이 `None` 을 반환 → LLM(또는 `--profile`)이 보정한다.

> 새 프로파일 추가 예: `PROFILES["royalty"]={"display":"로열티매출","evidence":[...],"checks":[("tax_invoice","critical"),("contract","critical"),("amount_cross","info")]}` 후 `CHECK_LABELS`/`CHECK_QUESTIONS`/`CHECK_RECONCILE`·`TYPE_TO_PROFILE` 에 항목 추가.

## 아키텍처 — 경계: 문서 읽는 판단 = LLM, 그 밖 = 결정형 (v0.5.1)

**판단 주체는 이 스킬을 실행 중인 Claude 또는 Codex다.** 현재 대화의 기본 파일 읽기·추론·파일 작성 기능으로 증빙 원문을 읽고 verdict JSON을 작성한다. 별도 모델 클라이언트·호출 서비스·인증키·모델별 과금 설정을 만들거나 요구하지 않는다. Python은 로컬 파일 준비·판정 검증·계산·엑셀 생성만 담당한다.

전수 실행 요청을 받으면 표본 목록 순서로 모든 건을 검토한다. 분량이 크면 몇 건씩 읽고 판정을 저장하며 이어간다. 자동으로 판정해 주는 별도 프로그램이 없다는 이유로 중단하거나 일부 표본만 처리하지 않는다. 완료 전 전체 표본 수·고유 ID·필수 체크 수를 결과와 대조하고, 읽지 못한 증빙은 해당 건에 사유를 기록한다.

```text
Python: 파일 로드·잠정분류·thin bundle(raw text + 샘플 + 프로파일 명세)
Claude/Codex: 현재 대화에서 증빙 원문을 읽고 체크별 verdict 작성(거래처·금액필드·날짜의미·정합성 판단 + 근거 인용)
Python: 스키마 검증 → 금액 산술 재검증(reconcile) → criticality 롤업 → 워크페이퍼 렌더
```

- **Python 은 금액·거래처·날짜를 추출·추측하지 않는다.** bundle 은 문서 **원문 텍스트**를 그대로 담고(후보 리스트 없음), LLM 이 사람 감사인처럼 라벨·표구조·문맥을 읽어 필드를 식별한다. (규칙기반 후보추출은 실데이터에서 주소·전화·사업자번호를 긁고 정작 청구금액은 못 떠서 폐기함.)
- **금액 authority = Python 재계산.** LLM 이 금액 체크에서 식별한 값을 `checks[cid].reconcile.claimed_value` 에 담으면, Python(`llm_schema.reconcile_amounts`)이 샘플 금액과 **독립 재계산 대조**한다. 불일치하거나 Pass인데 claimed_value 가 없으면 해당 체크를 **Exception 으로 강등**한다 — LLM 의 착오·환각 매칭을 잡는 최종 방어선.

### verdict 계약 (LLM 출력 형식)

LLM 은 샘플 1건마다 프로파일 checks 순서대로 아래 JSON 을 만든다. Python(`llm_schema`)이 검증·재검증·롤업한다.

```json
{
  "sample_folder": "SAMPLE-001",
  "profile": "overseas",
  "checks": {
    "amount_inv": {
      "result": "Pass",
      "confidence": "high",
      "summary": "대고객 CI 청구금액 USD 314,159.26 = 샘플 fc(가상 예시)",
      "evidence": [{"doc_id": "D002", "filename": "CI-DEMO-0001", "field": "Total", "quote": "USD 314,159.26"}],
      "issues": [],
      "manual_review_required": false,
      "reconcile": {"claimed_value": 314159.26, "target": "fc", "doc_id": "D002", "field": "CI Total"}
    }
  }
}
```

필수 규칙:
- `checks`에는 선택한 프로파일의 모든 체크 ID가 정확히 한 번씩 있어야 한다. 일부 체크만 작성하거나 임의 체크를 추가하면 스키마 오류다.
- `result`(Pass|Exception|Fail|N/A)·`confidence`(high|medium|low)·`summary`·`manual_review_required` 는 **모든 체크 필수**. 누락 시 스키마 오류 → 전체 Exception.
- **critical 체크의 Pass 는 `evidence` 인용(quote) 필수.**
- **증빙 준비 상태가 LLM 판정보다 우선한다.** 증빙 폴더가 없거나 비어 있으면 `Fail`, 파일은 있지만 읽을 수 있는 OCR 본문이 전혀 없으면 `Exception`이다. 종합판정·개별 체크·최종 조서에 같은 사유를 반영한다. 기존 `Fail`은 완화하지 않으며 verdict 누락·스키마 오류 사유도 보존한다. Python은 인용문이 실제 OCR 본문에 존재하는지 확인하지만, 그 인용이 판단을 충분히 뒷받침하는지는 Claude/Codex가 책임진다.
- **summary 작성 = 읽기 쉬운 한 문장**: 각 체크 summary 는 프로파일 명세의 `report` 문형을 따라 **감사인이 읽기 쉬운 자연스러운 한 문장**으로 쓴다(태그·라벨 금지). 한 문장에 **검증대상(거래처·금액·번호) + 확인한 증빙(파일명·문서번호)과 그 안의 확인 내용 + 결과([일치]/[차이]/[수동확인])** 를 녹인다. 가상 예시: `거래처 ACME의 PO(PO-DEMO-0001, PO No DEMO-0001)에서 발주 품목을 확인함 — 발주처 일치.` "일치"만 쓰지 않고 값·문서·근거를 담는다.
- `confidence=low` 또는 `manual_review_required=true` → 최소 Exception 으로 롤업.
- **금액 재검증 대상 = `amount_inv`·`tax_invoice`·`amount_cross`·`contract`.** 이들을 Pass 로 낼 땐 반드시 `reconcile.claimed_value`(**순수 숫자**)를 담는다 — 없으면 Python 이 Exception 으로 강등. (billing 등 정성 체크는 reconcile 불필요.)
- `reconcile.target`: `fc`(해외 외화금액, 없으면 krw 폴백) / `krw` / `supply_value`(국내 공급가액=krw 또는 공급대가=krw×1.1).
- 여러 표본의 `verdicts.json`은 `{"verdicts": [<표본별 verdict>, ...]}` 형식을 사용한다. `sample_folder`는 샘플 mapping의 `folder`와 정확히 일치하고 중복되지 않아야 한다.

### Incoterms 정책 경계 (결정형 룩업)

그룹·위험이전 지점은 Python 고정 정책표(`scripts/incoterms.py`)가 확정한다. LLM 은 이 기준을 바꾸지 않고 제출 증빙이 그 지점을 입증하는지만 판단한다.

| Group | 조건 | 위험이전 | LLM 판단 |
|---|---|---|---|
| E / F / C | EXW / FCA·FAS·FOB / CFR·CIF·CPT·CIP | 출발지 | 출고·선적·운송개시 증빙 충분한가 |
| D | DAP·DPU·DDP (DAT=legacy) | 도착지 | POD·배송완료·도착지 인도 증빙 충분한가 |

## 판단 루브릭 (LLM SSOT — 실데이터 검증 반영)

체크별 판단 질문은 `profiles.CHECK_QUESTIONS` 에 요약되어 프롬프트에 실린다. 상세 기준:

- **금액 필드 식별**: 문서 어딘가에 같은 숫자가 있다는 이유로 Pass 하지 않는다. **라벨된 필드**를 읽는다 — 공급가액 ≠ 세액 ≠ 합계, 운임·보험료·VAT·환율·수량·단가와 구분.
- **중계무역 이중송장**: 중계무역 폴더엔 대고객 **CI(매출)** 와 中國→韓國 **INV/PL(매입원가)** 이 함께 온다. 금액 대조는 **대고객 CI(매출)** 를 본다. 매입 INV/PL 을 매출로 오인 금지.
- **국내 공급가액**: 샘플 매출액(전표 대변)=공급가액. **거래명세표 합계(공급대가)=공급가액×1.1** 관계로 교차검증. reconcile target=`supply_value`(공급가액=krw 또는 공급대가=krw×1.1 허용).
- **거래처 동일성**: 샘플 거래처 ↔ 증빙상 비교 대상 party(buyer/customer/공급받는자)가 실질적으로 같은 상대방인가. seller/운송사/배송지 등 다른 역할과 구분하고, 부분문자열·법인격 표기(`주식회사`·`Inc`)만으로 일치 처리 금지. (**관계사 여부·이전가격 등은 이 스킬 범위 밖** — 오직 샘플↔증빙 party 일치만 본다.)
- **날짜 의미**: 선적일·출고일·도착일·세금계산서 작성일·계약기간·귀속기간을 구분. 첫 날짜를 매출인식일로 가정 금지. **OCR 날짜 오독**(예: 연도 2015/2005 등)을 sanity check.
- **증빙 세트 정합성**(`evidence_consistency`, info): CI/PO/BL/POD/세금계산서/계약서 번호·party·금액·날짜 흐름이 같은 거래인지 교차 확인.
- **얼라인·OCR 은 사용자 책임**: 증빙은 샘플당 폴더 1개(폴더명=샘플 folder), 원문은 사용자가 TXT·MD·JSON으로 사전 변환. 스킬은 OCR 하지 않는다.
- **Incoterms 누락/상충**: 샘플 운임조건이 없거나(값 `0`·공백) 증빙 간 상충(예: CI=EXW vs PO=CPT)이면 → `incoterms`=**Exception**(위험이전 지점 확정 불가 → 회사 질의 대상). 확정된 D조건이 없으면 `pod`=`N/A`(판단 보류)로 둔다.
- **critical 체크의 의심 처리(Pass+수동검토 vs Fail)**: critical 체크(billing/tax_invoice/contract)에서 **party·금액에 의심은 있으나 명백한 불일치·증빙부재는 아닌** 경우 → `result="Pass"` + `manual_review_required=true`(롤업이 종합 Exception 유도). **증빙 자체 부재 또는 명백한 불일치만 `Fail`.**

## 워크플로우

### AI 실행 계약

- 사용자가 전수 실행을 요청하면 모든 표본을 끝까지 처리한다. 증빙이 없거나 읽히지 않는 표본도 중단 사유가 아니며 각각 `Fail` 또는 `Exception`으로 남기고 다음 표본으로 진행한다.
- 시트·열 의미와 매출유형이 명확하면 mapping과 프로파일을 스스로 확정해 진행하고, 진행 보고에 적용 내용을 적는다. 필수 열을 둘 이상으로 해석할 수 있거나 알려지지 않은 매출유형을 확정할 수 없을 때만 한 번에 모아 질문한다.
- 실자료와 산출물은 저장소 밖 **보관소**에 둔다. `<보관소>` 는 환경변수 `CPA_SKILLS_STORAGE` 가 있으면 `$CPA_SKILLS_STORAGE/skill-revenue-tod`, 없으면 `~/cpa-skills-data/skill-revenue-tod` 이고 그 아래 `input`(샘플리스트·`evidence/`)·`work`·`output`·`logs` 칸을 쓴다. 기본 산출물은 `<보관소>/output/` 의 `sample-mapping.json`, `bundles.json`, `verdicts.json`, `results.json`, `revenue-tod-workpaper.xlsx`다. 사용자가 다른 출력 경로를 지정하면 그 경로를 따른다. **git 저장소 안 경로에는 쓰지 않는다** — 스크립트가 종료코드 2로 거부한다.
- 판정은 별도 모델 연결 없이 현재 Claude/Codex가 수행한다. bundle을 여러 묶음으로 나눠 읽어도 되지만 표본별 판정을 즉시 저장하고 누락 없이 이어간다.
- 완료 전에 `샘플 수 = 고유 folder 수 = bundle 수 = verdict 수 = result 수`를 확인한다. 엑셀을 재개봉해 Summary 집계와 상세 시트 수를 확인하고, 최종 보고에 처리 건수·Pass/Exception/Fail·산출물 경로·수동검토 필요 사항을 적는다.

기본 실행 순서:

```bash
python scripts/tod_engine.py <sample.xlsx> --mapping <보관소>/output/sample-mapping.json --bundles-out <보관소>/output/bundles.json
# 현재 Claude/Codex가 모든 bundle의 OCR 본문을 읽고 <보관소>/output/verdicts.json 작성
python scripts/tod_engine.py <sample.xlsx> --mapping <보관소>/output/sample-mapping.json --verdicts <보관소>/output/verdicts.json --out <보관소>/output/results.json
python scripts/tod_workpaper.py <보관소>/output/results.json <보관소>/output/revenue-tod-workpaper.xlsx "<회사명>" "<감사기간>"
```

### Phase 1: 샘플 mapping과 증빙 준비 스캔

먼저 샘플 엑셀과 증빙 루트를 스캔한다. 명확한 항목은 바로 진행하고 결과를 기록한다.

#### 1-1. 샘플리스트 필드 탐지 → mapping 생성·검증
표준 샘플리스트 템플릿은 없다. 모양이 매번 다르므로 **Claude/Codex가 xlsx를 읽어 필드를 탐지**한다.
- **최소 필수: sample number(식별자/폴더), 거래처명, 금액.** (+있으면 매출유형·CI번호·Incoterms·통화·외화금액·전표번호)
- Claude/Codex가 시트·헤더·행범위를 훑어 각 필드가 **어느 열인지 판단**하고 적용 내용을 진행 보고에 남긴다.
- **필수 필드를 신뢰성 있게 찾지 못한 경우에만 질문한다.** mapping을 작업 출력 폴더의 JSON으로 작성하고 `scripts/tod_engine.py --mapping`에 전달한다. 스킬 소스를 클라이언트별로 수정하지 않는다.
- mapping 형식과 검증 규칙은 [references/sample-mapping.md](references/sample-mapping.md)를 따른다. 실제 실행에서 mapping을 만들 때만 이 문서를 읽는다.
- **주의(실데이터):** 한 시트에 매출유형별 **하위표가 여러 개 쌓이고 스키마가 다를 수 있다**(예: 해외=선적/CI 리스트, 국내=GL 전표 덤프). 이 경우 mapping의 `sections`를 유형별로 나눈다.
- **주의(해외 금액):** 해외 금액 재검증 대상(`amount_inv`)은 **외화금액(fc) 컬럼**이다. 원화 `KRW Amount`는 외화×환율이라 CI 숫자와 맞지 않는다. mapping에서 `fc_amount`를 현지통화 금액 열에 연결한다.
- 비어 있지 않은 통합문서에 mapping이 없거나 mapping 결과가 0건이면 **실패로 종료**한다. 실제로 값이 전혀 없는 통합문서만 정상적인 0건 입력으로 구분한다.

#### 1-2. 증빙 준비 상태 스캔
`preflight_alignment(samples, evidence_root)` 로 샘플당 증빙 폴더 준비(없음/빈폴더)와 readable(OCR 텍스트) 비율을 스캔한다. 증빙은 **샘플당 폴더 1개(폴더명=샘플 folder)** — 얼라인은 **사용자 책임**이며 스킬은 임의 추측 매칭하지 않는다. 기본 위치는 `<evidence_root>/<folder>`이고, 유형별 하위 디렉터리를 사용한 경우에도 전체 하위 트리에서 동일한 폴더명이 하나뿐일 때만 연결한다.

#### 1-3. 스캔 결과에 따른 진행

- 최소 필드(샘플 식별자·거래처·금액)를 신뢰성 있게 매핑할 수 없으면 해당 후보를 제시하고 질문한다.
- 매출유형 컬럼이 없거나 값이 비표준이면 증빙 구성으로 프로파일 후보를 제시하고 사용자에게 확정을 요청한다.
- 증빙 폴더 미정렬이나 OCR 텍스트 부족은 표본별 `Fail`·`Exception`으로 기록하고 전수 처리를 계속한다. 사용자가 먼저 자료 보완을 원한다고 명시한 경우에만 중단한다.

### Phase 2: 프로파일 결정

`select_profile`이 알려진 매출유형을 자동 매핑한다. 적용 건수를 유형그룹별로 진행 보고에 남긴다. 매핑 미상(유형 비표준·누락) 그룹만 Claude/Codex가 증빙 구성으로 후보를 제시하고 사용자가 확정한다(BL·Invoice → 해외 / 세금계산서·계약서만 → 용역). 확정된 프로파일로만 bundle과 판정을 만든다.

### Phase 3: 증빙 분류 (파일명 잠정분류)

파일명 기반으로 증빙 유형을 분류한다. 분류 우선순위가 중요하다. 단, 이 분류는 **잠정 분류**이며 LLM verdict에서 내용상 문서 역할을 확인한다.

**분류 순서 (우선순위 높은 것부터):**

1. **세금계산서**: '세금계산서' 포함
2. **거래명세서**: '거래명세', '인수증' 포함
3. **계약서**: '계약서', '계약', 'contract', 'agreement' 포함 (용역매출 증빙; 물류서류보다 앞)
4. **POD (Proof of Delivery)**: 'pod', 'proof of delivery', 'delivery receipt', '배송완료', 'delivery order' 등
5. **BL/AWB (선적서류)**: 'bl', 'b/l', 'hawb', 'awb', 'waybill', 'fedex', 'dhl', '선적', '출고증', '출고관련서류' 등
   - 단, 'pod'가 포함된 파일은 제외 (POD로 분류됨)
6. **CI (Commercial Invoice)**: 'ci-', 'ci_', 'commercial invoice' 등
   - 단, 'cipl', 'ci&pl' 포함 시 INV/PL로 분류
7. **PO (Purchase Order)**: 'po ', 'po-', 'purchase order', 'p_us_', 'pi -' 등
   - 단, 'pod', 'invoice', '출고' 포함 시 제외
8. **INV/PL (Invoice/Packing List)**: 'inv_', 'invoice', 'cipl', 'ci&pl', '출고완료' 등
9. **OTHER**: 위에 해당하지 않는 파일

**주의**: '출고'라는 단어가 세금계산서 파일명에 포함될 수 있다 (예: "세금계산서 - 2025.03.24 출고.pdf"). 세금계산서를 INV/PL보다 먼저 체크해야 오분류를 방지할 수 있다. (회계전표는 검증 대상이므로 증빙으로 분류하지 않는다.)

### Phase 4: OCR 텍스트 산출물 로드

`revenue-tod`는 **PDF OCR 또는 PDF 텍스트 추출을 직접 수행하지 않는다.** 사용자가 사전에 OCR 또는 멀티모달 판독을 수행해 샘플 폴더에 텍스트 산출물을 제공해야 한다.

지원 입력:
- 원문 증빙: `.pdf`, `.jpg`, `.png` 등은 파일 목록과 문서 분류 힌트로만 사용한다. 텍스트는 읽지 않는다.
- OCR/판독 산출물: `.txt`, `.md`, `.markdown`, `.json`
- JSON 산출물은 `content.full_text`, `full_text`, `text`, `markdown`, `pages`, `elements`, `ocr_response` 등 일반적인 OCR 응답 형태에서 텍스트를 읽는다.
- 빈 JSON·메타데이터만 있는 JSON·손상된 JSON은 본문으로 취급하지 않는다. 읽기 실패·빈 텍스트도 미판독으로 남긴다. 문서 하위폴더에서는 읽을 수 있는 산출물을 찾을 때까지 다음 후보를 확인한다.

권장 구조:

```text
_private/e2e/case-001/
  sample.xlsx
  evidence/
    S-001/
      CI-001.pdf          # 원문, 텍스트 판독 대상 아님
      CI-001.md           # 사용자가 OCR/멀티모달로 만든 텍스트 산출물
      BL-001.pdf
      BL-001.json
```

- 원문 PDF/이미지만 있고 OCR 텍스트 산출물이 없으면 `[원문 PDF/이미지 - OCR 텍스트 미제공]`으로 기록한다.
- OCR이 필요하면 운영자/AI가 별도 OCR 스킬 또는 멀티모달 모델을 사용해 텍스트 산출물을 만든 뒤 다시 실행한다.
- 텍스트가 없는 문서로는 `Pass` 근거를 만들지 않는다.

### Phase 5: 해외매출 프로파일 (`overseas`, 7 체크)

각 해외매출(중계무역/직수출) 샘플에 `overseas` 프로파일을 적용한다. 아래 7개 체크(`profiles.py` 의 `order`·`billing`·`shipping`·`incoterms`·`pod`·`amount_inv`·`evidence_consistency`)를 순서대로 수행한다.
**모든 체크는 구체적으로 "무엇을 대사하여 어떤 결과를 얻었는지" 기록해야 한다.**

#### T1. PO (Purchase Order) - 고객 주문 확인
- PO 파일 존재 여부 확인
- PO 본문에서 주문 당사자와 샘플 거래처의 역할·동일성을 확인
- 기록 형식: `"PO 파일 확인: [파일명] / PO에서 거래처명 '[이름]' 확인"`
- PO 미확인 시: `"PO 서류 미확인 - 고객 주문 증빙 없음"` → Fail

#### T2. Invoice(CI) - 빌링 확인
- CI 또는 INV/PL의 OCR 본문 확인
- CI번호 대조: 엑셀상 CI번호가 Invoice 텍스트 또는 파일명에 존재하는지
- 거래처명 대조: Invoice 텍스트에 엑셀상 거래처명이 존재하는지
- 기록 형식: `"Invoice 파일: [파일명] / CI번호 '[번호]' → Invoice 상 확인됨 [일치] / 거래처 '[이름]' → Invoice 상 확인됨 [일치]"`
- Invoice 미확인 시: Fail

#### T3. 선적서류(BL/AWB/출고증) - 인도 확인
- BL, AWB, 출고증 등 선적/출고서류 존재 여부 확인
- 가능한 경우 선적일/출고일 추출
- EXW 조건: BL 없이 출고증이나 INV/PL로 대체 가능
- 선적서류 미확인 시: Fail

#### T4. Incoterms - 매출인식조건 충족 여부
- 엑셀상 운임조건과 Invoice상 Incoterms 대조
- Incoterms별 매출인식 기준은 `scripts/incoterms.py`의 정책표를 사용한다.
  - **Group E (EXW)**: 출발지인도조건, 위험이전=출발지
  - **Group F (FCA/FAS/FOB)**: 운임미지급인도조건, 위험이전=출발지
  - **Group C (CFR/CIF/CPT/CIP)**: 운임지급인도조건, 위험이전=출발지
  - **Group D (DAP/DPU/DDP, legacy DAT)**: 도착지인도조건, 위험이전=도착지
- Python은 그룹·위험이전 지점을 확정하고, LLM은 해당 위험이전 증빙이 충분한지 판단한다.
- Incoterms 불일치 시: Exception으로 표기하고 수동확인 필요 기록

#### T5. POD - 도착 확인 (D조건 해당 시)
- Group D(DAP/DPU/DDP, legacy DAT) 조건인 경우에만 적용
- POD 파일 존재 및 배송완료일 추출
- D조건인데 POD 미확인 시: Exception
- D조건이 아닌 경우: N/A

#### T6. 금액 대조 (reconcile)
- LLM이 **대고객 CI(매출)** 의 청구금액 필드를 원문에서 식별한다(중계무역은 매입 INV/PL 아님). 수량·단가·운임·보험료·VAT·환율·날짜를 금액으로 오판하지 않는다.
- 식별한 값을 `checks.amount_inv.reconcile = {claimed_value, target:"fc", doc_id, field}` 에 담는다(`claimed_value` 는 **순수 JSON 숫자**, 콤마·통화기호·'원' 금지) → Python이 샘플 외화(fc, 없으면 krw)와 재계산 대조한다. Python 은 이 숫자를 regex 파싱하지 않는다.
- 후보 숫자 존재만으로 Pass 하지 않으며, reconcile 불일치/누락이면 Python이 Exception 으로 강등한다.

#### T7. 증빙 세트 정합성
- CI/Invoice, PO, BL/AWB, POD가 같은 거래를 입증하는지 교차 확인
- 비교 축: CI번호, PO번호, BL/AWB번호, 거래처/party 역할, 금액, 선적/도착/작성일 흐름
- 문서 하나가 맞아도 다른 문서가 다른 거래라면 Exception 또는 Fail 판단

### Phase 6: 국내매출 프로파일 (`domestic`, 5 체크)

국내매출 샘플에 `domestic` 프로파일을 적용한다 (`tax_invoice`·`trans_stmt`·`customer_po`·`amount_cross`·`evidence_consistency`).

#### ① 세금계산서 확인 (critical)
- 파일 존재 여부
- 공급가액 대조: 엑셀상 매출액(대변) vs 세금계산서상 공급가액
- 거래처 대조: 엑셀상 거래처 vs 세금계산서상 공급받는자
  - '(주)', '주식회사' 등 법인 표기 변형도 고려

#### ② 거래명세서(인수증) 확인
- 파일 존재 여부
- 합계금액 대조

#### ③ 구매주문서(고객 PO) 확인 (선택)
- 고객 발주 증빙 존재 시 거래처명 대조. 미제출이면 N/A(선택 증빙).

#### ④ 금액 종합 대조
- 엑셀 대변금액 vs 세금계산서 공급가액 vs 거래명세서 합계

#### ⑤ 증빙 세트 정합성
- 세금계산서, 거래명세서, 구매주문서가 같은 샘플 거래를 입증하는지 확인
- 공급받는자/거래처, 금액 필드, 작성일/거래일 흐름을 교차 확인

### Phase 7: 용역매출 프로파일 (`service`, 4 체크)

용역매출 샘플에 `service` 프로파일을 적용한다. 물류 이동 증빙(BL/거래명세서)이 **없으며** 계약서로 용역 제공을 입증한다 (`tax_invoice`·`contract`·`amount_cross`·`evidence_consistency`).

#### ① 세금계산서 확인 (critical)
- 공급가액·공급받는자 대조 (국내매출 ①과 동일).

#### ② 계약서 확인 (critical)
- 파일 존재 여부
- 거래처 대조: 엑셀상 거래처 vs 계약서상 당사자
- 계약금액 대조: 엑셀상 매출액 vs 계약서상 용역대가
- 용역기간: 계약/용역 기간 일자 추출 → **매출 귀속기간 적정성 수동확인**

#### ③ 금액 종합 대조
- 엑셀 대변금액 vs 세금계산서 공급가액 vs 계약금액

#### ④ 증빙 세트 정합성
- 세금계산서와 계약서가 같은 거래처, 같은 용역 범위/기간, 같은 금액 흐름을 입증하는지 확인

### Phase 8: 검증·재계산·롤업 (Python)

LLM이 체크별 `result`/`confidence`/`summary`/`evidence`/`issues`/`manual_review_required`(+금액체크는 `reconcile`)를 작성하면, Python이 ① 스키마 검증 → ② **금액 산술 재검증**(`reconcile_amounts`: 지목값을 샘플과 재계산 대조, 불일치/누락 시 Exception 강등) → ③ criticality 롤업 순으로 최종 판정한다.

| 판정 | 기준 |
|------|------|
| **Pass** | 모든 체크 통과 + 누적 exception 없음 |
| **Exception** | 증빙은 존재하나 자동대조 불가(수동확인 필요) 또는 운임조건 불일치 등 |
| **Fail** | `critical` 체크 부재/실패 (해외: PO·Invoice·선적 / 국내·용역: 세금계산서 / 용역: 계약서) |

LLM verdict 필수 규칙:
- `result`는 `Pass`, `Exception`, `Fail`, `N/A` 중 하나다.
- critical 체크의 `Pass`에는 근거 문서와 짧은 인용이 있어야 한다.
- `confidence=low` 또는 `manual_review_required=true`는 최소 `Exception`으로 롤업한다.
- schema 오류 또는 verdict 누락은 `Exception`으로 표시하고 수동검토 대상으로 남긴다.

### Phase 9: 엑셀 워크페이퍼 생성

`tod_workpaper.generate_workpaper()` 가 **Summary + 프로파일별 상세 시트**를 자동 생성한다. 상세 시트의 검증 열은 결과의 `checks`(프로파일 체크 순서)에서 **동적으로** 만들어지므로, 프로파일을 추가해도 워크페이퍼 코드는 수정할 필요가 없다.

#### Sheet 1: Summary
- 회사명, 감사대상기간
- 프로파일(구분)별 Pass/Exception/Fail 집계표 + Pass Rate
- Exception/Fail 목록 (폴더명, 구분, 결과, 사유)

#### Sheet 2+: 프로파일별 상세 (해외매출 / 국내매출 / 용역매출 …)
상단에 **그룹 헤더로 두 섹션을 시각 구획**한다:
- **① 검증대상 — 전표(장부) 기록 정보** (회색 밴드): 폴더명·거래처·금액 등(`base`; 해외는 CI No.·운임조건·통화·FC금액 추가)
- **② 증빙 검증 결과 — LLM 판정 + Python 재검증** (파랑): 각 체크의 **결과(Pass/Exception/Fail/N/A)**와 **상세(판정 요약+근거 인용)**, 종합결과, Exception 사유, 증빙파일 목록

#### 서식
- 헤더: 진한 파랑 배경 + 흰색 볼드
- Pass: 연두색 배경 / Exception: 노란색 배경 / Fail: 빨간색 배경 / N/A: 연파랑 배경
- 모든 셀: 얇은 테두리, 텍스트 줄바꿈
- 금액: #,##0 또는 #,##0.00 형식

## 핵심 원칙

1. **할루시네이션 금지**: 제공된 OCR 텍스트에서 읽지 못한 내용을 추정하지 않는다. "대조 불가 - 수동확인 필요"로 정직하게 기록한다.
2. **구체적 기재**: "일치" 또는 "불일치"만 쓰지 않고, 무엇(어떤 값)을 어디(어떤 서류)에서 확인하여 어떤 결과를 얻었는지 기재한다.
3. **증빙 기반**: 모든 판단은 실제 추출된 텍스트에 근거한다.
4. **분류 우선순위 준수**: 세금계산서 → 거래명세서 → 계약서 → POD → BL → CI → PO → INV/PL 순서로 분류한다.
5. **판단은 LLM이 원문에서**: 거래처 동일성, 올바른 금액 필드, 날짜 의미, 증빙 세트 정합성은 문서 원문(text)을 읽어 판단한다. Python 은 후보를 추출·추측하지 않는다(후보추출 폐기).
6. **금액 authority = Python 재계산**: LLM 은 금액을 *식별*해 `reconcile.claimed_value` 에 담고, Python 이 샘플과 *재계산 대조*한다. 문서 어딘가에 같은 숫자가 있다는 이유로 Pass 하지 않는다.
7. **문서 분류는 잠정값**: 파일명/폴더명 기반 `classified_type` 은 라우팅 힌트다. 실제 문서 역할은 LLM 이 내용으로 확인한다.
8. **Incoterms 경계 고정**: 그룹·위험이전 지점은 Python 정책표가 확정한다. LLM 은 정책표를 바꾸지 않고 증빙 충족 여부만 판단한다.
9. **회계전표는 대상**: 회계전표는 증빙이 아니라 검증 대상(샘플)이다 — 증빙으로 분류·대사하지 않는다.

## 추가 권고 테스트 항목 (선택)

TOD 수행 후 아래 항목을 추가 검토하면 감사 품질을 높일 수 있다:

- **매출 Cutoff 테스트**: 기말 전후 거래의 귀속기간 적정성
- **환율 적용 적정성**: 외화매출의 KRW 환산 시 적용환율
- **대손·반품·할인 확인**: Credit Note, 반품, 할인 적용 여부
- **Incoterms 불일치 질의**: 엑셀 vs Invoice 운임조건 상이 건 회사 질의
- **선적서류 미제출 건 추가 요청**: Fail 건에 대한 증빙 보완 요청
- **완전성(Completeness) 테스트**: 출하기록 → GL 역추적

## 설정

아래 명령은 스킬 루트에서 실행한다. `tod_engine.py` CLI:
`python scripts/tod_engine.py <sample.xlsx> --mapping <mapping.json> [--evidence DIR] [--out JSON] [--profile auto|overseas|domestic|service] [--bundles-out JSON] [--verdicts JSON]`

현재 Claude/Codex가 `bundles.json`을 읽고 `verdicts.json`을 직접 작성하는 것이 기본이다. `llm_runner.py`는 필요한 경우에만 쓰는 **로컬 파일 형식 변환기**다:
```bash
python scripts/llm_runner.py <보관소>/output/bundles.json --prompts-out <보관소>/work/prompts.jsonl
python scripts/llm_runner.py <보관소>/output/bundles.json --responses <보관소>/work/responses.jsonl --verdicts-out <보관소>/output/verdicts.json
```

`prompts.jsonl`은 현재 Claude/Codex가 읽을 검토 자료다. 각 line은 `sample_folder`, `profile`, `prompt`, `evidence_bundle`을 포함한다. `responses.jsonl`은 현재 대화에서 작성해 로컬에 저장한 판정이며, 각 line에 verdict JSON 자체, `verdict` 객체, 또는 `response`/`content` 문자열(JSON 또는 fenced JSON)을 담을 수 있다. 직접 `verdicts.json`을 작성했다면 이 변환 과정은 생략한다.

설정 우선순위는 **CLI flag > env > 기본값**. `.env` 파일은 자동 로드하지 않으며 환경변수는 실행 셸에서 설정한다.

| 항목 | CLI flag | env | 기본값 |
|---|---|---|---|
| 보관소 루트 | — | `CPA_SKILLS_STORAGE` | `~/cpa-skills-data` (그 아래 `skill-revenue-tod/`) |
| 증빙 폴더 최상위 | `--evidence` | — | `<보관소>/input/evidence` |
| 결과 JSON 경로 | `--out` | — | `<보관소>/output/tod_detailed_results.json` |
| 샘플 엑셀 mapping | `--mapping` | — | 비어 있지 않은 입력은 필수 |
| 프로파일 | `--profile` | — | auto (매출유형 자동 선택) |
| LLM bundle 출력 | `--bundles-out` | — | 없음 |
| LLM verdict 입력 | `--verdicts` | — | 없음 |
| 대화 검토 자료 출력 | `llm_runner.py --prompts-out` | — | 없음 |
| 대화에서 작성한 판정 입력 | `llm_runner.py --responses` | — | 없음 |
| LLM verdicts 출력 | `llm_runner.py --verdicts-out` | — | 없음 |

`tod_workpaper.py`의 출력 엑셀 경로는 positional 인자로 지정한다
(`python scripts/tod_workpaper.py <results.json> <output.xlsx> [회사명] [감사기간]`).

### 실행 전 확인
- **Python**: 3.10 이상
- **Python deps**: `python scripts/setup_venv.py` 또는 `pip install -r requirements.txt`
- **system 바이너리**: 없음
- **판정 환경**: 현재 스킬을 실행 중인 Claude 또는 Codex의 기본 기능.

## 의존성

- 런타임 외부 패키지: `openpyxl` 하나(샘플 Excel 읽기와 결과 Excel 쓰기)
- 공개본 설치: `pip install -r requirements.txt`

## 스크립트

핵심 Python 코드는 `scripts/` 디렉토리에 번들되어 있다 (`scripts/README.md` = 스크립트 맵):
- `scripts/tod_engine.py`: 파일 열거·텍스트 아티팩트 로드·**중첩 증빙 로더**·파일명 잠정분류(`classify_file`)·mapping 기반 샘플 추출·`build_evidence_bundle()`(thin bundle)·`analyze_sample_with_verdict()`(스키마검증+산술재검증+롤업)·CLI.
- `scripts/profiles.py`: **순수 명세 데이터** — `PROFILES`(증빙·체크·criticality)·`CHECK_LABELS`·`CHECK_QUESTIONS`(판단 질문)·`CHECK_RECONCILE`(금액 재검증 대상)·`select_profile`·`get_profile_spec`. 판단 로직 없음.
- `scripts/incoterms.py`: Incoterms Group E/F/C/D·위험이전 지점 고정 정책표(룩업).
- `scripts/llm_schema.py`: verdict JSON 검증(critical Pass citation 강제) · 인용문과 실제 OCR 본문 일치 검증 · **`reconcile_amounts`(금액 산술 재검증=Python authority)** · criticality 롤업.
- `scripts/prompt_builder.py`: thin bundle → 판정 프롬프트(원칙 + incoterms 정책표). 모델 호출 없음.
- `scripts/llm_runner.py`: 현재 대화에서 읽을 자료와 작성한 판정의 로컬 파일 형식 변환.
- `scripts/tod_workpaper.py`: 엑셀 워크페이퍼 생성기 (Summary + 프로파일별 상세, 검증 열 동적 구성).

클라이언트별 샘플리스트 차이는 작업 출력 폴더의 mapping JSON으로 흡수한다. 증빙 로더는 flat 파일과 `<샘플>/<문서폴더>/<doc>.md` 중첩 구조를 모두 지원한다.

개발 검증(소스 저장소): `.venv/Scripts/python.exe -m pytest tests -q` (POSIX는 `.venv/bin/python`). 범위: 분류·얼라인·중첩로더·mapping·프로파일 명세·verdict 스키마·인용 원문·롤업·금액 산술 재검증·엑셀 재개봉. 공개 미러에는 테스트와 실제 자료를 포함하지 않는다.
