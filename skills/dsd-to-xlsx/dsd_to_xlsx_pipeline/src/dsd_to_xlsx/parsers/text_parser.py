"""Handle DSD-specific text entities and transformations."""

from __future__ import annotations

import re


def process_text(text: str | None) -> str | None:
    """Process DSD text, converting custom entities to their values.

    DSD files use &cr; for line breaks (represented as &amp;cr; in XML).
    After XML parsing, these appear as literal '&cr;' strings.
    """
    if text is None:
        return None

    # &cr; -> newline
    text = text.replace("&cr;", "\n")

    # Collapse multiple &amp;cr; patterns that survive XML parsing
    text = text.replace("&amp;cr;", "\n")

    return text


def strip_spaces_for_match(text: str) -> str:
    """Remove all whitespace from text for pattern matching.

    Used for financial statement title identification where
    titles like '재 무 상 태 표' need to match '재무상태표'.
    """
    return re.sub(r"\s+", "", text)
