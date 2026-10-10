"""Media inventory + download list as rows, CSV and XLSX (SPEC §7.4)."""
from __future__ import annotations

import csv
from pathlib import Path

INVENTORY_COLUMNS = [
    ("Slide #", "slide"), ("Slide name", "slide_name"), ("Media", "media"), ("Type", "kind"),
    ("Duration", "duration"), ("Trimmed to", "trimmed"), ("Starts", "starts"), ("Loop", "loop"),
    ("Full screen", "full_screen"), ("Hidden when stopped", "hidden"), ("Volume", "volume"),
    ("Embedded or linked", "storage"), ("Format", "format"), ("Codec", "codec"), ("Resolution", "resolution"),
    ("Size (MB)", "mb"), ("Mac/PC risk", "risk"),
]
DOWNLOAD_COLUMNS = [("Slide #", "slide"), ("Slide name", "slide_name"), ("Site", "site"),
                    ("Found in", "found_in"), ("Link", "url"), ("Status", "status")]
STARTS = {"automatic": "Automatically", "click_sequence": "On click {clicks}", "no_timing": "Play button only",
          "on_click": "When clicked", "unknown": "Unknown"}


def inventory_rows(findings) -> list[dict]:
    risks = {(f.slide, f.shape_id): f.message for f in findings if f.check_id == "M004"}
    rows = []
    for f in (f for f in findings if f.check_id == "M002"):
        e = f.evidence
        dur = e.get("duration_s")
        trimmed = None
        if dur and (e.get("trim_start_ms") or e.get("trim_end_ms")):
            trimmed = max(0.0, dur - (e.get("trim_start_ms") or 0) / 1000 - (e.get("trim_end_ms") or 0) / 1000)
        rows.append({
            "slide": f.slide, "slide_name": e.get("slide_name"), "media": f"{f.shape_name} ({Path(e['file']).name})",
            "kind": e["kind"].capitalize(), "duration": _clock(dur), "trimmed": _clock(trimmed),
            "starts": STARTS[e["mode"]].format(clicks=e.get("clicks")),
            "loop": _yes(e["loop"]), "full_screen": _yes(e["full_screen"]), "hidden": _yes(e["hidden_when_stopped"]),
            "volume": "" if e.get("volume") is None else ("MUTED" if e["volume"] == 0 else f"{e['volume']}%"),
            "storage": "Linked" if e["linked"] else "Embedded",
            "format": Path(e["file"]).suffix.lstrip(".").upper(),
            "codec": " / ".join(c for c in (e.get("video_codec"), e.get("audio_codec")) if c),
            "resolution": f"{e['width']}×{e['height']}" if e.get("width") else "",
            "mb": e.get("mb", ""), "risk": risks.get((f.slide, f.shape_id), ""),
            "_seconds": trimmed if trimmed is not None else dur,
        })
    return rows


def totals(rows: list[dict]) -> str:
    videos = sum(1 for r in rows if r["kind"] == "Video")
    run = sum(r["_seconds"] or 0 for r in rows)
    mb = sum(r["mb"] or 0 for r in rows if isinstance(r["mb"], (int, float)))
    return f"{videos} video{'s' * (videos != 1)}, {len(rows) - videos} audio · total runtime {_clock(run) or '0:00'} · {mb:,.1f} MB"


def download_rows(findings) -> list[dict]:
    rows = []
    for f in findings:
        if f.check_id not in ("M005", "M006"):
            continue
        e = f.evidence
        rows.append({"slide": f.slide, "slide_name": e.get("slide_name"), "site": e.get("site"),
                     "found_in": e.get("found_in", "embedded player"), "url": e["url"],
                     "status": "Online video: needs internet" if f.check_id == "M005" else "Download if it plays in the show"})
    return sorted(rows, key=lambda r: r["slide"])


def write_csv(path: Path, columns, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:   # BOM so Excel reads UTF-8
        w = csv.writer(fh)
        w.writerow([c for c, _ in columns])
        for r in rows:
            w.writerow([r.get(k, "") for _, k in columns])


def write_xlsx(path: Path, inventory: list[dict], downloads: list[dict]):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    for i, (title, columns, rows, footer) in enumerate((
            ("Media", INVENTORY_COLUMNS, inventory, totals(inventory)),
            ("To download", DOWNLOAD_COLUMNS, downloads, f"{len(downloads)} link{'s' * (len(downloads) != 1)}"))):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = title
        ws.append([c for c, _ in columns])
        for r in rows:
            ws.append([r.get(k, "") for _, k in columns])
        ws.append([])
        ws.append([footer])
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
        # SPEC: columns sized so all text is visible, never spilling into the next cell.
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None and c.row <= len(rows) + 1) if rows else 10
            ws.column_dimensions[col[0].column_letter].width = min(max(width, 8) + 2, 80)
            for c in col:
                c.alignment = Alignment(vertical="top", wrap_text=False)
    wb.save(path)


def _clock(seconds) -> str:
    if seconds is None:
        return ""
    s = round(seconds)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _yes(flag) -> str:
    return "Yes" if flag else ""
