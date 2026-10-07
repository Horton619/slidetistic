"""Builds every shipped brand file from the hand-drawn sources in this folder.

    venv/bin/python assets/brand/build_brand.py

Sources (edit these):  icon-engine.svg, icon-engine-small.svg, src/lockup.svg
Outputs (never edit):  logo-lockup-dark.svg, logo-lockup-light.svg, png/*, ../icons/icon.icns, ../icons/icon.ico

Needs: rsvg-convert + ImageMagick (`magick`) from Homebrew, iconutil (macOS), and
Montserrat-VariableFont_wght.ttf (OFL) in ~/Library/Fonts or $BRAND_FONT.
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

HERE = Path(__file__).resolve().parent
ICONS = HERE.parent / "icons"
PNG = HERE / "png"
FONT = Path(os.environ.get("BRAND_FONT", Path.home() / "Library/Fonts/Montserrat-VariableFont_wght.ttf"))

# Dark → light: wheels/windows flip to white, light-grey bodies to navy, violet darkens for
# contrast on white. Placeholders avoid swapping a colour twice.
LIGHT_MAP = {
    "#DDE2F0": "#141B2D", "#070910": "#FFFFFF", "#8A9BBF": "#4A5878", "#4A5878": "#8A9BBF",
    "#141B2D": "#EEF0F7", "#9B8CFF": "#6E5BEA", "#120B33": "#FFFFFF",
}


def load_font() -> TTFont:
    font = TTFont(FONT)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": 700})
    return font


def text_path(font: TTFont, text: str, x: float, baseline: float, size: float,
              tracking: float = 0, anchor: str = "start") -> tuple[str, float]:
    """SVG path data for `text` as outlines. Returns (d, advance width in px)."""
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    names = [cmap[ord(c)] for c in text]
    width = sum(hmtx[n][0] * scale + tracking for n in names) - tracking
    pen_x = x - (width / 2 if anchor == "middle" else 0)
    parts = []
    for n in names:
        pen = SVGPathPen(glyphs)
        glyphs[n].draw(TransformPen(pen, (scale, 0, 0, -scale, pen_x, baseline)))
        parts.append(pen.getCommands())
        pen_x += hmtx[n][0] * scale + tracking
    return " ".join(p for p in parts if p), width


def outline_texts(svg: str, font: TTFont) -> str:
    """Replace each <text data-outline …> with outlined <path>s. tspans become their own paths."""
    def repl(m):
        attrs, body = m.group(1), m.group(2)
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        x, y, size = float(a["x"]), float(a["y"]), float(a["font-size"])
        tracking, anchor = float(a.get("letter-spacing", 0)), a.get("text-anchor", "start")
        runs = [(a["fill"], t) for t in [re.sub(r"<tspan.*", "", body, flags=re.S)] if t]
        runs += re.findall(r'<tspan fill="([^"]+)">([^<]*)</tspan>', body)
        out, cur = [], x
        if anchor == "middle":
            cur -= sum(text_path(font, t, 0, 0, size, tracking)[1] for _, t in runs) / 2
        for fill, t in runs:
            d, w = text_path(font, t, cur, y, size, tracking)
            out.append(f'<path fill="{fill}" d="{d}"/>')
            cur += w + tracking
        return "\n".join(out)
    return re.sub(r"<text data-outline([^>]*)>(.*?)</text>", repl, svg, flags=re.S)


def recolor(svg: str, mapping: dict) -> str:
    for i, src in enumerate(mapping):
        svg = svg.replace(src, f"@{i}@")
    for i, dst in enumerate(mapping.values()):
        svg = svg.replace(f"@{i}@", dst)
    return svg


def rsvg(src: Path, out: Path, width: int, height: int | None = None):
    args = ["rsvg-convert", "-w", str(width)] + (["-h", str(height)] if height else []) + ["-o", str(out), str(src)]
    subprocess.run(args, check=True)


def mac_icon(src: Path, out: Path, size: int, tmp: Path):
    """Apple's grid: the rounded square fills 824/1024 of the canvas, centred, transparent margin."""
    body = max(1, round(size * 824 / 1024))
    art = tmp / f"body_{size}.png"
    rsvg(src, art, body, body)
    subprocess.run(["magick", str(art), "-background", "none", "-gravity", "center",
                    "-extent", f"{size}x{size}", str(out)], check=True)


def main():
    font = load_font()
    PNG.mkdir(exist_ok=True)
    ICONS.mkdir(exist_ok=True)

    dark = outline_texts((HERE / "src" / "lockup.svg").read_text(), font)
    (HERE / "logo-lockup-dark.svg").write_text(dark)
    (HERE / "logo-lockup-light.svg").write_text(recolor(dark, LIGHT_MAP))

    big, small = HERE / "icon-engine.svg", HERE / "icon-engine-small.svg"
    for name in ("logo-lockup-dark", "logo-lockup-light"):
        rsvg(HERE / f"{name}.svg", PNG / f"{name}.png", 540)
        rsvg(HERE / f"{name}.svg", PNG / f"{name}@2x.png", 1080)
    rsvg(big, PNG / "icon-1024.png", 1024)
    rsvg(big, PNG / "icon-512.png", 512)
    rsvg(small, PNG / "icon-32.png", 32)
    rsvg(small, PNG / "icon-16.png", 16)

    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        iconset = tmp / "icon.iconset"
        iconset.mkdir()
        for base in (16, 32, 128, 256, 512):
            for mult, suffix in ((1, ""), (2, "@2x")):
                px = base * mult
                mac_icon(small if px <= 32 else big, iconset / f"icon_{base}x{base}{suffix}.png", px, tmp)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(ICONS / "icon.icns")], check=True)

        layers = []
        for px in (16, 24, 32, 48, 64, 128, 256):
            p = tmp / f"win_{px}.png"
            rsvg(small if px <= 32 else big, p, px, px)
            layers.append(str(p))
        subprocess.run(["magick", *layers, str(ICONS / "icon.ico")], check=True)

    shutil.copy(PNG / "icon-1024.png", ICONS / "icon.png")
    print("Built:", *sorted(p.relative_to(HERE.parent) for p in [*PNG.iterdir(), *ICONS.iterdir()]), sep="\n  ")


if __name__ == "__main__":
    main()
