from __future__ import annotations

from pptx.oxml.ns import qn

TEXT_BOX = "text_box"
PLACEHOLDER = "placeholder"
PICTURE = "picture"
TABLE = "table"
GROUP = "group"
CONNECTOR = "connector"
OTHER = "other"


def classify(shape) -> str:
    tag = shape.element.tag
    if tag == qn("p:grpSp"):
        return GROUP
    if tag == qn("p:pic"):
        return PICTURE
    if tag == qn("p:cxnSp"):
        return CONNECTOR
    if tag == qn("p:graphicFrame"):
        return TABLE if shape.has_table else OTHER
    if shape.is_placeholder:
        return PLACEHOLDER
    if tag == qn("p:sp") and shape.element.find(qn("p:nvSpPr")).find(qn("p:cNvSpPr")).get("txBox") == "1":
        return TEXT_BOX
    return OTHER


def has_text(shape) -> bool:
    """True when the shape shows text on the slide. Pictures never count, even with alt text."""
    kind = classify(shape)
    if kind in (PICTURE, GROUP, CONNECTOR):
        return False
    if kind == TABLE:
        return any(cell.text.strip() for row in shape.table.rows for cell in row.cells)
    return shape.has_text_frame and bool(shape.text_frame.text.strip())
