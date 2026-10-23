"""Recording a test's run of a screen's code, step by step, for the debugger.

A run is what SourceFolderRunner.run or run_code does: some events of a page,
in turn, from given values. While a Recorder is on (`recording`), each run
is recorded:
  - a step for each statement the test machine runs, with its place: the
    file within the source folder, the line, counted from 1, and the event
    or function it belongs to, as "home.load" or "showClock";
  - the stack of the events and functions running at each step, outermost
    first: an event, then what its calls and clicks run;
  - the values each step finds changed since the step before;
  - and how the run ended: the values it left, or the error that stopped it.
Lines the compiler adds with no place in the source, such as a function's
dispatching, make no step: their changes go with the next step.

The debugger also records the test's own Python lines in the same list of
steps (debug_adapter/python_steps.py), each at a PythonPlace. A run's steps
then stand under the Python frames that made the call: their frames start
with those.

The test machine always gives the same result from the same start, so the
debugger runs the whole test first and then moves through its recording,
backward as well as forward.
"""
from contextlib import contextmanager
import copy
from dataclasses import dataclass

from nxwright import NxwrightError

# Past this many steps in one process, the run stops: a recording that long
# is no use to step through, and holds much memory.
MOST_STEPS = 1_000_000

_MISSING = object()
_current = None     # the Recorder `recording` turned on, if any


class _Removed:
    """What a step's changes give a name the values no longer hold."""

    def __repr__(self):
        return "REMOVED"


REMOVED = _Removed()


def apply_changes(values: dict, changes: dict):
    """Applies a step's `changes` to `values`: sets each, and removes those
    marked REMOVED."""
    for name, value in changes.items():
        if value is REMOVED:
            values.pop(name, None)
        else:
            values[name] = value


@dataclass(frozen=True)
class Place:
    """Where a line of Editor code comes from: a file of the source folder,
    a line of it counted from 1, and its event or function."""
    file: str
    line: int
    owner: str


@dataclass(frozen=True)
class PythonPlace:
    """A line of a test's Python, about to run: its file's full path, the
    line, counted from 1, and its function, as "TargetTest.test_raise".
    `local_values` are the function's locals then, as text:
    ((name, text, entries), ...), where `entries` are the first entries of
    a list, tuple, or dict, ((key, text), ...), and empty otherwise."""
    file: str
    line: int
    owner: str
    local_values: tuple = ()


@dataclass
class Step:
    """One statement the test machine ran, or one line of the test's Python.
    `frames` are the places of the functions and events running, outermost
    first, this step's last. `changes` are the values the machine changed
    since the run's step before, by name. `run` is the index of the step's
    run in Recorder.runs, and None for a line of Python."""
    place: object
    frames: tuple
    changes: dict
    run: int = None


@dataclass
class RunRecording:
    """One run, from its start values to how it ended."""
    title: str                  # as "home: home.load, raise.up"
    folder: str                 # the source folder its places are files of
    start: dict                 # the values the run started from
    local_names: dict           # {owner: {generated variable: nxlang name}}
    end: dict = None            # the values it left
    error: str = None           # what stopped it, if anything
    # Whether its code was compiled from nxlang, whose generated variables
    # the debugger groups apart: none is generated in the Editor's own language.
    nxlang: bool = False


class TrackedValues(dict):
    """A machine's values, noting the names set or removed since the
    recorder last looked at them, in `touched`; None until it first looks.
    A step then compares those names, and the values that change in place,
    rather than every value: an app with thousands of values runs several
    steps a millisecond. Values of other kinds cannot change but through
    these methods."""

    def __init__(self, *arguments, **values):
        super().__init__(*arguments, **values)
        self.touched = None

    def _touch(self, name):
        if self.touched is not None:
            self.touched.add(name)

    def __setitem__(self, name, value):
        super().__setitem__(name, value)
        self._touch(name)

    def __delitem__(self, name):
        super().__delitem__(name)
        self._touch(name)

    def pop(self, name, *default):
        self._touch(name)
        return super().pop(name, *default)

    def setdefault(self, name, default=None):
        if name not in self:
            self[name] = default
        return self[name]

    def update(self, *arguments, **values):
        for name, value in dict(*arguments, **values).items():
            self[name] = value

    def __ior__(self, values):
        self.update(values)
        return self

    def popitem(self):
        self.touched = None
        return super().popitem()

    def clear(self):
        self.touched = None
        super().clear()


