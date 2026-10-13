# Adversarial decks: scope for a cloud agent

**Goal:** build a set of deliberately broken `.pptx` decks that attack every check and fix SlideTistic has, plus the
problems it doesn't catch yet. Write down what SlideTistic should report for each one. Then run SlideTistic on them
and list where it's wrong, crashes, or misses something.

The decks must look like real Canva, Google Slides, old-Office and badly designed decks, because that's what show
machines receive.

Repo: `Horton619/slidetistic`. Read `CLAUDE.md`, then `SPEC.md`, then `docs/EDGE_CASES.md` (every real case seen so
far) before building anything.

---

## 0. Setup (do this first, in the cloud session)

```
sudo apt-get update && sudo apt-get install -y poppler-utils   # pdftotext / pdftoppm (skip sudo if not available)
python3.11 -m venv venv || python3 -m venv venv               # 3.11 matches CI; 3.12 works too
venv/bin/pip install -r requirements.txt
venv/bin/python -m pytest -q                                  # should pass before you change anything
```

Always use `venv/bin/python`. Engine commands are listed under "Commands" in CLAUDE.md.

## 1. What the cloud machine can and can't do

- **It can't run PowerPoint.** The cloud is Linux. Every **L check** (layout fit: L001, L008–L011) and the
  drawn-word versions of G001/G002 need real PowerPoint renders.
- **It can:**
  - build decks with python-pptx and raw XML;
  - run `slidetistic scan` and `repair` with `--no-layout --no-visual`;
  - run the unit tests.
- For layout cases, build the deck and write the expected result. David runs those on his Mac later with
  `scripts/suite_run.py --layout`.
- **No client content.** Every deck uses made-up text and generated images. The repo is public.

## 2. Ground rules for the agent

1. **Never guess PowerPoint XML for timing, animation or media play modes.** CLAUDE.md says: build those in real
   PowerPoint. In the cloud, either:
   - copy the XML from an existing fixture (`tests/fixtures/media_modes/` and the builders), or
   - mark the deck **"needs a real-PowerPoint copy"** and describe exactly how to make it.
2. **One problem per deck where possible.** Name it `<ID or NEW>-<short-slug>.pptx`. Add a few "kitchen sink" decks
   that combine 10+ problems, to test how checks interact.
3. **For every deck, include its look-alike that must NOT be flagged.** Example: a picture off the slide (fine) next
   to text off the slide (red). False alarms matter as much as misses.
4. **Make source fingerprints match what X001 detects**, so presets apply:
   - **Canva:** fonts embedded once per weight ("Arial Nova Bold" as its own family), Canva layout names, picture-heavy
     slides, `(MS)` font aliases.
   - **Google Slides:** shapes named "Google Shape;123;p4", fonts like "Proxima Nova", a theme named "Simple Light",
     YouTube links.
   - **Old Office (2007–2013):** `.pptx` saved by Office 12/14 (`app.xml` AppVersion 12.0000 or 14.0000), 4:3
     slides, Calibri/Cambria body text, the old Office theme, `p14` extension elements missing.
   - **Keynote export:** Avenir/Helvetica Neue, Keynote's layout names.
5. **Stay under 25 MB per deck.** Use stand-in media (`engine/assets/media_stubs`) unless the size itself is the test.
6. **Deliverables** go in a branch, `adversarial-decks`, as a pull request. Don't push to `main`.
   - `tests/fixtures/adversarial/` holds the decks plus a builder script that can regenerate them.
   - `tests/fixtures/adversarial/MANIFEST.md`: one row per deck with what's broken, the source it imitates, the
     expected finding (check ID and status: red, yellow or green_fixed), and whether it needs `--layout`.
   - `docs/ADVERSARIAL_RESULTS.md`: what SlideTistic actually reported, deck by deck. List misses, false alarms,
     crashes and wrong fixes first.
   - A pytest file, `tests/test_adversarial.py`, that runs the data-only decks (no PowerPoint) and checks each
     expected finding. Mark tests for known misses `xfail` with a reason: they become the to-do list.

## 3. Existing checks to attack (every one needs at least one deck)

Fix = the check repairs it by default.

