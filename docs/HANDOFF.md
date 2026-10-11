# Handoff: Mac → PC (updated 2026-10-10, evening)

For Claude Code on David's Windows PC. Read `CLAUDE.md` and `SPEC.md` first; this file covers where
things stand, what the PC is for, and the brief for the **Windows PowerPoint renderer**, which is the next
thing to build. Rewrite this file when it goes stale.

## Where things stand

- **v0.4.0 released** (tag `v0.4.0`, commit `13cd730`): first CI release of the desktop app.
  - Mac: signed + notarized DMG and ZIP. Windows: unsigned NSIS installer `SlideTistic-Setup-0.4.0.exe`.
  - The first run split its uploads across two v0.4.0 releases; the Windows files were copied into the
    published release by hand (it has all eight files). The workflow now creates one draft up front.
    An empty duplicate v0.4.0 *draft* may still exist on GitHub; harmless, David hasn't okayed deleting it.
  - First Windows CI test run: 992/994; the 2 failures were tests reading UTF-8 as cp1252 (fixed).
- **Repo is public** (needed for electron-updater). Client decks never go in git: `corpus/` is ignored.
- **Signing secrets** are set on the repo (all five).
- **Windows scope today:** fonts, geometry, media, playback and content checks + fixes. **No layout fixes,
  no visual review, and box-based (noisy) off-slide warnings on Windows**: all three need PowerPoint to
  render the deck, and only the Mac (AppleScript) renderer exists. That's what the renderer below fixes.

### On `main` since v0.4.0 (ships in 0.4.1; not released yet)

- Windows: ffprobe couldn't read embedded videos (temp file held open). Fixed: video length/codec now work.
- **Media alert**: speaker chip on queue cards + colour-coded banner in the results pane (blue all
  embedded, amber prep needed, red won't play offline). David asked for this while testing.
- **Off-slide judged by drawn words** (G001/G002): with a render, a box that overhangs but whose words are
  all drawn inside the slide is silent; words cut off are red ("6 of 15 words are below the bottom").
  Key fact: **PowerPoint's PDF leaves out words that fall outside the slide** (Mac, broken deck slides 18
  and 20: 0/11 and 9/15 words drawn), so "every word drawn, all inside" is the test
  (`engine/core/layout/pdf.py: drawn_text`). Without a render the old box rules still apply.
  App scans now use the render on the Mac (`--layout`, ~4 s per deck).
- Layout fixes that resolved nothing are undone quietly (runner `_fit_problems`); paragraphs under 6 words
  are never orphans (`orphan_min_paragraph_words`); review tooltips read "width 3.22 → 3.04 in".
- David's feedback themes from testing: **cut noise hard**; never show a change that had no visible effect;
  operators care most about media (download/offline/re-embed) and text that's truly off the slide.

## What the PC is for

1. **Build the Windows PowerPoint renderer** (brief below). Biggest gap: show machines are mostly PCs.
2. Test the installed Windows app (checklist below).
3. Save Windows PowerPoint versions of the test decks ("never guess PowerPoint XML" needs Mac + Win saves).

## Setup on the PC

Claude Code on Windows runs commands in Git Bash. Paths below are Git Bash style.

```bash
git clone https://github.com/Horton619/slidetistic.git     # or `git pull` if already cloned
cd slidetistic
py -3.11 -m venv venv                              # Python 3.11 from python.org, matches CI
venv/Scripts/pip install -r requirements.txt
venv/Scripts/python -m pytest -q                   # should be all green (CI runs it on Windows now)
npm ci                                             # then `npm start` runs the app in dev
```

- **Tools for dev:** the engine finds Poppler and ffprobe via `SLIDETISTIC_TOOLS` (a folder), then PATH.
  The installed app ships ffprobe in `resources/tools`. For the renderer you also need Poppler for Windows
  (`pdftotext.exe`, `pdftoppm.exe` + their DLLs): download the release SlideFluid's workflow uses
  (oschwartz10612/poppler-windows v24.08.0-0), copy `Library/bin/*` into `vendor/win/` (git-ignored),
  and `export SLIDETISTIC_TOOLS="$PWD/vendor/win"`. Ask David before downloading.
- **Electron install trap (seen on the Mac):** newer npm may skip Electron's download step. If
  `npm start` says "Electron failed to install correctly", run `node node_modules/electron/install.js`.
