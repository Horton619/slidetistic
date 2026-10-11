# Handoff: PC → Mac (2026-10-10, night)

For Claude Code on David's Mac. Read this first, then `CLAUDE.md`. Everything the PC session did, found and
left open is here; details live in the linked files. Rewrite or delete this file once the Mac has acted on it.

## 1. Do this first

1. `git pull` (main ≥ `5c7a98a`), `venv/bin/pip install -r requirements.txt` (adds `pywin32`, Windows only).
2. `venv/bin/python -m pytest -q`: expect **1012 passed, 1 skipped** on the PC; on the Mac the Windows-only tests
   skip instead (`tests/test_render.py`). `-m powerpoint` drives real PowerPoint: run it on the Mac too.
3. Read the PC's note: `Dropbox/SlideTistic Test Suite/_mailbox/20261010-2300-win-renderer-pushed.md`.
4. **Run the shared suite and compare with the PC** (protocol: `docs/CROSS_PLATFORM_COMPARE.md`, "For the Mac
   session"). Quit PowerPoint first. Run from the Dropbox copy, not `corpus/vault` (decks are matched by hash):
   ```
   export SLIDETISTIC_TOOLS="$PWD/vendor/mac"
   venv/bin/python scripts/suite_run.py --suite ~/Dropbox/"SlideTistic Test Suite"
   venv/bin/python scripts/suite_run.py --suite ~/Dropbox/"SlideTistic Test Suite" --layout --images
   venv/bin/python scripts/suite_compare.py "<suite>/_runs/<pc run>" "<suite>/_runs/<mac run>"   # per pair
   ```
   The PC's runs on `5c7a98a` are in `_runs/` (`*-win-5c7a98a-nolayout`, `*-win-d5a682f-layout` (same engine code); the layout run
   is long and may still be filling in). Docs-only commits since then are fine: the comparer accepts commits
   whose `engine/` and `requirements.txt` are identical and says so in the report.
5. Reply in `_mailbox/` (`<YYYYMMDD-HHMM>-mac-<subject>.md`), log real differences in `docs/EDGE_CASES.md`,
   tell David. **Next (David): a heavy optimization round once the Mac suite run is in.**

## 2. What changed (the PC commits after your `28c0370`: `git log 28c0370..origin/main`)

**Windows PowerPoint renderer** (`engine/render.py`). `PowerPointRenderer` is now a platform switch over
`MacPowerPointRenderer` (unchanged behaviour) and `WindowsPowerPointRenderer` (COM via pywin32). Layout fixes,
the visual review and drawn-word G001/G002 work on Windows. Safety rules as in the brief: only the presentation
our `Open` returned is touched (confirmed by path), PowerPoint is quit or killed only if we started it and no
user window is in it. See `CLAUDE.md` → "Windows renderer".

**Shared engine changes: these run on the Mac too, check nothing moved:**
- `engine/core/layout/pdf.py`: bbox coordinates may be **negative** (Windows keeps off-slide text in the PDF;
  the parser used to drop those lines). Output decoded as UTF-8.
- `engine/core/runner.py`: a `RenderError` no longer crashes a repair. Baseline render fails → repair continues
  without layout; fails mid-fit → layout changes put back, other fixes kept (warning event).
  `_layout_for` asks `available()` every time.
- **Speed (identical results):** `Deck.slide_shapes(n)` walks one slide (find_shape, PdfLayout.slide, fit and the
  safety pass used to walk every slide); the safety pass computes layout findings once per render. PAT 23:
  over 25 min → 211 s, identical findings/changes/output fingerprints.
- `engine/core/fonts.py` `split_style`: strips repeated style words (`Barlow Bold Bold` took two repairs).
- `engine/core/media.py`: ffprobe output decoded as UTF-8.

**App** (`src/main.js`, `src/renderer/app.js`): a clicked Repair/Undo stops a running scan (unless mid-render)
and runs next; the scan re-runs after ("Waiting: a repair went first"). Stall guard: no engine output for 6 min
(scan) / 10 min (repair) → red card, queue moves on. Windows: PowerPoint detection (`app:info`) and
open-at-slide via PowerShell COM. David tested these in the dev app on the PC: all pass.

**CI** (`release.yml`, `release-win`): bundles Poppler for Windows (oschwartz10612 v24.08.0-0, SHA-256 pinned).

**Suite** (`scripts/suite_run.py`, `scripts/suite_compare.py`, `docs/CROSS_PLATFORM_COMPARE.md`): runs every
deck through `engine.cli` like the app; results, reports and notes stay in Dropbox (`_runs/`, `_compare/`,
`_mailbox/`). `SKIP.md` in the suite skips **lower-thirds decks** (David: not presentations); `TEST_DECKS.md`
#22 marked skipped. Your corpus-snapshot setup (`28c0370`) sits beside it; `pytest -m corpus` doesn't read
`SKIP.md` yet.

## 3. Windows facts the Mac code now depends on

- Windows PowerPoint 16 (64-bit) via COM: hidden slides are left out of the PDF; page = slide size exactly;
  ~1 s per export (~3 s to start PowerPoint).
- **Off-slide text stays in the PDF** (Mac leaves it out). pdftotext clips at the page edge, so words straddling
  it come out cut ("cuatro" → "ro") and count as not drawn. Net effect matches the Mac.
- PowerPoint is single-instance under COM: if David has PowerPoint open, our hidden copy opens inside it.
- A killed engine leaves its PowerPoint running hidden; the next engine closes it (recorded pid + start time,
  only when the engine that started it is gone and no window is visible).

## 4. Open (all in `docs/EDGE_CASES.md`)

| Issue | Status |
| --- | --- |
| **Layout fixes don't settle in one repair**: L009 nudges a box ~2% per round because PowerPoint doesn't re-wrap where Reflow predicted; 6-round cap; a second repair keeps going (Loop Lid slides 3 + 5; same as your CLARB 11). Safety pass keeps futile nudges because its "fixed nothing" undo is per slide | **Open**, David: optimization round. Proposed: jump after a missed prediction; undo per box |
| Layout repair is still CPU-heavy (python-pptx); PC: Ryzen 7 2700X; David says the Mac feels much faster | Compare per-stage timings + the benchmark in the PC's mailbox note |
| FENDT press-conference deck (AGCO, on APOLLO) hung a 0.4.0 scan on the PC; not in the suite | Open; stall guard contains it |
| Render inside David's already-open PowerPoint hung once (SaveAs wrote the PDF, never returned) | Guarded (abandoned after 300 s, renderer off for that run); cause open |
| Diagnostics "PowerPoint found" line is easy to miss (small grey text) | David to confirm what it shows; consider a status row |

## 5. Release status

- **0.4.1 not tagged.** David: ship after the renderer, and the big optimization round is next, so ask David
  whether 0.4.1 goes out before or after it. Tagging bumps `package.json` and triggers CI; the updater test
  (installed 0.4.0 → 0.4.1) is in `docs/HANDOFF.md`.
- Installed-app checklist on the PC (0.4.0): launch/settings pass; Repair-behind-scans fixed in the repo; the
  rest is still to do, especially **"When Clicked On" video plays on a clicker press in Windows PowerPoint**
  (use suite deck `media/09 …WHEN CLICKED ON…`; the PC's run converted it).

## 6. PC setup notes (for whoever works on the PC next)

Python 3.11.9 (installed via winget), Node 16.13.1 (npm ci works; Node 20 recommended), `gh` installed and
signed in, git identity set per repo. `vendor/win/` holds Poppler 24.08 + the installed app's ffprobe. The dev
app and the installed app share `%APPDATA%\SlideTistic` (settings + log).