| ID | Check | Attack ideas |
| --- | --- | --- |
| F001 (fix) | Weight in font name | "Montserrat SemiBold" as a family; a real family ending in a weight word ("Arial Rounded MT Bold": must NOT rename); weight names in other languages ("Fett"); an embedded face filed under the suffixed name (rename must not lose the match) |
| F002 (fix) | App-private font name | Canva aliases "Calibri (MS)", "Open Sans (Bold)"; an alias in a master, a layout, a table cell, a chart or SmartArt |
| F003 | Weight PowerPoint can't switch | Thin/Black weights with bold toggled on and off; `b="1"` on a font that has no bold |
| F004 | Canva-only font | Canva Sans, and a Canva-only font used only in the notes (shown? not shown?) |
| F005 (fix) | Embedded fonts under wrong names | The regular slot holding a Bold face; duplicate embeds; an embed whose name matches nothing in the deck |
| F006 (fix) | Office font embedded | Calibri/Arial embedded (bloat); Aptos embedded |
| F007 | Font missing on show machines | Fonts in the East Asian/complex-script slots (`ea`, `cs`), in `sym`, in master text only, in an unused layout (must be a note, not red), in theme major/minor fonts |
| F008 | Embed licence forbids it | fsType 2 (restricted), fsType 4 vs 8 |
| F009 | Free download available | A Google font named differently in the deck ("Source Sans Pro" vs "Source Sans 3"); a font with only some weights free |
| F011 | Emoji in text | Emoji with skin-tone modifiers, ZWJ sequences, flags, a variation selector on its own |
| G001 (fix) | Text off the slide | Negative x; group with a transform pushing a child off; rotated box whose corner leaves; text off but the box inside (overflow); a PICTURE off the slide (must NOT be touched) |
| G002 | Text below the slide | Autofit off and overflowing the bottom; `spAutoFit` box that grows down |
| G003 | Rotated/flipped text | 90°/270° vertical text, `flipH` on a text box, `vert="eaVert"` |
| G004 | Text inside groups | Deep nesting (5 levels), a group with chOff/chExt not equal to off/ext (scaled children) |
| G006 | Slide shape vs screen | 4:3, 16:10, A4, custom 1920×1200 px, portrait |
| L001 (fix, needs PowerPoint) | Header gained a line | A title with 0.3% too little width (PAT case); a title in a font that renders wider on Windows |
| L008 (fix, needs PowerPoint) | Outside the safe zone | Text 0.05 in into the border (must be skipped: tuning gate T001); a footer in the bottom band (not flagged); text on a filled shape (moves with it) |
| L009 (fix, needs PowerPoint) | Single word on last line | Bullets ending in one word; a title box PowerPoint is shrinking (`normAutofit fontScale="90000"`, now fixed by default) |
| L010 (fix, needs PowerPoint) | Text over text | Two boxes whose words interleave on one line (must NOT be red); stacked map labels; animated builds (a note, not a fix); invisible text the same colour as the background |
| L011 (needs PowerPoint) | Text partly over a picture | A caption half over a photo; text over a fully transparent picture |
| P001 | Timer advance | `advTm` on one slide; on every slide; an advance after 0 s |
| P002 | Click won't advance | `advClick="0"`; a kiosk show type |
| P003 | Odd show settings | Loop until Esc, a custom show, "browsed at a kiosk", narrations off |
| P004 | Link leaves the show | Hyperlinks to other files, to programs, to a `file://` UNC path, to an email, `ppaction://hlinkshowjump` |
| M001 (fix) | Video won't start from the clicker | "When clicked on" video; click sequence; a video in a group; two videos on one slide (copy the XML from fixtures) |
| M002 | Media inventory | Audio across slides; a video with a trim; a muted video |
| M003 | Linked media | A linked file that's missing; one next to the deck; an absolute `C:\Users\…` path |
| M004 | Format may not play | `.wmv`, `.avi`, `.mov` with ProRes, `.mkv` |
| M005 | Online video | YouTube and Vimeo embeds (Google Slides style) |
| M006 | Links to download | A YouTube link in the notes; a Drive link; a channel link that ISN'T a video (must not say "download") |
| M008/M009/M013 | Image size | A 95 MP photo shown thumbnail-size; a 200 px logo stretched full screen; a heavily cropped photo |
| M011 | Risky image format | EMF/WMF, TIFF, HEIC, a PNG whose declared type is JPEG |
| M012 | Video over 1080p | A 4K stand-in (metadata only) |
| C001 | Leftover template text | "Click to add title", "Lorem ipsum", "Presenter Name" |
| C002 | Empty slide | A placeholder-only slide; a slide whose only text is white on white |
| C004 | Hidden slide | Hidden slides, one at the end; one that a link jumps to |
| C007 | Review comments | Modern comments (`ppt/comments/modernComment_*.xml`) and legacy `comment1.xml`; resolved and unresolved |
| X001 | Where it came from | Mixed fingerprints (a Google deck later edited in Canva) |
| X002 | File name/size | Names with emoji, trailing spaces, `#`, a 260+ character path, a 2 GB deck |
| X003 | Needs another app | Embedded Excel/Word OLE objects, an embedded PDF, a Visio drawing |
| X004 | Linked to someone's computer | Linked pictures and OLE on `C:\Users\…`, `\\server\share`, `/Users/…` |

