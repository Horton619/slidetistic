"""The Mac installer window's background (David 2026-10-12): a disk image people open and drag SlideTistic into
Applications from. Running the app straight from the disk image or Downloads leaves it on a read-only copy that
can't update itself (0.4.0 → 0.4.3 failed that way), so the window says where it goes and why.

Layout matches package.json build.dmg: 540×480 window, app icon at (175, 245), Applications at (385, 245).
The window is 480 tall, not 380, because macOS 26 Finder always shows the toolbar and status bar on DMG windows
(96 px: 68 top, 28 bottom), even though the .DS_Store asks to hide them. Finder places icons and the background
from the top of the content area, so every y below is unchanged; the extra 100 px at the bottom is plain navy, so
a Finder that does hide the chrome shows background instead of a blank strip (same fix as SlideFluid 0213bad).
Writes build/dmg-bg.png and build/dmg-bg@2x.png.   venv/bin/python scripts/make_dmg_background.py
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BG, TEXT, DIM, ACCENT = (7, 9, 16), (221, 226, 240), (138, 155, 191), (155, 140, 255)
FONT = Path(os.environ.get("BRAND_FONT", Path.home() / "Library/Fonts/Montserrat-VariableFont_wght.ttf"))


def font(size, weight="Bold"):
    f = ImageFont.truetype(str(FONT), size)
    try:
        f.set_variation_by_name(weight)
    except (OSError, ValueError):
        pass
    return f


def draw(scale: int) -> Image.Image:
    W, H = 540 * scale, 480 * scale
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    logo = Image.open(ROOT / "assets/brand/png/logo-lockup-dark@2x.png").convert("RGBA")
    lw = 220 * scale
    logo = logo.resize((lw, int(logo.height * lw / logo.width)), Image.LANCZOS)
    img.paste(logo, ((W - lw) // 2, 34 * scale), logo)
    head = "Drag SlideTistic into Applications"
    f = font(19 * scale)
    d.text(((W - d.textlength(head, font=f)) / 2, 128 * scale), head, font=f, fill=TEXT)
    # Arrow from the app icon to Applications (icons are centred at x 175 and 385, y 245).
    y, x0, x1 = 245 * scale, 238 * scale, 322 * scale
    d.line([(x0, y), (x1 - 6 * scale, y)], fill=ACCENT, width=4 * scale)
    d.polygon([(x1, y), (x1 - 14 * scale, y - 9 * scale), (x1 - 14 * scale, y + 9 * scale)], fill=ACCENT)
    note = "Open it from Applications, so it can update itself."
    f2 = font(12 * scale, "Medium")
    d.text(((W - d.textlength(note, font=f2)) / 2, 328 * scale), note, font=f2, fill=DIM)
    brand = "Visual Entropy Productions"
    f3 = font(9 * scale, "Medium")
    d.text(((W - d.textlength(brand, font=f3)) / 2, 356 * scale), brand, font=f3, fill=(74, 88, 120))
    return img


if __name__ == "__main__":
    (ROOT / "build").mkdir(exist_ok=True)
    draw(1).save(ROOT / "build/dmg-bg.png")
    draw(2).save(ROOT / "build/dmg-bg@2x.png")
    print("wrote build/dmg-bg.png and build/dmg-bg@2x.png")
