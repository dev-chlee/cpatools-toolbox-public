from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DsdMeta:
    company_name: str = ""
    company_code: str = ""
    document_name: str = ""
    doc_version: str = ""
    images: list[str] = field(default_factory=list)
    extractions: dict[str, str] = field(default_factory=dict)
    # DART-required DOCUMENT-INFO attributes (also used as DOCUMENT-NAME ACODE).
    # Defaults chosen so existing callers still produce DART-compatible meta.xml
    # without explicit values. bsn_id == rpt_id == doc_id in observed samples.
    bsn_id: str = "00760"
    rpt_id: str = "00760"
    doc_id: str = "00760"
    iscorrection: str = "N"


@dataclass
class StyleInfo:
    font_size: int | None = None
    bold: bool = False
    align: str | None = None
    bg_color: str | None = None
    color: str | None = None


@dataclass
class DocumentNode:
    tag: str = ""
    attributes: dict[str, str] = field(default_factory=dict)
    children: list[DocumentNode] = field(default_factory=list)
    text: str | None = None
    tail: str | None = None
    style: StyleInfo | None = None
    # Optional reference to the originating lxml element. Used by the
    # xlsx renderer to build XPath cell-mapping for round-trip editing.
    # Excluded from repr/compare so existing tests that compare nodes
    # with attribute equality continue to work.
    source_element: object | None = field(default=None, repr=False, compare=False)


@dataclass
class FinancialItem:
    label: str = ""
    depth: int = 0
    note_ref: str | None = None
    current_value: float | None = None
    previous_value: float | None = None


@dataclass
class FinancialStatement:
    type: str = ""
    company_name: str = ""
    unit: str = ""
    period_label: str = ""
    items: list[FinancialItem] = field(default_factory=list)


@dataclass
class NoteSection:
    number: int = 0
    title: str = ""
    nodes: list[DocumentNode] = field(default_factory=list)


@dataclass
class DsdDocument:
    meta: DsdMeta = field(default_factory=DsdMeta)
    tree: DocumentNode = field(default_factory=DocumentNode)
    images: dict[str, bytes] = field(default_factory=dict)
    # Raw XML bytes preserved for lossless round-trip (xlsx template mode).
    # Optional — older callers / tests may create DsdDocument without these.
    raw_contents_xml: bytes | None = None
    raw_meta_xml: bytes | None = None
