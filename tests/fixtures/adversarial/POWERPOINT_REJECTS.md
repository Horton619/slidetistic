# Decks PowerPoint rejects

Checked 2026-10-13 on David's Mac (PowerPoint for Mac, Microsoft 365), round 2. Each deck below was opened as
a copy; PowerPoint said "found a problem with content … Repair?". After Repair it strips or rewrites the part it
can't read, then the engine measures that repaired deck, not the one on disk. Until a deck here is rebuilt from
a real PowerPoint save, its layout results (and any check that reads the broken part) are not trustworthy.

Swept: the 20 decks built with hand-written timing, comment, SmartArt, ink, OLE or media XML, then (after the
`app.xml` fix below) five Google/Keynote decks. The seven rows below still need real PowerPoint saves.

| Deck | What PowerPoint did after Repair | Helper that wrote the bad XML |
| --- | --- | --- |
| `C007-comments` | Comments kept but rewritten: the legacy `comment1.xml` converted to modern, `modernComment_N.xml` renamed `modernComment_<id>_0.xml`, `commentAuthors.xml` replaced | `kit.legacy_comment`, `kit.modern_comment` |
| `C007-resolved-only` | Same; the resolved thread's author shows as "Unknown User" (the author list didn't match) | `kit.modern_comment` |
| `F002-alias-in-smartart` | Diagram parts kept, but the SmartArt draws nothing: the slide is blank | `decks._smartart` |
| `R-rich-objects` | Ink removed (`ppt/ink/ink1.xml`, the `p14:contentPart`), and the SmartArt draws nothing. Chart, merged table and equation survive (PowerPoint renames the chart's workbook on save, as it does for any deck) | `decks._smartart`, `_INK` |
| `NEW-11-audio-across-slides` | The audio is removed from slide 1 (its `p:video` timing node goes with it) | `kit.as_audio` (writes the timing as `p:video` for a sound) |
| `M002-audio-trim-mute` | Opens fine, then prompts a few seconds later (when the media loads), every time; the late prompt blocks every later open | `kit.as_audio`, maybe `kit.media_trim` |
| `NEW-23-transition-sound-linked` | Transition sound removed (`p:sndAc` / `p:stSnd` / `p:snd`) | `transition(...)` with an external audio rel |

Not a reject, by design: `R-render-safety` is a `.pptx` holding a VBA project. PowerPoint refuses to open it at
all ("a macro-free file … contains VBA"). The engine's render copy strips macros first (`deck.render_safe`).

Opened cleanly: P001 ×3, P002, X003-ole-objects, X004-local-links, NEW-04, NEW-05, NEW-21, KS-canva-mess,
KS-office2010-mess. ("Opens cleanly" isn't proof the XML is what PowerPoint would write: NEW-04 and NEW-05 are
still to be replaced by real saves, per CLAUDE.md.)

## Fixed in round 2: empty `<AppVersion>` (22 decks)

`kit.google()` and `kit.keynote()` wrote `docProps/app.xml` with an empty `<AppVersion></AppVersion>`. PowerPoint
asks to repair any deck like that, so every Google- and Keynote-style deck prompted (found on
`L001-wider-on-windows` in the layout run, then `L010-overlap-cases`). Tested in PowerPoint on copies of
L001-wider-on-windows: `AppVersion` filled in opens cleanly, empty prompts, left out opens cleanly. `kit.set_app`
now leaves the element out when the version is empty (X001 reads only `<Application>`). The 22 committed decks got
the new `app.xml` and nothing else; L010, L009, G004, X001-fingerprints-keynote and L001-wider-on-windows were
re-opened in PowerPoint afterwards: all clean. L010's click animations were never the problem.

## What this means for the engine (separate from the decks)

When PowerPoint repairs a render copy, the engine can't tell. On the Mac the repaired deck's name becomes
"<name> - Repaired", so the export script's path check fails with `Can't get full name of missing value`
(seen on C007-comments: 197 s, then "Layout fixes skipped"). That's the safe outcome, but the warning isn't
crew-readable, the run waited on a dialog nobody could see, and the hidden copy became a visible window.
Two more, from the layout run:
- The repaired copy stays open after the engine gives up ("<name> - Repaired"); `cli cleanup` and the next
  engine don't close it either, because the name no longer matches.
- Clicking **Cancel** instead of Repair made the engine report "PowerPoint stopped responding", and the next
  engine process said the same, so the following deck lost its layout pass too. See
`docs/ADVERSARIAL_RESULTS.md`, round 2.
