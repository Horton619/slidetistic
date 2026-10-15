"""David 2026-10-15: Slido slides (an add-in draws over them at show time) are never flagged or fixed."""
from engine.core import addins, registry
from engine.core.findings import Status
from engine.core.runner import RunConfig, repair, scan
from tests.fixtures.builders import add_part, make_deck, text_box

TAGS_CT = "application/vnd.openxmlformats-officedocument.presentationml.tags+xml"
TAG_XML = (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:tagLst '
           b'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
           b'<p:tag name="SLIDO_POLL_UUID" val="00000000-0000-0000-0000-000000000000"/></p:tagLst>')


def _slido(prs):
    add_part(prs, prs.slides[1].part, "/ppt/tags/tag1.xml", TAGS_CT, addins.TAGS, TAG_XML)


def test_findings_on_an_addin_slide_are_information_and_never_fixed(tmp_path):
    off = lambda: text_box("Placeholder text that sits off the slide", x=-1, y=1, w=6, h=1)   # noqa: E731
    deck = make_deck(tmp_path, slides=[[off()], [off()]], post=_slido)
    checks = registry.discover()
    found = scan(deck, checks, RunConfig()).findings
    plain = [f for f in found if f.slide == 1 and f.check_id == "G001"]
    owned = [f for f in found if f.slide == 2 and f.check_id == "G001"]
    assert plain and plain[0].status == Status.RED and not plain[0].informational
    assert owned and all(f.informational and f.evidence["addin"] == "Slido" for f in owned)
    result = repair(deck, checks, RunConfig(), out_path=tmp_path / "out.pptx")
    assert {c.slide for c in result.changes if c.check_id == "G001"} == {1}, "slide 2 is Slido's: untouched"
