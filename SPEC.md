# SlideTistic — Build Spec (v0.1)

> Working name. A companion app to SlideFluid that scans Canva / Google Slides / Keynote decks
> for problems that break in PowerPoint, fixes what it safely can, and reports the rest in
> green / yellow / red.
>
> Owner: David Horton (AVSC / Visual Entropy Productions) · Spec date: 2026-10-06
> Audience: Claude Code. Read `CLAUDE.md` first; it holds the working rules for this repo.

---

## 1. What we're building

A desktop app (Apple Silicon Mac + Windows x64; no Intel Mac builds) where a crew member:

1. Drags a `.pptx` onto the window.
2. The app **scans** it right away, without changing anything, and shows what it found.
3. The user reviews the **options panel** (which checks to run and which fixes to apply), adjusts if needed.
4. Clicks **Repair**. The app writes a new file next to the original and **re-scans the result**.
5. Sees a **summary**: what was fixed, what may need a look, what is still broken, by slide and shape.

Original files are never modified.

### Why it exists (evidence so far)

From one real Canva deck (PAT MBD, 29 slides) that was "very broken" on Mac and nearly fine on PC:

| Problem | Detail | Fix that worked |
| --- | --- | --- |
| Fake font names | 176 of ~210 runs used `Calibri (MS)` / `Calibri (MS) Bold`; every weight embedded as its own fake family in the "regular" slot | Rename to real families + bold flag; rebuild embedded-font list |
| Zero-slack boxes | Titles 13.85" wide in a 13.81" box, 14.01" in 13.99" | Widen, keeping centered |
| Text box off-slide | Body box at x = −0.56" | Move inside slide |

Prototype scripts that did these fixes are in `reference/`. They are reference material, not the architecture: port their logic into checks (§5).

**Premise caveat:** everything above comes from one deck. Most checks in §7 are expected, not yet seen; the PAT deck had no video, timing or transitions, so every Playback and Media check needs new test decks. The build is designed so that is fine: checks are cheap to add, and each is validated against real decks before it is allowed to auto-fix.

---

## 2. Non-negotiable product rules

1. **Never modify the original file.** Output is `<name> - mended.pptx` in the same folder (configurable), plus a report.
2. **Scan never mutates.** Detection runs on a read-only view.
3. **Fit fixes go in a fixed order** (changed by David 2026-10-10): move/resize the box first, then tighten line spacing (floor `fit_min_line_spacing_pct`), then shrink the font as a last resort (cap `fit_max_font_shrink_pct`). Every fit change is shown in the review page.
4. **Images are allowed off-slide.** Off-slide checks apply to text-bearing shapes only.
5. **Green means verified.** A finding is "fixed" only if a re-scan after the fix no longer detects it.
6. **One check failing never stops a run.** It becomes a tool-error entry in the report.
7. **Every change is logged** with before/after values, so the report can show it and the UI can undo it.

---

## 3. Stack (mirror SlideFluid)

| Layer | Choice | Notes |
| --- | --- | --- |
| Engine | Python 3.11+, `python-pptx` + `lxml` for XML-level edits, `fontTools` for font files | Standalone CLI, testable without the UI |
| Engine ↔ UI | Subprocess + JSON-lines events on stdout | Same pattern as SlideFluid's `ConversionJob` |
| UI | Electron, `contextBridge` preload exposing `window.slidetistic`, unsubscribe-pattern listeners | Same as SlideFluid |
| Packaging | PyInstaller for the engine, electron-builder for Mac DMG + Windows NSIS | Same dev vs packaged path resolution as SlideFluid |
| PowerPoint bridge (phase 4+) | Windows: COM via `pywin32`. Mac: `osascript` (AppleScript), possibly calling a VBA routine | See §6. Mac is the riskiest piece; spike it early |
| Tests | `pytest`, fixture decks generated in code | §8 |

---

## 4. UX

### 4.1 Screens

**A. Drop screen.** A large drop zone ("Drop a deck to check it"), plus "Browse…". Accepts `.pptx` (`.ppt`, `.key`: refuse with a clear message). Multiple files → queue, one result card each.

**B. Results screen** (appears as soon as the scan finishes; SlideFluid-style split pane):

- **Header:** file name, detected source ("Looks like a Canva export"), slide count, whether the PowerPoint layout check is available on this machine.
- **Summary bar:** three counts with color + icon + word (never color alone):
  - 🟢 **Good / fixed** — `✓`
  - 🟡 **May need a look** — `!`
  - 🔴 **Still broken** — `✕`

  Before repair, the bar shows what was found. After repair: "12 fixed · 3 to look at · 1 still broken".
- **Left pane, options:** checks grouped (Fonts, Geometry, Layout fit, Playback, Media, Other). Each row has the check name, a one-line description, a count of findings, and two toggles: **Check** (run it) and **Fix** (apply its fix). Fix is disabled for report-only checks. A **source preset** dropdown (Canva / Google Slides / Other) sets defaults from the detected source; user changes stick per preset.
- **Right pane, findings:** grouped by slide ("Slide 22 · TextBox 6"), each with status color, message, and evidence ("text 13.85 in, box 13.81 in"). Filter chips: All / Red / Yellow / Green. Click a finding → detail drawer with before/after values and **Open in PowerPoint at this slide** (when the bridge is available).
- **Media tab** (beside Findings): the media inventory table (§7.4), with **Export CSV / XLSX**.
- **Get fonts button:** appears in the summary bar when F009 finds downloadable missing fonts ("4 missing fonts can be downloaded"). Shows the list and licenses before installing.
- **Primary button:** **Repair** (applies enabled fixes). Secondary: **Export report**.

**C. After repair:** the same results screen, re-scanned, plus "Saved: <path>" with **Show in Finder/Explorer**, **Open in PowerPoint**, and **Undo a change** per finding (re-runs repair without that fix).

**D. Settings modal:** output folder rule, file suffix, default preset, PowerPoint bridge on/off + **Test connection**, crew font inventory (a list of fonts installed on show machines, used by F007), target video play mode (default Automatically), allow network for font catalog and downloads (on/off), preflight (Python engine found, PowerPoint found, ffprobe found, permissions on Mac).

