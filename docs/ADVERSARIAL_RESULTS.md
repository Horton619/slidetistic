# Adversarial decks: results (2026-10-13)

What SlideTistic did with the decks built for `docs/ADVERSARIAL_DECKS.md`. All decks are made up; nothing
here comes from a client deck.

- **Decks:** 132 in `tests/fixtures/adversarial/` (128 committed, 4 built by the test because they're big).
  `MANIFEST.md` there lists each one with what it should trigger.
- **How it was run:** Linux cloud machine, no PowerPoint. Every deck went through
  `engine.cli scan --json --no-layout`, then `engine.cli repair --json --no-layout --no-visual --no-report`
  (`venv/bin/python -m tests.fixtures.adversarial.run_all --out <folder>`). Poppler 24.02 and ffprobe were
  installed, so the media checks ran with real probing.
- **Tests:** `tests/test_adversarial.py`: 239 pass, 41 xfail (the to-do list below), 4 skipped (no font
  catalog here; the `.ppsx` deck can't load in-process). `pytest -m slow` (500 slides, a 2 GB file): 5 pass.
- **Not tested here:** anything that needs PowerPoint. That's every L check, and G001/G002 judged by drawn
  words. See section 6.
- **Free-font check (F009):** the cloud network refused the catalog download (403), so F009 only said "font
  list not downloaded". `F009-renamed-google-font` goes on the Mac list too.

---

## 1. Crashes and hangs

Nothing crashed or hung. No traceback on any of the 132 decks. The zip bomb was refused in 0.3 s. The
500-slide deck took 11 s to scan and 22 s to repair; the 2,000-shape slide took 2 s and 4 s.

The closest thing to a crash:

- **`R-sldid-nowhere`**: the slide list in `presentation.xml` names a slide that doesn't exist.
  - Command: `engine.cli scan R-sldid-nowhere.pptx --json --no-layout`
  - Result: exit code 0, and **32 tool errors**, one per check, all saying
    `couldn't run: "no relationship with key 'rId999'"`.
  - Should be one plain message: "the deck's slide list is damaged", ideally with the slides that do
    load still checked. The crew sees 32 red "couldn't run" rows for one problem.
- **A `.ppsx` renamed to `.pptx`** (people do this to edit a show): the message is
  `Couldn't open X.pptx: file '/full/temp/path/X.pptx' is not a PowerPoint file, content type is
  'application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml'`. Plain enough to stop,
  but not crew-readable.

## 2. Wrong fixes

No repair broke an invariant (no X000) and no fix introduced a new problem, on any deck. A second repair
changed nothing on every deck. Pictures were never moved. Only layout fixes are untested (section 6).

One wrong result:

- **`R-duplicate-shape-ids`**: two off-slide text boxes share shape id 5 (merged slides do this).
  - G001 fixed the first box only. The second one is still 0.8 in off the left edge.
  - The report then marks **both** as red, "fix ran but the problem is still there". The box that was moved
    is shown as broken, and the one that's broken looks like a failed fix.
  - Why: `Deck.find_shape` returns the first shape with that id, and both findings share one key
    (check, slide, shape id, subject), so the re-scan can't tell them apart.
  - Any fix that finds its shape by id has the same problem (G001, M001, the L fixes).
  - Repeated repairs never fix the second box: `find_shape` keeps returning the first, which is already
    inside.

## 3. Misses (an existing check should have fired)

Most important first.

1. **M011 never flags HEIC or WebP pictures** (`M011-heic-webp`). python-pptx has no part class for
   `image/heic`, `image/heif` or `image/webp`, so those load as a plain part. `images.pictures` then hits
   `AttributeError` on `.image` and silently skips the picture. The HEIC/WebP rules in M011 can never fire on
   a real deck. M008 and M009 skip those pictures too (they use the same helper). iPhone photos make this
   likely.
2. **Emoji outside U+1F000–1FAFF** (`F011-default-emoji-no-selector`): ✅ ⌚ ⭐ ☕ aren't caught. They show
   as emoji by default on Mac and Windows. F011's pattern only covers the 1Fxxx blocks or a symbol followed
   by U+FE0F.
3. **Vertical text set by the text box, not rotation** (`G003-ea-vertical`): `bodyPr vert="eaVert"` or
   `"vert270"`. G003 only reads `rot` and flips.
4. **Unbracketed fill-ins** (`C001-leftovers` slide 3): "Presenter Name / Title, Organization" isn't caught.
   "[Speaker Name]" with brackets is. A YAML edit: add "presenter name", "company name", "your logo" to
   `template_text.yaml`.
5. **An "empty" slide whose only text is white on white** (`C002-empty-cases` slide 2): C002 counts any text
   as content. Same root as NEW-01 below.
6. **A linked transition sound on C:\\** (`NEW-23-transition-sound-linked`): X004 skips audio links ("M003's
   job") and M003 only looks at video/audio shapes, so nobody reports it.
7. **File names with `#`** (`X002-hash-name`) and **full paths over 260 characters** (`X002-long-path`):
   X002 checks the file name's characters and length, not `#`, `%` or the whole path. On Windows the long
   path is the real failure. Whether `#` trips show software is a question for David.
8. **Weight words in other languages** (`F001-german-fett`): "Roboto Fett" isn't recognised as Roboto bold.
   F007 does call it a missing font (red), so the crew isn't blind to it, but the fix isn't offered.
9. **Other Canva-style private names** (`F002-open-sans-paren-bold`): "Open Sans (Bold)" isn't in
   `font_aliases.yaml`. F007 calls it missing (red). Adding a line to the YAML is the fix once a real deck
   shows the pattern.
10. **A password-protected deck** (`R-encrypted`): refused, but the message says "damaged, an old .ppt
    renamed, or still downloading". An encrypted .pptx is an OLE file containing an `EncryptedPackage`
    stream, so it can be recognised and the message can say "password-protected: ask for an unprotected
    copy". The deck is a stand-in: make a real one to confirm (MANIFEST).
11. **Text overflowing a box that's inside the slide** (`G001-text-overflows-unwrapped`,
    `G002-autofit-off-overflow`): without PowerPoint, G001/G002 only look at boxes. That's expected; with
    PowerPoint they judge drawn words. Both decks are on the Mac list.
12. **PNG bytes declared as JPEG** (`M011-png-declared-jpeg`): not noticed. Judgment: needs a real
    PowerPoint test before it's worth a finding.

## 4. False alarms (findings on a deck that's fine)

1. **"Arial Rounded MT Bold"** (`F001-arial-rounded-mt-bold`): F001 says "may be a real font name" (yellow),
   though `office_bundled_fonts.yaml` lists that exact name as a font Office ships. F007 already treats it
   as covered. F001 should check the bundled list too.
2. **Canva Sans used only in the speaker notes** (`F004-canva-sans-notes-only`): F004 is red and says "in
   masters/layouts only". The audience never sees notes; at most a note. The wording is wrong too (it's
   notes, not masters).
3. **A stray U+FE0F after a letter or digit** (`F011-lone-variation-selector`): "Room 1️" from a
   copy-paste is reported as emoji. A keycap emoji needs U+20E3 too; a selector after a letter does nothing.
4. **Only resolved comments** (`C007-resolved-only`): still a yellow "check this is the final version".
   Judgment: ask David whether resolved-only should be a note.
5. **Two findings for one font** (`F003-montserrat-semibold`, `F003-thin-black-bold-toggled`): with
   Montserrat embedded, "Montserrat SemiBold" gets F003 yellow AND F007 red. The 2026-10-07 decision was
   "F003 only when the base family is available; F007 owns missing", so F007 should probably stay quiet
   here, or F003 should. Not marked xfail: ask David which one he wants.
6. **`.pptm` and `.ppsx` refused** (`R-macro-pptm`, `R-show-ppsx`): "Only .pptx files can be checked".
   That's a plain refusal, but show machines do get `.ppsx` (and sometimes `.pptm`) files, and the engine
   could read both: same zip, different main content type. Judgment: ask David.

Checked and fine (look-alikes that stayed quiet): pictures off the slide, a scaled group whose child's own x
is negative, centered text in an overhanging box (yellow, never red, never moved), fsType 4 and 8 embeds,
Aptos embedded (kept), typographic symbols, a YouTube channel link (not "download"), an "In Click Sequence"
video, empty placeholder prompts, TIFF pictures, 16:9 Google size, off-slide text on the master and notes
page, a "next slide" action link.

Not a false alarm, but worth knowing: `X002-2gb-deck` comes back **green_fixed** after repair, because the
mended copy is small. The 2 GB there is padding in front of the zip, which a rewrite drops. A real 2 GB deck
(media) would stay 2 GB and stay yellow.

## 5. New problems (section 5 of the scope)

Each has a deck named `NEW-xx-…` and an xfail test: "no check for this yet". Likelihood is from the scope;
the extras at the end are ranked the same way. **Detect first; no fix is proposed as automatic.**

| # | Likelihood | Problem | How a check would detect it | Fix safe? | Deck |
| --- | --- | --- | --- | --- | --- |
| 1 | Very high | Text the same colour as its background | Resolve each run's colour (run → paragraph → placeholder → master; scheme colours via theme + clrMap) and what's behind the box (slide → layout → master background, or a filled shape under it). Contrast under 1.5:1 → yellow "invisible text". With the render: sample the pixels under the letters | No: may be deliberate. Offer "delete" in the review | `NEW-01-text-same-colour-as-background` |
| 2 | Very high | Text on a busy photo, contrast under 3:1 | Needs the render: pdftoppm image + pdftotext letter boxes; compare text colour with the 10th-percentile background luminance under each line. Data-only stand-in: L011's geometry + light text | No; suggest a dark band | `NEW-02-text-on-busy-photo` (layout) |
| 3 | High | Body text under 18 pt | Resolve each visible run's size (run → paragraph → placeholder → master; apply normAutofit fontScale). Body text, more than a few words, under a YAML threshold → yellow. Skip footers, the bottom band, tables | No: reflows everything | `NEW-03-small-body-text` |
| 4 | High | Builds that hide content; exit on the last click | `playback.animated_shape_ids` already finds entrance/exit effects. Note "N clicks before this slide moves on"; exit effect in the last click group → yellow | No | `NEW-04-builds-and-exit-on-last-click` (exit XML approximate: needs a real-PowerPoint copy) |
| 5 | High | Long transitions; Morph on old Office | Read `p:transition` `spd` / `p14:dur` and the `p159:morph` choice in `mc:AlternateContent`. Over 2 s → yellow; Morph → yellow "needs PowerPoint 2019/365" | Shortening is safe but needs David's OK | `NEW-05-long-transitions-morph` (needs a real-PowerPoint copy) |
| 6 | High | Google theme fonts replaced by Arial stand-ins | **Mostly covered:** F005 yellow "exporter put Arial in its place" fires for both theme fonts. Gap: say it once at deck level ("every heading will show as Arial") | Detect only | `NEW-06-google-theme-font-substitution` (passes) |
| 7 | High | Pictures never compressed, crops kept | **Covered by M013** (fix off by default). The deck shows the default pitch (≥25 % and ≥5 MB) stays quiet on a small deck, which is right | M013's fix | `NEW-07-uncompressed-pictures` (passes) |
| 8 | Medium | The content is in the speaker notes | Visible words ≤ 3 and notes words ≥ 50 → yellow. C002 already says "nothing on it" for this slide, without saying where the content went | Detect only | `NEW-08-content-in-notes` |
| 9 | Medium | Slide numbers/footers disagree | A `sldNum` placeholder with no `a:fld type="slidenum"` → yellow "typed by hand"; footers that differ from the majority → note | Detect only | `NEW-09-footers-disagree` |
| 10 | Medium | Slides pasted from a 4:3 deck | Per slide: all shapes inside ≤ 75 % of the width from x≈0, in 4:3 proportions → yellow | Detect only | `NEW-10-merged-slide-sizes` |
| 11 | Medium | Background audio stops early (`numSld`) | Read the audio's "stop after N slides" and compare with the slides that follow | Detect only | `NEW-11-audio-across-slides` (needs a real-PowerPoint copy) |
| 12 | Medium | "Next" buttons that skip slides | Follow `hlinksldjump` targets: a button saying Next/Continue/→ that doesn't land on n+1 → yellow | Detect only | `NEW-12-next-button-skips` |
| 13 | Medium | Shapes wholly covered by other shapes | z-order walk: text inside a later opaque, unrotated picture or filled shape → yellow "hidden behind …". With the render: its words aren't drawn | Detect only | `NEW-13-covered-shapes` |
| 14 | Medium | Grouped transparent PNGs render black on old PowerPoint | Pictures with an alpha channel inside groups → note, Canva source only. Confirm on Office 2016 first | Detect only | `NEW-14-grouped-transparent-pictures` (layout) |
| 15 | Medium | WordArt 3D, glow, reflection | `a:glow`, `a:reflection`, `a:sp3d`, `a:scene3d`, `prstTxWarp` on text → note; judged in the visual review | Detect only | `NEW-15-wordart-effects` |
| 16 | Medium | OpenType-CFF embedded font | `fonts.read_embed` already parses the file: sfnt tag `OTTO` → yellow "Windows PowerPoint ignores CFF embeds; install it" | Detect only | `NEW-16-otf-cff-embed` |
| 17 | Low | Right-to-left text lost its direction | Paragraphs that are mostly bidi class R/AL with no `rtl="1"` → yellow | Plausible (set `rtl`, `algn="r"`), but needs a real before/after | `NEW-17-rtl-direction-lost` |
| 18 | Low | Chart linked to an external Excel file | **Already caught by X004** (red: the chart part's link to C:\\). Better wording: "PowerPoint will ask to update links; break the link" | Detect only | `NEW-18-chart-linked-to-excel` (passes) |
| 19 | Low | The same slide twice in a row | Hash each slide's visible text + picture digests; equal neighbours → yellow | Detect only | `NEW-19-duplicate-slides` |
| 20 | Low | Theme maps text to near-white | Resolve dk1/tx1 through clrMap vs lt1/bg1 or the background; under 3:1 → deck-level yellow | Detect only | `NEW-20-near-white-theme-text` |
| 21 | Low | Kiosk mode with timings that don't cover every slide | **Parts caught:** P003 red (kiosk) and P001 yellow (timings). Gap: kiosk + an untimed slide = the show stops with no way on. Raise red | Detect only | `NEW-21-deck-level-kiosk-timings` (passes) |
| 22 | Low | Proofing language not installed | Collect `lang` values; outside a YAML list of common Office proofing languages → note | None needed | `NEW-22-proofing-language` |

Extras found while building these:

| # | Likelihood | Problem | Reasoning | Deck |
| --- | --- | --- | --- | --- |
| 23 | Medium | HEIC/WebP pictures invisible to every image check | A bug, not a new check (section 3, item 1). Ranked high because phones produce HEIC and Canva exports WebP | `M011-heic-webp` |
| 24 | Medium | Duplicate shape ids break fixes and the report | Merged decks carry them; section 2 | `R-duplicate-shape-ids` |
| 25 | Medium | `.ppsx` show files refused | Show machines get these; same format as .pptx | `R-show-ppsx` |
| 26 | Low–Medium | Linked transition or action sound on C:\\ | Old Office decks with `chimes.wav`; falls between X004 and M003 | `NEW-23-transition-sound-linked` |
| 27 | Low–Medium | Hidden backup slide reached by a link gets a full yellow | A small change to C004: a note when a visible slide links to it | `NEW-24-hyperlink-to-hidden-slide` |
| 28 | Low | Unused embedded fonts (bloat) | Compare embedded names with the fonts text uses; a note with the MB it costs | `F005-duplicate-and-unused-embeds` |

## 6. Layout decks that need the Mac

These need PowerPoint's render. Each has its expected result in `MANIFEST.md`. Without PowerPoint every L
check stayed silent on them, which the tests check.

| Deck | What to look at |
| --- | --- |
| `L001-title-zero-slack.pptx` | After the font fix the title may wrap: L001 should catch it and fix it. Box width is an estimate: tighten it in PowerPoint first until the original title just fits one line |
| `L001-wider-on-windows.pptx` | Helvetica Neue header: one line on the Mac; compare with the PC (Arial is wider) |
| `L008-safe-zone-cases.pptx` | 0.05 in into the border: left alone (T001). Footer in the bottom band: not flagged. Panel text: moves with its panel or not at all |
| `L009-orphans.pptx` | One-word last line in the bullets: fixed. Title PowerPoint is shrinking (fontScale 90 %): see what happens |
| `L010-overlap-cases.pptx` | Interleaved boxes: not red. Stacked labels: per the letter rule. Two clicked-in boxes in one spot: one note. Invisible white name under real text: red today (TSCRA case) |
| `L011-picture-cases.pptx` | Caption half over a photo: flagged. Text over a fully transparent picture: ideally not |
| `G001-text-overflows-unwrapped.pptx` | Unwrapped line running off the right edge: G001 red by drawn words |
| `G002-autofit-off-overflow.pptx` | 12 lines overflowing a box near the bottom: G002 red by drawn words |
| `NEW-02-text-on-busy-photo.pptx` | Look at contrast in the review image |
| `NEW-14-grouped-transparent-pictures.pptx` | Check the shadows aren't black (Windows PowerPoint 2016 if one is around) |
| `F009-renamed-google-font.pptx` | Not layout: needs the font catalog. F009 should offer Source Sans 3 and Montserrat ExtraBold |

To run them, copy the folder into the shared suite and run only that folder:

```
cp -R tests/fixtures/adversarial/decks "<Dropbox>/SlideTistic Test Suite/adversarial"
venv/bin/python scripts/suite_run.py --suite "<Dropbox>/SlideTistic Test Suite" --layout --images --only 'adversarial/*'
```

(`--only 'adversarial/L0*'` runs just the L decks.) The whole folder is made up, so it's fine in Dropbox.

Decks whose XML is approximate and should be replaced by a real-PowerPoint save before anyone builds a check
on them (steps in `MANIFEST.md`): `F002-alias-in-smartart`, `M002-audio-trim-mute` (play across slides),
`R-encrypted`, `R-rich-objects`, `NEW-04`, `NEW-05`, `NEW-11`, `NEW-23`.

## Round 2 (Mac, 2026-10-13)

David's Mac, PowerPoint for Mac 16.113.4. Layout run: `_runs/20261013-1640-mac-69ae8fc+dirty-layout-adversarial-r2`
in the shared suite (decks in `adversarial-layout/`). Only the 10 layout decks were run with PowerPoint; the other
decks don't use it, so round 1 still stands for them.

### Most important

1. **G001-text-overflows-unwrapped: a wrong "fixed".** L008 sees the line running off the right edge (red) and
   moves the box 1.06 in left. The report says green_fixed. The after image still shows most of the sentence off the
   slide. Why: on the Mac, PowerPoint's PDF leaves out text past the slide edge, so after the move the engine sees
   a line that ends at the edge and thinks it fits.
2. **G002-autofit-off-overflow: half the text lost, reported as a yellow.** Only 6 of 12 lines are drawn; lines
   7–12 are below the slide. L008 says only "reaches into the 5% safe border at the bottom (by 0.32 in)". Same
   cause: the lost lines aren't in the PDF, so nothing counts them.
3. **Some made-up decks made PowerPoint ask "Repair?"** Details: `tests/fixtures/adversarial/POWERPOINT_REJECTS.md`.
   - 22 Google and Keynote decks: an empty `<AppVersion>` in `docProps/app.xml`. Fixed in the generator; those decks
     got the new `app.xml` and nothing else, and five were re-opened in PowerPoint: clean.
   - 7 still need real saves: both C007 comment decks, F002-alias-in-smartart, R-rich-objects (SmartArt, ink),
     M002 and NEW-11 (audio), NEW-23 (transition sound). PowerPoint strips or rewrites those parts.
4. **What the engine does when PowerPoint asks "Repair?"** (a client deck can do this too):
   - Repair: the copy is renamed "… - Repaired", the export script can't find it, and after ~3 min the deck gets
     "Layout fixes skipped: … Can't get full name of missing value". Safe, but not crew-readable.
   - The repaired copy then stays open in PowerPoint. Neither `cli cleanup` nor the next engine closes it (the
     name no longer matches). CLAUDE.md says copies never stay open.
   - Cancel: the engine says "PowerPoint stopped responding", and so does the next engine process, so the next
     deck lost its layout pass too.
   - The prompt shows on screen with no hint that SlideTistic is waiting for it.

### Layout decks, one by one

| Deck | What should happen | What happened on the Mac | Verdict |
| --- | --- | --- | --- |
| G001-text-overflows-unwrapped | Line off the right edge: red | L008 red, then a 1.06 in move reported as fixed; still off the slide | **Wrong fix** |
| G002-autofit-off-overflow | Text below the slide: red | 6 of 12 lines drawn; L008 yellow (safe border) | **Miss** |
| L001-title-zero-slack | After the font fix the title wraps; L001 fixes it | Box tightened first in PowerPoint (12.715 in is the narrowest one-line width; 12.712 wraps). F001 + F002 fixed; the title wrapped; L001 widened the box to 13.10 in; one line in the after image | OK |
| L001-wider-on-windows | One line on the Mac | One line. F007 red: Helvetica Neue is a Mac font, swap Arial | OK (PC still to do) |
| L008-safe-zone-cases | Hair into the border: leave it. Footer: not flagged. Panel text: with its panel or not at all | Nothing flagged, nothing moved. But the "hair into the border" paragraph is drawn inside the border (the box's padding pushes it in), so T001 isn't really tested | OK; deck needs a tweak |
| L009-orphans | One-word last line: fixed. 90 % title: see | No one-word last line in PowerPoint's render ("across the region"), so L009 rightly stays quiet. Title draws on two lines; L008 note: 0.04 in into the top border | Deck doesn't test it |
| L010-overlap-cases | Interleaved: not red. Stacked labels: letter rule. Click builds: one note. White name under text: red | Stacked labels: quiet (letters apart). White name: red, as today. Click builds: a **yellow**, not a note. "Interleaved" boxes actually overlap in the render ("Elementary" over "School Hub"), so red is right | Mostly OK; deck needs a wider gap; note-or-yellow is David's call |
| L011-picture-cases | Half-over caption: flagged. Invisible picture: not | Caption yellow (40 % over). Invisible picture: quiet. Also M009 on the tiny test pictures | OK |
| NEW-02-text-on-busy-photo | No check yet | Caption unreadable on noise; no finding (M009 on the 400 px photo) | As expected |
| NEW-14-grouped-transparent-pictures | No check yet | Soft grey on the Mac, not black | As expected (old Windows PowerPoint still to try) |

Clean run: no crashes, no tool errors, a second repair changed nothing on any of the 10.

### Font list (F009)

The catalog downloaded on the Mac (2,103 free fonts). On this Mac F009 says nothing for `F009-renamed-google-font`,
correctly: Montserrat and Source Sans Pro are installed here. With the installed list blanked (a clean show
machine) it offers "Montserrat … ExtraBold" and "Source Sans Pro … Regular". Fontsource still carries the old name
Source Sans Pro, which matches what the deck asks for, so that's the better offer than Source Sans 3. F007 red for
both, as expected.

### Real PowerPoint saves

Made by PowerPoint itself (AppleScript drives PowerPoint; PowerPoint writes the XML and saves). The author field
PowerPoint stamps was changed to "Sample Presenter".

- **NEW-04** (builds + exit on the last click): replaced. Real "Appear" is preset 1, not Fade (10).
- **NEW-05** (6 s Vortex + Morph): replaced. Both transitions sit inside `mc:AlternateContent` with a plain fade as
  the fallback. A detector reading only the top-level `p:transition` would see fades.
- **R-encrypted**: made, and it confirms round 1 (the message never says "password"). **Not committed:** PowerPoint
  writes the user's name inside the encrypted part, and the password is public.
- **Not done yet:** M002 and NEW-11 (inserting audio needs the file picker, which can't be driven in the background),
  F002-alias-in-smartart and R-rich-objects (SmartArt, ink), NEW-23 (Windows only), and the Windows saves of
  NEW-04/05.

### Changed from round 1

- G001-text-overflows-unwrapped and G002-autofit-off-overflow now expect **L008 red**: judging drawn words is L008's
  job; G001/G002 only look at boxes. Still xfail (needs PowerPoint, plus the two bugs above).
- L001-title-zero-slack: title box 13.81 → 12.715 in (PowerPoint's narrowest one-line width).
- `kit.set_app` leaves out an empty `<AppVersion>`; 22 decks changed in `app.xml` only.

### Questions for David (new)

- L010: two text boxes that build on clicks in the same spot get a full yellow. Should that be a note?
- How should the engine handle a deck PowerPoint wants to repair: say "PowerPoint had to repair this deck; layout
  not checked" and close the copy? Or check the repaired copy, with a warning?

## How to re-run

```
venv/bin/python -m tests.fixtures.adversarial.build          # rebuild the decks + MANIFEST.md
venv/bin/python -m pytest tests/test_adversarial.py          # expectations (xfail = to-do)
venv/bin/python -m pytest tests/test_adversarial.py -m slow  # 500 slides, 2 GB
venv/bin/python -m tests.fixtures.adversarial.run_all --out /tmp/adv   # CLI run, JSON per deck
```

When a to-do is fixed, its test reports XPASS(strict): remove that deck's `xfail=` in
`tests/fixtures/adversarial/decks.py`.

## Fixes (2026-10-14, David: "1 and 2")

Round 2's three bugs and round 1's to-do list. Each deck's `xfail` is gone, so its test now checks the fix.

- **Off-slide text the Mac doesn't draw** (G001-text-overflows-unwrapped, G002-autofit-off-overflow). L008 counts
  the words PowerPoint left out when the drawn text reaches an edge. Both decks are now red ("N words aren't drawn
  at all"), and a move that leaves words undrawn no longer counts as fixed. Checked with real PowerPoint. The replay
  fixture's old recording had the same wrong "fixed" ("edge" was still off): re-recorded.
- **"Repair?" prompt:** a plain message ("damaged parts … let it repair, save a copy"). A copy PowerPoint renamed
  "… - Repaired" is closed when its name holds our unique tag. It isn't marked stuck, so the next deck still gets its
  layout pass. Not yet tried live: that needs someone to answer the prompt on screen.
- **Misses fixed:**
  - F011: ✅⌚⭐☕ and keycaps.
  - G003: text direction.
  - C001: "Presenter Name" without brackets (yellow).
  - C002: white on white.
  - F001: Fett/Gras/Negrita/Grassetto + Kursiv/Italique/Cursiva/Corsivo, and "Open Sans (Bold)" (now F001's, which
    sets bold).
  - X002: full path over 259.
  - R-encrypted: says "password-protected".
  - X004: a linked transition sound.
  - M011/M008/M009: HEIC/WebP.
- **False alarms fixed:**
  - F001 on "Arial Rounded MT Bold".
  - F004 on a notes-only font (now a note).
  - F011 on a stray U+FE0F.
- **Robustness:**
  - Shapes sharing an id are never fixed; both say why.
  - A slide list naming a missing slide gets one plain refusal.
- **Still open (David's call):**
  - C007 on resolved-only comments.
  - '#' in file names.
  - Accepting .pptm/.ppsx.
  - F003 + F007 both on "Montserrat SemiBold".
  - M011 on PNG bytes declared JPEG (needs a PowerPoint test first).
  - The section 5 new checks.
