"""The debugger of a test and its screen code: recording a run, recording the
test's own Python, moving through the recording, the debug adapter's session,
and nxwright test's --list and --report."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.debug_adapter.adapter import DebugAdapter, run_test
from nxwright.debug_adapter.framing import read_message, write_message
from nxwright.debug_adapter.replay import Timeline, path_key
from nxwright.testing import SourceFolderRunner, ValueNotGiven
from nxwright.testing.looks import value_group
from nxwright.testing.recording import Recorder, recording
from nxwright.testing.reports import RecordingResult, results
from tests.test_folder_check import FolderTestCase

# A page whose load event calls a function, clicks a component, loops, and
# switches; and a library function the page includes.
LIBRARY = """function twice(value: number) -> number:
  var doubled = value * 2
  return doubled
"""
PAGE = """include "lib/numbers.nx"

on page0.load:
  sys0 = twice(n0.val)
  click title,1
  for (sys1 = 0; sys1 < 2; sys1++) {
    sys2 = sys2 + 1
  }
  switch (sys0) {
    case 6:
      title.txt = "six"
      break
  }

on title.down:
  sys2 = 10
"""
# A helper module beside the tests, which runs the page's load event.
HELPER = """from pathlib import Path

from nxwright.testing import SourceFolderRunner

SCREEN = SourceFolderRunner(Path(__file__).parent.parent / "app")


def load(value):
    values = {"sys2": 0, "n0.val": value, "title.txt": ""}
    return SCREEN.run("page0", [("page0", "load")], values)
"""
# Tests of that page, run by the debugger. test_unset_field does not set
# n0.val, which the page reads, so its run stops with an error;
# test_failing_check fails its assertion.
TEST = """import unittest

from helpers import SCREEN, load


class LoadTest(unittest.TestCase):

    def test_load(self):
        values = SCREEN.run("page0", [("page0", "load")],
                            {"sys2": 0, "n0.val": 3, "title.txt": ""})
        self.assertEqual(values["title.txt"], "six")

    def test_unset_field(self):
        SCREEN.run("page0", [("page0", "load")])


class TwoRunsTest(unittest.TestCase):

    def test_two_runs(self):
        first = load(3)
        self.assertEqual(first["title.txt"], "six")
        second = load(4)
        self.assertEqual(second["sys0"], 8)

    def test_failing_check(self):
        values = load(3)
        self.assertEqual(values["sys0"], 7)
"""


def test_line(text: str) -> int:
    """Returns the line, from 1, of the first line of TEST holding `text`."""
    return next(number for number, line in enumerate(TEST.split("\n"), start=1) if text in line)


class ScopeTest(unittest.TestCase):
    """Which scope of the Variables view each value goes in."""

    def test_each_record_of_the_test_machine_is_outside_the_page(self):
        # The records docs/testing.md lists, and the values the machine keeps
        # per component or file stream.
        for name in ("page opened", "sent", "replies", "eeprom", "eeprom accesses", "gpio",
                     "rand range", "reset", "other commands", "painted", "waveform",
                     "existing", "file contents", "file errors", "file commands",
                     "component errors", "refusals", "vis t0", "touch t0", "open file fs0"):
            with self.subTest(name):
                self.assertEqual(value_group(name, False), "Outside the page")
        self.assertEqual([value_group(name, False) for name in ("t0.txt", "sys0")],
                         ["Page", "Program"])


class FramingTest(unittest.TestCase):
    """The framing of the debug adapter's messages (framing.py)."""

    def test_a_message_reads_back(self):
        stream = io.BytesIO()
        write_message(stream, {"jsonrpc": "2.0", "id": 1, "result": "é"})
        stream.seek(0)
        self.assertEqual(read_message(stream), {"jsonrpc": "2.0", "id": 1, "result": "é"})
        self.assertIsNone(read_message(stream))

    def test_the_length_counts_bytes(self):
        stream = io.BytesIO()
        write_message(stream, {"text": "é"})
        self.assertIn(b"Content-Length: 13\r\n\r\n", stream.getvalue())

    def test_other_header_lines_are_ignored(self):
        body = b'{"id":1}'
        stream = io.BytesIO(b"Content-Type: application/vscode-jsonrpc\r\n"
                            b"Content-Length: %d\r\n\r\n%s" % (len(body), body))
        self.assertEqual(read_message(stream), {"id": 1})

    def test_a_header_without_a_length(self):
        with self.assertRaisesRegex(NxwrightError, "no Content-Length"):
            read_message(io.BytesIO(b"Content-Type: x\r\n\r\n{}"))

    def test_a_message_cut_short(self):
        with self.assertRaisesRegex(NxwrightError, "ended inside a message"):
            read_message(io.BytesIO(b"Content-Length: 10\r\n\r\n{}"))


