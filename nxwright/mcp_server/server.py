"""The MCP server's tools, on zeromcp, and the simulations they drive, each
by an id the server gives: "headless-1" for one running in the server's own
process (headless.py), "vscode-1" for one in a VS Code window (vscode.py).

The tools run one at a time: zeromcp's stdio reads a request only once it
has answered the one before. A Simulation needs that, as it is not made to
be driven from two threads.

zeromcp answers a tool with text alone, so `screen` writes its picture to a
PNG file and gives the file's path. The files are kept in a folder of the
computer's temporary folder until the server ends.
"""
import functools
from pathlib import Path
import tempfile
from typing import Annotated, BinaryIO

from zeromcp import McpServer, McpToolError

from nxwright import NxwrightError, installed_version
from nxwright.mcp_server.headless import HeadlessSimulation
from nxwright.mcp_server.simulations import DrivenSimulation
from nxwright.mcp_server.vscode import VsCodeSimulation, VsCodeWindows, channel_folder

# What an agent reads of the server as it connects.
_INSTRUCTIONS = (
    "Runs Nextion screen apps from nxwright source folders, as nxwright's simulator does, "
    "and lets you drive them. Start one with start_simulation, see the screen with screen, "
    "press it with tap, and let its timers run with wait. Points and boxes are in the "
    "page's pixels, from its top left corner, as in the picture that screen gives. Before "
    "you change an app or start one, call about: it guides you through the app's files, "
    "checking a change, and these tools, and lists the topics of nxwright's docs, which "
    "about gives by name.")
# The guide that `about` gives, written for an agent. It ships with the
# package (pyproject.toml), so that it matches the tools installed.
GUIDE_FILE = Path(__file__).resolve().parent / "guide.md"
# nxwright's package folder, which an install's docs lie in, and a source
# tree's lie beside (docs_folder).
_PACKAGE = Path(__file__).resolve().parent.parent
# The docs' contributors' writing guide, of no use to an agent: it does not
# ship (pyproject.toml), and is no topic in a source tree either.
_NOT_A_TOPIC = "STYLE"

SimulationId = Annotated[str, "The simulation's id, as start_simulation gave it."]
Component = Annotated[str | None, "A component of the page shown, by name, pressed at its "
                                  "centre. Give either this, or x and y."]
_ACROSS = "The page's pixel across, from its left edge."
_DOWN = "The page's pixel down, from its top edge."
X = Annotated[int | None, _ACROSS]
Y = Annotated[int | None, _DOWN]
# The longest wait, in milliseconds. The server answers one request at a
# time, so a long wait on an app whose timers run often would leave the agent
# no way to stop it; a longer wait is made in steps.
_LONGEST_WAIT = 60000
# The most lines of the log that a send answers with: the last ones, which
# end with the answer to the instruction sent.
_LOGGED_SHOWN = 10


def serve(stdin: BinaryIO, stdout: BinaryIO):
    """Serves MCP on `stdin` and `stdout` until the agent closes them."""
    with tempfile.TemporaryDirectory(prefix="nxwright-mcp-") as folder:
        mcp_server(Path(folder)).stdio(stdin, stdout)


