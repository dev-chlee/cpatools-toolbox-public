"""Extract TABLE nodes into 2D arrays with COLSPAN/ROWSPAN handling."""

from __future__ import annotations

from dsd_to_xlsx.models import DocumentNode


def extract_table(table_node: DocumentNode) -> list[list[str]]:
    """Convert a TABLE DocumentNode into a 2D list of cell text values.

    Handles COLSPAN and ROWSPAN by expanding merged cells.
    """
    rows = _collect_rows(table_node)
    if not rows:
        return []

    grid: list[list[str]] = []
    # Track occupied cells for rowspan
    occupied: dict[tuple[int, int], str] = {}

    for row_idx, row_node in enumerate(rows):
        cells = [c for c in row_node.children if c.tag in ("TD", "TH", "TU", "TE")]
        col_idx = 0
        row_data: list[str] = []

        for cell in cells:
            # Skip occupied cells from rowspan
            while (row_idx, col_idx) in occupied:
                row_data.append(occupied[(row_idx, col_idx)])
                col_idx += 1

            text = _collect_cell_text(cell).strip()
            colspan = _int_attr(cell, "COLSPAN", 1)
            rowspan = _int_attr(cell, "ROWSPAN", 1)

            # Fill colspan
            for c in range(colspan):
                actual_col = col_idx + c
                # Fill rowspan
                for r in range(rowspan):
                    if r > 0:
                        occupied[(row_idx + r, actual_col)] = text if c == 0 else ""
                if c == 0:
                    row_data.append(text)
                else:
                    row_data.append("")

            col_idx += colspan

        # Fill remaining occupied cells
        while (row_idx, col_idx) in occupied:
            row_data.append(occupied[(row_idx, col_idx)])
            col_idx += 1

        grid.append(row_data)

    return grid


def find_tables(root: DocumentNode) -> list[DocumentNode]:
    """Find all TABLE nodes in the document tree."""
    tables: list[DocumentNode] = []
    _walk_tables(root, tables)
    return tables


def _walk_tables(node: DocumentNode, tables: list[DocumentNode]) -> None:
    for child in node.children:
        if child.tag == "TABLE":
            tables.append(child)
        _walk_tables(child, tables)


def _collect_rows(table_node: DocumentNode) -> list[DocumentNode]:
    """Collect all TR nodes from a TABLE, including those inside THEAD/TBODY."""
    rows: list[DocumentNode] = []
    for child in table_node.children:
        if child.tag == "TR":
            rows.append(child)
        elif child.tag in ("THEAD", "TBODY", "TFOOT"):
            for sub in child.children:
                if sub.tag == "TR":
                    rows.append(sub)
    return rows


def _collect_cell_text(node: DocumentNode) -> str:
    """Recursively collect text from a cell node."""
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node.children:
        parts.append(_collect_cell_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _int_attr(node: DocumentNode, attr: str, default: int = 1) -> int:
    """Get an integer attribute value with default."""
    val = node.attributes.get(attr, "")
    try:
        return int(val)
    except ValueError:
        return default
