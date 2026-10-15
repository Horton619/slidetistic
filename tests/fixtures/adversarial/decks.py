"""The adversarial deck catalogue: one Spec per deck, with the builder that makes it and what SlideTistic
SHOULD report (docs/ADVERSARIAL_DECKS.md). Regenerate with `venv/bin/python -m tests.fixtures.adversarial.build`.

Expectations are what a crew member needs, not what the engine happens to do today. Where the engine
disagrees, the Spec carries `xfail="why"`: tests/test_adversarial.py turns those into xfail tests, which are
the to-do list. All text is made up (the repo is public).

Expectation statuses:
  red, yellow   that exact status (yellow excludes notes)
  note          a low-priority yellow (evidence["note"])
  problem       red or a non-note yellow
  info          an informational finding (inventories, fingerprints)
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

from . import kit
from .kit import (CANVA, GOOGLE, NS, NSDECL, STANDARD, WIDE, background, blank, body_pr, embed, fill, new_deck,
                  picture, save, text, transition)


@dataclass
class E:
    check: str
    status: str
    slide: int | None = None
    subject: str | None = None      # substring of the finding's subject

    def __str__(self):
        where = f" s{self.slide}" if self.slide else ""
        what = f" '{self.subject}'" if self.subject else ""
        return f"{self.check} {self.status}{where}{what}"


@dataclass
class Spec:
    name: str
    source: str                      # canva | google | office2010 | keynote | bad-design | powerpoint | engine
    broken: str                      # what's wrong, plain words
    build: object = None
    expect: list = field(default_factory=list)       # E(...) after scan
    absent: list = field(default_factory=list)       # "ID" (no problem finding) or ("ID", "red")
    fixed: list = field(default_factory=list)        # check ids whose findings repair should turn green_fixed
    kept_fonts: list = field(default_factory=list)   # typefaces that must still be in the repaired deck
    gone_fonts: list = field(default_factory=list)   # typefaces that must be gone after repair
    layout: bool = False             # the real answer needs PowerPoint (David's Mac)
    kind: str = "data"               # data | layout | robust | new | sink
    outcome: str = "ok"              # robust decks: "ok" (scans) or "error" (plain refusal)
    xfail: str | None = None         # known miss / false alarm: why
    repair_xfail: str | None = None
    safe_xfail: str | None = None    # test_repair_is_safe only
    rename: str | None = None        # X002: the test copies the deck to this file name first
    needs: list = field(default_factory=list)        # "ffprobe", "catalog"
    real_ppt: str | None = None      # how to make the real-PowerPoint copy, when the XML here is approximate
    saved: str | None = None         # the committed deck is a real PowerPoint save (what made it); never regenerated
    new: str | None = None           # section 5 / extra problems: how a check would detect it, is a fix safe
    overrides: dict = field(default_factory=dict)
    commit: bool = True              # False: built on demand by the test (too big for git)
    sidecar: str | None = None       # a file the test puts next to the deck (M003)
    slow: bool = False               # tests carry the `slow` marker (deselected by default: pytest -m slow)

    @property
    def file(self) -> str:
        return f"{self.name}.pptx"


SPECS: list[Spec] = []


def deck(name, source, broken, **kw):
    def register(fn):
        SPECS.append(Spec(name=name, source=source, broken=broken, build=fn, **kw))
        return fn
    return register


def _canva_deck():
    prs = new_deck(CANVA)
    kit.canva(prs)
    return prs


def _google_deck():
    prs = new_deck(GOOGLE)
    kit.google(prs)
    return prs


def _office_deck(version="14.0000"):
    prs = new_deck(STANDARD)
    kit.old_office(prs, version)
    return prs


def _embeds(prs, *items):
    kit._embed_fonts(prs, list(items))


# =====================================================================================================
# F: fonts
# =====================================================================================================

@deck("F001-roboto-bold-canva", "canva",
      "Text in 'Roboto Bold' (a fake family); Canva embedded Roboto's Bold face under 'Roboto Bold', regular slot.",
      expect=[E("F001", "red", subject="Roboto Bold"), E("F005", "red", subject="Roboto Bold")],
      fixed=["F001", "F005"], gone_fonts=["Roboto Bold"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Field day schedule", 1, 1, 12, 1.5, font="Roboto Bold", size=60)
    text(s, "Gates open at 8 a.m.", 1, 3, 12, 1, font="Roboto", size=32)
    _embeds(prs, embed("Roboto", "regular", "Roboto"), embed("Roboto Bold", "regular", "Roboto", "Bold"))
    return save(prs, path)


@deck("F001-arial-rounded-mt-bold", "powerpoint",
      "Look-alike: 'Arial Rounded MT Bold' is a real family whose name ends in Bold. Must NOT be renamed.",
      absent=["F001", "F007"], kept_fonts=["Arial Rounded MT Bold"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Kids' corner opens at noon", 1, 1, 10, 1.5, font="Arial Rounded MT Bold", size=44)
    return save(prs, path)


@deck("F001-german-fett", "canva",
      "Weight word in another language: 'Roboto Fett' (German for Bold). Roboto is embedded.",
      expect=[E("F001", "problem", subject="Roboto Fett")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Willkommen zur Messe", 1, 1, 14, 1.5, font="Roboto Fett", size=54)
    text(s, "Halle 3, Stand 12", 1, 3, 14, 1, font="Roboto", size=30)
    _embeds(prs, embed("Roboto", "regular", "Roboto"))
    return save(prs, path)


@deck("F001-embedded-under-suffixed-name", "canva",
      "Dealer Trust pattern: text 'Arial Nova Condensed Bold', embedded under that exact name, file says family "
      "'Arial Nova'. Renaming would orphan the embed: must be left alone (a note).",
      expect=[E("F001", "note", subject="Arial Nova Condensed Bold")], absent=[("F001", "red")],
      kept_fonts=["Arial Nova Condensed Bold"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Spring equipment sale", 1, 1, 14, 1.5, font="Arial Nova Condensed Bold", size=60)
    _embeds(prs, embed("Arial Nova Condensed Bold", "regular", "Arial Nova", "Bold"))
    return save(prs, path)


@deck("F001-doubled-and-italic", "canva",
      "'Lato Bold Italic' and 'Lato Bold Bold' as families, Lato embedded. One repair must fix both.",
      expect=[E("F001", "red", subject="Lato Bold Italic"), E("F001", "red", subject="Lato Bold Bold")],
      fixed=["F001"], gone_fonts=["Lato Bold Italic", "Lato Bold Bold"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Keynote: soil health", 1, 1, 14, 1.5, font="Lato Bold Bold", size=60)
    text(s, "with a sample speaker", 1, 3, 14, 1, font="Lato Bold Italic", size=30)
    text(s, "Room B", 1, 5, 14, 1, font="Lato", size=30)
    _embeds(prs, embed("Lato", "regular", "Lato"))
    return save(prs, path)


@deck("F002-calibri-ms-everywhere", "canva",
      "'Calibri (MS)' in the master title style, a layout placeholder, a table cell, a chart and a slide run.",
      expect=[E("F002", "red", subject="Calibri (MS)")], fixed=["F002"], gone_fonts=["Calibri (MS)"])
def _(path):
    prs = _canva_deck()
    master = prs.slide_masters[0]
    lvl = master._element.find(".//" + qn("p:titleStyle")).find(qn("a:lvl1pPr")).find(qn("a:defRPr"))
    kit._ordered_font(lvl, "a:latin", "Calibri (MS)")
    for ph in prs.slide_layouts[1].placeholders:
        if ph.placeholder_format.idx == 1:
            ph.text_frame.text = "Layout prompt"
            ph.text_frame.paragraphs[0].runs[0].font.name = "Calibri (MS)"
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Membership numbers"
    s.placeholders[1].text_frame.text = "Up 12% on last year"
    tbl = s.shapes.add_table(2, 2, Inches(1), Inches(6), Inches(8), Inches(2)).table
    for r in tbl.rows:
        for c in r.cells:
            c.text = "Region"
            c.text_frame.paragraphs[0].runs[0].font.name = "Calibri (MS)"
    data = CategoryChartData()
    data.categories = ["2024", "2025", "2026"]
    data.add_series("Members", (310, 340, 381))
    chart = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(10), Inches(4), Inches(8), Inches(5), data).chart
    chart.font.name = "Calibri (MS)"
    text(s, "Source: sample data", 1, 9.5, 8, 0.6, font="Calibri (MS)", size=16)
    return save(prs, path)


@deck("F002-open-sans-paren-bold", "canva",
      "'Open Sans (Bold)': another Canva-style private name, not in font_aliases.yaml.",
      # Round 1 expected F002; it's a weight written into the name, which F001 owns (rename + bold flag). 2026-10-14.
      expect=[E("F001", "red", subject="Open Sans (Bold)")], absent=[("F007", "red")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Volunteer briefing", 1, 1, 14, 1.5, font="Open Sans (Bold)", size=60)
    _embeds(prs, embed("Open Sans", "regular", "Open Sans"))
    return save(prs, path)


@deck("F002-alias-in-smartart", "canva",
      "'Calibri (MS)' only inside a SmartArt drawing part (dsp:txBody). Approximate SmartArt XML.",
      expect=[E("F002", "red")], fixed=["F002"], gone_fonts=["Calibri (MS)"],
      real_ppt="Insert ▸ SmartArt ▸ Basic Process with three steps, font Calibri, save; then run it through Canva "
               "import/export to get the '(MS)' alias, or edit the alias into ppt/diagrams/drawing1.xml by hand.")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    _smartart(prs, s, ["Plan", "Plant", "Harvest"], font="Calibri (MS)")
    return save(prs, path)


@deck("F003-thin-black-bold-toggled", "canva",
      "'Montserrat Thin' with bold ON and 'Montserrat Black' with bold OFF; Montserrat embedded.",
      expect=[E("F003", "yellow", subject="Montserrat Thin"), E("F003", "yellow", subject="Montserrat Black")],
      absent=["F001"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Thin but bold", 1, 1, 14, 1.5, font="Montserrat Thin", bold=True, size=54)
    text(s, "Black but not bold", 1, 3, 14, 1.5, font="Montserrat Black", bold=False, size=54)
    text(s, "Regular body", 1, 5, 14, 1, font="Montserrat", size=30)
    _embeds(prs, embed("Montserrat", "regular", "Montserrat"))
    return save(prs, path)


@deck("F003-montserrat-semibold", "canva",
      "'Montserrat SemiBold' as a family with Montserrat embedded: F003 yellow, F001 must not rename it.",
      expect=[E("F003", "yellow", subject="Montserrat SemiBold")], absent=["F001"],
      kept_fonts=["Montserrat SemiBold"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Partner logos", 1, 1, 14, 1.5, font="Montserrat SemiBold", size=54)
    text(s, "Thanks to our sponsors", 1, 3, 14, 1, font="Montserrat", size=30)
    _embeds(prs, embed("Montserrat", "regular", "Montserrat"))
    return save(prs, path)


@deck("F004-canva-sans", "canva", "Canva Sans on a slide (exists only inside Canva).",
      expect=[E("F004", "red", subject="Canva Sans")], absent=["F007"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Cattle market update", 1, 1, 14, 1.5, font="Canva Sans", size=54)
    return save(prs, path)


@deck("F004-canva-sans-notes-only", "canva",
      "Canva Sans used ONLY in the speaker notes. Notes show in Presenter View, not to the audience: a note at most.",
      absent=[("F004", "red")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Cattle market update", 1, 1, 14, 1.5, font="Arial", size=54)
    tf = s.notes_slide.notes_text_frame
    tf.text = "Mention the new weigh station."
    tf.paragraphs[0].runs[0].font.name = "Canva Sans"
    return save(prs, path)


@deck("F005-regular-slot-holds-bold", "google",
      "'Lato' regular slot holds Lato Bold; text uses 'Lato'. Re-filing would disconnect it: yellow, left alone.",
      expect=[E("F005", "yellow", subject="Lato")], absent=[("F005", "red")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Annual meeting", 0.5, 0.5, 9, 1, font="Lato", size=40)
    _embeds(prs, embed("Lato", "regular", "Lato", "Bold"))
    kit.google_names(s)
    return save(prs, path)


@deck("F005-duplicate-and-unused-embeds", "canva",
      "Two list entries for 'Lato' (duplicate embeds) plus an embed 'Zephyr Display' that no text uses (bloat).",
      absent=[("F005", "red")],
      new="Unused embeds: compare embeddedFontLst names with font_use.visible_fonts; report as a note with the MB "
          "it costs. Fix (drop the entry and its part) is safe only when no text, master or layout names it.")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Trade show floor plan", 1, 1, 14, 1.5, font="Lato", size=54)
    _embeds(prs, embed("Lato", "regular", "Lato"), embed("Lato", "bold", "Lato", "Bold"),
            embed("Zephyr Display", "regular", "Zephyr Display"))
    lst = prs.part._element.find(qn("p:embeddedFontLst"))
    dup = etree.fromstring(etree.tostring(lst[0]))
    lst.append(dup)
    return save(prs, path)


@deck("F006-calibri-arial-embedded", "canva", "Calibri and Arial embedded (Office fonts; bloat, can override on Mac).",
      expect=[E("F006", "yellow", subject="Calibri"), E("F006", "yellow", subject="Arial")], fixed=["F006"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Feed prices", 1, 1, 14, 1.5, font="Calibri", size=54)
    text(s, "Per ton, delivered", 1, 3, 14, 1, font="Arial", size=30)
    _embeds(prs, embed("Calibri", "regular", "Calibri"), embed("Arial", "regular", "Arial"))
    return save(prs, path)


@deck("F006-aptos-embedded", "powerpoint",
      "Look-alike: Aptos embedded. Office 2019/2021 lack Aptos, so this embed is useful: must NOT be removed.",
      absent=["F006", ("F007", "red")])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Board report", 1, 1, 10, 1.5, font="Aptos", size=44)
    _embeds(prs, embed("Aptos", "regular", "Aptos"))
    return save(prs, path)


@deck("F007-ea-cs-sym-slots", "google",
      "Missing fonts only in the East Asian (ea), complex-script (cs) and symbol (sym) slots, with text in "
      "those scripts: 'Noto Sans JP', 'Noto Naskh Arabic', 'Font Awesome 6 Free'.",
      expect=[E("F007", "red", subject="Noto Sans JP"), E("F007", "red", subject="Noto Naskh Arabic"),
              E("F007", "red", subject="Font Awesome 6 Free")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "ようこそ 東京会場へ", 0.5, 0.5, 9, 1, font="Arial", ea="Noto Sans JP", size=36)
    text(s, "مرحبا بكم في المعرض", 0.5, 2, 9, 1, font="Arial", cs="Noto Naskh Arabic", size=36)
    text(s, "\uf0e0 contact desk", 0.5, 3.5, 9, 1, font="Arial", sym="Font Awesome 6 Free", size=36)
    kit.google_names(s)
    return save(prs, path)


@deck("F007-master-theme-unused-layout", "google",
      "Theme heading/body fonts 'Proxima Nova'/'Gotham' (drawn via +mj-lt/+mn-lt on every slide: red), master "
      "title style 'Gilroy' overridden by the theme? no: Gilroy drawn in titles (red), and 'Bebas Neue' only in "
      "an unused layout (note).",
      expect=[E("F007", "red", subject="Gilroy"), E("F007", "red", subject="Gotham"),
              E("F007", "note", subject="Bebas Neue")])
def _(path):
    prs = _google_deck()
    kit.set_theme(prs, major="Proxima Nova", minor="Gotham")
    master = prs.slide_masters[0]
    lvl = master._element.find(".//" + qn("p:titleStyle")).find(qn("a:lvl1pPr")).find(qn("a:defRPr"))
    kit._ordered_font(lvl, "a:latin", "Gilroy")
    unused = prs.slide_layouts[8]
    for ph in unused.placeholders:
        ph.text_frame.text = "Caption prompt"
        ph.text_frame.paragraphs[0].runs[0].font.name = "Bebas Neue"
        break
    for i in range(2):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = f"Agenda part {i + 1}"
        s.placeholders[1].text = "Welcome, safety, schedule"
        kit.google_names(s, i + 1)
    return save(prs, path)


@deck("F008-fstype-restricted", "canva", "Embedded font whose licence flag (fsType 2) forbids embedding.",
      expect=[E("F008", "yellow", subject="Brandon Grotesque")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Sponsor thank-you", 1, 1, 14, 1.5, font="Brandon Grotesque", size=54)
    _embeds(prs, embed("Brandon Grotesque", "regular", "Brandon Grotesque", fs_type=2))
    return save(prs, path)


@deck("F008-fstype-preview-editable", "canva",
      "Look-alike: fsType 4 (preview & print) and 8 (editable) both allow embedding: must NOT be flagged.",
      absent=["F008"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Preview & print", 1, 1, 14, 1.5, font="Sample Sans", size=54)
    text(s, "Editable", 1, 3, 14, 1.5, font="Sample Serif", size=54)
    _embeds(prs, embed("Sample Sans", "regular", "Sample Sans", fs_type=4),
            embed("Sample Serif", "regular", "Sample Serif", fs_type=8))
    return save(prs, path)


@deck("F009-renamed-google-font", "google",
      "'Source Sans Pro' (Google renamed it 'Source Sans 3') and 'Montserrat ExtraBold' (only some weights asked). "
      "F007 must call both missing; F009 should offer Source Sans 3 and Montserrat 800.",
      expect=[E("F007", "red", subject="Source Sans Pro"), E("F009", "info", subject="Source Sans")],
      needs=["catalog"])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Research highlights", 0.5, 0.5, 9, 1, font="Source Sans Pro", size=40)
    text(s, "Three findings", 0.5, 2, 9, 1, font="Montserrat ExtraBold", size=30)
    kit.google_names(s)
    return save(prs, path)


@deck("F011-emoji-zoo", "canva",
      "Emoji with skin tones (👍🏽), a ZWJ family (👩‍👩‍👧), flags (🇺🇸 🇲🇽) and a forced-emoji heart (❤️).",
      expect=[E("F011", "yellow", slide=1)])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Great job team 👍🏽 👩‍👩‍👧", 1, 1, 14, 1.5, size=54)
    text(s, "Visitors from 🇺🇸 🇲🇽 ❤️", 1, 3, 14, 1.5, size=54)
    return save(prs, path)


@deck("F011-default-emoji-no-selector", "bad-design",
      "Emoji outside U+1F000–1FAFF with no U+FE0F: ✅ ⌚ ⭐ ☕ (emoji presentation by default on Mac and Windows).",
      expect=[E("F011", "yellow", slide=1)])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Checklist ✅  Breaks ☕  Time ⌚  Top pick ⭐", 1, 1, 11, 1.5, size=40)
    return save(prs, path)


@deck("F011-lone-variation-selector", "google",
      "Look-alike: a stray U+FE0F after ordinary letters/digits ('Room 1️' from a copy-paste). Not an emoji.",
      absent=["F011"])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Room 1\ufe0f, floor B\ufe0f", 0.5, 0.5, 9, 1, size=36)
    kit.google_names(s)
    return save(prs, path)


@deck("F011-typographic-symbols", "powerpoint",
      "Look-alike: © ® ™ → • ★ ✓ (text symbols, no emoji style). Must NOT be flagged.", absent=["F011"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Brand™ © 2026 → next • ★ ✓", 1, 1, 11, 1.5, size=40)
    return save(prs, path)


# =====================================================================================================
# G: geometry
# =====================================================================================================

@deck("G001-negative-x-canva", "canva",
      "Body box at x = −0.56 in, left-aligned (PAT slide 22). A photo bleeding off the left (fine, never moved).",
      expect=[E("G001", "red")], fixed=["G001"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    picture(s, kit.png(40, 30), x=-2, y=0, w=8, h=11.25, name="Photo bleed")
    text(s, "Quarterly harvest results by county and crop type", -0.56, 4, 12, 2, size=40, name="Body")
    return save(prs, path)


@deck("G001-picture-off-slide-only", "canva",
      "Look-alike: only pictures off the slide (bleeds on every edge). Nothing to flag, nothing to move.",
      absent=["G001", "G002"])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    picture(s, kit.png(20, 20), x=-3, y=-1, w=6, h=6)
    picture(s, kit.png(20, 20), x=17, y=8, w=6, h=6)
    text(s, "Safe inside", 6, 4, 8, 1.5, size=40)
    return save(prs, path)


@deck("G001-group-child-off", "canva",
      "A text box inside a group that sits off the left edge. Red; the fix refuses (inside a group).",
      expect=[E("G001", "red"), E("G004", "info")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    grp = s.shapes.add_group_shape()
    text(grp.shapes, "Grouped caption pinned left", 0, 0, 8, 1.5, size=36)
    picture(grp.shapes, kit.png(), x=8, y=0, w=3, h=1.5)
    grp.left, grp.top = Inches(-1.2), Inches(5)
    return save(prs, path)


@deck("G001-scaled-group-inside", "google",
      "Look-alike: group with chOff/chExt ≠ off/ext (children scaled to 50%). A child's own x looks off-slide, "
      "but its absolute position is inside. Must NOT be flagged.",
      absent=["G001"])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    grp = s.shapes.add_group_shape()
    text(grp.shapes, "Scaled label", 0, 0, 6, 1, size=28)
    x = grp._element.grpSpPr.get_or_add_xfrm()
    E_ = lambda v: str(int(Inches(v)))
    for tag, attrs in (("a:off", {"x": E_(1), "y": E_(1)}), ("a:ext", {"cx": E_(3), "cy": E_(0.5)}),
                       ("a:chOff", {"x": E_(-10), "y": E_(0)}), ("a:chExt", {"cx": E_(6), "cy": E_(1)})):
        el = x.find(qn(tag))
        if el is None:
            el = etree.SubElement(x, qn(tag))
        for k, v in attrs.items():
            el.set(k, v)
    child = grp.shapes[0]
    child.left = Inches(-10)
    kit.google_names(s)
    return save(prs, path)


@deck("G001-rotated-corner", "bad-design",
      "Box rotated 30° near the right edge: its corner leaves the slide. G003 yellow; G001 skips rotated text.",
      expect=[E("G003", "note")], absent=["G001"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "SALE", 10.5, 1, 3, 1, size=40).rotation = 30
    return save(prs, path)


@deck("G001-centered-overhang", "google",
      "Look-alike: box 0.3 in past the left edge, but short centered text sits well inside. Yellow (check by eye), "
      "never red, never moved without layout.",
      expect=[E("G001", "yellow")], absent=[("G001", "red")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Welcome", -0.3, 2, 6, 1, size=36, align=PP_ALIGN.CENTER)
    kit.google_names(s)
    return save(prs, path)


@deck("G001-text-overflows-unwrapped", "canva",
      "Box inside the slide, word wrap OFF, a long line runs past the right edge. The box is fine; the words aren't.",
      expect=[E("L008", "red")], layout=True)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "This sentence keeps going far past the edge of its own small box and off the slide", 12, 5, 6, 1,
         size=48, wrap=False)
    return save(prs, path)


@deck("G002-autofit-off-overflow", "office2010",
      "Autofit off; 12 lines of 24 pt in a 2 in box near the bottom: the text runs below the slide, the box doesn't.",
      expect=[E("L008", "red")], layout=True)
def _(path):
    prs = _office_deck()
    s = blank(prs)
    text(s, "\n".join(f"Line {i}: sample agenda item" for i in range(1, 13)), 1, 5, 8, 2, size=24,
         autofit="noAutofit", font="Calibri")
    return save(prs, path)


@deck("G002-spautofit-box-below", "google",
      "Shape-autofit box whose saved height already runs 0.6 in below the slide.",
      expect=[E("G002", "yellow")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Footnote one\nFootnote two\nFootnote three", 0.5, 4.6, 9, 1.6, size=18, autofit="spAutoFit")
    kit.google_names(s)
    return save(prs, path)


@deck("G003-rotated-flipped", "bad-design",
      "Text at 90° and 270°, and a text box with flipH (mirror-image text).",
      expect=[E("G003", "note")])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Side label", 1, 3, 3, 0.8, size=24).rotation = 90
    text(s, "Other side", 8, 3, 3, 0.8, size=24).rotation = 270
    t = text(s, "Mirror", 4, 5, 3, 0.8, size=24)
    kit.xfrm(t, flipH="1")
    return save(prs, path)


@deck("G003-ea-vertical", "google",
      "Vertical text by bodyPr vert='eaVert' (and 'vert270'), not by rotation. It's sideways text all the same.",
      expect=[E("G003", "note")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    body_pr(text(s, "縦書きの見出し", 0.5, 0.5, 1, 4, size=28), vert="eaVert")
    body_pr(text(s, "Sideways caption", 8, 0.5, 1, 4, size=20), vert="vert270")
    kit.google_names(s)
    return save(prs, path)


@deck("G004-deep-nesting", "keynote",
      "Text five groups deep, the innermost group off the right edge.",
      expect=[E("G004", "info"), E("G001", "yellow")], absent=[("G001", "red")])
def _(path):
    prs = new_deck(WIDE)
    kit.keynote(prs)
    s = blank(prs)
    shapes = s.shapes
    groups = []
    for _ in range(5):
        g = shapes.add_group_shape()
        groups.append(g)
        shapes = g.shapes
    text(shapes, "Deep caption", 0, 0, 3, 1, font="Avenir", size=24)
    groups[-1].left = Inches(12)
    return save(prs, path)


def _size_deck(size, label):
    def build(path):
        prs = new_deck(size)
        s = blank(prs)
        text(s, f"{label} slide", 0.5, 0.5, 4, 1, size=28)
        return save(prs, path)
    return build


for _name, _size, _label in (("G006-4x3", STANDARD, "4:3"), ("G006-16x10", (10, 6.25), "16:10"),
                             ("G006-a4", (10.833, 7.5), "A4"), ("G006-1920x1200px", (20, 12.5), "1920×1200"),
                             ("G006-portrait", (7.5, 13.333), "Portrait")):
    SPECS.append(Spec(_name, "bad-design", f"Slide size {_label}.", build=_size_deck(_size, _label),
                      expect=[E("G006", "yellow")]))
SPECS.append(Spec("G006-16x9-google", "google", "Look-alike: Google's 10 × 5.625 in is 16:9. Must NOT be flagged.",
                  build=_size_deck(GOOGLE, "Google 16:9"), absent=["G006"]))


# =====================================================================================================
# L: layout fit (need PowerPoint). Built here, judged on David's Mac.
# =====================================================================================================

LAYOUT_NOTE = "Layout check: run on the Mac. Without PowerPoint the L checks must stay silent."


@deck("L001-title-zero-slack", "canva",
      "PAT pattern: single-line title in a box ~0.3% narrower than the line ('Calibri (MS) Bold' → Calibri bold "
      "after F001/F002). Width 12.715 in is the narrowest PowerPoint for Mac still draws on one line (found by "
      "rendering in PowerPoint, 2026-10-13; 12.712 in wraps).",
      layout=True, kind="layout", expect=[E("F002", "red")])
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Regional Grazing Outlook 2026", 1, 0.8, 12.715, 1.6, font="Calibri (MS) Bold", size=72, name="Title 1")
    text(s, "Rainfall, stocking rates and feed costs", 1, 3, 14, 1, font="Calibri (MS)", size=36)
    return save(prs, path)


@deck("L001-wider-on-windows", "keynote",
      "Header in Helvetica Neue (Mac has it; Windows substitutes Arial, which is wider): one line on the Mac, "
      "two on the PC.", layout=True, kind="layout")
def _(path):
    prs = new_deck(WIDE)
    kit.keynote(prs)
    s = blank(prs)
    text(s, "Water Rights and the Next Five Years", 0.6, 0.5, 12.1, 1.2, font="Helvetica Neue", size=48,
         name="Title 1")
    return save(prs, path)


@deck("L008-safe-zone-cases", "canva",
      "Three cases: body text 0.05 in into the 5% border (tuning gate T001: leave it); a footer in the bottom band "
      "(never flagged); a big text block on a filled panel in the border (moves with its panel or not at all).",
      layout=True, kind="layout")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    m = CANVA[0] * 0.05
    text(s, "A body paragraph that starts just inside the border by a hair.", m - 0.05, 3, 9, 2, size=32)
    text(s, "sample.org/footer · page 4", 1, 10.4, 8, 0.6, size=16)
    panel = s.shapes.add_shape(1, Inches(CANVA[0] - 7.5), Inches(1), Inches(7.4), Inches(8))
    fill(panel, "1F4E79")
    text(s, "Panel heading\nThree lines of text\nsitting on the panel", CANVA[0] - 7.3, 1.2, 7.1, 6, size=40,
         color="FFFFFF")
    return save(prs, path)


@deck("L009-orphans", "google",
      "Bullets that end with one word on the last line, and a title PowerPoint is shrinking "
      "(normAutofit fontScale=90%).", layout=True, kind="layout")
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Our members manage more than four hundred thousand acres of grazing land across the region",
         0.5, 1.5, 6.2, 1.5, size=24)
    text(s, "Annual awards dinner and silent auction for the scholarship fund tonight",
         0.5, 0.2, 9, 1, size=36, autofit='<a:normAutofit xmlns:a="%s" fontScale="90000"/>' % NS["a"])
    kit.google_names(s)
    return save(prs, path)


@deck("L010-overlap-cases", "google",
      "Four cases: two boxes whose words interleave on one line (NOT red); stacked map labels; text revealed by "
      "clicks (a note, not a fix); invisible text the same colour as the background under real text (TSCRA).",
      layout=True, kind="layout")
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "First 10            School Hub", 0.5, 0.3, 6, 0.6, size=24)
    text(s, "Elementary", 2.0, 0.3, 2, 0.6, size=24)
    for i, town in enumerate(("Riverton", "Lakeside", "Hill City")):
        text(s, town, 6 + i * 0.15, 1.2 + i * 0.18, 2, 0.4, size=14)
    a = text(s, "Year 2019", 0.5, 2.5, 3, 0.6, size=24)
    b = text(s, "Year 2020", 0.5, 2.5, 3, 0.6, size=24)
    kit.entrance_on_click(s, [a.shape_id, b.shape_id])
    background(s, "FFFFFF")
    text(s, "Sample Presenter, Sample Org", 4, 4, 5, 0.6, size=24)
    text(s, "Previous Presenter Name", 4, 4.05, 5, 0.6, size=24, color="FFFFFF")
    kit.google_names(s)
    return save(prs, path)


@deck("L011-picture-cases", "canva",
      "A caption half over a photo; text over a fully transparent picture (should not count as over a picture).",
      layout=True, kind="layout")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    picture(s, kit.png(64, 48), x=2, y=2, w=8, h=6)
    text(s, "Caption hanging half off the photo edge", 7, 7, 8, 1, size=32)
    picture(s, kit.flat_png(64, 48, (0, 0, 0, 0)), x=11, y=2, w=7, h=5)
    text(s, "Over an invisible picture", 12, 4, 6, 1, size=32)
    return save(prs, path)


# =====================================================================================================
# P: playback
# =====================================================================================================

@deck("P001-one-slide-timed", "office2010", "One of four slides advances after 45 s (leftover rehearsal timing).",
      expect=[E("P001", "yellow")])
def _(path):
    prs = _office_deck()
    for i in range(4):
        s = blank(prs)
        text(s, f"Slide {i + 1}", 1, 1, 6, 1, font="Calibri")
        if i == 2:
            transition(s, advTm="45000")
    return save(prs, path)


@deck("P001-walk-in-loop", "powerpoint", "Every slide advances after 8 s with clicks off, loop on: a walk-in loop.",
      expect=[E("P001", "yellow"), E("P003", "yellow", subject="loop")])
def _(path):
    prs = new_deck(WIDE)
    for i in range(3):
        s = blank(prs)
        text(s, f"Sponsor {i + 1}", 1, 1, 6, 1)
        transition(s, advTm="8000", advClick="0")
    kit.show_pr(prs, loop="1", showNarration="1")
    return save(prs, path)


@deck("P001-advance-after-zero", "office2010", "A slide set to advance after 0 s: it flashes past.",
      expect=[E("P001", "problem")])
def _(path):
    prs = _office_deck()
    for i in range(3):
        s = blank(prs)
        text(s, f"Slide {i + 1}", 1, 1, 6, 1, font="Calibri")
        if i == 1:
            transition(s, advTm="0")
    return save(prs, path)


@deck("P002-advclick-off", "office2010", "Mouse-click advance off and no timer on slide 2.",
      expect=[E("P002", "yellow", slide=2)], absent=["P001"])
def _(path):
    prs = _office_deck()
    for i in range(3):
        s = blank(prs)
        text(s, f"Slide {i + 1}", 1, 1, 6, 1, font="Calibri")
        if i == 1:
            transition(s, advClick="0")
    return save(prs, path)


@deck("P003-kiosk", "office2010", "Show type 'Browsed at a kiosk' (clicks don't advance).",
      expect=[E("P003", "red", subject="kiosk")])
def _(path):
    prs = _office_deck()
    s = blank(prs)
    text(s, "Touch screen menu", 1, 1, 6, 1, font="Calibri")
    kit.show_pr(prs, inner="<p:kiosk/>", showNarration="1")
    return save(prs, path)


@deck("P003-window-custom-show-no-narration", "office2010",
      "Browsed in a window, plays a custom show of 2 of 4 slides, narrations off, show without animation.",
      expect=[E("P003", "yellow", subject="window"), E("P003", "yellow", subject="custom-show"),
              E("P003", "red", subject="no-animation")])
def _(path):
    prs = _office_deck()
    slides = []
    for i in range(4):
        s = blank(prs)
        text(s, f"Session slide {i + 1}", 1, 1, 6, 1, font="Calibri")
        slides.append(s)
    kit.custom_show(prs, "Short version", slides[:2])
    kit.show_pr(prs, inner='<p:browse/><p:custShow id="0"/>', showNarration="0", showAnimation="0")
    return save(prs, path)


@deck("P004-links-that-leave", "office2010",
      "Slide 1: web link. 2: link to another file (handout.pdf). 3: mailto. 4: UNC file link. 5: run a program. "
      "6: look-alike 'next slide' action link (stays in the show, not flagged).",
      expect=[E("P004", "yellow", slide=1), E("P004", "yellow", slide=2), E("P004", "yellow", slide=3),
              E("X004", "red", slide=4), E("X004", "red", slide=5)],
      absent=[E("P004", "problem", slide=6)])
def _(path):
    prs = _office_deck()
    targets = ["https://sample.org/program", "handout.pdf", "mailto:info@sample.org",
               "\\\\fileserver\\share\\backup deck.pptx", "file:///C:/Windows/System32/notepad.exe", None]
    for i, t in enumerate(targets):
        s = blank(prs)
        tb = text(s, f"Click here ({i + 1})", 1, 1, 6, 1, font="Calibri")
        if i == 4:
            kit.hyperlink_run(tb, t, action="ppaction://program")
        elif t is None:
            kit.hyperlink_run(tb, None, action="ppaction://hlinkshowjump?jump=nextslide")
        else:
            kit.hyperlink_run(tb, t)
    return save(prs, path)


# =====================================================================================================
# M: media
# =====================================================================================================

def _timing_for(slide, pic, mode):
    xml = (kit.HERE.parent / "media_modes" / f"{mode}.xml").read_text().split("-->", 1)[1]
    new = etree.fromstring(xml.replace("{SPID}", str(pic.shape_id)).strip())
    root = slide._element
    old = root.find(qn("p:timing"))
    if old is not None:
        root.remove(old)
    anchor = root.find(qn("p:clrMapOvr"))
    anchor.addnext(new)
    return new


@deck("M001-when-clicked", "powerpoint", "Video set to 'When Clicked On' (Windows save): the clicker can't start it.",
      expect=[E("M001", "red")], fixed=["M001"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    v = kit.video(s)
    _timing_for(s, v, "win_when_clicked")
    return save(prs, path)


@deck("M001-click-sequence-ok", "powerpoint", "Look-alike: video 'In Click Sequence' (Mac save). Fine.",
      absent=["M001"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    v = kit.video(s)
    _timing_for(s, v, "mac_click_sequence")
    return save(prs, path)


@deck("M001-video-in-group", "powerpoint", "A 'When Clicked On' video inside a group with its caption.",
      expect=[E("M001", "red")], fixed=["M001"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    v = kit.video(s, x=1, y=1)
    grp = s.shapes.add_group_shape()
    text(grp.shapes, "Clip: sample barn tour", 1, 4.6, 6, 0.6)
    grp._element.append(v._element)          # python-pptx can't add a movie to a group directly
    grp._element.recalculate_extents()
    _timing_for(s, v, "mac_when_clicked")
    return save(prs, path)


@deck("M001-two-videos-one-slide", "powerpoint", "Two 'When Clicked On' videos on one slide: they become clicks 1 and 2.",
      expect=[E("M001", "red")], fixed=["M001"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    a = kit.video(s, x=0.5, w=6)
    b = kit.video(s, x=6.8, w=6)
    timing = _timing_for(s, a, "win_when_clicked")
    other = etree.fromstring((kit.HERE.parent / "media_modes" / "win_when_clicked.xml").read_text()
                             .split("-->", 1)[1].strip().replace("{SPID}", str(b.shape_id)))
    for c in other.iter(qn("p:cTn")):
        c.set("id", str(int(c.get("id")) + 100))
    root_list = timing.find(qn("p:tnLst")).find(qn("p:par")).find(qn("p:cTn")).find(qn("p:childTnLst"))
    for child in other.find(qn("p:tnLst")).find(qn("p:par")).find(qn("p:cTn")).find(qn("p:childTnLst")):
        root_list.append(child)
    return save(prs, path)


@deck("M002-audio-trim-mute", "powerpoint",
      "Inventory: a trimmed video (p14:trim 2 s–8 s), a muted video (mute='1'), an MP3 sound. "
      "Audio 'play across slides' (numSld) needs a real-PowerPoint save, so it isn't faked here.",
      expect=[E("M002", "info", subject="video"), E("M002", "info", subject="audio")], needs=["ffprobe"],
      real_ppt="Insert ▸ Audio, Playback ▸ Play Across Slides, stop after 3 slides; save on Mac and on Windows.")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    v = kit.video(s, x=0.5, w=6)
    kit.media_trim(v, 2000, 8000)
    s2 = blank(prs)
    m = kit.video(s2, x=0.5, w=6)
    t = _timing_for(s2, m, "win_click_sequence")
    t.find(".//" + qn("p:cMediaNode")).set("mute", "1")
    s3 = blank(prs)
    a = kit.video(s3, data=(kit.MEDIA / "tone.mp3").read_bytes(), mime="audio/mpeg", ext="mp3", w=1, h=1)
    kit.as_audio(a)
    kit.rename_media(a, "mp3", "audio/mpeg")
    return save(prs, path)


@deck("M003-linked-media", "office2010",
      "Slide 1: linked video missing (C:\\Users\\…). Slide 2: linked video that sits next to the deck "
      "(intro.mp4, copied in by the test). Slide 3: /Users/… Mac path.",
      expect=[E("M003", "red", slide=1), E("M003", "yellow", slide=2), E("M003", "red", slide=3)],
      absent=["X004"], sidecar="intro.mp4")
def _(path):
    prs = _office_deck()
    for target in ("file:///C:/Users/sample/Videos/opener.mp4", "intro.mp4", "file:///Users/sample/Movies/closer.mov"):
        s = blank(prs)
        v = kit.video(s)
        kit.unembed_and_link(s, v, target)
    return save(prs, path)


@deck("M004-formats", "office2010",
      "Embedded .wmv, .avi, .mkv, and a .mov holding ProRes.",
      expect=[E("M004", "yellow", slide=1), E("M004", "yellow", slide=2), E("M004", "yellow", slide=3),
              E("M004", "yellow", slide=4)], needs=["ffprobe"])
def _(path):
    prs = _office_deck()
    for data, mime, ext in (((kit.STUBS / "stub.wmv").read_bytes(), "video/x-ms-wmv", "wmv"),
                            ((kit.STUBS / "stub.avi").read_bytes(), "video/x-msvideo", "avi"),
                            ((kit.MEDIA / "clip.mkv").read_bytes(), "video/x-matroska", "mkv"),
                            ((kit.MEDIA / "prores.mov").read_bytes(), "video/quicktime", "mov")):
        s = blank(prs)
        v = kit.video(s, data=data, mime=mime)
        kit.rename_media(v, ext, mime)
    return save(prs, path)


@deck("M005-online-video", "google",
      "Google style: a thumbnail picture linking to YouTube (slide 1) and a streaming Vimeo player rel (slide 2).",
      expect=[E("M005", "red", slide=1), E("M005", "red", slide=2)])
def _(path):
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    prs = _google_deck()
    s = blank(prs)
    p = picture(s, kit.png(32, 18), x=1, y=1, w=8, h=4.5)
    p.click_action.hyperlink.address = "https://www.youtube.com/watch?v=sampleVideo1"
    kit.google_names(s)
    s2 = blank(prs)
    text(s2, "Watch the clip", 1, 1, 6, 1)
    s2.part.relate_to("https://player.vimeo.com/video/100000001", RT.VIDEO, is_external=True)
    kit.google_names(s2, 2)
    return save(prs, path)


@deck("M006-links-to-download", "google",
      "Slide 1: YouTube link in the notes. Slide 2: Google Drive file link in text. Slide 3: look-alike: a YouTube "
      "CHANNEL link (not a video, nothing to download).",
      expect=[E("M006", "yellow", slide=1), E("M006", "yellow", slide=2), E("P004", "yellow", slide=3)],
      absent=[E("M006", "problem", slide=3)])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Our story", 1, 1, 6, 1)
    s.notes_slide.notes_text_frame.text = "Play https://youtu.be/sampleVid22 here"
    s2 = blank(prs)
    text(s2, "Footage: https://drive.google.com/file/d/1SAMPLEFILEID/view", 0.5, 1, 9, 1, size=18)
    s3 = blank(prs)
    tb = text(s3, "Follow our channel", 1, 1, 6, 1)
    kit.hyperlink_run(tb, "https://www.youtube.com/@sampleChannel")
    for i, sl in enumerate((s, s2, s3), 1):
        kit.google_names(sl, i)
    return save(prs, path)


@deck("M008-M009-image-sizes", "canva",
      "Slide 1: 2400×1800 noisy photo (~2.5 MB) shown 1.5 in wide (oversized). Slide 2: 200 px logo stretched "
      "to full screen (low-res). Slide 3: a 1600 px photo cropped to its middle 15% and shown full width (low-res "
      "after crop).",
      expect=[E("M008", "note", slide=1), E("M009", "yellow", slide=2), E("M009", "yellow", slide=3)], commit=False)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    picture(s, kit.noise_jpeg(2400, 1800), x=1, y=1, w=1.5, h=1.125)
    s2 = blank(prs)
    picture(s2, kit.png(200, 112), x=0, y=0, w=20, h=11.25)
    s3 = blank(prs)
    p = picture(s3, kit.png(1600, 900), x=0, y=0, w=20, h=11.25)
    p.crop_left, p.crop_right = 0.425, 0.425
    return save(prs, path)


@deck("M013-uncompressed-cropped", "canva",
      "Six 2400×1800 photos shown small and two heavily cropped: 'Compress pictures' never applied. Threshold "
      "overridden to 1 MB here so the deck stays small in git.",
      expect=[E("M013", "yellow")], overrides={"compress_pitch_min_mb": 1}, commit=False)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    for i in range(3):
        p = picture(s, kit.noise_jpeg(1600, 1200, seed=i + 5, quality=80), x=1 + i * 6, y=1, w=4, h=3)
        if i < 2:
            p.crop_left, p.crop_right = 0.3, 0.3
    return save(prs, path)


@deck("M011-vector-and-tiff", "office2010",
      "Slide 1 EMF, slide 2 WMF (yellow: draw differently on Mac), slide 3 TIFF (fine in current PowerPoint).",
      expect=[E("M011", "yellow", slide=1, subject="emf"), E("M011", "yellow", slide=2, subject="wmf")],
      absent=[E("M011", "problem", slide=3)])
def _(path):
    prs = _office_deck()
    kit.retype_image(picture(blank(prs), kit.emf(), w=3, h=1.5), "image/x-emf", "emf")   # Pillow calls EMF "WMF"
    picture(blank(prs), kit.wmf(), w=3, h=1.5)
    picture(blank(prs), kit.tiff())
    return save(prs, path)


@deck("M011-heic-webp", "canva",
      "Slide 1 HEIC (an iPhone photo, declared image/heic), slide 2 WebP (declared image/webp).",
      expect=[E("M011", "yellow", slide=1, subject="heic"), E("M011", "yellow", slide=2, subject="webp")])
def _(path):
    prs = _canva_deck()
    kit.retype_image(picture(blank(prs), kit.png(40, 30)), "image/heic", "heic")
    kit.retype_image(picture(blank(prs), kit.png(42, 30)), "image/webp", "webp")
    return save(prs, path)


@deck("M011-png-declared-jpeg", "google",
      "PNG bytes in a part declared image/jpeg (.jpeg). Whether PowerPoint minds is unknown: judgment.",
      expect=[E("M011", "problem")],
      xfail="M011 trusts the declared type, so a mismatch between bytes and declared type isn't noticed "
            "(judgment: needs a real PowerPoint test before it's worth a finding)")
def _(path):
    prs = _google_deck()
    kit.retype_image(picture(blank(prs), kit.png(41, 31)), "image/jpeg", "jpeg")
    return save(prs, path)


@deck("M012-4k-video", "powerpoint", "A 3840×2160 H.264 video (one-frame stand-in, 26 KB).",
      expect=[E("M012", "yellow")], absent=["M004"], needs=["ffprobe"])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    kit.video(s, data=(kit.MEDIA / "uhd_4k.mp4").read_bytes())
    return save(prs, path)


# =====================================================================================================
# C: content
# =====================================================================================================

@deck("C001-leftovers", "canva",
      "Slide 1 'Click to add title' typed as text; 2 'Lorem ipsum dolor sit amet'; 3 'Presenter Name' (no brackets); "
      "4 '[Speaker Name]'.",
      expect=[E("C001", "red", slide=1), E("C001", "red", slide=2), E("C001", "problem", slide=3),
              E("C001", "red", slide=4)])
def _(path):
    prs = _canva_deck()
    for t in ("Click to add title", "Lorem ipsum dolor sit amet, consectetur", "Presenter Name\nTitle, Organization",
              "Thank you, [Speaker Name]"):
        s = blank(prs)
        text(s, t, 1, 1, 14, 2, size=40)
    return save(prs, path)


@deck("C001-empty-placeholder-prompt", "powerpoint",
      "Look-alike: empty title/body placeholders (prompts show only while editing) next to real content.",
      absent=["C001"])
def _(path):
    prs = new_deck(WIDE)
    s = prs.slides.add_slide(prs.slide_layouts[1])
    text(s, "Real content on the slide", 1, 5, 8, 1)
    return save(prs, path)


@deck("C002-empty-cases", "powerpoint",
      "Slide 1: only empty placeholders (yellow 'nothing on it'). Slide 2: the only text is white on a white "
      "background (looks empty in the show).",
      expect=[E("C002", "yellow", slide=1), E("C002", "problem", slide=2)])
def _(path):
    prs = new_deck(WIDE)
    prs.slides.add_slide(prs.slide_layouts[1])
    s = blank(prs)
    background(s, "FFFFFF")
    text(s, "Leftover notes from the old version", 1, 1, 8, 1, color="FFFFFF")
    return save(prs, path)


@deck("C004-hidden", "office2010",
      "Five slides: 2 hidden, 5 hidden (at the end), 4 hidden but linked from slide 3 (a deliberate backup).",
      expect=[E("C004", "yellow", slide=2), E("C004", "yellow", slide=4), E("C004", "yellow", slide=5)])
def _(path):
    prs = _office_deck()
    slides = [blank(prs) for _ in range(5)]
    for i, s in enumerate(slides):
        tb = text(s, f"Slide {i + 1}", 1, 1, 6, 1, font="Calibri")
        if i == 2:
            kit.jump_to_slide(tb, slides[3])
    for n in (2, 4, 5):
        slides[n - 1]._element.set("show", "0")
    return save(prs, path)


@deck("C007-comments", "powerpoint",
      "Legacy comment on slide 1, modern (threaded) unresolved comment on slide 2, modern RESOLVED comment on slide 3.",
      expect=[E("C007", "yellow")])
def _(path):
    prs = new_deck(WIDE)
    slides = [blank(prs) for _ in range(3)]
    for i, s in enumerate(slides):
        text(s, f"Slide {i + 1}", 1, 1, 6, 1)
    kit.legacy_comment(prs, slides[0])
    kit.modern_comment(prs, slides[1], n=1)
    kit.modern_comment(prs, slides[2], n=2, status="resolved")
    return save(prs, path)


@deck("C007-resolved-only", "powerpoint",
      "Only resolved modern comments: the review is done. A note at most, not a yellow.",
      absent=["C007"],
      xfail="C007 counts comment parts, not open threads; resolved-only decks still get a yellow (judgment: ask David)")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Final version", 1, 1, 6, 1)
    kit.modern_comment(prs, s, n=1, status="resolved")
    return save(prs, path)


# =====================================================================================================
# X: other
# =====================================================================================================

@deck("X001-fingerprints-google", "google", "Google Slides fingerprint: size, 'Google Shape;…' names, Simple Light.",
      expect=[E("X001", "info", subject="google")])
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "Hello", 1, 1, 4, 1)
    kit.google_names(s)
    return save(prs, path)


@deck("X001-fingerprints-keynote", "keynote", "Keynote export fingerprint: layout names, empty app.xml, Avenir.",
      expect=[E("X001", "info", subject="keynote"), E("F007", "red", subject="Avenir")])
def _(path):
    prs = new_deck(WIDE)
    kit.keynote(prs)
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Hello from Keynote"
    s.shapes.title.text_frame.paragraphs[0].runs[0].font.name = "Avenir"
    return save(prs, path)


@deck("X001-old-office", "office2010",
      "Office 2010 save: AppVersion 14.0000, 4:3, Calibri, 'Office Theme'. X001 has no 'old Office' source yet.",
      expect=[E("X001", "info", subject="powerpoint")])
def _(path):
    prs = _office_deck()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Quarterly review"
    return save(prs, path)


@deck("X001-google-then-canva", "canva",
      "Mixed fingerprints: Google shape names and Google theme, then re-exported by Canva (Canva size, Calibri (MS)). "
      "Should say both, so the Canva preset still applies.",
      expect=[E("X001", "info", subject="canva")])
def _(path):
    prs = _canva_deck()
    kit.set_theme(prs, name="Simple Light")
    s = blank(prs)
    text(s, "Merged deck", 1, 1, 8, 1.5, font="Calibri (MS)", size=40)
    text(s, "From Google, then Canva", 1, 3, 8, 1.5, font="Calibri (MS)", size=30)
    kit.google_names(s)
    return save(prs, path)


def _x002(rename, broken, expect=None, absent=None, xfail=None):
    def build(path):
        prs = new_deck(WIDE)
        s = blank(prs)
        text(s, "File name test", 1, 1, 6, 1)
        return save(prs, path)
    return Spec(f"X002-{rename[1]}", "bad-design", broken, build=build, rename=rename[0],
                expect=expect or [], absent=absent or [], xfail=xfail)


SPECS.extend([
    _x002(("Keynote 🎤 final.pptx", "emoji-name"), "File name with an emoji.", expect=[E("X002", "yellow")]),
    _x002(("Session #4 slides.pptx", "hash-name"), "File name with '#' (breaks file:// URLs and some playback apps).",
          expect=[E("X002", "yellow")],
          xfail="BAD_CHARS doesn't include '#' (or '%', '&'); judgment: ask David whether show software trips on it"),
    _x002(("N" * 130 + ".pptx", "long-name"), "A 135-character file name.", expect=[E("X002", "yellow")]),
])


@deck("X002-long-path", "bad-design",
      "Short file name, but the folder path makes the full path over 260 characters (Windows MAX_PATH).",
      expect=[E("X002", "yellow")], rename="deep")
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Deep folder", 1, 1, 6, 1)
    return save(prs, path)


@deck("X002-2gb-deck", "bad-design", "A 2 GB deck (sparse file: 2 GB of zero bytes in front of a valid zip).",
      expect=[E("X002", "yellow", subject="size")], commit=False, rename="big", slow=True)
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Huge file", 1, 1, 6, 1)
    return save(prs, path)


@deck("X003-ole-objects", "office2010",
      "Embedded Excel sheet, Word document, PDF (Acrobat) and Visio drawing, one per slide.",
      expect=[E("X003", "yellow", slide=n) for n in range(1, 5)])
def _(path):
    prs = _office_deck()
    for prog in ("Excel.Sheet.12", "Word.Document.12", "Acrobat.Document.DC", "Visio.Drawing.15"):
        s = blank(prs)
        kit.ole_object(prs, s, prog, f"Object {prog}")
    return save(prs, path)


@deck("X004-local-links", "office2010",
      "Linked pictures on C:\\Users\\…, \\\\server\\share and /Users/…, and an OLE chart linked to C:\\.",
      expect=[E("X004", "red", slide=n) for n in range(1, 5)])
def _(path):
    prs = _office_deck()
    for target in ("file:///C:/Users/sample/Pictures/logo.png", "\\\\fileserver\\share\\photos\\venue.jpg",
                   "/Users/sample/Desktop/map.png"):
        kit.link_picture(blank(prs), target)
    kit.ole_object(prs, blank(prs), "Excel.Sheet.12", "Linked chart", link_target="file:///C:/Users/sample/Budget.xlsx")
    return save(prs, path)


# =====================================================================================================
# Section 4: break the engine itself
# =====================================================================================================

def _plain_deck(path, slides=1):
    prs = new_deck(WIDE)
    for i in range(slides):
        text(blank(prs), f"Slide {i + 1}", 1, 1, 6, 1)
    return save(prs, path)


def _zip_edit(path, edits: dict):
    """Rewrite members of a zip: {name: bytes | None (drop) | callable(old) -> bytes}."""
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in edits:
                e = edits[info.filename]
                if e is None:
                    continue
                data = e(zin.read(info)) if callable(e) else e
                zout.writestr(info.filename, data)
            else:
                zout.writestr(info, zin.read(info))
    tmp.replace(path)
    return path


@deck("R-truncated", "engine", "First half of a valid deck (interrupted download).", kind="robust", outcome="error")
def _(path):
    _plain_deck(path, 3)
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])
    return path


CFB = bytes.fromhex("D0CF11E0A1B11AE1")


@deck("R-encrypted", "engine",
      "Password-protected deck: an OLE compound file holding 'EncryptionInfo' and 'EncryptedPackage' streams "
      "(stand-in: CFB header + stream names, not a real encrypted file). Should say 'password-protected'.",
      kind="robust", outcome="error",
      real_ppt="File ▸ Passwords ▸ Password to open: 'sample'; save as .pptx. Done on the Mac 2026-10-13 (AppleScript "
               "`set password`): same message as the stand-in. Not committed: PowerPoint writes the user's name into "
               "the encrypted part and the password is public; re-save with a sample user name first.")
def _(path):
    names = b"".join(n.encode("utf-16-le") for n in ("Root Entry", "EncryptionInfo", "EncryptedPackage"))
    path.write_bytes(CFB + b"\0" * 504 + names + b"\0" * 1024)
    return path


@deck("R-ppt-renamed", "engine", "An old binary .ppt (compound file, 'PowerPoint Document' stream) renamed to .pptx.",
      kind="robust", outcome="error")
def _(path):
    path.write_bytes(CFB + b"\0" * 504 + "PowerPoint Document".encode("utf-16-le") + b"\0" * 1024)
    return path


@deck("R-macro-pptm", "engine", "A macro-enabled deck (.pptm, vbaProject.bin). Expected: scans (X003 'macros') "
      "or a plain refusal.", kind="robust", outcome="ok", rename="R-macro.pptm",
      xfail="the CLI refuses anything but .pptx by extension; .pptm decks reach show machines (judgment: ask David)")
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Macro deck", 1, 1, 6, 1)
    kit.add_part(prs, prs.part, "/ppt/vbaProject.bin", "application/vnd.ms-office.vbaProject", kit.VBA_RT, b"VBA")
    save(prs, path)
    return path


@deck("R-show-ppsx", "engine", "A PowerPoint Show (.ppsx): same zip as .pptx with a different main content type. "
      "Show machines get these. Expected: scans.", kind="robust", outcome="ok", rename="R-show.ppsx",
      xfail="the CLI refuses .ppsx by extension")
def _(path):
    _plain_deck(path)
    return _zip_edit(path, {"[Content_Types].xml": lambda b: b.replace(
        b"presentationml.presentation.main+xml", b"presentationml.slideshow.main+xml")})


@deck("R-zip-bomb", "engine", "Zip whose slide1.xml unpacks to 257 MB (~250 KB file). Must be refused fast.",
      kind="robust", outcome="error")
def _(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", b'<?xml version="1.0"?><Types/>')
        with z.open("ppt/slides/slide1.xml", "w", force_zip64=True) as f:
            chunk = b" " * (1 << 20)
            for _ in range(257):
                f.write(chunk)
    return path


@deck("R-missing-layout", "engine", "Slide whose layout relationship was removed.", kind="robust", outcome="ok")
def _(path):
    _plain_deck(path, 2)
    def drop(b):
        root = etree.fromstring(b)
        for rel in list(root):
            if rel.get("Type", "").endswith("/slideLayout"):
                root.remove(rel)
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _zip_edit(path, {"ppt/slides/_rels/slide1.xml.rels": drop})


@deck("R-rel-to-missing-part", "engine", "Slide relationship pointing at ppt/media/image99.png, which isn't in the zip.",
      kind="robust", outcome="ok")
def _(path):
    _plain_deck(path)
    def add(b):
        root = etree.fromstring(b)
        etree.SubElement(root, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship",
                         Id="rId99", Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image",
                         Target="../media/image99.png")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _zip_edit(path, {"ppt/slides/_rels/slide1.xml.rels": add})


@deck("R-sldid-nowhere", "engine", "presentation.xml lists a slide whose r:id has no relationship.",
      # Round 1 expected "ok"; 2026-10-14: one plain refusal is right (PowerPoint would ask to repair it too).
      kind="robust", outcome="error")
def _(path):
    _plain_deck(path, 2)
    def add(b):
        root = etree.fromstring(b)
        lst = root.find(qn("p:sldIdLst"))
        etree.SubElement(lst, qn("p:sldId"), {"id": "999", qn("r:id"): "rId999"})
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    return _zip_edit(path, {"ppt/presentation.xml": add})


@deck("R-duplicate-shape-ids", "engine",
      "Two off-slide text boxes sharing shape id 5 (merged slides do this). Both must be fixed, or neither; never "
      "the wrong one.", kind="robust", outcome="ok", expect=[E("G001", "red")])
# 2026-10-14: "neither". A shape whose id is shared on its slide is never fixed (runner._shared_id); both stay red
# with a plain reason. test_adversarial checks that nothing moved.
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    a = text(s, "First pinned left", -0.8, 1, 6, 1)
    b = text(s, "Second pinned left", -0.8, 4, 6, 1)
    for sh in (a, b):
        sh._element.nvSpPr.cNvPr.set("id", "5")
    return save(prs, path)


@deck("R-unicode-extremes", "engine",
      "RTL Arabic and Hebrew (rtl='1'), vertical CJK, stacked combining marks, a 10,000-character paragraph.",
      kind="robust", outcome="ok")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    for t in (text(s, "مرحبا بكم في المعرض السنوي", 1, 0.5, 8, 1), text(s, "ברוכים הבאים לתערוכה", 1, 1.6, 8, 1)):
        t.text_frame.paragraphs[0]._p.get_or_add_pPr().set("rtl", "1")
    body_pr(text(s, "縦書き日本語のテキスト", 11, 0.5, 1, 6), vert="eaVert")
    text(s, "Z\u0351\u036b\u0343\u036a\u0302a\u0300\u0301\u0302\u0303\u0304lgo\u0489", 1, 3, 8, 1)
    text(s, ("word " * 2000).strip(), 1, 4.5, 8, 2, size=8)
    return save(prs, path)


@deck("R-500-slides", "engine", "500 slides with a title and a line of text each.", kind="robust", outcome="ok",
      slow=True)
def _(path):
    prs = new_deck(WIDE)
    for i in range(500):
        s = blank(prs)
        text(s, f"Session {i + 1}", 1, 0.5, 8, 1, size=36)
        text(s, "Room, time and speaker", 1, 2, 8, 1)
    return save(prs, path)


@deck("R-zero-slides", "engine", "A deck with no slides at all.", kind="robust", outcome="ok")
def _(path):
    return save(new_deck(WIDE), path)


@deck("R-2000-shapes", "engine", "One slide with 2,000 small text boxes (a seating chart).", kind="robust", outcome="ok")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    for i in range(2000):
        text(s, f"{i + 1}", 0.1 + (i % 50) * 0.26, 0.1 + (i // 50) * 0.18, 0.25, 0.17, size=6)
    return save(prs, path)


@deck("R-rich-objects", "engine",
      "SmartArt (approximate XML), a chart with a title, a table with merged cells, an equation (OMML) and an ink "
      "drawing (approximate). Repair must keep every one.", kind="robust", outcome="ok",
      real_ppt="Insert each object in PowerPoint (Insert ▸ SmartArt, Chart, Table + Merge Cells, Equation, Draw ▸ Pen) "
               "and save on Mac and Windows; replace this deck with that file.")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    _smartart(prs, s, ["One", "Two", "Three"], font="Arial")
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("Votes", (3, 5))
    ch = s.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(7), Inches(0.3), Inches(5), Inches(3), data).chart
    ch.has_title = True
    ch.chart_title.text_frame.text = "Sample poll"
    tbl = s.shapes.add_table(3, 3, Inches(0.5), Inches(4), Inches(6), Inches(2)).table
    tbl.cell(0, 0).merge(tbl.cell(0, 2))
    tbl.cell(0, 0).text = "Merged header"
    tbl.cell(1, 0).text = "Row"
    s.shapes._spTree.append(etree.fromstring(_EQUATION))
    s.shapes._spTree.append(etree.fromstring(_INK.replace("{RID}", _ink_part(prs, s))))
    return save(prs, path)


@deck("R-render-safety", "engine",
      "Planted links for the render copy: a UNC linked picture, an http:// OLE link, an ActiveX control and macros. "
      "deck.write_render_copy must neutralise all of them.", kind="robust", outcome="ok",
      expect=[E("X003", "yellow", subject="activex"), E("X004", "red")])
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    kit.link_picture(s, "\\\\203.0.113.5\\share\\logo.png")
    kit.ole_object(prs, s, "Excel.Sheet.12", "Web sheet", link_target="http://203.0.113.5/budget.xlsx", x=5)
    r_id, _ = kit.add_part(prs, s.part, "/ppt/activeX/activeX1.xml", "application/vnd.ms-office.activeX+xml",
                           kit.CONTROL_RT, b'<?xml version="1.0"?><ax:ocx xmlns:ax="http://schemas.microsoft.com/office/2006/activeX" ax:classid="{8BD21D40-EC42-11CE-9E0D-00AA006002F3}"/>')
    controls = etree.fromstring(f'<p:controls {NSDECL}><p:control name="TextBox1" r:id="{r_id}" '
                                f'imgW="914400" imgH="304800"/></p:controls>')
    s._element.cSld.append(controls)
    kit.add_part(prs, prs.part, "/ppt/vbaProject.bin", "application/vnd.ms-office.vbaProject", kit.VBA_RT, b"VBA")
    return save(prs, path)


# --- approximate rich-object XML (marked real_ppt above) -------------------------------------------

def _smartart(prs, slide, steps, font):
    dgm = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
    dsp = "http://schemas.microsoft.com/office/drawing/2008/diagram"
    base = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    n = sum(1 for p in prs.part.package.iter_parts() if "/diagrams/data" in str(p.partname)) + 1
    pts = "".join(f'<dgm:pt modelId="{{0000000{i}-0000-0000-0000-000000000000}}"><dgm:t><a:bodyPr/><a:p><a:r>'
                  f'<a:rPr lang="en-US"><a:latin typeface="{font}"/></a:rPr><a:t>{t}</a:t></a:r></a:p></dgm:t></dgm:pt>'
                  for i, t in enumerate(steps, 1))
    data = f'<dgm:dataModel xmlns:dgm="{dgm}" xmlns:a="{NS["a"]}"><dgm:ptLst>{pts}</dgm:ptLst><dgm:cxnLst/></dgm:dataModel>'
    shapes = "".join(
        f'<dsp:sp modelId="{{1000000{i}-0000-0000-0000-000000000000}}"><dsp:nvSpPr><dsp:cNvPr id="0" name=""/>'
        f'<dsp:cNvSpPr/></dsp:nvSpPr><dsp:spPr><a:xfrm><a:off x="{i * 2000000}" y="0"/><a:ext cx="1800000" cy="900000"/>'
        f'</a:xfrm><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom></dsp:spPr><dsp:txBody><a:bodyPr/><a:p><a:r>'
        f'<a:rPr lang="en-US" sz="2400"><a:latin typeface="{font}"/></a:rPr><a:t>{t}</a:t></a:r></a:p></dsp:txBody>'
        f'</dsp:sp>' for i, t in enumerate(steps))
    drawing = f'<dsp:drawing xmlns:dsp="{dsp}" xmlns:a="{NS["a"]}"><dsp:spTree><dsp:nvGrpSpPr><dsp:cNvPr id="0" name=""/>' \
              f'<dsp:cNvGrpSpPr/></dsp:nvGrpSpPr><dsp:grpSpPr/>{shapes}</dsp:spTree></dsp:drawing>'
    ct = "application/vnd.openxmlformats-officedocument.drawingml.diagram"
    ids = {}
    for kind, blob, rt in (("data", data, f"{base}/diagramData"),
                           ("layout", f'<dgm:layoutDef xmlns:dgm="{dgm}"/>', f"{base}/diagramLayout"),
                           ("quickStyle", f'<dgm:styleDef xmlns:dgm="{dgm}"/>', f"{base}/diagramQuickStyle"),
                           ("colors", f'<dgm:colorsDef xmlns:dgm="{dgm}"/>', f"{base}/diagramColors"),
                           ("drawing", drawing, "http://schemas.microsoft.com/office/2007/relationships/diagramDrawing")):
        sub = {"data": "Data", "layout": "Layout", "quickStyle": "Style", "colors": "Colors", "drawing": "Drawing"}[kind]
        ctype = (f"{ct}{sub}+xml" if kind != "drawing" else "application/vnd.ms-office.drawingml.diagramDrawing+xml")
        ids[kind], _ = kit.add_part(prs, slide.part, f"/ppt/diagrams/{kind}{n}.xml", ctype, rt,
                                    ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + blob).encode())
    sid = kit.next_id(slide)
    xml = (f'<p:graphicFrame {NSDECL}><p:nvGraphicFramePr><p:cNvPr id="{sid}" name="Diagram {n}"/><p:cNvGraphicFramePr/>'
           f'<p:nvPr/></p:nvGraphicFramePr><p:xfrm><a:off x="457200" y="457200"/><a:ext cx="6000000" cy="900000"/></p:xfrm>'
           f'<a:graphic><a:graphicData uri="{dgm}"><dgm:relIds xmlns:dgm="{dgm}" r:dm="{ids["data"]}" '
           f'r:lo="{ids["layout"]}" r:qs="{ids["quickStyle"]}" r:cs="{ids["colors"]}"/></a:graphicData></a:graphic>'
           f'</p:graphicFrame>')
    slide.shapes._spTree.append(etree.fromstring(xml))


_EQUATION = (
    f'<mc:AlternateContent {NSDECL} xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main">'
    f'<mc:Choice Requires="a14"><p:sp><p:nvSpPr><p:cNvPr id="900" name="Equation"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
    f'<p:spPr><a:xfrm><a:off x="7000000" y="3500000"/><a:ext cx="3000000" cy="600000"/></a:xfrm><a:prstGeom prst="rect">'
    f'<a:avLst/></a:prstGeom></p:spPr><p:txBody><a:bodyPr/><a:p><a14:m><m:oMathPara '
    f'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"><m:oMath><m:r><m:t>y=mx+b</m:t></m:r></m:oMath>'
    f'</m:oMathPara></a14:m></a:p></p:txBody></p:sp></mc:Choice><mc:Fallback><p:sp><p:nvSpPr><p:cNvPr id="900" '
    f'name="Equation"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="7000000" y="3500000"/>'
    f'<a:ext cx="3000000" cy="600000"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr><p:txBody>'
    f'<a:bodyPr/><a:p><a:r><a:rPr lang="en-US"/><a:t>y = mx + b</a:t></a:r></a:p></p:txBody></p:sp></mc:Fallback>'
    f'</mc:AlternateContent>')

_INK = (f'<mc:AlternateContent {NSDECL}><mc:Choice Requires="p14"><p14:contentPart r:id="{{RID}}" '
        f'xmlns:p14="{NS["p14"]}"><p14:nvContentPartPr><p14:cNvPr id="901" name="Ink 1"/><p14:cNvContentPartPr/>'
        f'<p14:nvPr/></p14:nvContentPartPr><p14:xfrm><a:off x="8000000" y="5000000"/><a:ext cx="1000000" cy="500000"/>'
        f'</p14:xfrm></p14:contentPart></mc:Choice><mc:Fallback/></mc:AlternateContent>')


def _ink_part(prs, slide):
    ink = (b'<?xml version="1.0"?><inkml:ink xmlns:inkml="http://www.w3.org/2003/InkML">'
           b'<inkml:trace>0 0, 10 10, 20 5</inkml:trace></inkml:ink>')
    r_id, _ = kit.add_part(prs, slide.part, "/ppt/ink/ink1.xml", "application/inkml+xml",
                           "http://schemas.openxmlformats.org/officeDocument/2006/relationships/customXml", ink)
    return r_id


# =====================================================================================================
# Section 5: problems SlideTistic doesn't check yet (NEW). Each is an xfail until a check exists.
# =====================================================================================================

def new_problem(name, source, broken, how, **kw):
    def register(fn):
        SPECS.append(Spec(name=name, source=source, broken=broken, build=fn, kind="new", new=how,
                          expect=kw.pop("expect", [E("NEW", "problem")]),
                          xfail=kw.pop("xfail", "no check for this yet (docs/ADVERSARIAL_RESULTS.md §5)"), **kw))
        return fn
    return register


@new_problem("NEW-01-text-same-colour-as-background", "canva",
             "White text on a white slide background (invisible leftover), and dark grey on black.",
             "Resolve each run's colour (run → paragraph → list style → placeholder → master, scheme colours via the "
             "theme and clrMap) and the background behind the box (slide bg → layout → master, or a filled shape "
             "under it). Flag contrast < 1.5:1 as yellow 'invisible text'. With the render: sample pixels under the "
             "letters. Fix: not safe automatically (it may be deliberate); offer 'delete' in the review.")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    background(s, "FFFFFF")
    text(s, "Sample Org, Sample Department", 2, 4, 12, 1, size=36, color="1A1A1A")
    text(s, "Old presenter's name", 2, 5, 12, 1, size=36, color="FFFFFF")
    s2 = blank(prs)
    background(s2, "000000")
    text(s2, "Barely there", 2, 4, 12, 1, size=36, color="141414")
    return save(prs, path)


@new_problem("NEW-02-text-on-busy-photo", "canva",
             "Thin white 20 pt text across a busy (noise) photo: WCAG contrast well under 3:1 in places.",
             "Needs the render: rasterise the slide (pdftoppm), take the letter boxes from pdftotext, compare the text "
             "colour with the 10th-percentile background luminance under each line; flag < 3:1 as yellow. Data-only "
             "approximation: text box over a picture (L011's geometry) + light text colour. Fix: not automatic; "
             "suggest a dark band behind the text.", layout=True)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    picture(s, kit.noise_jpeg(400, 225, quality=60), x=0, y=0, w=20, h=11.25)
    text(s, "Thin caption over a busy photo", 2, 8, 16, 1, size=20, color="FFFFFF")
    return save(prs, path)


@new_problem("NEW-03-small-body-text", "bad-design",
             "Body text at 10–12 pt on a 13.33 in slide: unreadable from the back of a ballroom.",
             "Resolve each visible run's size (run → paragraph → placeholder → master body style; normAutofit fontScale "
             "applies). Flag body text under 18 pt (threshold in YAML) when it's more than a few words; skip footers, "
             "captions in the bottom band and tables. Yellow. Fix: never automatic (it reflows everything).")
def _(path):
    prs = new_deck(WIDE)
    s = blank(prs)
    text(s, "Results", 0.6, 0.4, 12, 1, size=40)
    text(s, "\n".join(["Eleven point body text explaining the method in detail, sentence after sentence."] * 6),
         0.6, 1.6, 12, 5, size=11)
    return save(prs, path)


@new_problem("NEW-04-builds-and-exit-on-last-click", "office2010",
             "Four bullets each appear on a click, and the last click EXITS the summary: if the presenter "
             "advances early the slide moves on with content never shown; the last build hides content.",
             "Count click-triggered entrance effects per slide (playback.animated_shape_ids already finds entr/exit). "
             "Note: 'N clicks before this slide moves on'. Exit effect on the last click group: yellow. In this real "
             "save, Appear is presetID 1 (entr) and Disappear is presetID 1 (exit), not the Fade (10) the old stand-in "
             "used.",
             saved=f"PowerPoint for Mac 16.113.4, 2026-10-13: plain text boxes from python-pptx, then AppleScript `add effect … fx animation type "
                   "appear trigger on page click` on the 4 bullets, and the same with `exit animation` true on the "
                   "summary box; saved by PowerPoint. Windows save still to do.")
def _(path):
    raise AssertionError("saved PowerPoint file; see Spec.saved")


@new_problem("NEW-05-long-transitions-morph", "powerpoint",
             "A 6 s Vortex transition and a Morph transition (p159:morph), which Office 2016/2019 can't play.",
             "Read p:transition dur/spd, including inside mc:AlternateContent: in this real save BOTH transitions sit "
             "in mc:Choice (Vortex as p14:vortex with p14:dur='6000', Morph as p159:morph), with a plain fade as the "
             "mc:Fallback. A detector reading only top-level p:transition sees the fades. Yellow when duration > 2 s; "
             "yellow for Morph ('needs PowerPoint 2019/365; older versions fade').",
             saved=f"PowerPoint for Mac 16.113.4, 2026-10-13: three plain slides from python-pptx, then AppleScript `entry effect vortex left` with "
                   "`transition duration` 6 on slide 2 and `entry effect morph by object` on slide 3; saved by "
                   "PowerPoint. Windows save still to do.")
def _(path):
    raise AssertionError("saved PowerPoint file; see Spec.saved")


@new_problem("NEW-06-google-theme-font-substitution", "google",
             "Google export: theme fonts renamed to 'Proxima Nova'/'Google Sans', text uses +mj-lt/+mn-lt only, "
             "Arial embedded under the theme names as stand-ins.",
             "F007 already resolves theme references through font_use.visible_fonts; the gap is telling the crew that "
             "the stand-in decides the look: when F005's 'exporter stand-in' fires for a THEME font, raise one "
             "deck-level yellow ('every heading will show as Arial'). Detect-only.",
             expect=[E("F005", "yellow", subject="Proxima Nova"), E("F005", "yellow", subject="Google Sans")],
             absent=[("F007", "red")], xfail=None)
def _(path):
    prs = _google_deck()
    kit.set_theme(prs, major="Proxima Nova", minor="Google Sans")
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Theme heading"
    s.placeholders[1].text = "Theme body text"
    kit.google_names(s)
    _embeds(prs, embed("Proxima Nova", "regular", "Arial"), embed("Google Sans", "regular", "Arial"))
    return save(prs, path)


@new_problem("NEW-07-uncompressed-pictures", "canva",
             "Same as M013 but under the default thresholds: two 2 MB photos shown as thumbnails. M013 is the check; "
             "this deck shows the default pitch (≥25 % and ≥5 MB) stays quiet on small decks, which is right.",
             "Covered by M013 (fix off by default). Nothing new to build.",
             expect=[], absent=["M013"], xfail=None, commit=False)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    for i in range(2):
        picture(s, kit.noise_jpeg(1600, 1200, seed=20 + i, quality=80), x=1 + i * 5, y=1, w=3, h=2.25)
    return save(prs, path)


@new_problem("NEW-08-content-in-notes", "bad-design",
             "Slide 2 is blank but its speaker notes hold 180 words of what should be on screen.",
             "Per slide: visible words (C002's text) ≤ 3 and notes words ≥ 50 → yellow 'the content may be in the "
             "notes'. Detect-only.")
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Introduction", 1, 1, 8, 1)
    s = blank(prs)
    s.notes_slide.notes_text_frame.text = " ".join(["The second point covers rotation schedules and water."] * 20)
    return save(prs, path)


@new_problem("NEW-09-footers-disagree", "office2010",
             "Slides 1–3 use a real slide-number field; slide 4's 'number' is typed text '7' and its footer says an "
             "old event name.",
             "Collect footer/slide-number placeholders (ph type sldNum/ftr/dt) per slide: a sldNum placeholder with no "
             "a:fld type='slidenum' is static text → yellow 'slide number typed by hand'; footers whose text differs "
             "from the majority → note. Detect-only.")
def _(path):
    prs = _office_deck()
    for i in range(4):
        s = blank(prs)
        text(s, f"Topic {i + 1}", 1, 1, 6, 1, font="Calibri")
        num = text(s, str(i + 1), 9, 7, 0.8, 0.4, font="Calibri", size=12, name="Slide Number Placeholder")
        if i < 3:
            r = num.text_frame.paragraphs[0]._p
            for run in r.findall(qn("a:r")):
                r.remove(run)
            fld = etree.SubElement(r, qn("a:fld"), id="{B6F15528-21DE-4FAA-801E-634DDDAF4B2B}", type="slidenum")
            etree.SubElement(fld, qn("a:rPr"), lang="en-US")
            etree.SubElement(fld, qn("a:t")).text = str(i + 1)
            r.insert(0, fld)
        else:
            num.text_frame.text = "7"
        text(s, "Sample Expo 2026" if i < 3 else "Sample Expo 2023", 3, 7, 4, 0.4, font="Calibri", size=12,
             name="Footer Placeholder")
    return save(prs, path)


@new_problem("NEW-10-merged-slide-sizes", "bad-design",
             "16:9 deck with slides pasted from a 4:3 deck: their content sits in a 10 in-wide column, a picture "
             "stretched to the old size.",
             "Per slide, the bounding box of all shapes vs the slide: content spanning ≤ 75 % of the width, starting "
             "near x=0, matching 4:3 proportions → yellow 'slide may have come from a 4:3 deck'. Detect-only.")
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Native wide slide", 0.6, 0.5, 12, 1)
    s = blank(prs)
    text(s, "Pasted 4:3 slide", 0.5, 0.5, 9, 1)
    picture(s, kit.png(40, 30), x=0, y=1.6, w=10, h=5.9)
    return save(prs, path)


@new_problem("NEW-11-audio-across-slides", "office2010",
             "Background music meant to play across the deck stops after 2 slides (numSld too small). NOT faked: "
             "needs a real-PowerPoint copy. This deck only carries the audio; the timing comes from PowerPoint.",
             "Read p:audio/p:cMediaNode numSld (or the 'stop after N slides' play command) and compare with the slide "
             "count after the audio's slide; yellow when it stops early. Detect-only.",
             real_ppt="Insert ▸ Audio on slide 1 of a 6-slide deck, Playback ▸ Play Across Slides, then Animation Pane "
                      "▸ Effect Options ▸ Stop playing after 2 slides; save on Mac and Windows.")
def _(path):
    prs = _office_deck()
    s = blank(prs)
    a = kit.video(s, data=(kit.MEDIA / "tone.mp3").read_bytes(), mime="audio/mpeg", w=1, h=1)
    kit.as_audio(a)
    kit.rename_media(a, "mp3", "audio/mpeg")
    for i in range(5):
        text(blank(prs), f"Slide {i + 2}", 1, 1, 6, 1, font="Calibri")
    return save(prs, path)


@new_problem("NEW-12-next-button-skips", "office2010",
             "Kiosk-style 'Next' buttons: slide 1's jumps to slide 3 (skips 2); slide 3's says Next but jumps to 1.",
             "Follow hlinksldjump / hlinkshowjump targets per slide: a button whose text says Next/Continue/→ but "
             "doesn't land on n+1 → yellow. Detect-only.")
def _(path):
    prs = _office_deck()
    slides = [blank(prs) for _ in range(3)]
    for i, s in enumerate(slides):
        text(s, f"Menu page {i + 1}", 1, 1, 6, 1, font="Calibri")
    kit.jump_to_slide(text(slides[0], "Next ▶", 7, 6, 2, 0.8, font="Calibri"), slides[2])
    kit.jump_to_slide(text(slides[2], "Next ▶", 7, 6, 2, 0.8, font="Calibri"), slides[0])
    return save(prs, path)


@new_problem("NEW-13-covered-shapes", "canva",
             "A text box and a chart wholly covered by a full-slide opaque picture placed above them (dead content).",
             "z-order walk per slide: a text-bearing shape whose bounds lie inside a later opaque, unrotated picture or "
             "filled shape (no transparency, no alpha) → yellow 'hidden behind <name>'. With the render: its words "
             "aren't in pdftotext. Detect-only.")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Speaker bio nobody will see", 3, 3, 10, 2, size=36)
    picture(s, kit.noise_jpeg(400, 225, quality=50, seed=3), x=0, y=0, w=20, h=11.25, name="Full bleed photo")
    return save(prs, path)


@new_problem("NEW-14-grouped-transparent-pictures", "canva",
             "Group of three PNGs with alpha (soft shadows) inside another group: older Windows PowerPoint renders "
             "the transparent areas black when printing/exporting.",
             "Find pictures with an alpha channel (PNG colour type 4/6 or tRNS) inside groups; note-level yellow, "
             "only when the deck's source is Canva. Needs a real-PowerPoint render on Office 2016 to confirm.",
             layout=True)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    outer = s.shapes.add_group_shape()
    inner = outer.shapes.add_group_shape()
    for i in range(3):
        picture(inner.shapes, kit.flat_png(64, 64, (0, 0, 0, 90)), x=2 + i * 4, y=3, w=3, h=3)
    return save(prs, path)


@new_problem("NEW-15-wordart-effects", "office2010",
             "WordArt with 3D bevel, glow and reflection (a:sp3d, a:glow, a:reflection): Mac and Windows draw these "
             "differently.",
             "Look for a:effectLst/a:glow, a:reflection, a:sp3d, a:scene3d, prstTxWarp on text-bearing shapes → note. "
             "The visual review is where it's judged.")
def _(path):
    prs = _office_deck()
    s = blank(prs)
    t = text(s, "GRAND OPENING", 1, 2, 8, 2, font="Calibri", size=60)
    sppr = t._element.spPr
    sppr.append(etree.fromstring(f'<a:effectLst xmlns:a="{NS["a"]}"><a:glow rad="139700"><a:srgbClr val="FFC000">'
                                 f'<a:alpha val="40000"/></a:srgbClr></a:glow><a:reflection blurRad="6350" stA="50000" '
                                 f'endA="300" endPos="55000" dir="5400000" sy="-100000" algn="bl" rotWithShape="0"/>'
                                 f'</a:effectLst>'))
    sppr.append(etree.fromstring(f'<a:scene3d xmlns:a="{NS["a"]}"><a:camera prst="orthographicFront"/>'
                                 f'<a:lightRig rig="threePt" dir="t"/></a:scene3d>'))
    sppr.append(etree.fromstring(f'<a:sp3d xmlns:a="{NS["a"]}"><a:bevelT w="63500" h="25400"/></a:sp3d>'))
    return save(prs, path)


@new_problem("NEW-16-otf-cff-embed", "canva",
             "An embedded font whose file is OpenType-CFF ('OTTO' data, PostScript outlines). PowerPoint for Windows "
             "can't use CFF embeds; Mac 16.17+ can.",
             "fonts.read_embed already parses the file: if the sfnt tag is 'OTTO' (CFF/CFF2), yellow 'embedded as "
             "OpenType-CFF; Windows PowerPoint ignores it; install the font'. Detect-only.")
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Postscript outlines", 1, 1, 14, 1.5, font="Sample Display", size=54)
    _embeds(prs, embed("Sample Display", "regular", "Sample Display", bare_ttf=True))
    part = next(p for p in prs.part.package.iter_parts() if str(p.partname).startswith("/ppt/fonts/"))
    part._blob = b"OTTO" + part.blob[4:]
    return save(prs, path)


@new_problem("NEW-17-rtl-direction-lost", "google",
             "Arabic and Hebrew paragraphs with no rtl='1' and left alignment (direction lost on export): punctuation "
             "and numbers land on the wrong side.",
             "Paragraph text whose strong characters are mostly RTL (Unicode bidi class R/AL) but pPr rtl is not '1' "
             "→ yellow. Fix (set rtl='1', algn='r') is plausible but needs a real-PowerPoint before/after first.")
def _(path):
    prs = _google_deck()
    s = blank(prs)
    text(s, "مرحبا بكم: الجلسة 2، القاعة 5.", 0.5, 0.5, 9, 1, size=32, align=PP_ALIGN.LEFT)
    text(s, "ברוכים הבאים: מושב 3, אולם 1.", 0.5, 2, 9, 1, size=32, align=PP_ALIGN.LEFT)
    kit.google_names(s)
    return save(prs, path)


@new_problem("NEW-18-chart-linked-to-excel", "office2010",
             "A chart whose data is linked to C:\\Users\\…\\sales.xlsx (externalData with autoUpdate): PowerPoint asks "
             "'update links?' on open.",
             "X004 sees the external relationship from the chart part (it should already fire: checked below). New "
             "wording: chart links prompt on open; tell the crew to break the link (File ▸ Info ▸ Edit links).",
             expect=[E("X004", "red")], xfail=None)
def _(path):
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    prs = _office_deck()
    s = blank(prs)
    data = CategoryChartData()
    data.categories = ["Q1", "Q2"]
    data.add_series("Sales", (10, 12))
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE, Inches(1), Inches(1), Inches(8), Inches(5), data)
    cpart = gf.chart.part
    for r_id, rel in list(cpart.rels.items()):
        if rel.reltype == RT.PACKAGE:
            cpart.drop_rel(r_id)
    r_id = cpart.relate_to("file:///C:/Users/sample/Documents/sales.xlsx", RT.OLE_OBJECT, is_external=True)
    ext = cpart._element.find(qn("c:externalData"))
    if ext is None:
        ext = etree.SubElement(cpart._element, qn("c:externalData"))
    ext.set(qn("r:id"), r_id)
    etree.SubElement(ext, qn("c:autoUpdate"), val="1")
    return save(prs, path)


@new_problem("NEW-19-duplicate-slides", "bad-design",
             "Slides 2 and 3 are identical (same text, same picture): merged decks do this.",
             "Hash each slide's visible text + picture part digests; consecutive equal hashes → yellow 'slide N repeats "
             "slide N-1'. Detect-only (deleting is the presenter's call).")
def _(path):
    prs = new_deck(WIDE)
    text(blank(prs), "Welcome", 1, 1, 6, 1)
    for _ in range(2):
        s = blank(prs)
        text(s, "Our three priorities", 1, 1, 6, 1)
        picture(s, kit.png(30, 20), x=7, y=1, w=4, h=3)
    return save(prs, path)


@new_problem("NEW-20-near-white-theme-text", "bad-design",
             "Theme colour scheme maps dark text (dk1) to #E8E8E8 on a white background: body text is near-white.",
             "Resolve the theme's dk1/tx1 through clrMap and compare with lt1/bg1 (or the slide background): contrast "
             "under 3:1 for text using scheme colours → yellow, deck-level. Detect-only.")
def _(path):
    prs = new_deck(WIDE)
    kit.set_theme(prs, colors={"dk1": "E8E8E8"})
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Pale heading"
    s.placeholders[1].text = "Pale body text in the theme colour"
    return save(prs, path)


@new_problem("NEW-21-deck-level-kiosk-timings", "office2010",
             "Deck-level: 'Use timings' on, kiosk mode, and the only timings are 2 s on some slides.",
             "P003 already flags kiosk (red); P001 flags the timings. The gap is the combination: kiosk + timings that "
             "don't cover every slide = the show stops on an untimed slide with no way to advance. Raise red.",
             expect=[E("P003", "red", subject="kiosk"), E("P001", "yellow")], xfail=None)
def _(path):
    prs = _office_deck()
    for i in range(4):
        s = blank(prs)
        text(s, f"Info screen {i + 1}", 1, 1, 6, 1, font="Calibri")
        if i in (0, 1):
            transition(s, advTm="2000")
    kit.show_pr(prs, inner="<p:kiosk/>", useTimings="1", showNarration="1")
    return save(prs, path)


@new_problem("NEW-22-proofing-language", "google",
             "Runs tagged lang='en-ZW' with noProof and dirty='0' everywhere, plus 'xh-ZA' on one slide: PowerPoint "
             "may offer to download proofing tools on open.",
             "Collect a:rPr lang values; languages outside a YAML list of common Office proofing languages → note. "
             "Fix: none (harmless in the show). Lowest priority.")
def _(path):
    prs = _google_deck()
    s = blank(prs)
    t = text(s, "Spelling squiggles off", 0.5, 0.5, 9, 1, lang="en-ZW")
    t.text_frame.paragraphs[0].runs[0]._r.get_or_add_rPr().set("noProof", "1")
    text(s, "Molo, wamkelekile", 0.5, 2, 9, 1, lang="xh-ZA")
    kit.google_names(s)
    return save(prs, path)


# --- extras found while building these (ranked in ADVERSARIAL_RESULTS.md) ---------------------------

@new_problem("NEW-23-transition-sound-linked", "office2010",
             "A transition sound linked to C:\\Windows\\Media\\chimes.wav (p:sndAc/p:stSnd with an external audio "
             "relationship). On the show machine the sound is missing; on some PCs PowerPoint pauses to look for it.",
             "X004 skips audio relationships (left to M003), and M003 only sees media shapes, so nobody reports it. "
             "Fix: let X004 report external audio rels that aren't media shapes (transition and action sounds). "
             "Approximate XML: needs a real-PowerPoint copy.",
             expect=[E("X004", "red")], xfail=None,
             real_ppt="Transitions ▸ Sound ▸ Other Sound…, pick a .wav, untick embed is not offered on Mac: use Windows "
                      "PowerPoint 2010-style 'link to sound' via an action setting (Insert ▸ Action ▸ Play sound).")
def _(path):
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    prs = _office_deck()
    s = blank(prs)
    text(s, "Ding", 1, 1, 6, 1, font="Calibri")
    r_id = s.part.relate_to("file:///C:/Windows/Media/chimes.wav", RT.AUDIO, is_external=True)
    transition(s, inner=f'<p:fade/><p:sndAc><p:stSnd><p:snd r:embed="{r_id}" name="chimes.wav"/></p:stSnd></p:sndAc>')
    return save(prs, path)


@new_problem("NEW-24-hyperlink-to-hidden-slide", "office2010",
             "The only route to a backup slide is a link to a HIDDEN slide; C004 reports it as 'will be skipped' "
             "like any other.",
             "C004: when an hlinksldjump on a visible slide targets the hidden slide, downgrade to a note "
             "('hidden backup slide, reached by a link on slide N'). Small change to C004, not a new check.",
             expect=[E("C004", "note", slide=2)],
             xfail="C004 doesn't look at links; a deliberate linked backup slide is a full yellow")
def _(path):
    prs = _office_deck()
    a, b = blank(prs), blank(prs)
    kit.jump_to_slide(text(a, "Show the backup chart", 1, 1, 6, 1, font="Calibri"), b)
    text(b, "Backup chart", 1, 1, 6, 1, font="Calibri")
    b._element.set("show", "0")
    return save(prs, path)


@new_problem("NEW-25-off-slide-text-in-notes-master-only", "canva",
             "Look-alike for G001: text off the edge of the NOTES page and the slide master (not on any slide).",
             "G001 walks slides only, which is right; this deck guards against a future change walking masters.",
             expect=[], absent=["G001"], xfail=None)
def _(path):
    prs = _canva_deck()
    s = blank(prs)
    text(s, "Inside", 2, 2, 8, 1)
    scrap = text(s, "Master scrap off-slide", -3, 1, 2, 1)
    prs.slide_masters[0].shapes._spTree.append(scrap._element)     # moved from the slide to the master
    notes = s.notes_slide.shapes._spTree
    off = text(s, "Notes scrap off the page", -4, 1, 2, 1)
    notes.append(off._element)
    return save(prs, path)


# =====================================================================================================
# Kitchen sinks: 10+ problems at once, to test how checks interact
# =====================================================================================================

@deck("KS-canva-mess", "canva",
      "Canva kitchen sink: Calibri (MS) Bold title with its embed, Roboto Bold run, Canva Sans, off-slide body, a "
      "picture bleed, emoji, a When-Clicked video, a YouTube thumbnail, a hidden slide, leftover 'Lorem ipsum', a "
      "200 px logo full screen, Calibri embedded, review comment.",
      kind="sink",
      expect=[E("F001", "red"), E("F002", "red"), E("F004", "red"), E("F005", "red"), E("F006", "yellow"),
              E("G001", "red"), E("F011", "yellow"), E("M001", "red"), E("M005", "red"), E("C004", "yellow"),
              E("C001", "red"), E("M009", "yellow"), E("C007", "yellow"), E("X001", "info", subject="canva")],
      fixed=["F001", "F002", "G001", "M001"])
def _(path):
    prs = _canva_deck()
    s1 = blank(prs)
    text(s1, "Annual Conference 2026", 1, 0.6, 14, 1.6, font="Calibri (MS) Bold", size=66)
    text(s1, "Lorem ipsum dolor sit amet", -0.6, 3, 10, 1.5, font="Calibri (MS)", size=36)
    text(s1, "Thanks 🙌🏾", 1, 6, 6, 1, font="Roboto Bold", size=36)
    text(s1, "Canva-only flourish", 1, 8, 8, 1, font="Canva Sans", size=30)
    picture(s1, kit.png(30, 30), x=16, y=-1, w=6, h=6)
    s2 = blank(prs)
    v = kit.video(s2, x=1, y=1, w=8, h=4.5)
    _timing_for(s2, v, "win_when_clicked")
    p = picture(s2, kit.png(32, 18), x=10, y=1, w=8, h=4.5)
    p.click_action.hyperlink.address = "https://www.youtube.com/watch?v=sampleVideo2"
    s3 = blank(prs)
    picture(s3, kit.png(200, 112), x=0, y=0, w=20, h=11.25)
    s3._element.set("show", "0")
    kit.legacy_comment(prs, s1)
    _embeds(prs, embed("Calibri (MS)", "regular", "Calibri (MS)"),
            embed("Calibri (MS) Bold", "regular", "Calibri (MS)", "Bold"),
            embed("Roboto Bold", "regular", "Roboto", "Bold"), embed("Calibri", "regular", "Calibri"))
    return save(prs, path)


@deck("KS-google-mess", "google",
      "Google kitchen sink: Proxima Nova theme, Google shape names, YouTube link in notes, Drive link, a text box "
      "off the left with a group child off too, rotated label, emoji, mailto link, 'Click to add text', an empty "
      "slide, Source Sans Pro.",
      kind="sink",
      expect=[E("F007", "red"), E("M006", "yellow"), E("G001", "red"), E("G003", "note"), E("P004", "yellow"),
              E("C001", "red"), E("C002", "yellow"), E("F011", "yellow"), E("X001", "info", subject="google")])
def _(path):
    prs = _google_deck()
    kit.set_theme(prs, major="Proxima Nova", minor="Proxima Nova")
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Program overview 🚜"
    s1.placeholders[1].text = "Click to add text"
    s1.notes_slide.notes_text_frame.text = "Video: https://www.youtube.com/watch?v=sampleVideo3"
    text(s1, "Pinned left label", -0.4, 4.6, 4, 0.6, font="Source Sans Pro")
    s2 = blank(prs)
    grp = s2.shapes.add_group_shape()
    text(grp.shapes, "Grouped and off", 0, 0, 3, 0.6)
    grp.left = Inches(-0.8)
    text(s2, "Side", 8.5, 1, 1.5, 0.5).rotation = 90
    tb = text(s2, "Email us", 1, 3, 3, 0.6)
    kit.hyperlink_run(tb, "mailto:events@sample.org")
    text(s2, "Footage: https://drive.google.com/file/d/1SAMPLE2/view", 1, 4, 8, 0.6, size=14)
    blank(prs)
    for i, s in enumerate(prs.slides, 1):
        kit.google_names(s, i)
    return save(prs, path)


@deck("KS-office2010-mess", "office2010",
      "Old-Office kitchen sink: 4:3, AppVersion 14, timings on some slides, kiosk off but loop on, advClick off, "
      "embedded Excel, linked picture on C:\\, linked video missing, .wmv video, hidden slide, a web link, "
      "a legacy comment, a 'TBD'.",
      kind="sink",
      expect=[E("G006", "yellow"), E("P001", "yellow"), E("P003", "yellow", subject="loop"), E("P002", "yellow"),
              E("X003", "yellow"), E("X004", "red"), E("M003", "red"), E("C004", "yellow"), E("P004", "yellow"),
              E("C007", "yellow"), E("C001", "yellow")])
def _(path):
    prs = _office_deck()
    s1 = blank(prs)
    tb = text(s1, "Budget review (dates TBD)", 1, 1, 8, 1, font="Calibri", size=36)
    kit.hyperlink_run(tb, "https://sample.org/budget")
    transition(s1, advTm="30000")
    s2 = blank(prs)
    kit.ole_object(prs, s2, "Excel.Sheet.12", "Budget sheet")
    kit.link_picture(s2, "file:///C:/Users/sample/Pictures/chart.png", x=5)
    transition(s2, advClick="0")
    s3 = blank(prs)
    v = kit.video(s3)
    kit.unembed_and_link(s3, v, "file:///C:/Users/sample/Videos/ad.mp4")
    s4 = blank(prs)
    w = kit.video(s4, data=(kit.STUBS / "stub.wmv").read_bytes(), mime="video/x-ms-wmv")
    kit.rename_media(w, "wmv", "video/x-ms-wmv")
    s4._element.set("show", "0")
    kit.legacy_comment(prs, s1)
    kit.show_pr(prs, loop="1", showNarration="1")
    return save(prs, path)


def by_name() -> dict[str, Spec]:
    return {s.name: s for s in SPECS}
