"""A copy of a deck with only some slides in its slide list, for exporting just the slides a fit round changed
(review 2026-10-13, 3.10). The other slides' parts stay in the file, unlisted: nothing that points at them (a
link to a slide, a notes page) is left dangling, and PowerPoint draws only listed slides."""
from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def write_subset(src: Path, dst: Path, keep: set[int]) -> list[int]:
    """Write `dst` listing only the slides numbered in `keep` (1-based, in deck order). Returns the kept numbers in
    order: the subset's slide 1 is the first of them, and so on."""
    with zipfile.ZipFile(src) as zin:
        root = etree.fromstring(zin.read("ppt/presentation.xml"))
        lst = root.find(f"{{{P}}}sldIdLst")
        kept = []
        for n, sld in enumerate(list(lst) if lst is not None else [], 1):
            if n in keep:
                kept.append(n)
            else:
                lst.remove(sld)
        pres = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = pres if info.filename == "ppt/presentation.xml" else zin.read(info)
                zout.writestr(info, data)
    return kept
