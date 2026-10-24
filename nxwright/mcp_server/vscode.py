"""Simulations in VS Code, driven through a window's agent channel: the
local connection the nxwright extension opens while the setting
nxwright.agents.allowControl is on (editors/vscode/src/agentChannel.ts, and
agentChannelServer.ts, its VS Code side).

Each window with its channel open writes a file into the channels' folder
(channel_folder): the port the channel listens on, on 127.0.0.1, this
computer's own address, the same on every system; its token, a secret only
the user's own account can read; and the window's workspace folders. A
conversation says hello with the token first, then sends requests, one JSON
object a line: {id, method, params}, each answered {id, result} or {id,
error: {message}}. An error's message is written for the agent, which
reads it as it is.

A window runs one simulation at a time, a debugging session, which the
channel's requests name by the session's id. In VS Code the app runs on its
own, its time that of the clock on the wall.

The client never waits forever: connecting and the hello's answer have
HELLO_LIMIT, each other answer ANSWER_LIMIT. Each limit is on the whole
answer, not on each read, so that a program sending a byte at a time cannot
hold the client longer. A window that does not answer in time, as one whose
extension host hangs, is given up on, and the server answers other tools
again.
"""
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import sys
import time

from nxwright import NxwrightError
from nxwright.mcp_server.simulations import DrivenSimulation
from nxwright.testing.gpio_pins import PIN_NAMES

# The version of the channel's messages this server speaks, as hello gives it.
_MESSAGES_VERSION = 1
# The setting that opens a window's channel, as an error names it.
ALLOW_CONTROL = "nxwright.agents.allowControl"
# The one address the client connects to: this computer's own, as the
# extension listens on it (agentChannel.ts, CHANNEL_HOST). A file naming
# another is left out, so that the token never leaves this computer, even
# through a file someone changed.
CHANNEL_HOST = "127.0.0.1"
# How long connecting and the hello's answer may take, in seconds. The
# channel answers hello at once, so one later than this is a window that is
# gone, as one that crashed, whose file's port another program now holds.
HELLO_LIMIT = 5
# How long each other answer may take, in seconds: well past those that
# rightly take seconds, as a stop, which waits up to 10 s for the session's
# end, or a start, which waits for the app's.
ANSWER_LIMIT = 60


def channel_folder(platform: str = None, env=None, home: Path = None):
    """Returns the folder of the channels' files on the system `platform`,
    sys.platform by default, given its environment `env` and the user's
    home folder `home`, as the extension writes them there
    (agentChannel.ts, channelFolder): in the user's own application data.
    None on Windows without LOCALAPPDATA."""
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    if platform == "win32":
        local = env.get("LOCALAPPDATA")
        return Path(local) / "nxwright" / "agent-channels" if local else None
    home = Path(env.get("HOME") or Path.home()) if home is None else home
    if platform == "darwin":
        return home / "Library" / "Application Support" / "nxwright" / "agent-channels"
    data = env.get("XDG_DATA_HOME") or str(home / ".local" / "share")
    return Path(data) / "nxwright" / "agent-channels"


@dataclass(frozen=True)
class Window:
    """A VS Code window with its channel open, as its file says: `file`,
    the port the channel listens on, on `host`, its token, and the
    workspace folders."""
    file: Path
    host: str
    port: int
    token: str
    workspace_folders: tuple


def windows(folder) -> list:
    """Returns the Windows whose files lie in the channels' folder `folder`,
    in the files' order. A file that cannot be read, or says no window, is
    left out: one a window was writing, one of an older extension
    (holds_older_files), or one of something else. So is one whose host is
    not CHANNEL_HOST, or whose port is not a whole number a socket can
    have: Python would make port 70000 port 4464, which another program may
    hold."""
    found = []
    for file, said in _files(folder):
        try:
            host, port = str(said["host"]), said["port"]
            # Only a number the file gives as a whole one: int() would take
            # 5000.7, "5000", or true too.
            if host != CHANNEL_HOST or type(port) is not int or not 0 < port < 65536:
                continue
            found.append(Window(file, host, port, str(said["token"]),
                                tuple(str(entry) for entry in said["workspaceFolders"])))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def holds_older_files(folder) -> bool:
    """Whether the channels' folder `folder` holds a file of an older
    nxwright extension, whose channel this client cannot reach: one that
    gives an `address`, a named pipe or a Unix socket, and no port. A
    window running that extension writes one, and so did one that crashed,
    whose file stayed."""
    return any(isinstance(said, dict) and "address" in said and "port" not in said
               for _, said in _files(folder))


