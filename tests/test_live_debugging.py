"""Debugging a running simulation (debug_adapter/live.py), through the debug
adapter's requests, as VS Code sends them; and how the simulation shares its
time, on a clock the tests move by hand."""
import base64
import threading
import time
import unittest
from unittest import mock

from nxwright.debug_adapter.adapter import DebugAdapter
from nxwright.debug_adapter.live import LIVE_DRAWING, WAVES_PACE, LiveSimulation, WallClock
from nxwright.drawing.screen_pictures import ScreenPictures
from nxwright.source.source_folder import read_app
from nxwright.testing.simulation import Simulation
from nxwright.testing.wave_generators import generator_settings, generator_to_json
from tests.test_simulation import SimulationTestCase, placed, table

# How long a test waits for the simulation's thread, in seconds.
_PATIENCE = 10


class LiveTestCase(SimulationTestCase):
    """page0 with a button, "go", whose press counts in `count` over three
    lines, and a timer, off until "start" turns it on."""

    def setUp(self):
        super().setUp()
        self.program("int count=0, ticks=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0), placed("start", "button", 0, 100),
                            placed("bad", "button", 0, 200), placed("hold", "button", 0, 300),
                            table("tick", "timer", tim=50, en=0)], """\
on go.down:
  count = count + 1
  count = count + 10
  prints "pressed",0

on start.down:
  tick.en = 1

on tick.timer:
  ticks = ticks + 1

on hold.down:
  delay = 300

on bad.down:
  count = count / ticks
""")
        self.page("second", [])
        self.sent = []
        self.lock = threading.Lock()
        self.adapter = DebugAdapter(self.send)
        self.sequence = 0

    def tearDown(self):
        try:
            self.end_session()
        finally:
            super().tearDown()

    def end_session(self):
        """Ends the debugging session, and waits for the simulation's thread
        to stop, so that it no longer reads the folder tearDown deletes."""
        self.request("disconnect")
        live = self.adapter._live
        if live is not None and live._thread.is_alive():
            live._thread.join(_PATIENCE)
            self.assertFalse(live._thread.is_alive(), "the simulation did not end")

    def send(self, message: dict):
        with self.lock:
            self.sent.append(message)

    def request(self, command: str, **arguments) -> dict:
        self.sequence += 1
        self.adapter.handle({"type": "request", "seq": self.sequence, "command": command,
                             "arguments": arguments})
        with self.lock:
            return [message for message in self.sent
                    if message.get("request_seq") == self.sequence][-1]

    def request_later(self, command: str, **arguments) -> int:
        """Sends a request whose reply may come later, from the simulation's
        thread, and returns its number."""
        self.sequence += 1
        self.adapter.handle({"type": "request", "seq": self.sequence, "command": command,
                             "arguments": arguments})
        return self.sequence

    def replies_to(self, sequence: int) -> list:
        with self.lock:
            return [message for message in self.sent if message.get("type") == "response"
                    and message.get("request_seq") == sequence]

    def reply_to(self, sequence: int) -> dict:
        """Waits for the reply to the request numbered `sequence`."""
        deadline = time.monotonic() + _PATIENCE
        while time.monotonic() < deadline:
            replies = self.replies_to(sequence)
            if replies:
                return replies[0]
            time.sleep(0.01)
        self.fail("request %d had no reply" % sequence)

    def events(self, name: str) -> list:
        with self.lock:
            return [message["body"] for message in self.sent if message.get("event") == name]

    def wait_for(self, name: str, count: int = 1) -> dict:
        """Waits for the `count`th event `name`, and returns its body."""
        deadline = time.monotonic() + _PATIENCE
        while time.monotonic() < deadline:
            found = self.events(name)
            if len(found) >= count:
                return found[count - 1]
            time.sleep(0.01)
        self.fail("no %s event %d came" % (name, count))

    def wait_for_log(self, count: int = 1) -> list:
        """Waits for the `count`th output event of the log, in the Debug
        Console, and returns its lines without their times."""
        deadline = time.monotonic() + _PATIENCE
        while time.monotonic() < deadline:
            found = [body for body in self.events("output") if body["category"] == "stdout"]
            if len(found) >= count:
                return [line.split(" s  ", 1)[1]
                        for line in found[count - 1]["output"].splitlines()]
            time.sleep(0.01)
        self.fail("no log %d came" % count)

    def launch(self, breakpoints: dict = None, **arguments):
        self.request("initialize")
        self.request("launch", sourceFolder=str(self.root), **arguments)
        for path, lines in (breakpoints or {}).items():
            self.request("setBreakpoints", source={"path": str(self.root / path)},
                         breakpoints=[{"line": line} for line in lines])
        self.request("configurationDone")

    def frames(self) -> list:
        frames = self.request("stackTrace", threadId=1)["body"]["stackFrames"]
        return [(frame["name"], frame["line"]) for frame in frames]

    def program_value(self, name: str):
        scopes = self.request("scopes", frameId=1)["body"]["scopes"]
        reference = next(entry["variablesReference"] for entry in scopes
                         if entry["name"] == "Program")
        found = self.request("variables", variablesReference=reference)["body"]["variables"]
        return next(variable["value"] for variable in found if variable["name"] == name)


