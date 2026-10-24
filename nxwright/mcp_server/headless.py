"""A headless simulation: the app of a source folder running in the MCP
server's own process, without VS Code (testing/simulation.py).

Its time moves only when a tool lets it: a wait of 500 ms runs, at once,
whatever falls due in the next 500 ms of the app's time. It has no serial
port, and its SD cards are kept in memory. Its pinyin table, for Chinese
input, is the installed Nextion Editor's, when one is found, as a
simulation in VS Code takes it by default.

An error in the app's code, such as a division by zero, raises NxwrightError
saying so, as the simulator in VS Code stops on it. The simulation stays as
the error left it, and goes on with the next action.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.drawing.screen_pictures import ScreenPictures
from nxwright.mcp_server.simulations import DrivenSimulation
from nxwright.testing import looks
from nxwright.testing.gpio_pins import checked_level
from nxwright.testing.pinyin_table import installed_pinyin_table, read_pinyin_table
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation


class HeadlessSimulation(DrivenSimulation):
    """The app of `source_folder`, started from program.nx, or on `page`
    without running program.nx. Raises NxwrightError when the app does not
    build, as the simulator in VS Code refuses it."""

    where = "headless"

    def __init__(self, source_folder: Path, page: str = None):
        super().__init__(Path(source_folder).resolve())
        # The pictures keep what a page without background is drawn over,
        # as the simulator's panel does: so each page left is shown to them.
        self._previews = Previews()
        self._pictures = ScreenPictures()
        # None until the app has started: a page left meanwhile shows nothing.
        self._simulation = None
        self._simulation = _running_app(lambda: Simulation(
            self.source_folder, page, pinyin_table=_pinyin_table(), leaving=self._leaving))

    def _leaving(self):
        """The page about to be left, as its code left it. Before the app has
        started, nothing shows yet."""
        if self._simulation is not None:
            inputs = self._simulation.drawing_inputs()
            self._pictures.shown(self._previews.simulation_drawing(self._simulation, inputs))

    # Actions.

    def press(self, x: int, y: int):
        simulation = self._simulation
        self._touchable("press", x, y)
        _running_app(lambda: simulation.press(simulation.component_at(x, y), x, y))

    def move(self, x: int, y: int):
        self._touchable("move", x, y)
        _running_app(lambda: self._simulation.move(x, y))

    def release(self):
        _running_app(self._simulation.release)

    def _touchable(self, action: str, x: int, y: int):
        """Raises NxwrightError when the screen cannot take the touch
        (looks.touch_refusal)."""
        refusal = looks.touch_refusal(self._simulation, action, x, y)
        if refusal is not None:
            raise NxwrightError(refusal)

    def wait(self, milliseconds: int):
        _running_app(lambda: self._simulation.advance(milliseconds))

    def send(self, instruction: str):
        _running_app(lambda: self._simulation.serial_input(instruction))

    def set_input(self, pin: int, level: int):
        checked_level(pin, level)
        _running_app(lambda: self._simulation.set_input(pin, level))

    def set_inputs(self, levels: dict):
        _running_app(lambda: self._simulation.set_inputs(levels))

    def start_again(self):
        _running_app(self._simulation.start_again)

    def stop(self):
        self._simulation = None

    # Looks.

    def screen(self, picture: bool = True) -> dict:
        return looks.screen(self._simulation, self._previews, self._pictures, picture)

    def components(self) -> list:
        return looks.components(self._simulation)

    def values(self, names: list = None) -> dict:
        return looks.values(self._simulation, names)

    def log(self, after: int = 0) -> list:
        return looks.log(self._simulation, after)


def _running_app(action):
    """Returns action(), which runs the app's code. nxwright's own refusals,
    NxwrightError, pass as they are. Any other exception is an error in the
    app's code, as the simulator in VS Code takes it (debug_adapter/live.py),
    and raises NxwrightError naming it."""
    try:
        return action()
    except NxwrightError:
        raise
    except Exception as error:
        # A division by zero, for one, comes with no message of its own.
        said = ": %s" % error if str(error) else ""
        raise NxwrightError("the app's code stopped with an error: %s%s"
                            % (type(error).__name__, said)) from error


def _pinyin_table():
    """The installed Nextion Editor's pinyin table, or None. One that cannot
    be read leaves the simulation without a table: the app still runs, and
    its log says so at its first pinyin command."""
    installed = installed_pinyin_table()
    if installed is None:
        return None
    try:
        return read_pinyin_table(installed)
    except NxwrightError:
        return None
