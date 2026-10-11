# Mac ↔ PC comparison (2026-10-10)

## For the Mac session: do this next

The PC ran the suite on commit `fb7ecba` (Windows renderer). Its results are in the Dropbox suite under
`_runs/` and there's a note in `_mailbox/`. To compare:

1. `git pull` (same commit as the PC's runs, or newer: then tell the PC to re-run), `venv/bin/pip install -r requirements.txt`.
2. Quit PowerPoint (the renderer works with it open, but a clean run is easier to compare).
3. Run from the **Dropbox** copy, not `corpus/vault` (decks are matched by hash, and the Dropbox copy is the
   one both machines read):
   ```
   export SLIDETISTIC_TOOLS="$PWD/vendor/mac"
   venv/bin/python scripts/suite_run.py --suite ~/Dropbox/"SlideTistic Test Suite"
   venv/bin/python scripts/suite_run.py --suite ~/Dropbox/"SlideTistic Test Suite" --layout --images
   ```
   (Adjust the Dropbox path. Each writes `_runs/<date>-mac-<commit>-<nolayout|layout>/`.)
4. Compare each Mac run with the PC run of the same kind:
   ```
   venv/bin/python scripts/suite_compare.py "<suite>/_runs/<pc run>" "<suite>/_runs/<mac run>"
   ```
   The report lands in `<suite>/_compare/`. Read it, log real differences in `docs/EDGE_CASES.md`.
5. Leave a note in `<suite>/_mailbox/` (`<YYYYMMDD-HHMM>-mac-<subject>.md`): which runs, what differed,
   what you fixed (commit), and what the PC should run next. Tell David.

Both machines write into the same Dropbox folder, so David can open any run, report or note from either.

Goal: run the **same decks** through the **same engine commit** on the Mac and the PC, and get one report of
where the two disagree. Show machines are mostly PCs and crew laptops mostly Macs, so a deck must come out
the same (or knowingly different) on both.

Two Claude Code sessions, one on each machine, never run at the same time and can't call each other. They
talk through two shared places David already has:

| Channel | Carries | Why |
| --- | --- | --- |
| **git** (`Horton619/slidetistic`) | code, this protocol, run/compare scripts | Both machines must run the same commit |
| **Dropbox** `SlideTistic Test Suite/` | the decks, run results, reports, mailbox notes | Client content never goes in git (CLAUDE.md) |

## Folder layout (Dropbox)

```
SlideTistic Test Suite/
  TEST_DECKS.md            # Mac's human-readable list (exists)
  SKIP.md                  # decks both runners leave out, one backtick pattern + reason per line
  suite.json               # NEW: machine-readable list: sha256, size, path, expected findings per deck
  <show folders>/...       # the decks: READ ONLY, never write next to them
  _runs/<YYYYMMDD-HHMM>-<mac|win>-<commit7>/
    run.json               # platform, OS, PowerPoint version, Python, commit (+dirty flag), renderer,
                           # Poppler/ffprobe versions, settings, start/end
    decks/<sha12>.json     # one per deck (below)
    images/<sha12>/...     # optional (--images): the review JPEGs, for side-by-side visual diffs
  _compare/<runA>__<runB>.md   (+ .html with images side by side)
  _mailbox/<YYYYMMDD-HHMM>-<from>-<subject>.md
```

## Skipped decks

`SKIP.md` in the suite folder lists decks that aren't real presentations for this use, as a pattern on the
deck's path plus the reason. `suite_run.py` leaves them out on both machines and records them in `run.json`
(`skipped`). First entry (David, 2026-10-10): **lower-thirds graphics decks** (`*lower thirds*`): their text
sits in the bottom border on purpose, so the layout checks don't apply. Add a line there, not a code change.

## Deck identity = file hash, not path

Paths differ between the machines: the Mac copies live under `corpus/vault/…`, and Windows rewrote
`02_9:1: Press Conference` to `02_9_1_ Press Conference` (`:` isn't allowed in Windows names). Every deck is
identified by the SHA-256 of its bytes. The runner checks each file against `suite.json` and reports
**missing / not yet synced / changed** decks instead of comparing different files. (On 2026-10-10 the PC had
22 of 32 files; all ten missing ones are 50–205 MB, Dropbox still syncing.)

## Per-deck result (`decks/<sha12>.json`)

- `deck`: relative path, size, sha256
- `scan`: findings as `[check, status, slide, shape_id, subject]` rows (the same `rows()` the corpus
  snapshots use), plus each finding's evidence numbers
- `repair`: findings after repair, every change `[check, slide, shape, prop, before, after]`,
  second-repair change count (must be 0)
- `layout`: per text box the renderer judged: words drawn / total, drawn bounds (EMU), off edges;
  fit rounds and what each changed
- `media`: inventory rows (duration, codec, resolution, play mode)
- `timing`: scan, repair, each render (seconds), fit rounds
- `errors`: crashed checks, render errors, timeouts (each deck runs in its own process with a time limit,
  so one stuck deck can't stop the run)

## Scripts

```
venv/<bin|Scripts>/python scripts/suite_run.py --suite "<Dropbox>/SlideTistic Test Suite" [--layout] [--images] [--only <glob>]
venv/<bin|Scripts>/python scripts/suite_compare.py <runA> <runB>      # writes _compare/<runA>__<runB>.md/.html
# not built yet: suite_manifest.py (TEST_DECKS.md → suite.json with expected findings per deck)
```

## How the comparison judges a difference

| Kind | Rule | A difference means |
| --- | --- | --- |
| Data-only checks (fonts F, media M, playback P, content C, X, box-based G) | Must match exactly | A platform bug (encoding, paths, ffprobe, zip handling). Log it |
| Media probe values | Duration/codec/resolution must match | ffprobe build or temp-file bug |
| Render-based (G001/G002 drawn words, L checks, visual review) | Shown side by side, never auto-failed | Usually font rendering differences; large ones get a look |
| Crash, repair that introduces a problem, second repair still changing things | Fails on either side | Engine bug (e.g. `Barlow Bold Bold`, found on the PC) |
| Timing | Side by side | Slow paths (e.g. 500 MB deck, 6 fit rounds: 10 min on the PC) |
| Expectations in `suite.json` | Each side vs. the list | Regression on one platform |

The report opens with: decks compared, decks skipped (missing/changed hash), exact-match count, then one
section per deck with only the differences.

## Mailbox (how the two sessions talk)

A note is a short markdown file in `_mailbox/`, newest first by name: `20261010-2140-win-render-pass.md`.
Each one says what was run (run folder names, commit), what was found, and **what the other side should do
next** (e.g. "pull `abc1234`, run `suite_run.py --layout`, then compare with `20261010-2130-win-abc1234`").
At the start of any suite work, each session reads the mailbox, does what's asked, and replies with a new
note. David starts the sessions; nothing polls on its own. (Later, if useful: a scheduled task on each
machine that checks `_mailbox/` for a request and runs it.)

## Round trip

1. Mac: write `suite.json` from its copies (hashes), drop a note.
2. Both: `git pull` the same commit; run `suite_run.py` (once without layout, once with `--layout --images`).
3. Whoever runs second: `suite_compare.py`, write the report, drop a note with the findings.
4. Differences: log in `docs/EDGE_CASES.md`, fix on either machine, push, next round on the new commit.

## Rules

- Decks are read only: results go under `_runs/`, `_compare/`, `_mailbox/` and nowhere else.
- Run results quote client text (finding subjects, messages) and may hold slide images: they stay in
  Dropbox, never in git, never in an Artifact.
- Both sides must run the same commit; the comparer refuses mismatched commits unless `--allow-mismatch`.
- Close PowerPoint before a `--layout` run (see below).

## Known PC issues this already surfaced (2026-10-10)

- **Rendering in David's open PowerPoint can hang.** PowerPoint is single-instance under COM, so the engine's
  hidden copy opens inside David's PowerPoint. Two lower-thirds decks hung in `SaveAs` there (PowerPoint idle,
  no visible dialog); the same deck exports in 9 s in PowerPoint's own instance. The watchdog won't kill a
  PowerPoint that isn't ours, so the call never returned. Cause not yet found.
- **Layout repair is CPU-bound in python-pptx** (placeholder inheritance lookups on every round): a 70-slide
  5.7 MB deck spends 65–155 s per fit round. Same Python on the Mac, so the comparison will show both.