class LiveDebuggingTest(LiveTestCase):

    def test_the_start_is_told_page_by_page_before_the_first_drawing(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        with self.lock:
            names = [message["event"] for message in self.sent if message.get("type") == "event"]
        self.assertEqual(self.events("nxwright/starting"),
                         [{"number": 1, "count": 2, "page": "page0"},
                          {"number": 2, "count": 2, "page": "second"},
                          {"number": 2, "count": 2, "page": None}])
        last_starting = len(names) - 1 - names[::-1].index("nxwright/starting")
        self.assertLess(last_starting, names.index("nxwright/drawing"))
        # In the Debug Console: each page, then each of its files on a line of its own.
        console = "".join(body["output"] for body in self.events("output")
                          if body["category"] == "console")
        root = self.root.resolve()
        self.assertEqual(console, "Compiling page 1 of 2: page0\n    %s\n"
                                  "Compiling page 2 of 2: second\n    %s\n"
                                  "Compiling program.nx\n    %s\n"
                         % (root / "pages" / "page0.nx", root / "pages" / "second.nx",
                            root / "program.nx"))

    def test_a_breakpoint_in_a_press_then_stepping(self):
        self.launch({"pages/page0.nx": [3]})
        self.wait_for("nxwright/drawing")
        self.request("nxwright/press", x=10, y=10)
        stop = self.wait_for("stopped")
        self.assertEqual(stop["reason"], "breakpoint")
        self.assertEqual(self.frames()[0], ("go.down", 3))
        self.assertEqual(self.program_value("count"), "1")
        self.request("next")
        self.wait_for("stopped", 2)
        self.assertEqual(self.frames()[0], ("go.down", 4))
        self.assertEqual(self.program_value("count"), "11")
        # Back, then forward again, through what was recorded.
        self.request("stepBack")
        self.assertEqual(self.frames()[0], ("go.down", 3))
        self.request("next")
        self.assertEqual(self.frames()[0], ("go.down", 4))
        self.request("continue")
        self.assertEqual(self.wait_for_log(), ["SIM SEND: 70 72 65 73 73 65 64"])

    def test_a_session_ends_before_its_folder_goes(self):
        # tearDown deletes the folder, which the simulation's thread reads
        # as the app starts: the thread must have stopped by then.
        self.launch()
        live = self.adapter._live
        self.end_session()
        self.assertFalse(live._thread.is_alive())

    def test_the_thread_is_announced(self):
        # VS Code pauses only a thread it knows of, and learns of one from
        # this event, or once the debuggee stops: a simulation may never stop.
        self.launch()
        self.assertEqual(self.wait_for("thread"), {"reason": "started", "threadId": 1})

    def test_pausing_and_continuing_while_time_passes(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        self.request("nxwright/press", x=10, y=110)
        self.wait_for("nxwright/drawing", 2)
        self.request("pause")
        stop = self.wait_for("stopped")
        self.assertEqual(stop["reason"], "pause")
        ticks = self.adapter._live.simulation.globals["ticks"]
        time.sleep(0.2)
        # Paused, time stands still.
        self.assertEqual(self.adapter._live.simulation.globals["ticks"], ticks)
        self.request("continue")
        deadline = time.monotonic() + _PATIENCE
        while self.adapter._live.simulation.globals["ticks"] < ticks + 2:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)

    def test_an_error_in_the_code_stops_as_an_exception(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        self.request("nxwright/press", x=10, y=210)
        stop = self.wait_for("stopped")
        self.assertEqual(stop["reason"], "exception")
        self.assertIn("ZeroDivisionError", stop["description"])

    def test_an_app_that_does_not_build_ends_the_session(self):
        self.write("pages/page0.nx", "on go.down:\n  nowhere.val = 1\n")
        self.launch()
        self.wait_for("terminated")
        errors = [body for body in self.events("output") if body["category"] == "stderr"]
        self.assertIn("nowhere", errors[0]["output"])

    def test_a_start_again_that_does_not_build_leaves_the_app_running(self):
        # It stops on the refusal, as on an exception. Once the debugger goes
        # on, the app runs on as it was.
        self.launch()
        drawing = self.wait_for("nxwright/drawing")
        self.write("pages/page0.nx", "on go.down:\n  nowhere.val = 1\n")
        self.request("nxwright/startAgain")
        stop = self.wait_for("stopped")
        self.assertEqual(stop["reason"], "exception")
        self.assertIn("pages/page0.nx line 2: nowhere", stop["description"])
        self.request("continue")
        self.request("nxwright/press", x=10, y=10)
        self.assertEqual(self.wait_for_log()[-1], "SIM SEND: 70 72 65 73 73 65 64")
        self.assertEqual(self.adapter._live.simulation.starts, drawing["start"])

    def test_a_press_during_a_delay_waits(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        self.request("nxwright/press", x=10, y=310)
        self.request("nxwright/press", x=10, y=10)
        self.assertEqual(self.wait_for_log()[-1], "SIM SEND: 70 72 65 73 73 65 64")

    def test_a_program_that_opens_no_page(self):
        self.program("int count=0, ticks=0\n")
        self.launch()
        self.request("nxwright/serial", text="count=3")
        self.assertEqual(self.wait_for_log()[0], "SIM RECV: count=3")
        self.assertEqual(self.events("nxwright/drawing"), [])
        self.assertEqual(self.events("terminated"), [])

    def test_the_logs_formats_from_the_launch(self):
        self.launch(logReceived="hex", logSent="both")
        self.request("nxwright/serial", text="count=3")
        self.assertEqual(self.wait_for_log()[0], "SIM RECV: 63 6f 75 6e 74 3d 33 ff ff ff")

    def test_an_unknown_log_format_stops_the_launch(self):
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), logSent="sideways")
        self.assertFalse(reply["success"])
        self.assertIn("text, hex, or both", reply["message"])

    def test_the_gpio_pins_at_the_launch_and_when_set(self):
        self.launch(gpioInputs={"pio2": 0})
        pins = self.wait_for("nxwright/gpio")["pins"]
        self.assertEqual([pin["level"] for pin in pins], [1, 1, 0, 1, 1, 1, 1, 1])
        self.assertEqual(pins[2], {"mode": 0, "component": None, "level": 0})
        self.assertTrue(self.request("nxwright/gpioInput", pin=2, level=1)["success"])
        self.assertEqual(self.wait_for("nxwright/gpio", 2)["pins"][2]["level"], 1)

    def test_a_gpio_level_out_of_range_is_refused(self):
        self.launch()
        for pin, level, said in ((2, 5, "0 or 1"), (8, 0, "from 0 to 7"), (2.0, 0, "from 0 to 7"),
                                 (True, 0, "from 0 to 7"), (2, 0.0, "0 or 1")):
            with self.subTest(pin=pin, level=level):
                reply = self.request("nxwright/gpioInput", pin=pin, level=level)
                self.assertFalse(reply["success"])
                self.assertIn(said, reply["message"])

    def test_several_gpio_levels_set_in_one_action(self):
        self.launch()
        self.wait_for("nxwright/gpio")
        self.assertTrue(self.request("nxwright/gpioInputs",
                                     levels={"pio2": 0, "pio5": 0})["success"])
        # One action, so the pins' event comes once, with both levels.
        pins = self.wait_for("nxwright/gpio", 2)["pins"]
        self.assertEqual([pin["level"] for pin in pins], [1, 1, 0, 1, 1, 0, 1, 1])

    def test_several_gpio_levels_are_checked_before_any_is_queued(self):
        self.launch()
        for levels, said in (({"pio2": 0, "pio5": 2}, "0 or 1"), ({"pi02": 0}, "pio0 to pio7"),
                             ({}, "at least one"), ([0, 1], "by name")):
            with self.subTest(levels=levels):
                reply = self.request("nxwright/gpioInputs", levels=levels)
                self.assertFalse(reply["success"])
                self.assertIn(said, reply["message"])

    def test_an_unknown_gpio_input_stops_the_launch(self):
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), gpioInputs={"pi02": 0})
        self.assertFalse(reply["success"])
        self.assertIn("pio0 to pio7", reply["message"])

    def test_a_launch_another_check_stops_makes_no_eeprom_file(self):
        path = self.root.parent / "eeprom.bin"
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), eeprom=str(path),
                             logSent="sideways")
        self.assertFalse(reply["success"])
        self.assertFalse(path.exists())

    def test_a_missing_eeprom_file_is_made(self):
        # Holding an empty EEPROM, and the Debug Console says so.
        path = self.root.parent / "eeprom.bin"
        self.launch(eeprom=str(path))
        self.wait_for("nxwright/drawing")
        self.assertEqual(path.read_bytes(), bytes(1024))
        console = "".join(body["output"] for body in self.events("output")
                          if body["category"] == "console")
        self.assertIn("The EEPROM's file %s was made, holding an empty EEPROM." % path, console)

    def test_stopping_on_entry(self):
        self.launch(stopOnEntry=True)
        self.wait_for("stopped")
        self.assertEqual(self.frames()[0][0], "program")

    def test_the_drawing_and_starting_again(self):
        self.launch()
        drawing = self.wait_for("nxwright/drawing")
        self.assertEqual((drawing["page"], drawing["dim"], drawing["width"]), ("page0", 100, 800))
        self.assertEqual((drawing["start"], drawing["entry"]), (1, 1))
        self.request("nxwright/startAgain")
        self.assertEqual(self.wait_for_log()[0], "started again, the EEPROM kept")
        drawing = self.wait_for("nxwright/drawing", 2)
        self.assertEqual((drawing["start"], drawing["entry"]), (2, 2))

    def test_a_page_changed_while_ref_stop_holds_is_drawn_as_the_page_before(self):
        # The panel keeps the page before, as that page's entry, until
        # ref_star. The screen's brightness changes at once.
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "dim=50"):
            simulation.serial_input(line)
        self.adapter._live_news("drawing", simulation)
        drawing = self.events("nxwright/drawing")[-1]
        self.assertEqual((drawing["page"], drawing["entry"], drawing["dim"]), ("page0", 1, 50))
        simulation.serial_input("ref_star")
        self.adapter._live_news("drawing", simulation)
        drawing = self.events("nxwright/drawing")[-1]
        self.assertEqual((drawing["page"], drawing["entry"]), ("second", 2))


