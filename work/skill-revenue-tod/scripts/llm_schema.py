"""
LLM verdict schema and deterministic rollup for revenue TOD.

The LLM makes judgment calls per profile check. This module only validates the
shape of that judgment and applies deterministic audit rollup rules.
"""

RESULTS = {"Pass", "Exception", "Fail", "N/A"}
CONFIDENCES = {"high", "medium", "low"}


class VerdictError(ValueError):
    """Raised when an LLM verdict does not satisfy the required schema."""


def validate_verdict(verdict, profile):
    """Return a list of schema errors. Empty list means valid."""
    errors = []
    if not isinstance(verdict, dict):
        return ["verdict는 JSON 객체여야 합니다."]
    checks = verdict.get("checks")
    if not isinstance(checks, dict):
        return ["verdict.checks는 JSON 객체여야 합니다."]

    expected = {c["id"]: c for c in profile.get("checks", [])}
    for cid in sorted(set(checks) - set(expected)):
        errors.append(f"알 수 없는 check id: {cid}")

    for cid, spec in expected.items():
        raw = checks.get(cid)
        label = spec.get("label", cid)
        if raw is None:
            errors.append(f"{cid}: verdict check가 누락되었습니다.")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{cid}: check verdict는 객체여야 합니다.")
            continue

        result = raw.get("result")
        if result not in RESULTS:
            errors.append(f"{cid}: result는 {sorted(RESULTS)} 중 하나여야 합니다.")

        confidence = raw.get("confidence")
        if confidence not in CONFIDENCES:
            errors.append(f"{cid}: confidence는 {sorted(CONFIDENCES)} 중 하나여야 합니다.")

        if not isinstance(raw.get("summary"), str) or not raw.get("summary", "").strip():
            errors.append(f"{cid}: summary가 필요합니다.")

        evidence = raw.get("evidence", [])
        if evidence is None:
            evidence = []
        if not isinstance(evidence, list):
            errors.append(f"{cid}: evidence는 배열이어야 합니다.")
        else:
            for idx, item in enumerate(evidence):
                if not isinstance(item, dict):
                    errors.append(f"{cid}: evidence[{idx}]는 객체여야 합니다.")
                    continue
                if not item.get("filename") and not item.get("doc_id"):
                    errors.append(f"{cid}: evidence[{idx}]에 filename 또는 doc_id가 필요합니다.")
                if not item.get("quote"):
                    errors.append(f"{cid}: evidence[{idx}]에 quote가 필요합니다.")

        if (
            spec.get("criticality") == "critical"
            and result == "Pass"
            and not evidence
        ):
            errors.append(f"{cid}: critical Pass에는 근거 인용이 필요합니다. ({label})")

        issues = raw.get("issues", [])
        if issues is not None and not isinstance(issues, list):
            errors.append(f"{cid}: issues는 배열이어야 합니다.")

        manual_review = raw.get("manual_review_required")
        if not isinstance(manual_review, bool):
            errors.append(f"{cid}: manual_review_required는 boolean이어야 합니다.")

    return errors


def validate_evidence_citations(verdict, documents):
    """판정의 문서 ID·파일명·인용문이 실제 읽힌 OCR 본문과 일치하는지 검사한다."""
    if not isinstance(verdict, dict) or not isinstance(verdict.get('checks'), dict):
        return []  # 기본 스키마 오류에서 처리
    docs = {doc.get('doc_id'): doc for doc in (documents or []) if doc.get('doc_id')}
    errors = []

    def normalized(value):
        return ''.join(str(value or '').split())

    for cid, check in verdict['checks'].items():
        if not isinstance(check, dict) or not isinstance(check.get('evidence', []), list):
            continue
        for idx, item in enumerate(check.get('evidence') or []):
            if not isinstance(item, dict):
                continue
            doc_id = item.get('doc_id')
            filename = item.get('filename')
            quote = normalized(item.get('quote'))
            if not doc_id or not filename:
                errors.append(f'{cid}: evidence[{idx}]에 doc_id와 filename이 모두 필요합니다.')
                continue
            doc = docs.get(doc_id)
            if doc is None:
                errors.append(f'{cid}: evidence[{idx}]의 doc_id를 찾을 수 없습니다: {doc_id}')
                continue
            if filename != doc.get('filename'):
                errors.append(f'{cid}: evidence[{idx}]의 filename이 {doc_id}와 일치하지 않습니다.')
            if not doc.get('readable') or not normalized(doc.get('text')):
                errors.append(f'{cid}: evidence[{idx}]가 읽을 수 없는 문서를 인용했습니다: {doc_id}')
            elif not quote or quote not in normalized(doc.get('text')):
                errors.append(f'{cid}: evidence[{idx}] 인용문을 {doc_id} 본문에서 찾을 수 없습니다.')
    return errors


def assert_valid_verdict(verdict, profile):
    """Raise VerdictError when the verdict is invalid."""
    errors = validate_verdict(verdict, profile)
    if errors:
        raise VerdictError("; ".join(errors))