def mcp_server(pictures_folder: Path) -> McpServer:
    """Returns the server, with its tools, writing the pictures `screen`
    takes into `pictures_folder`."""
    simulations = _Simulations(pictures_folder)
    # The protocol wants a version even from a source copy, which has none.
    server = McpServer("nxwright", installed_version() or "unknown", _INSTRUCTIONS)

    # Registered first, and named to sort first, so that it leads the list of
    # tools, whether an agent keeps the server's order or sorts them by name.
    @server.tool
    @_refusals
    def about(topic: Annotated[str | None, "A topic of nxwright's docs, such as testing, "
                                          "as the list after the guide gives them. Without "
                                          "it, the guide."] = None) -> str:
        """A usage guide to read first: the files of an app's source folder, checking a
        change, using these tools, and what to do when one refuses. It ends with the topics
        of nxwright's docs: with a topic, about gives that doc, whole."""
        return about_text(topic, docs_folder())

    @server.tool
    @_refusals
    def start_simulation(
            source_folder: Annotated[str, "The source folder of the app: the folder that "
                                          "contains its app.toml."],
            page: Annotated[str | None, "A page to start on, without running program.nx. "
                                        "Without it, the app starts from program.nx, as a "
                                        "screen switched on does."] = None,
            in_vscode: Annotated[bool, "Whether to start it in VS Code, in the window whose "
                                       "workspace contains the source folder, where the user "
                                       "watches it."] = False) -> dict:
        """Starts the app of a source folder in a simulation. Without in_vscode, it runs
        without VS Code: its time moves only when you let it, with wait, it has no serial
        port, and its SD cards start empty. With in_vscode, it runs in the VS Code window
        whose workspace contains the folder, if that window lets agents in (the user setting
        nxwright.agents.allowControl), on the clock on the wall; VS Code may ask the user
        first, and the start then waits for the answer. Returns the simulation's id, which
        the other tools take, and the page the app is on."""
        return simulations.start(Path(source_folder), page, in_vscode)

    @server.tool
    @_refusals
    def list_simulations() -> list:
        """Lists the simulations running, each with its id, its source folder, where it
        runs, "headless" or "vscode", and the page the app is on: those this server
        started without VS Code, and those of each VS Code window that lets agents in,
        whether the user or an agent started them."""
        return simulations.listed()

    @server.tool
    @_refusals
    def screen(simulation: SimulationId,
               picture: Annotated[bool, "Whether to write a picture of the screen too."] = True
               ) -> str:
        """Describes what the screen shows: one line for each component that shows, in the
        order they are drawn, so that a later line lies on top, then what the app's code
        painted, then the components that do not show. Unless picture is false, it ends
        with the path of a PNG file of the screen, at one pixel for each of the page's."""
        return simulations.screen(simulation, picture)

    @server.tool
    @_refusals
    def components(simulation: SimulationId) -> list:
        """Lists the components of the page shown, the page first, each with its name, type,
        box (x, y, w, h), and whether it shows. A component without a place on the screen,
        as a timer, has no box."""
        return simulations.get(simulation).components()

    @server.tool
    @_refusals
    def tap(simulation: SimulationId, component: Component = None, x: X = None,
            y: Y = None) -> str:
        """Presses the screen, then releases it, as a finger tapping. If the app's code stops
        with an error as the screen is pressed, the press stays held: release lets it go."""
        driven = simulations.get(simulation)
        driven.press(*_point(driven, component, x, y))
        driven.release()
        return "Tapped."

    @server.tool
    @_refusals
    def press(simulation: SimulationId, component: Component = None, x: X = None,
              y: Y = None) -> str:
        """Presses the screen and holds it, until release. Move the press with move, as a
        finger dragging. The screen takes one touch at a time."""
        driven = simulations.get(simulation)
        driven.press(*_point(driven, component, x, y))
        return "Pressed."

    @server.tool
    @_refusals
    def move(simulation: SimulationId, x: Annotated[int, _ACROSS],
             y: Annotated[int, _DOWN]) -> str:
        """Moves the press held to another point of the page."""
        simulations.get(simulation).move(x, y)
        return "Moved."

    @server.tool
    @_refusals
    def release(simulation: SimulationId) -> str:
        """Releases the press held."""
        simulations.get(simulation).release()
        return "Released."

    @server.tool
    @_refusals
    def wait(simulation: SimulationId,
             milliseconds: Annotated[int, "How long, in milliseconds, from 0 to 60000."]
             ) -> str:
        """Lets time pass in the app: its timers run, and what moves on the screen moves.
        Without VS Code, the app's time moves that much at once; in VS Code, the app runs
        on its own, and this waits as long on the clock. For longer than a minute, wait
        again."""
        if milliseconds < 0:
            raise NxwrightError("a wait lasts 0 milliseconds or more")
        if milliseconds > _LONGEST_WAIT:
            raise NxwrightError("a wait lasts at most %d milliseconds: wait again for longer"
                                % _LONGEST_WAIT)
        simulations.get(simulation).wait(milliseconds)
        return "Waited %d ms." % milliseconds

    @server.tool
    @_refusals
    def send(simulation: SimulationId,
             instruction: Annotated[str, "An instruction in Nextion's language, such as "
                                         "page 1 or t0.txt=\"Hi\"."]) -> str:
        """Sends the screen an instruction, as if it came on the serial line. Answers with
        the log's lines since your last send or log, or since the start: what the screen
        received, what it sent back, such as a return code or what get asked for, and why
        an instruction did not run. The last 10 lines at most."""
        simulations.get(simulation).send(instruction)
        given, logged = simulations.log_since_given(simulation)
        since = "since your last send or log" if given else "since the simulation started"
        if not logged:
            return "Sent. The log has no line %s." % since
        lines = ["Sent. The log %s:" % since]
        if len(logged) > _LOGGED_SHOWN:
            lines.append("... %d lines before these: call log with after %d"
                         % (len(logged) - _LOGGED_SHOWN, given))
        return "\n".join(lines + logged[-_LOGGED_SHOWN:])

    @server.tool
    @_refusals
    def log(simulation: SimulationId,
            after: Annotated[int, "Only the lines after the one of this number."] = 0) -> list:
        """Lists the simulation's log: what the screen receives and sends on its serial
        line, and what else happens outside the screen, as a start again. Each line comes
        with its number, counted from 1, and the app's time in milliseconds."""
        return simulations.log(simulation, after)

    @server.tool
    @_refusals
    def values(simulation: SimulationId,
               names: Annotated[list[str] | None, "The names to read, such as t0.txt or "
                                                  "sys0, or a component's name alone, such as "
                                                  "t0, for each of its attributes. Without "
                                                  "them, every value."] = None
               ) -> dict:
        """Reads values as the code of the page shown names them: components' attributes,
        such as t0.txt, int variables, and system variables, such as sys0. A component's
        name alone gives each of its attributes."""
        return simulations.get(simulation).values(names)

    @server.tool
    @_refusals
    def set_input(simulation: SimulationId,
                  pin: Annotated[int, "The GPIO pin, 0 to 7."],
                  level: Annotated[int, "Its level, 0 or 1."]) -> str:
        """Sets the level that the world outside the screen gives a GPIO input, as a
        button or a switch wired to it would."""
        simulations.get(simulation).set_input(pin, level)
        return "Set."

    @server.tool
    @_refusals
    def start_again(simulation: SimulationId) -> str:
        """Starts the app again, as a screen switched off and on. The EEPROM keeps what the
        app wrote."""
        simulations.get(simulation).start_again()
        return "Started again."

    @server.tool
    @_refusals
    def stop_simulation(simulation: SimulationId) -> str:
        """Ends the simulation."""
        simulations.stop(simulation)
        return "Stopped."

    return server


