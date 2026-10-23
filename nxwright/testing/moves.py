"""Components moving across the page, as `move` moves them:
`move <component>,<x1>,<y1>,<x2>,<y2>,<priority>,<time>` takes the component
from (x1, y1) to (x2, y2) in `time` milliseconds, as the Editor's simulator
showed (tests/test_simulation.py, MoveTest).

The moves of the page shown run in turns, one priority at a time, the
highest first. The moves of a turn run together, each over its own time,
and the next turn starts once the last of them has ended. The queue
chooses once the code that gave a move has ended, so the moves one event
gives compete by priority. A move given while a turn runs joins it when
its priority is the turn's, and otherwise waits. A move for a component
that already has a move of its priority, waiting or running, is dropped.

A move starting puts its component at (x1, y1), then takes it in a straight
line, at a steady speed, to (x2, y2), setting the component's `x` and `y` as
it goes, which code reads at the moment it reads them. It steps every STEP
milliseconds, and each step is drawn as a move by code is: the component's
old box gives back the page's background, where drawing commands painted
over it (Simulation._mark_moved).
The Editor's simulator drew a move over a fill so (tests/fixtures/moves/).
A step marks the record of what was painted (simulation.py, _compacted), so
a long move over paint fills it: past its bound, the oldest of those marks
go first, and the start of the band shows the paint again.

Code setting `x` or `y` meanwhile does not stop it: the move sets them again
before code next reads them, as `catch_up` brings them to the clock. A move
of no time never reaches the queue: the test machine puts its component at
its end at once (editor_machine.py).

The queue is one of the page's clocked components (clocked.py), kept by the
simulation under MOVES, a new one each time a page opens: a page change
drops the moves of the page before.
"""
from dataclasses import dataclass

from nxwright.testing.clocked import ClockedComponent
from nxwright.testing.opening_effects import Slide

# The name the simulation keeps the moves under, among the page's clocked
# components: no component's, as a name holds no space.
MOVES = "the moves"
# How often the moves step, in milliseconds: about as often as the Editor's
# simulator stepped a diagonal move over a fill, whose band's lower edge
# went in 173 stairs over about 2.75 s (tests/fixtures/moves/).
STEP = 16


@dataclass
class Move:
    """One move as `move` gives it: its component's name, where it starts
    and ends, `origin` and `destination`, both (x, y), its priority, and its
    time in milliseconds, more than 0."""
    component: str
    origin: tuple
    destination: tuple
    priority: int
    time: int


class Moves(ClockedComponent):
    """The moves of the page shown: those waiting their turn, in the order
    given, and the turn running, if any."""

    def __init__(self):
        super().__init__(MOVES)
        self._waiting = []
        self._running = []          # the turn: [(Move, its Slide)]
        self._counted = None        # the clock its last step or catch-up reached
        # {component: (x, y)} where its last start or step drew it. Code reads
        # the places catch_up gives between steps, which are not drawn.
        self._drawn_at = {}
        self._moved = []            # (component, before, after) of its last step or choice

    @property
    def drawn(self) -> list:
        """Empty: what it changes, it moves (moved)."""
        return []

    @property
    def moved(self) -> list:
        """The components its last step or choice put somewhere, each with
        where it was drawn before and where it is now."""
        return list(self._moved)

    def add(self, move: Move) -> bool:
        """Queues `move`, which starts in its turn, once `choose` is called.
        Returns False, queuing nothing, when its component already has a
        move of its priority, waiting or running."""
        given = self._waiting + [running for running, _ in self._running]
        if any(other.component == move.component and other.priority == move.priority
               for other in given):
            return False
        self._waiting.append(move)
        return True

    def choose(self, fields: dict, clock: int) -> bool:
        """Starts the moves waiting that may start, called once the code
        that gave moves has ended. Returns whether it put a component
        anywhere (moved)."""
        self._moved = []
        self._start_turn(fields, clock)
        return bool(self._moved)

    def _start_turn(self, fields: dict, clock: int):
        """Starts the moves waiting of the turn's priority, when a turn runs,
        or else of the highest priority waiting, as a new turn."""
        if self._running:
            priority = self._running[0][0].priority
        elif self._waiting:
            priority = max(move.priority for move in self._waiting)
        else:
            priority = None
        for move in [move for move in self._waiting if move.priority == priority]:
            self._waiting.remove(move)
            # It was drawn where code last put it.
            before = (fields.get(move.component + ".x", 0), fields.get(move.component + ".y", 0))
            self._put_drawn(fields, move.component, before, move.origin)
            self._running.append((move, Slide(move.origin, move.destination, clock, move.time)))
        self._count(clock)

    def start(self, fields: dict, clock: int):
        """A page opens with no moves."""

    def resume(self, fields: dict, clock: int):
        """The screen wakes: the turn running goes on from where it waited."""
        if self._counted is not None:
            for _, slide in self._running:
                slide.start += clock - self._counted
        self._count(clock)

    def changed(self, attribute: str, fields: dict, clock: int):
        """Never called: the queue is no component code writes to. Code
        writing a moving component's `x` or `y` is overwritten by the move
        (catch_up)."""

    def catch_up(self, fields: dict, clock: int):
        """Puts each moving component where its move has it at `clock`."""
        for move, slide in self._running:
            _put(fields, move.component, slide.at(min(clock, slide.end)))
        self._counted = clock

    def step(self, fields: dict, clock: int) -> list:
        self._moved = []
        for move, slide in self._running:
            self._put_drawn(fields, move.component, self._drawn_at[move.component],
                            slide.at(clock) if clock < slide.end else move.destination)
        self._running = [(move, slide) for move, slide in self._running if clock < slide.end]
        if self._running:
            self._count(clock)
        else:
            self._start_turn(fields, clock)
        return []

    def _put_drawn(self, fields: dict, component: str, before: tuple, place: tuple):
        """Puts `component` at `place`, drawn there, from `before` (moved)."""
        _put(fields, component, place)
        self._drawn_at[component] = place
        self._moved.append((component, before, place))

    def _count(self, clock: int):
        """Sets when the queue steps next: every STEP milliseconds, and at the
        end of each move of the turn, so that it stops there; None while no
        turn runs."""
        self._counted = clock
        if not self._running:
            self.due = None
        else:
            self.due = min(clock + STEP, *(slide.end for _, slide in self._running))


def _put(fields: dict, component: str, place: tuple):
    """Sets a component's `x` and `y`, as code reads them."""
    fields[component + ".x"], fields[component + ".y"] = place