class AgentRequestsTest(LiveTestCase):
    """What an agent asks of a simulation through the extension: actions
    answered once handled, and looks at what the simulation holds."""

    def count(self) -> int:
        return self.adapter._live.simulation.globals["count"]

    def started(self):
        self.launch()
        self.wait_for("nxwright/drawing")

    def test_an_action_handled_is_answered_once_done(self):
        self.started()
        reply = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True))
        self.assertTrue(reply["success"])
        # The press's event ran before the reply.
        self.assertEqual(self.count(), 11)
        self.assertTrue(self.reply_to(self.request_later("nxwright/release", handled=True))
                        ["success"])

    def test_the_looks(self):
        self.started()
        self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True))
        components = self.reply_to(self.request_later("nxwright/components"))["body"]
        self.assertEqual(components["components"][1],
                         {"name": "go", "type": "button", "x": 0, "y": 0, "w": 100, "h": 50,
                          "shown": True})
        values = self.reply_to(self.request_later("nxwright/values", names=["count"]))["body"]
        self.assertEqual(values, {"values": {"count": 11}})
        lines = self.reply_to(self.request_later("nxwright/log", after=0))["body"]["lines"]
        self.assertEqual([(entry["number"], entry["line"]) for entry in lines],
                         [(1, "SIM SEND: 70 72 65 73 73 65 64")])

    def test_a_look_at_the_screen(self):
        # Its text layout, the page shown, and a PNG picture, in base64.
        self.started()
        shown = self.reply_to(self.request_later("nxwright/screen"))["body"]
        self.assertEqual(shown["page"], "page0")
        self.assertIn("go", shown["text"])
        self.assertEqual(base64.b64decode(shown["png"])[:8], b"\x89PNG\r\n\x1a\n")
        unpictured = self.reply_to(self.request_later("nxwright/screen", picture=False))["body"]
        self.assertEqual(set(unpictured), {"text", "page"})

    def test_the_pictures_see_every_drawing_the_panel_gets(self):
        # So that a page without background is pictured over what showed
        # before it, though no agent asked for a picture then.
        self.page("page0", [placed("go", "button", 0, 0)], "on go.down:\n  page second\n")
        given = []
        with mock.patch.object(ScreenPictures, "shown", autospec=True,
                               side_effect=lambda pictures, drawing: given.append(
                                   drawing["page"])):
            self.started()
            self.request("nxwright/press", x=10, y=10)
            self.wait_for("nxwright/drawing", 3)
        sent = [drawing["page"] for drawing in self.events("nxwright/drawing")]
        self.assertEqual(given[:len(sent)], sent)

    def test_a_look_that_fails_says_why(self):
        self.started()
        reply = self.reply_to(self.request_later("nxwright/values", names=["speed"]))
        self.assertFalse(reply["success"])
        self.assertEqual(reply["message"], "the page shown has nothing named speed")

    def test_a_look_is_answered_while_stopped_at_a_breakpoint(self):
        # As the debugger's Variables view reads it: the event in progress.
        self.launch({"pages/page0.nx": [3]})
        self.wait_for("nxwright/drawing")
        self.request("nxwright/press", x=10, y=10)
        self.wait_for("stopped")
        values = self.reply_to(self.request_later("nxwright/values", names=["count"]))["body"]
        self.assertEqual(values, {"values": {"count": 1}})

    def test_an_action_while_stopped_is_refused(self):
        self.started()
        self.request("pause")
        self.wait_for("stopped")
        reply = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True))
        self.assertFalse(reply["success"])
        self.assertIn("stopped in the debugger", reply["message"])
        self.request("continue")
        time.sleep(0.2)
        self.assertEqual(self.count(), 0)

    def test_an_action_stopped_at_a_breakpoint_is_answered_then_finishes(self):
        self.launch({"pages/page0.nx": [3]})
        self.wait_for("nxwright/drawing")
        sequence = self.request_later("nxwright/press", x=10, y=10, handled=True)
        self.wait_for("stopped")
        reply = self.reply_to(sequence)
        self.assertFalse(reply["success"])
        self.assertIn("stopped in the debugger while handling it", reply["message"])
        self.request("continue")
        deadline = time.monotonic() + _PATIENCE
        while self.count() != 11:
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.01)
        self.assertEqual(len(self.replies_to(sequence)), 1)

    def test_an_action_stopped_by_an_error_in_the_code_goes_no_further(self):
        # The reply gives the error, and that the simulation waits on the
        # debugger. The machine's division by zero has no text: its kind
        # stands for it.
        self.started()
        reply = self.reply_to(self.request_later("nxwright/press", x=10, y=210, handled=True))
        self.assertFalse(reply["success"])
        self.assertIn("on an error in the code while handling it, so it goes no further: "
                      "ZeroDivisionError.", reply["message"])
        self.assertIn("handles no action until the debugger lets it go on", reply["message"])

    def test_an_agents_start_again_on_a_folder_that_no_longer_builds(self):
        # The refusal reaches the agent, with its file and line.
        self.started()
        self.write("pages/page0.nx", "on go.down:\n  nowhere.val = 1\n")
        reply = self.reply_to(self.request_later("nxwright/startAgain", handled=True, agent=True))
        self.assertFalse(reply["success"])
        self.assertIn("pages/page0.nx line 2: nowhere", reply["message"])

    def test_an_action_waiting_when_the_debugger_pauses_is_not_done(self):
        # The delay of hold's press keeps the press on go waiting in turn.
        self.started()
        self.request("nxwright/press", x=10, y=310)
        sequence = self.request_later("nxwright/press", x=10, y=10, handled=True)
        self.request("pause")
        self.wait_for("stopped")
        reply = self.reply_to(sequence)
        self.assertFalse(reply["success"])
        self.assertIn("before handling it, so it was not done", reply["message"])
        self.request("continue")
        time.sleep(0.6)
        self.assertEqual(self.count(), 0)

    def test_moves_replaced_are_answered_with_the_move_that_replaced_them(self):
        self.started()
        self.request("nxwright/press", x=10, y=310)
        moves = [self.request_later("nxwright/move", x=x, y=310, handled=True)
                 for x in (20, 30, 40)]
        for sequence in moves:
            self.assertTrue(self.reply_to(sequence)["success"])
        time.sleep(0.1)
        self.assertEqual([len(self.replies_to(sequence)) for sequence in moves], [1, 1, 1])

    def test_an_agents_move_never_replaces_the_users(self):
        # An agent's move may be refused, while a serial port is connected:
        # the user's own move waiting before it must not be lost with it.
        self.started()
        self.request("nxwright/press", x=10, y=310)
        self.request("nxwright/move", x=20, y=310)
        self.request_later("nxwright/move", x=30, y=310, handled=True, agent=True)
        live = self.adapter._live
        with live._condition:
            kinds = [kind for _, kind in live._actions]
        self.assertEqual(len([kind for kind in kinds if kind is not None]), 2)

    def test_the_session_ending_answers_what_waits(self):
        self.started()
        self.request("nxwright/press", x=10, y=310)
        sequence = self.request_later("nxwright/press", x=10, y=10, handled=True)
        self.request("disconnect")
        reply = self.reply_to(sequence)
        self.assertFalse(reply["success"])
        self.assertIn("the simulation ended", reply["message"])

    def test_after_a_start_that_failed_nothing_waits(self):
        # The simulation's thread is gone: an answer would never come.
        self.write("pages/page0.nx", "on go.down:\n  nowhere.val = 1\n")
        self.launch()
        self.wait_for("terminated")
        for command, arguments in (("nxwright/press", {"x": 10, "y": 10, "handled": True}),
                                   ("nxwright/values", {})):
            with self.subTest(command):
                reply = self.request(command, **arguments)
                self.assertFalse(reply["success"])
                self.assertIn("the simulation has ended", reply["message"])

    def test_a_request_after_terminated_is_refused_at_once(self):
        # Held between telling of the failure, as terminated, and its end,
        # the simulation's thread could answer nothing more: a request then
        # is refused at once, not left for that thread to answer.
        self.write("pages/page0.nx", "on go.down:\n  nowhere.val = 1\n")
        told, go_on = threading.Event(), threading.Event()
        news = self.adapter._live_news

        def held_news(kind, body):
            news(kind, body)
            if kind == "failed":
                told.set()
                go_on.wait(_PATIENCE)
        try:
            with mock.patch.object(self.adapter, "_live_news", held_news):
                self.launch()
                self.assertTrue(told.wait(_PATIENCE), "the start did not fail")
                reply = self.request("nxwright/values")
        finally:
            go_on.set()
        self.assertFalse(reply["success"])
        self.assertIn("the simulation has ended", reply["message"])

    def test_an_agents_action_without_a_port_is_done(self):
        self.started()
        reply = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True,
                                                 agent=True))
        self.assertTrue(reply["success"])
        self.assertEqual(self.count(), 11)

    def test_an_agents_touch_the_screen_cannot_take_is_refused(self):
        # One touch at a time, on the page, as without VS Code
        # (looks.touch_refusal).
        self.started()
        agent = {"handled": True, "agent": True}
        self.assertTrue(self.reply_to(self.request_later("nxwright/press", x=200, y=10, **agent))
                        ["success"])
        for command, arguments, refusal in (
                ("nxwright/press", {"x": 10, "y": 10},
                 "the screen is pressed already, and takes one touch at a time: "
                 "release it first"),
                ("nxwright/move", {"x": 900, "y": 10},
                 "900,10 lies off the page, which is 800 x 480")):
            with self.subTest(command):
                reply = self.reply_to(self.request_later(command, **arguments, **agent))
                self.assertFalse(reply["success"])
                self.assertEqual(reply["message"], refusal)
        self.assertEqual(self.count(), 0)
        self.assertTrue(self.reply_to(self.request_later("nxwright/release", **agent))
                        ["success"])
        reply = self.reply_to(self.request_later("nxwright/move", x=20, y=10, **agent))
        self.assertEqual(reply["message"], "the screen is not pressed: press it first")
        # The user's own touches on the panel are not checked.
        self.assertTrue(self.reply_to(self.request_later("nxwright/move", x=20, y=10,
                                                         handled=True))["success"])

    def test_an_agents_action_is_always_handled_before_its_reply(self):
        # Its reply is how it is refused, while a serial port is connected.
        self.started()
        reply = self.request("nxwright/press", x=10, y=10, agent=True)
        self.assertFalse(reply["success"])
        self.assertIn("handled", reply["message"])