def docs_folder(package: Path = _PACKAGE):
    """Returns the folder of nxwright's docs: `package`'s docs/, as an
    install holds them (pyproject.toml ships them there), or else docs/
    beside `package` in a source tree, as a checkout and an editable install
    have them. None when neither is there, as after a packaging slip. A
    folder beside an installed package is no source tree's, as one another
    project left in site-packages, so it is not taken."""
    installed = package / "docs"
    if installed.is_dir():
        return installed
    tree = package.parent
    if (tree / "pyproject.toml").is_file() and (tree / "docs").is_dir():
        return tree / "docs"
    return None


def about_text(topic: str, folder) -> str:
    """Returns what `about` gives: with no `topic`, the guide, then the docs'
    topics, each with its doc's title; with a topic, that doc, whole. A
    topic is a doc's file name, with or without ".md", looked up among the
    docs of `folder` (docs_folder), never joined to it as a path. Raises
    NxwrightError for a topic the docs do not have, or when `folder` is
    None, saying the docs are not installed."""
    docs = _topics(folder)
    if topic is None:
        return GUIDE_FILE.read_text(encoding="utf-8") + _topic_list(docs)
    if folder is None:
        raise NxwrightError("nxwright's docs are not installed here, so there is no topic %s"
                            % topic)
    name = topic[:-len(".md")] if topic.endswith(".md") else topic
    if name not in docs:
        raise NxwrightError("nxwright's docs have no topic %s; the topics are %s"
                            % (topic, ", ".join(docs)))
    return docs[name].read_text(encoding="utf-8")


def _topics(folder) -> dict:
    """Returns {topic: its doc's file} of the docs in `folder`, by name, but
    the contributors' writing guide; none for no folder."""
    if folder is None:
        return {}
    return {path.stem: path for path in sorted(folder.glob("*.md")) if path.stem != _NOT_A_TOPIC}


def _topic_list(docs: dict) -> str:
    """The guide's last section: the docs' topics, each with its doc's
    title, its first line without the heading's "# ", or that the docs are
    not installed."""
    if not docs:
        return ("\n## nxwright's docs\n\nnxwright's docs are not installed here, so `about` "
                "gives no topic.\n")
    lines = ["", "## nxwright's docs", "",
             "Call `about` with a topic for that doc of nxwright's docs, whole:", ""]
    for name, path in docs.items():
        with open(path, encoding="utf-8") as doc:
            title = doc.readline().strip().removeprefix("# ")
        lines.append("- `%s`: %s" % (name, title))
    return "\n".join(lines) + "\n"


