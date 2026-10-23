"""Scrolling texts in the simulation: each moves by itself, on the
simulation's clock, as the Editor's simulator moved them.

A scrolling text's text moves `dis` pixels every `tim` milliseconds while
`en` is 1, the first step `tim` milliseconds after its page opens. Where it
is, its left moving across or its top moving up or down, in page pixels, is
kept in its `vvs0` or `vvs1`, the other being 32767, as the screen keeps
them; code may read them. W and H, its text's width and height in its font,
it keeps in `vvs2` and `vvs3`, as code read them in the Editor's simulator.
They are the size of the block of lines the text is drawn as: `spax`
between characters, `spay` between lines, and the lines `isbr` wraps
inside its border, as that simulator measured them. It measures them as
its page opens, and at each step before it moves. The drawing places the
text across its way by them (scrolling_text_drawing.py).
With x, y, w, and h the component's place:
  - left to right (`dir` 0): it starts at x - W - 1, outside on the left;
    once a step takes it past x + w - 1, it starts again at x - W;
  - right to left (1): it starts at x + w, outside on the right; once a
    step takes it below x - W, it starts again at x + w - 1;
  - top to bottom (2), and bottom to top (3): the same, down and up, with
    y, h, and H.
All of this matched the Editor's simulator's `vvs0` and `vvs1` step by step
(tests/fixtures/scrolling-text/).

Code changing it, as the Editor's simulator showed in a first set of runs:
  - a step starts again where code set `vvs0` or `vvs1`;
  - `en` 0 leaves the text where it is, and `en` 1 after it counts `tim`
    from then;
  - a new `txt` keeps its place;
  - a `dir` turned the other way along its line keeps its place, moving
    the other way;
  - code setting `tim`, even to the value it has, or `en` to 1, while it
    moves, keeps its count, unlike a timer's: its next step comes `tim`
    after its last, at once when that time has passed.
And in a later set:
  - a new `font` keeps its place too;
  - a new `txt` or `font` is not measured until the text's next step,
    which measures it before it moves: put where that step comes round,
    the text came round by its new size;
  - `ref`, `en` 1, and a new `vvs0` measure nothing, so a stopped text
    keeps its size;
  - a `dir` turned from across to up or down, or back, takes effect at the
    text's next step. That step puts the text where it starts again once
    it has gone out, by its new size, and moves it no further. Until then
    the text shows, and code reads its place, as it was. A stopped text
    does not turn. The first set of runs had read the turn as coming at
    once: each came within a tick of a step.
"""
from nxwright.drawing.scrolling_text_drawing import (LEFT_TO_RIGHT, RIGHT_TO_LEFT, TOP_TO_BOTTOM,
                                                     direction)
from nxwright.testing.card_files import component_attributes
from nxwright.testing.clocked import ClockedComponent

# What the screen keeps in a scrolling text's `vvs0` or `vvs1` that does not
# hold where its text is.
UNUSED_PLACE = 32767
# The attributes that start, stop, or time a scrolling text's steps.
_TIMING = ("en", "tim")
# The ways a text moves across, left or right.
_ACROSS = (LEFT_TO_RIGHT, RIGHT_TO_LEFT)


