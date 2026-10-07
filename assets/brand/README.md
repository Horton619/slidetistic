# Brand assets

Edit the **sources**, then rebuild everything with:

```
venv/bin/python assets/brand/build_brand.py
```

| File | What it is | Edit? |
| --- | --- | --- |
| `src/lockup.svg` | Engine towing the "P" deck + wordmark, with live text | Source |
| `icon-engine.svg` | Engine only, for 64 px and up (dock, installer, Start menu) | Source |
| `icon-engine-small.svg` | Simplified silhouette, for 16–32 px (tabs, taskbar, tray) | Source |
| `logo-lockup-dark.svg` / `-light.svg` | Lockup with text converted to outlines (Montserrat Bold), for dark / light backgrounds | Generated |
| `png/` | Lockup @1x/@2x, icon PNGs | Generated |
| `../icons/icon.icns` | Mac icon. Apple grid: 824/1024 body with transparent margin; small art at 16–32 px | Generated |
| `../icons/icon.ico` | Windows icon, 16–256 px; small art at 16–32 px | Generated |

Rules:
- **Accent `#9B8CFF`** (light version: `#6E5BEA`, for contrast on white).
- **Generic "P" tile only.** Never use Microsoft's PowerPoint logo or its orange (trademark).
- **Wordmark font: Montserrat Bold (OFL)**, outlined, so no machine needs the font installed. Not SF
  Pro: Apple's license limits it to Apple platforms.
- The Fun skin's Comic Sans is **live system text in the UI only**, never outlined into shipped art
  (it's a Microsoft font).

The build needs `rsvg-convert` and `magick` (Homebrew), `iconutil` (macOS), and
`Montserrat-VariableFont_wght.ttf` in `~/Library/Fonts` (or set `$BRAND_FONT`).
