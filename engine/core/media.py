"""Video/audio on slides: what's there, how it starts, and its playback settings.

Every timing pattern here was read from decks saved by real PowerPoint (Mac and Windows, corpus
2026-10-09; samples in tests/fixtures/media_modes/). Anything else is reported as "unknown", never
guessed. See CLAUDE.md "Never guess PowerPoint XML".

  Automatically     play effect (mediacall, presetID 1) is nodeType="afterEffect" in the first click
                    group of the main sequence, and that group starts on evt="onBegin" of mainSeq
  In click sequence play effect is nodeType="clickEffect"; it needs one click per click group up to it
  When Clicked On   no play effect in the main sequence; only the self-trigger (interactiveSeq on the
                    video, mediacall presetID 2). Seen in 8 Dropbox-corpus videos (Mac + Win) and it is
                    byte-for-byte a click-sequence save minus its main-sequence <p:seq> block. Inferred:
                    confirm with a deck saved with Start = "When Clicked On" (docs/BROKEN_DECK_RECIPE.md)
  No timing         no play effect at all: the video waits for someone to press its play control
  Full screen       <p:video fullScrn="1">      Loop: repeatCount="indefinite" on the media node's cTn
  Hidden            <p:cMediaNode showWhenStopped="0">     Volume: vol (0-100000), mute="1"
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from pptx.oxml.ns import qn

P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
EFFECT_TYPES = ("clickEffect", "withEffect", "afterEffect")


@dataclass
class MediaItem:
    slide: int
    shape_id: int
    shape_name: str
    kind: str                         # "video" | "audio"
    pic: object                       # the p:pic element
    slide_part: object
    linked: bool                      # True when the file lives outside the deck
    target: str                       # package part name, or the external path/URL
    media_part: object | None         # the embedded media part, when embedded
    mode: str = "no_timing"           # automatic | click_sequence | on_click | no_timing | unknown
    clicks: int | None = None         # clicks needed before it starts (click_sequence)
    play_ctn: object = None           # the play effect's p:cTn
    group_par: object = None          # its click group's p:par
    main_seq_id: str | None = None
    volume: int | None = None         # percent
    muted: bool = False
    hidden_when_stopped: bool = False
    full_screen: bool = False
    loop: bool = False
    trim_start_ms: float | None = None
    trim_end_ms: float | None = None
    probe: dict | None = field(default=None, repr=False)


def media_items(deck) -> list[MediaItem]:
    items = []
    for n, slide in enumerate(deck.slides, 1):
        root = slide.part._element
        for pic in root.iter(qn("p:pic")):
            nv_pr = pic.find(f"{qn('p:nvPicPr')}/{qn('p:nvPr')}")
            if nv_pr is None:
                continue
            file_el = nv_pr.find(qn("a:videoFile"))
            kind = "video"
            if file_el is None:
                file_el, kind = nv_pr.find(qn("a:audioFile")), "audio"
            if file_el is None:
                continue
            c_nv = pic.find(f"{qn('p:nvPicPr')}/{qn('p:cNvPr')}")
            item = MediaItem(n, int(c_nv.get("id")), c_nv.get("name"), kind, pic, slide.part,
                             *_locate(slide.part, file_el, nv_pr))
            _read_timing(root, item)
            _read_trim(nv_pr, item)
            items.append(item)
    return items


def _locate(part, file_el, nv_pr):
    """(linked, target, media_part). p14:media r:embed is the embedded file; a:videoFile r:link may be external."""
    p14 = next((m for m in nv_pr.iter(f"{{{P14}}}media")), None)
    embed_id = p14.get(qn("r:embed")) if p14 is not None else None
    if embed_id and embed_id in part.rels and not part.rels[embed_id].is_external:
        mp = part.rels[embed_id].target_part
        return False, str(mp.partname), mp
    link_id = file_el.get(qn("r:link")) or file_el.get(qn("r:embed"))
    if link_id and link_id in part.rels:
        rel = part.rels[link_id]
        if rel.is_external:
            return True, rel.target_ref, None
        return False, str(rel.target_part.partname), rel.target_part
    return True, "", None


def _targets(el, spid: int) -> bool:
    return any(t.get("spid") == str(spid) for t in el.iter(qn("p:spTgt")))


def _read_timing(root, item: MediaItem):
    timing = root.find(qn("p:timing"))
    if timing is None:
        return
    for node in timing.iter(qn("p:video"), qn("p:audio")):
        cm = node.find(qn("p:cMediaNode"))
        if cm is None or not _targets(cm, item.shape_id):
            continue
        item.full_screen = node.get("fullScrn") == "1"
        vol = cm.get("vol")
        item.volume = round(int(vol) / 1000) if vol is not None else None
        item.muted = cm.get("mute") == "1"
        item.hidden_when_stopped = cm.get("showWhenStopped") == "0"
        ctn = cm.find(qn("p:cTn"))
        item.loop = ctn is not None and ctn.get("repeatCount") == "indefinite"

    main = next((c for c in timing.iter(qn("p:cTn")) if c.get("nodeType") == "mainSeq"), None)
    plays = [c for c in timing.iter(qn("p:cTn"))
             if c.get("presetClass") == "mediacall" and c.get("presetID") == "1" and _targets(c, item.shape_id)]
    in_main = [c for c in plays if main is not None and _is_inside(c, main)]
    if in_main:
        item.main_seq_id = main.get("id")
        groups = main.find(qn("p:childTnLst")).findall(qn("p:par"))
        play = in_main[0]
        group = next(g for g in groups if _is_inside(play, g))
        index = groups.index(group)
        firsts = [_first_effect_type(g) for g in groups[: index + 1]]
        item.play_ctn, item.group_par = play, group
        if index == 0 and firsts[0] in ("afterEffect", "withEffect") and _starts_on_begin(group, item.main_seq_id):
            item.mode, item.clicks = "automatic", 0
        elif firsts[-1] in EFFECT_TYPES:
            item.mode, item.clicks = "click_sequence", sum(1 for t in firsts if t == "clickEffect")
        else:
            item.mode = "unknown"
    elif plays or _self_trigger(timing, item.shape_id):
        item.mode = "on_click"
    elif main is not None and any(c.get("presetClass") == "mediacall" and _targets(c, item.shape_id)
                                  for c in main.iter(qn("p:cTn"))):
        item.mode = "unknown"     # e.g. a play/pause toggle in the click sequence (Mac, 1 corpus video)
    # else: no play effect anywhere → stays "no_timing"


def _self_trigger(timing, spid: int) -> bool:
    """An interactive sequence triggered by clicking the video itself."""
    for c in timing.iter(qn("p:cTn")):
        if c.get("nodeType") != "interactiveSeq":
            continue
        trig = c.find(f"{qn('p:stCondLst')}/{qn('p:cond')}/{qn('p:tgtEl')}/{qn('p:spTgt')}")
        if trig is not None and trig.get("spid") == str(spid):
            return True
    return False


# The main-sequence block PowerPoint writes for one "In Click Sequence" video, copied from its own
# saves (Mac and Windows are identical; tests/fixtures/media_modes/*_click_sequence.xml). {SPID} is the
# video's shape id; {ID0}… are cTn ids, filled with numbers unused in the slide's timing tree.
_P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
CLICK_GROUP = (
    f'<p:par {_P}><p:cTn id="{{ID0}}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/></p:stCondLst><p:childTnLst>'
    '<p:par><p:cTn id="{ID1}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
    '<p:par><p:cTn id="{ID2}" presetID="1" presetClass="mediacall" presetSubtype="0" fill="hold" nodeType="clickEffect">'
    '<p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst><p:cmd type="call" cmd="playFrom(0.0)"><p:cBhvr>'
    '<p:cTn id="{ID3}" dur="{DUR}" fill="hold"/><p:tgtEl><p:spTgt spid="{SPID}"/></p:tgtEl></p:cBhvr></p:cmd>'
    '</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>')
MAIN_SEQ = (
    f'<p:seq {_P} concurrent="1" nextAc="seek"><p:cTn id="{{IDM}}" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
    '{GROUP}</p:childTnLst></p:cTn>'
    '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
    '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>')


def with_click_sequence_play(timing, spid: int, dur_ms: int | None):
    """A copy of `timing` with a click-sequence play step for video `spid` (last click on the slide)."""
    from copy import deepcopy
    from lxml import etree
    new = deepcopy(timing)
    next_id = max((int(c.get("id", 0)) for c in new.iter(qn("p:cTn"))), default=0) + 1
    ids = {f"ID{i}": str(next_id + i) for i in range(4)}
    group = CLICK_GROUP.format(SPID=spid, DUR=dur_ms or 1, **ids)
    main = next((c for c in new.iter(qn("p:cTn")) if c.get("nodeType") == "mainSeq"), None)
    if main is not None:
        main.find(qn("p:childTnLst")).append(etree.fromstring(group))
    else:
        root_list = next(c for c in new.iter(qn("p:cTn")) if c.get("nodeType") == "tmRoot").find(qn("p:childTnLst"))
        seq = MAIN_SEQ.replace("{GROUP}", group.replace(f" {_P}", "")).replace("{IDM}", str(next_id + 4))
        root_list.insert(0, etree.fromstring(seq))     # PowerPoint writes the main sequence first
    return new


def _is_inside(el, ancestor) -> bool:
    node = el
    while node is not None:
        if node is ancestor:
            return True
        node = node.getparent()
    return False


def _first_effect_type(group) -> str | None:
    first = next((c for c in group.iter(qn("p:cTn")) if c.get("nodeType") in EFFECT_TYPES), None)
    return first.get("nodeType") if first is not None else None


def _starts_on_begin(group, main_seq_id) -> bool:
    ctn = group.find(qn("p:cTn"))
    conds = ctn.find(qn("p:stCondLst")) if ctn is not None else None
    if conds is None:
        return False
    for cond in conds.findall(qn("p:cond")):
        tn = cond.find(qn("p:tn"))
        if cond.get("evt") == "onBegin" and tn is not None and tn.get("val") == main_seq_id:
            return True
    return False


def _read_trim(nv_pr, item: MediaItem):
    trim = next(nv_pr.iter(f"{{{P14}}}trim"), None)
    if trim is not None:
        item.trim_start_ms = float(trim.get("st")) if trim.get("st") else None
        item.trim_end_ms = float(trim.get("end")) if trim.get("end") else None


# --- file facts via ffprobe ------------------------------------------------------------------

def ffprobe_path() -> str | None:
    import os
    return os.environ.get("SLIDETISTIC_FFPROBE") or shutil.which("ffprobe")


def probe(item: MediaItem) -> dict | None:
    """Duration, container, codecs, resolution, size. None if ffprobe isn't available or the file is linked."""
    if item.media_part is None or not ffprobe_path():
        return None
    blob = item.media_part.blob
    return _probe_blob(item.target, len(blob), blob)


_PROBE_CACHE: dict[tuple, dict | None] = {}


def _probe_blob(partname: str, size: int, blob: bytes) -> dict | None:
    key = (partname, size, hash(blob[:65536]))
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    with tempfile.NamedTemporaryFile(suffix=Path(partname).suffix) as f:
        f.write(blob)
        f.flush()
        try:
            out = subprocess.run([ffprobe_path(), "-v", "error", "-show_format", "-show_streams", "-of", "json", f.name],
                                 capture_output=True, text=True, timeout=60)
            data = json.loads(out.stdout or "{}")
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            data = {}
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("disposition", {}).get("attached_pic") != 1), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    result = None
    if fmt:
        result = {
            "duration_s": round(float(fmt["duration"]), 2) if fmt.get("duration") else None,
            "container": fmt.get("format_name", ""),
            "video_codec": video.get("codec_name") if video else None,
            "audio_codec": audio.get("codec_name") if audio else None,
            "width": video.get("width") if video else None,
            "height": video.get("height") if video else None,
            "mb": round(size / 1_048_576, 1),
        }
    _PROBE_CACHE[key] = result
    return result
