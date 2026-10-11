# Handoff: start here (updated 2026-10-11, end of the long Mac session)

For any new Claude Code session, Mac or PC. Read this, then `CLAUDE.md` (how we work, rules, gotchas), then
`SPEC.md` (what we're building; §11 is the dated decisions log). `docs/POLISH.md` is the parked UI/behaviour
list; `docs/EDGE_CASES.md` logs every real-deck surprise; `docs/CROSS_PLATFORM_COMPARE.md` is the Mac ↔ PC
suite protocol. The Dropbox suite's `_mailbox/` holds notes between the Mac and PC sessions: read the newest.

## 1. Where things stand

- **Released:** v0.4.1 (tag `v0.4.1`, commit `23bf87a`): signed + notarized Mac DMG/ZIP and Windows NSIS
  installer, all 8 files in one release. The release workflow now creates one draft up front (v0.4.0's uploads
  were split across two releases; an empty duplicate **v0.4.0 draft** still exists on GitHub: harmless,
  David hasn't okayed deleting it).
- **Next release: v0.4.2** = v0.4.1 + `d868312` (placeholder fix, vanished-text safety) + `daa365c` (Keynote
  ingest) + docs. Tagging it starts CI (~12 min). David's goal: install the **production** 0.4.2 on the PC and
  test it, including the 0.4.0/0.4.1 → 0.4.2 auto-update.
- **Repo is public** (`Horton619/slidetistic`): client decks, run results and anything quoting client text
  never go in git. Signing secrets are set (all five).
- **Machines:** Mac (Apple Silicon, PowerPoint 16.113, Keynote Creator Studio 15.4 + classic Keynote 14.5) and
  David's Windows PC (Ryzen 7 2700X, PowerPoint 16 64-bit, Python 3.11.9, Node 16, gh). Each runs its own
  Claude Code session; they talk through git and the Dropbox suite `_mailbox/`. The Mac is 2–3× faster per CPU
  benchmark (loop 0.09 s vs 0.19 s; lxml 0.29 s vs 0.91 s).

## 2. What David wants next (his words, 2026-10-11)

1. Commit + push, start a release cycle (0.4.2) "so we can test the full new exe from production on the PC".
2. A fresh session with this handoff (the long session's context was full).
3. Fine-tuning of which layout moves help is **later** ("we aren't quite at that point yet"); the review needs a
   way for him to mark changes he agrees/disagrees with first (POLISH.md).

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

## 6. Open, in order

1. **PC:** install production 0.4.2; auto-update test (0.4.1 → 0.4.2); run both suites on the 0.4.2 commit and
   compare with the Mac's; verify media stand-ins render pixel-identically on Windows (render `media/09` both ways);
   **"When Clicked On" video plays on a clicker press in Windows PowerPoint** (suite `media/09`; only verified
   on Mac so far); Poll Everywhere add-in tab storm on the PC (EDGE_CASES, open).
2. Second-repair changes 14 → 0 (§5). Then `docs/POLISH.md` (red vs yellow in the review is David's newest ask).
3. **Tidy the Dropbox suite, only AFTER the PC's 0.4.2 sweep is in and compared** (David, 2026-10-11: don't move
   things while the PC is comparing). It's 1.5 GB (1.3 GB decks) and ~3,700 small files in `_runs/`, mostly page
   images. Plan, all in one pass, with a mailbox note to the PC: (a) keep only the newest run per platform + mode,
   archive/delete the rest; (b) `suite_run.py` stops saving page images unless asked; (c) move decks into
   `decks/` (decks are matched by hash, but update SKIP.md, TEST_DECKS.md, `.corpus-path` and the test that
   names a deck path); (d) handled mailbox notes go to `_mailbox/read/`.
4. David's open questions: M008 ignores photos under 2 MB (flag smaller?); noisy checks (M009, X003, M008, M011,
   G003 grouping, small L011 overlaps); accept corpus snapshot diffs; Fun-skin tagline list.
5. Later: P005 click map, C007 remove-comments fix, F009 Google-font downloader, CI off deprecated Node 20 actions,
   Windows `.ppt`/`.key` messages reviewed on the PC.

## 7. How David works (also in his global CLAUDE.md)

Collaborator, not a drone: offer alternatives, flag trade-offs, give one-or-two-sentence recaps. Stability and the
end product first; a small speed gain that risks either is his call (he prefers flagging slides for manual review
over long computation). Never commit or push without being asked ("ship"/"push" = yes). He adds "oh also" asks
mid-build: land each as a small isolated change. Plain, crew-readable wording in the app.