class DebuggerTestCase(FolderTestCase):
    """FolderTestCase's folder with PAGE and LIBRARY, and a folder of tests,
    "tests", holding TEST and HELPER beside it."""

    def setUp(self):
        super().setUp()
        self.write("pages/lib/numbers.nx", LIBRARY)
        self.write("pages/page0.nx", PAGE)
        # n0, a number, whose val the page reads.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "n0"\ntype = "number"\nx = 0\ny = 40\nw = 100\n'
                     'h = 30\n')
        self.tests = self.root.parent / "tests"
        self.tests.mkdir()
        (self.tests / "test_page.py").write_text(TEST, encoding="utf-8")
        (self.tests / "helpers.py").write_text(HELPER, encoding="utf-8")
        # Running the folder's tests imports its modules from it, by name.
        for module in ("test_page", "helpers"):
            self.addCleanup(sys.modules.pop, module, None)
        self.addCleanup(lambda: str(self.tests) in sys.path and sys.path.remove(str(self.tests)))

    def record(self, values: dict = None) -> Recorder:
        """Records a run of the page's load event, with no Python traced."""
        values = values or {"sys2": 0, "n0.val": 3, "title.txt": ""}
        with recording(Recorder()) as recorder:
            SourceFolderRunner(self.root).run("page0", [("page0", "load")], values)
        return recorder

    def traced(self, test: str) -> tuple:
        """Records `test` as the debugger does: (Recorder, failures)."""
        recorder = Recorder()
        _, failures = run_test(self.tests, test, recorder)
        return recorder, failures

    def line_of(self, path: str, text: str) -> int:
        """Returns the line, from 1, of the first line of `path` holding `text`."""
        lines = self.text(path).split("\n")
        return next(number for number, line in enumerate(lines, start=1) if text in line)


class RecordingTest(DebuggerTestCase):

    def test_places_and_depths(self):
        recorder = self.record()
        [run] = recorder.runs
        seen = [(step.place.file, step.place.line, step.place.owner, len(step.frames))
                for step in recorder.steps]
        page, library = "pages/page0.nx", "pages/lib/numbers.nx"
        self.assertEqual(seen[0], (page, 4, "page0.load", 1))
        # The call runs the function's body one level deeper, in its own file.
        self.assertIn((library, 2, "twice", 2), seen)
        self.assertIn((library, 3, "twice", 2), seen)
        # The hand-made click runs the component's event one level deeper.
        self.assertIn((page, self.line_of(page, "sys2 = 10"), "title.down", 2), seen)
        # The loop's head comes back on each turn.
        loop = self.line_of(page, "for (")
        self.assertEqual([entry for entry in seen if entry[1] == loop and entry[2] == "page0.load"
                          and entry[0] == page], [(page, loop, "page0.load", 1)] * 3)
        self.assertIn((page, self.line_of(page, 'title.txt = "six"'), "page0.load", 1), seen)
        self.assertEqual((run.end["title.txt"], run.error), ("six", None))

    def test_local_names(self):
        [run] = self.record().runs
        names = run.local_names["twice"]
        self.assertEqual(sorted(names.values()), ["(result)", "doubled", "value"])

    def test_changes(self):
        recorder = self.record()
        changed = [name for step in recorder.steps for name in step.changes]
        self.assertIn("sys0", changed)
        self.assertEqual(recorder.runs[0].start["sys2"], 0)

    def test_an_error_ends_the_run(self):
        with self.assertRaises(ValueNotGiven), recording(Recorder()) as recorder:
            SourceFolderRunner(self.root).run("page0", [("page0", "load")], {"sys2": 0})
        self.assertIn("ValueNotGiven", recorder.runs[0].error)
        self.assertIn("n0.val has no value", recorder.runs[0].error)

    def test_a_cap_on_steps(self):
        with mock.patch("nxwright.testing.recording.MOST_STEPS", 5), \
                self.assertRaisesRegex(NxwrightError, "passed 5 steps"):
            self.record()

    def test_nothing_is_recorded_when_off(self):
        values = SourceFolderRunner(self.root).run("page0", [("page0", "load")],
                                                   {"sys2": 0, "n0.val": 3, "title.txt": ""})
        self.assertEqual(values["title.txt"], "six")


