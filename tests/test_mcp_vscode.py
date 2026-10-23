"""The MCP server driving simulations in VS Code (mcp_server/vscode.py),
through each window's agent channel, which a stand-in written here plays:
it listens where the extension's channel does, on 127.0.0.1, says so in
its window's file, and answers the channel's messages
(editors/vscode/src/agentChannelServer.ts)."""
import base64
import json
import os
from pathlib import Path
import secrets
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from nxwright.mcp_server import vscode
from nxwright.mcp_server.server import mcp_server
from nxwright.mcp_server.vscode import channel_folder
from nxwright.project.pictures import write_png
from tests.test_mcp_server import APP, _Agent

# The answer of a component list, as the channel gives the page's.
COMPONENTS = [{"name": "page0", "type": "page", "x": 0, "y": 0, "w": 800, "h": 480,
               "shown": True},
              {"name": "b0", "type": "button", "x": 20, "y": 400, "w": 100, "h": 50,
               "shown": True}]
PNG = write_png(1, 1, bytes((10, 20, 30, 255)))


class StandInChannel:
    """A window's agent channel, standing in for VS Code: it listens on
    127.0.0.1, on a port the system picks, as the extension's channel does,
    and a file in `folder` says so, with its token and the window's
    workspace folders. It answers each conversation's requests, once hello
    came with the token, from `running`, the window's one simulation, or
    None. `requests` lists those it was sent after hello, as (method,
    params); `refusals` gives a method the error to answer it with.
    `greeting` False leaves the hello unanswered, and `answering` False
    each request after it; `trickling`, a number of seconds, sends each
    request's answer a byte at a time, that far apart."""

    def __init__(self, folder: Path, workspace_folders: list, token: str = None):
        self.token = secrets.token_hex(32)
        self.requests = []
        self.refusals = {}
        self.running = None
        self.greeting = True
        self.answering = True
        self.trickling = 0
        self._sessions = 0
        self._closing = False
        self._listener = socket.create_server(("127.0.0.1", 0))
        self.port = self._listener.getsockname()[1]
        self._ready = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()
        self._ready.wait(5)
        self.file = folder / ("%s.json" % secrets.token_hex(8))
        self.file.write_text(json.dumps({
            "host": "127.0.0.1", "port": self.port, "token": token or self.token,
            "workspaceFolders": [str(entry) for entry in workspace_folders],
            "pid": os.getpid()}), encoding="utf-8")

    def close(self):
        """Stops listening; a conversation in progress goes on until its
        client goes. Its file stays, as a window that crashed leaves it."""
        self._closing = True
        # Wakes the listener waiting for a client, which then stops. Closing
        # its socket from this thread instead would not wake it on Linux,
        # where it would go on taking clients.
        try:
            with socket.create_connection(("127.0.0.1", self.port), 5):
                pass
        except OSError:
            pass

    def _serve(self):
        self._ready.set()
        with self._listener:
            while True:
                connection, _ = self._listener.accept()
                if self._closing:
                    connection.close()
                    return
                threading.Thread(target=self._converse, args=(connection,),
                                 daemon=True).start()

    def _converse(self, connection):
        """Answers the lines `connection` brings until the client goes, or
        until a first line that is no hello with the token."""
        with connection:
            unread, greeted = b"", False
            while True:
                try:
                    data = connection.recv(65536)
                except OSError:
                    return
                if not data:
                    return
                unread += data
                while b"\n" in unread:
                    line, unread = unread.split(b"\n", 1)
                    request = json.loads(line)
                    if not greeted:
                        if request["method"] != "hello" or \
                                request["params"].get("token") != self.token:
                            return
                        greeted = True
                        if self.greeting:
                            self._write(connection, {"id": request["id"],
                                                     "result": {"version": 1}}, 0)
                        continue
                    self.requests.append((request["method"], request["params"]))
                    if not self.answering:
                        continue
                    try:
                        body = {"result": self._answer(request["method"], request["params"])}
                    except LookupError as error:
                        body = {"error": {"message": error.args[0]}}
                    self._write(connection, dict({"id": request["id"]}, **body),
                                self.trickling)

    def _write(self, connection, answer: dict, trickling: float):
        """Sends `answer`, a byte every `trickling` seconds when that is not
        0. A client that gave up on it, and went, ends the sending."""
        data = json.dumps(answer).encode() + b"\n"
        try:
            if not trickling:
                connection.sendall(data)
                return
            for index in range(len(data)):
                connection.sendall(data[index:index + 1])
                time.sleep(trickling)
        except OSError:
            pass

    def _answer(self, method: str, params: dict) -> dict:
        if method in self.refusals:
            raise LookupError(self.refusals[method])
        if method == "simulations":
            return {"simulations": [self.running] if self.running else []}
        if method == "start":
            if self.running:
                raise LookupError("a simulation of %s runs in this window: drive it, or stop "
                                  "it first" % self.running["sourceFolder"])
            self._sessions += 1
            self.running = {"session": "session-%d" % self._sessions,
                            "sourceFolder": params["sourceFolder"],
                            "page": params.get("page") or "page0"}
            return {"session": self.running["session"], "page": self.running["page"]}
        if not self.running or params.get("session") != self.running["session"]:
            raise LookupError("no simulation runs in this window as %s"
                              % json.dumps(params.get("session")))
        if method == "stop":
            self.running = None
            return {}
        if method == "screen":
            shown = {"text": "page page0 (800 x 480), background colour #ffffff",
                     "page": "page0"}
            if params.get("picture", True):
                shown["png"] = base64.b64encode(PNG).decode("ascii")
            return shown
        if method == "components":
            return {"components": COMPONENTS}
        if method == "values":
            values = {"t0.txt": "Home", "sys0": 3}
            names = params.get("names")
            return {"values": values if names is None else {name: values[name]
                                                            for name in names}}
        if method == "log":
            lines = [{"number": 1, "time": 0, "line": "receives page 0"},
                     {"number": 2, "time": 40, "line": "sends 66 00"}]
            return {"lines": [line for line in lines if line["number"] > params.get("after", 0)]}
        return {}


