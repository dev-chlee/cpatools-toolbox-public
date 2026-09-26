"""Shared utilities for document_layout blocks."""

from collections.abc import Iterator
from typing import NamedTuple

from google.cloud import documentai

Block = documentai.Document.DocumentLayout.DocumentLayoutBlock

# A block's position path inside one Document (see iter_blocks_with_paths).
BlockPath = tuple[int | str, ...]


class PageItem(NamedTuple):
    """One entry of the HTML page assignment.

    ``mode`` is ``"full"`` (block with its whole subtree) or ``"text_only"``
    (the block's own text only). ``path`` is the block's position path from
    :func:`iter_blocks_with_paths`; the verifier pairs items with the response
    blocks by this path alone.
    """

    block: Block
    mode: str
    path: BlockPath


def parse_heading_level(block_type: str) -> int:
    """Extract heading level from block type string. (e.g., 'heading-2' -> 2)"""
    parts = block_type.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return 1


def collect_block_text(block: Block, texts: list[str]) -> None:
    """Recursively collect text from a block.

    A text block's own text (when non-empty) is collected first, then its
    child blocks are always visited, even when the parent text is empty.
    Table cells and list entries are visited in document order.
    """
    # Same traversal as iter_subtree_blocks, so MD cell text order always
    # matches the verifier's expected order.
    for node in iter_subtree_blocks(block):
        if node.text_block and node.text_block.text:
            texts.append(node.text_block.text.strip())


def iter_subtree_blocks(block: Block) -> Iterator[Block]:
    """Yield ``block`` and all of its descendants in document (depth-first) order.

    Descendants are: text-block children, blocks inside table cells (header
    rows first, then body rows, cells left to right), and blocks inside list
    entries. Each block is yielded before its own descendants.
    """
    for _, node in iter_blocks_with_paths(block, ()):
        yield node


def iter_blocks_with_paths(
    block: Block, path: BlockPath
) -> Iterator[tuple[BlockPath, Block]]:
    """Yield ``(path, block)`` for ``block`` and all descendants in document order.

    The order is that of :func:`iter_subtree_blocks`. ``path`` is the start
    block's own position path; each descendant's path extends its parent's:

    - text-block child ``j``: ``path + (j,)``
    - table cell block: ``path + ("header" | "body", row, cell, k)``, where
      ``row`` counts within the header rows or the body rows respectively
    - list entry block: ``path + (entry, k)``

    For a whole document, start each top-level block ``i`` with ``(i,)``.
    Paths are then unique within the document and the same on every read of
    the same (or a structurally identical) Document.
    """
    yield path, block
    if block.text_block:
        for j, child in enumerate(block.text_block.blocks):
            yield from iter_blocks_with_paths(child, path + (j,))
    elif block.table_block:
        for kind, rows in (
            ("header", block.table_block.header_rows),
            ("body", block.table_block.body_rows),
        ):
            for r, row in enumerate(rows):
                for c, cell in enumerate(row.cells):
                    for k, sub in enumerate(cell.blocks):
                        yield from iter_blocks_with_paths(sub, path + (kind, r, c, k))
    elif block.list_block:
        for e, entry in enumerate(block.list_block.list_entries):
            for k, sub in enumerate(entry.blocks):
                yield from iter_blocks_with_paths(sub, path + (e, k))


def block_page_range(block: Block) -> tuple[int, int] | None:
    """Return ``(page_start, page_end)`` from the block's own page_span.

    A missing or zero ``page_end`` is treated as ``page_start``. Returns None
    when the block has no page_span (or its ``page_start`` is 0).
    """
    if not block.page_span or not block.page_span.page_start:
        return None
    start = block.page_span.page_start
    end = block.page_span.page_end or start
    return start, max(start, end)


def subtree_page_range(block: Block) -> tuple[int, int] | None:
    """Return ``(min page_start, max page_end)`` over ``block`` and all descendants.

    Uses :func:`iter_subtree_blocks` and :func:`block_page_range`; blocks
    without a page_span are ignored. Returns None when no block in the
    subtree has a page_span.
    """
    ranges = [
        r for r in (block_page_range(b) for b in iter_subtree_blocks(block))
        if r is not None
    ]
    if not ranges:
        return None
    return min(r[0] for r in ranges), max(r[1] for r in ranges)