### 4.2 Status color rules (engine decides, UI only displays)

| Status | Meaning | Examples |
| --- | --- | --- |
| `green_clean` | Check ran, nothing found | Counted in summary, not listed per item |
| `green_fixed` | Problem found, fixed, and re-scan confirms it is gone | Font renamed; off-slide text moved inside |
| `yellow` | Possible problem, or fixed-but-unverifiable, or needs a human choice | Fit measured by estimate only; "Montserrat SemiBold" may be a real family; slide 22 text moved 0.9 in, check visually |
| `red` | Confirmed problem not fixed (fix off, refused, or failed) | Font missing on show machines; text off-slide with fix disabled |
| `tool_error` | A check crashed | Listed separately: "This check couldn't run on slide 9" |

**Confidence rule:** any finding whose evidence comes from the font-metrics estimate rather than PowerPoint is at most `yellow`.

### 4.3 Report

A self-contained HTML file (`<name> - mended report.html`) with the summary, all findings, the media inventory, all changes (before → after), the checks that ran and their settings, the engine version, and whether the PowerPoint bridge was used.

---

## 5. Architecture: built for "oh, and add a check for ___"

The whole design aims at one property: **adding a check is adding a file, never editing a list.**

```
slidetistic/
  engine/
    cli.py                 # scan / repair / list-checks commands, JSON-lines output
    core/
      deck.py              # Deck model: loads pptx, slides, shapes, absolute geometry
      shapes.py            # classify(): text_box | placeholder | picture | table | group | connector | other
      geometry.py          # group-transform math (chOff/chExt), rotation, slide bounds
      edits.py             # EditSession: the ONLY way checks change the deck; logs every change
      findings.py          # Finding, Status, Evidence dataclasses
      registry.py          # auto-discovers checks; orders them by declared dependencies
      runner.py            # scan → plan → apply → re-scan → summarize; isolates check failures
      fingerprint.py       # detects source (Canva, Google, Keynote, PDF-converted, native)
      layout/
        base.py            # LayoutProvider interface
        estimate.py        # fontTools metrics estimate (confidence: low)
        pptx_win.py        # PowerPoint via COM (confidence: high)
        pptx_mac.py        # PowerPoint via AppleScript (confidence: high)
    checks/
      fonts/   F001_weight_in_family_name.py, F002_canva_font_alias.py, ...
      geometry/ G001_text_off_slide.py, ...
      layout/  L001_single_line_wrapped.py, ...
      playback/ P001_auto_advance.py, ...
      media/   M001_video_play_mode.py, M002_media_inventory.py, ...
      other/
      _template.py         # copy this to start a new check
    rules/                 # DATA, not code: edits here need no code change
      font_aliases.yaml    # "Calibri (MS)": "Calibri"
      office_fonts.yaml    # fonts that ship with Office on Mac + Windows
      canva_only_fonts.yaml
      weight_suffixes.yaml # Bold → b=1; SemiBold/Light/Black → flag only
      thresholds.yaml      # margins, headroom %, tolerances
      presets.yaml         # per-source default toggles
      font_licenses.yaml   # licenses allowed for auto-download
    services/
      fonts_catalog.py     # Google Fonts list: fetch, cache, lookup
      fonts_install.py     # per-user install on Mac / Windows
      media_probe.py       # ffprobe wrapper (duration, codec, size)
  app/                     # Electron (main.js, preload.js, renderer/)
  tests/
    fixtures/builders.py   # helpers that generate tiny decks in code
    checks/test_F001_*.py  # one test file per check
    test_contracts.py      # runs automatically against EVERY registered check
    test_corpus.py         # snapshot tests on real decks (local only, not in git)
  reference/               # prototype scripts from the PAT deck investigation
  docs/EDGE_CASES.md       # running log of every "oh by the way"
  CLAUDE.md
```

### 5.1 The check contract

Every check is a class in its own file:

```python
from engine.core import Check, Finding, Status, Evidence

class WeightInFamilyName(Check):
    id = "F001"
    title = "Weight in font name"
    group = "fonts"
    description = "Font names like 'Roboto Bold' that Mac PowerPoint can't resolve."
    default_check = True
    default_fix = True
    sources = ["canva", "google", "any"]   # which presets enable it by default
    requires = []                           # e.g. ["layout"] if it needs a LayoutProvider
    runs_after = []                         # check ids that must run first
    version = 1

    def detect(self, deck, ctx) -> list[Finding]:
        ...  # read-only; never edits

    def fix(self, deck, finding, edits, ctx) -> None:
        ...  # all changes through `edits`; raise FixRefused("reason") to decline
```

Rules every check follows:

- `detect` is pure: same deck in, same findings out, no edits.
- `fix` changes **only** the shapes/parts named in its finding, and only through `EditSession` (`edits.set_geometry(...)`, `edits.set_run_font(...)`, `edits.replace_part(...)`).
- Fixes must be **idempotent**: running repair twice changes nothing the second time.
- Tunable numbers come from `rules/thresholds.yaml`, never literals in code.
- A check that needs real layout declares `requires = ["layout"]`. If only the estimate provider is available, it still runs, but its findings cap at `yellow`.

### 5.2 Runner flow

1. **Load + fingerprint** the deck.
2. **Scan:** run every enabled check's `detect` in dependency order. Catch exceptions per check → `tool_error`.
3. **Plan:** collect fixable findings for checks with Fix on. The `EditSession` refuses two fixes touching the same property of the same shape in one pass (`conflict` → `yellow`, reported).
4. **Apply** in dependency order (fonts before geometry before layout: font changes alter every later measurement).
5. **Write** the output file.
6. **Re-scan** the output with all enabled checks. Findings that disappeared → `green_fixed`. Still there → `red`. Newly appeared (a fix caused a problem) → keeps the check's own severity, with "introduced by <check>" (changed 2026-10-10: an orphan caused by a font fix is a yellow, not an emergency).
7. **Emit** summary + report.

### 5.3 Engine CLI and events

