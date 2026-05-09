"""Extract high-level report metadata from a DsdDocument.

The renderer surfaces this as a standalone `보고서정보` xlsx sheet so
a reader can tell at a glance what document they're looking at, what
period it covers, which financial statements are present, and so on.

Design principles:
  * Best-effort. Every field can be empty or None — DSDs vary and not
    every document exposes, say, an audit opinion in a stable form.
  * No new parser dependencies. We inspect the already-parsed
    ``DsdDocument`` — meta, tree, images.
  * The extractor returns a plain dataclass. Rendering (label text,
    ordering, formatting) lives in the xlsx renderer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from dsd_to_xlsx.extractors.financial_extractor import extract_financial_statements
from dsd_to_xlsx.models import DocumentNode, DsdDocument
from dsd_to_xlsx.parsers.note_splitter import split_notes


# Strong opinion markers — always end with '의견' or are '의견거절'
# ('한정적으로' etc. won't accidentally match these).
_OPINION_STRONG_RE = re.compile(r"(적정의견|한정의견|부적정의견|의견거절)")
# Weak fallback used only when no strong marker is present: the opinion
# word must be followed by a small window containing either '을 표명'
# (감사의견을 표명) or '으로' — idiomatic Korean audit-report phrasing.
_OPINION_WEAK_RE = re.compile(
    r"(적정|한정|부적정)(?=[^.]{0,30}?(표명|으로|이다\.|임|이며))"
)
_AUDITOR_RE = re.compile(r"(\S{2,15}회계법인)")
_PERIOD_FULL_RE = re.compile(
    r"(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})\s*[일]?"
    r"\s*(?:부터|~|\-|–|까지)?\s*"
    r"(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})"
)
_DATE_POINT_RE = re.compile(
    r"(\d{4})\s*[.년]\s*(\d{1,2})\s*[.월]\s*(\d{1,2})"
)
_TERM_RE = re.compile(r"제\s*(\d+)\s*\(([당전])\)\s*기")
_UNIT_RE = re.compile(r"\(단위\s*[:：]\s*([^\)]+)\)")

# Consolidation / basis prefixes used to classify reports
_CONSOLIDATION_KEYWORDS = (
    ("연결", "연결"),
    ("별도", "별도"),
)


@dataclass
class ReportMetadata:
    """Flat dataclass of extracted report-level metadata.

    Every field is optional. Missing fields render as '(정보 없음)'.
    """

    # Identity
    company_name: str = ""
    company_code: str = ""
    document_name: str = ""
    consolidation_basis: str = ""  # '연결' / '별도' / ''

    # Period
    term_label: str = ""                # e.g. "제 24(당) 기"
    current_period_start: str = ""      # YYYY-MM-DD
    current_period_end: str = ""
    unit: str = ""                      # "원" / "천원" / "백만원"

    # Audit
    auditor: str = ""
    audit_opinion: str = ""

    # Content inventory
    statement_types_present: list[str] = field(default_factory=list)
    notes_count: int = 0
    images_count: int = 0

    # Source context
    source_filename: str = ""

    @property
    def has_balance_sheet(self) -> bool:
        return "BALANCE_SHEET" in self.statement_types_present

    @property
    def has_income_statement(self) -> bool:
        return "INCOME_STATEMENT" in self.statement_types_present

    @property
    def has_equity_changes(self) -> bool:
        return "EQUITY_CHANGES" in self.statement_types_present

    @property
    def has_cash_flow(self) -> bool:
        return "CASH_FLOW" in self.statement_types_present


def extract_report_metadata(
    doc: DsdDocument, *, source_path: str | Path | None = None,
) -> ReportMetadata:
    """Inspect the DsdDocument and return a populated ReportMetadata."""
    md = ReportMetadata()

    # Identity
    md.company_name = (doc.meta.company_name or "").strip()
    md.company_code = (doc.meta.company_code or "").strip()
    md.document_name = (doc.meta.document_name or "").strip()

    # Body text for regex searches — collect once
    body_text = _collect_all_text(doc.tree)
    body_normalized = _collapse_ws(body_text)

    # Consolidation basis: look in document_name first, then body
    md.consolidation_basis = _detect_consolidation_basis(
        md.document_name, body_normalized,
    )

    # Unit
    unit_match = _UNIT_RE.search(body_text)
    if unit_match:
        md.unit = unit_match.group(1).strip()

    # Term (제 N(당) 기) — take the first 당기 occurrence
    for m in _TERM_RE.finditer(body_text):
        num, which = m.group(1), m.group(2)
        if which == "당":
            md.term_label = f"제 {num}(당) 기"
            break

    # Period: prefer a full range ("2024.01.01 ~ 2024.12.31"), else a
    # point date near 당기 (year-end for 재무상태표)
    range_match = _PERIOD_FULL_RE.search(body_text)
    if range_match:
        md.current_period_start = _fmt_ymd(*range_match.group(1, 2, 3))
        md.current_period_end = _fmt_ymd(*range_match.group(4, 5, 6))
    else:
        # fall back to the most recent date_point mention — usually the 당기말
        dates = _DATE_POINT_RE.findall(body_text)
        if dates:
            md.current_period_end = _fmt_ymd(*dates[0])

    # Auditor (회계법인) — pick the shortest plausible mention
    auditors = {m.group(1) for m in _AUDITOR_RE.finditer(body_text)}
    if auditors:
        md.auditor = min(auditors, key=len)

    # Audit opinion — strong markers first, then weak fallback
    strong = [m.group(1) for m in _OPINION_STRONG_RE.finditer(body_text)]
    if strong:
        # Adverse/disclaimer opinions dominate when multiple appear
        priority = {
            "의견거절": 0, "부적정의견": 1, "한정의견": 2, "적정의견": 3,
        }
        strong.sort(key=lambda o: priority.get(o, 99))
        md.audit_opinion = strong[0]
    else:
        weak = [m.group(1) for m in _OPINION_WEAK_RE.finditer(body_text)]
        if weak:
            priority = {"부적정": 0, "한정": 1, "적정": 2}
            weak.sort(key=lambda o: priority.get(o, 99))
            md.audit_opinion = weak[0]

    # Content inventory
    statements = extract_financial_statements(doc)
    md.statement_types_present = [s.type for s in statements]
    md.notes_count = len(split_notes(doc.tree))
    md.images_count = len(doc.images)

    if source_path is not None:
        md.source_filename = Path(source_path).name

    return md


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_all_text(node: DocumentNode) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node.children:
        parts.append(_collect_all_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _fmt_ymd(y: str, m: str, d: str) -> str:
    try:
        return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    except (TypeError, ValueError):
        return ""


def _detect_consolidation_basis(document_name: str, body: str) -> str:
    haystacks = (document_name or "", body[:2000] if body else "")
    for hay in haystacks:
        if not hay:
            continue
        for keyword, label in _CONSOLIDATION_KEYWORDS:
            if keyword in hay:
                return label
    return ""
