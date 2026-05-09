"""Shared xlsx sheet-naming rules for notes (주석) sheets.

The xlsx renderer writes note sheets named after the DSD's original
note heading (e.g. "1. 일반사항", "2. 중요한 회계정책") so a reader
scanning the xlsx tabs can tell at a glance which note they're
opening. The verifier needs the inverse — parse the number back out
of a sheet name so it can match xlsx sheets against DSD notes.

Both helpers live here so the producer and consumer can't drift.

Excel constraints handled:
  * 31-char maximum sheet-name length → truncate with '…'
  * Forbidden characters ``: \\ / ? * [ ]`` → replaced with '_'
  * Empty title → fall back to the bare number
"""

from __future__ import annotations

import re

# Excel forbids these in sheet names. Apostrophes aren't on the list
# but confuse some Office features — leave them alone for now.
_FORBIDDEN_CHARS = set(r':\/?*[]')

# Max Excel sheet-name length
_MAX_LEN = 31

# Truncation ellipsis — a single character that still fits in legacy
# Office code pages (unlike '…').
_ELLIPSIS = "~"

# Extract the leading "N." from a sheet name.
_SHEET_NUMBER_RE = re.compile(r"^(\d+)\.")


def note_sheet_name(number: int, title: str) -> str:
    """Build the xlsx sheet name for a note.

    Format: ``"{number}. {title}"``. Forbidden chars in the title
    are replaced with '_'. If the result exceeds 31 chars it's cut
    at the last safe boundary and a trailing '~' is appended so the
    user can see the title was truncated.

    When ``title`` is empty (renderer shouldn't hit this, but
    defensive), the sheet name is just the number as a string.
    """
    clean_title = "".join(
        "_" if c in _FORBIDDEN_CHARS else c
        for c in (title or "").strip()
    )

    if not clean_title:
        return str(number)[:_MAX_LEN]

    base = f"{number}. {clean_title}"
    if len(base) <= _MAX_LEN:
        return base

    # Truncate and mark with the ellipsis character
    return base[: _MAX_LEN - len(_ELLIPSIS)] + _ELLIPSIS


def parse_note_sheet_name(name: str) -> int | None:
    """Recover the note number from a sheet name.

    Accepts both the new format (``"1. 일반사항"``) and the legacy
    ``"주석NN"`` format — after the renderer switch, old xlsx files
    produced by previous releases should still verify correctly.
    Returns None if no number can be extracted (e.g. a 보고서정보
    sheet or a random user-renamed tab).
    """
    if not name:
        return None

    # Legacy 주석NN / 주석N-with-suffix
    if name.startswith("주석"):
        rest = name[len("주석"):]
        # Allow a trailing openpyxl-dedup suffix (e.g. "주석02" vs
        # "주석021") by grabbing the leading digits only.
        leading = ""
        for ch in rest:
            if ch.isdigit():
                leading += ch
            else:
                break
        if leading:
            try:
                # "01" → 1. For "021" the renderer would have used
                # "02" + "1" (dedup suffix), but the dedup suffix
                # ambiguity was the original problem. Prefer the
                # longest-matching 2-digit form when possible.
                return int(leading[:2]) if len(leading) >= 2 else int(leading)
            except ValueError:
                return None
        return None

    # New "N. title" format
    m = _SHEET_NUMBER_RE.match(name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None

    return None