def _files(folder) -> list:
    """The channels' files in `folder`, in their names' order, each as
    (file, what it says); one that cannot be read is left out."""
    if folder is None or not folder.is_dir():
        return []
    found = []
    for file in sorted(folder.glob("*.json")):
        try:
            found.append((file, json.loads(file.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    return found


class Channel:
    """A conversation with one window's channel, which has said hello, for
    a request or two: a with statement closes it. Raises OSError, as it is
    made, when the channel does not answer within `hello_limit` seconds,
    as a window that crashed leaves its file, or refuses the token. Each
    other answer has `answer_limit` seconds."""

    def __init__(self, window: Window, hello_limit: float = None, answer_limit: float = None):
        self.window = window
        hello_limit = HELLO_LIMIT if hello_limit is None else hello_limit
        self._answer_limit = ANSWER_LIMIT if answer_limit is None else answer_limit
        self._unread = b""
        self._sent = 0
        self._socket = socket.create_connection((window.host, window.port), hello_limit)
        try:
            answer = self._exchange("hello", {"token": window.token}, hello_limit)
        except (OSError, NxwrightError) as error:
            self.close()
            raise OSError("the channel did not answer: %s" % error) from None
        if answer.get("version") != _MESSAGES_VERSION:
            self.close()
            raise OSError("the channel speaks messages of version %s, not %d"
                          % (answer.get("version"), _MESSAGES_VERSION))

    def __enter__(self):
        return self

    def __exit__(self, *raised):
        self.close()

    def call(self, method: str, params: dict) -> dict:
        """Returns the result of the request `method` with `params`. Raises
        NxwrightError with the channel's error, written for the agent, or
        saying the window did not answer in time, or stopped answering."""
        try:
            return self._exchange(method, params, self._answer_limit)
        except TimeoutError:
            raise NxwrightError(_too_late(method, self.window, self._answer_limit)) from None
        except OSError:
            raise NxwrightError("the VS Code window of %s stopped answering"
                                % ", ".join(self.window.workspace_folders)) from None

    def close(self):
        self._socket.close()

    def _exchange(self, method: str, params: dict, limit: float) -> dict:
        """Sends a request, and returns its result, which must come within
        `limit` seconds. Raises TimeoutError when it does not."""
        deadline = time.monotonic() + limit
        self._sent += 1
        self._socket.settimeout(limit)
        self._socket.sendall(json.dumps({"id": self._sent, "method": method, "params": params})
                             .encode("utf-8") + b"\n")
        while b"\n" not in self._unread:
            # Each read waits only for the time the whole answer has left.
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("no answer within %g s" % limit)
            self._socket.settimeout(left)
            data = self._socket.recv(65536)
            if not data:
                raise OSError("the channel closed the connection")
            self._unread += data
        line, self._unread = self._unread.split(b"\n", 1)
        try:
            answer = json.loads(line)
        except ValueError:
            raise OSError("the channel's answer is no JSON object") from None
        if "error" in answer:
            raise NxwrightError(str(answer["error"].get("message", "")))
        return answer.get("result") or {}


def _too_late(method: str, window: Window, limit: float) -> str:
    """What the agent reads when the window did not answer `method` within
    `limit` seconds."""
    said = ("the VS Code window of %s did not answer within %g s, so nxwright mcp stopped "
            "waiting: what was asked may still be done" % (", ".join(window.workspace_folders),
                                                          limit))
    if method == "start":
        # VS Code asks the user first when the folder is not trusted, as a
        # debugging session runs its code, or when the start connects a
        # serial port.
        said += (". VS Code may be asking the user first, such as whether to trust the folder, "
                 "or to connect a serial port: the simulation then starts as the user answers, "
                 "and list_simulations lists it")
    return said


class VsCodeWindows:
    """The VS Code windows whose channels are open, found from their files
    in `folder`, the channels' folder. Each request goes through a
    conversation of its own, so that a window reloaded, or one that
    stopped answering, is met afresh."""

    def __init__(self, folder, hello_limit: float = None, answer_limit: float = None):
        self._folder = folder
        # None takes HELLO_LIMIT and ANSWER_LIMIT as they are when used.
        self._limits = (hello_limit, answer_limit)

    def start(self, source_folder: Path, page: str = None) -> tuple:
        """Starts the app of `source_folder` in the window whose workspace
        contains it (window_for), from program.nx, or on `page`. Returns
        (VsCodeSimulation, the page the app is on, or None). It returns once
        the app has started, which waits for the user's answer when VS Code
        asks first."""
        source = Path(os.path.realpath(source_folder))
        params = {"sourceFolder": str(source)}
        if page is not None:
            params["page"] = page
        window = self.window_for(source)
        started = self.call(window.file, "start", params)
        return (VsCodeSimulation(source, self, window.file, started["session"]),
                started.get("page"))

    def running(self) -> list:
        """Returns the simulations running in each window that answers, as
        (window's file, session, source folder, page)."""
        found = []
        for window in windows(self._folder):
            try:
                with Channel(window, *self._limits) as channel:
                    listed = channel.call("simulations", {})["simulations"]
            except (OSError, NxwrightError):
                continue
            found += [(window.file, entry["session"], Path(entry["sourceFolder"]),
                       entry.get("page")) for entry in listed]
        return found

    def call(self, window_file: Path, method: str, params: dict) -> dict:
        """Returns the result of a request to the window whose channel's file
        is `window_file`. Raises NxwrightError with the window's refusal, or
        when the window is closed, did not answer the hello in time, or no
        longer lets agents in."""
        window = next((window for window in windows(self._folder)
                       if window.file == window_file), None)
        try:
            if window is None:
                raise OSError("its file is gone")
            with Channel(window, *self._limits) as channel:
                return channel.call(method, params)
        except OSError:
            raise NxwrightError("the VS Code window of this simulation is closed, did not "
                                "answer, or no longer lets agents in (%s)" % ALLOW_CONTROL
                                ) from None

    def window_for(self, source: Path) -> Window:
        """Returns the window whose workspace contains the source folder `source`,
        a real path, among those that answer: the one whose workspace folder
        containing it lies deepest. Raises NxwrightError when none contains
        it, or when several contain it alike, naming them."""
        containing = []
        for window in windows(self._folder):
            depths = [len(Path(folder).parts) for folder in map(os.path.realpath,
                                                                window.workspace_folders)
                      if _inside(source, Path(folder))]
            if depths and self._answers(window):
                containing.append((max(depths), window))
        if not containing:
            refusal = ("no VS Code window lets an agent start %s: open the folder in VS Code, "
                       "and turn on the setting %s in your user settings" % (source, ALLOW_CONTROL))
            if holds_older_files(self._folder):
                refusal += (". The channels' folder also holds a file of an older nxwright "
                            "extension, which this nxwright cannot reach: if a VS Code window "
                            "runs one, update it to this nxwright's version. A file a window "
                            "that crashed left looks the same")
            raise NxwrightError(refusal)
        deepest = max(depth for depth, _ in containing)
        chosen = [window for depth, window in containing if depth == deepest]
        if len(chosen) > 1:
            raise NxwrightError(
                "several VS Code windows contain %s alike, so it is not clear which to start "
                "it in: %s. Close all but one of them" % (source, "; ".join(
                    ", ".join(window.workspace_folders) for window in chosen)))
        return chosen[0]

    def _answers(self, window: Window) -> bool:
        """Whether `window`'s channel answers hello with its token, within
        the hello's limit."""
        try:
            Channel(window, *self._limits).close()
        except OSError:
            return False
        return True


class VsCodeSimulation(DrivenSimulation):
    """The simulation `session` of the VS Code window whose channel's file
    is `window_file`, reached through `windows`, a VsCodeWindows. The user
    watches it in the window's simulator panel, and may press the screen
    too."""

    where = "vscode"

    def __init__(self, source_folder: Path, windows: VsCodeWindows, window_file: Path,
                 session: str):
        super().__init__(source_folder)
        self._windows, self.window_file, self.session = windows, window_file, session

    def _call(self, method: str, **params) -> dict:
        return self._windows.call(self.window_file, method, dict(params, session=self.session))

    # Actions.

    def press(self, x: int, y: int):
        self._call("press", x=x, y=y)

    def move(self, x: int, y: int):
        self._call("move", x=x, y=y)

    def release(self):
        self._call("release")

    def wait(self, milliseconds: int):
        # The app runs on its own, on the clock on the wall.
        time.sleep(milliseconds / 1000)

    def send(self, instruction: str):
        self._call("serial", text=instruction)

    def set_input(self, pin: int, level: int):
        self._call("gpioInput", pin=pin, level=level)

    def set_inputs(self, levels: dict):
        # The channel takes the pins by name, as JSON's keys are texts.
        self._call("gpioInputs", levels={PIN_NAMES[pin]: level for pin, level in levels.items()})

    def start_again(self):
        self._call("startAgain")

    def stop(self):
        self._call("stop")

    # Looks.

    def screen(self, picture: bool = True) -> dict:
        shown = self._call("screen", picture=picture)
        found = {"text": shown["text"], "page": shown.get("page")}
        if picture and shown.get("png"):
            found["png"] = base64.b64decode(shown["png"])
        return found

    def components(self) -> list:
        return self._call("components")["components"]

    def values(self, names: list = None) -> dict:
        if names is None:
            return self._call("values")["values"]
        return self._call("values", names=names)["values"]

    def log(self, after: int = 0) -> list:
        return self._call("log", after=after)["lines"]


def _inside(source: Path, folder: Path) -> bool:
    """Whether the real path `source` lies inside the folder `folder`, or is
    it, as the system tells paths apart: on Windows, whatever the case of
    their letters."""
    try:
        common = os.path.commonpath([os.path.normcase(source), os.path.normcase(folder)])
    except ValueError:
        # Paths on different drives.
        return False
    return common == os.path.normcase(folder)
