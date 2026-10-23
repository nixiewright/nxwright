"""Debugging a running simulation (testing/simulation.py).

A test's run is recorded whole before the debugger moves through it
(adapter.py). A simulation never ends, so it is debugged while it runs. It
runs on a thread of its own, recorded as it goes by a Recorder that keeps
its last KEEP steps. Before each statement, the recorder's watch asks
whether the debugger stops there: at a breakpoint's line, where a step
forward from the present ends, or where the debugger asked to pause. Once
stopped, the thread waits. The debugger moves through what was recorded,
backward and forward (replay.py), and moving forward past the present lets
the thread go on.

The simulation's time follows the clock on the wall while it runs, and
stands still while it is paused or stopped. Timers run one at a time,
presses and the serial line taking their turns between them. When the app's
events take longer than its timers' periods, a late timer runs once, at
once, as a screen runs it, rather than once for each period missed: the
simulation's time then falls behind the wall's. A `delay` holds the thread for
as long as it lasts, as it holds the screen; presses and typed instructions
wait meanwhile. After each thing that happens, the thread sends the drawing
of the page shown and the log's new lines; while an event runs long, as one
drawing a chart, it sends them too, from the values in progress, as the
Editor's simulator shows a long event drawing: LIVE_DRAWING seconds after
the last drawing ended, or as long as it took if longer.

A look at what the simulation holds, as its values, is taken on its
thread too, so that it never reads the simulation half changed: in turn
with the presses while the simulation runs, and at once while the debugger
holds the thread stopped, as the debugger's own views read it then.

An error in the code, such as a division by zero, stops the simulation as
on an exception, at the last step recorded; continuing goes on from there.
An app that does not build, or whose start fails, ends the session.
"""
from collections import deque
from pathlib import Path
import threading
import time

from nxwright.debug_adapter.replay import Timeline, path_key
from nxwright.testing.recording import Recorder
from nxwright.testing.simulation import Simulation

# How many of its last steps a simulation's recording keeps.
KEEP = 1_000_000
# The longest the thread waits before looking at the clock again, in seconds.
_LONGEST_WAIT = 0.25
# How often, in seconds, a long event's drawing in progress is sent.
LIVE_DRAWING = 0.1
# What the GPIO pins were last sent as before any were: unlike any pins, so
# that the first news sends them, None for a screen without GPIO included.
_NOT_SENT = object()
# The kind of a look in the queue of actions: it changes nothing, and is
# never replaced by another.
_LOOK = object()


class Ended(Exception):
    """Raised on the simulation's thread once the session ends, to leave
    the event running."""


class WallClock:
    """The time on the wall, and waiting for it to pass. A test may give the
    live simulation a clock of its own, moved by hand, so that tests of the
    pacing do not rest on how fast the machine runs."""

    def now(self) -> float:
        """The time on the wall, in seconds, from an arbitrary start."""
        return time.monotonic()

    def wait(self, condition: threading.Condition, seconds: float):
        """Waits `seconds` on `condition`, which the caller holds, or less
        when it is notified."""
        condition.wait(seconds)


