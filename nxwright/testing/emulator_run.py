"""Running a source folder's app with its MCU emulator, in a test.

An MCU emulator is a Python program that takes the microcontroller's place
at the other end of the screen's serial line (nxwright/mcu.py). In the
simulator, the app and the emulator are two programs joined by a connection,
and both run in real time.

run_with_emulator runs the two in the test's own process, for a number of
seconds of the simulation's time (simulation.py), with the emulator's line
joined to the app directly. When the emulator waits in a read or a `sleep`,
that time passes without a real wait. A test can therefore run the app for
minutes of the simulation's time in a moment, and the run goes the same way
every time.

This works for an emulator that does all its waiting through the line. One
that calls time.sleep waits for real, and the simulation's time stands still
meanwhile.
"""
import sys
from pathlib import Path
from unittest import mock

from nxwright import NxwrightError, mcu
from nxwright.testing.simulation import Simulation

# How many times in a row an emulator may use the line without letting the
# simulation's time pass, before the line stops the test.
_MOST_CALLS_WITHOUT_WAITING = 100_000


def run_with_emulator(source_folder, main, seconds: float) -> "EmulatorRun":
    """Runs the app of the source folder `source_folder` with an MCU emulator
    for `seconds` seconds of the simulation's time, and returns what
    happened, as an EmulatorRun.

    `main` is the function that runs the emulator, and is called with no
    arguments. While `main` runs:
      - mcu.open returns a line joined to the app, whatever it is given. The
        app has started by then, and what it sent when it started waits in
        the line.
      - sys.argv has the program's name alone, so that an emulator that
        reads a port number from the command line finds none.

    Only a read that waits and a `sleep` let the simulation's time pass. An
    emulator that goes on using the line without either, such as a loop that
    polls `in_waiting`, would never end, so the line stops it with
    NxwrightError after _MOST_CALLS_WITHOUT_WAITING uses of the line in a
    row.

    Once `seconds` have passed, the line closes, the same as when a
    simulation ends. The emulator's next `sleep` or write then raises
    mcu.LineClosed, and so does its next read once no byte is left to return.
    A LineClosed that `main` does not catch ends the emulator, and does not
    reach the test. If `main` returns before the time is over, the app runs
    on alone for the rest of the time.

    Raises NxwrightError if the app does not build, or its start fails."""
    line = _SimulatedLine(seconds)
    line.join(Simulation(Path(source_folder), sending=line.screen_sent))
    with mock.patch.object(mcu, "open", lambda listen=None: line), \
            mock.patch.object(sys, "argv", sys.argv[:1]):
        try:
            main()
        except mcu.LineClosed:
            pass
    line.run_out()
    return EmulatorRun(line)


class EmulatorRun:
    """What happened while an app ran with its MCU emulator
    (run_with_emulator):
      - `received`: the bytes the screen received from the emulator;
      - `sent`: the bytes the screen sent;
      - `page`: the name of the page shown at the end;
      - `value(name)`: a value at the end."""

    def __init__(self, line: "_SimulatedLine"):
        self._simulation = line.simulation
        self.received = bytes(line.received)
        self.sent = bytes(line.sent)

    @property
    def page(self) -> str:
        return self._simulation.page

    def value(self, name: str):
        """Returns the value of `name` at the end of the run. `name` is
        written the way the code of the page shown writes it, such as
        `t0.txt`, `settings.limit.val` for a component of another page, or
        the name of a variable of program.nx. Raises NxwrightError if the app
        has no such value."""
        values = self._simulation.values()
        if name not in values:
            raise NxwrightError("the app has no value named %s on the page %s"
                                % (name, self._simulation.page))
        return values[name]


