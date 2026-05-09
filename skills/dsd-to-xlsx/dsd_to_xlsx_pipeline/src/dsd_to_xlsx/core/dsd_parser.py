"""Main orchestrator for DSD file parsing."""

from __future__ import annotations

from pathlib import Path

from dsd_to_xlsx.core.unzipper import extract_dsd
from dsd_to_xlsx.models import DsdDocument
from dsd_to_xlsx.parsers.content_parser import parse_contents
from dsd_to_xlsx.parsers.meta_parser import parse_meta, parse_meta_from_contents


def parse(dsd_path: str | Path) -> DsdDocument:
    """Parse a DSD file and return a DsdDocument.

    This is the main entry point for the library. The returned
    DsdDocument includes raw contents.xml and meta.xml bytes so that
    downstream renderers (e.g. xlsx template mode) can preserve the
    original XML for lossless round-trip.
    """
    files = extract_dsd(dsd_path)

    # Keep raw bytes for lossless round-trip
    contents_content = files.get("contents.xml", b"")
    meta_content = files.get("meta.xml", b"")

    # Parse meta.xml
    meta = parse_meta(meta_content)

    # Parse contents.xml and enrich meta
    meta = parse_meta_from_contents(contents_content, meta)

    # Parse document tree
    tree = parse_contents(contents_content)

    # Collect image files
    images: dict[str, bytes] = {}
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp"}
    for filename, data in files.items():
        ext = Path(filename).suffix.lower()
        if ext in image_extensions:
            images[filename] = data

    return DsdDocument(
        meta=meta,
        tree=tree,
        images=images,
        raw_contents_xml=contents_content or None,
        raw_meta_xml=meta_content or None,
    )