def rollup_verdict(verdict, profile):
    """
    Apply deterministic rollup rules to a valid verdict.

    Critical Fail drives overall Fail. Any Exception/Fail on non-critical checks,
    low confidence, or manual review flag drives overall Exception.
    """
    assert_valid_verdict(verdict, profile)
    overall = "Pass"
    exceptions = []
    checks = verdict["checks"]

    for spec in profile.get("checks", []):
        cid = spec["id"]
        label = spec.get("label", cid)
        crit = spec.get("criticality", "info")
        check = checks[cid]
        result = check["result"]
        confidence = check["confidence"]
        manual_review = check["manual_review_required"]
        issues = check.get("issues") or []

        if result == "Fail" and crit == "critical":
            overall = "Fail"
            exceptions.append(f"{label}: critical Fail")
        elif result in {"Fail", "Exception"} and overall != "Fail":
            overall = "Exception"
            exceptions.append(f"{label}: {result}")

        if confidence == "low" and overall != "Fail":
            overall = "Exception"
            exceptions.append(f"{label}: low confidence")

        if manual_review and overall != "Fail":
            overall = "Exception"
            exceptions.append(f"{label}: manual review required")

        for issue in issues:
            if issue:
                exceptions.append(f"{label}: {issue}")

    return {"overall": overall, "exceptions": exceptions}


def _to_number(v):
    """순수 숫자만 float 로 받는다(규칙 파싱 없음). 문자열·기타는 None → 재검증 불가로 처리.
    claimed_value 는 verdict 스키마에서 JSON 숫자로 강제하므로 문자열이 오면 미제공으로 본다."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def _matches(claimed, target, rel=0.001, absmin=1.0):
    """상대 tolerance(기본 0.1%) 내 일치."""
    if claimed is None or target in (None, 0):
        return False
    return abs(claimed - target) <= max(absmin, abs(target) * rel)


def reconcile_amounts(verdict, sample, profile):
    """
    금액 재검증(authority=Python). LLM이 reconcile.claimed_value 로 *식별*한 금액을
    Python이 샘플 금액과 재계산 대조한다. Pass인데 불일치/누락이면 verdict를 mutate하여
    해당 체크를 Exception으로 강등하고 issue를 남긴다. 강등 메시지 리스트를 반환.
      target: 'fc'(외화, 없으면 krw) | 'krw' | 'supply_value'(공급가액=krw 또는 공급대가=krw×1.1)
    """
    msgs = []
    checks = verdict.get("checks", {})
    fc = _to_number(sample.get("fc_amount"))
    krw = _to_number(sample.get("krw_amount"))

    for spec in profile.get("checks", []):
        kind = spec.get("reconcile")
        if not kind:
            continue
        cid = spec["id"]
        label = spec.get("label", cid)
        check = checks.get(cid)
        if not isinstance(check, dict) or check.get("result") != "Pass":
            continue  # Pass 주장만 가드 (Exception/Fail/N/A는 이미 보수적)

        rec = check.get("reconcile") or {}
        claimed = _to_number(rec.get("claimed_value"))
        if claimed is None:
            check["result"] = "Exception"
            check.setdefault("issues", []).append(
                "금액 재검증 불가: reconcile.claimed_value 누락 또는 비숫자(JSON 숫자 필수)")
            msgs.append(f"{label}: claimed_value 누락/비숫자 → Exception")
            continue

        if kind == "fc":
            ok = _matches(claimed, fc if fc not in (None, 0) else krw)
        elif kind == "krw":
            ok = _matches(claimed, krw)
        elif kind == "supply_value":
            ok = _matches(claimed, krw) or (krw is not None and _matches(claimed, krw * 1.1))
        else:
            ok = True  # 알 수 없는 target은 통과

        if not ok:
            check["result"] = "Exception"
            check.setdefault("issues", []).append(
                f"금액 재계산 불일치: LLM 주장 {claimed:,.0f} ↔ 샘플({kind})")
            msgs.append(f"{label}: 재계산 불일치({claimed:,.0f})")
    return msgs


def format_check_detail(check):
    """워크페이퍼 상세 셀 텍스트 — 결론/근거/이슈 를 줄바꿈 섹션으로 분리(가독성)."""
    sections = []

    summary = check.get("summary")
    if summary:
        sections.append(f"【결론】 {summary}")

    evidence = check.get("evidence") or []
    if evidence:
        lines = ["【근거】"]
        for item in evidence:
            filename = item.get("filename") or item.get("doc_id", "")
            field = item.get("field", "")
            quote = item.get("quote", "")
            lines.append(f" · {filename} {field}: \"{quote}\"".rstrip())
        sections.append("\n".join(lines))

    issues = [str(i) for i in (check.get("issues") or []) if i]
    if issues:
        sections.append("【이슈】\n" + "\n".join(f" · {i}" for i in issues))

    if check.get("manual_review_required"):
        sections.append("【수동검토 필요】")

    return "\n".join(sections)
