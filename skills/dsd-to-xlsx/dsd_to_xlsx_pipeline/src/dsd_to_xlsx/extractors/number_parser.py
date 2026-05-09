"""Parse Korean-format numbers from financial statements.

Handles formats like:
  "43,548,941,885"     -> 43548941885.0
  "(8,162,169,511)"    -> -8162169511.0
  "-8162169511"        -> -8162169511.0
  "-1,234"             -> -1234.0
  "1581"               -> 1581.0  (no commas)
  "-"                  -> None
  ""                   -> None
  "(1,581)"            -> -1581.0

Rejects strings with irregular comma grouping (not Korean thousands format):
  "4,6,36"             -> None  (note reference list, not a number)
  "1,23"               -> None
"""

from __future__ import annotations

import re

# Strict Korean thousands-separator number pattern:
#   - plain integer: "123", "1581"
#   - grouped: "1,234" / "43,548,941,885" (first group 1-3 digits, rest exactly 3)
#   - optional decimal
_NUMBER_BODY = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
# Signed form — openpyxl stores negatives as raw int/float so the str()
# we pass in here looks like "-168329392". Parenthesized form stays the
# DSD-source canonical representation, handled separately below.
_NUMBER_RE = re.compile(rf"^-?{_NUMBER_BODY}$")
_PAREN_NUMBER_RE = re.compile(rf"^\({_NUMBER_BODY}\)$")


def parse_number(text: str | None) -> float | None:
    """Parse a Korean-format number string to float.

    Returns None for empty strings, dashes, or unparseable values.
    Strings with irregular comma grouping (e.g. "4,6,36") are treated as
    non-numeric text and return None.

    Negatives are accepted in two forms:
      * Parenthesized  "(1,234)"   — DSD / original-XML canonical form
      * Signed prefix  "-1,234"    — openpyxl / xlsx raw-value form
    """
    if text is None:
        return None

    text = text.strip()

    if not text or text == "-" or text == "–":
        return None

    # Check for parentheses (negative numbers)
    negative = False
    if _PAREN_NUMBER_RE.match(text):
        negative = True
        body = text[1:-1]
    elif _NUMBER_RE.match(text):
        body = text
    else:
        return None

    try:
        value = float(body.replace(",", ""))
    except ValueError:
        return None

    return -value if negative else value


def is_number_cell(text: str | None) -> bool:
    """Check if a text string looks like a number cell in a financial table."""
    if text is None:
        return False
    text = text.strip()
    if not text:
        return False
    if text == "-" or text == "–":
        return True
    return bool(_NUMBER_RE.match(text) or _PAREN_NUMBER_RE.match(text))
