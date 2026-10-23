"""Combo boxes in the simulation: their lists opened, scrolled, and chosen
from under touches and code, as the Editor's simulator did
(tests/fixtures/combo-box/, and drawing/combo_box_drawing.py for the look).

A release on the closed box opens its list (`down` 1), and one on the open
box closes it. A press anywhere on the open list, an item, a scroll mark,
or a gap, belongs to the box, as its Touch Press event shows; its release
chooses the item under it, if any, setting `val` and `txt`, and closes the
list. All of this comes before the box's Touch Release event runs. A drag
on the open list scrolls it a whole item each time the touch moves an
item's length, chooses nothing, and leaves it open (assumed: the Editor
tool cannot drag).

Code setting `val` moves an open list to show its item. Setting `down`
opens or closes the list. A new `path` or `qty` keeps the open list within
its items. What code's `val` does to the box's own values, its `txt`, and a
`val` past the last item taken back, is worked as tests work it
(list_working.py), after the list moves here.

Each method takes a box's attributes by their own names (`val`), and
returns those to change.
"""
from nxwright.drawing.combo_box_drawing import LEFT, RIGHT, direction, items, list_layout, value


class ComboBoxes:
    """The combo boxes of the page shown, from when it opened: the first
    item each open list shows."""

    def __init__(self):
        self._firsts = {}       # {box: the first item its open list shows}

    def enter(self, box: str, values: dict):
        """The page opens, showing `box`, with its attributes `values`."""
        self._firsts.pop(box, None)
        if values.get("down") == 1:
            self._open(box, values)

    def scrolled(self) -> dict:
        """The first item each open list shows, {box: number}, as
        page_drawing.draw_page takes it."""
        return dict(self._firsts)

    def first_under(self, box: str, values: dict, x: int, y: int):
        """The first item `box`'s open list shows, when the page's pixel
        (x, y) is on that list, or None: a press there may drag it."""
        area = self.list_area(box, values)
        if area is None or not (area["x"] <= x < area["x"] + area["w"]
                                and area["y"] <= y < area["y"] + area["h"]):
            return None
        return self._firsts.get(box)

    def list_area(self, box: str, values: dict):
        """The rectangle of `box`'s open list, which a press reaches the box
        by, or None when it is closed or has no items."""
        if values.get("down") != 1:
            return None
        layout = list_layout(values, len(items(values)), self._firsts.get(box))
        return layout.area if layout else None

    def follow(self, box: str, values: dict, start_first: int, moved_x: int,
               moved_y: int) -> bool:
        """A press on `box`'s open list, made when it showed items from
        `start_first` (first_under), has moved by (moved_x, moved_y): the
        list follows it a whole item at a time. A press elsewhere, None,
        scrolls nothing. Returns whether it scrolled."""
        if values.get("down") != 1 or start_first is None:
            return False
        lines = items(values)
        layout = list_layout(values, len(lines), start_first)
        if layout is None:
            return False
        moved = moved_x if direction(values) in (LEFT, RIGHT) else moved_y
        pitch = max(value(values, "hig") + value(values, "vvs0"), 1)
        # Moving the touch back, up or left, brings later items in.
        first = min(max(start_first - round(moved / pitch), 0),
                    len(lines) - len(layout.items))
        if first == self._firsts.get(box):
            return False
        self._firsts[box] = first
        return True

    def released(self, box: str, values: dict, x: int, y: int, scrolled: bool) -> dict:
        """A press on `box`, or on its open list, made at the page's pixel
        (x, y), ends. Returns the attributes it changes, as the module's
        docstring says; a press that scrolled the list changes none. The
        item chosen is the one under the press: a press that moved less
        than an item's length and ended over another still chooses the
        first (assumed: the Editor tool cannot drag)."""
        if scrolled:
            return {}
        on_box = values["x"] <= x < values["x"] + values["w"] and \
            values["y"] <= y < values["y"] + values["h"]
        if values.get("down") != 1:
            if not on_box:
                return {}
            self._open(box, values)
            return {"down": 1}
        changes = {"down": 0}
        lines = items(values)
        layout = None if on_box else list_layout(values, len(lines), self._firsts.get(box))
        for number, item in layout.items if layout else ():
            if item["x"] <= x < item["x"] + item["w"] and item["y"] <= y < item["y"] + item["h"]:
                changes.update(val=number, txt=lines[number])
        self._firsts.pop(box, None)
        return changes

    def code_set(self, box: str, attribute: str, values: dict):
        """Code has set `box`'s `attribute`, which `values` hold: its open
        list moves, as the module's docstring says."""
        lines = items(values)
        if attribute == "val":
            chosen = values.get("val")
            if isinstance(chosen, int) and 0 <= chosen < len(lines) and box in self._firsts:
                self._open(box, values)
        elif attribute == "down":
            if values.get("down") == 1:
                self._open(box, values)
            else:
                self._firsts.pop(box, None)
        elif attribute in ("path", "qty") and box in self._firsts:
            layout = list_layout(values, len(lines), self._firsts[box])
            if layout is None:
                self._firsts.pop(box)
            else:
                self._firsts[box] = layout.first

    def _open(self, box: str, values: dict):
        """Opens `box`'s list where it shows its chosen item."""
        layout = list_layout(values, len(items(values)))
        self._firsts[box] = layout.first if layout else 0
