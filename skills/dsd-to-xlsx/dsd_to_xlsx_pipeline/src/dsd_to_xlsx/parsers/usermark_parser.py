"""Parse USERMARK attribute strings into StyleInfo objects.

USERMARK format examples:
  "F-18 "          -> font_size=18
  "F-BT14 "        -> font_size=14, bold=True
  "F-BT14 B"       -> font_size=14, bold=True
  "B"              -> bold=True
  "F-14 B"         -> font_size=14, bold=True
  "A-C"            -> align=CENTER
  "BC0XDCDCDC"     -> bg_color=#DCDCDC
  "0X000000"       -> color=#000000
"""

from __future__ import annotations

import re

from dsd_to_xlsx.models import StyleInfo


def parse_usermark(usermark: str | None) -> StyleInfo | None:
    """Parse a USERMARK string into a StyleInfo object."""
    if not usermark:
        return None

    style = StyleInfo()
    parts = usermark.strip().split()

    for part in parts:
        _parse_part(part, style)

    # Check if any field was actually set
    if (
        style.font_size is None
        and not style.bold
        and style.align is None
        and style.bg_color is None
        and style.color is None
    ):
        return None

    return style


def _parse_part(part: str, style: StyleInfo) -> None:
    """Parse a single USERMARK part and update style."""
    # Bold standalone
    if part == "B":
        style.bold = True
        return

    # Font specification: F-{size} or F-BT{size}
    font_match = re.match(r"F-(?:BT)?(\d+)", part)
    if font_match:
        style.font_size = int(font_match.group(1))
        if "BT" in part:
            style.bold = True
        return

    # Alignment: A-C, A-L, A-R
    align_match = re.match(r"A-([CLR])", part)
    if align_match:
        align_map = {"C": "CENTER", "L": "LEFT", "R": "RIGHT"}
        style.align = align_map.get(align_match.group(1))
        return

    # Background color: BC0X{hex}
    bg_match = re.match(r"BC0X([0-9A-Fa-f]{6})", part)
    if bg_match:
        style.bg_color = f"#{bg_match.group(1)}"
        return

    # Text color: 0X{hex}
    color_match = re.match(r"^0X([0-9A-Fa-f]{6})$", part)
    if color_match:
        style.color = f"#{color_match.group(1)}"
        return
