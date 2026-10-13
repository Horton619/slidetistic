# F009 — Free-font downloader via Fontsource (design, 2026-10-11)

Replaces the source part of SPEC §7.5. Scope decided by David 2026-10-11: **Fontsource only**. No web
search, no archive.org, no substitution table, no near-miss suggestions. Fonts Fontsource doesn't have
stay with F007 (red) / F004 (Canva-only, red); David sources those by hand.

## 1. What Fontsource gives us (checked 2026-10-11)

| Fact | Status |
|---|---|
| `GET https://api.fontsource.org/v1/fonts` → every family (id, family, subsets, weights, styles, defSubset, variable, type, category, version). Filterable (`?family=Montserrat`). No API key in the docs. | Docs |
| `GET /v1/fonts/{id}` → same plus `license` (e.g. `"OFL-1.1"`), `unicodeRange` per subset, `npmVersion`, and `variants[weight][style][subset].url.{woff2,woff,ttf}` | Fetched live for `montserrat` (`license` is in the response but not in the docs) |
| Files live on jsDelivr: `https://cdn.jsdelivr.net/fontsource/fonts/<id>@<ver>/<subset>-<weight>-<style>.ttf` | Docs + live URLs |
| **Files are split by Unicode subset** (latin, latin-ext, cyrillic…), one static file per weight/style/subset, even for variable families | Live response |
| TTF name tables are intact (family/subfamily/full/PostScript names usable by PowerPoint) | **Not verified**: the container and the Mac shell are both blocked from api.fontsource.org / jsDelivr by the proxy. Spike S1. |
| Rate limits | Not documented. We make one catalog call a week plus one call per family on install, so it shouldn't matter. |

Static per-weight files are a plus: PowerPoint (especially Mac) handles variable fonts badly, and
google/fonts on GitHub often only ships the variable file.

Not using the `fontsource-downloader` PyPI package: it's a Rust extension (extra PyInstaller risk) and we
only need two GETs and a file write. Plain `urllib` with the macOS/Windows system certificates.

## 2. Where it sits in the pipeline

```
scan ─ F001–F004 normalize names ─ F007 (red: missing) ─ F009 (yellow: downloadable)
                                                            │
                     Get fonts (button) or auto-install ────┘
                                                            │
                     install → restart *our* hidden PowerPoint → render → layout fixes
```

**Order matters:** layout fixes (L001–L011) are planned against PowerPoint's render. If the font is
installed after the render, every fit fix was computed against the substitute font and is wrong once the
real font is on the show machine. So on **repair**, any install happens before the first render.

## 3. F009 check (detect only)

- File: `engine/checks/fonts/F009_free_font_available.py`, `report_only = True`,
  `runs_after = ["F001", "F002", "F003", "F004"]`, sources canva/google/any.
- **Candidates** = the families F007 reports as missing (same "covered" rule), minus Canva-only (F004),
  minus families already installed on this machine. Move F007's covered-set logic into
  `fonts.uncovered_families(deck, ctx)` and have both checks call it. F007's behavior must not change
  (golden rule 8; prove it with the corpus diff).
- **Match:** casefolded exact family name against the cached catalog. No fuzzy matching.
- **Variants needed**, from the deck's runs (`fonts.font_refs`):
  - `b`/`i` flags → 400/700 × normal/italic.
  - Weight-named families (`Montserrat SemiBold`, the F003 cases) → base family + weight, using
    `weight_suffixes.yaml` plus a new `weight_numbers` map (Thin 100 … Black 900) in the same file.
  - A variant the family doesn't have (no italics, say) → listed in the finding as "not available,
    PowerPoint will fake it".
- **Subsets needed:** always `defSubset` (latin), plus any subset whose `unicodeRange` covers characters
  actually used in that family's runs (ł, ő, Cyrillic, Vietnamese).
