# CLAUDE.md — SlideTistic

Read `SPEC.md` for what we're building. This file is how we work.

## How David works

David directs in short additions during build and test: "oh, and add a check for ___",
"by the way, Google decks do ___". Expect many of these. Each one must land as a small,
isolated change that cannot break existing checks. When a request is ambiguous, build the
**detect** half first (report only), show the findings on the fixtures and corpus, and ask
before adding a fix.

## Golden rules

1. **A new check is a new file.** Never add checks to a central list, `if/elif` chain, or
   the UI. The registry discovers `engine/checks/**/[A-Z][0-9][0-9][0-9]_*.py`; the UI builds
   itself from `slidetistic list-checks`.
2. **Data goes in `engine/rules/*.yaml`, not code.** A new font alias, Office font, Canva-only
   font, threshold or preset default is a YAML edit with no code change.
3. **Checks never edit the deck directly.** Only through `EditSession` in `fix()`. `detect()` is read-only.
4. **Checks never measure text themselves.** Use `ctx.layout` (PowerPoint's own render via PDF). Estimate-based findings cap at yellow.
   Every finding should say *why* in `evidence["rule"]`: the heuristic and the numbers (diagnostic mode).
5. **Never touch pictures for off-slide reasons.** Off-slide rules apply to text-bearing shapes only.
6. **Fit fixes in order: box, then line spacing, then font size** (David, 2026-10-10). Floors and caps live in
   `thresholds.yaml`; every fit change must be visible in the review page.
7. **Never modify the input file.** Tests assert this.
8. **Don't change another check's behavior to make a new one pass.** If two checks conflict,
   declare `runs_after` or raise it with David.

## Recipe: "add a check for ___"

1. **Classify it.** Is it really a new check, a rule-data change (step 2 above), or a bug in an
   existing check? A new edge case in an existing check = fix that check + add a fixture; don't
   create a near-duplicate check.
2. **Log it** in `docs/EDGE_CASES.md` (date, what David saw, source app, which check, fixture name).
3. **Pick the next free ID** in the group (`F` fonts, `G` geometry, `L` layout fit, `P` playback, `M` media, `C` content, `X` other). IDs are never reused or renumbered.
4. **Copy** `engine/checks/_template.py` to `engine/checks/<group>/<ID>_<slug>.py`. Fill in the
   metadata. New checks start with `default_fix = False` unless David says otherwise.
5. **Write fixtures first** in `tests/checks/test_<ID>_<slug>.py`: at least one deck where it
   fires, one where it must not (including the nearest look-alike case, e.g. a picture for an
   off-slide text check).
6. **Implement** `detect`, then `fix` if wanted. Thresholds go in `rules/thresholds.yaml`.
7. **Run** `pytest` (contract tests run on the new check automatically), then `pytest -m corpus`
   if the corpus path is set. Report the corpus diff to David: what the new check finds across
   real decks, and confirm no other check's results moved.
8. **Summarize** in one or two lines: check ID, what it detects, fix on/off, fixture names.

## Recipe: "this deck broke and the tool missed it"

1. Get the deck into the local corpus folder (never commit client decks).
2. Find which check should have caught it. Write the smallest fixture that reproduces it.
3. Fix the check; confirm the fixture passes and the corpus diff shows only the intended change.
4. Log it in `docs/EDGE_CASES.md`.

## Never guess PowerPoint XML

For anything PowerPoint encodes in the timing tree or extensions (video play modes, triggers,
animations, trims), build the case in real PowerPoint, save it, and use that file as the fixture.
The pattern from memory is not good enough; detectors must match saved files from both Mac and Windows.

## Commands

Always use the project venv (`venv/`, Python 3.11 to match CI), never system `python3`.
On Windows (Git Bash) the venv is `venv/Scripts/python`, and the engine needs `export SLIDETISTIC_TOOLS="$PWD/vendor/win"`.

```
venv/bin/python -m pytest                      # unit + contract tests (fast, always)
venv/bin/python -m pytest -m powerpoint        # drives real PowerPoint (Mac or Windows; never in CI)
venv/bin/python -m pytest -m corpus            # snapshot tests on real decks (local)
venv/bin/python -m pytest -m corpus --update-snapshots   # only after David accepts the diff
venv/bin/python -m engine.cli list-checks --json
venv/bin/python -m engine.cli scan <deck.pptx> --json
venv/bin/python -m engine.cli repair <deck.pptx> --preset canva --json   # + "<out> report.html" with visual review
venv/bin/python -m engine.cli repair <deck.pptx> --no-visual            # report without PowerPoint renders
venv/bin/python -m engine.cli media <deck.pptx> --xlsx out.xlsx          # inventory + download list
```

Reports with client slides go in the git-ignored `corpus/reports/`; view them with the `reports`
preview server (`.claude/launch.json`, port 8799). The visual review drives PowerPoint for Mac via
AppleScript. Working copies get unique names (`slidetistic-<uuid>-<label>.pptx`); after opening, the renderer
takes the *active* presentation and confirms its full path before exporting/closing. Never address a
presentation by name, and never enumerate David's open presentations: a name clash once closed his deck.
AppleScript gotcha: `out` is a reserved word in PowerPoint's dictionary; `whose` filters aren't supported.

**Windows renderer** (`WindowsPowerPointRenderer`, COM via pywin32): opens a copy with
`Presentations.Open(copy, ReadOnly, WithWindow=False)`, confirms `FullName` is the copy, `SaveAs(pdf, 32)`,
closes it. Callers only use `render.PowerPointRenderer` (the platform switch). ~1 s per export, ~3 s once to
start PowerPoint. PowerPoint is single-instance: if David's PowerPoint is open, the hidden copy opens in it,
so never use `ActivePresentation`, never enumerate `Presentations`, and only quit (or kill after a hang) the
POWERPNT.EXE process we started, when no other deck or visible window is in it. Windows gotchas:
- **The PDF keeps off-slide text** (the Mac leaves it out); pdftotext clips at the page edge, so expect
  negative coordinates and cut words ("cuatro" → "ro"). A clipped word counts as not drawn.
- The COM object has no `HWND`; which PowerPoint is ours = the process that appeared on dispatch.
- Decode subprocess output as UTF-8 explicitly; Windows defaults to cp1252.
- A killed engine leaves its PowerPoint running hidden. The renderer records the PowerPoint it started
  (`%TEMP%/slidetistic/owned-powerpoint.json`, pid + start time) and the next engine closes that exact
  process if it has no visible window. All COM calls run on one daemon thread with a time limit.
- Releasing the last COM handle after PowerPoint quits raises a handled `0x80010108`; pytest's fault
  handler prints it as "Windows fatal exception". Harmless.

**Mac ↔ PC suite:** `scripts/suite_run.py` / `scripts/suite_compare.py` run the shared Dropbox
`SlideTistic Test Suite` and compare platforms; results, reports and notes live in that folder (`_runs/`,
`_compare/`, `_mailbox/`), never in git. Read `_mailbox/` first. Protocol: `docs/CROSS_PLATFORM_COMPARE.md`.
Same folder as the corpus snapshot tests below: those check one machine against its own snapshots; the suite
scripts compare Mac against PC. `SKIP.md` (lower-thirds decks) is read by `suite_run.py` only, not yet by
`pytest -m corpus`.

**Corpus:** the real-deck folder is read from `--corpus`, `$SLIDETISTIC_CORPUS`, or the git-ignored
`.corpus-path` file: the shared suite in `Dropbox/SlideTistic Test Suite/` (32 decks, same on Mac and PC; its `TEST_DECKS.md` says what each should trigger; never copy it into git). Snapshots live in the git-ignored `corpus/snapshots/`.
A run takes ~3 min for ~66 decks. It always fails on a crashed check, a repair that introduces a problem,
or a second repair that still changes something. The "corpus diff" section at the end is what to report
to David; only run `--update-snapshots` after he accepts it.

## Packaging (phase 3)

```
scripts/vendor_mac_tools.sh      # Poppler pdftotext + pdftoppm → vendor/mac (dylibbundler, no Homebrew paths)
scripts/build_ffprobe.sh         # minimal LGPL ffprobe (demuxers only, ~4 MB) → vendor/<mac|win>
npm run build:engine             # PyInstaller one-folder engine → backend/dist/slidetistic_engine/
npx electron-builder --mac --dir -c.mac.identity=- -c.mac.notarize=false   # local ad-hoc test build
```

- The engine finds helper programs via `engine/core/tools.py`: `SLIDETISTIC_<NAME>`, then `SLIDETISTIC_TOOLS`
  (main.js sets it to `resources/tools` packaged, `vendor/<plat>` in dev), then PATH.
- The registry loads checks from `.py` files and rules from YAML, so the spec ships `engine/checks` and
  `engine/rules` as data and `collect_submodules("engine")` as hidden imports. A missing hidden import builds
  fine and only fails at run time; CI's "Smoke-test the engine" step catches it.
- `vendor/` is git-ignored; CI rebuilds it every release (`.github/workflows/release.yml`, tag `v*`).
- The minimal ffprobe matched Homebrew's full ffprobe on all 333 corpus videos (2026-10-10). Don't ship
  Homebrew's ffmpeg: it's a GPL build with 36 libraries.

Test-only checks live in `tests/dummy_checks/` (X998 crashes on purpose, X999 fixes negative-x text).
They prove the runner and contracts work; they are never shipped.

## Engine gotchas

- **python-pptx writes on read.** `prs.slides` adds an empty `<p:sldIdLst>` to a slideless deck.
  Use `Deck.slides`, never `deck.prs.slides`, inside `detect()`. The read-only contract test
  catches this class of bug: if it fails, look for a python-pptx `get_or_add_*` call.
- **Group geometry:** `shape.left` on a group child is in the group's child space. Use
  `ShapeView.bounds` (absolute) for decisions; `EditSession.set_geometry` takes local values.

## Conventions

- Units: EMU internally (914400 per inch). Convert to inches only for messages.
- Shape identity in findings: slide index (1-based for humans), shape id, and shape name.
- Messages are plain, short, crew-readable: "Title text needs 13.85 in; box is 13.81 in."
- Status vocabulary is fixed: `green_clean`, `green_fixed`, `yellow`, `red`, `tool_error`.
  Don't invent new statuses; add an evidence field instead.
- Mirror SlideFluid's IPC style: JSON-lines events, typed preload API, unsubscribe-pattern listeners.

## Reference

`reference/fix_canva_fonts.py` and `reference/audit_tight_boxes.py` are prototypes from the
first investigation (PAT MBD deck). Port their logic into checks. Note: the width estimate in
`audit_tight_boxes.py` over-flags heavily; don't port it as a decision-maker.