class PythonStepsTest(DebuggerTestCase):

    def test_the_tests_lines_and_its_runs_in_order(self):
        recorder, failures = self.traced("test_page.TwoRunsTest.test_two_runs")
        self.assertEqual(failures, [])
        test_file = str(self.tests / "test_page.py")
        lines = [(index, step.place.line) for index, step in enumerate(recorder.steps)
                 if step.run is None and step.place.file == test_file]
        self.assertEqual([line for _, line in lines],
                         [test_line("first = load(3)"), test_line('first["title.txt"]'),
                          test_line("second = load(4)"), test_line('second["sys0"]')])
        # The first run's steps come between the call and the first assertion,
        # under the test's frame and the helper's.
        runs = [index for index, step in enumerate(recorder.steps) if step.run == 0]
        self.assertTrue(lines[0][0] < min(runs) and max(runs) < lines[1][0])
        first = recorder.steps[runs[0]]
        self.assertEqual([place.owner for place in first.frames],
                         ["TwoRunsTest.test_two_runs", "load", "page0.load"])
        self.assertEqual(len(recorder.runs), 2)

    def test_only_the_folder_of_tests_is_traced(self):
        recorder, _ = self.traced("test_page.TwoRunsTest.test_two_runs")
        files = {Path(step.place.file).name for step in recorder.steps if step.run is None}
        self.assertEqual(files, {"test_page.py", "helpers.py"})

    def test_locals_as_text(self):
        recorder, _ = self.traced("test_page.TwoRunsTest.test_two_runs")
        place = next(step.place for step in recorder.steps if step.run is None
                     and step.place.line == test_line('first["title.txt"]'))
        local_values = {name: (text, dict(entries)) for name, text, entries in place.local_values}
        self.assertEqual(local_values["first"][1]["'title.txt'"], "'six'")
        self.assertIn("self", local_values)

    def test_a_failing_assertion_stops_at_its_line(self):
        recorder, failures = self.traced("test_page.TwoRunsTest.test_failing_check")
        [(position, message)] = failures
        self.assertEqual(recorder.steps[position].place.line, test_line('values["sys0"], 7'))
        self.assertTrue(message.startswith("AssertionError"), message)

    def test_an_unhashable_exception(self):
        # An exception class with __eq__ and no __hash__ cannot be a dict key.
        (self.tests / "test_odd.py").write_text(
            "import unittest\n\n\n"
            "class Odd(Exception):\n"
            "    def __eq__(self, other):\n"
            "        return False\n\n\n"
            "class OddTest(unittest.TestCase):\n\n"
            "    def test_odd(self):\n"
            "        raise Odd('odd')\n", encoding="utf-8")
        self.addCleanup(sys.modules.pop, "test_odd", None)
        recorder, failures = self.traced("test_odd.OddTest.test_odd")
        [(position, message)] = failures
        self.assertEqual((recorder.steps[position].place.line, message), (12, "test_odd.Odd: odd"))

    def test_an_error_inside_a_run_stops_at_its_statement(self):
        recorder, failures = self.traced("test_page.LoadTest.test_unset_field")
        [(position, message)] = failures
        step = recorder.steps[position]
        self.assertEqual((step.place.file, step.place.line), ("pages/page0.nx", 4))
        self.assertIn("n0.val has no value", message)


