"""Layout fixes settle (optimization round 2026-10-11): a repair finishes its layout work in one go, and
repairing the result again changes nothing. A stand-in PowerPoint wraps text with hidden slack, so the
engine's predictions can miss the way real PowerPoint's do (Loop Lid, CLARB 11)."""
from collections import Counter

import pytest

from engine.core import Deck, registry, runner
from engine.core.content import is_hidden, shape_text
from engine.core.fit import RUN_PROPS
from engine.core.layout import pdf as pdfmod
from engine.core.layout.pdf import Line, PdfLayout, Word
from engine.core.runner import RunConfig, repair
from tests.fixtures.builders import make_deck, text_box

PT = 12700


def fake_layout(slack: float):
    class FakePdf(PdfLayout):
        """Greedy word wrap at the box's text area × (1 + slack), from the deck in memory."""
        def _load(self):
            if self._pages is not None:
                return
            self._pages = {}
            for n, slide in enumerate(self.deck.slides, 1):
                if is_hidden(slide):
                    continue
                lines = []
                for sv in self.deck.slide_shapes(n):
                    if not sv.text_bearing or sv.bounds is None:
                        continue
                    b = sv.bounds
                    szs = [int(e.get("sz")) for e in sv.shape.text_frame._txBody.iter(*RUN_PROPS) if e.get("sz")]
                    sz = max(szs) / 100 if szs else 18.0
                    cw, gap, lh = 0.5 * sz * PT, 0.25 * sz * PT, 1.2 * sz * PT
                    area = (b.width - 0.2 * 914400) * (1 + slack)
                    y = b.top + 0.05 * 914400
                    for para in shape_text(sv.shape).split("\n"):
                        rows, cur, used = [], [], 0.0
                        for w in para.split():
                            ww = len(w) * cw
                            if cur and used + gap + ww > area:
                                rows.append(cur)
                                cur, used = [], 0.0
                            used = ww if not cur else used + gap + ww
                            cur.append(w)
                        if cur:
                            rows.append(cur)
                        for r in rows:
                            x, boxes = b.left + 0.1 * 914400, []
                            for w in r:
                                boxes.append(Word(w, x, x + len(w) * cw))
                                x += len(w) * cw + gap
                            lines.append(Line(boxes[0].left, y, boxes[-1].right, y + lh, r, boxes))
                            y += lh
                self._pages[n] = lines
    return FakePdf


@pytest.fixture
def stand_in_powerpoint(monkeypatch):
    def use(slack):
        cls = fake_layout(slack)
        monkeypatch.setattr(pdfmod, "PdfLayout", cls)
        monkeypatch.setattr(runner, "_layout_for", lambda deck, config: cls(deck, None) if config.layout else None)
        monkeypatch.setattr(runner, "_RENDERER", object())
    return use


TEXTS = ["Parents need consistent support from trusted home visitors to build lasting resilience across "
         "every stage of early childhood development together",
         "Water rights in Texas follow the rule of capture which lets landowners pump groundwater beneath their "
         "property with very few restrictions"]


# Each case left one word alone on the last line, and the pre-2026-10-11 engine changed the box's width
# 3-5 times trying to fix it (found by sweeping box widths against this stand-in).
@pytest.mark.parametrize("slack,text,width", [(0.0, 0, 3.86), (0.03, 0, 3.74), (0.03, 0, 5.78),
                                              (-0.03, 0, 3.98), (-0.03, 0, 4.7), (-0.03, 1, 3.5)])
def test_layout_fixes_settle_and_a_second_repair_changes_nothing(tmp_path, stand_in_powerpoint, slack, text, width):
    stand_in_powerpoint(slack)
    src = make_deck(tmp_path, text_box(TEXTS[text], x=1, y=2, w=width, h=2.5, name="Body"))
    checks = registry.discover()
    first = repair(src, checks, RunConfig(layout=True), out_path=tmp_path / "once.pptx")
    per_box = Counter((c.slide, c.shape_id) for c in first.changes if c.check_id.startswith("L") and c.prop == "width")
    assert all(n <= 2 for n in per_box.values()), per_box
    # Fixed, or left exactly as it was: never a box nudged without the orphan going away.
    orphan_left = any(f.check_id == "L009" and f.status.value == "yellow" for f in first.findings)
    assert not (orphan_left and per_box), (per_box, "box changed but the orphan is still there")
    second = repair(first.output_path, checks, RunConfig(layout=True), out_path=tmp_path / "twice.pptx")
    assert [c for c in second.changes if c.check_id.startswith("L")] == []
