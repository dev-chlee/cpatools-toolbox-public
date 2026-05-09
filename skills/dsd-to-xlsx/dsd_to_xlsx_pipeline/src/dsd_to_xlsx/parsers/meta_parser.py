"""Parse meta.xml into DsdMeta dataclass."""

from __future__ import annotations

from lxml import etree

from dsd_to_xlsx.core.xml_parser import parse_xml
from dsd_to_xlsx.models import DsdMeta


def parse_meta(content: bytes) -> DsdMeta:
    """Parse meta.xml content into a DsdMeta object."""
    root = parse_xml(content)

    meta = DsdMeta()

    # DOCUMENT-HEADER
    header = root.find("DOCUMENT-HEADER")
    if header is not None:
        meta.company_code = header.get("regcik", "")
        meta.company_name = header.get("regname", "")

    # DOCUMENT-INFO
    doc_info = root.find("DOCUMENT-INFO")
    if doc_info is not None:
        meta.doc_version = doc_info.get("docver", "")

    # DOCUMENT-IMG-LIST
    img_list = root.find("DOCUMENT-IMG-LIST")
    if img_list is not None:
        for img in img_list.findall("IMG"):
            filename = img.get("filename", "")
            if filename:
                meta.images.append(filename)

    # EXTRACT items (both header and contents type)
    for extract in root.findall("EXTRACT"):
        for item in extract.findall("ITEM"):
            name = item.get("name", "")
            value = item.get("value", "")
            if name:
                meta.extractions[name] = value

    return meta


def parse_meta_from_contents(content: bytes, meta: DsdMeta) -> DsdMeta:
    """Enrich DsdMeta with info from contents.xml DOCUMENT-HEADER."""
    root = parse_xml(content)

    header = root.find("DOCUMENT-HEADER")
    if header is not None:
        doc_name = header.find("DOCUMENT-NAME")
        if doc_name is not None and doc_name.text:
            meta.document_name = doc_name.text

        company = header.find("COMPANY-NAME")
        if company is not None and company.text:
            meta.company_name = company.text
            code = company.get("AREGCIK", "")
            if code:
                meta.company_code = code

    return meta