class GeneratorRequestsTest(LiveTestCase):
    """The waveform generator's requests, on the page "second", which has a
    waveform of two channels, "chart"."""

    def setUp(self):
        super().setUp()
        self.page("second", [table("chart", "waveform", x=0, y=0, w=50, h=50, ch=2)])
        self.feeding = {"waveforms": [{"page": "second", "waveform": "chart"}],
                        "interval": 10, "channels": [{"channel": 0}]}

    def later(self, command: str, **arguments) -> dict:
        """Sends a request answered by the simulation's thread, and returns
        its reply."""
        return self.reply_to(self.request_later(command, **arguments))

    def points(self) -> list:
        """The points of the chart's channel 0, none while the app starts."""
        simulation = self.adapter._live.simulation
        return [] if simulation is None else simulation.waves().get("chart", {}).get(0, [])

    def wait_for_points(self, count: int):
        deadline = time.monotonic() + _PATIENCE
        while time.monotonic() < deadline:
            if len(self.points()) >= count:
                return
            time.sleep(0.01)
        self.fail("%d points did not come" % count)

    def test_the_waveforms_a_generator_can_feed(self):
        self.launch(page="second")
        self.assertEqual(self.later("nxwright/waveforms")["body"],
                         {"waveforms": [{"page": "second", "waveform": "chart", "channels": 2}]})

    def test_the_generator_starts_changes_and_stops(self):
        self.launch(page="second")
        self.assertEqual(self.later("nxwright/generator")["body"], {"generator": None})
        self.assertTrue(self.later("nxwright/startGenerator", settings=self.feeding)["success"])
        self.wait_for_points(3)
        self.assertEqual(self.later("nxwright/generator")["body"], {"generator": self.feeding})
        changed = dict(self.feeding, shape="custom", values=[77])
        self.assertTrue(self.later("nxwright/changeGenerator", settings=changed)["success"])
        self.wait_for_points(len(self.points()) + 3)
        self.assertEqual(self.points()[-1], 77)
        self.assertTrue(self.later("nxwright/stopGenerator")["success"])
        self.assertEqual(self.later("nxwright/generator")["body"], {"generator": None})
        lines = [line for body in self.events("output") if body["category"] == "stdout"
                 for line in body["output"].splitlines()]
        self.assertTrue(any("the waveform generator starts" in line for line in lines), lines)

    def test_a_generators_points_come_on_their_own_between_drawings(self):
        self.launch(page="second")
        self.wait_for("nxwright/drawing")
        self.later("nxwright/startGenerator", settings=self.feeding)
        sent = self.wait_for("nxwright/waves", 5)
        self.assertEqual((sent["page"], [wave["component"] for wave in sent["waveforms"]]),
                         ("second", ["chart"]))
        shape = sent["waveforms"][0]["shapes"][0]
        self.assertEqual((shape["kind"], shape["component"], shape["w"]), ("wave", "chart", 50))
        self.assertGreaterEqual(len(shape["points"]), 5)
        # They belong to the drawing sent before them, the only one.
        drawings = self.events("nxwright/drawing")
        self.assertEqual(len(drawings), 1)
        self.assertEqual((sent["start"], sent["entry"]),
                         (drawings[0]["start"], drawings[0]["entry"]))

    def test_a_refused_generator_leaves_the_simulation_running(self):
        self.launch(page="second")
        for settings, refusal in (
                (dict(self.feeding, shape="saw"), "settings: shape 'saw' is not a shape"),
                (dict(self.feeding, waveforms=[{"page": "second", "waveform": "none"}]),
                 "the page second has no waveform none")):
            with self.subTest(refusal=refusal):
                reply = self.later("nxwright/startGenerator", settings=settings)
                self.assertFalse(reply["success"])
                self.assertIn(refusal, reply["message"])
        for command, arguments in (("nxwright/stopGenerator", {}),
                                   ("nxwright/changeGenerator", {"settings": self.feeding})):
            reply = self.later(command, **arguments)
            self.assertEqual((reply["success"], reply["message"]),
                             (False, "no waveform generator is running"))
        self.assertEqual(self.events("stopped"), [])
        self.assertTrue(self.later("nxwright/startGenerator", settings=self.feeding)["success"])

    def test_the_generator_starts_while_the_debugger_holds_the_simulation(self):
        self.launch(page="second")
        self.wait_for("nxwright/drawing")
        self.request("pause", threadId=1)
        self.wait_for("stopped")
        self.assertTrue(self.later("nxwright/startGenerator", settings=self.feeding)["success"])
        self.assertEqual(self.points(), [])
        self.request("continue", threadId=1)
        self.wait_for_points(2)

    def test_a_launch_starts_the_generator_of_its_file(self):
        file = self.root / "waves.json"
        file.write_text(generator_to_json(generator_settings(self.feeding, "test")),
                        encoding="utf-8")
        self.launch(page="second", waveGenerator=str(file))
        self.wait_for_points(2)
        self.assertEqual(self.later("nxwright/generator")["body"], {"generator": self.feeding})

    def test_a_launch_is_refused_for_a_file_it_cannot_use(self):
        self.request("initialize")
        for file, refusal in ((str(self.root / "missing.json"), "cannot be read"),
                              (["waves.json"], "must be a settings file's path")):
            with self.subTest(file=file):
                reply = self.request("launch", sourceFolder=str(self.root), page="second",
                                     waveGenerator=file)
                self.assertFalse(reply["success"])
                self.assertIn(refusal, reply["message"])

    def test_a_launch_fails_for_a_waveform_the_app_lacks(self):
        file = self.root / "waves.json"
        settings = dict(self.feeding, waveforms=[{"page": "second", "waveform": "none"}])
        file.write_text(generator_to_json(generator_settings(settings, "test")),
                        encoding="utf-8")
        self.launch(page="second", waveGenerator=str(file))
        self.wait_for("terminated")
        failed = [body["output"] for body in self.events("output")
                  if body["category"] == "stderr"]
        self.assertIn("the page second has no waveform none", "".join(failed))


