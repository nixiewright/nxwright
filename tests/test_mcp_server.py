"""The MCP server, `nxwright mcp` (mcp_server/), driven as an agent drives
it: MCP's messages on its standard input and output, one JSON object a line.
The app is fixtures/mcp/app: on page0, a text t0 "Home", a number n0 that
the timer tm0 steps every 100 ms, and a button b0 whose release opens the
page "second", whose text t0 is "Second"."""
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.mcp_server.server import GUIDE_FILE, about_text, docs_folder, mcp_server

APP = Path(__file__).resolve().parent / "fixtures" / "mcp" / "app"
DOCS = Path(__file__).resolve().parents[1] / "docs"
RUN = Path(__file__).resolve().parent.parent / "run.py"
INITIALIZE = {"jsonrpc": "2.0", "id": 0, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "test", "version": "1"}}}


class _Agent:
    """Talks to `server` as an agent does, one request at a time."""

    def __init__(self, server):
        self.server = server
        self.sent = 0
        self.request(INITIALIZE)
        self.request({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def request(self, message: dict):
        """Sends `message`, and returns the server's answer, or None for a
        notification."""
        stdout = io.BytesIO()
        self.server.stdio(io.BytesIO(json.dumps(message).encode() + b"\n"), stdout)
        answer = stdout.getvalue()
        return json.loads(answer) if answer else None

    def call(self, tool: str, **arguments) -> dict:
        """Calls `tool`, and returns the call's result: its content and isError."""
        self.sent += 1
        answer = self.request({"jsonrpc": "2.0", "id": self.sent, "method": "tools/call",
                               "params": {"name": tool, "arguments": arguments}})
        return answer["result"]

    def text(self, tool: str, **arguments) -> str:
        """Calls `tool`, which must succeed, and returns its text."""
        result = self.call(tool, **arguments)
        if result["isError"]:
            raise AssertionError(result["content"][0]["text"])
        return result["content"][0]["text"]

    def data(self, tool: str, **arguments):
        """Calls `tool`, which must succeed, and returns its JSON answer."""
        return json.loads(self.text(tool, **arguments))

    def refusal(self, tool: str, **arguments) -> str:
        """Calls `tool`, which must refuse, and returns the error's text."""
        result = self.call(tool, **arguments)
        if not result["isError"]:
            raise AssertionError("%s was not refused: %s" % (tool, result["content"][0]["text"]))
        return result["content"][0]["text"]


class McpServerTest(unittest.TestCase):

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.pictures = Path(folder.name)
        self.agent = _Agent(mcp_server(self.pictures))
        started = self.agent.data("start_simulation", source_folder=str(APP))
        self.simulation = started["simulation"]
        self.assertEqual(started, {"simulation": "headless-1", "page": "page0"})

    def page_shown(self) -> str:
        return self.agent.data("components", simulation=self.simulation)[0]["name"]

    def test_the_tools(self):
        listed = self.agent.request({"jsonrpc": "2.0", "id": 100, "method": "tools/list"})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
        self.assertEqual(sorted(tools), [
            "about", "components", "list_simulations", "log", "move", "press", "release",
            "screen", "send", "set_input", "set_inputs", "start_again", "start_simulation",
            "stop_simulation",
            "tap", "values", "wait"])
        # A tap goes to a component or to a point: neither is required.
        self.assertEqual(tools["tap"]["inputSchema"]["required"], ["simulation"])

    def test_about_leads_the_tools_and_gives_the_guide(self):
        listed = self.agent.request({"jsonrpc": "2.0", "id": 100, "method": "tools/list"})
        names = [tool["name"] for tool in listed["result"]["tools"]]
        # First in the server's order, and first by name.
        self.assertEqual(names[0], "about")
        self.assertEqual(min(names), "about")
        # The guide, then the docs' topics, each with its doc's title.
        about = self.agent.text("about")
        self.assertTrue(about.startswith(GUIDE_FILE.read_text(encoding="utf-8")))
        self.assertIn("- `testing`: Testing your app\n", about)
        self.assertNotIn("STYLE", about)
        # What an agent reads as it connects sends it there first.
        connected = self.agent.request(INITIALIZE)
        self.assertIn("call about", connected["result"]["instructions"])

    def test_a_topic_gives_its_doc_whole(self):
        # By its file's name, with or without ".md", as the docs' links write it.
        doc = (DOCS / "testing.md").read_text(encoding="utf-8")
        self.assertEqual(self.agent.text("about", topic="testing"), doc)
        self.assertEqual(self.agent.text("about", topic="testing.md"), doc)

    def test_an_unknown_topic_is_refused_naming_the_topics(self):
        # A topic is a name of the list, never a path.
        for topic in ("speed", "../README", "STYLE"):
            with self.subTest(topic=topic):
                refusal = self.agent.refusal("about", topic=topic)
                self.assertIn("no topic %s" % topic, refusal)
                self.assertIn("testing", refusal)

    def test_the_screen_as_text_and_as_a_picture(self):
        text = self.agent.text("screen", simulation=self.simulation, picture=False)
        self.assertIn('"Home"', text)
        self.assertNotIn("picture:", text)
        lines = self.agent.text("screen", simulation=self.simulation).split("\n")
        self.assertTrue(lines[-1].startswith("picture: "), lines[-1])
        picture = Path(lines[-1][len("picture: "):])
        self.assertEqual(picture.parent, self.pictures)
        self.assertEqual(picture.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        # Each picture is a file of its own.
        again = self.agent.text("screen", simulation=self.simulation).split("\n")[-1]
        self.assertNotEqual(again, lines[-1])
        self.assertTrue(picture.exists())

    def test_a_tap_on_a_component_by_name(self):
        self.assertEqual(self.agent.text("tap", simulation=self.simulation, component="b0"),
                         "Tapped.")
        self.assertEqual(self.page_shown(), "second")
        self.assertIn('"Second"', self.agent.text("screen", simulation=self.simulation,
                                                  picture=False))

    def test_a_press_at_a_point_held_then_released(self):
        self.agent.text("press", simulation=self.simulation, x=50, y=420)
        self.assertEqual(self.page_shown(), "page0")
        self.agent.text("move", simulation=self.simulation, x=60, y=430)
        self.agent.text("release", simulation=self.simulation)
        self.assertEqual(self.page_shown(), "second")

    def test_a_wait_runs_the_timers(self):
        self.assertEqual(self.agent.text("wait", simulation=self.simulation, milliseconds=350),
                         "Waited 350 ms.")
        self.assertEqual(self.agent.data("values", simulation=self.simulation,
                                         names=["n0.val"]), {"n0.val": 3})

    def test_an_instruction_from_the_serial_line(self):
        self.agent.text("send", simulation=self.simulation, instruction='t0.txt="Hi"')
        self.assertEqual(self.agent.data("values", simulation=self.simulation,
                                         names=["t0.txt"]), {"t0.txt": "Hi"})
        # A component's name alone gives each of its attributes.
        attributes = self.agent.data("values", simulation=self.simulation, names=["t0"])
        self.assertEqual(attributes["t0.txt"], "Hi")
        self.assertTrue(all(name.startswith("t0.") for name in attributes))

    def test_the_log_from_a_line(self):
        # program.nx's printh sends the first line.
        first = self.agent.data("log", simulation=self.simulation)
        self.agent.text("send", simulation=self.simulation, instruction='prints "ok",0')
        later = self.agent.data("log", simulation=self.simulation, after=len(first))
        self.assertEqual([(entry["number"], entry["line"]) for entry in later],
                         [(len(first) + 1, 'receives prints "ok",0'),
                          (len(first) + 2, "sends 6f 6b")])

    def test_every_value_reads_as_json(self):
        everything = self.agent.data("values", simulation=self.simulation)
        self.assertEqual((everything["t0.txt"], everything["sys0"]), ("Home", 0))

    def test_several_gpio_inputs_in_one_step(self):
        self.assertEqual(self.agent.text("set_inputs", simulation=self.simulation,
                                         levels={"pio2": 0, "pio5": 0}), "Set.")
        self.assertEqual(self.agent.data("values", simulation=self.simulation,
                                         names=["pio2", "pio5", "pio6"]),
                         {"pio2": 0, "pio5": 0, "pio6": 1})

    def test_a_start_again(self):
        self.agent.text("tap", simulation=self.simulation, component="b0")
        self.agent.text("start_again", simulation=self.simulation)
        self.assertEqual(self.page_shown(), "page0")

    def test_a_start_on_a_page(self):
        started = self.agent.data("start_simulation", source_folder=str(APP), page="second")
        self.assertEqual(started, {"simulation": "headless-2", "page": "second"})
        self.assertEqual([entry["simulation"] for entry in
                          self.agent.data("list_simulations")], ["headless-1", "headless-2"])

    def test_a_stopped_simulation_is_gone(self):
        self.assertEqual(self.agent.text("stop_simulation", simulation=self.simulation),
                         "Stopped.")
        self.assertEqual(self.agent.data("list_simulations"), [])
        self.assertIn("no simulation headless-1 runs",
                      self.agent.refusal("tap", simulation=self.simulation, component="b0"))

    def refused(self, tool: str, **arguments) -> str:
        return self.agent.refusal(tool, simulation=self.simulation, **arguments)

    def test_refusals(self):
        self.assertEqual(self.refused("tap"), "give a component's name, or x and y")
        self.assertEqual(self.refused("tap", component="b0", x=1, y=1),
                         "give a component's name, or x and y, not both")
        self.assertEqual(self.refused("tap", component="b9"),
                         "the page shown has no component named b9")
        self.assertEqual(self.refused("tap", component="tm0"),
                         "tm0 has no place on the screen, so it cannot be pressed")
        self.assertEqual(self.refused("wait", milliseconds=-1),
                         "a wait lasts 0 milliseconds or more")
        # At most a minute at a time, so that the server answers again soon.
        self.assertEqual(self.refused("wait", milliseconds=60001),
                         "a wait lasts at most 60000 milliseconds: wait again for longer")
        self.assertEqual(self.agent.text("wait", simulation=self.simulation,
                                         milliseconds=60000), "Waited 60000 ms.")
        self.assertIn("pin", self.refused("set_input", pin=9, level=0))
        self.assertIn("pio0 to pio7", self.refused("set_inputs", levels={"pi02": 0}))
        self.assertIn("t9.txt", self.refused("values", names=["t9.txt"]))
        self.assertTrue(self.agent.refusal("start_simulation",
                                           source_folder=str(APP.parent / "missing")))

    def test_one_touch_at_a_time(self):
        # A screen takes one touch at a time: a second press while one is
        # held is refused, and so is a move with none held. A release with
        # none held does nothing, so it is taken.
        self.agent.text("press", simulation=self.simulation, component="t0")
        self.assertEqual(self.refused("press", component="b0"),
                         "the screen is pressed already, and takes one touch at a time: "
                         "release it first")
        self.assertEqual(self.refused("tap", component="b0"),
                         "the screen is pressed already, and takes one touch at a time: "
                         "release it first")
        self.agent.text("release", simulation=self.simulation)
        self.assertEqual(self.page_shown(), "page0")
        self.assertEqual(self.refused("move", x=10, y=10),
                         "the screen is not pressed: press it first")
        self.assertEqual(self.agent.text("release", simulation=self.simulation), "Released.")
        # Starting again lets a press held go.
        self.agent.text("press", simulation=self.simulation, component="t0")
        self.agent.text("start_again", simulation=self.simulation)
        self.agent.text("tap", simulation=self.simulation, component="b0")
        self.assertEqual(self.page_shown(), "second")

    def test_a_tap_whose_press_starts_the_app_again(self):
        # `rest` starts the app again, which forgets the press. The tap's
        # release is still taken, as a release with none held does nothing.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Path(folder.name) / "app"
        shutil.copytree(APP, app)
        (app / "pages" / "page0.nx").write_text("on b0.down:\n  rest\n", encoding="utf-8")
        resting = self.agent.data("start_simulation", source_folder=str(app))["simulation"]
        self.assertEqual(self.agent.text("tap", simulation=resting, component="b0"), "Tapped.")

    def test_a_point_off_the_page(self):
        for x, y in ((800, 10), (10, 480), (-1, 10), (10, -1)):
            with self.subTest(x=x, y=y):
                self.assertEqual(self.refused("tap", x=x, y=y),
                                 "%d,%d lies off the page, which is 800 x 480" % (x, y))
        self.agent.text("press", simulation=self.simulation, x=799, y=479)
        self.assertEqual(self.refused("move", x=900, y=10),
                         "900,10 lies off the page, which is 800 x 480")
        self.agent.text("release", simulation=self.simulation)

    def test_a_hidden_component_by_name(self):
        self.agent.text("send", simulation=self.simulation, instruction="vis b0,0")
        self.assertEqual(self.refused("tap", component="b0"),
                         "b0 does not show, so it cannot be pressed")

    def test_what_the_log_has_since(self):
        # A send answers with the log's lines since the agent's last send or
        # log, or since the start: here, program.nx's printh, the instruction
        # received, then its refusal.
        self.assertEqual(self.agent.text("send", simulation=self.simulation,
                                         instruction="page 9"),
                         "Sent. The log since the simulation started:\n"
                         "sends 00 00 00 ff ff ff 88 ff ff ff\n"
                         "receives page 9\n"
                         "sends 03 ff ff ff")
        self.assertEqual(self.agent.text("send", simulation=self.simulation,
                                         instruction="get t0.txt"),
                         "Sent. The log since your last send or log:\n"
                         "receives get t0.txt\n"
                         "sends 70 48 6f 6d 65 ff ff ff (get)")
        # Why an instruction did not run is given too.
        self.agent.text("send", simulation=self.simulation, instruction="com_stop")
        self.assertEqual(self.agent.text("send", simulation=self.simulation,
                                         instruction='t0.txt="Hi"'),
                         "Sent. The log since your last send or log:\n"
                         'receives t0.txt="Hi"\n'
                         "held: the serial line is stopped")
        # Lines the agent read with log are not given again.
        self.agent.text("send", simulation=self.simulation, instruction="com_star")
        self.agent.text("tap", simulation=self.simulation, component="t0")
        self.agent.data("log", simulation=self.simulation)
        self.assertEqual(self.agent.text("send", simulation=self.simulation,
                                         instruction="sendme"),
                         "Sent. The log since your last send or log:\n"
                         "receives sendme\n"
                         "sends 66 00 ff ff ff (sendme)")

    def test_what_the_log_has_since_at_most_ten_lines(self):
        # A copy of the app whose button sends a byte 12 times as it is released.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Path(folder.name) / "app"
        shutil.copytree(APP, app)
        (app / "pages" / "page0.nx").write_text("on b0.up:\n" + "  printh 01\n" * 12,
                                                encoding="utf-8")
        printing = self.agent.data("start_simulation", source_folder=str(app))["simulation"]
        # The log's first line is program.nx's printh.
        self.assertEqual(len(self.agent.data("log", simulation=printing)), 1)
        # The last ten lines, which end with the answer to the instruction
        # sent; before them, the instruction received and two of the bytes.
        self.assertEqual(self.agent.text("send", simulation=printing, instruction="click b0,0"),
                         "\n".join(["Sent. The log since your last send or log:",
                                    "... 3 lines before these: call log with after 1"]
                                   + ["sends 01"] * 10))

    def test_a_start_again_that_does_not_build(self):
        # The agent's edit has a mistake: the start again is refused, and
        # the app runs on as it was, for every tool.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Path(folder.name) / "app"
        shutil.copytree(APP, app)
        edited = self.agent.data("start_simulation", source_folder=str(app))["simulation"]
        (app / "pages" / "page0.nx").write_text("on b0.up:\n  n0.val=n0.val+\n",
                                                encoding="utf-8")
        self.assertIn("pages/page0.nx line 2: n0.val=n0.val+",
                      self.agent.refusal("start_again", simulation=edited))
        self.assertEqual([entry["page"] for entry in self.agent.data("list_simulations")],
                         ["page0", "page0"])
        self.assertIn('"Home"', self.agent.text("screen", simulation=edited, picture=False))
        self.agent.text("tap", simulation=edited, component="b0")
        self.assertEqual(self.agent.data("components", simulation=edited)[0]["name"], "second")

    def test_an_error_in_the_apps_code(self):
        # A copy of the app whose button divides by sys0, which is 0.
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        app = Path(folder.name) / "app"
        shutil.copytree(APP, app)
        (app / "pages" / "page0.nx").write_text("on b0.up:\n  n0.val=1/sys0\n", encoding="utf-8")
        failing = self.agent.data("start_simulation", source_folder=str(app))["simulation"]
        self.assertEqual(self.agent.refusal("tap", simulation=failing, component="b0"),
                         "the app's code stopped with an error: ZeroDivisionError")
        # The simulation goes on, as the error left it.
        self.assertEqual(self.agent.data("components", simulation=failing)[0]["name"], "page0")


class McpCommandTest(unittest.TestCase):

    def test_nxwright_mcp_answers_on_its_standard_input(self):
        done = subprocess.run([sys.executable, str(RUN), "mcp"],
                              input=json.dumps(INITIALIZE).encode() + b"\n",
                              capture_output=True, timeout=60, check=True)
        answer = json.loads(done.stdout.decode().splitlines()[0])
        self.assertEqual(answer["result"]["serverInfo"]["name"], "nxwright")

    def test_the_package_ships_the_guide(self):
        project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml")
                                .read_text(encoding="utf-8"))
        shipped = project["tool"]["setuptools"]["package-data"]["nxwright.mcp_server"]
        self.assertIn(GUIDE_FILE.name, shipped)

    def test_the_package_ships_the_docs(self):
        # setuptools ships a folder outside the package, docs/, only for a
        # package listed by name: so every package is listed, and one left
        # out would not ship.
        root = Path(__file__).resolve().parents[1]
        setuptools = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))[
            "tool"]["setuptools"]
        packages = sorted(".".join(folder.relative_to(root).parts)
                          for folder in (root / "nxwright").rglob("*")
                          if (folder / "__init__.py").is_file()) + ["nxwright"]
        self.assertEqual(sorted(setuptools["packages"]), sorted(packages + ["nxwright.docs"]))
        self.assertEqual(setuptools["package-dir"]["nxwright.docs"], "docs")
        self.assertEqual(setuptools["package-data"]["nxwright.docs"], ["*.md"])
        self.assertEqual(setuptools["exclude-package-data"]["nxwright.docs"], ["STYLE.md"])


