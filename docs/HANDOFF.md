# Handoff: start here (updated 2026-10-12, Mac session: tuning, review, fonts)

For any new Claude Code session, Mac or PC. Read this, then `CLAUDE.md` (how we work, rules, gotchas), then
`SPEC.md` (what we're building; §11 is the dated decisions log). `docs/POLISH.md` is the parked UI/behaviour
list; `docs/EDGE_CASES.md` logs every real-deck surprise; `docs/CROSS_PLATFORM_COMPARE.md` is the Mac ↔ PC
suite protocol. The Dropbox suite's `_mailbox/` holds notes between the Mac and PC sessions: read the newest.

## 1. Where things stand

- **Released:** v0.4.2 (commit `8108db1`): signed + notarized Mac DMG/ZIP and Windows installer. The PC tested
  the production build on 2026-10-11 and it passed: auto-update, clicker video, stand-ins, smoke test (mailbox
  `20261011-1515-win-0.4.2-sweep.md`). The PC also pushed `9b44291`: tables only move, and renames wait out
  Dropbox locks.
- **Next release: v0.4.3** = everything in §3b (tuning, the review screen, fonts, the new layout heuristics).
- **Repo is public** (`Horton619/slidetistic`): client decks, run results and anything quoting client text
  never go in git. Signing secrets are set (all five). An empty duplicate **v0.4.0 draft** is still on GitHub:
  harmless, and David hasn't okayed deleting it.
- **Machines:** Mac (Apple Silicon, PowerPoint 16.113, Keynote Creator Studio 15.4, Creative Cloud) and David's
  Windows PC (Ryzen 7 2700X, PowerPoint 16). Each runs its own Claude Code session; they talk through git and the
  Dropbox suite `_mailbox/`.

## 2. What David wants next (2026-10-12)

1. **A round 3 of votes** on the v0.4.3 heuristics. Repair the suite in the app with Tuning mode on, then run
   `tune`. Rounds so far: round 1 had 14 % approval (388 votes), round 2 had 48 % (103 votes).
2. **Real text-collision examples:** none exist in the suite. All 17 earlier L010 reds were stacked labels or
   interleaved text boxes, and the one left is invisible text. When David finds a real one (font rendering or
   reflow), it becomes a fixture.
3. **Open decisions:** font shrinking in L010/L008 (he wanted to see examples first, and those turned out to be the
   box-vs-letter bug); embed-for-show guidance for Creative Cloud fonts.

## 3. What the 2026-10-11 session did (all on `main`)

**Optimization round** (commit `b285ae5`; rules in CLAUDE.md "Optimization round"). Measured:
| What | Before | After |
|---|---|---|
| PAT 23 layout repair CPU (simulated layout) | 125 s | 16 s |
| TSCRA CWD repair (media/07) | 55 min PC / 10 min Mac | 91–95 s Mac |
| Whole suite in the real app (31 decks, Mac) | n/a | scan 3.5 min + repair 17 min; median deck 26 s, slowest 95 s |
| Mac CLI suite with PowerPoint (incl. 2nd repair, `--images`) | 1 h 07 min | 30 min |
Proof method: `/private/tmp/…/scratchpad/opt_proof/` is gone with the session; the method was a fake-layout
repair (`tests/test_fit_settles.py` has the stand-in PowerPoint) on 4 decks, comparing change lists, findings and
a SHA-1 of every saved zip part before/after each change. Every pure-speed change was byte-identical.

- **Fit settles:** `Reflow` predicts a width *range* (`fit_wrap_band_pct: 1`); a box gets
  `fit_max_attempts_per_box: 2` then goes back as it was; `tests/test_fit_settles.py` = 6 cases the old engine
  crept 3–5× on (all fail on old code, pass now). Outcome is "fixed, or untouched", never half-nudged.
- **Builds and crowds (L010):** text with an entrance/exit animation (or inside an animated group;
  `playback.animated_shape_ids`) is never "text over text": one yellow "animated build" note per slide.
  >`overlap_max_per_slide: 12` collisions → one red for the slide, no fix attempts. `fit_time_budget_s: 120`.
  TSCRA slide 41 (22 stacked year cards, each appearing on a click) was 231 reds and the 55-minute repair.
- **Speed:** shape-list cache (`--shape-cache on|off|check`, app Diagnostics switch, default on); rounds 2+ only
  re-check changed slides; safety pass reuses the settled round; one PowerPoint export per content per job
  (`render.content_key`); review JPEGs 4 at a time.
- **Render copies:** PowerPoint gets decks with tiny media stand-ins (`engine/assets/media_stubs`); verified
  pixel-identical on Mac PowerPoint (19 pages, worst diff 0). Not yet verified on Windows (ask the PC).
- **Mac hang protection:** size-based export limit; stop after a hang (`MacPowerPointRenderer.broken`);
  `STUCK_FILE` for the next process; 30 s probe export; recovery = close our stuck copies by their unique names
  → polite quit (60 s) → force-quit only as last resort (macOS then shows Microsoft's crash report: tell David to
  untick "Recover work"). Never quits PowerPoint if anything of David's is open (count only). `_render_lock`:
  one export at a time across every SlideTistic process, Mac and Windows. Tested with a forced hang: 17 s.
- **Hidden PowerPoint (Mac, default on, `--powerpoint-visible` / Diagnostics switch):** launched hidden; a
  shown PowerPoint with nothing open is hidden too; hidden again after the document window appears and after
  close. **Limitation:** PowerPoint's own "Export As PDF" progress window un-hides it for ~1–2 s per export
  (longer on big decks); never takes focus.
- **Compression (M013, fix off by default, per-deck switch in the app):** PowerPoint-style 150 ppi + delete
  cropped areas; only pictures whose every reference we measured (never a layout/master/background use);
  JPEG stays JPEG (q85, EXIF/ICC kept), PNG stays PNG. Pitched at ≥25 % and ≥5 MB; 11 of 31 suite decks get
  it. Real results: 65→19 MB, 204→68 MB, 39.9→19.7 MB. **M012** flags video above 1080p (report only).
- **App:** media chip on queue cards + colour banner (blue embedded / amber prep / red won't play offline);
  ▶ VIDEO / ♪ AUDIO badges with start mode on review slides; findings appear before slide images; compression
  banner + switch; temp-file purge (review bundles at launch and on ✕; engine work folders >6 h; Settings →
  Diagnostics "Clear temporary files"; `cli cleanup [--all]`).
- **Placeholder bug (`d868312`):** moving a placeholder that inherits its position from the layout made
  python-pptx write only that value (top → 0); text vanished on every lower-thirds slide. `EditSession`
  pins the inherited position first. Safety pass now counts **words not drawn** too (Mac PDF omits fully
  off-slide text). Test: `tests/test_placeholder_geometry.py` (+ a `-m powerpoint` test on the real deck).
- **Keynote ingest (`daa365c`):** `engine/keynote.py`, see CLAUDE.md. 81 MB deck: 11 s convert, cached 1.5 s.
  X001 detects Keynote exports by layout names (`rules/keynote_layouts.yaml`). App: "Converting from Keynote",
  then a KEYNOTE DETECTED banner saying it was converted and what to check.

## 3b. What the 2026-10-12 session did

- **Tuning mode** (`docs/TUNING.md`): 👍/👎 per changed slide → `_feedback/votes-<machine>.jsonl` (numbers only) →
  `slidetistic tune` (approval by kind of change, proposals replayed against the votes, follow-up questions) →
  `tune --apply` / hand-written gates in `rules/tuning.yaml`. Gate **T001**: no L008 pull for text under 0.1 in
  into the border.
- **Safe-zone fixes narrowed (L008),** from David's findings and 305 votes:
  - the header/footer band (15 %) is never moved and isn't flagged for sitting in the border;
  - near-edge pulls only for blocks ≥25 % of the slide;
  - text on a filled shape moves with the shape, or not at all.
- **Boxes vs letters** (David: "you are mis-reading overlapping text boxes as overlapping text"):
  - "off the slide" now requires the render to show letters touching the edge (`PdfLayout.cut_off`);
  - collisions use the letter zone (cap height → baseline; `fit.letter_zone`, `letter_top_pct` /
    `letter_baseline_pct`), and a clean pixel row between letters clears them (`PdfLayout.letters_apart`);
  - moves now avoid filled shapes, outlines and lines, not just text and pictures (`fit.obstacles`).
- **F001 bug:** it renamed "X Bold" names the deck embeds a font under, which orphaned the embedded file and made
  the text regular (Dealer Trust). It now renames only what F005 can refile (`fonts.canva_weight_embed`, shared).
- **Review screen:**
  - red/amber/accent/grey edges and badges per slide;
  - a "Broken: x of y checked" strip with ✓ per red slide plus one "Whole deck" item, remembered per deck file;
  - filter Everything / Broken + Look at / Broken only (**R**);
  - a **Notes** level (yellow + `evidence["note"]`, not counted in `summary.yellow`; `summary.notes` instead).
- **Fonts:**
  - **F009**, free fonts: sources are Microsoft's Aptos ZIP (`rules/font_downloads.yaml`), then Fontsource, then
    Google; the deck's name picks the entry and every file is name-checked;
  - Fonts banner and tab (like Media), with Get (per-user install) and **Collect fonts next to deck** (copies,
    readably named);
  - Creative Cloud fonts are read for their names;
  - F007: fonts no shown text uses are notes (`core/font_use.py`, checked against PowerPoint PDFs);
  - 157 PowerPoint-bundled fonts count as covered (`rules/office_bundled_fonts.yaml`; F006's list stays
    conservative);
  - the design, research and sources are in `docs/F009_FONTSOURCE_DESIGN.md` §10–13.

## 4. Hard-won facts (don't rediscover)

- **Electron:** 31.7.7 is SIGKILLed on macOS 26 → we use 32.3.3. New npm skips install scripts, so Electron's
  download may not run: unzip the cached zip from `~/Library/Caches/electron` into `node_modules/electron/dist`
  and write `path.txt` (memory note `reference-electron-dev-install`). SlideFluid still pins 31.7.7.
- **Mac PowerPoint can freeze on one export** ("Processing slide 35 of 35") and queue everything behind it; cause
  unknown, not reproducible on demand. Hang protection above contains it.
- **Mac PDF leaves fully off-slide text out; Windows keeps it** (pdftotext clips at the edge). "Every word drawn,
  all inside the slide" is the test (`layout/pdf.py: drawn_text`).
- **Keynote:** classic 14.5 shows "Use the New Version of Keynote" on **every launch** (blocks automation);
  Creator Studio 15.4 shows a one-time welcome whose Continue accepts the licence (David accepted it on the Mac).
  Its export leaves `docProps/app.xml` empty. A damaged .key leaves a Keynote dialog up, hence the pre-check.
- **Force-quitting PowerPoint** triggers Microsoft's crash-report dialog; avoid it.
- **Computer use in the app:** the macOS file picker is a separate process; background clicks don't select rows.
  Use full-screen control, then Browse → ⇧⌘G → type the path (a file path selects it) → Open. Opening a folder
  queues every deck in it.
- **Suite:** SKIP.md skips lower-thirds decks in `suite_run.py`; the app doesn't. David: lower-thirds decks are
  purpose-built; don't chase their layout quirks.
- **Vault** (`/Volumes/Minerva/Vault`) is READ ONLY. The test suite lives in `~/Dropbox/SlideTistic Test Suite`
  (32 decks incl. `media/` samples; `TEST_DECKS.md` lists what each triggers). `corpus/vault/` holds the same
  decks locally (git-ignored); `corpus/app-run/` has the app run's repaired decks.

- **Line boxes are not letters** (2026-10-12): pdftotext's line box spans the font's whole ascent and descent (a
  script title's box reached 1 in above its tallest letter). Never decide "off the slide" or "text over text" from
  boxes alone: use `PdfLayout.cut_off` / `letters_apart` (the render) or `fit.letter_zone` (when predicting).
- **Canva per-weight embeds:** "Roboto Bold" embedded under that name holds Roboto's Bold face. Mac PowerPoint 16.113
  DOES use it as written (Dealer Trust rendered bold before any fix). Rename only together with an F005 refile.
- **Office fonts:** PowerPoint ships 183 font families (`PowerPoint.app/Contents/Resources/DFonts`), and Office for
  Windows installs the same set. `office_fonts.yaml` (26, F006 deletes embeds of these) stays conservative;
  `office_bundled_fonts.yaml` (157) only means "not missing".
- **Fontsource static files are misnamed** for variable families (Montserrat 400 = "Montserrat Thin"); Google's
  CSS API with a legacy user agent gives correct, full-character-set TTFs. python.org Python can't verify HTTPS
  without `truststore` / `certifi` (`engine/core/http.py`).
- **Creative Cloud fonts** are hidden files (`~/Library/Application Support/Adobe/CoreSync/plugins/livetype/.r`,
  Windows `%APPDATA%\Adobe\CoreSync\plugins\livetype\r`). They're read for names; Collect fonts copies them for
  David's own show folders (his call, 2026-10-12). Activation can't be automated.

## 5. Suite results so far

- No-layout, Mac vs PC: 31/31 identical (data checks match exactly across platforms).
- Layout, PC `85f42cd` vs Mac `ae3957c` (old code): 31 compared, 0 exact-check differences, 13 identical, 18 differ
  only in render-based findings (font rendering). Report in `_compare/`.
- New code, Mac `20261011-1207-mac-daa365c-layout` (= v0.4.2 engine): 31 decks, 0 crashes, 0 timeouts, 0 tool_errors,
  Keynote deck converted + repaired. **Second-repair changes: 14** across 7 decks (AACS 1410 3, TSCRA 2026 Room 202 3,
  CLARB 01-02 MASTER 2, media/03 2, media/10 2, PAT 1, media/09 1), down from 76 (Mac `ae3957c`) / 59 (PC `85f42cd`).
  Goal is 0. `suite_run.py` stores only the count: to find the checks, re-run `repair` on a repaired deck with
  `--json` and read the `change` events (first job for engine work; candidate: also save them in the deck json).
  **The PC has not run the new code yet** (mailbox `20261011-1240-mac-release-0.4.2-requests.md`).

- **2026-10-12 final** (`_runs/20261012-1748-mac-…-layout`, v0.4.3 engine): 31 decks, 0 crashes, 0 tool_errors,
  5 second-repair changes. Reds 141 → 71 and yellows 1025 → 596 (+511 notes) against that morning's run; L010 reds 17 → 1.

## 6. Open, in order

1. **Round 3 of votes** on v0.4.3, then `tune`. Show David the real text-collision examples from the suite run
   (§5).
2. **PC:** test v0.4.3 production: the Fonts tab, Get fonts (Windows registry install: written but never run on
   Windows), Collect fonts (no symlinks needed; it copies), Creative Cloud path on Windows, and the auto-update.
3. **Decisions waiting on David:** font shrinking (L010/L008) after he sees real collisions; embed-for-show guidance
   for Creative Cloud fonts; Dropbox suite tidy-up (§ earlier plan in this file's history: keep newest runs,
   `_mailbox/read/`).
4. **Yellows still high on some decks:** L011, C004, L009, M009 are the next tuning targets (median 10 per deck).
5. Earlier items still open: M008 small photos, noisy checks (M009, X003, G003), corpus snapshot acceptance,
   P005 click map, C007 fix, CI off Node 20 actions.

## 7. How David works (also in his global CLAUDE.md)

Collaborator, not a drone: offer alternatives, flag trade-offs, give one-or-two-sentence recaps. Stability and the
end product first; a small speed gain that risks either is his call (he prefers flagging slides for manual review
over long computation). Never commit or push without being asked ("ship"/"push" = yes). He adds "oh also" asks
mid-build: land each as a small isolated change. Plain, crew-readable wording in the app.