class _Simulations:
    """The simulations running, by id, and the pictures `screen` writes."""

    def __init__(self, pictures_folder: Path):
        self._pictures_folder = pictures_folder
        self._running = {}
        self._started = {"headless": 0, "vscode": 0}
        self._pictures = 0
        self._windows = VsCodeWindows(channel_folder())

    def start(self, source_folder: Path, page: str = None, in_vscode: bool = False) -> dict:
        if in_vscode:
            driven, shown = self._windows.start(source_folder, page)
        else:
            driven = HeadlessSimulation(source_folder, page)
            shown = _page_shown(driven)
        return {"simulation": self._named(driven), "page": shown}

    def _named(self, driven: DrivenSimulation) -> str:
        """Gives `driven` the next id of its kind, and keeps it by that id."""
        self._started[driven.where] += 1
        simulation = "%s-%d" % (driven.where, self._started[driven.where])
        self._running[simulation] = driven
        return simulation

    def _take_vscode_simulations(self) -> dict:
        """Keeps by an id each simulation the VS Code windows run, the user's
        own included, so that the tools reach them, and forgets those that
        no longer run. Returns the page each one's app is on, by its id, as
        its window listed it."""
        running = self._windows.running()
        now = {(file, session) for file, session, _, _ in running}
        kept = {}
        for simulation, driven in list(self._running.items()):
            if isinstance(driven, VsCodeSimulation):
                if (driven.window_file, driven.session) in now:
                    kept[(driven.window_file, driven.session)] = simulation
                else:
                    del self._running[simulation]
        pages = {}
        for file, session, source_folder, page in running:
            if (file, session) not in kept:
                kept[(file, session)] = self._named(VsCodeSimulation(
                    source_folder, self._windows, file, session))
            pages[kept[(file, session)]] = page
        return pages

    def get(self, simulation: str) -> DrivenSimulation:
        if simulation not in self._running:
            raise NxwrightError("no simulation %s runs: list_simulations lists those that do"
                                % simulation)
        return self._running[simulation]

    def stop(self, simulation: str):
        self.get(simulation).stop()
        del self._running[simulation]

    def log(self, simulation: str, after: int) -> list:
        """The log's lines after line number `after`, the last of them noted
        as given to the agent."""
        driven = self.get(simulation)
        lines = driven.log(after)
        if lines:
            driven.log_given = max(driven.log_given, lines[-1]["number"])
        return lines

    def log_since_given(self, simulation: str) -> tuple:
        """The number of the log's last line given to the agent, and the
        lines logged since."""
        given = self.get(simulation).log_given
        return given, [entry["line"] for entry in self.log(simulation, given)]

    def listed(self) -> list:
        # A VS Code simulation's page comes with its window's list, rather
        # than from a request of its own, which a window closing between
        # the two would fail.
        vscode_pages = self._take_vscode_simulations()
        return [{"simulation": simulation, "source_folder": str(driven.source_folder),
                 "where": driven.where,
                 "page": vscode_pages[simulation] if simulation in vscode_pages
                 else _page_shown(driven)}
                for simulation, driven in self._running.items()]

    def screen(self, simulation: str, picture: bool) -> str:
        shown = self.get(simulation).screen(picture)
        # No picture before a page shows, as before program.nx opens one.
        if "png" not in shown:
            return shown["text"]
        # A new file each time, so that an earlier picture stays as it was.
        self._pictures += 1
        path = self._pictures_folder / ("%s-%d.png" % (simulation, self._pictures))
        path.write_bytes(shown["png"])
        return "%s\npicture: %s" % (shown["text"], path)


def _page_shown(driven: DrivenSimulation):
    """The name of the page `driven`'s app is on, which taps go to, or None
    before it opens one. While `ref_stop` holds the screen after a page
    change, the screen still shows the page before (screen)."""
    shown = driven.components()
    return shown[0]["name"] if shown else None


def _point(driven: DrivenSimulation, component: str, x: int, y: int) -> tuple:
    """The page's pixel a press goes to: the centre of `component`'s box,
    or (x, y). Raises NxwrightError unless one of the two is given."""
    if component is None:
        if x is None or y is None:
            raise NxwrightError("give a component's name, or x and y")
        return x, y
    if x is not None or y is not None:
        raise NxwrightError("give a component's name, or x and y, not both")
    found = next((entry for entry in driven.components() if entry["name"] == component), None)
    if found is None:
        raise NxwrightError("the page shown has no component named %s" % component)
    if found["x"] is None:
        raise NxwrightError("%s has no place on the screen, so it cannot be pressed"
                            % component)
    if not found["shown"]:
        raise NxwrightError("%s does not show, so it cannot be pressed" % component)
    return found["x"] + found["w"] // 2, found["y"] + found["h"] // 2


def _refusals(tool):
    """Has `tool` answer nxwright's refusals, NxwrightError, and a file it
    cannot read, OSError, as a tool's error, which the agent reads: the
    command line takes them so too (cli.main). Any other exception is a
    bug, which zeromcp answers with its traceback."""
    @functools.wraps(tool)
    def refusing(*arguments, **named):
        try:
            return tool(*arguments, **named)
        except (NxwrightError, OSError) as error:
            raise McpToolError(str(error)) from None
    return refusing