class ChannelFolderTest(unittest.TestCase):
    """Where the channels' files lie, as the extension puts them
    (agentChannel.ts, channelFolder)."""

    def test_in_the_users_own_application_data(self):
        self.assertEqual(channel_folder("win32", {"LOCALAPPDATA": r"C:\Users\me\AppData\Local"},
                                        Path("/unused")),
                         Path(r"C:\Users\me\AppData\Local") / "nxwright" / "agent-channels")
        self.assertIsNone(channel_folder("win32", {}, Path("/unused")))
        self.assertEqual(channel_folder("darwin", {}, Path("/Users/me")),
                         Path("/Users/me/Library/Application Support/nxwright/agent-channels"))
        self.assertEqual(channel_folder("linux", {"XDG_DATA_HOME": "/data"}, Path("/home/me")),
                         Path("/data/nxwright/agent-channels"))
        self.assertEqual(channel_folder("linux", {}, Path("/home/me")),
                         Path("/home/me/.local/share/nxwright/agent-channels"))


class WindowsFilesTest(unittest.TestCase):
    """Which of the channels' files the client takes as windows
    (vscode.windows)."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)

    def write(self, name: str, **said):
        file = dict({"host": "127.0.0.1", "port": 50000, "token": "0" * 64,
                     "workspaceFolders": [str(APP)], "pid": 1}, **said)
        (self.folder / name).write_text(json.dumps(file), encoding="utf-8")

    def test_a_window_on_this_computers_own_address(self):
        self.write("a.json")
        self.assertEqual([(window.host, window.port) for window in vscode.windows(self.folder)],
                         [("127.0.0.1", 50000)])

    def test_a_file_naming_another_host_is_left_out(self):
        # The token goes nowhere but this computer, even if someone changed the file.
        self.write("a.json", host="192.0.2.1")
        self.write("b.json", host="localhost")
        self.assertEqual(vscode.windows(self.folder), [])

    def test_a_port_no_socket_can_have_is_left_out(self):
        # Python would connect to 70000 as to port 4464, and int() would take
        # 5000.7, "5000", and true as a port the file did not quite give.
        for port in (70000, 0, -1, 5000.7, "5000", True):
            with self.subTest(port=port):
                self.write("a.json", port=port)
                self.assertEqual(vscode.windows(self.folder), [])


class VsCodeTestCase(unittest.TestCase):
    """A server whose channels' folder is a folder of the test's, and the
    workspace, a folder containing the app's source folder."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "data"
        if sys.platform == "win32":
            settings = {"LOCALAPPDATA": str(data)}
        elif sys.platform == "darwin":
            settings = {"HOME": str(data)}
        else:
            settings = {"XDG_DATA_HOME": str(data)}
        patched = mock.patch.dict(os.environ, settings)
        patched.start()
        self.addCleanup(patched.stop)
        self.folder = channel_folder()
        self.folder.mkdir(parents=True)
        self.workspace = APP.parent
        self.pictures = root / "pictures"
        self.pictures.mkdir()
        self.agent = _Agent(mcp_server(self.pictures))

    def window(self, *workspace_folders, token: str = None) -> StandInChannel:
        channel = StandInChannel(self.folder, list(workspace_folders) or [self.workspace],
                                 token)
        self.addCleanup(channel.close)
        return channel