class LaunchDefinesTest(LiveTestCase):
    """A launch configuration's `defines`, new values of app.toml's defines
    for the simulation. The app starts `count` at START, and places "go" at
    x = LEFT through a placeholder."""

    def setUp(self):
        super().setUp()
        self.write("app.toml", self.text("app.toml") + "\n[defines]\nSTART = 7\nLEFT = 0\n")
        self.program("int count=0, ticks=0\ncount=START\n\npage page0\n")
        self.page("page0", [placed("go", "button", "%LEFT%", 0)])

    def started(self, **arguments):
        self.launch(**arguments)
        self.wait_for("nxwright/drawing")
        return self.adapter._live.simulation

    def test_the_simulations_thread_reads_the_new_values(self):
        simulation = self.started(defines={"START": 40, "LEFT": 200})
        self.assertEqual(simulation.globals["count"], 40)
        self.assertEqual(self.drawn_at(simulation, "go"), (200, 0))

    def test_without_defines_the_simulation_reads_the_defaults(self):
        simulation = self.started()
        self.assertEqual(simulation.globals["count"], 7)
        self.assertEqual(self.drawn_at(simulation, "go"), (0, 0))

    def test_the_adapters_thread_reads_the_new_values(self):
        # The adapter answers requests on its own thread, which reads the
        # folder too, such as the pictures of a look at the screen.
        self.started(defines={"START": 40})
        self.adapter._requests["test/start"] = lambda arguments: read_app(self.root)["defines"]
        reply = self.request("test/start")
        self.assertEqual(reply["body"]["START"], 40)

    def test_a_value_app_toml_does_not_allow_stops_the_launch(self):
        for defines, said in (({"STRAT": 40}, "does not declare STRAT (it declares LEFT, START)"),
                              ({"START": "many"}, "START is a number"),
                              ({"START": True}, "a whole number or a text"),
                              ([40], "must be an object")):
            with self.subTest(defines=defines):
                self.request("initialize")
                reply = self.request("launch", sourceFolder=str(self.root), defines=defines)
                self.assertFalse(reply["success"])
                self.assertIn(said, reply["message"])
                self.assertIn("launch configuration's defines", reply["message"])
                self.assertIsNone(self.adapter._live)

    def test_a_test_takes_no_defines(self):
        self.request("initialize")
        reply = self.request("launch", testFolder=str(self.root), test="test_x.Test.test_x",
                             defines={"START": 40})
        self.assertFalse(reply["success"])
        self.assertIn("defines is only for a simulation", reply["message"])


