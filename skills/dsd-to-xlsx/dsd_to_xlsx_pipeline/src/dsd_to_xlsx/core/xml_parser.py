"""XML parsing wrapper using lxml."""

from __future__ import annotations

from lxml import etree


def parse_xml(content: bytes) -> etree._Element:
    """Parse XML content bytes into an lxml element tree.

    Handles the custom entities like &cr; found in DSD files
    by using a lenient parser.
    """
    parser = etree.XMLParser(recover=True, encoding="utf-8")
    return etree.fromstring(content, parser=parser)


def parse_xml_string(content: str) -> etree._Element:
    """Parse XML string into an lxml element tree."""
    return parse_xml(content.encode("utf-8"))