class VsCodeSimulationTest(VsCodeTestCase):

    def setUp(self):
        super().setUp()
        self.channel = self.window()
        self.started = self.agent.data("start_simulation", source_folder=str(APP),
                                       in_vscode=True)
        self.simulation = self.started["simulation"]

    def sent(self) -> list:
        """The requests the window was sent since this was last asked."""
        sent, self.channel.requests[:] = list(self.channel.requests), []
        return sent

    def test_a_start_in_the_window_containing_the_source_folder(self):
        self.assertEqual(self.started, {"simulation": "vscode-1", "page": "page0"})
        self.assertEqual(self.sent(), [("start", {"sourceFolder": str(APP.resolve())})])

    def test_the_actions_go_to_the_windows_simulation(self):
        self.sent()
        self.agent.text("tap", simulation=self.simulation, component="b0")
        self.agent.text("send", simulation=self.simulation, instruction="page 1")
        self.agent.text("set_input", simulation=self.simulation, pin=2, level=1)
        self.agent.text("start_again", simulation=self.simulation)
        session = {"session": "session-1"}
        self.assertEqual(self.sent(), [
            ("components", session),
            ("press", dict(session, x=70, y=425)), ("release", session),
            # A send answers with what the screen sent since, from the log.
            ("serial", dict(session, text="page 1")), ("log", dict(session, after=0)),
            ("gpioInput", dict(session, pin=2, level=1)),
            ("startAgain", session)])

    def test_a_wait_lets_time_pass_on_the_clock_alone(self):
        # The app runs on its own in VS Code: nothing is sent.
        self.sent()
        self.assertEqual(self.agent.text("wait", simulation=self.simulation, milliseconds=20),
                         "Waited 20 ms.")
        self.assertEqual(self.sent(), [])

    def test_the_looks(self):
        text = self.agent.text("screen", simulation=self.simulation)
        said, _, path = text.rpartition("\npicture: ")
        self.assertEqual(said, "page page0 (800 x 480), background colour #ffffff")
        self.assertEqual(Path(path).read_bytes(), PNG)
        self.assertEqual(self.agent.text("screen", simulation=self.simulation, picture=False),
                         said)
        self.assertEqual(self.agent.data("components", simulation=self.simulation), COMPONENTS)
        self.assertEqual(self.agent.data("values", simulation=self.simulation,
                                         names=["t0.txt"]), {"t0.txt": "Home"})
        self.assertEqual([line["number"] for line in self.agent.data(
            "log", simulation=self.simulation, after=1)], [2])

    def test_the_windows_refusals_reach_the_agent_as_they_are(self):
        self.channel.refusals["press"] = ("VS Code waits for the user's answer, whether an agent "
                                          "may act on this simulation; try again once the user "
                                          "has answered")
        self.assertEqual(self.agent.refusal("press", simulation=self.simulation, x=1, y=1),
                         self.channel.refusals["press"])

    def test_one_simulation_listed_by_the_window_and_stopped(self):
        self.sent()
        listed = self.agent.data("list_simulations")
        self.assertEqual(listed, [{"simulation": "vscode-1", "source_folder": str(APP.resolve()),
                                   "where": "vscode", "page": "page0"}])
        # One request a window, which gives the page too: no window closing
        # between two requests can fail the list.
        self.assertEqual(self.sent(), [("simulations", {})])
        self.assertEqual(self.agent.text("stop_simulation", simulation=self.simulation),
                         "Stopped.")
        self.assertIn(("stop", {"session": "session-1"}), self.sent())
        self.assertEqual(self.agent.data("list_simulations"), [])
        self.assertIn("no simulation vscode-1 runs",
                      self.agent.refusal("screen", simulation=self.simulation))


