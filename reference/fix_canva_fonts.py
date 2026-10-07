#!/usr/bin/env python3
"""
fix_canva_fonts.py  -  normalize font references in Canva/Google-exported .pptx files.

Problem it fixes:
  Canva exports reference each weight as its own font family ("Calibri (MS) Bold",
  "Roboto Bold") and embeds every font in the <p:regular> slot under that fake name,
  even though the font file inside is family "Calibri (MS)" / "Roboto", style Bold.
  Windows PowerPoint loads embedded fonts under the name the deck asks for, so it copes.
  Mac PowerPoint apparently does not, so it substitutes a fallback font and text reflows.

What it does:
  1. Rewrites typeface names on every run:  "X Bold" -> "X" (+ b="1"), "X Italic" -> "X" (+ i="1"),
     and Canva aliases like "Calibri (MS)" -> "Calibri".
  2. Rebuilds the embedded-font list with real family names and proper regular/bold/italic slots,
     read from the font files themselves.
  3. Drops embedded copies of fonts that ship with Office (Calibri), so the installed one is used.

Usage:  python3 -I fix_canva_fonts.py input.pptx output.pptx
"""
import io, re, struct, sys, zipfile
from fontTools.ttLib import TTFont

ALIASES = {"Calibri (MS)": "Calibri"}            # Canva-private names -> real installed family
DROP_EMBED = {"Calibri"}                           # ships with Office on Mac and PC; don't embed
STYLE_SUFFIXES = [(" Bold Italic", "1", "1"), (" Bold", "1", None), (" Italic", None, "1")]


def eot_inner(data):
    """Return (family, bold, italic) for an EOT .fntdata blob (or plain TTF)."""
    try:
        if data[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            ttf = data
        else:
            eotsize, fdsize, ver, flags = struct.unpack_from("<IIII", data, 0)
            weight, = struct.unpack_from("<I", data, 28)
            italic = data[27]
            if flags & 0x4:   # MicroType Express compressed: can't parse; use EOT header only
                o = 82
                names = []
                for _ in range(4):
                    sz, = struct.unpack_from("<H", data, o); o += 2
                    names.append(data[o:o + sz].decode("utf-16le").strip("\x00")); o += sz + 2
                return names[0], weight >= 600, bool(italic)
            ttf = data[len(data) - fdsize:]
        t = TTFont(io.BytesIO(ttf), lazy=True)
        n = t["name"]
        fam = n.getDebugName(16) or n.getDebugName(1)
        sub = (n.getDebugName(17) or n.getDebugName(2) or "").lower()
        return fam, ("bold" in sub or t["OS/2"].usWeightClass >= 600), ("italic" in sub)
    except Exception:
        return None


def normalize_name(name):
    """'Roboto Bold' -> ('Roboto', '1', None); 'Calibri (MS) Bold' -> ('Calibri', '1', None)."""
    b = i = None
    for suf, sb, si in STYLE_SUFFIXES:
        if name.endswith(suf):
            name, b, i = name[: -len(suf)], sb, si
            break
    return ALIASES.get(name, name), b, i


def fix_xml(xml, log):
    def fix_rpr(m):
        tag_open, tagname, body = m.group(1), "<" + m.group(2), m.group(3)
        want_b = want_i = None

        def sub_face(fm):
            nonlocal want_b, want_i
            new, b, i = normalize_name(fm.group(2))
            want_b, want_i = want_b or b, want_i or i
            if new != fm.group(2):
                log[fm.group(2)] = new
            return f'{fm.group(1)}typeface="{new}"'

        body = re.sub(r'(<a:(?:latin|ea|cs|sym) )typeface="([^"]*)"', sub_face, body)
        for attr, want in (("b", want_b), ("i", want_i)):
            if want and not re.search(rf'\s{attr}="', tag_open):
                tag_open = tag_open.replace(tagname, f'{tagname} {attr}="1"', 1)
        return tag_open + body

    # rPr / defRPr / endParaRPr blocks that have child elements
    pat = r'(<(a:(?:rPr|defRPr|endParaRPr))\b[^>]*[^/]>)(.*?)(?=</a:(?:rPr|defRPr|endParaRPr)>)'
    return re.sub(pat, fix_rpr, xml, flags=re.S)


def main(src, dst):
    zin = zipfile.ZipFile(src)
    files = {n: zin.read(n) for n in zin.namelist()}
    renamed = {}

    for n in list(files):
        if n.endswith(".xml") and n.startswith("ppt/") and "/fonts/" not in n:
            x = files[n].decode("utf8")
            if "typeface=" in x:
                files[n] = fix_xml(x, renamed).encode("utf8")

    # ---- rebuild embedded font list
    pres = files["ppt/presentation.xml"].decode("utf8")
    rels = files["ppt/_rels/presentation.xml.rels"].decode("utf8")
    relmap = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="(fonts/[^"]+)"', rels))
    relmap.update({a: b for b, a in re.findall(r'Target="(fonts/[^"]+)"[^>]*Id="(rId\d+)"', rels)})
    families, dropped = {}, []
    for rid, target in relmap.items():
        info = eot_inner(files["ppt/" + target])
        if not info:
            continue
        fam, bold, ital = info
        fam = ALIASES.get(fam, fam)
        if fam in DROP_EMBED:
            dropped.append((fam, target, rid))
            continue
        slot = {(0, 0): "regular", (1, 0): "bold", (0, 1): "italic", (1, 1): "boldItalic"}[(int(bold), int(ital))]
        families.setdefault(fam, {})[slot] = rid

    if "<p:embeddedFontLst>" in pres:
        order = ["regular", "bold", "italic", "boldItalic"]
        lst = "".join(
            f'<p:embeddedFont><p:font typeface="{f}"/>'
            + "".join(f'<p:{s} r:id="{slots[s]}"/>' for s in order if s in slots)
            + "</p:embeddedFont>" for f, slots in sorted(families.items()))
        pres = re.sub(r"<p:embeddedFontLst>.*?</p:embeddedFontLst>",
                      f"<p:embeddedFontLst>{lst}</p:embeddedFontLst>" if lst else "", pres, flags=re.S)
        files["ppt/presentation.xml"] = pres.encode("utf8")
        for fam, target, rid in dropped:
            rels = re.sub(rf'<Relationship [^>]*Id="{rid}"[^>]*/>', "", rels)
            files.pop("ppt/" + target, None)
        files["ppt/_rels/presentation.xml.rels"] = rels.encode("utf8")

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            if n in files:
                zout.writestr(zin.getinfo(n), files[n])

    print("Renamed typefaces:")
    for a, b in sorted(renamed.items()):
        print(f"  {a!r:24} -> {b!r}")
    print("Embedded fonts now:")
    for f, s in sorted(families.items()):
        print(f"  {f}: {', '.join(s)}")
    if dropped:
        print("Dropped embeds (use installed copy):", ", ".join(sorted({d[0] for d in dropped})))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