class ReplayTest(DebuggerTestCase):

    def setUp(self):
        super().setUp()
        self.timeline = Timeline(self.record())

    def place(self, position: int) -> tuple:
        step = self.timeline.step(position)
        return step.place.line, step.place.owner

    def test_step_over_skips_the_call(self):
        call = self.place(0)
        after = self.timeline.next_line(0)
        self.assertEqual(self.place(after), (self.line_of("pages/page0.nx", "click title"),
                                             "page0.load"))
        self.assertNotEqual(self.place(after), call)

    def test_step_into_and_out(self):
        inside = self.timeline.next_line(0, into=True)
        self.assertEqual(self.place(inside)[1], "twice")
        back = self.timeline.next_line(inside, out=True)
        self.assertEqual(self.place(back)[1], "page0.load")

    def test_step_back(self):
        after = self.timeline.next_line(0)
        self.assertEqual(self.timeline.previous_line(after), 0)
        self.assertIsNone(self.timeline.previous_line(0))

    def test_breakpoints_both_ways(self):
        line = self.line_of("pages/lib/numbers.nx", "return doubled")
        breakpoints = {(path_key(str(self.root / "pages/lib/numbers.nx")), line)}
        found = self.timeline.next_breakpoint(0, breakpoints)
        self.assertEqual(self.place(found), (line, "twice"))
        self.assertIsNone(self.timeline.next_breakpoint(found, breakpoints))
        self.assertEqual(self.timeline.next_breakpoint(len(self.timeline) - 1, breakpoints,
                                                       backward=True), found)

    def test_a_breakpoint_on_a_call_stops_once(self):
        # The call's line has steps before the call and after it returns.
        breakpoints = {(path_key(str(self.root / "pages/page0.nx")), 4)}
        self.assertIsNone(self.timeline.next_breakpoint(0, breakpoints))
        self.assertEqual(self.timeline.next_breakpoint(len(self.timeline) - 1, breakpoints,
                                                       backward=True), 0)

    def test_values_at_a_step(self):
        last = len(self.timeline) - 1
        # sys0 starts as program.nx declares it, then the code sets it.
        self.assertEqual(self.timeline.values_at(0)["sys0"], 0)
        self.assertEqual(self.timeline.values_at(last)["sys0"], 6)

    def test_a_growing_recording(self):
        recorder = Recorder()
        with recording(recorder):
            SourceFolderRunner(self.root).run("page0", [("page0", "load")],
                                              {"sys2": 0, "n0.val": 3, "title.txt": ""})
            timeline = Timeline(recorder)
            first_run = len(timeline)
            self.assertIsNone(timeline.next_line(first_run - 1))
            SourceFolderRunner(self.root).run("page0", [("title", "down")], {"sys2": 0})
        timeline.catch_up()
        self.assertEqual(len(timeline), first_run + 1)
        self.assertEqual(timeline.next_line(first_run - 1), first_run)
        self.assertEqual(timeline.values_at(first_run)["sys2"], 0)


class PythonReplayTest(DebuggerTestCase):

    def setUp(self):
        super().setUp()
        recorder, _ = self.traced("test_page.TwoRunsTest.test_two_runs")
        self.timeline = Timeline(recorder)
        self.call = next(position for position in range(len(self.timeline))
                         if self.timeline.step(position).place.line == test_line("first = load(3)"))

    def owner(self, position: int) -> str:
        return self.timeline.step(position).place.owner

    def test_step_over_a_run_goes_to_the_next_line(self):
        after = self.timeline.next_line(self.call)
        self.assertEqual(self.timeline.step(after).place.line, test_line('first["title.txt"]'))
        self.assertEqual(self.timeline.previous_line(after), self.call)

    def test_step_into_the_helper_then_the_screen_and_out(self):
        helper = self.timeline.next_line(self.call, into=True)
        self.assertEqual(self.owner(helper), "load")
        screen = self.timeline.next_line(self.timeline.next_line(helper), into=True)
        self.assertEqual(self.owner(screen), "page0.load")
        back = self.timeline.next_line(screen, out=True)
        self.assertEqual(self.owner(back), "TwoRunsTest.test_two_runs")

    def test_at_a_python_line_the_screen_shows_the_last_run(self):
        after = self.timeline.next_line(self.call)
        self.assertEqual(self.timeline.values_at(after)["title.txt"], "six")
        self.assertEqual(self.timeline.values_at(self.call), {})

    def test_a_breakpoint_in_the_test_file(self):
        line = test_line('second["sys0"]')
        found = self.timeline.next_breakpoint(0, {(path_key(str(self.tests / "test_page.py")),
                                                   line)})
        self.assertEqual(self.timeline.step(found).place.line, line)


