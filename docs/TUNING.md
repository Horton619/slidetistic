# Tuning the layout fixes with David's votes

Built 2026-10-11 after David said more than half of the layout "repairs" were inconsequential or worse.
The idea: David votes, the votes become data, and Claude turns that data into **rule changes David approves**.
Nothing changes the rules on its own.

## David's side (in the app)

1. Settings › Diagnostics › **Tuning mode** (off by default; crews never see it).
2. Repair decks as usual. The Review tab shows a "Tuning mode" bar with **Start voting (V)**; every changed
   slide's card gets 👍 / 👎.
3. In full screen:
   - **Y** or **↑**: 👍, then the next unvoted slide.
   - **N** or **↓**: 👎 (stays on the slide).
   - **1–4**: 👎 with a reason, then the next slide. The reasons are 1 *Not worth it*, 2 *Made it worse*,
     3 *Wrong kind of fix*, 4 *Shouldn't have flagged it*.
   - **0**: clears the vote.
   - **B** / **Space** still flip before ↔ after.
4. One vote covers the whole slide. Voting again replaces the earlier vote. A new repair that changes the slide
   differently is a new item to vote on.

## Where votes go

- The shared Dropbox suite: `SlideTistic Test Suite/_feedback/votes-<machine>.jsonl`. There's one file per
  machine, so the Mac and the PC never write the same file. If the suite isn't there, votes go to
  `userData/feedback`.
- Each line records:
  - deck hash, deck file name and slide number;
  - the vote and the 👎 reason;
  - `tuning_sig`, which identifies the exact set of changes;
  - `changes`: per changed shape, the numbers below;
  - `diff_pct`: the share of the slide's pixels that visibly changed;
  - the thresholds and gate set in force, and the engine and app versions.
- **No slide text is stored.**

## The numbers (engine/core/tuning.py)

| Feature | Meaning |
|---|---|
| `check`, `fix` | L001/L008/L009/L010; move · resize · spacing · font · push (L008 pushing the text below) · pair (text moved with its shape) · other |
| `move_in`, `width_pct`, `font_pct`, `spacing_pct` | net change David sees (before → after), from the review's diff |
| `role`, `words`, `font_pt`, `in_group` | title / header / body / text; size of the text |
| `severity`, `problem` | the finding that triggered the fix (red / yellow; subject) |
| `past_border_in`, `past_edge_in` | L008: how far the text was past the safe border / slide edge |
| `orphan_words`, `lines` | L009 |
| `overlap_pt` | L010 |
| `extra_lines` | L001 |
| `attempts` | how many planned fixes went into the net change |
| `on_shape`, `band`, `area_pct` | text sits on a filled shape; in the header/footer band (top / bottom / placeholder / none); box's share of the slide (added 2026-10-12) |

The gate check (at fix time) sees the *planned* fix; the review records the *net* change. They are the same
for a box changed once, which is nearly every box.

## Claude's side

```
venv/bin/python -m engine.cli tune                 # report + proposals + questions (reads _feedback)
venv/bin/python -m engine.cli tune --out report.md
venv/bin/python -m engine.cli tune --apply P2      # after David says yes: adds the gate to rules/tuning.yaml
```

- **Report:**
  - approval by kind of change;
  - 👎 reasons;
  - median move and visible change;
  - how many changes were nearly invisible (<0.5 % of pixels).
- **Proposals:** single-condition gates (e.g. "skip L008 moves when move_in ≤ 0.06 in on yellow findings"),
  picked greedily. Each one is **replayed against every vote**: 👎 avoided, 👍 lost, and slides only partly
  affected.
  - A proposal must avoid ≥3 👎, and ≥75 % of the votes it touches must be 👎.
  - Losing a 👍 costs twice what avoiding a 👎 gains (stability first).
  - The last line projects the approval rate with every proposal applied.
- **Questions:** the kinds of change David split on, with the numbers that differ most. Ask him these at the end
  of a voting session ("follow up at the end", his request).
- **"Wrong kind of fix" and "Shouldn't have flagged it"** usually need a threshold or detection change
  (`thresholds.yaml`, a check's own rule), not a gate. Read the reasons and propose those to David in words.
- After applying a gate, run `pytest` and the suite. The second-repair count must not go up, and the corpus
  diff should show only the gated fixes turning into open yellow findings.

## Gates (rules/tuning.yaml)

```yaml
gates:
  - id: T001
    check: L008
    fix: move
    when: {move_in: {max: 0.06}, severity: yellow}
    action: skip
    why: skip L008 move fixes, move_in ≤ 0.06, severity = yellow
    votes: avoids 5 👎, loses 0 👍 (2026-10-12, 40 votes)
```

A gated fix raises `FixRefused("left as it was: … (tuning T001)")`. The finding keeps its severity and shows
that reason in Findings. IDs are never reused. To undo a gate, delete it (git has the history).

## Rounds so far

| Round | Engine | Votes | Approved | Main 👎 reason | What changed after |
|---|---|---|---|---|---|
| 1 (2026-10-12 am) | 0.4.2 + tuning | 388 | 14 % | Made it worse | L008: header/footer band, small blocks left, text moves with its shape |
| 2 (2026-10-12 pm) | + review/notes | 103 | 48 % | Not worth it | T001 (<0.1 in), letters-not-boxes (off-slide, collisions), moves avoid shapes, F001 embed fix |

Lessons that votes alone didn't show; looking at the slides with David did:
- the false off-slide titles and the stacked map labels were measurement bugs (line box ≠ letters);
- the "deck-wide fix" 👎s were F001 orphaning embedded fonts.

So when a kind of change is voted down in a cluster, **render before/after pairs and look** before writing a gate.
