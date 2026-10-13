# Polish pass list

UI and behaviour refinements David wants, parked until the core is stable. Add a line per item with the date
and who asked; move it to "Done" (with the commit) when it ships.

## To do

- **Stacked banners** at the top of the results pane (source, off-slide alert, media, compression) get busy;
  fold into one collapsible strip (David, 2026-10-11: fine for now).
- **PowerPoint flashes into view during each PDF export** in hidden mode (Mac; ~1-2 s, longer on big decks).
  PowerPoint's export window un-hides the app; a re-hide loop would flicker. Look for a better way.
- **Several layout changes per slide per round** (optimization table item): slides with many safe-zone moves
  take one round each (TSCRA CWD uses all 6 rounds). Batch non-interacting moves; risky, David decides.
- **Lower-thirds decks** behave oddly under the layout checks; David: purpose-built, don't chase it.

## Done

- **Review panel: tell RED from YELLOW at a glance** (David, 2026-10-11): severity edges and badges, "Broken: x of y checked"
  with ✓ per red slide, filter + R, and the Notes level (2026-10-12).
- **Fine-tune which layout moves help** (David, 2026-10-11): Tuning mode, 👍/👎 per changed slide → `tune`
  proposals David approves (`docs/TUNING.md`).
