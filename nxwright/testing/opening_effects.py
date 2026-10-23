"""Components sliding in as their page opens, by their `effect`, `time`, and
`first`, as the Editor's simulator showed (tests/test_common_attributes.py).
The Editor's simulator slid nothing in on a Basic screen, which does not
hold `effect`, and the simulation starts no slide on such a screen
(simulation.py, _start_opening).

A component whose `effect` is 1 to 8 starts wholly off the screen, beyond
the edge or the corner its effect names, and slides in a straight line, at
a steady speed, to its place, over `time` milliseconds. The components of
one `first` slide together; the groups take turns, the highest `first`
first, each once the one before is in place, the longest of its slides
ended. A component waiting its turn is not drawn. The Editor's simulator
took a little longer than `time` says, about 2 percent, timed with
nothing typed into it, and now and then ran slower for a few seconds;
`time` is taken here as the vendor's milliseconds.

The simulation (simulation.py) draws each component where `place` says,
hides those `waiting` names, and steps the slides every STEP milliseconds
while one runs, about as often as the Editor's simulator stepped them:
their `x` and `y` keep their values, as code reads them. A component that
code moves slides on, and its slide's end puts its `x` and `y` back at
its place (`ended`). The next group waits for the longest slide of the one
before, as the Editor's simulator showed: one group's short slide had
ended, its long one had not, and the next group was not drawn. The place
on a slide's way is assumed: the share of the way its time has gone, cut
toward its start. While something drawing commands painted shows, each
step draws the component again as a move by code does: the page's
background comes back in the box it left, and it shows over what was
painted, as the Editor's simulator drew slides over a `fill`
(tests/fixtures/drawing-assumptions/, page41 to page43; simulation.py,
_mark_slides).
"""
from nxwright.project.screen_arithmetic import divide_toward_zero

# The way each effect comes in: where it starts, -1 before the screen's
# left or top edge, 1 past its right or bottom one, 0 at its own place.
EFFECT_FROM = {1: (0, -1), 2: (0, 1), 3: (-1, 0), 4: (1, 0),
               5: (-1, -1), 6: (1, -1), 7: (-1, 1), 8: (1, 1)}
# How often the slides step, in milliseconds: about as often as the Editor's
# simulator stepped page43's diagonal slide, whose band's edges went in steps
# of about 3 pixels across and 2 down (tests/fixtures/drawing-assumptions/).
STEP = 20


class Slide:
    """One component's slide: from `origin` to `place`, both (x, y), from
    `start` for `duration` milliseconds of the simulation's clock, in a
    straight line at a steady speed. A move takes one too (moves.py)."""

    def __init__(self, origin: tuple, place: tuple, start: int, duration: int):
        self.origin, self.place, self.start, self.duration = origin, place, start, duration

    @property
    def end(self) -> int:
        return self.start + self.duration

    def at(self, clock: int) -> tuple:
        """Where it is at `clock`, between its start and its end."""
        gone = clock - self.start
        return tuple(origin + divide_toward_zero((place - origin) * gone, self.duration)
                     for origin, place in zip(self.origin, self.place))


class OpeningEffects:
    """The slides of a page that opened at `clock`, of its `components`,
    [(name, its values by attribute)] in ID order, on a screen of `screen`,
    (width, height)."""

    def __init__(self, components: list, screen: tuple, clock: int):
        groups = {}
        for name, values in components:
            way = EFFECT_FROM.get(values.get("effect", 0))
            if way is not None:
                groups.setdefault(values.get("first", 0), []).append((name, values, way))
        self._slides = {}
        start = clock
        for first in sorted(groups, reverse=True):
            duration = 0
            for name, values, way in groups[first]:
                time = max(values.get("time", 0), 0)
                self._slides[name] = Slide(_origin(values, way, screen),
                                            (values["x"], values["y"]), start, time)
                duration = max(duration, time)
            start += duration

    def place(self, name: str, clock: int):
        """Where the component `name` is drawn at `clock`, (x, y), while it
        slides; None once it is in place, or when it does not slide. Before
        its turn, it is where it will start."""
        slide = self._slides.get(name)
        if slide is None or clock >= slide.end:
            return None
        return slide.origin if clock < slide.start else slide.at(clock)

    def drawn_at(self, clock: int) -> dict:
        """Where each sliding component is drawn at `clock`, (x, y) by name:
        on its slide's way, or in its place once the slide ends. One waiting
        its turn is left out, as it is not drawn."""
        return {name: slide.place if clock >= slide.end else slide.at(clock)
                for name, slide in self._slides.items() if clock >= slide.start}

    def waiting(self, clock: int) -> set:
        """The components waiting their turn at `clock`, which are not drawn."""
        return {name for name, slide in self._slides.items() if clock < slide.start}

    def end(self, name: str):
        """Puts the component `name` in its place at once, as when code
        hides or shows it, or a touch drags it (assumed for a drag)."""
        self._slides.pop(name, None)

    def ended(self, clock: int) -> list:
        """The slides ended by `clock`, each once, as [(name, its place (x,
        y))]. Where code moved the component meanwhile, the place it slid to
        is its own again."""
        done = [(name, slide.place) for name, slide in self._slides.items() if clock >= slide.end]
        for name, _ in done:
            del self._slides[name]
        return done

    def next_step(self, clock: int):
        """When the slides step next after `clock`, or None once every one
        has ended: every STEP milliseconds, and at each slide's start and
        end, so that each shows at its turn and stops in its place."""
        moments = [moment for slide in self._slides.values()
                   for moment in (slide.start, slide.end) if moment > clock]
        if not moments:
            return None
        return min([clock + STEP] + moments)


def _origin(values: dict, way: tuple, screen: tuple) -> tuple:
    """Where a component of `values` starts sliding in, coming the `way`
    EFFECT_FROM gives: wholly off the screen of `screen`, (width, height),
    beyond that edge or corner."""
    starts = []
    for along, own, size, screen_size in zip(way, (values["x"], values["y"]),
                                             (values["w"], values["h"]), screen):
        starts.append(own if along == 0 else -size if along < 0 else screen_size)
    return tuple(starts)
