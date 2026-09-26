"""
매출 TOD 검증 프로파일 레지스트리 (순수 명세 데이터)
====================================================
샘플리스트 한 행 = 장부에 기록된 매출(회계전표) = **검증 대상**.
TOD = 그 전표를 외부 증빙(Invoice/BL/세금계산서/계약서…)으로 입증한다.

이 모듈은 **판단하지 않는다.** 매출유형별 검증 프로파일(기대 증빙·체크 목록·criticality·
체크별 판단 질문·금액 재검증 대상)을 선언할 뿐이다. 판단은 스킬 구동 LLM 이 하고
(SKILL.md 루브릭), Python 은 스키마 검증·산술 재검증·criticality 롤업만 한다.

새 유형 추가 = PROFILES 에 dict 한 개(+ 필요 시 CHECK_LABELS/QUESTIONS/RECONCILE 항목).
"""


# ============================================================
# 체크 라벨 (워크페이퍼·verdict 표시용)
# ============================================================

CHECK_LABELS = {
    "order": "PO 주문확인",
    "billing": "Invoice 빌링",
    "shipping": "선적/인도",
    "incoterms": "Incoterms 매출인식",
    "pod": "POD 도착확인",
    "amount_inv": "금액대조",
    "tax_invoice": "세금계산서",
    "trans_stmt": "거래명세서",
    "customer_po": "구매주문서(고객 PO)",
    "amount_cross": "금액 종합대조",
    "contract": "계약서",
    "evidence_consistency": "증빙 세트 정합성",
}


# ============================================================
# 체크별 판단 질문 (LLM 운영 루브릭 — 상세는 SKILL.md)
# ============================================================

CHECK_QUESTIONS = {
    "order": "고객 주문 증빙(PO/Order)이 존재하고, 부분문자열이 아니라 party 역할/문맥상 샘플 거래처의 주문으로 판단되는가?",
    "billing": "Invoice/CI 가 buyer/customer, CI번호, 청구금액 측면에서 같은 거래를 입증하는가? "
               "중계무역이면 대고객 CI(매출)와 中國→韓國 INV/PL(매입원가)을 구분하고 대고객 CI 를 본다.",
    "shipping": "BL/AWB/출고증 등 선적·인도 증빙이 샘플 거래의 인도를 입증하는가? (선적일/출고일 식별)",
    "incoterms": "정책표 기준(E/F/C=위험이전 출발지, D=위험이전 도착지)에 따라 필요한 위험이전 증빙이 충족되는가?",
    "pod": "Group D(도착지인도) 거래에서 POD 가 도착지 인도를 입증하는가? (POD 일자 OCR 오독 sanity check)",
    "amount_inv": "Invoice 에서 대고객 청구금액(중계무역은 CI 매출, 매입 INV/PL 아님)에 해당하는 올바른 금액 필드를 "
                  "식별했고, 그 값이 샘플 외화/원화 금액과 일치하는가? reconcile.claimed_value 에 그 숫자를 담는다.",
    "tax_invoice": "세금계산서의 공급받는자(공급자 아님)와 공급가액(세액·합계 아님)이 샘플 거래처/매출액을 입증하는가? "
                   "공급대가(합계)=공급가액×1.1 관계로 교차검증. 공급가액을 reconcile.claimed_value 에 담는다.",
    "trans_stmt": "거래명세서/인수증이 샘플 거래와 금액을 보조 입증하는가? (합계=공급가액×1.1 인지 유의)",
    "customer_po": "고객 구매주문서가 제출된 경우 party 역할/문맥상 샘플 거래처의 주문으로 판단되는가? 없으면 N/A.",
    "amount_cross": "샘플 매출액(공급가액), 세금계산서 공급가액, 거래명세서 합계, 계약금액이 서로 정합적인가? "
                    "확정 공급가액을 reconcile.claimed_value 에 담는다.",
    "contract": "계약 당사자가 실질적으로 샘플 거래처와 동일하며, 계약금액/해당 회차 용역대가와 용역기간·매출귀속을 입증하는가? "
                "대조 금액을 reconcile.claimed_value 에 담는다.",
    "evidence_consistency": "증빙 세트가 CI/PO/BL/POD/세금계산서/계약서의 번호·party·금액·날짜 흐름상 같은 샘플 거래를 "
                            "일관되게 입증하는가? (오편철 주의)",
}


# ============================================================
# 금액 재검증 대상 (llm_schema.reconcile_amounts 가 사용)
#   target: 'fc'(외화, 없으면 krw 폴백) | 'supply_value'(공급가액=krw, 공급대가=krw×1.1 허용)
# ============================================================

# ============================================================
# 체크별 리포트(조서화) 체크리스트 — summary 에 반드시 담을 항목
#   "무엇을 담아라"만 규정. 문장 구성은 LLM. (고정 템플릿 아님 — 엣지 경직 방지)
# ============================================================