- **Finding:** `yellow`, one per family. Message: "Montserrat is a free font (OFL-1.1) and isn't installed.
  Get fonts can install Regular, SemiBold, Bold (slides 3, 7, 12)." Evidence: catalog id, version, license,
  variants, subsets, `rule`.
- **No network in detect.** Detect reads only the cached catalog. With no cache at all: one deck-level
  `yellow`, "Couldn't check for free fonts: font list not downloaded yet."

## 4. New modules

**`engine/core/fonts_catalog.py`**
- `refresh(force=False)`: GET `/v1/fonts`, save to the cache dir (Mac `~/Library/Caches/SlideTistic/fontsource/`,
  Windows `%LOCALAPPDATA%\SlideTistic\Cache\fontsource\`). Refresh when older than 7 days and the network
  setting is on. A stale cache is still used offline.
- `lookup(family) -> CatalogEntry | None`, `details(id)` (GET `/v1/fonts/{id}`, cached per id + version).
- The app calls `refresh()` in the background at launch, never during a scan.

**`engine/core/fonts_install.py`**
- `installed_families()`: scan system + user font dirs (and Office's own font folder on Mac) with fontTools,
  reading name IDs 1/16 and 4/6. Cached by dir mtime. Used by F009 (skip what's already here).
- `download(entry, variants, subsets)`: TTF URL pinned to `@<npmVersion>`, not `@latest`. Fall back to
  woff2 → TTF with fontTools only when no TTF is offered (that needs the `brotli` package).
- **Validate before installing:** fontTools opens the file; the family name inside matches what the deck
  asks for (including the Windows-style `Montserrat SemiBold` name ID 1); it has glyphs for the characters
  the deck uses. Anything that fails isn't installed and is reported.
- `install(files)`:
  - Mac: copy to `~/Library/Fonts/`.
  - Windows: copy to `%LOCALAPPDATA%\Microsoft\Windows\Fonts\`, write
    `HKCU\Software\Microsoft\Windows NT\CurrentVersion\Fonts` ("<Full name> (TrueType)" = path),
    `AddFontResourceEx`, broadcast `WM_FONTCHANGE` (pywin32 is already a dependency).
  - File name `SlideTistic-<id>-<weight><style>-<subset>.ttf`.
  - Skip a file whose PostScript name is already installed: duplicate PS names confuse Mac PowerPoint.
  - Append to `installed.json` in the cache dir (what, when, which deck) so `fonts uninstall` can undo it.
    The graphics machines get re-imaged anyway; this is for David's own Mac.

## 5. CLI and app

```
slidetistic fonts catalog [--refresh]
slidetistic fonts get <deck> [--install] [--json]     # JSON-lines progress events, SlideFluid IPC style
slidetistic fonts installed [--json]
slidetistic fonts uninstall [--all | <family>]
```

- **Get fonts** button (already in SPEC §5): shows families, weights and license, then installs, then re-scans.
- Settings: the existing "Allow network for font catalog and downloads" toggle, plus a new
  **"Install free fonts automatically"** toggle. When it's on, repair installs before rendering (§2).
- **PowerPoint restart.** New fonts aren't seen until PowerPoint restarts (expected on both platforms;
  test it, spike S3). The renderer quits the hidden PowerPoint it started after an install. If David's own
  PowerPoint is open, the hidden copy runs inside it and renders with the substitute font. In that case the
  app shows "Restart PowerPoint to use the new fonts" and doesn't render until he does. Never quit his
  PowerPoint for him.

## 6. Decision needed: does "installed here" count for F007?

F007 says "missing on **show machines**": embedded, Office, or on the crew font list. It never looks at
what's installed on the machine running SlideTistic. So after Get fonts, F007 stays red, which looks broken.
Options:
1. **Setting "This computer is a show machine"**. When it's on, fonts installed here count as covered and F007
   turns green after an install; when it's off, F007 stays red with "installed on this computer only".
   *Recommended:* this fits running SlideTistic on the graphics machine as well as prepping on the Mac.
2. Install adds the family to the crew font list automatically. Simpler, but the list stops meaning what
   the show machines have.
3. Leave F007 as is and let F009's green carry the result.

## 7. SPEC edits this implies (for David to accept)

- §7.5: source = Fontsource. Delete "Google's official source only" and "Never download from third-party
  font sites". Delete `font_licenses.yaml`: Fontsource only carries open-licensed fonts. The license still
  shows in the finding and the Get fonts dialog.
- §7.5: delete "near-misses are reported as suggestions".
- §10 open decisions: "Google Fonts source" → **Decided: Fontsource API + jsDelivr files (2026-10-11)**.

## 8. Tests

- `tests/fixtures/fontsource_catalog.json` (trimmed real response; recapture once the network allows) and
  `fontsource_montserrat.json`. All HTTP mocked; CI has no network.
- F009 fires: Montserrat not installed. Must not fire: Calibri (Office), Canva Sans (F004), `Calibri (MS)`
  (alias → Office), a family not in the catalog (F007 only), Montserrat already installed.
- Variant picking: bold-italic run → 700 italic; `Montserrat SemiBold` → 600; text with "ł" → adds latin-ext.
- Install tests run against a temp font dir (`SLIDETISTIC_FONT_DIR` override); a Windows registry test runs on the PC only.
- `pytest -m network`: one live round-trip (catalog, details, download Montserrat 400 latin, validate). Never in CI.
- Corpus: F007 results unchanged after the refactor; report F009 hits across the suite (TEST_DECKS #6).

## 9. Spikes before building

- **S1 (blocking):** download a few subset TTFs (Montserrat 600, Poppins 400 italic, Open Sans 700) and dump
  name IDs 1/2/4/6/16/17 with fontTools. Confirm Mac and Windows PowerPoint both resolve them by the
  names Canva/Google decks use. Needs a network that reaches jsDelivr: David's own shell, not this sandbox.
- **S2:** two subsets of one weight installed side by side share the same family and PostScript name, so
  the OS keeps one. Pick one of: (a) install only latin and warn yellow about any characters outside it;
  (b) merge the subset files with `fontTools.merge`; (c) for `type: google`, take the full static file from
  google/fonts instead. Recommend (a) for v1: US/Canada decks are almost all latin, and French accents are
  in latin.
- **S3:** confirm PowerPoint (Mac + Win) needs a restart to see a newly installed font, and whether our
  hidden renderer instance does.
- **S4:** reachability of api.fontsource.org and cdn.jsdelivr.net from venue/hotel networks. Cache downloaded
  files so a second deck with the same font needs no network.

---

## 10. Research results (2026-10-12, Mac, network open)

Spikes S1 and S2 were run from the Mac shell. Nothing was installed: files went to a scratch folder and were
inspected with fontTools 4.66.1.

### S1: Fontsource's static files often carry the wrong family name. **Blocking for "Fontsource only".**

- **Sample:** 25 popular families. For each: latin subset, weights 400/700/600 (or 300), plus 400 italic,
  pinned `@5.3.0`. Checked name IDs 1/2/16/17 against the catalog's `family`.
- **Result: 45 of 93 files are wrong**, in two kinds:
  - **Variable families cut into static files with the default instance's names left in (12 of 25
    families).** Montserrat 400 is named *"Montserrat Thin" Regular*, and 600 is *"Montserrat Thin SemiBold"*. The
    same goes for Raleway, Nunito, Source Sans 3, Rubik, Quicksand, Josefin Sans and League Spartan (the default
    instance's weight name), Merriweather (*"Merriweather Light 18pt"*), DM Sans (*"DM Sans 9pt"*) and
    Archivo (*"Archivo SemiBold"* for every weight).
    - Installed as-is, PowerPoint would list "Montserrat Thin" and a deck asking for "Montserrat" would still
      fall back to a substitute. Montserrat is the most common Canva font.
    - The cause is upstream: google/fonts ships only `Montserrat[wght].ttf`, whose default instance is Thin
      (`METADATA.pb` says `full_name: "Montserrat Thin"`).
  - **Static families with Windows-style names** (Poppins 600 = *"Poppins SemiBold" Regular*, no ID 16/17;
    Lato Light, Barlow SemiBold). Google's own files are named the same way, and decks ask for exactly these names
    (the F003 cases), so these are probably fine. They still need the PowerPoint test (S3).
- **Subsets aren't supersets:** Montserrat `latin-ext-600` has ł but **not** é. A deck with both would need
  two files merged into one font. That confirms S2 is real.

### Better source for the files: Google Fonts' own CSS API, asked for TTF

- **How:** `GET https://fonts.googleapis.com/css2?family=Montserrat:ital,wght@0,400;0,600;1,400` with a legacy
  user agent (`Mozilla/4.0`) returns `@font-face` blocks whose `src` is a **static, full-charset TTF** on
  fonts.gstatic.com. (Modern browsers get subset woff2; old ones get TTF.) No API key needed.
- **Every family checked comes back correctly named:**
  - Montserrat 400 → `Montserrat / Regular`; 600 → `Montserrat SemiBold / Regular` with 16/17
    `Montserrat / SemiBold` (both Windows and Mac style).
  - DM Sans → `DM Sans`; Merriweather → `Merriweather`; Raleway, Nunito, Archivo and Source Sans 3 → correct.
- **One file per weight/style holds every script** (Montserrat 1,312 characters: latin, latin-ext, Cyrillic,
  Vietnamese). **S2 goes away:** no subset choice and no merging. Files are 50–570 KB.
- **Forgiving:** weights a family lacks are skipped rather than failing the request. Legacy names still resolve
  ("Source Sans Pro").
- **Risk:** the legacy-UA TTF response is long-standing Google behaviour but undocumented. If it stops, the
  fallback is google/fonts on GitHub: static TTFs for static families (Poppins ships every weight), and for
  variable families `fontTools.varLib.instancer.instantiateVariableFont(vf, {"wght": w},
  updateFontNames=True)`.
  - Tested: this produces names identical to Google's for wght-only fonts (Montserrat 400/600).
  - Fonts with extra axes need care: DM Sans pinned at `opsz=14` comes out as "DM Sans 14pt", so the extra axes
    must be pinned and their names elided.

**Recommendation:**
- **Catalog and license:** Fontsource's catalog (`/v1/fonts`, 2,103 families: 1,984 `google`, 119 `other`).
  It's keyless, one call, and has license, weights and styles.
- **Files for `type: google` (94 %):** Google's CSS API, as TTF.
- **Fontsource files** only for `type: other`, after the same name validation, which rejects a bad file
  rather than installing it.
- **Validation as the last line of defence:** whatever the source, the file's ID 1 or ID 16 must equal the
  family the deck asks for. Otherwise it isn't installed and the finding says so.

### HTTPS from Python fails on python.org builds

The venv's Python (python.org framework build) can't verify certificates
(`CERTIFICATE_VERIFY_FAILED`): it doesn't read the macOS keychain. The PyInstaller engine will behave the same.
The design's "plain urllib with the system certificates" doesn't work as written. Options:
- `truststore` (uses the OS trust store on Mac and Windows; good behind venue proxies with their own CA);
- `certifi` (a bundled CA list);
- shelling out to `curl`, which ships with macOS and with Windows 10+.

Recommend `truststore` + `certifi` fallback: pure Python, no PyInstaller risk. Add both to requirements and
the spec's hidden imports.

### How much F009 would catch on the suite

F007 reports **82 missing families** across the 31 suite decks (scan, run `20261011-1207-mac-daa365c-layout`).
- **Exact catalog match: 11.** Lato, Source Sans 3, Source Serif 4, Poppins, Noto Serif, Contrail One, Space
  Grotesk, Source Sans Pro, Raleway, Noto Sans Symbols, Roboto.
- **Adding weight-suffix matching** (`Lato Light`, `Roboto Light`, `Space Grotesk Light`, `League Spartan Thin`,
  `Noto Serif bold/Regular`) brings it to about 17. F009 must use the same weight-suffix rules as F003.
- **The rest can't be downloaded free:**
  - commercial: Gotham, Proxima Nova, Avenir, Minion/Trajan Pro, Museo Sans, Neue Haas, D-DIN;
  - Apple-only: Helvetica, Gill Sans, Hiragino;
  - Microsoft: Aptos, Segoe UI, Franklin Gothic, Rockwell, Calisto MT, Seaford, Malgun Gothic.
- So F009 helps a real minority (roughly 1 deck in 5 here) and is cheap once built. It isn't the fix for most
  missing fonts.

### Side findings for David (not F009)

- **Aptos is missing in 11 of 31 decks** (plus Aptos Display/Narrow/Black/ExtraBold). It's Office's default font
  since 2023, a cloud font that Microsoft 365 downloads on first use. Office 2019/2021 show machines don't have
  it, so F007 is right to flag it. Worth a crew-facing message: "Aptos is Office 365's default font; older Office
  substitutes it."
- **CSS leftovers reach F007 as font names:** `Arial,Sans-Serif`, `Courier New,monospace`,
  `Wingdings,Sans-Serif`, `inherit` (Google Slides/Canva). They should be normalized (first family in the list;
  drop `inherit`) in F001/F002's rule data. That's an edge case to log.
- **Windows system fonts flagged as missing:** Segoe UI, Malgun Gothic, Microsoft New Tai Lue. They are on every
  Windows show machine but aren't in the Office list. Part of the "noisy F007" open question.

### Still open

- **S3:** install a font and confirm both PowerPoints resolve the deck's names. Does each need a restart? Does our
  hidden renderer? This **installs fonts on a real machine**: David's go-ahead first (a throwaway family
  like Contrail One on the Mac, then the PC).