class AdapterTest(DebuggerTestCase):

    def setUp(self):
        super().setUp()
        self.sent = []
        self.adapter = DebugAdapter(self.sent.append)
        self.sequence = 0

    def request(self, command: str, **arguments) -> dict:
        self.sequence += 1
        self.adapter.handle({"type": "request", "seq": self.sequence, "command": command,
                             "arguments": arguments})
        return [message for message in self.sent
                if message.get("request_seq") == self.sequence][-1]

    def stops(self) -> list:
        return [message["body"] for message in self.sent if message.get("event") == "stopped"]

    def ended(self) -> bool:
        return any(message.get("event") == "terminated" for message in self.sent)

    def frames(self) -> list:
        frames = self.request("stackTrace", threadId=1)["body"]["stackFrames"]
        return [(frame["name"], frame["line"]) for frame in frames]

    def variables(self, frame: int, scope: str) -> dict:
        scopes = self.request("scopes", frameId=frame)["body"]["scopes"]
        reference = next(entry["variablesReference"] for entry in scopes if entry["name"] == scope)
        found = self.request("variables", variablesReference=reference)["body"]["variables"]
        return {variable["name"]: variable for variable in found}

    def start(self, test: str, breakpoints: dict = None, **launch):
        self.assertTrue(self.request("initialize")["body"]["supportsStepBack"])
        for path, lines in (breakpoints or {}).items():
            self.request("setBreakpoints", source={"path": str(path)},
                         breakpoints=[{"line": line} for line in lines])
        reply = self.request("launch", testFolder=str(self.tests), test=test, **launch)
        self.assertTrue(reply["success"], reply.get("message"))
        self.request("configurationDone")

    def test_a_session(self):
        call_line = self.line_of("pages/lib/numbers.nx", "return doubled")
        self.start("test_page.LoadTest.test_load",
                   {self.root / "pages/lib/numbers.nx": [call_line]})
        self.assertEqual(self.stops()[-1]["reason"], "entry")
        self.assertEqual(self.frames(), [("LoadTest.test_load", test_line("values = SCREEN"))])
        self.request("continue", threadId=1)
        self.assertEqual(self.stops()[-1]["reason"], "breakpoint")
        self.assertEqual(self.frames(), [("twice", call_line), ("page0.load", 4),
                                         ("run page0: page0.load", 0),
                                         ("LoadTest.test_load", test_line("values = SCREEN"))])
        local_values = self.variables(1, "Locals")
        self.assertEqual({(name, variable["value"]) for name, variable in local_values.items()},
                         {("value", "3"), ("doubled", "6"), ("(result)", "0")})
        self.assertEqual(self.variables(1, "Page")["title.txt"]["value"], '""')
        # The test's frame, under the screen's, shows its own locals at its line.
        self.assertIn("self", self.variables(4, "Locals"))
        self.request("stepOut", threadId=1)
        self.assertEqual(self.frames()[0][0], "page0.load")
        self.request("reverseContinue", threadId=1)
        self.assertEqual(self.frames()[0], ("twice", call_line))
        self.request("stepBack", threadId=1)
        self.assertEqual(self.frames()[0][0], "twice")
        output = [message for message in self.sent if message.get("event") == "output"]
        self.assertIn("ok", output[0]["body"]["output"])

    def test_python_locals_and_the_screen_at_an_assertion(self):
        line = test_line('values["title.txt"], "six"')
        self.start("test_page.LoadTest.test_load", {self.tests / "test_page.py": [line]},
                   stopOnEntry=False)
        self.assertEqual((self.stops()[-1]["reason"], self.frames()[0]),
                         ("breakpoint", ("LoadTest.test_load", line)))
        values = self.variables(1, "Locals")["values"]
        self.assertGreater(values["variablesReference"], 0)
        entries = self.request("variables", variablesReference=values["variablesReference"])
        self.assertIn(("'title.txt'", "'six'"), {(entry["name"], entry["value"])
                                                 for entry in entries["body"]["variables"]})
        self.assertEqual(self.variables(1, "Page")["title.txt"]["value"], '"six"')

    def test_a_failing_assertion_stops_as_an_exception(self):
        self.start("test_page.TwoRunsTest.test_failing_check", stopOnEntry=False)
        self.assertEqual(self.stops()[-1]["reason"], "exception")
        self.assertIn("AssertionError", self.stops()[-1]["description"])
        self.assertEqual(self.frames()[0], ("TwoRunsTest.test_failing_check",
                                            test_line('values["sys0"], 7')))

    def test_stepping_over_a_failure_stops_on_it(self):
        self.start("test_page.TwoRunsTest.test_failing_check")
        self.request("next", threadId=1)
        self.assertEqual(self.stops()[-1]["reason"], "exception")

    def test_an_error_stops_as_an_exception(self):
        self.start("test_page.LoadTest.test_unset_field", stopOnEntry=False)
        self.assertEqual(self.stops()[-1]["reason"], "exception")
        self.assertIn("n0.val has no value", self.stops()[-1]["description"])
        self.assertEqual(self.frames()[0], ("page0.load", 4))

    def test_the_session_ends_past_the_last_step(self):
        self.start("test_page.LoadTest.test_load")
        for _ in range(200):
            if self.ended():
                break
            self.request("next", threadId=1)
        self.assertTrue(self.ended())

    def test_replies_come_before_events(self):
        self.start("test_page.LoadTest.test_load")
        kinds = [message.get("command") or message.get("event") for message in self.sent]
        self.assertLess(kinds.index("initialize"), kinds.index("initialized"))
        self.sent.clear()
        self.request("next", threadId=1)
        self.assertEqual([message["type"] for message in self.sent], ["response", "event"])

    def test_a_launch_without_its_test(self):
        self.request("initialize")
        reply = self.request("launch", testFolder=str(self.tests))
        self.assertFalse(reply["success"])

    def test_disconnect(self):
        self.request("initialize")
        self.request("disconnect")
        self.assertTrue(self.adapter.finished)