```
slidetistic scan   <file> [--preset canva] [--checks F001,G001] [--json]
slidetistic repair <file> [--preset canva] [--fix F001,F002] [--out <path>] [--json]
slidetistic list-checks --json          # UI builds the options panel from this
slidetistic preflight --json
slidetistic media <file> --csv|--xlsx|--json   # media inventory only
slidetistic fonts get <file> [--install]       # download (and install) missing free fonts
```

JSON-lines events: `{"type":"progress",...}`, `{"type":"finding",...}`, `{"type":"change",...}`, `{"type":"summary",...}`, `{"type":"error",...}`. The UI renders the options panel from `list-checks`, so **a new check shows up in the UI with zero UI code**.

---

## 6. LayoutProvider (how fit is measured)

Only PowerPoint knows how PowerPoint lays out text. Checks never measure on their own; they ask `ctx.layout`.

```python
class LayoutProvider:
    name: str
    confidence: Literal["high", "low"]
    def measure(self, slide_index, shape_id) -> Measurement: ...
    # Measurement: line_count, text_bounds (left, top, width, height) in EMU, per-paragraph line counts
```

| Provider | When | Confidence |
| --- | --- | --- |
| `pptx_win` | Windows with PowerPoint installed; opens a temp copy via COM, reads `TextFrame2.TextRange.BoundLeft/Top/Width/Height` and the line count | high |
| `pptx_mac` | Mac with PowerPoint; drives it with AppleScript (may need a small VBA helper). Needs macOS Automation permission | high |
| `estimate` | Always available; fontTools advance widths + greedy wrap, no kerning | low |

**Spikes before building on this (phase 4):**

- Windows: confirm COM returns laid-out bounds and line counts for a temp copy, headless or minimized, in under ~0.5 s per slide.
- Mac: confirm AppleScript can get the same values from Mac PowerPoint. If it can't, fall back to a `.ppam` add-in the app installs, or ship Mac as estimate-only (all fit findings yellow). Decide after the spike; don't build around a guess.

Known: the estimate provider over-flagged badly on the PAT deck (about 30 flags for 2 real problems). It is a fallback, not a decision-maker.

---

## 7. Initial check catalog

Status column: **Seen** = present in the PAT deck; **Expected** = needs a fixture and a real deck to confirm.

| ID | Check | Detect | Fix | Default | Evidence |
| --- | --- | --- | --- | --- | --- |
| F001 | Weight in font name | Typeface ends `Bold`/`Italic`/`Bold Italic` and base family exists | Strip suffix, set `b`/`i` | Check + Fix | Seen |
| F002 | Canva font alias | Typeface in `font_aliases.yaml` | Map to real family | Check + Fix | Seen |
| F003 | Other weight names | `SemiBold`, `Medium`, `Light`, `Black`, `Thin` suffixes | None (may be real installed families) | Check only → yellow | Expected |
| F004 | Canva-only font | Typeface in `canva_only_fonts.yaml` | None; suggest substitute | Check only → red | Expected |
| F005 | Embedded font list mismatched | Declared embed name ≠ family inside the font file, or wrong slot | Rebuild list with real names + slots | Check + Fix | Seen |
| F006 | Redundant embed of Office font | Embedded family in `office_fonts.yaml` | Drop the embed | Check + Fix | Seen |
| F007 | Font missing on show machines | Used family not embedded, not Office, not in crew inventory | None; install link | Check only → red | Expected |
| F008 | Embed licence forbids embedding | fsType restricts embedding. (MTX compression dropped 2026-10-09: PowerPoint compresses every embed) | None; recommend install | Check only → yellow | Corpus |
| G001 | Text off-slide | Text-bearing shape's absolute bounds cross the slide edge (pictures exempt). With layout: confirm the **laid-out text** crosses, not just the box | Shift inside, 0.2 in margin; refuse if wider than slide | Check + Fix | Seen (slide 22) |
| G002 | Text below slide bottom | Bottom of text-bearing shape > slide height | None | Check only → yellow | Seen (slide 22, 0.11 in) |
| G003 | Rotated / flipped text | `rot` or flips on a text-bearing shape | None; excludes it from other fixes | Check only → yellow | Expected |
| G004 | Text inside groups | Text-bearing shape inside a group | None in v1 (fixes inside groups deferred) | Check only, informational | Seen |
| L001 | One-line text wraps | Laid-out line count > design line count (§7.1) | Widen by alignment (§7.2) | Check (Fix after validation) | Seen (slides 5, 24) |
| L002 | Text overflows bottom | Laid-out text height > box height | Grow height by anchor | Check (Fix after validation) | Expected |
| L003 | Unwrapped text overflows sideways | `wrap="none"` and laid-out width > box width | Widen by alignment | Check (Fix after validation) | Expected |
| L004 | Stale autofit (Google) | `normAutofit` with `fontScale`/`lnSpcReduction` | Turn autofit off, then L001–L003 apply | Check only until tested | Expected |
| L005 | Percentage line spacing | `lnSpc/spcPct` | Convert to exact points at current size | Check only until tested | Expected |
| L006 | Fix created overlap | After fixes, a grown text box intersects another shape it didn't before | Revert that change | Always on | Expected |
| L007 | Table cell overflow | Cell text height > row height | None | Check only → yellow | Expected |
| X001 | Source fingerprint | Canva / Google / Keynote / PDF-converted / native | None; sets preset | Always on, informational | Seen (Canva) |
| F009 | Missing font is freely downloadable | F007 font found in the Google Fonts catalog (§7.5) | **Get fonts** button: download + install for this user | Check on; install only on button press | Expected |
| P001 | Slide auto-advances | `p:transition` has `advTm` (advance after a time) | Remove the timed advance, keep click advance | Check (Fix off by default; may be an intended loop) → yellow | Expected |
| P002 | Click advance disabled | `p:transition advClick="0"` with no timed advance (slide can get stuck) | Re-enable click advance | Check + Fix → red if found | Expected |
| P003 | Deck set to kiosk / loop mode | `presProps.xml` show settings: kiosk, loop until Esc | None | Check only → yellow | Expected |
| M001 | Video won't start from the clicker | Play mode "When clicked on" or no start setting (§7.3). "In click sequence" and "Automatically" are fine | Convert to "In click sequence" (needs a PowerPoint-saved "When clicked on" fixture first) | Check → red/yellow | Corpus |
| M002 | Media inventory | Every video/audio on every slide (§7.4) | None; produces the media list | Always on, informational | Expected |
| M003 | Linked media missing | Media relationship is external (`TargetMode="External"`) or the target file isn't in the package | None | Check only → red | Expected |
| M004 | Video format risky on Mac/PC | Container/codec PowerPoint on the other platform may not play (e.g. WMV on Mac) | None; suggest MP4 (H.264/AAC) | Check only → yellow | Expected |

