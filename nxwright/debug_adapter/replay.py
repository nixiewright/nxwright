"""Moving through a recording (testing/recording.py), as a debugger moves
through a running program, forward and backward.

A timeline holds the steps of a Recorder, in order: lines of the test's
Python, and the statements of screen code its runs executed. A position is
a step, about to run. A step's line is its file and line, with its run for
screen code, and its depth is how many functions and events are running,
Python's and the screen's together. Moving by source line, as the
debugger's "step over" does, goes to the next step on another line, no
deeper: one source line may compile into many Editor lines, and a Python
line that runs screen code holds that code's steps, deeper. "Step into"
goes to the next step on another line at any depth; "step out", to the next
step shallower. Stepping back lands on the first step of the line before,
no deeper.

The recording may still grow while the debugger moves through it. A
recording only ever gains steps at its end, so what was worked out for the
steps already there stays true. A simulation's recording also drops its
oldest steps (Recorder's `keep`): positions keep counting every step
recorded, and the oldest kept, `first`, is as far back as stepping goes.
"""
import os
from pathlib import Path

from nxwright.testing.recording import PythonPlace, apply_changes

# Every this many steps of a run, its values are kept, so that finding the
# values at a step replays at most this many steps' changes.
_CHECKPOINT = 2000


class Timeline:
    """The steps of `recorder`, a Recorder, in order. `catch_up` takes in
    the steps recorded since."""

    def __init__(self, recorder):
        self.recorder = recorder
        self.runs = recorder.runs
        self.first = recorder.first      # the oldest position kept
        self._starts = []        # per position from `first`: whether its step starts a line
        self._last_runs = []     # per position from `first`: the last run begun by then, or None
        self._run_starts = {}    # {run: the position of its first step}
        self._checkpoints = {}   # {position: the values when it is about to run}
        self._depth_lines = {}   # {depth: the line last stepped at that depth}
        self.catch_up()

    def catch_up(self):
        """Takes in the steps recorded since the timeline last looked, and
        forgets those the recording dropped."""
        dropped = self.recorder.first - self.first
        if dropped > 0:
            del self._starts[:dropped]
            del self._last_runs[:dropped]
            self.first = self.recorder.first
            self._checkpoints = {position: values for position, values
                                 in self._checkpoints.items() if position >= self.first}
        for position in range(len(self), self.recorder.first + len(self.recorder.steps)):
            step = self.step(position)
            if step.run is not None:
                self._run_starts.setdefault(step.run, position)
            last = self._last_runs[-1] if self._last_runs else None
            self._last_runs.append(step.run if step.run is not None else last)
            self._starts.append(self._starts_line(position))

    def _starts_line(self, position: int) -> bool:
        """Returns whether the step at `position`, the next taken in, starts
        a source line. A line that makes a call holds steps before and after
        the call's own steps, which run deeper: the line starts only once."""
        line, depth = self.line_of(position)
        for deeper in [other for other in self._depth_lines if other > depth]:
            del self._depth_lines[deeper]
        starts = self._depth_lines.get(depth) != line
        self._depth_lines[depth] = line
        return starts

    def __len__(self) -> int:
        """The position after the last step taken in."""
        return self.first + len(self._starts)

    def step(self, position: int):
        """Returns the Step at a position."""
        return self.recorder.steps[position - self.recorder.first]

    def line_of(self, position: int) -> tuple:
        """Returns ((run, file, line), depth) of a step; run is None for Python."""
        step = self.step(position)
        return (step.run, step.place.file, step.place.line), len(step.frames)

    def path_of(self, place, run) -> str:
        """Returns the full path of a place's file: a Python place's own, or a
        screen place's in its run's source folder."""
        if isinstance(place, PythonPlace):
            return place.file
        return str(Path(self.runs[run].folder) / place.file)

    def run_shown_at(self, position: int):
        """Returns the index of the run whose values values_at shows at
        `position`: the step's own, or at a line of Python, the last run
        before it; None when there is none."""
        run = self.step(position).run
        return run if run is not None else self._last_runs[position - self.first]

    def values_at(self, position: int) -> dict:
        """Returns the screen's values when the step at `position` is about to
        run. At a line of Python, those the last run before it left."""
        run = self.step(position).run
        if run is None:
            last = self.run_shown_at(position)
            return dict(self.runs[last].end or {}) if last is not None else {}
        # A run whose first steps were dropped starts at the oldest kept, from
        # the values before it (Recorder._drop).
        first = max(self._run_starts[run], self.first)
        kept = [checkpoint for checkpoint in self._checkpoints if first <= checkpoint <= position]
        start = max(kept, default=None)
        values = dict(self._checkpoints[start] if start is not None else self.runs[run].start)
        for index in range(first if start is None else start + 1, position + 1):
            apply_changes(values, self.step(index).changes)
            if (index - first) % _CHECKPOINT == 0:
                self._checkpoints[index] = dict(values)
        return values

    def next_line(self, position: int, into: bool = False, out: bool = False):
        """Returns where stepping forward from `position` stops: "step over",
        or with `into` "step into", or with `out` "step out". Returns None at
        the end."""
        for later in range(position + 1, len(self)):
            if self.step_stops(position, later, into, out):
                return later
        return None

    def step_stops(self, position: int, later: int, into: bool = False, out: bool = False) -> bool:
        """Returns whether stepping forward from `position`, as next_line
        says, stops at the later step `later` when no step between does."""
        line, depth = self.line_of(position)
        other_line, other_depth = self.line_of(later)
        if out:
            return other_depth < depth
        return (other_line != line or other_depth < depth) and (into or other_depth <= depth)

    def starts_line(self, position: int) -> bool:
        """Returns whether the step at `position` starts a source line."""
        return self._starts[position - self.first]

    def previous_line(self, position: int):
        """Returns where stepping back from `position` stops: the first step
        of the line before it, no deeper, passing over the steps of any call
        that line makes. Returns None at the start."""
        line, depth = self.line_of(position)
        found = target = None
        for earlier in range(position - 1, self.first - 1, -1):
            other = self.line_of(earlier)
            if found is None:
                if other[0] != line and other[1] <= depth:
                    found, target = earlier, other
            elif other == target:
                found = earlier
            elif other[1] <= target[1]:
                break
        return found

    def next_breakpoint(self, position: int, breakpoints: set, backward: bool = False):
        """Returns the next position after `position`, or before it with
        `backward`, whose step starts a line holding a breakpoint; None when
        there is none. `breakpoints` holds (path_key of a file, line). A line
        that makes a call stops once, before the call."""
        positions = (range(position - 1, self.first - 1, -1) if backward
                     else range(position + 1, len(self)))
        keys = {}   # {(run, file): its path_key}, worked out once per file
        for other in positions:
            if not self._starts[other - self.first]:
                continue
            step = self.step(other)
            file = (step.run, step.place.file)
            if file not in keys:
                keys[file] = path_key(self.path_of(step.place, step.run))
            if (keys[file], step.place.line) in breakpoints:
                return other
        return None


def path_key(path: str) -> str:
    """Returns the form of a path that compares equal for every way of writing it."""
    return os.path.normcase(os.path.abspath(path))