class DrawingInProgressTest(SimulationTestCase):

    def test_none_while_a_page_loads(self):
        # The screen shows a new page once its load event ends: until then,
        # the panel keeps the old page.
        self.program("page page0\n")
        news = []
        live = LiveSimulation(self.root, notify=lambda kind, body: news.append(kind))
        live.simulation = Simulation(self.root)
        live.simulation.loading = True
        live._send_news(in_progress=True)
        self.assertNotIn("drawing", news)
        live.simulation.loading = False
        live._send_news(in_progress=True)
        self.assertIn("drawing", news)

    def test_the_page_left_is_drawn_before_the_change(self):
        # A page without background is drawn over it.
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0)], "on go.down:\n  page second\n")
        drawn = []
        live = LiveSimulation(self.root, notify=lambda kind, body: drawn.append(
            body.page) if kind == "drawing" else None)
        live.simulation = Simulation(self.root, leaving=live._page_leaving)
        live.simulation.press("go")
        self.assertEqual(drawn, ["page0"])

    def test_while_work_waits_a_tenth_of_a_second_apart_at_most(self):
        # Instructions arriving faster than they run would otherwise each be
        # followed by a drawing, which holds them up.
        self.program("page page0\n")
        news = []
        # A clock moved by hand, so that neither the machine's speed nor its
        # clock's resolution decides when the wait is over.
        wall = ManualWallClock()
        live = LiveSimulation(self.root, notify=lambda kind, body: news.append(kind), wall=wall)
        live.simulation = Simulation(self.root)
        self.assertFalse(live._more_waiting())
        live.act(lambda simulation: None)
        self.assertTrue(live._more_waiting())
        live._send_news()
        live.simulation.changes += 1
        live._send_news(busy=True)
        self.assertEqual(news.count("drawing"), 1)      # too soon after the last
        wall.move(LIVE_DRAWING)
        live._send_news(busy=True)
        self.assertEqual(news.count("drawing"), 2)      # its turn
        live.simulation.changes += 1
        live._send_news()
        self.assertEqual(news.count("drawing"), 3)      # nothing waits: drawn at once