class DocsFolderTest(unittest.TestCase):
    """Where `about` finds nxwright's docs: in the package, as an install
    holds them, or beside it, in a source tree."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.package = self.root / "nxwright"
        self.package.mkdir()

    def write_doc(self, folder: Path):
        folder.mkdir()
        (folder / "testing.md").write_text("# Testing your app\n\nRun them.\n", encoding="utf-8")

    def test_in_an_installed_package(self):
        self.write_doc(self.package / "docs")
        self.assertEqual(docs_folder(self.package), self.package / "docs")

    def test_beside_the_package_in_a_source_tree(self):
        (self.root / "pyproject.toml").write_text("", encoding="utf-8")
        self.write_doc(self.root / "docs")
        self.assertEqual(docs_folder(self.package), self.root / "docs")

    def test_not_beside_an_installed_package(self):
        # Another project's docs folder, as one left in site-packages, is
        # not nxwright's: only a source tree's is.
        self.write_doc(self.root / "docs")
        self.assertIsNone(docs_folder(self.package))

    def test_with_no_docs_the_guide_says_so(self):
        self.assertTrue(about_text(None, None).startswith(GUIDE_FILE.read_text(encoding="utf-8")))
        self.assertIn("nxwright's docs are not installed", about_text(None, None))
        with self.assertRaisesRegex(NxwrightError, "nxwright's docs are not installed"):
            about_text("testing", None)
