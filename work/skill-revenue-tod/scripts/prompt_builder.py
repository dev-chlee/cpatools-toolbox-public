"""
현재 Claude/Codex 대화에서 읽을 매출 TOD 검토 자료 구성기.

증빙 bundle과 판단 기준을 하나의 문자열로 묶는다. 현재 대화에서 이 자료의
원문을 읽고 판정을 작성한다.
"""

import json

from incoterms import grouped_policy


VERDICT_SCHEMA_HINT = {
    "sample_folder": "sample folder id",
    "profile": "overseas|domestic|service",
    "checks": {
        "<check_id>": {
            "label": "check display label",
            "result": "Pass|Exception|Fail|N/A",
            "confidence": "high|medium|low",
            "summary": "short audit conclusion",
            "evidence": [
                {
                    "doc_id": "D001",
                    "filename": "source file name",
                    "field": "field being cited",
                    "quote": "short exact quote from provided text",
                }
            ],
            "reconcile": {
                "claimed_value": 314159.26,
                "target": "fc|krw|supply_value",
                "doc_id": "D001",
                "field": "공급가액|CI Total|계약금액 등",
            },
            "issues": [],
            "manual_review_required": False,
        }
    },
    "overall_notes": [],
}


def build_judgment_prompt(bundle):
    """Return a Korean judgment prompt for one sample evidence bundle."""
    payload = {
        "task": "매출 TOD 샘플 1건의 증빙 원문(text)을 직접 읽고 profile checks별 verdict JSON을 작성한다.",
        "principles": [
            "현재 스킬을 실행 중인 Claude/Codex 대화의 기본 파일 읽기·추론·파일 작성 기능으로 판정한다. 별도 모델 호출 프로그램을 만들지 않는다.",
            "각 문서의 text(원문)를 읽어 판단한다. classified_type은 파일명/폴더명 기반 잠정 분류이므로 내용으로 실제 역할을 확인한다.",
            "거래처: 샘플 거래처와 증빙상 비교 대상 party(buyer/customer/공급받는자)가 같은 상대방인지 본다. seller/vendor/운송사/배송지 등 다른 역할과 구분하고, 부분문자열·법인격 표기(주식회사·Inc)만으로 같은 거래처라 하지 않는다. (관계사 여부·이전가격은 이 스킬 범위 밖 — 샘플↔증빙 party 일치만.)",
            "금액: 라벨된 올바른 금액 필드를 먼저 식별한다(공급가액≠부가세≠합계). 중계무역은 대고객 CI(매출)와 中國→韓國 INV/PL(매입원가)을 구분해 대고객 CI를 본다. 국내는 공급대가(합계)=공급가액×1.1 관계로 교차검증한다. 문서 어딘가에 같은 숫자가 있다는 이유만으로 Pass 하지 않는다.",
            "금액 체크(reconcile 대상)는 식별한 값을 evidence[]에 인용하고, 별도로 checks[cid].reconcile={claimed_value, target, doc_id, field} 로 담는다. claimed_value 는 반드시 순수 JSON 숫자(가상 예: 314159.26)이며 콤마·통화기호·'원' 등 문자를 넣지 않는다. Python이 샘플 금액과 재계산 대조한다.",
            "날짜: 선적일·출고일·도착일·세금계산서 작성일·계약기간·귀속기간 의미를 구분한다. 첫 날짜를 매출인식일로 가정하지 않는다. OCR 날짜 오독(예: 2015/2005 등 연도 오독)을 sanity check 한다.",
            "Incoterms 그룹·위험이전 지점은 incoterms_policy를 따른다(E/F/C=출발지, D=도착지). 정책표를 바꾸지 않고 제공 증빙이 그 지점을 입증하는지만 판단한다.",
            "증빙 세트가 같은 거래를 입증하는지 CI번호·PO번호·BL/AWB번호·party·금액·날짜 흐름으로 교차 확인한다.",
            "Pass에는 근거 문서와 짧은 인용을 남긴다. critical 체크의 citation 없는 Pass는 금지한다.",
            "각 체크의 summary 는 감사인이 읽기 쉬운 **자연스러운 한 문장**으로 쓴다(태그·불릿·[검증대상] 같은 라벨 금지). 그 체크 report 의 문형을 따라, 한 문장에 검증대상(거래처·금액·번호)과 확인한 증빙(파일명·문서번호)·그 안에서 확인한 내용과 결과([일치]/[차이]/[수동확인])를 녹여 쓴다. 가상 예: '거래처 ACME의 PO(PO-DEMO-0001, PO No DEMO-0001)에서 발주 품목을 확인함 — 발주처가 거래처와 일치.' '일치'만 쓰지 않고 값·문서·근거를 담는다.",
            "확신이 낮거나 텍스트가 부족하면 Exception과 manual_review_required=true를 사용한다. 제공 텍스트 밖의 사실을 만들지 않는다.",
        ],
        "incoterms_policy": grouped_policy(),
        "verdict_schema": VERDICT_SCHEMA_HINT,
        "evidence_bundle": bundle,
    }
    return (
        "너는 외부감사 매출 Test of Details(TOD)를 수행하는 감사 보조자다.\n"
        "아래 JSON payload만 근거로 판단하고, 답변은 verdict JSON 하나만 반환한다.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    )
