"""DSD → xlsx 단방향 변환 파이프라인 (독립 패키지)."""

from pathlib import Path
from typing import Union

__version__ = "0.2.0"

from dsd_to_xlsx.core.dsd_parser import parse
from dsd_to_xlsx.models import (
    DocumentNode,
    DsdDocument,
    DsdMeta,
    FinancialItem,
    FinancialStatement,
    StyleInfo,
)
from dsd_to_xlsx.renderers.xlsx_renderer import render_xlsx
from dsd_to_xlsx.verify import verify, VerifyReport


def convert(dsd_path: Union[str, Path], xlsx_path: Union[str, Path]) -> Path:
    """DSD 파일 하나를 xlsx로 변환. 출력 경로를 Path로 반환."""
    doc = parse(dsd_path)
    out = Path(xlsx_path)
    render_xlsx(doc, out)
    return out


__all__ = [
    "__version__",
    "convert",
    "parse",
    "render_xlsx",
    "verify",
    "VerifyReport",
    "DsdDocument",
    "DsdMeta",
    "DocumentNode",
    "StyleInfo",
    "FinancialItem",
    "FinancialStatement",
]
