"""L010 on build slides and crowded slides (2026-10-11, TSCRA CWD slide 41: 22 year cards stacked in one spot,
each appearing on a click, read as 231 collisions and cost a 55-minute repair)."""
from lxml import etree

from engine.core import Deck, Status
from engine.core.layout.pdf import ShapeText
from tests.checks.test_contracts_layout import FakeLayout, detect, line
from tests.fixtures.builders import make_deck, text_box

P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def appear_on_click(*shape_ids):
    """A real-shaped p:timing: each shape gets an entrance effect on its own click."""
    pars = "".join(
        f'<p:par><p:cTn id="{10 + i * 3}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{11 + i * 3}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'<p:par><p:cTn id="{12 + i * 3}" presetID="10" presetClass="entr" presetSubtype="0" fill="hold" nodeType="clickEffect">'
        f'<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:set><p:cBhvr><p:cTn id="{100 + i}" dur="1" fill="hold"/>'
        f'<p:tgtEl><p:spTgt spid="{sid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
        f'</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        f'</p:childTnLst></p:cTn></p:par>' for i, sid in enumerate(shape_ids))
    xml = (f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">'
           f'<p:childTnLst><p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq">'
           f'<p:childTnLst>{pars}</p:childTnLst></p:cTn></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>')

    def post(prs):
        prs.slides[0]._element.append(etree.fromstring(xml))
    return post


def stacked(tmp_path, n, post=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    deck = Deck(make_deck(tmp_path, *[text_box(str(2000 + i), x=5, y=3, w=2, h=0.6, name=f"Y{i}") for i in range(n)],
                          post=post))
    ids = [sv.shape_id for sv in deck.slide_shapes(1)]
    layout = FakeLayout({1: {sid: ShapeText(sid, [line([str(2000 + i)], 360, 216)], [0]) for i, sid in enumerate(ids)}})
    return deck, ids, layout


def test_stacked_cards_that_appear_on_clicks_are_one_build_note_not_collisions(tmp_path):
    deck0, ids, _ = stacked(tmp_path / "a", 6)
    deck, ids, layout = stacked(tmp_path / "b", 6, post=appear_on_click(*ids))
    found = detect("L010", deck, layout)
    assert [(f.status, f.subject) for f in found] == [(Status.YELLOW, "animated build")]
    assert "6 animated text boxes" in found[0].message


def test_more_than_twelve_collisions_on_a_slide_become_one_finding(tmp_path):
    deck, ids, layout = stacked(tmp_path, 7)                 # 7 boxes in one spot: 21 colliding pairs
    found = detect("L010", deck, layout)
    assert [(f.status, f.subject) for f in found] == [(Status.RED, "many")]
    assert "21 places" in found[0].message


def test_a_real_two_box_collision_is_still_reported_and_fixable(tmp_path):
    deck, ids, layout = stacked(tmp_path, 2)
    [f] = detect("L010", deck, layout)
    assert f.status == Status.RED and f.subject.startswith("with ")