class ManualWallClock(WallClock):
    """A clock on the wall that moves only when moved: by what a test says
    statements and drawings cost, and by the simulation's waits, which pass
    at once. Work planned for a time runs once the clock reaches it, as a
    press comes in the middle of an event.

    It counts whole nanoseconds, as a real clock does. Each wait lasts one
    at least, so that time always goes on. A wait of a rounding error's
    length, added to a float, would leave the clock where it was."""

    def __init__(self):
        self._nanoseconds = 0
        self._planned = []      # [(nanoseconds, work)], in time order

    def now(self) -> float:
        return self._nanoseconds / 1e9

    def wait(self, condition, seconds: float):
        # Work planned meanwhile ends the wait early, as an action's notify
        # does on a real clock. The loop then looks again. Unlike a real
        # wait, this one keeps `condition` held. The planned work, such as
        # an action, takes it again, which the condition's reentrant lock
        # allows.
        nanoseconds = round(seconds * 1e9)
        if self._planned:
            nanoseconds = min(nanoseconds, self._planned[0][0] - self._nanoseconds)
        self._move_on(max(nanoseconds, 1))

    def at(self, moment: float, work):
        """Plans `work()` for when the clock reaches `moment`, in seconds."""
        self._planned.append((round(moment * 1e9), work))
        self._planned.sort(key=lambda planned: planned[0])

    def move(self, seconds: float):
        """Moves the clock on by `seconds`, doing the work planned meanwhile."""
        self._move_on(round(seconds * 1e9))

    def _move_on(self, nanoseconds: int):
        self._nanoseconds += nanoseconds
        while self._planned and self._planned[0][0] <= self._nanoseconds:
            self._planned.pop(0)[1]()


class CostedLiveSimulation(LiveSimulation):
    """A live simulation of `source_folder` on a ManualWallClock, `wall`.
    Each statement it runs costs `statement` seconds of it, and each drawing
    `drawing`. It keeps when each drawing began, in `drawings`. A stop or a
    failure, kept in `troubles`, ends it at once."""

    def __init__(self, source_folder, wall: ManualWallClock, statement: float,
                 drawing: float = 0.0):
        super().__init__(source_folder, notify=self._news, wall=wall)
        self.statement_cost, self.drawing_cost = statement, drawing
        self.drawings = []
        self.waves = []         # when the waveforms' points were sent on their own
        self.troubles = []

    def _news(self, kind: str, body):
        if kind == "drawing":
            self.drawings.append(self._wall.now())
            self._wall.move(self.drawing_cost)
        elif kind == "waves":
            self.waves.append(self._wall.now())
        elif kind in ("stopped", "failed"):
            self.troubles.append(body)
            self.end()

    def _watch(self, position: int, step):
        self._wall.move(self.statement_cost)
        super()._watch(position, step)


