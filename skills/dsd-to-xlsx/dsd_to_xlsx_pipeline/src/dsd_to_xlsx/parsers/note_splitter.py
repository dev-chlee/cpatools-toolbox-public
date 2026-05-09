"""Split the Notes (주석) section into numbered sub-sections."""

from __future__ import annotations

import re

from dsd_to_xlsx.models import DocumentNode, NoteSection
from dsd_to_xlsx.parsers.text_parser import strip_spaces_for_match


def split_notes(root: DocumentNode) -> list[NoteSection]:
    """Split the notes SECTION-2 into individual NoteSection objects.

    Identifies note boundaries by looking for bold P tags or bold SPAN tags
    whose text starts with "N. title" pattern.
    """
    notes_section = _find_notes_section(root)
    if notes_section is None:
        return []

    sections: list[NoteSection] = []
    current: NoteSection | None = None

    for child in notes_section.children:
        match = _detect_note_boundary(child)
        if match is not None:
            number, title = match
            current = NoteSection(number=number, title=title, nodes=[])
            sections.append(current)
            current.nodes.append(child)
        elif current is not None:
            current.nodes.append(child)

    return sections


def _find_notes_section(root: DocumentNode) -> DocumentNode | None:
    """Find the SECTION-2 whose TITLE contains '주석'."""
    for node in _walk(root):
        if node.tag == "SECTION-2":
            title_text = _get_section_title(node)
            if "주석" in strip_spaces_for_match(title_text):
                return node
    return None


def _get_section_title(section: DocumentNode) -> str:
    """Extract the TITLE text from a SECTION node."""
    for child in section.children:
        if child.tag == "TITLE":
            return _collect_text(child)
    return ""


# A real note heading is a top-level number like "1. 일반사항". Sub-section
# markers such as "1.1 개요", "1.2 범위" that live inside a note body used
# to match the looser '^(\d+)\.\s*(.+)' pattern and produced duplicate
# note.number values — which openpyxl then had to disambiguate with suffix
# sheets like 주석011, 주석012. Tighten the regex:
#   * the number must be followed by a period AND one-or-more spaces
#   * the title must begin with a letter-like character (Korean 가-힣,
#     Latin A-Za-z, or an opening bracket '(' — some audit reports start
#     with "(가) …")
# "1.1 개요" fails the "period + whitespace" requirement (period is
# followed by another digit), so sub-sections are now ignored.
_NOTE_BOUNDARY_RE = re.compile(r"^(\d+)\.\s+([가-힣A-Za-z(][^\n]*)")


def _detect_note_boundary(node: DocumentNode) -> tuple[int, str] | None:
    """Detect if a node marks the start of a new note section.

    Returns (number, title) if detected, else None.

    Patterns (in priority order):
      - <P USERMARK="B">N. title</P>   (bold P)
      - <P><SPAN USERMARK="...B...">N. title</SPAN></P>  (bold SPAN)
      - <P>N. title…</P>               (plain P — some DSDs don't bold
                                        note headings at all)

    The strict ``_NOTE_BOUNDARY_RE`` (requires a space + letter-like
    first char after the period) is what keeps the plain-P fallback
    safe: body paragraphs starting with "(1)", "1.1 …", "1) …", or
    a continuation sentence don't match.
    """
    if node.tag != "P":
        return None

    # Pattern 1: Bold P tag with direct text
    if _is_bold(node):
        text = (node.text or "").strip()
        match = _NOTE_BOUNDARY_RE.match(text)
        if match:
            return int(match.group(1)), match.group(2).strip()

    # Pattern 2: Bold SPAN inside P
    for child in node.children:
        if child.tag == "SPAN" and _is_bold(child):
            text = (child.text or "").strip()
            match = _NOTE_BOUNDARY_RE.match(text)
            if match:
                return int(match.group(1)), match.group(2).strip()

    # Pattern 3: Plain P whose first line starts with "N. title"
    text = (node.text or "").strip()
    match = _NOTE_BOUNDARY_RE.match(text)
    if match:
        return int(match.group(1)), match.group(2).strip()

    return None


def _is_bold(node: DocumentNode) -> bool:
    """Check if a node has bold style."""
    return node.style is not None and node.style.bold


def _collect_text(node: DocumentNode) -> str:
    """Recursively collect all text content from a node."""
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node.children:
        parts.append(_collect_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _walk(node: DocumentNode):
    """Walk the document tree depth-first."""
    yield node
    for child in node.children:
        yield from _walk(child)