## 4. Break the engine itself (robustness)

Each of these must give a plain error or a tool_error. None may crash, hang or modify the input.

- Zip problems: a truncated file; a password-protected (encrypted) deck; a `.ppt` renamed `.pptx`; a `.pptm` with
  macros; a `.ppsx`/`.potx`.
- A zip bomb (an XML part over 256 MB declared). It must be refused fast.
- Broken XML: a slide that references a missing layout; a relationship to a missing part; duplicate shape IDs; a
  `p:sldId` pointing nowhere.
- Unicode extremes: right-to-left text (Arabic, Hebrew), vertical CJK, combining characters, a 10,000-character
  paragraph.
- A 500-slide deck; a deck with 0 slides; a slide with 2,000 shapes.
- SmartArt, charts with text, tables with merged cells, equations (OMML), ink annotations.
- External links planted to test render-copy safety: a UNC image link, an `http://` OLE link, ActiveX controls. The
  render copy must neutralise all of them; see `deck.render_safe`.

## 5. New problems SlideTistic doesn't check yet, most likely first

Probability is how often this hits a live show. For each one, build the deck, say how a check would detect it, and
say whether a fix is safe. **Detect first, fix later** (CLAUDE.md: David reviews before a fix is added).

| # | Likelihood | Problem | Source it imitates |
| --- | --- | --- | --- |
| 1 | Very high | Text the same colour as its background (invisible leftovers, seen on TSCRA) | Any, often Canva |
| 2 | Very high | Text on a busy photo with poor contrast (WCAG ratio under 3:1) | Canva, bad design |
| 3 | High | Font size under 18 pt in body text: unreadable in a ballroom | Bad design |
| 4 | High | Animations that hide content until clicks the presenter won't do; exit animations on the last build | Old Office, bad design |
| 5 | High | Slide transitions with long durations, or "Morph" on a machine without Office 365 | PowerPoint 365 |
| 6 | High | Fonts substituted by Google Slides' export (theme fonts renamed, `+mj-lt` resolving to a font that isn't installed) | Google Slides |
| 7 | High | Pictures with "Compress pictures" never applied, plus cropped areas kept (deck size) | Canva, old Office |
| 8 | Medium | Speaker notes holding the actual content (an empty slide with full notes) | Bad design |
| 9 | Medium | Slide numbers and footers disagreeing between slides (some fields static text) | Old Office templates |
| 10 | Medium | Mixed slide sizes merged from two decks (pasted slides scaled wrong) | Merged decks |
| 11 | Medium | Linked audio playing across slides that stops early (`numSld` too small) | Old Office |
| 12 | Medium | Hyperlinked "Next" buttons that skip slides | Old Office, kiosks |
| 13 | Medium | Shapes wholly covered by other shapes (dead content) | Canva, merged decks |
| 14 | Medium | Grouped pictures with transparency that print or render black on older PowerPoint | Canva |
| 15 | Medium | WordArt/text effects (3D, glow) that render differently on Mac and Windows | Old Office |
| 16 | Medium | Embedded fonts in a format older PowerPoint can't use (OTF-CFF embedded) | Canva |
| 17 | Low | Right-to-left text whose direction is lost on export | Google Slides |
| 18 | Low | Charts linked to an external Excel file (update prompt on open) | Old Office |
| 19 | Low | Duplicate slides back-to-back (the same content twice) | Merged decks |
| 20 | Low | A theme colour scheme that maps text to near-white on the projector | Bad design |
| 21 | Low | "Kiosk mode" or "Use timings" set at deck level | Old Office |
| 22 | Low | Spell-check squiggles disabled per run and `lang` set to a language not installed (proofing prompt) | Google Slides |

Add any others the agent finds, ranked the same way, with the reasoning.

## 6. Report back

`docs/ADVERSARIAL_RESULTS.md`, in this order:

1. **Crashes and hangs.** The deck, the command, the traceback.
2. **Wrong fixes.** The fix made something worse, or changed text, shapes or media (an invariant broke: X000).
3. **Misses.** An existing check should have fired and didn't.
4. **False alarms.** A finding on a deck that's fine.
5. **Section 5 results.** For each new problem: how common, how to detect it, whether a fix is safe, and the
   fixture name.
6. **Layout decks that need the Mac.** The list, with the exact `suite_run.py --layout` command.

Keep the wording plain. David reads this on a phone.