class PacingTest(SimulationTestCase):
    """How a live simulation shares its time, on a clock moved by hand. Each
    statement and each drawing costs a set time, so that these tests do not
    rest on how fast the machine runs."""

    def setUp(self):
        super().setUp()
        self.wall = ManualWallClock()

    def run_until(self, live: CostedLiveSimulation, moment: float):
        """Runs `live` on its thread until the clock reaches `moment`."""
        self.wall.at(moment, live.end)
        self.addCleanup(live.end)
        live.start(False)
        live._thread.join(_PATIENCE)
        self.assertFalse(live._thread.is_alive(), "the simulation did not end")
        self.assertEqual(live.troubles, [])

    def press_at(self, live: CostedLiveSimulation, moment: float) -> list:
        """Plans a press of "go" for `moment`. Returns a list of when it came
        and when its event ended, filled in as they happen."""
        times = []

        def press(simulation):
            simulation.press("go")
            times.append(self.wall.now())

        def come():
            times.append(moment)
            live.act(press)
        self.wall.at(moment, come)
        return times

    def long_event(self, live: CostedLiveSimulation) -> tuple:
        """Runs `live` on page0 with a button, "go", whose press runs a loop
        of a thousand turns, pressed at 1 second. Returns how long the event
        took, in seconds, and when each drawing during it began."""
        self.program("int turns=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0)], """\
on go.down:
  turns = 0
  while (turns < 1000) {
    turns = turns + 1
  }
""")
        times = self.press_at(live, 1)
        self.run_until(live, 20)
        self.assertEqual(len(times), 2, "the event did not end")
        came, ended = times
        return ended - came, [moment for moment in live.drawings if came <= moment < ended]

    def test_a_timer_slower_than_its_period_lets_presses_through(self):
        # Each tick takes longer than its period. A screen runs a late timer
        # once, not once for each period missed, so a press waits for one
        # tick at most. Running every tick missed instead, the simulation
        # would fall further behind at each catch-up, each several times
        # longer than the last: within a few presses, one waits for seconds.
        self.program("int count=0, turns=0, runs=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0), table("tick", "timer", tim=50)], """\
on go.down:
  count = count + 1

on tick.timer:
  runs = runs + 1
  turns = 0
  while (turns < 150) {
    turns = turns + 1
  }
""")
        live = CostedLiveSimulation(self.root, self.wall, statement=0.0005)
        presses = [self.press_at(live, 1.0 * number) for number in range(1, 7)]
        self.run_until(live, 7.5)
        # The ticks took more than twice their period, as this test needs.
        self.assertLess(live.simulation.globals["runs"], 7.5 / 0.100)
        for number, times in enumerate(presses, 1):
            self.assertEqual(len(times), 2, "press %d was not answered" % number)
            self.assertLess(times[1] - times[0], 0.5, "press %d" % number)

    def test_a_late_timer_runs_once_not_once_for_each_period_missed(self):
        # While each tick takes longer than its period, the simulation's time
        # falls behind the wall's. Once the ticks are quick again, they run
        # at their period: the periods missed are not run in a burst.
        self.program("int slow=1, turns=0, runs=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0), table("tick", "timer", tim=50)], """\
on go.down:
  slow = 0

on tick.timer:
  runs = runs + 1
  if (slow == 1) {
    turns = 0
    while (turns < 150) {
      turns = turns + 1
    }
  }
""")
        live = CostedLiveSimulation(self.root, self.wall, statement=0.0005)
        self.press_at(live, 5)
        runs = []
        for moment in (5, 6):
            self.wall.at(moment, lambda: runs.append(live.simulation.globals["runs"]))
        self.run_until(live, 7.5)
        # Before the press, the ticks took more than twice their period.
        self.assertLess(runs[0], 5 / 0.100)
        # After it, the tick already due runs at once, then one each period,
        # as on a screen.
        self.assertLessEqual(runs[1] - runs[0], 1 + 1.0 / 0.050)

    def test_a_long_event_is_drawn_as_it_runs(self):
        # Every LIVE_DRAWING seconds of its work, as the Editor's simulator
        # shows a long event drawing.
        live = CostedLiveSimulation(self.root, self.wall, statement=0.001)
        took, during = self.long_event(live)
        self.assertAlmostEqual(len(during), took / LIVE_DRAWING, delta=2)

    def test_a_slow_drawing_leaves_a_long_event_time_to_run(self):
        # Each drawing takes longer than the time between drawings in
        # progress. Timed from before each drawing, every statement would
        # draw, and the event would hardly go on. Timed from each drawing's
        # end instead, and at least as long apart as one takes, they leave
        # the event's own work half of its time at least. The check allows
        # one statement's cost of error.
        statement, drawing = 0.001, 2.5 * LIVE_DRAWING
        live = CostedLiveSimulation(self.root, self.wall, statement, drawing)
        took, during = self.long_event(live)
        work = took - len(during) * drawing
        self.assertGreater(len(during), 1)
        self.assertLessEqual(len(during) * drawing, work + statement)

    def test_a_generators_points_are_sent_alone_a_frame_apart_at_least(self):
        # A point every 2 ms, for a second: the points go on their own,
        # WAVES_PACE apart at least, and no drawing of the page is made.
        self.program("page page0\n")
        self.page("page0", [table("chart", "waveform", x=0, y=100, w=200, h=50, ch=1)])
        live = CostedLiveSimulation(self.root, self.wall, statement=0)
        feeding = generator_settings({"waveforms": [{"page": "page0", "waveform": "chart"}],
                                      "interval": 2, "channels": [{"channel": 0}]}, "test")
        self.wall.at(0.5, lambda: live.act(lambda simulation:
                                           simulation.start_generator(feeding)))
        self.run_until(live, 1.5)
        self.assertEqual([moment for moment in live.drawings if moment > 0.5], [])
        apart = [later - earlier for earlier, later in zip(live.waves, live.waves[1:])]
        self.assertGreater(len(live.waves), 40)
        self.assertGreaterEqual(min(apart), WAVES_PACE - 1e-9)
        # Each goes as soon as a tick comes once its pace allows.
        self.assertLess(max(apart), WAVES_PACE + 0.004)
        self.assertGreater(len(live.simulation.waves()["chart"][0]), 190)

    def test_a_waveform_generator_slower_than_its_interval_lets_presses_through(self):
        # Each tick of the generator takes three times its interval. Its
        # ticks take turns with the presses, as a timer's do, so a press
        # waits for one tick at most, and the points fall behind the clock.
        self.program("int count=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0),
                            table("chart", "waveform", x=0, y=100, w=200, h=50, ch=1)], """\
on go.down:
  count = count + 1
""")
        live = CostedLiveSimulation(self.root, self.wall, statement=0.0005)
        feeding = generator_settings({"waveforms": [{"page": "page0", "waveform": "chart"}],
                                      "interval": 1, "channels": [{"channel": 0}]}, "test")
        ticks = []
        tick = Simulation._generator_tick

        def costly_tick(simulation):
            ticks.append(self.wall.now())
            self.wall.move(0.003)
            tick(simulation)

        self.wall.at(0.5, lambda: live.act(lambda simulation:
                                           simulation.start_generator(feeding)))
        presses = [self.press_at(live, 1.0 * number) for number in range(1, 4)]
        with mock.patch.object(Simulation, "_generator_tick", autospec=True,
                               side_effect=costly_tick):
            self.run_until(live, 3.5)
        # The ticks fell behind their interval, as this test needs.
        self.assertGreater(len(ticks), 100)
        self.assertLess(len(ticks), 3.0 / 0.002)
        self.assertEqual(live.simulation.globals["count"], 3)
        for number, times in enumerate(presses, 1):
            self.assertEqual(len(times), 2, "press %d was not answered" % number)
            self.assertLess(times[1] - times[0], 0.01, "press %d" % number)


if __name__ == "__main__":
    unittest.main()