### 7.1 Design line count (key heuristic for L001)

With auto-fit on, Canva saves a text box at the text's own height, so the box records how many lines the designer saw:

`design_lines = floor((box_height − top_inset − bottom_inset − paragraph_spacing) / line_pitch)`

PAT slide 5: box 98.75 pt, exact pitch 91 pt → 1 line. Valid only when line spacing is exact points (`spcPts`), as in Canva. Google decks use percentages; L001 must not trust this rule there (report `yellow`, or use L005 first).

### 7.2 Grow rules (all values in `thresholds.yaml`)

| Text setting | Grow width | Grow height |
| --- | --- | --- |
| Centered / middle-anchored | Both sides equally | Up and down equally |
| Left / top-anchored | Right | Down |
| Right / bottom-anchored | Left | Up |
| Justified | Right | — |

- Slide margin: 0.2 in. A centered box that hits the margin may shift up to 0.25 in; beyond that, refuse → `yellow`.
- Width headroom: laid-out width + 6% (a judgment value; tune from the corpus).
- Single-line (title) boxes may widen to the slide margin. Multi-line body text widens at most 10%, then grows in height instead.
- Height headroom: laid-out height + half a line.

### 7.3 Video play modes (M001)

PowerPoint stores "Start: Automatically / In click sequence / When clicked on" in the slide's timing tree (`p:timing`), not on the video shape. **The exact XML for each mode must be captured from real PowerPoint saves before coding.** Don't write the detector from memory.

Required first step (phase 2): in PowerPoint on Mac and on Windows, build one slide per mode (Automatically, In click sequence, When clicked on, plus "no timing at all", which is how some Google/Canva exports arrive). Save, unzip, and record the `p:timing` signature of each as fixtures in `tests/fixtures/media_modes/`. Then:

- Detector: classify each video as `automatic`, `click_sequence`, `on_click_trigger`, `no_timing`, or `unknown` (unknown → yellow, never guessed).
- Fix: rewrite to the target mode from settings (default **Automatically**). Fix stays off by default until it round-trips: fixed deck opened in PowerPoint on both platforms shows "Automatically" and the video plays on slide entry.
- Also report per video: Loop until stopped, Rewind after playing, Play full screen, Hide while not playing, start/end trim. These come from the same timing tree and the `p14:media` extension.

### 7.4 Media inventory (M002)

Always produced, shown in a **Media** tab and included in the report. Exportable as CSV, and as XLSX (columns sized so all text is visible, no wrapping into neighboring cells).

| Column | Source |
| --- | --- |
| Slide # | Slide order |
| Slide name | `p:cSld@name` if set; else the title placeholder text; else the first text on the slide (trimmed to 60 chars); else "Slide N". Canva decks usually have no title placeholders, so the first-text fallback matters |
| Media name | Shape name + file name inside the package (`ppt/media/media3.mp4`) |
| Type | Video / audio |
| Duration | Full file duration via bundled `ffprobe` (falls back to `pymediainfo`) |
| Trimmed duration | Duration after PowerPoint start/end trim, when trimmed |
| Play mode | From M001 |
| Loop / rewind / full screen / hidden | From timing + `p14:media` |
| Embedded or linked | Linked + missing = red (M003) |
| Container / codec / resolution / size (MB) | `ffprobe` |
| Mac/PC risk | From M004 |

Totals line: number of videos, total runtime, total media size.

### 7.5 Missing-font resolver (F009)

- **Catalog:** the Google Fonts family list, cached locally and refreshed weekly when online (source: the official Google Fonts API or the `google/fonts` GitHub repository metadata; pick in phase 2 and record why). The app works offline with the last cached list.
- **Match:** exact family-name match after F001/F002 normalization ("Roboto Bold" → Roboto). No fuzzy matching; near-misses are reported as suggestions only.
- **Get fonts button** (results screen and the finding detail): downloads the needed families and weights from Google's official source only, then installs **for the current user** (no admin rights):
  - Mac: copy to `~/Library/Fonts`.
  - Windows: per-user install (`%LOCALAPPDATA%\Microsoft\Windows\Fonts` + the `HKCU` font registry entry), supported on Windows 10 1809 and later.
  - After install: re-scan; F007/F009 findings for those fonts turn green. Tell the user PowerPoint must be **restarted** to see new fonts.
- **Licensing:** only fonts whose catalog license is OFL, Apache 2.0 or UFL. Never download from third-party font sites. Commercial fonts (Adobe, Monotype, etc.) are reported with their name and "licensed font, get it from the client".
- **Optional, phase 4+:** embed the installed fonts into the mended deck via the PowerPoint bridge (save with embedded fonts), so the deck works on machines without the install.

---

## 8. Testing: how new checks avoid breaking old ones

Three layers, all in CI (`pytest`):

1. **Per-check fixtures.** Every check ships with at least one deck where it **should** fire and one where it **should not**, built in code by `tests/fixtures/builders.py` (e.g. `make_deck(text_box(x=-0.5, text="hi", font="Roboto Bold"))`). Each edge case gets its own named fixture.
2. **Contract tests**, run automatically against every registered check, with nothing to write per check:
   - `detect` does not modify the deck.
   - `fix` is idempotent (second repair = zero changes).
   - `fix` touches only shapes in its findings.
   - No crash on: empty deck, all-picture deck, groups, nested groups, rotated shapes, tables, placeholders, notes-only text, non-Latin text, a 4:3 deck, a 10 × 5.625 in (Google) deck, a 20 × 11.25 in (Canva) deck.
   - Metadata valid: unique id, group known, thresholds referenced exist in `thresholds.yaml`.
