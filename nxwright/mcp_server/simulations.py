"""What the MCP server's tools drive: a simulation of an app, whichever
kind it is. Each kind gives the same actions and the same looks, so that one
set of tools serves them all (server.py).

An action changes what the screen does, as a press or an instruction from
the serial line does; it returns once the simulation has handled it. A look
reads what the screen shows, and changes nothing. Points and boxes are in
the page's pixels, from its top left corner.
"""
from abc import ABC, abstractmethod
from pathlib import Path


class DrivenSimulation(ABC):
    """A simulation of the app of `source_folder` that the tools drive.
    `where` says where it runs: "headless", in the server's own process, or
    "vscode", in a VS Code window."""

    where: str

    def __init__(self, source_folder: Path):
        self.source_folder = source_folder
        # The number of the log's last line the tools gave the agent, so that
        # a send answers with only what came after it.
        self.log_given = 0

    # Actions.

    @abstractmethod
    def press(self, x: int, y: int):
        """Presses the screen at the page's pixel (x, y), and holds it."""

    @abstractmethod
    def move(self, x: int, y: int):
        """Moves the press held to the page's pixel (x, y)."""

    @abstractmethod
    def release(self):
        """Releases the press held."""

    @abstractmethod
    def wait(self, milliseconds: int):
        """Lets `milliseconds` pass, the app's timers running meanwhile."""

    @abstractmethod
    def send(self, instruction: str):
        """Runs `instruction` as if it came on the serial line."""

    @abstractmethod
    def set_input(self, pin: int, level: int):
        """Sets the level, 0 or 1, of the GPIO input `pin`, 0 to 7."""

    @abstractmethod
    def start_again(self):
        """Starts the app again, as a screen switched off and on."""

    @abstractmethod
    def stop(self):
        """Ends the simulation."""

    # Looks.

    @abstractmethod
    def screen(self, picture: bool = True) -> dict:
        """Returns what the screen shows: "text", its text layout
        (testing/screen_text.py); "page", the name of the page shown; and,
        when `picture`, "png", the bytes of a PNG picture of it. All three
        describe the same screen."""

    @abstractmethod
    def components(self) -> list:
        """Returns the components of the page shown, the page first, each
        a dict of `name`, `type`, `x`, `y`, `w`, `h`, and `shown`."""

    @abstractmethod
    def values(self, names: list = None) -> dict:
        """Returns {name: value} for `names`, or for every name, as the code
        of the page shown names them, such as "t0.txt" or "sys0"; a
        component's name alone, such as "t0", gives each of its attributes.
        Raises NxwrightError for a name that code does not know."""

    @abstractmethod
    def log(self, after: int = 0) -> list:
        """Returns the log's lines after line number `after`, each a dict of
        `number`, counted from 1 since the simulation started, `time`, the
        app's, in milliseconds, and `line`."""
