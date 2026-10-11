# Polish pass list

UI and behaviour refinements David wants, parked until the core is stable. Add a line per item with the date
and who asked; move it to "Done" (with the commit) when it ships.

## To do

- **Review panel: tell RED from YELLOW at a glance** (David, 2026-10-11). The review tiers mix "broken, fix before
  the show" with "worth a look"; each slide card (and its boxes) should make the severity unmistakable, e.g.
  a red or amber edge/badge per card and per box, and a filter to show only reds.
- **Fine-tune which layout moves help** (David, 2026-10-11). Some text moves have little effect or make a slide
  worse. Needs a way for David to mark changes he agrees or disagrees with, e.g. 👍/👎 per slide in the review,
  saved where Claude can read it back, to tune the fit rules against.
- **Stacked banners** at the top of the results pane (source, off-slide alert, media, compression) get busy;
  fold into one collapsible strip (David, 2026-10-11: fine for now).
- **PowerPoint flashes into view during each PDF export** in hidden mode (Mac; ~1-2 s, longer on big decks).
  PowerPoint's export window un-hides the app; a re-hide loop would flicker. Look for a better way.
- **Several layout changes per slide per round** (optimization table item): slides with many safe-zone moves
  take one round each (TSCRA CWD uses all 6 rounds). Batch non-interacting moves; risky, David decides.
- **Lower-thirds decks** behave oddly under the layout checks; David: purpose-built, don't chase it.

## Done

(nothing yet)
