"""
Incoterms policy for revenue TOD.

Python owns the fixed lookup table: Incoterms group and risk-transfer point.
LLM owns the audit judgment: whether provided evidence proves that point.
"""

import re


INCOTERMS_POLICY = {
    "EXW": {
        "group": "E",
        "korean_label": "출발지인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "출고 또는 인도 가능 상태를 입증하는 증빙",
    },
    "FCA": {
        "group": "F",
        "korean_label": "운임미지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "출고, 운송인 인도 또는 선적을 입증하는 증빙",
    },
    "FAS": {
        "group": "F",
        "korean_label": "운임미지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "선측 인도 또는 선적 관련 증빙",
    },
    "FOB": {
        "group": "F",
        "korean_label": "운임미지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "본선 선적 또는 선적 관련 증빙",
    },
    "CFR": {
        "group": "C",
        "korean_label": "운임지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "선적 또는 운송 개시를 입증하는 증빙",
    },
    "CIF": {
        "group": "C",
        "korean_label": "운임지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "선적 또는 운송 개시를 입증하는 증빙",
    },
    "CPT": {
        "group": "C",
        "korean_label": "운임지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "운송인 인도 또는 운송 개시를 입증하는 증빙",
    },
    "CIP": {
        "group": "C",
        "korean_label": "운임지급인도조건",
        "risk_transfer": "출발지",
        "expected_evidence": "운송인 인도 또는 운송 개시를 입증하는 증빙",
    },
    "DAP": {
        "group": "D",
        "korean_label": "도착지인도조건",
        "risk_transfer": "도착지",
        "expected_evidence": "도착지 인도, 배송완료 또는 POD 증빙",
    },
    "DPU": {
        "group": "D",
        "korean_label": "도착지인도조건",
        "risk_transfer": "도착지",
        "expected_evidence": "도착지 양하, 배송완료 또는 POD 증빙",
    },
    "DDP": {
        "group": "D",
        "korean_label": "도착지인도조건",
        "risk_transfer": "도착지",
        "expected_evidence": "도착지 인도, 배송완료 또는 POD 증빙",
    },
    # DAT is Incoterms 2010 legacy terminology, kept for backwards-compatible
    # client evidence and historical sample lists. Incoterms 2020 replaced it
    # with DPU.
    "DAT": {
        "group": "D",
        "korean_label": "도착지인도조건",
        "risk_transfer": "도착지",
        "expected_evidence": "도착지 터미널 인도, 배송완료 또는 POD 증빙",
        "legacy": True,
    },
}

INCOTERMS_TERMS = tuple(INCOTERMS_POLICY)
_TERM_RE = re.compile(r"\b(" + "|".join(INCOTERMS_TERMS) + r")\b", re.IGNORECASE)


def normalize_incoterm(term):
    """Return normalized Incoterms code, or None if unknown/blank."""
    if not term:
        return None
    code = str(term).strip().upper()
    return code if code in INCOTERMS_POLICY else None


def extract_incoterms(text):
    """Extract the first known Incoterms code from text."""
    if not text:
        return None
    m = _TERM_RE.search(text)
    return m.group(1).upper() if m else None


def get_incoterms_policy(term):
    """Return a policy dict for an Incoterms code, or None if unknown."""
    code = normalize_incoterm(term)
    if not code:
        return None
    policy = dict(INCOTERMS_POLICY[code])
    policy["term"] = code
    return policy


def risk_transfer_point(term):
    """Return '출발지' or '도착지' for a known Incoterms code."""
    policy = get_incoterms_policy(term)
    return policy["risk_transfer"] if policy else None


def grouped_policy():
    """Return the Incoterms policy grouped for LLM prompt payloads."""
    groups = [
        ("E", "출발지인도조건", "출발지", ["EXW"]),
        ("F", "운임미지급인도조건", "출발지", ["FCA", "FAS", "FOB"]),
        ("C", "운임지급인도조건", "출발지", ["CFR", "CIF", "CPT", "CIP"]),
        ("D", "도착지인도조건", "도착지", ["DAP", "DPU", "DDP", "DAT"]),
    ]
    return [
        {
            "group": group,
            "korean_label": label,
            "risk_transfer": risk,
            "terms": terms,
            "expected_evidence": INCOTERMS_POLICY[terms[0]]["expected_evidence"],
        }
        for group, label, risk, terms in groups
    ]
