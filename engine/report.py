"""Self-contained HTML report (SPEC §4.3): summary, visual review, findings, media, changes, checks."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from . import __version__, export, visual
from .core import Status

CSS = """
:root{--bg:#070910;--surface:#0E1420;--surface-2:#141B2D;--border:#1E2840;--accent:#9B8CFF;--text:#DDE2F0;
--dim:#8A9BBF;--muted:#4A5878;--green:#34D399;--amber:#FFB547;--red:#FF5A5F;--blue:#5B9BFF}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,-apple-system,'Segoe UI',sans-serif}
main{max-width:1240px;margin:0 auto;padding:28px 20px 80px}
.eyebrow{color:var(--accent);letter-spacing:.18em;text-transform:uppercase;font-size:11px;font-weight:600}
h1{margin:4px 0 2px;font-size:24px}h2{font-size:17px;margin:34px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.meta{color:var(--dim);font-size:13px}.bar{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}
.pill{display:flex;align-items:center;gap:8px;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-weight:600}
.pill b{font-size:20px}.g{color:var(--green)}.y{color:var(--amber)}.r{color:var(--red)}.i{color:var(--blue)}
.slide{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px}
.slide h3{margin:0 0 10px;font-size:14px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}.single{max-width:640px}
.frame{margin-top:18px}
@media(max-width:800px){.pair{grid-template-columns:1fr}}
.frame{position:relative;border:1px solid var(--border);border-radius:6px;background:#fff}
.frame img{border-radius:5px}
.frame img{display:block;width:100%}.cap{display:block;color:var(--dim);font-size:12px;margin:0 0 4px}
.box{position:absolute;--k:var(--accent);outline:2px solid var(--k);outline-offset:3px;border-radius:2px;cursor:help}
.box.font{--k:#9B8CFF}.box.placement{--k:#22D3EE}.box.layout{--k:#F472B6}.box.media{--k:#60A5FA}.box.content{--k:#E5E7EB}
.box.yellow{outline-style:dashed}.box.red{outline-width:3px}.box.note{outline-style:dotted;opacity:.55}
.box .tag{display:none;position:absolute;left:-3px;top:-21px;z-index:3;background:var(--k);color:#070910;font-size:10px;font-weight:700;padding:1px 5px;border-radius:3px;white-space:nowrap}
.box.red .tag,.box:hover .tag{display:block}.box.red .tag::before{content:"✕ ";color:#7a0010}
.box:hover{z-index:4}
.box:hover::after{content:attr(data-label);position:absolute;left:0;top:100%;margin-top:6px;z-index:5;width:max-content;max-width:380px;
background:var(--surface-2);color:var(--text);border:1px solid var(--border);padding:7px 9px;border-radius:6px;font-size:12px;white-space:pre-line}
.box.flip:hover::after{left:auto;right:0}
.alert{background:rgba(255,90,95,.12);border:1px solid var(--red);color:var(--text);border-radius:8px;padding:12px 14px;margin:14px 0;font-weight:600}
.alert a{color:var(--red)}.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--dim);margin:6px 0 14px}
.legend span{display:inline-flex;align-items:center;gap:6px}.sw{width:14px;height:10px;border:2px solid;border-radius:2px}
.tier{margin:22px 0 10px;font-size:15px}.tier small{color:var(--dim);font-weight:400}
.why{color:var(--dim);font-size:12px;margin-top:3px}
.source{background:rgba(155,140,255,.12);border:1px solid var(--accent);border-radius:8px;padding:12px 14px;margin:14px 0}
.source b{color:var(--accent);letter-spacing:.06em}.source span{color:var(--dim);font-size:12px;display:block;margin-top:3px}
.placeholder{display:flex;align-items:center;justify-content:center;aspect-ratio:16/9;color:var(--muted);background:var(--surface-2)}
.chips{display:flex;gap:8px;margin-bottom:10px}.chip{background:var(--surface);border:1px solid var(--border);color:var(--dim);border-radius:14px;padding:4px 12px;cursor:pointer;font:inherit}
.chip.on{border-color:var(--accent);color:var(--text)}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:top}
th{color:var(--dim);font-weight:600;position:sticky;top:0;background:var(--bg)}td.s{white-space:nowrap;font-weight:600}
.wrap{overflow-x:auto}.note{color:var(--dim);font-size:13px}a{color:var(--accent)}
footer{position:fixed;bottom:0;left:0;right:0;z-index:10;pointer-events:none;display:flex;justify-content:space-between;padding:8px 20px;
background:var(--bg);border-top:1px solid var(--border);color:var(--muted);font-size:12px}footer a{pointer-events:auto;color:var(--muted)}
"""

ICON = {Status.GREEN_FIXED: ("✓", "g", "Fixed"), Status.YELLOW: ("!", "y", "Look at"),
        Status.RED: ("✕", "r", "Broken"), Status.TOOL_ERROR: ("?", "r", "Couldn't run"),
        Status.GREEN_CLEAN: ("i", "i", "Info")}

JS = """
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{
 document.querySelectorAll('.chip').forEach(x=>x.classList.toggle('on',x===c));
 const f=c.dataset.f;document.querySelectorAll('#findings tbody tr').forEach(r=>r.hidden=!(f==='all'||r.dataset.s===f));});
"""


def e(x) -> str:
    return html.escape("" if x is None else str(x))


def build(result, checks, out: Path, *, source: str | None = None, visuals=None, visual_note: str = "",
          config=None, diagnostic: bool = True) -> Path:
    """diagnostic: show the rule behind every call (on while SlideTistic is being tuned)."""
    s = result.summary()
    findings = sorted(result.findings, key=lambda f: (f.slide or 0, f.check_id))
    problems = [f for f in findings if not f.informational]
    deck_name = Path(result.input_path).name
    titles = {c.id: c.title for c in checks}
    parts = [f"<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>SlideTistic report · {e(deck_name)}</title><style>{CSS}</style></head><body><main>"]

    parts.append(f"<div class=eyebrow>SlideTistic report</div><h1>{e(deck_name)}</h1><div class=meta>"
                 + " · ".join(x for x in (source and e(source),
                                          f"Saved as <b>{e(Path(result.output_path).name)}</b>" if result.output_path else "Scan only, nothing changed",
                                          datetime.now().strftime("%Y-%m-%d %H:%M"), f"engine {__version__}") if x)
                 + "</div>")
    fixed, look, broken = s["green_fixed"], s["yellow"], s["red"] + s["tool_error"]
    parts.append("<div class=bar>"
                 f"<div class='pill g'>✓ <b>{fixed}</b> fixed</div><div class='pill y'>! <b>{look}</b> to look at</div>"
                 f"<div class='pill r'>✕ <b>{broken}</b> still broken</div>"
                 f"<div class='pill i'>{len(result.changes)} change{'s' * (len(result.changes) != 1)} made</div></div>")

    banner = _source_banner(findings)
    if banner:
        parts.append(banner)

    off = sorted({f.slide for f in findings if f.status == Status.RED and f.subject == "off-slide" and f.slide})
    if off:
        parts.append("<div class=alert>✕ Text runs off the slide on slide" + "s" * (len(off) > 1) + " "
                     + ", ".join(f"<a href='#slide-{n}'>{n}</a>" for n in off) + ". Fix these before the show.</div>")

    parts.append("<h2>Visual review</h2>")
    if visuals:
        parts.append("<p class=note>As PowerPoint draws them. Hover a box for details"
                     + (" and the rule behind it." if diagnostic else ".") + "</p><div class=legend>"
                     + "".join(f"<span><i class=sw style='border-color:{c}'></i>{visual.KIND_LABEL[k]}</span>"
                               for k, c in (("font", "#9B8CFF"), ("placement", "#22D3EE"), ("layout", "#F472B6"),
                                            ("media", "#60A5FA"), ("content", "#E5E7EB")))
                     + "<span>━ changed · ┅ needs a look · ✕ broken</span></div>")
        for tier in (1, 2, 3):
            block = [v for v in visuals if v.tier == tier]
            if not block:
                continue
            parts.append(f"<h3 class=tier>{tier}. {e(visual.TIERS[tier])} <small>· {len(block)} slide"
                         f"{'s' * (len(block) != 1)}</small></h3>")
            for v in block:
                pair = (_frame("Before", v.before_png, v.before_boxes, diagnostic)
                        + _frame("After", v.after_png, v.after_boxes, diagnostic)) if result.output_path else \
                    _frame("As PowerPoint draws it", v.before_png, v.before_boxes, diagnostic)
                parts.append(f"<section class=slide id=slide-{v.slide}><h3>Slide {v.slide}</h3>"
                             f"<div class={'pair' if result.output_path else 'single'}>{pair}</div></section>")
        for tier in (4, 5):
            same = [v.slide for v in visuals if v.tier == tier]
            if same:
                parts.append(f"<h3 class=tier>{tier}. {e(visual.TIERS[tier])} <small>· slide{'s' * (len(same) > 1)} "
                             f"{e(_ranges(same))}</small></h3>")
    else:
        parts.append(f"<p class=note>{e(visual_note or 'No slide changed visually.')}</p>")

    order = {Status.RED: 0, Status.TOOL_ERROR: 1, Status.YELLOW: 2, Status.GREEN_FIXED: 3}
    parts.append("<h2>Findings</h2><div class=chips>"
                 + "".join(f"<button class='chip{' on' * (k == 'all')}' data-f={k}>{label}</button>"
                           for k, label in (("all", "All"), ("red", "✕ Broken"), ("yellow", "! Look at"), ("green_fixed", "✓ Fixed")))
                 + "</div><div class=wrap><table id=findings><thead><tr><th></th><th>Where</th><th>Check</th><th>What</th></tr></thead><tbody>")
    for f in sorted(problems, key=lambda f: (order.get(f.status, 9), f.slide or 0, f.check_id)):
        icon, cls, word = ICON[f.status]
        where = f"<a href='#slide-{f.slide}'>Slide {f.slide}</a>" + (f" · {e(f.shape_name)}" if f.shape_name else "") \
            if f.slide else "Whole deck"
        why = _why(f) if diagnostic else ""
        parts.append(f"<tr data-s={f.status.value}><td class='s {cls}'>{icon} {word}</td><td>{where}</td>"
                     f"<td>{e(f.check_id)} {e(titles.get(f.check_id, ''))}</td><td>{e(f.message)}"
                     + (f"<div class=why>{e(f.evidence['fix_result'])}</div>" if f.evidence.get("fix_result") else "")
                     + (f"<div class=why>Introduced by {e(f.evidence['introduced_by'])}</div>" if f.evidence.get("introduced_by") else "")
                     + (f"<div class=why>Why: {e(why)}</div>" if why else "")
                     + "</td></tr>")
    if not problems:
        parts.append("<tr><td colspan=4 class=note>Nothing to report. Clean deck.</td></tr>")
    parts.append("</tbody></table></div>")

    info = [f for f in findings if f.informational and f.check_id not in ("M002",)]
    if info:
        parts.append("<h2>About this deck</h2><ul class=note>" + "".join(
            f"<li>{'Slide ' + str(f.slide) + ': ' if f.slide else ''}{e(f.message)}</li>" for f in info) + "</ul>")

    inventory, downloads = export.inventory_rows(result.findings), export.download_rows(result.findings)
    parts.append("<h2>Media</h2>")
    if inventory:
        parts.append(_table(export.INVENTORY_COLUMNS, inventory) + f"<p class=note>{e(export.totals(inventory))}</p>")
    else:
        parts.append("<p class=note>No video or audio in this deck.</p>")
    if downloads:
        parts.append("<h2>To download</h2><p class=note>Fetch these and embed them before the show.</p>"
                     + _table(export.DOWNLOAD_COLUMNS, downloads, link_key="url"))

    if result.changes:
        parts.append("<h2>Changes</h2><div class=wrap><table><thead><tr><th>Check</th><th>Where</th><th>What</th><th>Before</th><th>After</th></tr></thead><tbody>")
        for c in result.changes[:2000]:
            where = f"Slide {c.slide} · {e(c.shape_name)}" if c.slide else e(c.part or "deck")
            parts.append(f"<tr><td>{e(c.check_id)}</td><td>{where}</td><td>{e(c.prop)}</td><td>{e(c.before)}</td><td>{e(c.after)}</td></tr>")
        parts.append("</tbody></table></div>")
        if len(result.changes) > 2000:
            parts.append(f"<p class=note>…and {len(result.changes) - 2000} more.</p>")

    parts.append("<h2>Checks</h2><div class=wrap><table><thead><tr><th>ID</th><th>Check</th><th>Ran</th><th>Fix</th><th>Version</th></tr></thead><tbody>")
    for c in checks:
        ran = config.check_on(c) if config else True
        fix = "report only" if c.report_only else ("on" if config and config.fix_on(c) else "off")
        parts.append(f"<tr><td>{c.id}</td><td>{e(c.title)}</td><td>{'yes' if ran else 'no'}</td><td>{fix}</td><td>{c.version}</td></tr>")
    parts.append("</tbody></table></div>")

    parts.append(f"</main><footer><span>© {datetime.now().year} Visual Entropy Productions</span>"
                 f"<a href='https://veproductions.net'>veproductions.net</a></footer><script>{JS}</script></body></html>")
    out.write_text("".join(parts), encoding="utf-8")
    return out


def _frame(caption, png, boxes, diagnostic=True) -> str:
    inner = f"<img src='{png}' alt='{caption}'>" if png else "<div class=placeholder>Not rendered (hidden slide)</div>"
    marks = "".join(
        f"<div class='box {b.kind} {b.mode}{' flip' if b.left + b.width / 2 > 50 else ''}' style='left:{b.left:.2f}%;top:{b.top:.2f}%;width:{b.width:.2f}%;height:{b.height:.2f}%'"
        f" data-label='{e(b.label + (chr(10) + 'Why: ' + b.detail if diagnostic and b.detail else ''))}'>"
        f"<span class=tag>{e(visual.KIND_LABEL[b.kind])}</span></div>" for b in boxes)
    return f"<div><span class=cap>{caption}</span><div class=frame>{inner}{marks}</div></div>"


# David 2026-10-10: shout it when the deck came from somewhere other than PowerPoint.
SOURCE_SHOUT = {
    "canva": ("CANVA DETECTED!", "Buckle up, we got a gRaPhIc dEsIgNeR on our hands."),
    "google": ("GOOGLE SLIDES DETECTED!", "Someone \u201ccollaborated\u201d on this. Expect stand-in fonts and links to YouTube."),
    "keynote": ("KEYNOTE DETECTED!", "Bold of them to assume the show machine has Avenir."),
    "pdf": ("PDF IN A TRENCH COAT DETECTED!", "Every slide is a picture. Nothing here can be edited, only looked at."),
}


def _source_banner(findings) -> str:
    f = next((f for f in findings if f.check_id == "X001"), None)
    if not f or f.subject not in SOURCE_SHOUT:
        return ""
    title, joke = SOURCE_SHOUT[f.subject]
    return f"<div class=source><b>{e(title)}</b> {e(joke)}<span>{e(f.message)}</span></div>"


NOISY = {"box_emu", "box_in", "slides", "seconds", "names", "urls", "text_shapes", "slots", "signals"}


def _why(f) -> str:
    """The rule behind a finding, or a compact dump of its evidence when a check doesn't state one."""
    if f.evidence.get("rule"):
        return f.evidence["rule"]
    bits = [f"{k}={v}" for k, v in f.evidence.items()
            if k not in NOISY | {"fix_result", "introduced_by"} and v not in (None, "", [], {})]
    return "; ".join(bits)[:300]


def _ranges(nums) -> str:
    out, start = [], None
    for i, n in enumerate(nums):
        start = n if start is None else start
        if i + 1 == len(nums) or nums[i + 1] != n + 1:
            out.append(str(start) if start == n else f"{start}–{n}")
            start = None
    return ", ".join(out)


def _table(columns, rows, link_key=None) -> str:
    head = "".join(f"<th>{e(c)}</th>" for c, _ in columns)
    body = "".join("<tr>" + "".join(
        f"<td><a href='{e(r[k])}'>{e(r[k])}</a></td>" if k == link_key else f"<td>{e(r.get(k, ''))}</td>"
        for _, k in columns) + "</tr>" for r in rows)
    return f"<div class=wrap><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