3. **Corpus snapshots.** Real decks in a local folder (path in settings, not in git: client content). `pytest -m corpus` scans each, compares findings to a saved snapshot, and prints a diff. A new check shows exactly what it adds across every real deck; an unexpected change in another check fails the run until the snapshot is reviewed and accepted (`--update-snapshots`).

**Promotion rule:** a fix's default stays off until, on the corpus, it catches 90%+ of hand-fixed problems, produces under 1 false flag per deck, and makes zero slides worse.

---

## 9. Build phases

Each phase ends with something usable. Do not start a phase until the previous one's tests pass.

| Phase | Deliverable | Done when |
| --- | --- | --- |
| 0 | Engine skeleton: Deck model, geometry (with groups), EditSession, registry, runner, CLI, contract tests, `_template.py` | `slidetistic list-checks` works; contract tests run on a dummy check |
| 1 | Font checks F001–F008 ported from `reference/fix_canva_fonts.py`, rules YAML | PAT deck output matches the hand-verified MacFix deck's font state |
| 2 | Geometry checks G001–G004, X001 fingerprint, HTML report. Playback P001–P003. Media: capture PowerPoint play-mode reference decks (§7.3), then M001 detect, M002 inventory + CSV/XLSX export, M003, M004 | PAT slide 22 flagged + fixed; pictures off-slide never flagged; each play mode classified correctly on the reference decks from both platforms |
| 2b | Font resolver F009: catalog cache, Get fonts button, per-user install on Mac + Windows | A deck using Montserrat on a clean machine goes red → Get fonts → green after re-scan |
| 3 | Electron app: drop zone, results screen, options panel from `list-checks`, summary bar, repair, report export, settings, preflight | Full drag → scan → repair → summary loop on Mac and Windows builds |
| 4 | LayoutProvider spikes (Windows, Mac), then providers; L001–L003 detect only | PAT slides 5 and 24 flagged by L001 with high confidence; estimate fallback caps at yellow |
| 5 | L fixes + L006 overlap guard, M001 play-mode fix, P001 fix, promoted one at a time via the promotion rule | Each passes corpus targets; M001 fix verified by opening the result in PowerPoint on both platforms |
| 6 | L004, L005, L007, more checks as the corpus surfaces them | Ongoing |

---

## 10. Open decisions

| Decision | Options | Needed by |
| --- | --- | --- |
| ~~App name~~ | **Decided: SlideTistic** (2026-10-07) | — |
| Mac or Windows bridge first | Depends on what show machines mostly run | Phase 4 |
| Mac PowerPoint automation route | AppleScript direct / AppleScript + VBA / bundled `.ppam` / estimate-only | Phase 4 spike |
| ~~Ship inside SlideFluid or separate app~~ | **Decided: separate app**, each app gets a button that launches the other (2026-10-07) | — |
| Fixes inside groups | Deferred in v1; revisit with corpus evidence | Phase 6 |
| Auto-advance default | Fix off (current: some decks loop on purpose) or on for the Canva/Google presets | Phase 2 |
| ~~Default target play mode~~ | **Decided: In click sequence** (2026-10-09) | — |
| Google Fonts source | Official API (needs a key) or google/fonts GitHub metadata | Phase 2b |
| Bundle ffprobe | Adds ~50–80 MB per platform; alternative pymediainfo is smaller but needs its native library | Phase 2 |

---

## 11. Decisions log

### 2026-10-07: kickoff Q&A with David

**Workflow.** A presenter emails a link to their deck. Crew download it from Google Drive, Canva, etc. and run SlideTistic on it **as soon as it arrives**, instead of auditing and repairing it by hand. The goal is speed: the deck should be ready for presentation with no manual work. Show machines are usually **Windows PCs**; crew personal machines are usually **Macs**, so most repairs run on a Mac before the deck goes to a PC.

**Platforms and distribution.** Apple Silicon Mac (signed and notarized) + Windows x64. No Intel Mac. Distributed from GitHub Releases with electron-updater auto-update, the same pipeline as SlideFluid (global CLAUDE recipe). Auto-update ships with the first app build, not later.

**Status vocabulary.** Inventories and fingerprints (G004, X001, M002) use a `Finding.informational = True` flag, not a new status. They are listed but never counted as problems.

**Queue (Drop screen).**
- Dropping a **folder** queues every `.pptx` inside it.
- Every queued file has an always-visible **✕** to remove it from the queue.
- Files over 1 GB (`large_file_warn_mb` in thresholds) show a warning that scanning may take longer. There is no size cap.

**Output.**
- Output **never overwrites**: `Deck - mended.pptx`, then `Deck - mended (2).pptx`, and so on.
- The default output folder is the input file's folder. If that can't be written to, fall back to Downloads on Mac and Desktop on Windows.

**Persistence.** Every preset's toggles are remembered between launches.

**Errors.** A deck that is locked, password-protected or corrupt gets a big red ✕ card with a plain explanation, and the rest of the queue carries on.

**Responsiveness (hard rule).** Every click gets an immediate visible reaction, and anything that takes time shows an animated "Scanning…" or "Repairing…" state, even when no accurate % or ETA is possible. Use real progress where the engine can give it (check *n* of *m*), with an indeterminate animation otherwise. Never use a fake percentage.

**Look.** A continuation of SlideFluid: reuse its two skins (Professional `#070910` / `#3DFFCC`, and the second skin) with the same tokens, so it feels like the same family.

**Power-user.** A Diagnostics tab in Settings (engine log, raw JSON, check versions, preflight), FlowCast/SlideFluid style.

**Scope additions.**
- **Keynote input:** convert `.key` → `.pptx` (via Keynote on the Mac), then scan for translation issues. This needs its own check group of Keynote-conversion edge cases; it comes after the core loop works. Mac-only by nature, since Keynote has no Windows version.
- **SlideFluid cross-launch:** a button in each app that opens the other. The SlideFluid workflow itself doesn't change.

**Engine Python:** 3.11, matching SlideFluid's CI.

### 2026-10-07: branding