class UsersOwnSimulationTest(VsCodeTestCase):

    def test_a_simulation_the_user_started_listed_beside_the_headless_ones(self):
        channel = self.window()
        channel.running = {"session": "user", "sourceFolder": str(APP), "page": "page0"}
        headless = self.agent.data("start_simulation", source_folder=str(APP))["simulation"]
        listed = self.agent.data("list_simulations")
        self.assertEqual([(entry["simulation"], entry["where"]) for entry in listed],
                         [(headless, "headless"), ("vscode-1", "vscode")])
        # The agent drives it by the id listed, as long as it runs.
        self.agent.text("tap", simulation="vscode-1", x=5, y=5)
        self.assertIn(("press", {"session": "user", "x": 5, "y": 5}), channel.requests)
        self.assertEqual(self.agent.data("list_simulations")[1]["simulation"], "vscode-1")
        channel.running = None
        self.assertEqual(len(self.agent.data("list_simulations")), 1)
        self.assertIn("no simulation vscode-1 runs",
                      self.agent.refusal("tap", simulation="vscode-1", x=5, y=5))


class FindingTheWindowTest(VsCodeTestCase):
    """Which window a start in VS Code goes to: among those whose channel
    answers, the one whose workspace folder containing the source folder
    lies deepest."""

    def start(self) -> dict:
        return self.agent.call("start_simulation", source_folder=str(APP), in_vscode=True)

    def test_none_contains_the_source_folder(self):
        self.window(APP.parent.parent / "elsewhere")
        refusal = self.agent.refusal("start_simulation", source_folder=str(APP),
                                     in_vscode=True)
        self.assertIn("open the folder in VS Code", refusal)
        self.assertIn("nxwright.agents.allowControl", refusal)

    def test_the_window_whose_workspace_folder_lies_deepest(self):
        outer = self.window(APP.parent.parent)
        inner = self.window(APP)
        self.assertFalse(self.start()["isError"])
        self.assertEqual([method for method, _ in inner.requests], ["start"])
        self.assertEqual(outer.requests, [])

    def test_two_windows_alike_are_named(self):
        self.window(APP)
        self.window(APP)
        refusal = self.agent.refusal("start_simulation", source_folder=str(APP),
                                     in_vscode=True)
        self.assertIn("several VS Code windows", refusal)
        self.assertIn(str(APP), refusal)

    def test_a_window_whose_channel_does_not_answer_is_left_out(self):
        # A window that crashed left its file: nothing listens there.
        gone = self.window(APP)
        gone.close()
        living = self.window(APP.parent)
        self.assertFalse(self.start()["isError"])
        self.assertEqual([method for method, _ in living.requests], ["start"])

    def test_a_window_refusing_the_token_is_left_out(self):
        self.window(APP, token="0" * 64)
        self.assertIn("open the folder in VS Code",
                      self.agent.refusal("start_simulation", source_folder=str(APP),
                                         in_vscode=True))


