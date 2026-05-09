"""Extract structured data from TE/TU coded elements.

TE (Table Extraction) elements have ACODE attributes that map to
specific data fields. TU (Table Unit) elements have AUNIT attributes.
"""

from __future__ import annotations

from dsd_to_xlsx.models import DocumentNode


def extract_coded_data(root: DocumentNode) -> dict[str, str]:
    """Walk the tree and collect TE/TU coded values."""
    data: dict[str, str] = {}
    _walk_coded(root, data)
    return data


def _walk_coded(node: DocumentNode, data: dict[str, str]) -> None:
    """Recursively collect TE ACODE and TU AUNIT values."""
    if node.tag == "TE":
        code = node.attributes.get("ACODE", "")
        if code:
            text = _collect_text(node).strip()
            if text:
                data[code] = text

    elif node.tag == "TU":
        unit = node.attributes.get("AUNIT", "")
        value = node.attributes.get("AUNITVALUE", "")
        if unit and value:
            data[unit] = value
        elif unit:
            text = _collect_text(node).strip()
            if text:
                data[unit] = text

    # Also collect EXTRACTION elements from SUMMARY
    elif node.tag == "EXTRACTION":
        code = node.attributes.get("ACODE", "")
        if code:
            text = _collect_text(node).strip()
            if text:
                data[code] = text

    for child in node.children:
        _walk_coded(child, data)


def _collect_text(node: DocumentNode) -> str:
    """Collect all text from a node and its children."""
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node.children:
        parts.append(_collect_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)