class Recorder:
    """Records runs, as the test machine and SourceFolderRunner tell it of
    them, and the test's Python lines, as the debugger's tracing does.
    `steps` holds every step, in order.

    A simulation never ends, so its recorder is made with `keep`: it keeps
    only its last `keep` steps, dropping the oldest as it goes. `first` is
    then the number of the oldest step kept, counting every step recorded:
    steps[0] is step `first`. A run whose first steps were dropped starts
    from the values at its oldest step kept. `watch(position, step)`, when
    set, is called after each step is recorded, with its number: the
    debugger stops a simulation there."""

    def __init__(self, keep: int = None):
        self.runs = []
        self.steps = []
        self.first = 0
        self.keep = keep
        self.watch = None
        self._frames = []    # the run's events and functions running
        self._python = []    # the test's Python functions running, outermost first
        self._last = {}
        self._tracked = None         # the TrackedValues the last step compared
        self._in_place = set()       # the names in _last of values that change in place

    def begin(self, title: str, folder: str, values: dict, local_names: dict,
              nxlang: bool = False):
        """Starts recording a run of the source folder `folder`, from
        `values`, its code compiled from nxlang or not."""
        self.runs.append(RunRecording(title, folder, _copied(values), local_names,
                                      nxlang=nxlang))
        self._frames, self._last = [], _copied(values)
        self._tracked = None
        self._in_place = {name for name, value in self._last.items()
                          if isinstance(value, _IN_PLACE)}

    def enter(self):
        """Notes that the machine starts running an event: a frame of its own."""
        self._frames.append(None)

    def leave(self):
        """Notes that the machine finished an event."""
        self._frames.pop()

    def step(self, place: Place, values: dict):
        """Records a step of the run at `place`, about to run, with the values
        as they are. Raises NxwrightError past MOST_STEPS."""
        self._count()
        changes = {}
        tracked = isinstance(values, TrackedValues)
        if tracked and values is self._tracked and values.touched is not None:
            # Only what was set or removed since the last step, and what
            # changes in place, can differ.
            for name in values.touched | self._in_place:
                if name not in values:
                    if name in self._last:
                        changes[name] = REMOVED
                        del self._last[name]
                        self._in_place.discard(name)
                else:
                    self._compare(name, values[name], changes)
        else:
            for name, value in values.items():
                self._compare(name, value, changes)
            # A simulation's values lose names, such as the old page's
            # components after a page change. Every name of `values` is in
            # _last by now, so _last holds more exactly when some were lost.
            if len(self._last) > len(values):
                for name in self._last.keys() - values.keys():
                    changes[name] = REMOVED
                    del self._last[name]
                    self._in_place.discard(name)
        if tracked:
            values.touched = set()
            self._tracked = values
        self._frames[-1] = place
        self.steps.append(Step(place, tuple(self._python) + tuple(self._frames), changes,
                               len(self.runs) - 1))
        if self.watch is not None:
            self.watch(self.first + len(self.steps) - 1, self.steps[-1])

    def _compare(self, name: str, value, changes: dict):
        """Notes `value` in `changes` when it differs from the last step's."""
        if self._last.get(name, _MISSING) != value:
            changes[name] = self._last[name] = _copied(value)
            if isinstance(value, _IN_PLACE):
                self._in_place.add(name)
            else:
                self._in_place.discard(name)

    def end(self, values: dict, error: str = None):
        """Ends the run, as it left `values`, stopped by `error` when given."""
        run = self.runs[-1]
        run.end, run.error = _copied(values), error

    def python_call(self):
        """Notes that a Python function of the test starts: a frame of its own."""
        self._python.append(None)

    def python_return(self):
        """Notes that a Python function of the test returned."""
        self._python.pop()

    def python_line(self, place: PythonPlace):
        """Records a step at a line of the test's Python, about to run, in
        the function that started last. Raises NxwrightError past MOST_STEPS."""
        self._count()
        self._python[-1] = place
        self.steps.append(Step(place, tuple(self._python), {}))

    def _count(self):
        if self.keep is not None:
            if len(self.steps) >= self.keep:
                self._drop(max(self.keep // 10, 1))
        elif len(self.steps) >= MOST_STEPS:
            raise NxwrightError("the recording passed %d steps; record a shorter run"
                                % MOST_STEPS)

    def _drop(self, count: int):
        """Drops the `count` oldest steps. The run of each keeps its values
        as they were before its oldest step kept."""
        for step in self.steps[:count]:
            if step.run is not None:
                apply_changes(self.runs[step.run].start, step.changes)
        del self.steps[:count]
        self.first += count


@contextmanager
def recording(recorder: Recorder):
    """Turns recording on for every run in the process while it lasts."""
    global _current
    previous, _current = _current, recorder
    try:
        yield recorder
    finally:
        _current = previous


def current_recorder():
    """Returns the Recorder that is on, or None."""
    return _current


def _copied(value):
    """Returns `value`, copied when it is a list or dict the machine may change in place."""
    return copy.deepcopy(value) if isinstance(value, _IN_PLACE) else value


# The kinds of values the machine changes in place, which a step compares
# however they were set.
_IN_PLACE = (list, dict)
