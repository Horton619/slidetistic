from pptx.opc.packuri import PackURI

from tests.checks.helpers import Status, run_scan
from tests.fixtures.builders import make_deck, picture


def test_m011_emf_flagged(tmp_path):
    def post(prs):
        # The saved type follows the part's extension, so rename the image part as an .emf.
        pic = prs.slides[0].shapes[0]
        part = pic.part.related_part(pic._element.blip_rId)
        part.partname = PackURI("/ppt/media/image1.emf")
        part._content_type = "image/x-emf"
    src = make_deck(tmp_path, picture(), post=post)
    assert [(f.subject, f.status) for f in run_scan(src, "M011").findings] == [("image/x-emf", Status.YELLOW)]


def test_m011_png_not_flagged(tmp_path):
    assert run_scan(make_deck(tmp_path, picture()), "M011").findings == []