- **S4:** venue networks (fonts.googleapis.com, fonts.gstatic.com, api.fontsource.org, cdn.jsdelivr.net).
  Cache downloaded files so the second deck needs nothing.
- **SPEC §7.5:** its original "Google's official source only" line is closer to this result than "Fontsource
  only". Decide the source split with David: catalog from Fontsource, files from Google.

---

## 11. Built (2026-10-12)

- **Modules:**
  - `engine/core/http.py`: truststore → certifi → default.
  - `engine/core/fonts_catalog.py`: Fontsource list, weekly cache, `lookup`, `details`.
  - `engine/core/fonts_install.py`:
    - Google CSS API TTFs for `type: google`, Fontsource latin TTFs for `other`;
    - `check_file` name/weight/style check (it refuses Fontsource's "Montserrat Thin" files and variable fonts);
    - per-user install on Mac and Windows (HKCU registry + `AddFontResourceW`), with `installed.json` and `uninstall`.
- **F009** (informational, `report_only`):
  - only for fonts F007 reports AND that shown text actually uses (`engine/core/font_use.py`);
  - weight words resolved (`Space Grotesk Light` → Space Grotesk 300);
  - skips fonts already installed here;
  - with no cached list: one note.
- **Which fonts shown text uses** (`font_use.visible_fonts`): inheritance run → list style → layout/master
  placeholder → master text styles → theme. Also counted:
  - SmartArt and chart text;
  - fixed text on the layout/master behind the slide (respecting "hide background graphics");
  - East Asian/symbol fonts on shown runs.

  Checked against PowerPoint's own PDFs (`pdffonts`) on 8 suite decks; the only differences were substitutes.
- **F007:** a missing font that no shown text uses is now a **note** ("named in the deck but no text uses it"): 58 of
  116 suite reds. F009 never offers those.
- **CLI:** `fonts catalog [--refresh]`, `fonts get <deck> [--family F] [--install] [--json]`, `fonts installed`,
  `fonts uninstall [family|--all]`.
- **App:**
  - Fonts banner (like Media) + queue chip;
  - **Fonts tab**: every font, its status, the slides it's shown on, whether it's embedded, and **Get**;
  - an inline confirm before installing; after install, a toast to restart PowerPoint, then the deck is re-checked;
  - the font list is refreshed in the background 20 s after launch, weekly.
- **Tests:**
  - `tests/checks/test_F009_free_font_available.py`, `tests/test_font_use.py`;
  - every test runs with private font folders (conftest), so nothing is ever installed for real.

## 12. Wider supply (researched 2026-10-12)

Matched against the 43 missing families that shown text uses across the suite:
- **Font Squirrel** (1,036 families, JSON API) and **Fontshare** (100, JSON API): **nothing beyond Fontsource**.
- **Microsoft Aptos** is an official free download (Microsoft Download Center id 106087, a 2.8 MB ZIP, Mac + Windows).
  Aptos/Aptos Display/Narrow is the most common missing font (5+ decks). It isn't on Fontsource, so it's outside
  David's "only that API" rule: **ask him** before adding a second source.
- **Adobe Fonts** (Proxima Nova, Museo Sans, Neue Haas Grotesk, Avenir Next LT Pro): activation only, through the
  Creative Cloud app, with no files to download. The best we can do is a rules list that says "available in Adobe
  Fonts: activate it in Creative Cloud".
- **The rest are Microsoft/Apple system fonts:**
  - Office-for-Windows fonts: Segoe UI, Franklin Gothic, Rockwell, Book Antiqua, MS PGothic. On a Windows show
    machine they're present, so moving them into `conditional_fonts.yaml windows` (yellow) would remove false reds.
    That's a rule-data change: ask David.
  - Mac-only fonts: Helvetica, Gill Sans, Avenir, Hiragino. These already get swap suggestions.

## 13. More sources + Collect fonts (2026-10-12)

- **Lookup order** (David: "Microsoft fonts if available, Google if Fontsource doesn't have it; if they disagree
  on the name, use the one that matches the name in the ppt"):
  1. `rules/font_downloads.yaml`: makers' own free downloads, starting with Microsoft's Aptos ZIP (29 static files).
  2. Fontsource.
  3. Google's family list (`fonts.google.com/metadata/fonts`).

  The deck's exact name picks the entry, and every file is name-checked against it.
- **Creative Cloud:** Adobe Fonts activated on this computer are read, for their names only, from the hidden
  CoreSync `livetype` folder. They count as "on this computer" (so they're never offered for download), and the
  Fonts tab says so. Missing commercial fonts get a "Search Adobe Fonts ↗" link: activation can't be automated.
- **Collect fonts next to deck** (`fonts collect`, Fonts tab button; a testing aid David asked for):
  - makes `<deck> - fonts/` next to the deck, with every non-Office font that shown text uses, named by what it is;
  - installed and Creative Cloud fonts are **copied** from where they are (Creative Cloud's `.r/.139.otf`
    becomes `Proxima Nova Bold.otf`); free fonts not installed here are downloaded;
  - FONTS.txt lists each font with its source, path, and what wasn't found; the folder opens in Finder.

  David's show content folders live on his own machine (Desktop/Downloads, "<show> content" folders sorted by type
  and day), so the deck's fonts are real files next to it (David 2026-10-12: "dont worry about the dropbox edge case").
- **Found along the way:** Book Antiqua, Franklin Gothic and Rockwell ship inside PowerPoint itself
  (`PowerPoint.app/Contents/Resources/DFonts`), so F007 calling them missing is wrong. The office_fonts.yaml edit is
  waiting on David.