# 사람이 읽는 **자연스러운 한 문장** 문형(태그·불릿 금지). <…>는 실제 값으로 채운다.
# 한 문장에 (검증대상=거래처·금액·번호) + (확인한 증빙 파일명·번호와 그 안의 내용) + (결과)를 녹인다.
CHECK_REPORT = {
    "order": "거래처 <거래처>의 PO(<파일명>, PO No <번호>)에서 발주 품목·발주처를 확인함 — 발주처가 거래처와 <일치/불일치>.",
    "billing": "Invoice(<파일명>, CI No <번호>)에서 CI번호·청구처·청구금액을 확인함 — 샘플 거래처 <거래처>와 <일치/차이/수동확인>.",
    "shipping": "선적서류(<파일명>, BL/AWB No <번호>)에서 선적·출고일과 당사자를 확인함 — 인도 <입증/미입증>.",
    "incoterms": "Invoice상 운임조건 <값>을 <증빙>으로 확인함 — 정책상 위험이전 <지점>, 샘플 <값>과 <일치/차이>, 조건 <충족/미충족>.",
    "pod": "POD(<파일명>)에서 배송완료·수령(<도착일>)을 확인함 — 도착 <입증/미입증>. (D조건 아니면 N/A)",
    "amount_inv": "대고객 CI(<파일명>)의 청구금액 <증빙값>을 샘플 외화 <fc>와 재계산 대조함 — <일치/차이>.",
    "tax_invoice": "세금계산서(<파일명>)에서 공급받는자·공급가액을 확인함 — 거래처 <거래처>, 공급가액 <값>=매출액 <일치/차이>.",
    "trans_stmt": "거래명세서(<파일명>)에서 합계금액·인수를 확인함 — 공급가액×1.1 <일치/차이>, 인수 <확인/미확인>.",
    "customer_po": "구매주문서(<파일명>)에서 발주처를 확인함 — 거래처 <일치/불일치>. (미제출 시 N/A)",
    "amount_cross": "샘플 매출액 <값>을 세금계산서 공급가액·거래명세서 합계와 대조함 — <정합/불일치>.",
    "contract": "계약서(<파일명>)에서 당사자·계약금액·용역기간을 확인함 — 거래처·금액 <일치/차이>, 매출 귀속 <적정/확인필요>.",
    "evidence_consistency": "CI·PO·BL·POD·세금계산서의 번호·party·금액·날짜 흐름을 교차 확인함 — 같은 거래 <입증/불일치>.",
}


# 금액 재검증 대상 = **금액 정합 체크만.** (billing=CI#/거래처 정성체크는 제외 — 금액은 amount_inv 담당)
CHECK_RECONCILE = {
    "amount_inv": "fc",          # 해외: 대고객 CI 청구금액 ↔ 샘플 외화(fc, 없으면 krw)
    "tax_invoice": "supply_value",  # 국내/용역: 세금계산서 공급가액 ↔ 샘플(공급가액=krw 또는 공급대가=krw×1.1)
    "amount_cross": "supply_value",
    "contract": "krw",
}


# ============================================================
# 프로파일 레지스트리 (checks = [(check_id, criticality)])
#   criticality ∈ {'critical', 'info', 'optional'}
#   - 'critical' 체크가 Fail → 샘플 overall = Fail
#   - 그 외 Fail/Exception 또는 누적 exceptions → Exception
# ============================================================

PROFILES = {
    "overseas": {
        "display": "해외매출",
        "evidence": ["Invoice", "PO", "BL/AWB", "POD(D조건)"],
        "checks": [
            ("order", "critical"),
            ("billing", "critical"),
            ("shipping", "critical"),
            ("incoterms", "info"),
            ("pod", "info"),
            ("amount_inv", "info"),
            ("evidence_consistency", "info"),
        ],
    },
    "domestic": {
        "display": "국내매출",
        "evidence": ["세금계산서", "거래명세서", "구매주문서"],
        "checks": [
            ("tax_invoice", "critical"),
            ("trans_stmt", "info"),
            ("customer_po", "optional"),
            ("amount_cross", "info"),
            ("evidence_consistency", "info"),
        ],
    },
    "service": {
        "display": "용역매출",
        "evidence": ["세금계산서", "계약서"],
        "checks": [
            ("tax_invoice", "critical"),
            ("contract", "critical"),
            ("amount_cross", "info"),
            ("evidence_consistency", "info"),
        ],
    },
}

# 샘플리스트 '매출유형' 컬럼 → 프로파일 매핑 (유형컬럼 우선)
TYPE_TO_PROFILE = {
    "국내매출": "domestic",
    "중계무역": "overseas",
    "직수출": "overseas",
    "수출": "overseas",
    "해외매출": "overseas",
    "용역매출": "service",
    "용역": "service",
}


def select_profile(sample):
    """샘플의 '매출유형'으로 프로파일 id 반환. 매핑 미상이면 None(=LLM 보정 신호)."""
    t = (sample.get("type") or "").strip()
    return TYPE_TO_PROFILE.get(t)


def get_profile_spec(profile_id):
    """LLM 판단용 profile 명세(JSON 직렬화 가능) 반환."""
    prof = PROFILES[profile_id]
    checks = []
    for cid, crit in prof["checks"]:
        checks.append({
            "id": cid,
            "label": CHECK_LABELS.get(cid, cid),
            "criticality": crit,
            "question": CHECK_QUESTIONS.get(cid, ""),      # 무엇을 판단
            "report": CHECK_REPORT.get(cid, ""),           # 무엇을 조서에 담을지
            "reconcile": CHECK_RECONCILE.get(cid),
        })
    return {
        "id": profile_id,
        "display": prof["display"],
        "evidence": list(prof.get("evidence", [])),
        "checks": checks,
    }
