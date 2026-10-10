# Handoff: Mac → PC (2026-10-10)

For Claude Code on David's Windows PC. Read `CLAUDE.md` and `SPEC.md` first; this file covers
where things stand and what the PC is for. Delete or rewrite this file when it goes stale.

## Where things stand

- **v0.4.0 released** (tag `v0.4.0`, commit `13cd730`): first CI release of the desktop app.
  - Mac: signed + notarized DMG and ZIP built in CI. Not yet installed on a real machine.
  - Windows: unsigned NSIS installer, `SlideTistic-Setup-0.4.0.exe` on the Releases page. **Never run by a person.**
  - CI green on both. The first run split its uploads across two v0.4.0 releases (fixed in the workflow);
    the Windows files were copied into the published release by hand, so it now has all eight files.
  - First Windows CI test run: 992/994; the 2 failures were tests reading UTF-8 files as cp1252 (fixed).
- **Repo is public** (needed for electron-updater). Client decks never go in git: `corpus/` is ignored.
- **Signing secrets** are set on the repo (all five). Nothing to do there.
- **Windows scope today:** fonts, geometry, media, playback and content checks + fixes. **No layout fixes
  and no visual review on Windows**: both need PowerPoint to render the deck, and only the Mac
  (AppleScript) renderer exists. The engine switches them off by itself when no renderer is available.
- Known bug in the **0.4.0 Windows build only**: video length/codec missing (temp file held open while
  ffprobe read it; Windows blocks that). Fixed on `main` after the tag; ships in 0.4.1.

## What the PC is for

1. Test the installed Windows app (checklist below).
2. Save Windows PowerPoint versions of the test decks: the "never guess PowerPoint XML" rule needs both
   Mac and Windows saves, and there's no other Windows machine.
3. Run the engine's test suite on Windows for the first time.
4. Later (phase 4): the Windows PowerPoint renderer (COM automation) to bring layout fixes and visual
   review to Windows. Show machines are mostly PCs, so this is the biggest gap.

## Setup on the PC

Claude Code on Windows runs commands in Git Bash. Paths below are Git Bash style.

```bash
git clone https://github.com/Horton619/slidetistic.git
cd slidetistic
py -3.11 -m venv venv                              # Python 3.11 from python.org, matches CI
venv/Scripts/pip install -r requirements.txt
venv/Scripts/python -m pytest -q                   # first ever Windows run; failures are findings, not blockers
npm ci                                             # then `npm start` runs the app in dev
```

- **ffprobe (dev only):** the installed app ships its own. For dev, point the engine at it:
  `export SLIDETISTIC_TOOLS="/c/Program Files/SlideTistic/resources/tools"` (adjust to the install
  folder), or put any ffprobe on PATH. Without it, video length/codec are just blank.
- **Electron install trap (seen on the Mac):** newer npm may skip Electron's download step. If
  `npm start` says "Electron failed to install correctly", run `node node_modules/electron/install.js`;
  if that silently does nothing, see the memory note on unzipping the cached Electron by hand.
- Claude's memory notes from the Mac (four small files) go in
  `C:\Users\<you>\.claude\projects\<this project's folder>\memory\`. Open Claude Code in the clone once
  so that folder exists, then copy them in.

## Test checklist: installed Windows app (0.4.0)

Install from the Releases page. It's unsigned, so SmartScreen will warn: **More info → Run anyway**.
Log file for anything odd: `%APPDATA%\SlideTistic\slidetistic.log` (also Settings → Diagnostics).

- [ ] Launches; the queue and drop zone appear; Settings opens (all four tabs).
- [ ] Drop a single deck → it scans; findings and the Canva/Google banner look right.
- [ ] Drop a folder → every deck inside is queued; ✕ removes one.
- [ ] A `.key` or a broken file gets a red ✕ card with a plain explanation.
- [ ] Repair → "Deck - mended.pptx" appears next to the original; repairing again makes "(2)".
      **The original must be untouched.**
- [ ] Open the mended deck in **Windows PowerPoint**:
  - [ ] Fonts look right; Mac-only fonts (Avenir etc.) were swapped.
  - [ ] **A video that was "When Clicked On" now plays on a clicker/arrow press** in Slide Show. This
        conversion has only been verified in Mac PowerPoint; this is the most important check.
  - [ ] Nothing else changed that shouldn't have.
- [ ] Review tab: shows a note that the visual review needs PowerPoint for Mac (expected on Windows).
- [ ] Media tab: videos listed (lengths blank in 0.4.0, see known bug); CSV/Excel export saves.
- [ ] Watch folder (Settings → General): drop a deck in the folder → it's scanned automatically.
- [ ] "SlideFluid ↗" button: opens SlideFluid if it's in its default install folder
      (`%LOCALAPPDATA%\Programs\slidefluid`), otherwise says it isn't installed.
- [ ] Settings → Diagnostics → Check for updates: says "You have the latest version" (until 0.4.1 exists).

## Then: the updater test (do together with Claude on the Mac or PC)

Ship 0.4.1 (contains the Windows ffprobe fix): bump `package.json`, commit, tag `v0.4.1`, push. Wait for
CI plus ~5 min. Start the installed 0.4.0. Within ~60 s it should download 0.4.1 and show the
"ready, restart" banner; Restart → app relaunches as 0.4.1 and video lengths now appear. Same test on
the Mac with the DMG install. If anything fails, the raw updater error shows in Settings → Diagnostics.

## Windows PowerPoint saves to make

From `docs/BROKEN_DECK_RECIPE.md`: build `broken_win.pptx` in **Windows** PowerPoint (or open the Mac
`broken_mac.pptx`, redo the video/animation settings on Windows, and Save As). Highest value, because
Windows saves the timing XML its own way: items 01–09 (video start modes, rewind, loop, trim, mute,
audio), 13–16 (auto-advance, click advance, click animations, trigger), 27 (comments). Copy decks
into the local `corpus/` folder; never commit them.

Still unbuilt on the Mac deck too: slides 9–16, 27, 31–33, plus the `broken_showsettings` copy.

## Open questions for David (carried over)

- Slide 35 "huge photo, small": M008 ignores photos under 2 MB (this one is 0.78 MB). Flag smaller ones?
- Noisy checks: M009 (stretched logos), X003 (embedded objects), M008, M011, G003 grouping, small L011
  overlaps: keep, tone down, or hide?
- Accept the corpus snapshot diffs (Downloads + Dropbox) so later changes are measured against them.
- Fun-skin taglines: pick a rotation list (the Pro skin is now "PowerPoint is my special interest.").

## Next build work (suggested order)

1. Windows PowerPoint renderer (COM): PowerPoint → PDF on Windows, then the same Poppler path.
   Needs Poppler bundled for Windows too (SlideFluid's workflow downloads a Windows Poppler build).
2. P005 click map (needs saved decks with click animations from Mac and Windows).
3. Faster layout repair (~80 s per deck now).
4. C007 "remove comments" fix, F009 Google-font downloader, move the release workflow off
   deprecated Node 20 GitHub actions (warning only today).
5. Keynote conversion.
