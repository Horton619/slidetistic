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
4. **Checks never measure text themselves.** Use `ctx.layout`. Estimate-based findings cap at yellow.
5. **Never touch pictures for off-slide reasons.** Off-slide rules apply to text-bearing shapes only.
6. **Never shrink fonts or change line spacing to make text fit.** Grow the box.
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

```
venv/bin/python -m pytest                      # unit + contract tests (fast, always)
venv/bin/python -m pytest -m corpus            # snapshot tests on real decks (local)
venv/bin/python -m pytest -m corpus --update-snapshots   # only after David accepts the diff
venv/bin/python -m engine.cli list-checks --json
venv/bin/python -m engine.cli scan <deck.pptx> --json
venv/bin/python -m engine.cli repair <deck.pptx> --preset canva --json
```

**Corpus:** the real-deck folder is read from `--corpus`, `$SLIDETISTIC_CORPUS`, or the git-ignored
`.corpus-path` file (currently David's `~/Downloads`). Snapshots live in the git-ignored `corpus/snapshots/`.
A run takes ~3 min for ~66 decks. It always fails on a crashed check, a repair that introduces a problem,
or a second repair that still changes something. The "corpus diff" section at the end is what to report
to David; only run `--update-snapshots` after he accepts it.

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