class ScrollingText(ClockedComponent):
    """A scrolling text of the page shown, moving as the module's docstring
    says. `measure(values)` returns the (width, height) of its text as the
    drawing lays it out, from `values`, its attributes by their own names,
    or (0, 0) when its font cannot be read."""

    def __init__(self, name: str, measure):
        super().__init__(name)
        self.measure = measure
        self.size = (0, 0)       # its text's width and height, as last measured
        self.measure_due = True  # whether code changed it since it was last measured
        self.counted_from = 0    # when its count began: its last step, or its start
        self.way = RIGHT_TO_LEFT  # its `dir` at its last placing: the way it shows

    def start(self, fields: dict, clock: int):
        self._measure(fields)
        self._place(fields, self._first_place(fields))
        self._count_from(fields, clock)

    def resume(self, fields: dict, clock: int):
        self._count_from(fields, clock)

    def changed(self, attribute: str, fields: dict, clock: int):
        # Any attribute may change how its text is laid out, so each marks
        # it to be measured at its next step. One that changes nothing does
        # no harm: measured again, the text gives the same size.
        self.measure_due = True
        if attribute in _TIMING:
            on = self._value(fields, "en", 1) == 1
            if not on:
                self.due = None
            elif self.due is None:
                # Turned on, it counts `tim` from then.
                self._count_from(fields, clock)
            else:
                # On already, it keeps its count: its next step comes `tim`
                # after its last.
                self.due = self.counted_from + max(self._value(fields, "tim", 150), 1)

    def step(self, fields: dict, clock: int) -> list:
        if self.measure_due:
            self._measure(fields)
        start, length, extent = self._extent(fields)
        if self._across(fields) != (self.way in _ACROSS):
            # Turned between across and up or down since its last step: the
            # step puts it where it comes round for its new way, no further.
            place = self._coming_round_place(fields)
        elif self._forward(fields):
            place = self.place(fields) + self._value(fields, "dis", 0)
            if place > start + length - 1:
                place = self._coming_round_place(fields)
        else:
            place = self.place(fields) - self._value(fields, "dis", 0)
            if place < start - extent:
                place = self._coming_round_place(fields)
        self._place(fields, place)
        self._count_from(fields, clock)
        return []

    def place(self, fields: dict) -> int:
        """Returns where its text is: its left moving across, its top moving
        up or down, in page pixels, by the way it shows."""
        return self._value(fields, "vvs0" if self.way in _ACROSS else "vvs1",
                           self._first_place(fields))

    def _value(self, fields: dict, attribute: str, default):
        return fields.get("%s.%s" % (self.name, attribute), default)

    def _first_place(self, fields: dict) -> int:
        """Where the text starts as its page opens: just outside the
        component, one pixel further out than where it starts again."""
        start, length, extent = self._extent(fields)
        return start - extent - 1 if self._forward(fields) else start + length

    def _coming_round_place(self, fields: dict) -> int:
        """Where the text starts again once it has gone out: just outside
        the component, at the side it moves in from."""
        start, length, extent = self._extent(fields)
        return start - extent if self._forward(fields) else start + length - 1

    def _extent(self, fields: dict) -> tuple:
        """The component's start and length along the text's way, and the
        text's own length that way."""
        if self._across(fields):
            return self._value(fields, "x", 0), self._value(fields, "w", 0), self.size[0]
        return self._value(fields, "y", 0), self._value(fields, "h", 0), self.size[1]

    def _way(self, fields: dict) -> int:
        """Its `dir`, 0 to 3, the type's default when `fields` has none."""
        key = self.name + ".dir"
        return direction({"dir": fields[key]} if key in fields else {})

    def _across(self, fields: dict) -> bool:
        return self._way(fields) in _ACROSS

    def _forward(self, fields: dict) -> bool:
        """Whether the text moves right or down, its place growing."""
        return self._way(fields) in (LEFT_TO_RIGHT, TOP_TO_BOTTOM)

    def _place(self, fields: dict, place: int):
        """Keeps where the text is in `vvs0` or `vvs1`, the other unused, in
        the way its `dir` now gives."""
        self.way = self._way(fields)
        across = self.way in _ACROSS
        fields[self.name + ".vvs0"] = place if across else UNUSED_PLACE
        fields[self.name + ".vvs1"] = UNUSED_PLACE if across else place

    def _measure(self, fields: dict):
        """Measures its text, keeping its width and height in `vvs2` and `vvs3`."""
        self.size = self.measure(component_attributes(self.name, fields))
        fields[self.name + ".vvs2"], fields[self.name + ".vvs3"] = self.size
        self.measure_due = False

    def _count_from(self, fields: dict, clock: int):
        """Sets the next step `tim` milliseconds from `clock`, or none while
        `en` is 0."""
        on = self._value(fields, "en", 1) == 1
        self.counted_from = clock
        self.due = clock + max(self._value(fields, "tim", 150), 1) if on else None
