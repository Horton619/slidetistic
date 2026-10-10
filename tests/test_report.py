"""Report + visual review, with a fake renderer standing in for PowerPoint."""
import io
from pathlib import Path

from PIL import Image, ImageDraw

from engine import cli, report, visual
from engine.core import registry
from engine.core.runner import RunConfig, repair, scan
from tests.fixtures.builders import embed, make_deck, text_box


class FakeRenderer:
    """'Renders' slide N of a deck as a grey image; the mended deck's slides in `differ` get a mark."""
    def __init__(self, differ=()):
        self.differ, self.pdfs, self.pages = set(differ), [], []

    def to_pdf(self, pptx, label):
        self.pdfs.append(label)
        return Path(label)

    def page_image(self, pdf, page):
        self.pages.append((str(pdf), page))
        img = Image.new("RGB", (192, 108), "grey")
        if str(pdf) == "after" and page in self.differ:
            ImageDraw.Draw(img).rectangle([20, 20, 80, 60], fill="white")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=90)
        return out.getvalue()


def canva_deck(tmp_path, **kw):
    return make_deck(tmp_path, slides=[[text_box("Title", font="Calibri (MS) Bold", name="T")],
                                       [text_box("Plain", font="Calibri", name="P")],
                                       [text_box("Body", x=-0.56, name="Off")]], **kw)


def test_plan_boxes_changed_shapes_only(tmp_path):
    src = canva_deck(tmp_path)
    result = repair(src, registry.discover(), RunConfig(), out_path=tmp_path / "out.pptx")
    plan = {v.slide: v for v in visual.plan(result, src, result.output_path)}
    assert set(plan) == {1, 3}                       # slide 2 untouched
    assert (plan[1].after_boxes[0].kind, plan[1].after_boxes[0].mode) == ("font", "changed")
    assert plan[3].after_boxes[0].kind == "placement"
    assert plan[3].before_boxes[0].left < 0          # moved box: before is off-slide…
    assert plan[3].after_boxes[0].left > 0           # …after is inside


def test_identical_renders_fold_and_different_ones_show(tmp_path):
    src = canva_deck(tmp_path)
    result = repair(src, registry.discover(), RunConfig(), out_path=tmp_path / "out.pptx")
    visuals = visual.plan(result, src, result.output_path)
    visual.render(visuals, src, result.output_path, FakeRenderer(differ={3}))
    by = {v.slide: v for v in visuals}
    assert by[1].looks_same and by[1].tier == 4
    assert not by[3].looks_same and by[3].tier == 2
    html = report.build(result, registry.discover(), tmp_path / "r.html", visuals=visuals).read_text(encoding="utf-8")
    assert "4. Changed underneath, looks identical" in html and "slide 1<" in html
    assert "<h3>Slide 3</h3>" in html and "<h3>Slide 1</h3>" not in html


def test_tiers_order_broken_first_and_alert_banner(tmp_path):
    from engine.core import Finding, Status
    from engine.core.runner import Result
    src = make_deck(tmp_path, slides=[[text_box("a", name="A")], [text_box("b", name="B")]])
    r = Result(input_path=src, findings=[
        Finding("L008", Status.RED, "Text runs off the bottom", slide=2, shape_id=2, subject="off-slide",
                evidence={"rule": "text drawn below the slide", "box_emu": [0, 0, 914400, 914400]}),
        Finding("L009", Status.YELLOW, "'whole.' alone", slide=1, shape_id=2, subject="para0",
                evidence={"rule": "last line has 1 word", "box_emu": [0, 0, 914400, 457200]})])
    visuals = visual.plan(r, src, None)
    assert [(v.slide, v.tier) for v in visuals] == [(1, 3), (2, 1)]
    html = report.build(r, registry.discover(), tmp_path / "r.html", visuals=visuals).read_text(encoding="utf-8")
    assert html.index("1. Broken") < html.index("3. Needs a look")
    assert "Text runs off the slide on slide <a href='#slide-2'>2</a>" in html
    assert "Why: text drawn below the slide" in html and "box layout red" in html


def test_hidden_slides_skip_pdf_pages(tmp_path):
    # PowerPoint's PDF leaves hidden slides out: slide 3 is page 2 when slide 2 is hidden.
    src = canva_deck(tmp_path, hidden=[2])
    result = repair(src, registry.discover(), RunConfig(), out_path=tmp_path / "out.pptx")
    visuals = [v for v in visual.plan(result, src, result.output_path) if v.slide == 3]
    r = FakeRenderer()
    visual.render(visuals, src, result.output_path, r)
    assert ("before", 2) in r.pages and ("after", 2) in r.pages


def test_report_contains_summary_findings_media_and_checks(tmp_path):
    src = canva_deck(tmp_path, notes=["", "", "Play https://youtu.be/abc first"])
    checks = registry.discover()
    result = repair(src, checks, RunConfig(), out_path=tmp_path / "out.pptx")
    html = report.build(result, checks, tmp_path / "r.html", visual_note="Visual review turned off.").read_text(encoding="utf-8")
    for needle in ("fixed</div>", "to look at", "still broken", "Visual review turned off.", "To download",
                   "https://youtu.be/abc", "<td>F001</td>", "Visual Entropy Productions"):
        assert needle in html, needle


def test_scan_report_says_nothing_changed(tmp_path):
    src = make_deck(tmp_path, text_box("Clean", font="Arial"))
    checks = registry.discover()
    html = report.build(scan(src, checks, RunConfig()), checks, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "Scan only, nothing changed" in html


def test_cli_repair_writes_report_beside_output(tmp_path):
    src = canva_deck(tmp_path)
    assert cli.main(["repair", str(src), "--no-visual"]) == 0
    assert (tmp_path / "deck - mended report.html").exists()


def test_canva_shout_banner(tmp_path):
    from tests.fixtures.builders import CANVA
    src = make_deck(tmp_path, text_box("x", font="Calibri (MS) Bold"), size=CANVA)
    checks = registry.discover()
    html = report.build(scan(src, checks, RunConfig()), checks, tmp_path / "r.html").read_text(encoding="utf-8")
    assert "CANVA DETECTED!" in html and "gRaPhIc dEsIgNeR" in html


def test_no_shout_for_powerpoint_decks(tmp_path):
    src = make_deck(tmp_path, text_box("Hello", font="Arial"))
    checks = registry.discover()
    assert "DETECTED!" not in report.build(scan(src, checks, RunConfig()), checks, tmp_path / "r.html").read_text(encoding="utf-8")
