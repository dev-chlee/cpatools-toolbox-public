"""Extract financial statements from DSD document tree.

Identifies financial statement tables by their title text and
extracts structured FinancialItem data.
"""

from __future__ import annotations

import re

from dsd_to_xlsx.extractors.number_parser import parse_number
from dsd_to_xlsx.extractors.table_extractor import (
    _collect_cell_text,
    _collect_rows,
    extract_table,
    find_tables,
)
from dsd_to_xlsx.models import (
    DocumentNode,
    DsdDocument,
    FinancialItem,
    FinancialStatement,
)
from dsd_to_xlsx.parsers.text_parser import strip_spaces_for_match

# Financial statement type identification patterns
STATEMENT_PATTERNS: dict[str, str] = {
    "재무상태표": "BALANCE_SHEET",
    "포괄손익계산서": "INCOME_STATEMENT",
    "자본변동표": "EQUITY_CHANGES",
    "현금흐름표": "CASH_FLOW",
}

# Allowed prefixes that real statement titles can carry. Title tables in
# semiannual/quarterly/consolidated reports are worded like
# '반 기 재 무 상 태 표' or '연결재무상태표'; after space-collapsing,
# their normalized forms are '반기재무상태표' / '연결재무상태표'. We
# permit the keyword to be preceded by any one of these prefixes (empty
# string included — the plain-annual case).
#
# The prefix set is closed: arbitrary text like '재무상태표 상 자산'
# (a note summary) normalizes to '재무상태표상자산' which does NOT end
# with any keyword, so it still gets rejected.
_TITLE_PREFIXES: tuple[str, ...] = (
    "",
    "반기",
    "분기",
    "연결",
    "별도",
    "반기연결",
    "반기별도",
    "분기연결",
    "분기별도",
    "연결반기",
    "연결분기",
)


def identify_statement_keyword(grid: list[list[str]]) -> str | None:
    """Return the statement keyword this table is a *title* for, else None.

    Rules (shared by extractor, verifier, xlsx renderer):

      * A cell matches when its space-normalized text equals a statement
        keyword, *optionally* preceded by one of ``_TITLE_PREFIXES``
        (반기/분기/연결/별도 and their combinations). Spaced variants
        like '반 기 재 무 상 태 표' collapse to '반기재무상태표' and
        match via the '반기' prefix.
      * Embellishments like '재무상태표 상 자산' (note-body summaries)
        normalize to strings the keyword does not occur as a pure
        suffix of — rejected.
      * Cells with ellipses ('···', '..') are TOC rows, skipped.
      * If two or more distinct statement keywords are found in the same
        grid, treat as a table-of-contents and skip — TOC tables list
        every statement name with page numbers.
    """
    matched: set[str] = set()
    for row in grid:
        for cell in row:
            if "..." in cell or "···" in cell or ".." in cell:
                continue
            normalized = strip_spaces_for_match(cell)
            for keyword in STATEMENT_PATTERNS:
                if not normalized.endswith(keyword):
                    continue
                prefix = normalized[: -len(keyword)] if keyword else normalized
                if prefix in _TITLE_PREFIXES:
                    matched.add(keyword)
                    break
    if len(matched) != 1:
        return None
    return next(iter(matched))


def extract_financial_statements(doc: DsdDocument) -> list[FinancialStatement]:
    """Extract all financial statements from a DsdDocument."""
    tables = find_tables(doc.tree)
    statements: list[FinancialStatement] = []

    i = 0
    while i < len(tables):
        table = tables[i]
        grid = extract_table(table)

        # Check if this is a title table for a financial statement
        stmt_type = _identify_statement_type(grid)
        if stmt_type is not None:
            company_name, unit, period_label = _extract_header_info(grid)

            # The data table follows the title table
            if i + 1 < len(tables):
                data_table = tables[i + 1]
                data_grid = extract_table(data_table)
                items = _extract_items(data_grid)

                statements.append(
                    FinancialStatement(
                        type=stmt_type,
                        company_name=company_name or doc.meta.company_name,
                        unit=unit,
                        period_label=period_label,
                        items=items,
                    )
                )
                i += 2
                continue

        i += 1

    return statements


def _identify_statement_type(grid: list[list[str]]) -> str | None:
    """Identify if a table grid is a financial statement title table.

    Delegates to :func:`identify_statement_keyword` for the grid-level
    rules, then maps the keyword to the canonical type name.
    """
    keyword = identify_statement_keyword(grid)
    if keyword is None:
        return None
    return STATEMENT_PATTERNS[keyword]


def _extract_header_info(grid: list[list[str]]) -> tuple[str, str, str]:
    """Extract company name, unit, and period label from a title table."""
    company_name = ""
    unit = ""
    period_label = ""

    for row in grid:
        for cell in row:
            text = cell.strip()
            # Unit pattern: (단위: 원) or (단위: 백만원)
            unit_match = re.search(r"\(단위\s*:\s*(\S+)\)", text)
            if unit_match:
                unit = unit_match.group(1)

            # Period label: 제 XX(당) 기
            if re.search(r"제\s*\d+\s*\(당\)", text):
                period_label = text

            # Company name: typically in a cell by itself, Korean text
            if (
                not unit_match
                and not re.search(r"제\s*\d+", text)
                and not re.search(r"\d{4}년", text)
                and text
                and not _is_statement_title(text)
            ):
                if len(text) > 2 and not text.startswith("("):
                    company_name = text

    return company_name, unit, period_label


def _is_statement_title(text: str) -> bool:
    """Check if text is a financial statement title."""
    normalized = strip_spaces_for_match(text)
    return any(p in normalized for p in STATEMENT_PATTERNS)


def _extract_items(grid: list[list[str]]) -> list[FinancialItem]:
    """Extract financial items from a data table grid.

    Expects columns: label, note_ref, current_value, previous_value
    (4 columns typically, but handles 3 columns too).
    """
    items: list[FinancialItem] = []

    # Skip header row(s)
    start = 0
    for i, row in enumerate(grid):
        if any("과" in c and "목" in c for c in row):
            start = i + 1
            break

    for row in grid[start:]:
        if not row or not any(c.strip() for c in row):
            continue

        label = row[0].strip() if len(row) > 0 else ""
        if not label:
            continue

        # Calculate depth from leading spaces
        depth = len(row[0]) - len(row[0].lstrip())
        # Normalize: 2-3 spaces = 1 level
        depth = depth // 2 if depth > 0 else 0

        note_ref = None
        current_value = None
        previous_value = None

        if len(row) >= 4:
            note_ref = row[1].strip() or None
            current_value = parse_number(row[2])
            previous_value = parse_number(row[3])
        elif len(row) >= 3:
            current_value = parse_number(row[1])
            previous_value = parse_number(row[2])

        items.append(
            FinancialItem(
                label=label,
                depth=depth,
                note_ref=note_ref,
                current_value=current_value,
                previous_value=previous_value,
            )
        )

    return items
