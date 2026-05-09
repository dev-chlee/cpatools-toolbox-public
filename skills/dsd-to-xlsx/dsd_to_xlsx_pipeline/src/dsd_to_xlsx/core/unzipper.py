"""DSD ZIP archive extraction with CP949 filename decoding."""

from __future__ import annotations

import zipfile
from pathlib import Path


def extract_dsd(dsd_path: str | Path) -> dict[str, bytes]:
    """Extract all files from a DSD archive.

    Returns a dict mapping decoded filenames to their content bytes.
    DSD files use CP949 encoding for Korean filenames.
    """
    dsd_path = Path(dsd_path)
    files: dict[str, bytes] = {}

    with zipfile.ZipFile(dsd_path, "r") as zf:
        for info in zf.infolist():
            # DSD archives use CP949 encoding for Korean filenames
            try:
                filename = info.filename.encode("cp437").decode("cp949")
            except (UnicodeDecodeError, UnicodeEncodeError):
                filename = info.filename

            files[filename] = zf.read(info)

    return files