class TestCommandTest(DebuggerTestCase):

    def run_tests(self, *options: str) -> tuple:
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(["test", str(self.tests), *options])
        return code, output.getvalue()

    def test_list(self):
        self.assertEqual(self.run_tests("--list"),
                         (0, "test_page.LoadTest.test_load\ntest_page.LoadTest.test_unset_field\n"
                             "test_page.TwoRunsTest.test_failing_check\n"
                             "test_page.TwoRunsTest.test_two_runs\n"))

    def test_report(self):
        report = self.root.parent / "report.json"
        code, _ = self.run_tests("--report", str(report))
        self.assertEqual(code, 1)
        found = {entry["id"]: entry for entry in json.loads(report.read_text(encoding="utf-8"))}
        self.assertEqual(found["test_page.LoadTest.test_load"]["outcome"], "passed")
        failed = found["test_page.LoadTest.test_unset_field"]
        self.assertEqual((failed["outcome"], Path(failed["file"]).name, failed["line"]),
                         ("error", "test_page.py",
                          test_line('        SCREEN.run("page0", [("page0", "load")])')))
        self.assertEqual(found["test_page.TwoRunsTest.test_failing_check"]["outcome"], "failed")

    def test_report_of_other_outcomes(self):
        class Sample(unittest.TestCase):
            @unittest.expectedFailure
            def test_expected(self):
                self.fail()

            @unittest.expectedFailure
            def test_unexpected(self):
                pass

            def test_part(self):
                with self.subTest(part=1):
                    self.fail("part one")

        suite = unittest.defaultTestLoader.loadTestsFromTestCase(Sample)
        result = unittest.TextTestRunner(stream=io.StringIO(),
                                         resultclass=RecordingResult).run(suite)
        found = {entry["id"].rsplit(".", 1)[1]: entry["outcome"]
                 for entry in results(result, Path(__file__).parent)}
        self.assertEqual(found, {"test_expected": "passed", "test_unexpected": "failed",
                                 "test_part": "failed"})




class RollingRecordingTest(unittest.TestCase):
    """A simulation's recording, which keeps only its last steps."""

    def record(self, keep):
        from nxwright.testing.editor_machine import EditorMachine
        from nxwright.testing.recording import Place
        recorder = Recorder(keep=keep)
        machine = EditorMachine({"sys0": 0, "sys1": 0}, recorder=recorder)
        recorder.begin("run", ".", machine.values, {})
        lines = ["for(sys1=0;sys1<30;sys1++)", "{", "sys0=sys0+2", "}"]
        machine.run(lines, [Place("a.nx", number, "e") for number in (1, 2, 3, 4)])
        recorder.end(machine.values)
        return Timeline(recorder)

    def test_the_kept_steps_give_the_same_values(self):
        whole, rolling = self.record(None), self.record(20)
        self.assertLessEqual(len(rolling.recorder.steps), 20)
        self.assertGreater(rolling.first, 0)
        self.assertEqual(len(rolling), len(whole))
        for position in range(rolling.first, len(rolling)):
            self.assertEqual(rolling.values_at(position), whole.values_at(position), position)

    def test_stepping_back_stops_at_the_oldest_kept(self):
        rolling = self.record(20)
        self.assertIsNone(rolling.previous_line(rolling.first))
        found = rolling.next_breakpoint(len(rolling) - 1, {(path_key("a.nx"), 3)}, backward=True)
        self.assertGreaterEqual(found, rolling.first)
        self.assertIsNone(rolling.next_breakpoint(found, {(path_key("a.nx"), 4)}, backward=True))


if __name__ == "__main__":
    unittest.main()