class _SimulatedLine(mcu.LineBase):
    """The screen's serial line, joined to a Simulation in the same process
    for `seconds` seconds of the simulation's time. It has the members of
    mcu.Line. A read that waits, and a `sleep`, let the simulation's time
    pass, in whole milliseconds. Once the run's time is over, the line is
    closed, the same as mcu.Line once the simulation has closed its end.

    `received` is what the screen received from the emulator, and `sent`
    what the screen sent, each as a bytearray."""

    def __init__(self, seconds: float):
        super().__init__()
        self.simulation = None
        self.received = bytearray()
        self.sent = bytearray()
        # How much of the simulation's time has passed since the run began,
        # and how much of the run is left, in milliseconds. The line counts
        # both itself, because the simulation's own clock starts again from
        # 0 when the app starts again.
        self._passed = 0
        self._left = max(round(seconds * 1000), 0)
        # How many times in a row the emulator used the line without letting
        # time pass (_used).
        self._calls_without_waiting = 0

    def join(self, simulation: Simulation):
        """Joins the line to `simulation`, which must have been created with
        this line's `screen_sent` as its `sending`."""
        self.simulation = simulation
        self._pass(0)

    def screen_sent(self, data: bytes):
        """Receives the bytes the screen sends. The Simulation calls it as
        its `sending`."""
        self.sent += data
        self._waiting += data

    def write(self, data: bytes) -> int:
        """Sends `data` to the screen, and returns how many bytes that is.
        The screen runs the instructions in `data` at once. Raises LineClosed
        once the line is closed."""
        self._used()
        if self._over:
            raise mcu.LineClosed("the simulation closed the line")
        self.received += data
        self.simulation.serial_received(bytes(data))
        return len(data)

    @property
    def in_waiting(self) -> int:
        """How many bytes a read would return without waiting."""
        self._used()
        return len(self._waiting)

    def sleep(self, seconds: float):
        """Lets `seconds` seconds of the simulation's time pass. Raises
        LineClosed if the run's time is over by then, so that an emulator
        that only sleeps ends too. Raises ValueError if `seconds` is
        negative, the same as time.sleep."""
        if seconds < 0:
            raise ValueError("sleep length must be non-negative")
        self._used()
        self._pass(round(seconds * 1000))
        if self._over:
            raise mcu.LineClosed("the simulation closed the line")

    def close(self):
        """Closes the line. The app runs on."""
        self._over = True

    def run_out(self):
        """Lets what is left of the run's time pass."""
        self._pass(self._left)

    def _deadline(self):
        """Returns when a read that starts now stops waiting, in milliseconds
        of the simulation's time since the run began, or None if the read
        waits until the run's time is over. Each read calls `_deadline`
        once, so `_deadline` also counts the read as a use of the line."""
        self._used()
        return None if self.timeout is None else self._passed + round(self.timeout * 1000)

    def _more(self, deadline) -> bool:
        """Lets the simulation's time pass until the screen sends bytes, or
        until `deadline`, or until the run's time is over. Returns whether
        bytes came."""
        count = len(self._waiting)
        while len(self._waiting) == count and not self._over:
            wait = self._left if deadline is None else min(self._left, deadline - self._passed)
            if wait <= 0:
                return False
            # Wait only until the next thing the screen does by itself,
            # such as a timer's event, because only that can send bytes.
            due = self.simulation.next_due()
            if due is not None:
                wait = min(wait, max(due - self.simulation.clock, 1))
            self._pass(wait)
        return len(self._waiting) > count

    def _used(self):
        """Counts one use of the line by the emulator. Raises NxwrightError
        once the emulator has used the line _MOST_CALLS_WITHOUT_WAITING
        times in a row without letting time pass, because the app cannot do
        anything meanwhile, and such a loop would never end."""
        self._calls_without_waiting += 1
        if self._calls_without_waiting > _MOST_CALLS_WITHOUT_WAITING:
            raise NxwrightError(
                "the emulator used the line %d times in a row without waiting, so the "
                "simulation's time cannot pass. Please make the emulator wait with "
                "line.sleep, or in a read" % _MOST_CALLS_WITHOUT_WAITING)

    def _pass(self, milliseconds: int):
        """Lets `milliseconds` of the simulation's time pass, or what is left
        of the run's time if that is less. Closes the line once the run's
        time is over."""
        step = min(milliseconds, self._left)
        if step > 0:
            self.simulation.advance(step)
            self._calls_without_waiting = 0
        self._passed += step
        self._left -= step
        if self._left == 0:
            self._over = True