- Claude's memory notes from the Mac go in `C:\Users\<you>\.claude\projects\<this project's folder>\memory\`
  (David copies them over).

## Shared real-deck test suite (Mac and PC test the same decks)

32 client decks chosen so each kind of finding shows up in one or two decks, plus media samples (Google
"picture that opens YouTube", PowerPoint Online Video, YouTube links, embedded video in every start mode
including a real "When Clicked On"). They live in **Dropbox, never in git** (the repo is public and these
are client decks): `Dropbox/SlideTistic Test Suite/`, with `TEST_DECKS.md` there listing what each deck
should trigger. Point the corpus tests at it, once per machine:

```bash
echo "C:/Users/<you>/Dropbox/SlideTistic Test Suite" > .corpus-path    # git-ignored; use your Dropbox path
venv/Scripts/python -m pytest -m corpus                                 # first run: no snapshots yet
```

Snapshots are per machine (`corpus/snapshots/`, git-ignored), keyed by the deck's path inside the suite.
The first run on each machine fails with "no snapshot yet": review the findings against `TEST_DECKS.md`,
then `--update-snapshots`. Expect some Mac/PC differences where fonts render differently; report them
rather than forcing them to match. Make sure Dropbox has the folder fully downloaded (not online-only).

## Brief: Windows PowerPoint renderer

**Goal:** on Windows with PowerPoint installed, the engine renders decks exactly as it does on the Mac,
so layout fixes, the visual review (before/after slide pictures) and drawn-word off-slide checks all work.
Everything downstream already exists and is platform-neutral: it only needs a PDF of the deck.

### The contract (copy the Mac class in `engine/render.py`)

```
name: str                                   # shown in diagnostics, e.g. "PowerPoint for Windows"
available() -> (bool, reason)               # staticmethod; reason is shown to the user when False
to_pdf(pptx: Path, label: str) -> Path      # export a COPY of the deck to PDF; raise RenderError on failure
page_image(pdf, page, width=960) -> bytes   # JPEG via pdftoppm (identical on both platforms)
cleanup()                                   # delete work files
```

Callers construct `PowerPointRenderer` directly in three places: `engine/core/runner.py` (`_layout_for`)
and `engine/cli.py` (`_write_report`, `_undo_slide`). Add one `get_renderer()` / platform switch in
`engine/render.py` and point those three at it; don't spread `sys.platform` checks around.

### How (COM via pywin32)

- `pywin32` in `requirements.txt` with a marker: `pywin32==<version>; sys_platform == "win32"`.
  PyInstaller handles it through pyinstaller-hooks-contrib; check the packaged engine still lists 40 checks.
- `pythoncom.CoInitialize()`; `app = win32com.client.Dispatch("PowerPoint.Application")`.
- Copy the deck to a unique temp path first (`slidetistic-<uuid>-<label>.pptx`), like the Mac.
  `shutil.copyfile` doesn't carry the Mark-of-the-Web, so no Protected View.
- `pres = app.Presentations.Open(str(copy), ReadOnly=True, Untitled=False, WithWindow=False)`, then
  `pres.SaveAs(str(pdf), 32)` (32 = ppSaveAsPDF) or `pres.ExportAsFixedFormat(...)`, then `pres.Close()`.
- **Safety rules, non-negotiable** (a name clash once closed David's own deck on the Mac):
  - Only ever touch the `pres` object returned by *your* `Open`. Never index `app.Presentations`, never use
    `ActivePresentation`, never look up a presentation by name, never enumerate the user's open decks.
  - If PowerPoint was already running before you started, never call `app.Quit()`. Detect it with
    `win32com.client.GetActiveObject("PowerPoint.Application")` before dispatching. If you started it
    and nothing else is open in it, quitting is fine.
  - Never modify the input file (only the copy is opened, read-only).
- **Hangs:** a COM call can block on a dialog (repair prompt, password, missing-link warning). Put a
  timeout around the export (the Mac uses 300 s) and turn a hang into `RenderError` with a plain message.
  Password-protected decks: `Open` raises; report it, don't prompt.
- `available()`: False with a reason if not Windows, PowerPoint isn't registered
  (`HKEY_CLASSES_ROOT\PowerPoint.Application`), or Poppler isn't found via `tools.find`.

### Things to verify on the PC (the Mac behaviour the engine depends on)

1. **Hidden slides are left out of the PDF.** `PdfLayout._load` maps pages to slides assuming that.
   If Windows includes them, use `ExportAsFixedFormat` with `IncludeHiddenSlides=False` (msoFalse).
2. **Words outside the slide are left out of the PDF text.** `drawn_text` relies on it. Run
   `corpus/broken_mac.pptx` (David will copy it over): slide 18's off-left box must draw 0 of 11 words,
   slide 20's box 9 of 15, slide 19's 2 of 2.
   The probe script pattern: build `PdfLayout(deck, renderer)`, then for each text shape compare
   `len(_tokens(shape_text(sv.shape)))` with the drawn tokens from `layout.measure(slide, shape_id)`.
3. **Page size = slide size** (PDF points × 12700 = EMU), so word positions land in slide coordinates.
4. **Speed:** the Mac exports a 30-slide deck in ~1–3 s. Report the Windows time.
5. End to end: `venv/Scripts/python -m engine.cli repair "<PAT deck>" --out out.pptx --review-dir rd`
   should give results close to the Mac's (PAT: 58 fixed, 27 to look at, 0 broken). Fonts render
   differently on Windows, so some layout calls will legitimately differ; report the diff, don't force it.

### Also to wire up

- `src/main.js`: `app:info` reports `powerpoint: null` on Windows; detect it (registry or ask the engine).
  `ppt:openAtSlide` on Windows just opens the file; with COM it can open and `GotoSlide(n)` in the
  user's own PowerPoint window (this one is meant to be visible and stay open).
- CI (`.github/workflows/release.yml`, `release-win` job): bundle Poppler for Windows into `vendor/win`
  (copy SlideFluid's download step, but take `pdftotext.exe` and `pdftoppm.exe` plus DLLs). The engine
  smoke test can't render on CI (no PowerPoint there); `available()` returning False must not fail anything.
- Tests: the renderer can't run in CI. Keep logic that doesn't need PowerPoint (platform switch, unique
  names, error mapping) unit-testable; mark any real-PowerPoint test so it's skipped unless asked for.
- Docs: `CLAUDE.md` (renderer notes + any Windows gotchas found), `SPEC.md` decisions log,
  `docs/EDGE_CASES.md` for anything surprising.

## Test checklist: installed Windows app

Install from the Releases page (unsigned: SmartScreen → **More info → Run anyway**).
Log file: `%APPDATA%\SlideTistic\slidetistic.log` (also Settings → Diagnostics).

- [ ] Launches; queue and drop zone appear; Settings opens (all four tabs).
- [ ] Drop a deck → it scans; findings and the Canva/Google banner look right.
- [ ] Drop a folder → every deck inside is queued; ✕ removes one.
- [ ] A `.key` or a broken file gets a red ✕ card with a plain explanation.
- [ ] Repair → "Deck - mended.pptx" next to the original; repairing again makes "(2)". Original untouched.
- [ ] Open the mended deck in **Windows PowerPoint**:
  - [ ] Fonts look right; Mac-only fonts (Avenir etc.) were swapped.
  - [ ] **A video that was "When Clicked On" now plays on a clicker/arrow press** in Slide Show (only
        verified in Mac PowerPoint so far; the most important check).
- [ ] Media tab lists videos; CSV/Excel export saves. (0.4.0: lengths blank, fixed in 0.4.1.)
- [ ] Watch folder picks up a dropped deck. SlideFluid button opens it or says it isn't installed.
- [ ] Settings → Diagnostics → Check for updates works.

## Windows PowerPoint saves to make

From `docs/BROKEN_DECK_RECIPE.md`: `broken_win.pptx` built in Windows PowerPoint, especially items 01–09
(video start modes, rewind, loop, trim, mute, audio), 13–16 (advance, click animations, trigger) and 27
(comments). Decks go in the local `corpus/` folder, never in git.

## Open questions for David (carried over)

- Ship 0.4.1 now, or after the renderer?
- Slide 35 "huge photo, small": M008 ignores photos under 2 MB. Flag smaller ones?
- Noisy checks: M009, X003, M008, M011, G003 grouping, small L011 overlaps: keep, tone down, or hide?
- Accept the corpus snapshot diffs so later changes are measured against them.
- Fun-skin taglines rotation list (Pro is now "PowerPoint is my special interest.").

## After the renderer

1. P005 click map (needs saved decks with click animations from Mac and Windows).
2. Faster layout repair (~80 s per deck now).
3. C007 "remove comments" fix, F009 Google-font downloader, move CI off deprecated Node 20 actions.
4. Keynote conversion.
