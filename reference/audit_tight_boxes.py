#!/usr/bin/env python3
"""
audit_tight_boxes.py - flag text boxes with too little horizontal slack, or that sit off-slide.

Measures each line with the deck's own embedded font files (exact advance widths),
re-wraps paragraphs greedily at the box width, and reports any line that fills
more than THRESH of the available width. Those are the boxes that reflow when a
different layout engine (Mac vs PC, PowerPoint vs Canva) measures text slightly wider.

Usage: python3 -I audit_tight_boxes.py deck.pptx [thresh=0.97]
Notes: ignores kerning (slightly overestimates width); skips runs whose font isn't embedded.
"""
import io, re, struct, sys, zipfile
from fontTools.ttLib import TTFont

EMU_IN = 914400
THRESH = float(sys.argv[2]) if len(sys.argv) > 2 else 0.97


def load_fonts(z):
    fonts = {}
    for n in z.namelist():
        if not n.startswith("ppt/fonts/"):
            continue
        d = z.read(n)
        try:
            flags = struct.unpack_from("<I", d, 12)[0]
            if flags & 0x4:
                continue  # MTX-compressed, can't read metrics
            fd = struct.unpack_from("<I", d, 4)[0]
            t = TTFont(io.BytesIO(d[len(d) - fd:]))
        except Exception:
            continue
        nm = t["name"]
        fam = nm.getDebugName(16) or nm.getDebugName(1)
        bold = t["OS/2"].usWeightClass >= 600
        fam = {"Calibri (MS)": "Calibri"}.get(fam, fam)
        fonts[(fam, bold)] = (t.getBestCmap(), t["hmtx"], t["head"].unitsPerEm)
    return fonts


def text_w(f, s, pt):
    cmap, hm, upm = f
    return sum(hm[cmap.get(ord(c), ".notdef")][0] for c in s) / upm * pt / 72


def main(path):
    z = zipfile.ZipFile(path)
    fonts = load_fonts(z)
    pres = z.read("ppt/presentation.xml").decode()
    sw = int(re.search(r'<p:sldSz cx="(\d+)"', pres).group(1))
    slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                    key=lambda n: int(re.search(r"(\d+)", n.split("/")[-1]).group(1)))
    for sn in slides:
        num = int(re.search(r"(\d+)", sn.split("/")[-1]).group(1))
        x = z.read(sn).decode("utf8")
        in_group = set()
        for g in re.findall(r"<p:grpSp>.*?</p:grpSp>", x, re.S):
            in_group.update(re.findall(r'<p:cNvPr [^>]*name="([^"]*)"', g))
        for sp in re.findall(r"<p:sp>.*?</p:sp>", x, re.S):
            if "<a:t>" not in sp:
                continue
            name = re.search(r'<p:cNvPr [^>]*name="([^"]*)"', sp).group(1)
            off = re.search(r'<a:off x="(-?\d+)" y="(-?\d+)"/>', sp)
            ext = re.search(r'<a:ext cx="(\d+)" cy="(\d+)"/>', sp)
            if not (off and ext):
                continue
            ox, cx = int(off.group(1)), int(ext.group(1))
            body = re.search(r"<a:bodyPr([^>]*)", sp).group(1)
            ins = lambda k, d: int((re.search(rf'{k}="(\d+)"', body) or [None, d])[1])
            avail = (cx - ins("lIns", 91440) - ins("rIns", 91440)) / EMU_IN
            issues = []
            if name not in in_group and (ox < 0 or ox + cx > sw):
                issues.append(f"box extends off-slide (x {ox/EMU_IN:+.2f}in to {(ox+cx)/EMU_IN:.2f}in, slide {sw/EMU_IN:.2f}in)")
            for para in re.findall(r"<a:p>.*?</a:p>", sp, re.S):
                runs = re.findall(r"<a:r>(.*?)</a:r>", para, re.S)
                if not runs:
                    continue
                # use the first run's font/size for the paragraph (good enough for an audit)
                r0 = runs[0]
                face = re.search(r'<a:latin typeface="([^"]+)"', r0)
                sz = re.search(r' sz="(\d+)"', r0)
                bold = ' b="1"' in r0
                text = "".join(re.findall(r"<a:t>([^<]*)</a:t>", para))
                text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
                if not (face and sz and text.strip()):
                    continue
                fam = face.group(1)
                for suf in (" Bold Italic", " Bold", " Italic"):
                    if fam.endswith(suf):
                        fam, bold = fam[: -len(suf)], bold or "Bold" in suf
                        break
                fam = {"Calibri (MS)": "Calibri"}.get(fam, fam)
                f = fonts.get((fam, bold))
                if not f:
                    continue
                pt = int(sz.group(1)) / 100
                indent = 0.0
                m = re.search(r'<a:pPr[^>]*marL="(\d+)"', para)
                if m:
                    indent = int(m.group(1)) / EMU_IN
                width = avail - indent
                line, worst = "", (0, "")
                for word in text.split(" "):
                    trial = (line + " " + word) if line else word
                    if text_w(f, trial, pt) <= width or not line:
                        line = trial
                    else:
                        fill = text_w(f, line, pt) / width
                        worst = max(worst, (fill, line))
                        over = text_w(f, trial, pt) / width   # would the next word *almost* fit?
                        if over <= 2 - THRESH:
                            worst = max(worst, (over, trial))
                        line = word
                fill = text_w(f, line, pt) / width
                worst = max(worst, (fill, line))
                if worst[0] >= THRESH:
                    issues.append(f"{worst[0]*100:5.1f}% {'OVER' if worst[0] > 1 else 'full'}: \"{worst[1][:60]}\" ({fam}{' Bold' if bold else ''} {pt:g}pt)")
            for i in issues:
                print(f"slide {num:2d}  {name:12s} {i}")


if __name__ == "__main__":
    main(sys.argv[1])