- **Accent: Signal violet `#9B8CFF`** on SlideFluid Professional's base tokens. It was chosen because it can't be confused with any status color: teal reads as "fixed" green, and blue is the informational color.
- **Status colors are identical in every skin:** green `#34D399` fixed, amber `#FFB547` look, red `#FF5A5F` broken, blue `#5B9BFF` info. Unlike SlideFluid's Fun skin, no skin may recolor them.
- **Fun skin:** wacky rainbows, Comic Sans, tongue-in-cheek copy ("graphic design is my passion", "Make it go choo choo", "derailed"). It uses SlideFluid Fun's base colors, and the status colors above still apply.
- **Logo:** a steam locomotive, in three files in `assets/brand/`. `logo-lockup-dark.svg` is the engine towing a "P" deck on a flatcar plus the wordmark, used in the app UI header, splash and About screen. `icon-engine.svg` is the engine only, for 64 px and up (dock, installer). `icon-engine-small.svg` is a simplified silhouette for 16–32 px (tabs, taskbar). Use a generic "P" tile, never Microsoft's PowerPoint logo (trademark). Wordmark outlined in Montserrat Bold (OFL); light-background variant uses violet `#6E5BEA`. Generated by `assets/brand/build_brand.py` → `assets/icons/icon.icns` + `icon.ico` (see `assets/brand/README.md`).

### 2026-10-09: visual review, content checks, media retrieval list

**Visual review (before/after images).** The report shows each changed slide twice, as rendered by **real PowerPoint**, with a violet box over every changed shape. An operator can confirm the changes at a glance.
- Rendering: PowerPoint exports the original and the mended deck to PDF (Mac: AppleScript `save … as save as PDF`, about 1 s per deck; Windows: COM `SaveAs` PDF). Poppler `pdftoppm` turns the pages into images; it is already vendored in SlideFluid. Spiked 2026-10-09. AppleScript **PNG export is broken** on current Mac PowerPoint (it reports success and writes nothing), so use PDF.
- Mac PowerPoint is sandboxed. Work files go in `~/Library/Containers/com.microsoft.Powerpoint/Data/tmp/slidetistic/` to avoid file-access prompts.
- What gets a box: any shape whose XML differs between the original and the mended deck, matched by (slide, shape id). This is independent of which check made the change. Deck-level changes (embedded font list, theme) are listed as text above the images.
- Boxes are HTML overlays positioned in % of slide size, not drawn into the images. The report stays light, and hovering a box shows the change ("font name: Calibri (MS) Bold → Calibri, bold on").
- Only changed slides are shown. Report-only findings get a box on the "before" image only.
- Needs PowerPoint installed. Without it, the report is text-only and says why. LibreOffice was rejected: its rendering differs from PowerPoint's, which would mislead on exactly the font and layout problems we fix.
- **Mode:** on by default after Repair (an operator can turn it off in Settings for speed).

**New group C (content)** for C001–C007. The group letters are now F G L P M X C.

**Media retrieval list (M005 + M006).** Crew already have a YouTube downloader, so SlideTistic does **not** download. It produces a list of every online video, embedded web video and media link, with slide number, link, where it was found (slide, notes, hyperlink, embedded player), and slide name. The list is shown in the Media tab, included in the report, and exported as CSV/XLSX, so the operator can fetch each file and embed it by hand.

**Added checks (Tier 1 + 2).** All are report-only to start (`default_fix = False`):

| ID | Check | Detect | Status |
| --- | --- | --- | --- |
| M005 | Online video | Video linked from the web (YouTube/Vimeo/etc. as external video, or a picture hyperlinked to a video site, as Google exports it) | red |
| M006 | Media links to download | Video/file-share URLs in slide text, notes and hyperlinks (patterns in `rules/media_links.yaml`) | yellow |
| C001 | Leftover template text | Phrases in `rules/template_text.yaml` ("Click to add title", "Lorem ipsum", "TBD", "[Name]") | red |
| C002 | Placeholder slide | Slide whose only text is a placeholder phrase ("Video here"), or a slide with nothing visible (blank: yellow) | yellow |
| C004 | Hidden slide | `show="0"` | informational |
| P005 | Click map | Clicks per slide (click-triggered animation steps + advance). **Needs real PowerPoint-saved fixtures** before coding | informational |
| P004 | Link leaves the show | Clickable hyperlinks to web pages or other files | yellow |
| G006 | Aspect ratio | Slide size isn't the target ratio (setting, default 16:9) | yellow |
| F010 | Mac-only fonts | Data only: `rules/mac_only_fonts.yaml` with suggested swaps, used in F007's message | — |
| F011 | Emoji in text | Emoji characters in slide text (look different on Mac vs Windows; can show as boxes) | yellow |
| M008 | Oversized image | Image pixels far beyond what it's displayed at (threshold in `thresholds.yaml`) | yellow |
| M009 | Low-resolution image | Image would show below the target resolution on a 1920×1080 output | yellow |
| M011 | Risky image format | WebP, HEIC, WMF/EMF | yellow |
| X002 | File hygiene | Deck over a size threshold; filename with emoji, slashes or extreme length | yellow |
| X003 | Needs another app | Embedded OLE objects, ActiveX controls, macro-enabled package | yellow |
| X004 | Linked to a local path | External relationships pointing at `C:\…`, `/Users/…` or `file://` | red |
| C007 | Review comments left in | Comment parts present | yellow (fix: remove, off) |

### 2026-10-09: phase 2 built