class TimeLimitsTest(VsCodeTestCase):
    """The client gives up on a window that does not answer in time, as
    one whose extension host hangs, and the server answers other tools
    again. A limit is cut short only around the call a test is about, so
    that the test waits a fraction of a second, and the stand-in that
    answers is not held to it on a busy machine."""

    def limited(self, name: str, seconds: float):
        """Cuts the limit `name` of vscode.py to `seconds`, for the calls
        made inside the with block: each call reads it as it connects."""
        return mock.patch.object(vscode, name, seconds)

    def start(self) -> dict:
        return self.agent.call("start_simulation", source_folder=str(APP), in_vscode=True)

    def test_a_request_never_answered(self):
        channel = self.window()
        simulation = self.agent.data("start_simulation", source_folder=str(APP),
                                     in_vscode=True)["simulation"]
        channel.answering = False
        with self.limited("ANSWER_LIMIT", 0.3):
            refusal = self.agent.refusal("screen", simulation=simulation)
        self.assertIn("did not answer within 0.3 s", refusal)
        self.assertIn("what was asked may still be done", refusal)
        self.assertNotIn("asking the user", refusal)
        # The server answers other tools again.
        self.assertFalse(self.agent.call("start_simulation", source_folder=str(APP))["isError"])

    def test_a_start_never_answered_may_wait_for_the_user(self):
        self.window().answering = False
        with self.limited("ANSWER_LIMIT", 0.3):
            refusal = self.agent.refusal("start_simulation", source_folder=str(APP),
                                         in_vscode=True)
        self.assertIn("did not answer within 0.3 s", refusal)
        self.assertIn("VS Code may be asking the user first, such as whether to trust the "
                      "folder", refusal)
        self.assertIn("list_simulations lists it", refusal)

    def test_a_window_whose_hello_never_comes_is_left_out(self):
        # A window that crashed left its file, and another program now
        # listens on its port, taking connections but not answering. One
        # start reaches both windows, so the living one is held to the
        # short limit too: 2 s, which a busy machine meets.
        self.window(APP).greeting = False
        living = self.window(APP.parent)
        began = time.monotonic()
        with self.limited("HELLO_LIMIT", 2):
            self.assertFalse(self.start()["isError"])
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual([method for method, _ in living.requests], ["start"])

    def test_an_answer_sent_a_byte_at_a_time_is_cut_off(self):
        channel = self.window()
        simulation = self.agent.data("start_simulation", source_folder=str(APP),
                                     in_vscode=True)["simulation"]
        # Each read comes in time, but the whole answer would take seconds.
        channel.trickling = 0.05
        began = time.monotonic()
        with self.limited("ANSWER_LIMIT", 0.3):
            refusal = self.agent.refusal("components", simulation=simulation)
        self.assertIn("did not answer within 0.3 s", refusal)
        self.assertLess(time.monotonic() - began, 2)

    def test_a_file_of_an_older_extension_is_said(self):
        (self.folder / "older.json").write_text(json.dumps({
            "address": r"\\.\pipe\nxwright-agent-older", "token": "0" * 64,
            "workspaceFolders": [str(APP)], "pid": 1}), encoding="utf-8")
        refusal = self.agent.refusal("start_simulation", source_folder=str(APP),
                                     in_vscode=True)
        self.assertIn("open the folder in VS Code", refusal)
        self.assertIn("a file of an older nxwright extension", refusal)
        self.assertIn("A file a window that crashed left looks the same", refusal)