class LiveSimulation:
    """A simulation running on its own thread, which the debugger stops.

    `notify(kind, body)` is called from the thread: "stopped", with the
    position and the reason, and the "description" of an error; "starting",
    with a StartProgress (simulation.py), as each start of the app compiles
    its pages; "drawing", with the simulation, after each thing that changed
    it; "log", with the log's new lines; "gpio", with the GPIO pins
    (Simulation.pins), at the start and whenever they change; and "failed",
    with why the app could not start. `start` starts the thread. The other
    methods are the debugger's, called from the adapter's thread. `sending`,
    `cards`, `eeprom_file`, `pinyin_table`, and `inputs` are the
    simulation's (simulation.py). `wall` is the clock on the wall the
    simulation's time follows, a WallClock unless given."""

    def __init__(self, source_folder, page=None, values=None, eeprom=b"", notify=None,
                 sending=None, cards=None, log_formats=None, wall: WallClock = None,
                 eeprom_file: Path = None, pinyin_table=None, inputs: dict = None):
        self.recorder = Recorder(keep=KEEP)
        self.timeline = Timeline(self.recorder)
        self.simulation = None
        self.breakpoints = set()     # {(path_key, line)}
        self._arguments = (source_folder, page, values, eeprom, sending, cards, log_formats,
                           eeprom_file, pinyin_table, inputs)
        self._notify = notify
        self._wall = wall if wall is not None else WallClock()
        self._condition = threading.Condition()
        self._actions = deque()      # (action, kind): what to do next on the thread, in order
        self._waiting = False        # whether the thread waits at a step
        self._paused = False         # whether the thread waits between events
        self._pause_asked = False
        self._ended = False
        self._busy = False           # whether the thread is doing something
        self._rule = None            # where a step forward stops, as position -> bool
        self._keys = {}              # {(run, file): its path_key}
        self._anchor = None          # (wall clock, simulation clock), when time last restarted
        # How far the simulation's clock was ahead of the wall's when it last
        # stopped, a `delay` not yet waited out, in milliseconds.
        self._owed = 0
        self._logged = 0
        self._drawn = None           # the simulation's `changes` when last drawn
        self._pins_sent = _NOT_SENT  # the GPIO pins as last sent
        # When the drawing was last sent, or the work running began; when it
        # was last sent; both by the clock on the wall; and how long the last
        # drawing took, in seconds.
        self._sent_at = 0.0
        self._drawn_at = 0.0
        self._drawing_time = 0.0
        self._thread = threading.Thread(target=self._main, name="simulation", daemon=True)

    # The debugger's side.

    def start(self, stop_on_entry: bool):
        """Starts the simulation, stopping at its first step when asked."""
        if stop_on_entry:
            self._rule = lambda position: True
        self._thread.start()

    @property
    def present(self) -> int:
        """The position of the last step recorded, or None before any."""
        self.timeline.catch_up()
        return len(self.timeline) - 1 if len(self.timeline) > self.timeline.first else None

    def resume(self, rule=None):
        """Lets the simulation go on, stopping at a breakpoint, or where
        `rule(position)` holds for a new step."""
        with self._condition:
            self._rule = rule
            self._waiting = self._paused = False
            self._anchor = None
            self._condition.notify_all()

    def pause(self):
        """Stops the simulation: at its next step while something runs, or
        between events, at the last step recorded."""
        with self._condition:
            if self._waiting or self._paused:
                return
            if self._busy:
                self._pause_asked = True
            else:
                self._paused = True
                self._stop(self.present, "pause")

    def act(self, action, kind: str = None):
        """Has the thread do `action(simulation)`, once what it does is done.
        An action of a `kind`, such as a move of the press, replaces one of
        the same kind still waiting last in the queue. Returns the action
        replaced, or None."""
        with self._condition:
            replaced = None
            if kind is not None and self._actions and self._actions[-1][1] == kind:
                replaced = self._actions.pop()[0]
            self._actions.append((action, kind))
            self._condition.notify_all()
        return replaced

    def look(self, read):
        """Has the thread do `read(simulation)`, which changes nothing: in
        turn with the actions while the simulation runs, and at once while
        the debugger holds it stopped. The simulation is None while the app
        is still starting. `read` must not raise."""
        with self._condition:
            self._actions.append((read, _LOOK))
            self._condition.notify_all()

    @property
    def stopped(self) -> bool:
        """Whether the debugger holds the simulation stopped, at a step or
        paused between events."""
        with self._condition:
            return self._waiting or self._paused

    @property
    def over(self) -> bool:
        """Whether the thread has ended, the session over or the app's start
        failed: nothing it is given to do will be done."""
        with self._condition:
            if self._ended:
                return True
        return self._thread.ident is not None and not self._thread.is_alive()

    def end(self):
        """Ends the session: the thread leaves what it runs and stops."""
        with self._condition:
            self._ended = True
            self._condition.notify_all()

    # The thread's side.

    def _main(self):
        (source_folder, page, values, eeprom, sending, cards, log_formats,
         eeprom_file, pinyin_table, inputs) = self._arguments
        self.recorder.watch = self._watch
        # Busy while the app starts, so that a pause meanwhile waits for a step.
        with self._condition:
            self._busy = True
        try:
            self.simulation = Simulation(source_folder, page, values, self.recorder, eeprom,
                                         sending=sending, leaving=self._page_leaving,
                                         cards=cards, log_formats=log_formats,
                                         eeprom_file=eeprom_file, pinyin_table=pinyin_table,
                                         inputs=inputs,
                                         starting=lambda progress: self._notify("starting",
                                                                                progress))
        except Ended:
            return
        except Exception as error:
            # An app that does not build, or whose start fails, ends the
            # session. The session is over before the adapter is told, so
            # a request that comes after `terminated` is refused at once.
            # Left for this thread, it would never be answered.
            self.end()
            self._notify("failed", "%s: %s" % (type(error).__name__, error))
            return
        finally:
            with self._condition:
                self._busy = False
        self._send_news()
        with self._condition:
            if self._pause_asked and not self._paused:
                self._pause_asked = False
                self._paused = True
                self._stop(self.present, "pause")
        while True:
            with self._condition:
                self._hold(lambda: self._paused or self._waiting)
                if self._ended:
                    return
                if self._anchor is None:
                    # Time starts again: a delay not waited out still holds.
                    self._anchor = (self._wall.now(), self.simulation.clock - self._owed)
                    self._owed = 0
            now = self._now()
            if self.simulation.clock > now:
                # A delay holds the screen until the wall clock catches up;
                # presses and typed instructions wait in the queue.
                self._wait((self.simulation.clock - now) / 1000)
                continue
            with self._condition:
                # Taken with the look for a pause, and marked busy at once,
                # so that a pause cannot slip between the two.
                if self._paused or self._waiting or self._ended:
                    continue
                action, kind = self._actions.popleft() if self._actions else (None, None)
                time_passes = action is None and int(now) > self.simulation.clock
                self._busy = (action is not None and kind is not _LOOK) or time_passes
            if kind is _LOOK:
                action(self.simulation)
            elif action is not None:
                self._do(lambda: action(self.simulation))
            else:
                if time_passes:
                    # Up to the next timer due, at most: timers run one at a
                    # time, and presses and the serial line take their turns
                    # between them.
                    due = self.simulation.next_due()
                    until = int(now) if due is None else min(int(now), due)
                    self._do(lambda: self.simulation.advance(
                        max(until - self.simulation.clock, 0)))
                    self._skip_missed_ticks()
                due = self.simulation.next_due()
                wait = _LONGEST_WAIT if due is None else \
                    min(max(due - self._now(), 0) / 1000, _LONGEST_WAIT)
                if wait > 0 and self.simulation.changes != self._drawn:
                    # Nothing to do now: a drawing held back while work waited goes.
                    self._send_news()
                self._wait(wait, True)

    def _skip_missed_ticks(self):
        """When the wall clock has already passed a timer's next run, as when
        the app's events take longer than its timers' periods, the timer
        runs once, at once, rather than once for each period missed: the
        simulation's time falls behind the wall's."""
        due = self.simulation.next_due()
        if due is not None and self._now() > due:
            with self._condition:
                if self._anchor is not None:
                    self._anchor = (self._wall.now(), due)

    def _now(self) -> float:
        """The simulation's time now, by the wall clock since time restarted."""
        if self._anchor is None:
            return self.simulation.clock
        restarted, clock = self._anchor
        return clock + (self._wall.now() - restarted) * 1000

    def _wait(self, seconds: float, until_action: bool = False):
        """Waits `seconds`, or less when an action comes and `until_action`."""
        with self._condition:
            if not self._ended and not (until_action and self._actions):
                self._wall.wait(self._condition, seconds)

    def _do(self, work) -> bool:
        """Does `work`, the thread marked busy, then sends the drawing and
        the log. An error in the code stops the simulation as on an
        exception. Returns False once the session ended."""
        # A drawing in progress comes only once the work has run LIVE_DRAWING.
        self._sent_at = self._wall.now()
        try:
            work()
        except Ended:
            return False
        except Exception as error:
            with self._condition:
                self._paused = True
                # The error's own text for an agent, or its kind when it has none.
                self._stop(self.present, "exception", "%s: %s" % (type(error).__name__, error),
                           str(error) or type(error).__name__)
        finally:
            with self._condition:
                self._busy = False
        if self.simulation is not None:
            # A pause shows the present, held back or not.
            self._send_news(busy=self._more_waiting() and not self._pause_asked)
        with self._condition:
            if self._pause_asked and not self._paused:
                self._pause_asked = False
                self._paused = True
                self._stop(self.present, "pause")
        return True

    def _page_leaving(self):
        """The page about to be left is drawn as its code left it: a page
        without background is drawn over it. Before the app has started,
        nothing shows yet."""
        if self.simulation is not None:
            self._send_news(in_progress=True)

    def _more_waiting(self) -> bool:
        """Whether more work waits to run now: a press, an instruction, or a
        timer due."""
        with self._condition:
            if self._actions:
                return True
        due = self.simulation.next_due() if self.simulation is not None else None
        return due is not None and due <= self._now()

    def _send_news(self, in_progress: bool = False, busy: bool = False):
        """Sends the drawing, when the state changed since the last, or when
        `in_progress`, an event running long, and a page shows; and the log's
        new lines. `busy`, more work waiting, holds the drawing back until
        its turn comes, as in progress. A failure to send them goes to the
        log rather than ending the thread."""
        try:
            changed = in_progress or self.simulation.changes != self._drawn
            # While a new page's load event runs, the screen still shows the
            # page before, which the panel keeps.
            loading = in_progress and self.simulation.loading
            # Drawing after each of many instructions arriving fast would hold
            # them up; the last, with nothing waiting, is drawn at once.
            early = busy and self._wall.now() - self._drawn_at < max(LIVE_DRAWING,
                                                                     self._drawing_time)
            if changed and self.simulation.page is not None and not loading and not early:
                self._drawn = self.simulation.changes
                began = self._wall.now()
                try:
                    self._notify("drawing", self.simulation)
                finally:
                    # Timed from its end, failed or not, so that the event's
                    # own work goes on between drawings in progress, however
                    # long one takes.
                    self._sent_at = self._drawn_at = self._wall.now()
                    self._drawing_time = self._sent_at - began
        except Exception as error:
            self.simulation.log.append((self.simulation.clock, "the panel could not be drawn: "
                                        "%s: %s" % (type(error).__name__, error)))
        lines = self.simulation.log[self._logged:]
        self._logged = len(self.simulation.log)
        if lines:
            self._notify("log", lines)
        pins = self.simulation.pins()
        if pins != self._pins_sent:
            self._pins_sent = pins
            self._notify("gpio", pins)

    def _watch(self, position: int, step):
        """Before each statement: sends a long event's drawing in progress
        when it is time, and stops there when the debugger should."""
        self.timeline.catch_up()
        # At least as long as the last drawing took passes between two, so
        # that drawing takes half of a long event's time at most.
        between = max(LIVE_DRAWING, self._drawing_time)
        if self.simulation is not None and not self.simulation.loading and \
                self._wall.now() - self._sent_at >= between:
            self._send_news(in_progress=True)
        with self._condition:
            if self._ended:
                raise Ended()
            reason = None
            if self._rule is not None and self._rule(position):
                reason = "step"
            elif self.breakpoints and self.timeline.starts_line(position) and \
                    (self._key(step), step.place.line) in self.breakpoints:
                reason = "breakpoint"
            elif self._pause_asked:
                reason = "pause"
            if reason is None:
                return
            self._rule, self._pause_asked = None, False
            self._waiting = True
            self._stop(position, reason)
            self._hold(lambda: self._waiting)
            if self._ended:
                raise Ended()

    def _hold(self, stopped):
        """Waits while `stopped()` holds, the condition held, taking each
        look that comes meanwhile: the thread stands still, so a look reads
        the simulation as it stands, an event's values in progress included.
        The looks run with the condition let go, so that the debugger's
        requests are not held up meanwhile."""
        while stopped() and not self._ended:
            looks = [read for read, kind in self._actions if kind is _LOOK]
            if not looks:
                self._condition.wait()
                continue
            self._actions = deque(entry for entry in self._actions if entry[1] is not _LOOK)
            self._condition.release()
            try:
                for read in looks:
                    read(self.simulation)
            finally:
                self._condition.acquire()

    def _key(self, step) -> str:
        file = (step.run, step.place.file)
        if file not in self._keys:
            self._keys[file] = path_key(self.timeline.path_of(step.place, step.run))
        return self._keys[file]

    def _stop(self, position, reason: str, description: str = None, error: str = None):
        """Tells the debugger the simulation stopped at `position`, keeping
        what is left of a delay for when it goes on. A stop on an exception
        gives, beside its `description`, the `error` it was on in words, for
        an agent's reply."""
        if self.simulation is not None and self._anchor is not None:
            self._owed = max(self.simulation.clock - self._now(), 0)
        self._notify("stopped", {"position": position, "reason": reason,
                                 "description": description, "error": error})
