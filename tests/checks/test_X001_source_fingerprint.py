from tests.checks.helpers import run_scan
from tests.fixtures.builders import CANVA, GOOGLE, make_deck, picture, text_box


def source(path):
    [f] = run_scan(path, "X001").findings
    return f.subject


def test_x001_canva_by_size_and_font_alias(tmp_path):
    assert source(make_deck(tmp_path, text_box(font="Calibri (MS) Bold"), size=CANVA)) == "canva"


def test_x001_google_by_shape_names(tmp_path):
    def named(shapes):
        tb = text_box("x")(shapes)
        tb.name = "Google Shape;54;p13"
        return tb
    assert source(make_deck(tmp_path, named, size=GOOGLE)) == "google"


def test_x001_pdf_conversion(tmp_path):
    full = picture(x=0, y=0, w=13.333, h=7.5)
    assert source(make_deck(tmp_path, slides=[[full], [full], [full]])) == "pdf"


def test_x001_plain_powerpoint(tmp_path):
    assert source(make_deck(tmp_path, text_box("Hello"))) == "powerpoint"
