"""EditSession: the only way a check's fix() may change the deck. Every change is logged."""
from __future__ import annotations

from lxml import etree

from .deck import ShapeView
from .findings import Change


class EditConflict(Exception):
    """Two checks tried to change the same property of the same thing in one repair."""


class FixRefused(Exception):
    """Raised by a fix() that decides not to change anything. The message is shown to the user."""


class EditSession:
    def __init__(self, deck):
        self.deck = deck
        self.changes: list[Change] = []
        self._owner: dict[tuple, str] = {}
        self.check_id: str | None = None
        self._runs_after: set[str] = set()
        self._refiners: set[str] = set()
        self.notes: list[dict] = []     # tuning: what each planned layout fix was (core/tuning.py)

    def allow_refining(self, check_ids):
        """Checks that may adjust each other's edits (the layout fit pass: it re-renders between rounds,
        so a later round's change is a refinement of an earlier one, not a fight)."""
        self._refiners = set(check_ids)

    def begin(self, check_cls):
        """Called by the runner before each check's fixes."""
        self.check_id = check_cls.id
        self._runs_after = set(check_cls.runs_after)

    # --- shapes -------------------------------------------------------------------------------

    def set_geometry(self, sv: ShapeView, *, left=None, top=None, width=None, height=None):
        """Values are in the shape's own coordinate space (= slide space unless it's in a group)."""
        # A placeholder that inherits its position from the layout has no <a:xfrm> of its own, and
        # python-pptx writes only the value being set, leaving the rest 0: moving one sideways made it
        # zero-size and its text vanished (app run 2026-10-11, lower-thirds deck, every slide). Pin the
        # inherited position first so a move changes only what it means to.
        if any(v is not None for v in (left, top, width, height)) and _inherits_xfrm(sv.shape):
            inherited = {p: getattr(sv.shape, p) for p in ("left", "top", "width", "height")}
            if None not in inherited.values():
                self._claim((sv.slide_number, sv.shape_id, "position"))
                for p, v in inherited.items():
                    setattr(sv.shape, p, v)
                self.deck.invalidate()
        for prop, value in (("left", left), ("top", top), ("width", width), ("height", height)):
            if value is None:
                continue
            before = getattr(sv.shape, prop)
            if before == int(value):
                continue
            self._claim((sv.slide_number, sv.shape_id, prop))
            setattr(sv.shape, prop, int(value))
            self._log(Change(self.check_id, sv.slide_number, sv.shape_id, sv.name, prop, before, int(value)))

    def set_attr(self, sv: ShapeView, element, attr: str, value: str | None, prop: str):
        """Set (or remove, with value=None) an XML attribute on an element belonging to shape `sv`."""
        before = element.get(attr)
        if before == value:
            return
        self._claim((sv.slide_number, sv.shape_id, prop))
        _set(element, attr, value)
        self._log(Change(self.check_id, sv.slide_number, sv.shape_id, sv.name, prop, before, value))

    # --- deck-level XML (masters, layouts, theme, presentation.xml) ---------------------------

    def set_part_attr(self, part, element, attr: str, value: str | None, prop: str):
        before = element.get(attr)
        if before == value:
            return
        partname = str(part.partname)
        self._claim((partname, element.getroottree().getpath(element), attr))
        _set(element, attr, value)
        self._log(Change(self.check_id, None, None, None, prop, before, value, part=partname))

    def replace_element(self, part, old, new, *, prop: str, before: str, after: str):
        """Swap `old` for `new` (or remove it when new is None). before/after are human summaries."""
        if new is not None and etree.tostring(old) == etree.tostring(new):
            return
        partname = str(part.partname)
        self._claim((partname, old.getroottree().getpath(old)))
        parent = old.getparent()
        if new is None:
            parent.remove(old)
        else:
            parent.replace(old, new)
        self._log(Change(self.check_id, None, None, None, prop, before, after, part=partname))

    def replace_blob(self, part, blob: bytes, *, prop: str, before: str, after: str):
        """Swap a binary part's bytes (a picture's image data, e.g. compression)."""
        partname = str(part.partname)
        self._claim((partname, "blob"))
        part._blob = blob
        self._log(Change(self.check_id, None, None, None, prop, before, after, part=partname))

    def drop_rel(self, part, r_id: str, *, prop: str, before: str):
        """Remove a relationship. Its target part is left out of the saved file if nothing else uses it."""
        partname = str(part.partname)
        self._claim((partname, "rel", r_id))
        part.rels.pop(r_id)
        self._log(Change(self.check_id, None, None, None, prop, before, None, part=partname))

    # ------------------------------------------------------------------------------------------

    def _claim(self, key: tuple):
        owner = self._owner.get(key)
        # A check that declares runs_after=[owner] is refining that check's result, not fighting it.
        refining = owner in self._refiners and self.check_id in self._refiners
        if owner is not None and owner != self.check_id and owner not in self._runs_after and not refining:
            raise EditConflict(f"{key[-1]} was already changed by {owner}")
        self._owner[key] = self.check_id

    def _log(self, change: Change):
        self.changes.append(change)
        self.deck.invalidate()          # every edit goes through here: remembered shape lists are stale


def _inherits_xfrm(shape) -> bool:
    """True when the shape has no position of its own (a placeholder taking it from its layout)."""
    from pptx.oxml.ns import qn
    sp_pr = shape.element.find(qn("p:spPr"))
    return getattr(shape, "is_placeholder", False) and (sp_pr is None or sp_pr.find(qn("a:xfrm")) is None)


def _set(element, attr: str, value: str | None):
    if value is None:
        element.attrib.pop(attr, None)
    else:
        element.set(attr, value)
