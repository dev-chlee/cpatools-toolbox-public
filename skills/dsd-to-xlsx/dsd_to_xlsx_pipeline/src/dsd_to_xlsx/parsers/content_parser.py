"""Parse contents.xml into a DocumentNode tree."""

from __future__ import annotations

from lxml import etree

from dsd_to_xlsx.core.xml_parser import parse_xml
from dsd_to_xlsx.models import DocumentNode
from dsd_to_xlsx.parsers.text_parser import process_text
from dsd_to_xlsx.parsers.usermark_parser import parse_usermark


def parse_contents(content: bytes) -> DocumentNode:
    """Parse contents.xml bytes into a DocumentNode tree."""
    root = parse_xml(content)
    return _element_to_node(root)


def _element_to_node(elem: etree._Element) -> DocumentNode:
    """Recursively convert an lxml element to a DocumentNode."""
    tag = etree.QName(elem.tag).localname if isinstance(elem.tag, str) else str(elem.tag)

    attributes = dict(elem.attrib)
    usermark = attributes.pop("USERMARK", None)
    style = parse_usermark(usermark)

    node = DocumentNode(
        tag=tag,
        attributes=attributes,
        text=process_text(elem.text),
        tail=process_text(elem.tail),
        style=style,
        source_element=elem,
    )

    for child_elem in elem:
        child_node = _element_to_node(child_elem)
        node.children.append(child_node)

    return node
