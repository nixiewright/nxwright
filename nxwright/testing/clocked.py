"""Components that change on the simulation's clock without code, such as a
scrolling text, which moves by itself, or an animation, which plays. The
simulation (simulation.py) keeps one ClockedComponent for each such
component of the page shown, and steps it in time order with the page's
timers.

The simulation calls `start` as the page opens, `resume` as the screen
wakes, `changed` when code changes one of the component's attributes,
`step` once its `due` time comes, and `catch_up` before code runs and once
a `delay` has moved the clock. After each step, the component is drawn
again, and the events `step` returns run, as the component's own. Each call
is given `fields`, the values of the page shown by name as its code names
them ("st0.vvs0"), which it may change, and `clock`, the simulation's time
in milliseconds.
"""


class ClockedComponent:
    """One component that changes on the clock, `name` on the page shown.
    `due` is when it next steps, by the simulation's clock, or None while it
    does not."""

    def __init__(self, name: str):
        self.name = name
        self.due = None

    @property
    def drawn(self) -> list:
        """The names of the components its last step changed in place, which
        the simulation draws again: its own, by default."""
        return [self.name]

    @property
    def moved(self) -> list:
        """The components its last step moved, each as (name, the place it
        was drawn at before, the place it is drawn at now), which the
        simulation draws again at their new places, giving back what was
        under the old (Simulation._mark_moved). Empty, by default."""
        return []

    def start(self, fields: dict, clock: int):
        """Its page opens: it starts from its first state."""
        raise NotImplementedError

    def resume(self, fields: dict, clock: int):
        """The screen wakes: it counts again from `clock`, as it was."""
        raise NotImplementedError

    def changed(self, attribute: str, fields: dict, clock: int):
        """Code changed its `attribute`, which `fields` holds."""
        raise NotImplementedError

    def catch_up(self, fields: dict, clock: int):
        """Brings what code may read of it up to `clock`, between two steps,
        such as a player's `tim`. It sets only what code reads, draws
        nothing, and counts as no change. By default there is nothing to
        bring: a scrolling text's place moves only at its steps."""

    def step(self, fields: dict, clock: int) -> list:
        """Steps once, at its `due` time, and sets the next. Returns the
        names of its events to run now, in order, such as "playend"."""
        raise NotImplementedError