- **Video play modes are evidence-based.** Corpus: 31 videos in 17 decks, saved by Mac and Windows PowerPoint. The timing trees are saved as fixtures in `tests/fixtures/media_modes/` (structure only, no client content). "Automatically" = play step `nodeType="afterEffect"` in click group 1, plus an `evt="onBegin"` condition on that group. "In click sequence" = `clickEffect`. Identical on both platforms. Also confirmed: `<p:video fullScrn="1">`, `repeatCount="indefinite"` (loop), `showWhenStopped="0"` (hidden), `vol` / `mute`. **Not yet seen** (reported as unknown/unconfirmed): "When clicked on" and "Rewind after playing".
- **M001 target changed (David, 2026-10-09):** shows are clicker-driven, so the goal is **"In Click Sequence"**, not "Automatically". Both of those are fine; M001 flags only **"When Clicked On"** (red) and videos with **no start setting** (yellow), since the clicker can't start either. The earlier "make it automatic" fix was removed.
- **"When Clicked On" found (Dropbox corpus, 2026-10-09: 307 videos, 727 decks):** 8 videos (6 Windows saves, 2 Mac) have only the self-trigger and no play step in the click sequence. That is exactly a click-sequence save minus its main-sequence block, on both platforms. The M001 fix inserts PowerPoint's own block (multiple videos on one slide become clicks 1, 2, 3 in order). Tested: the result matches PowerPoint's click-sequence save structurally; a real 47-slide deck converted 6 videos and opened and exported cleanly in Mac PowerPoint. **Confirmed by David in PowerPoint 2026-10-10** (all converted videos show In Click Sequence; slide 27's three videos are clicks 1–3). Fix **on by default**.
- **G001 is red only when geometry proves the words are cut off:** left/right-aligned text whose first character position (box edge + inner margin + paragraph indent) is past the slide edge. Other overhangs are yellow, the fix is refused, and the visual review shows them. Overhangs inside a box's own inner margin are ignored. Corpus: 206 boxes cross an edge in 17 decks, most harmlessly. **PAT slide 22** (centered, 0.56 in off the left) is yellow: the hand-made MacFix left it in place too.
- **Visual review shipped** in the HTML report. Slide images are JPEG (PNG made a 30-slide report 15.7 MB; JPEG makes it 2.3 MB). Slides whose before and after renders are visually identical fold into one line. Outlines sit outside shapes so they never cover text: a first version hid the first letters and made correct text look cut off.
- **Source fingerprint (X001):** Canva = 20 × 11.25 in slides or `(MS)` font aliases; Google = shapes named `Google Shape;…` or 10 × 5.625 in; PDF conversion = ≥80 % of slides are one full-slide picture.

### 2026-10-10: layout fit and review page (David's review of the PAT report)

**Verified:** M001 "When Clicked On" → "In Click Sequence" works in PowerPoint (fix on by default).

**What a good layout means (David):**
- **Safe zone:** a **5 % border on every edge** (`safe_zone_pct`). Text must sit inside it, especially on projected screens. PAT slide 29's text runs to the bottom edge, which is bad.
- **No orphans:** never a single word alone on a paragraph's last line. PAT slide 27: "whole".
- **Overlaps:** box overlap doesn't matter; **text overlapping other text is critical**. Text fully inside a graphic is assumed intentional; text **partially** over a graphic is a possible problem.
- **Font fixes can make layout worse.** The real font is wider and re-wraps (PAT slides 19 and 27), so layout checks must run after font fixes and judge the result.

**Fit fixes allowed (rule 3 above):** box first, then line spacing, then font size (last resort).

**Layout source:** what PowerPoint actually draws. Words and lines come from PowerPoint's own PDF export (already produced for the visual review) via Poppler `pdftotext -bbox-layout`. This gives line breaks, word positions and real text extents per slide, with no font measuring of our own (CLAUDE.md rule 4). Windows: the same PDF route via COM.

**Review page:** blocks in severity order, then slide order:
1. Text off the slide / still broken
2. Visible changes SlideTistic made (verify)
3. Needs a look
4. Changed underneath, looks identical (one folded line)

Each slide appears once, in its most severe block. Boxes are coloured by **kind** (font, placement, layout fit, media/playback, content) with a legend; hovering a box shows the details. Off-slide text gets an alert banner at the top.

**Diagnostic mode** (on until we leave testing): every finding and change shows the rule that decided it, with the numbers used, so David can disagree precisely.

### 2026-10-10 (later): layout fit fixes

David reviewed the first layout report: the problems were flagged but not fixed ("after" unchanged), and the font fix made slide 19 worse. Now:

- **Layout fixes run in rounds after all other fixes.** Each round: save the working copy → PowerPoint renders it → detect → fix. There is **one change per slide per round**, so each fix is judged against a fresh render of its slide; two blind changes on the same slide collided (PAT 24). Rounds stop when nothing changes (`fit_max_rounds`, 6).
- **Re-wrap prediction** (`engine/core/fit.py: Reflow`): PowerPoint's own word widths, line pitch and paragraph gaps from the render predict the line breaks at any box width. It is calibrated conservatively against the breaks PowerPoint actually made. Every candidate change must predict: no single-word last lines, no extra lines, **no text over text**, inside the safe zone. A real re-render still verifies each one.
- **L010 collision:** re-wrap one of the two boxes (smallest width change first, narrowing up to 15 %, widening up to the safe width); then the same search with the font shrunk up to the cap.
- **L009 orphan:** smallest width change in −15 % … +`body_widen_max_pct` that fixes it.
- **L008 safe zone**, box → spacing → font:
  1. Narrow to the safe width.
  2. Too tall: tighten line spacing to the floor, then shrink the font.
  3. Nudge in (landing slightly inside the line).
  4. **Never onto other text.** If the nudge would hit text below, *push* that text down first when it has room; if a bottom-border block can't move up, tighten its spacing. Otherwise leave it for a person: text over text is worse than text near the edge.
- **Rendered words are matched to boxes in reading order** (each box's text is a known word sequence), so words two boxes share ("Health") and lines pdftotext merges across boxes resolve correctly.
- **Problems a fix causes** keep their own severity, with "introduced by …".
- **PAT result:** 57 fixed, 1 still broken (slide 18's 'care' orphan resists the prediction). The left-over yellows are top/bottom-border cases where nothing can make room without breaking another rule.

**Source shout (David):** the report opens with "CANVA DETECTED! Buckle up, we got a gRaPhIc dEsIgNeR on our hands." (plus Google / Keynote / PDF versions). In the app (phase 3) this belongs on the results header, and the Fun skin can go wilder.

### 2026-10-10 (evening): text-based fitting + final safety pass (David's second review)

- **Headers keep their line count.** 1 → 2 lines in a header breaks the designer's layout. Header = the slide's largest, short (≤ 12 words) text. **L001** compares it with PowerPoint's render of the *original* deck and fixes it (widen, then font). A lone text block (PAT 19) isn't a header; balanced lines with no orphan are enough there.
- **Font shrink cap raised to 15 %** (`fit_max_font_shrink_pct`).
- **Decisions use where the text is drawn, never the box edge.** A box clamp shoved PAT 18's bullets (box 0.8 in off-slide, text indented 1.6 in) 1.8 in right, under an illustration. One search (`fit.plan_fit`) serves every fit fix: box → line spacing → font, cheapest first. Each candidate's re-wrap is predicted, and it must never leave the slide, never land on other text, never slide onto a **new image**, add no orphans, and (headers) no lines. Only the safe-zone fix must end fully inside the 5 % border; the others must not end up further into it than they already are.
- **"Images" = pictures + shapes filled with an image.** Canva exports photos and charts as image-filled freeforms (PAT 5). Plain coloured panels behind text are not obstacles.
- **Final safety pass:** after the fit rounds, PowerPoint renders the result once more. Any slide now worse than before the layout fixes (text off the slide, text over text, words hidden behind an image, a header with more lines) is put back exactly as it was and reported ("undone by the final safety check"). **Text may never go off a slide.**
- **An unfinished fix keeps the finding's own severity.** A title still near the edge is "look at", not "broken". Red is for what the check itself calls red.
- **PAT:** 58 fixed, 0 still broken; the safety pass restored slide 18 when an intermediate fix hid words behind the illustration.

### 2026-10-10 (night): Windows PowerPoint renderer (built on David's PC)

- **Layout fixes, the visual review and drawn-word off-slide checks now run on Windows.** `engine/render.py`
  has `MacPowerPointRenderer` and `WindowsPowerPointRenderer`; `PowerPointRenderer` is the platform switch,
  so the runner and CLI didn't change. Windows uses COM (pywin32): open a copy read-only and windowless,
  `SaveAs` PDF, close. Then the same Poppler path as the Mac (Poppler for Windows bundled in CI, hash-pinned).
- **Measured on the PC (PowerPoint 16, 64-bit):** hidden slides are left out of the PDF (as on the Mac);
  page size = slide size exactly; ~1 s per export, ~3 s once to start PowerPoint; a 6-slide repair with
  layout fixes and visual review takes 5–11 s.
- **Difference from the Mac:** Windows PowerPoint keeps off-slide text in the PDF. pdftotext clips it at the
  page edge, so "words drawn" means the same on both platforms once negative coordinates are parsed.
- **Safety:** only the presentation our own `Open` returned is touched; PowerPoint is quit (or killed after
  a 300 s hang) only if we started it and nothing of the user's is open in it.
- **App queue (David):** a clicked Repair stops the running scan and starts immediately; the scan re-runs
  next. A job with no progress for 6 min (scan) or 10 min (repair) is stopped with a plain red card, so
  one unreadable deck can't freeze the queue. "Open in PowerPoint at this slide" works on Windows.

### 2026-10-11: Tuning mode (David's 👍/👎 votes tune the layout fixes)

- **Why:** David judged more than half of the layout "repairs" to be inconsequential or worse.
- **How:** Settings › Diagnostics › Tuning mode adds 👍/👎 (plus four optional 👎 reasons) to every changed slide.
  One vote covers the whole slide. Votes are JSON lines in the Dropbox suite's `_feedback/votes-<machine>.jsonl`
  and hold numbers only (`engine/core/tuning.py` features), never slide text.
- **Rules change only with David's approval:** `slidetistic tune` reports approval by kind of change, proposes
  gates replayed against every vote, and asks about splits; `tune --apply P#` writes an approved gate to
  `rules/tuning.yaml`. A gated fix isn't made, and its finding stays "worth a look" (fixed, or untouched).

### 2026-10-12: Safe-zone fixes narrowed (David's first 305 votes)

- **Header/footer band:** text drawn entirely in the top or bottom 15 % of the slide (`header_footer_band_pct`),
  and footer / slide-number / date / header placeholders, is placed on purpose. It isn't flagged for sitting in
  the border, and it's never moved, even when it runs off the slide (that stays red for a person).
- **Only big blocks are pulled in from the border:** text whose box covers ≥25 % of the slide
  (`safe_zone_fix_min_area_pct`). Smaller text near an edge is reported (yellow) and left as designed.
- **Text sitting on a filled shape** (≥80 % of the box over it, `on_shape_min_overlap_pct`) moves together with
  the shape by the same amount, or not at all.

### 2026-10-12: Free fonts (F009), Fonts tab, Notes, broken-slide checks

- **F009 source:** the catalog comes from the Fontsource API (David: only fonts that API lists). Files come from
  Google Fonts' CSS API as TTF (correct names, full character set), or from Fontsource for its non-Google fonts.
  Every file is name-checked before it's installed per user. See docs/F009_FONTSOURCE_DESIGN.md §10–12.
- **Fonts tab + banner** (like Media): every font, its status, the slides it's shown on, embedded or not, Get.
- **Fonts no text uses** become notes in F007 (half of all font reds were these).
- **Notes level:** low-priority yellows (small text by an edge; under 15 % of text over a picture; fonts no text
  uses) are shown collapsed and not counted with the yellows.
- **Broken slides:** each red slide, plus one "whole deck" item, gets ✓ Checked. A counter tells the operator when
  everything critical has been looked at, remembered per deck file. The filter (R) shows broken slides only.

### 2026-10-12 (evening): Round 2 votes → letters, not boxes

- Round 2: 103 votes, 48 % approved (round 1: 14 %). Applied:
  - **T001** (no L008 pull for text under 0.1 in into the border; David approved);
  - **off-slide** = letters touching the edge in the render (a line box crossing it isn't);
  - **text over text** = letter zones overlapping with no clean pixel row between them (stacked labels aren't);
  - **moves avoid** filled shapes, outlines and lines;
  - **F001** renames only names F005 can refile (Dealer Trust: renaming an embedded "X Bold" made the text regular).
- Still with David: font shrinking for overlaps/safe zone (decide after seeing real collisions).
