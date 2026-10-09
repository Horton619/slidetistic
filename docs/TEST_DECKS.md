# Test decks to collect

Real decks go in the local corpus folder (`corpus/` in this repo is git-ignored, so client decks
never get committed). For each deck, a one-line note helps a lot: where it came from, what was
wrong when it opened, and what you fixed by hand. **A before/after pair (original + your hand-fixed
copy) is worth five unfixed decks**: it's the answer key the promotion rule (SPEC §8) measures against.

File naming suggestion: `<source>_<short-name>.pptx`, plus `<source>_<short-name> - handfixed.pptx`
when you have one. Example: `canva_pat-mbd.pptx`, `canva_pat-mbd - handfixed.pptx`.

## Priority 1: needed for phases 1–2 (fonts, geometry)

| # | What to find | Source | Feeds |
|---|---|---|---|
| 1 | **The PAT MBD deck + its MacFix version** | Canva | F001–F008, G001, L001. Phase 1 can't be signed off without it |
| 2 | 2–3 more Canva exports, ideally with different fonts (not just Calibri) | Canva | F001, F002, F005 |
| 3 | A Canva deck using a **Canva-only font** (Canva Sans, or anything from Canva's own library) | Canva | F004 |
| 4 | A deck with weights beyond Bold: **SemiBold, Medium, Light, Black, Thin** | Canva or Google | F003 |
| 5 | 2–3 **Google Slides** downloads (File → Download → .pptx), one with lots of text | Google | Fingerprint, L004, L005 |
| 6 | A deck using a **free Google font not on your Mac** (Montserrat, Poppins, Lato…) | Any | F007, F009 |
| 7 | A deck using a **paid font** (Adobe, Monotype) | Any | F007 (the "get it from the client" message) |
| 8 | Any deck where **text hangs off the slide edge** | Any | G001, G002 |
| 9 | A deck with **images deliberately bleeding off the edge** (full-bleed photos) | Canva | G001 must NOT flag these |
| 10 | A deck with **grouped text** (title + subtitle grouped, text inside grouped graphics) | Canva | G004, group geometry |
| 11 | A deck with **rotated or flipped text** | Any | G003 |
| 12 | A **known-good native PowerPoint deck** that should come back clean | PowerPoint | False-positive guard |

## Priority 2: Playback and Media (phase 2)

| # | What to find | Feeds |
|---|---|---|
| 13 | A deck with **auto-advancing slides** (timed advance), ideally one meant to loop and one not | P001 |
| 14 | A deck set to **kiosk / loop until Esc** | P003 |
| 15 | Decks with **embedded video**: one MP4, and anything odd (MOV, WMV, very large) | M002, M004 |
| 16 | A deck with **linked (not embedded) video** whose file is missing | M003 |
| 17 | A deck with **trimmed video** and one with **audio** | M002 |
| 18 | A Canva or Google deck with video: how do their exports encode it? | M001 `no_timing` |

## Priority 2b: content and links (added 2026-10-09)

| # | What to find | Feeds |
|---|---|---|
| 20 | A **Google Slides deck with an inserted YouTube video**, downloaded as .pptx | M005 (how Google really encodes it) |
| 21 | A PowerPoint deck with an **"Online Video"** inserted (Insert → Video → Online) | M005 |
| 22 | Decks with **video links in the speaker notes** ("play this: https://…") | M006 |
| 23 | An **unfinished template deck**: "Click to add…", "Lorem ipsum", "[Speaker name]", "VIDEO HERE" slides | C001, C002 |
| 24 | A deck with **hidden slides** and one with **review comments** left in | C004, C007 |
| 25 | A deck with a **linked Excel chart** (linked, not embedded) from someone's PC | X004, X003 |
| 26 | A deck with a **huge phone photo** shown small, and a **tiny logo** stretched full-screen | M008, M009 |
| 27 | A deck with **click animations** (several builds per slide), saved from PowerPoint on Mac **and** Windows | P005 (click map) |

## Priority 3: Keynote (after the core loop works)

| # | What to find | Feeds |
|---|---|---|
| 19 | 2–3 **`.key` files**, plus PowerPoint exports of them that broke | Keynote conversion checks |

## Things I'll build in PowerPoint myself (Mac), you don't need to find these

- **Video play-mode reference decks** (SPEC §7.3): one slide each set to Automatically, In click
  sequence, When clicked on, and no timing. I can build the Mac versions on this machine.
- **The Windows versions are still needed.** Without a Windows PC with PowerPoint, someone has to
  make the same four slides on a show PC. I'll prepare a tiny starter deck with exact steps when we
  get there.

## Not useful

- Decks that are only pictures (e.g. PDF-to-PPTX conversions from SlideFluid). Those are already
  covered by code-built fixtures.
