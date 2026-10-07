"""EditSession: the only way a check's fix() may change the deck. Every change is logged."""
from __future__ import annotations

from .deck import ShapeView
from .findings import Change


class EditConflict(Exception):
    """Two checks tried to change the same property of the same shape in one repair."""


class FixRefused(Exception):
    """Raised by a fix() that decides not to change anything. The message is shown to the user."""


class EditSession:
    def __init__(self, deck):
        self.deck = deck
        self.changes: list[Change] = []
        self._owner: dict[tuple, str] = {}
        self.check_id: str | None = None   # set by the runner before each fix()

    def set_geometry(self, sv: ShapeView, *, left=None, top=None, width=None, height=None):
        """Values are in the shape's own coordinate space (= slide space unless it's in a group)."""
        for prop, value in (("left", left), ("top", top), ("width", width), ("height", height)):
            if value is None:
                continue
            before = getattr(sv.shape, prop)
            if before == int(value):
                continue
            self._claim(sv, prop)
            setattr(sv.shape, prop, int(value))
            self._log(sv, prop, before, int(value))

    def set_attr(self, sv: ShapeView, element, attr: str, value: str | None, prop: str):
        """Set (or remove, with value=None) an XML attribute on an element belonging to `sv`."""
        before = element.get(attr)
        if before == value:
            return
        self._claim(sv, prop)
        if value is None:
            del element.attrib[attr]
        else:
            element.set(attr, value)
        self._log(sv, prop, before, value)

    def _claim(self, sv: ShapeView, prop: str):
        key = (sv.slide_number, sv.shape_id, prop)
        owner = self._owner.setdefault(key, self.check_id)
        if owner != self.check_id:
            raise EditConflict(f"{prop} on slide {sv.slide_number} '{sv.name}' was already changed by {owner}")

    def _log(self, sv: ShapeView, prop: str, before, after):
        self.changes.append(Change(self.check_id, sv.slide_number, sv.shape_id, sv.name, prop, before, after))
