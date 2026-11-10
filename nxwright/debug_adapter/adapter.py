"""The debug adapter: VS Code's debugger for a test and the screen code it runs.

It speaks the Debug Adapter Protocol (DAP): JSON messages over standard
input and output, framed as the Language Server Protocol's are
(framing.py). A launch names a test, by its folder and its
id as unittest writes it (`test_home.TargetTest.test_raise`). The adapter
runs that test in its own process, recording the lines of the test's own
Python (python_steps.py) and every run of screen code it makes
(testing/recording.py), then lets the debugger move through the recording
(replay.py):
  - breakpoints on lines of .nx files and of the test's Python files;
  - continue, step over, step into, step out, step back, and reverse
    continue, across the test's lines and the screen code its runs execute;
  - the stack of functions and events running, innermost first: the
    screen's, a label naming their run, then the test's;
  - the values, in groups: Locals, a Python function's locals, or an
    event's or function's under their nxlang names; Page, the components'
    values; Program, the `int` globals and system variables; Outside the
    page, what the machine records there; and Generated, the variables the
    compiler adds. At a line of Python, the screen's groups show what the
    last run left.
A test that fails, or stops with an error, stops the debugger where it did,
as on an exception: at a failing assertion, on the test's line; at an
error inside a run, on the screen statement. Moving past the recording's
last step ends the session. The test's own output and result go to the
Debug Console.

A launch that names a source folder rather than a test runs the app in a
simulation (testing/simulation.py), debugged while it runs (live.py): the
same requests, but moving forward past the present lets the simulation go
on. Its `sdCard0` and `sdCard1` name folders of the computer standing for
the screen's SD cards (testing/sd_cards.py). Its `pinyinTable` names the
screen's pinyin table, which the app's pinyin commands read: input.bin, or a
TFT file holding it; without one, the installed Nextion Editor's
(testing/pinyin_table.py). Its `serialPort`, {"name":
"COM4", "baud": 115200}, connects the screen's serial line to that port
(serial_port.py). Its `gpioInputs`, {"pio2": 0}, gives the GPIO inputs'
starting levels (testing/gpio_pins.py). Custom requests carry
what happens to the screen: "nxwright/press" at (x, y), "nxwright/move" to
(x, y) while pressed, "nxwright/release", "nxwright/serial" with an
instruction's text, "nxwright/startAgain", "nxwright/gpioInput",
setting a GPIO pin's level, {"pin": 2, "level": 0}, and "nxwright/gpioInputs",
setting several at the same moment, {"levels": {"pio2": 0, "pio5": 0}}; and
the serial port's settings: "nxwright/serialPorts" answers with the
computer's ports, the rates, and the port's state, and "nxwright/serialPort"
connects the port `name` at `baud`, or disconnects it when `name` is empty.

A real screen can be connected beside the simulation, on a port of its own
called the screen port. These requests act on it:
  - "nxwright/screenPort" connects the port `name` as the screen port, at
    `baud`, or disconnects the screen port when `name` is empty;
  - "nxwright/findScreen" finds the rate of the screen on the port `name`,
    then connects that port as the screen port at that rate;
  - "nxwright/serialPorts" also answers with the screen port's state, in
    `screen`, and whether the bridge runs, in `bridged`;
  - "nxwright/startScreenAgain" sends the screen `rest`, whether the bridge
    runs or not;
  - "nxwright/bridge" joins the MCU port to the screen port when `on` is
    true, so that a program on the MCU port talks to the real screen
    (bridge.py). If `simulator` is given too, the simulation also receives
    the program's bytes. `simulator` is "listens" if the screen answers the
    program, or "answers" if the simulation does. When `on` is false, it
    joins the MCU port back to the simulation;
  - "nxwright/serial" sends its instruction to each place that `to` lists,
    such as ["simulator", "screen"], or to the simulation alone when `to`
    is not given.
The log shows what the screen receives and sends in "SCR RECV:" and
"SCR SEND:" lines, beside the simulation's "SIM RECV:" and "SIM SEND:"
lines.

An agent drives a simulation through the extension, with the same requests
for what happens to the screen and three more arguments. Given `handled`,
one is answered once the simulation's thread has handled it, rather than
at once. One sent while the debugger holds the simulation stopped is
refused; one the debugger stops before or while handling it is answered
with why. A move another replaced is answered with it. Given `agent`, it is
an agent's, which `handled` must come with: while a serial port is
connected, it is refused unless also `allowed`, which the extension gives
once the user agreed, since what the app sends then reaches a device. An
agent's press or move is refused too when the screen cannot take it, as
a second press while one is held (looks.touch_refusal). An agent never
reaches the real screen. A "nxwright/serial" from an agent is refused if
its `to` includes the screen, and the log an agent reads leaves out the
screen's lines. An agent also looks at what the simulation holds (testing/looks.py):
"nxwright/screen", its text layout and, unless `picture` is false, a PNG
picture of it in base64, "nxwright/components", "nxwright/values", those
of `names` or all, and
"nxwright/log", the lines after the line numbered `after`. A look is
answered once the simulation's thread has taken it, at once while the
debugger holds it stopped.

Custom events carry what the simulator panel and side bar show: "nxwright/starting", as
each start of the app compiles its pages, with the number of the page
compiling, the page count, and the page's name, or no page once all are
compiled; "nxwright/drawing", with the page shown, its drawing, the files
of its pictures, and which start of the screen and which entry of the page
it belongs to; "nxwright/serialState", with the MCU port's state when it
changes, "nxwright/screenState", with the screen port's, and
"nxwright/bridgeState", with whether the bridge runs; and "nxwright/gpio",
with each GPIO pin's mode, bound component, and level, or none for a
screen without GPIO, at the start and whenever one changes. The log goes to
the Debug Console, as output events, each line with the simulation's time.
So do, as each start compiles, the pages and the full path of each of their
files.
"""
import base64
import contextlib
import io
from pathlib import Path
import sys
import threading
import traceback
import unittest

from nxwright import NxwrightError
from nxwright.debug_adapter.framing import read_message, write_message
from nxwright.debug_adapter.live import LiveSimulation
from nxwright.debug_adapter.python_steps import PythonTracer
from nxwright.debug_adapter.replay import Timeline, path_key
from nxwright.debug_adapter.bridge import Bridge
from nxwright.debug_adapter.serial_port import (RATES, REPLY_LENGTHS, LoggedPieces, SerialLink,
                                                port_names, screen_rate)
from nxwright.drawing.screen_pictures import ScreenPictures
from nxwright.project.device_settings import TextCodec
from nxwright.source.defines import LAUNCH_CONFIGURATION, launch_defines, overriding_defines
from nxwright.source.source_folder import read_app
from nxwright.testing import looks
from nxwright.testing.gpio_pins import checked_level, checked_levels, levels_by_name
from nxwright.testing.looks import value_group
from nxwright.testing.pinyin_table import installed_pinyin_table, read_pinyin_table
from nxwright.testing.sd_cards import card_folder
from nxwright.testing.simulation import read_eeprom_file
from nxwright.testing.simulation_log import END, log_format, shown, shown_instruction
from nxwright.testing.preview import Previews
from nxwright.testing.recording import PythonPlace, Recorder, recording

_SCOPES = ["Locals", "Page", "Program", "Outside the page", "Generated"]
_THREAD = 1
# Variable references at or past this one are a value's entries; below it,
# a scope of a frame: frame * 10 + its index in _SCOPES + 1.
_ENTRIES = 1_000_000
# What a request's handler returns when its reply comes later (_Reply).
_LATER = object()
# How the debugger stopped the simulation, as a refused action says it.
_STOPPED_HOW = {"breakpoint": "at a breakpoint", "step": "at a step", "pause": "paused",
                "exception": "on an error in the code", "entry": "at its start"}


class DebugAdapter:
    """Answers the debugger's messages, sending replies and events through
    `send(message)`. After disconnect, `finished` is True."""

    def __init__(self, send):
        self._send = send
        self._sequence = 0
        self.finished = False
        self._timeline = None
        self._position = 0
        self._failures = []          # [(position, message)] where the test stopped
        self._entries = []           # the entries of the values shown, by reference
        self._held = None            # events waiting for the reply being made, if any
        self._breakpoints = set()    # {(path_key, line)}
        self._by_file = {}           # {path_key: {lines}}, as the debugger last set them
        self._launched = self._configured = self._started = False
        self._stop_on_entry = True
        self._live = None            # the LiveSimulation of a simulation's session
        self._link = None            # its serial line's SerialLink, to the MCU
        self._screen_link = None     # the SerialLink of a real screen beside it
        self._screen_replies = None  # the LoggedPieces of what that screen sends
        # The LoggedPieces of what the MCU sends the screen, while bridged.
        self._mcu_instructions = None
        self._bridge = None          # the Bridge joining the MCU port to the screen, if any
        self._bridge_simulator = None  # while bridged: "listens", "answers", or None
        self._bridge_lock = threading.Lock()
        self._log_formats = None     # its log's forms, {"received": ..., "sent": ...}
        self._finding = False        # whether a screen's rate is being found
        self._finding_lock = threading.Lock()
        self._defines = {}           # its new values of app.toml's defines, {name: text}
        self._after = []             # what to do once the reply being made is sent
        self._emitting = threading.Lock()
        self._main_thread = threading.current_thread()
        self._previews = Previews()
        # The pictures of the simulation's screen an agent asks for, given
        # each drawing the panel gets (ScreenPictures); and a lock, as a
        # drawing may come from another thread than the look that asks.
        self._pictures = ScreenPictures()
        self._pictures_lock = threading.Lock()
        self._request = None         # the request being answered
        # The actions and looks whose replies wait, sent from the
        # simulation's thread, or from here as it stops or ends.
        self._waiting_replies = set()
        self._waiting_lock = threading.Lock()
        self._requests = {"initialize": self._initialize, "launch": self._launch,
                          "setBreakpoints": self._set_breakpoints,
                          "configurationDone": self._configuration_done,
                          "threads": self._threads, "stackTrace": self._stack_trace,
                          "scopes": self._scopes, "variables": self._variables,
                          "continue": self._continue, "reverseContinue": self._reverse_continue,
                          "next": self._next, "stepIn": self._step_in, "stepOut": self._step_out,
                          "stepBack": self._step_back, "pause": self._pause,
                          "disconnect": self._disconnect, "terminate": self._disconnect,
                          "nxwright/press": self._press, "nxwright/move": self._move,
                          "nxwright/release": self._release,
                          "nxwright/serial": self._serial,
                          "nxwright/startAgain": self._start_again,
                          "nxwright/gpioInput": self._gpio_input,
                          "nxwright/gpioInputs": self._gpio_inputs,
                          "nxwright/serialPorts": self._serial_ports,
                          "nxwright/serialPort": self._serial_port,
                          "nxwright/screenPort": self._screen_port,
                          "nxwright/findScreen": self._find_screen,
                          "nxwright/bridge": self._join_ports,
                          "nxwright/startScreenAgain": self._start_screen_again,
                          "nxwright/components": self._components,
                          "nxwright/values": self._values, "nxwright/log": self._log,
                          "nxwright/screen": self._screen}

    def handle(self, message: dict):
        """Answers one request. A mistake in answering it must not end the
        session: the reply says it failed, and the trace goes to standard error."""
        if message.get("type") != "request":
            return
        # A simulation's defines also apply to what this thread reads of the
        # folder. The simulation's own thread sets them in live.py.
        with overriding_defines(self._defines, LAUNCH_CONFIGURATION):
            self._answer(message)

    def _answer(self, message: dict):
        """Answers the request `message` (handle)."""
        # The protocol sends a request's reply before the events it causes,
        # such as the stop after a step, so those wait for the reply.
        self._held = []
        self._request = message
        handler = self._requests.get(message.get("command"))
        try:
            if handler is None:
                raise NxwrightError("the request %s is not supported" % message.get("command"))
            body = handler(message.get("arguments") or {})
        except NxwrightError as error:
            self._respond(message, False, message=str(error))
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            self._respond(message, False, message=str(error))
        else:
            if body is not _LATER:
                self._respond(message, True, body)
        held, self._held = self._held, None
        for event in held:
            self._emit(event)
        after, self._after = self._after, []
        for work in after:
            work()
        self._start_when_ready()

    def _respond(self, request: dict, success: bool, body: dict = None, message: str = None):
        reply = {"type": "response", "request_seq": request.get("seq"), "success": success,
                 "command": request.get("command"), "body": body or {}}
        if message is not None:
            reply["message"] = message
        self._emit(reply)

    def _event(self, event: str, body: dict = None):
        message = {"type": "event", "event": event, "body": body or {}}
        # Events of the simulation's thread go at once; those of a request
        # wait for its reply.
        if self._held is not None and threading.current_thread() is self._main_thread:
            self._held.append(message)
        else:
            self._emit(message)

    def _emit(self, message: dict):
        with self._emitting:
            self._sequence += 1
            self._send(dict(message, seq=self._sequence))

    def _initialize(self, arguments: dict) -> dict:
        self._event("initialized")
        return {"supportsConfigurationDoneRequest": True, "supportsStepBack": True}

    def _launch(self, arguments: dict) -> dict:
        if arguments.get("sourceFolder"):
            return self._launch_simulation(arguments)
        folder, test = arguments.get("testFolder"), arguments.get("test")
        if not folder or not test:
            raise NxwrightError("a launch names the test's folder (testFolder) and its id (test)")
        if arguments.get("defines") is not None:
            raise NxwrightError("defines is only for a simulation (sourceFolder): a test uses the "
                                "defaults of app.toml's [defines]")
        self._stop_on_entry = arguments.get("stopOnEntry", True)
        recorder = Recorder()
        output, self._failures = run_test(Path(folder), test, recorder)
        self._event("output", {"category": "console", "output": output})
        self._timeline = Timeline(recorder)
        self._launched = True
        return {}

    def _launch_simulation(self, arguments: dict) -> dict:
        """Prepares a simulation of the app of `sourceFolder`, from program.nx
        or from `page` with `values`, its EEPROM kept in the file `eeprom`,
        made when missing (simulation.read_eeprom_file), its
        serial line on the port `serialPort` names, its SD cards `sd0/` and
        `sd1/` the folders `sdCard0` and `sdCard1` name, if any, and its log
        showing what the screen receives and sends as `logReceived` and
        `logSent` say: text, hex, or both. Its pinyin table is the one
        `pinyinTable` names, which stops the launch when it holds none, or
        else the installed Nextion Editor's, if found. Its GPIO inputs start
        at the levels `gpioInputs` gives, as {"pio2": 0} (gpio_pins.py).
        `defines` gives app.toml's defines new values, as {"LIMIT": 40}."""
        source_folder = Path(arguments["sourceFolder"])
        defines = {}
        if arguments.get("defines") is not None:
            defines = launch_defines(arguments["defines"])
            # Read now, so that a name app.toml does not declare, or a value
            # of the wrong type, stops the launch rather than the simulation.
            with overriding_defines(defines, LAUNCH_CONFIGURATION):
                read_app(source_folder)
        port = arguments.get("serialPort")
        if port is not None:
            port = _port_settings(port)
        # Checked before anything starts: a folder that will not do stops the
        # launch, saying why.
        cards = {card: card_folder(arguments[setting])
                 for card, setting in (("sd0/", "sdCard0"), ("sd1/", "sdCard1"))
                 if arguments.get(setting) is not None}
        log_formats = {"received": log_format(arguments.get("logReceived", "text"), "logReceived"),
                       "sent": log_format(arguments.get("logSent", "hex"), "logSent")}
        pinyin_table = self._pinyin_table(arguments.get("pinyinTable"))
        inputs = arguments.get("gpioInputs")
        if inputs is not None:
            levels_by_name(inputs)
        # Last of the checks, as a missing file is made here.
        eeprom, eeprom_file = b"", None
        if arguments.get("eeprom"):
            eeprom_file = Path(arguments["eeprom"])
            eeprom, made = read_eeprom_file(eeprom_file)
            if made:
                self._event("output", {"category": "console",
                                       "output": "The EEPROM's file %s was made, holding an "
                                                 "empty EEPROM.\n" % eeprom_file})
        self._stop_on_entry = arguments.get("stopOnEntry", False)
        self._link = SerialLink(self._mcu_bytes, self._serial_news, "MCU port")
        self._screen_replies = LoggedPieces(self._screen_sent, REPLY_LENGTHS)
        self._mcu_instructions = LoggedPieces(self._screen_received, {})
        self._screen_link = SerialLink(self._screen_bytes, self._screen_news, "screen port")
        self._log_formats = log_formats
        self._defines = defines
        self._live = LiveSimulation(source_folder, arguments.get("page"),
                                    arguments.get("values"), eeprom, self._live_news,
                                    self._simulation_sends, cards, log_formats,
                                    eeprom_file=eeprom_file, pinyin_table=pinyin_table,
                                    inputs=inputs, defines=defines)
        # Connected before the app starts, so that what it sends first goes
        # out. Either way the side bar hears the port's state.
        if port is not None:
            self._link.connect(*port)
        else:
            self._event("nxwright/serialState", self._link.state())
        self._timeline = self._live.timeline
        self._position = None
        self._launched = True
        return {}

    def _pinyin_table(self, named):
        """Returns the simulation's pinyin table: the one `named` names, or
        else the installed Nextion Editor's, or None. One named that holds no
        table raises NxwrightError, which stops the launch. The installed
        one is found, not asked for: when it cannot be read, the Debug
        Console says why, and the simulation runs without it."""
        if named:
            return read_pinyin_table(Path(named))
        installed = installed_pinyin_table()
        if installed is None:
            return None
        try:
            return read_pinyin_table(installed)
        except NxwrightError as error:
            self._event("output", {"category": "console",
                                   "output": "The Nextion Editor's pinyin table was not read: "
                                             "%s.\n" % error})
            return None

    def _live_news(self, kind: str, body):
        """What the simulation's thread tells (LiveSimulation's `notify`)."""
        if kind == "stopped":
            self._position = body["position"]
            self._entries = []
            event = {"reason": body["reason"], "threadId": _THREAD, "allThreadsStopped": True}
            if body.get("description"):
                event["description"] = event["text"] = body["description"]
            self._event("stopped", event)
            for waiting in self._replies_waiting():
                waiting.interrupt(body["reason"], body.get("error"))
        elif kind == "starting":
            self._starting(body)
        elif kind == "drawing":
            simulation = body
            drawing = self._previews.simulation_drawing(simulation,
                                                        simulation.drawing_inputs())
            # Each drawing, so that a picture of a page without background
            # shows what it is drawn over, as the panel does. Nothing is
            # painted until a picture is asked for.
            with self._pictures_lock:
                self._pictures.shown(drawing)
            self._event("nxwright/drawing", drawing)
        elif kind == "log":
            self._event("output", {"category": "stdout",
                                   "output": "".join(_log_line(time, text)
                                                     for time, text in body)})
        elif kind == "gpio":
            self._event("nxwright/gpio", {"pins": body})
        elif kind == "failed":
            self._event("output", {"category": "stderr",
                                   "output": "The simulation could not start: %s\n" % body})
            self._event("terminated")
            self._end_replies_waiting()

    def _starting(self, progress):
        """Tells how far a start of the app has come, a StartProgress
        (testing/simulation.py): to the panel, and to the Debug Console, with
        the full path of each file about to compile on a line of its own."""
        self._event("nxwright/starting", {"number": progress.number, "count": progress.count,
                                          "page": progress.page})
        if progress.page is not None:
            heading = "Compiling page %d of %d: %s" % (progress.number, progress.count,
                                                       progress.page)
        elif progress.files:
            heading = "Compiling program.nx"
        else:
            return      # a start page was given: program.nx's code does not run
        lines = [heading] + ["    " + path for path in progress.files]
        self._event("output", {"category": "console",
                               "output": "".join(line + "\n" for line in lines)})

    def _set_breakpoints(self, arguments: dict) -> dict:
        lines = [breakpoint["line"] for breakpoint in arguments.get("breakpoints", [])]
        self._by_file[path_key(arguments["source"]["path"])] = set(lines)
        self._breakpoints = {(path, line) for path, file_lines in self._by_file.items()
                             for line in file_lines}
        if self._live is not None:
            self._live.breakpoints = self._breakpoints
        return {"breakpoints": [{"verified": True, "line": line} for line in lines]}

    def _configuration_done(self, arguments: dict) -> dict:
        self._configured = True
        return {}

    def _start_when_ready(self):
        """Stops at the session's first place, once launched and configured."""
        if self._started or not (self._launched and self._configured):
            return
        self._started = True
        if self._live is not None:
            # VS Code pauses only a thread it knows of: a simulation, which
            # need never stop, announces its own.
            self._event("thread", {"reason": "started", "threadId": _THREAD})
            self._live.breakpoints = self._breakpoints
            self._live.start(self._stop_on_entry)
            return
        if not len(self._timeline):
            self._event("output", {"category": "console",
                                   "output": "The test ran no code to step through.\n"})
            self._event("terminated")
            return
        if self._stop_on_entry:
            self._stop_at(0, "entry")
        else:
            self._position = -1     # before the first step, so that it can stop there
            self._continue({})

    def _threads(self, arguments: dict) -> dict:
        return {"threads": [{"id": _THREAD,
                             "name": "simulation" if self._live is not None else "test"}]}

    def _frames(self) -> list:
        """Returns the frames at the current step, innermost first: each a
        place, or the title of a run, which labels the screen's frames. A
        simulation paused before its first step has none."""
        if self._position is None:
            return []
        step = self._timeline.step(self._position)
        frames = list(reversed(step.frames))
        if step.run is not None:
            screen = sum(1 for place in frames if not isinstance(place, PythonPlace))
            frames.insert(screen, "run %s" % self._timeline.runs[step.run].title)
        return frames

    def _stack_trace(self, arguments: dict) -> dict:
        if self._position is None:
            return {"stackFrames": [], "totalFrames": 0}
        run = self._timeline.step(self._position).run
        frames = []
        for level, place in enumerate(self._frames()):
            if isinstance(place, str):
                frames.append({"id": level + 1, "name": place, "line": 0, "column": 0,
                               "presentationHint": "label"})
                continue
            frame = {"id": level + 1, "name": place.owner if place else "(added by the compiler)",
                     "line": place.line if place else 0, "column": 1}
            if place is not None:
                path = self._timeline.path_of(place, run)
                frame["source"] = {"name": Path(path).name, "path": path}
            frames.append(frame)
        return {"stackFrames": frames, "totalFrames": len(frames)}

    def _scopes(self, arguments: dict) -> dict:
        frame = arguments["frameId"]
        return {"scopes": [{"name": name, "variablesReference": frame * 10 + index + 1,
                            "expensive": name == "Generated"}
                           for index, name in enumerate(_SCOPES)]}

    def _variables(self, arguments: dict) -> dict:
        reference = arguments["variablesReference"]
        if reference >= _ENTRIES:
            entries = self._entries[reference - _ENTRIES]
            return {"variables": [{"name": key, "value": text, "variablesReference": 0}
                                  for key, text in entries]}
        frame, scope = divmod(reference - 1, 10)
        if self._position is None:
            return {"variables": []}
        if _SCOPES[scope] == "Locals":
            return {"variables": self._locals(frame)}
        values = self._timeline.values_at(self._position)
        run = self._timeline.run_shown_at(self._position)
        nxlang = run is not None and self._timeline.runs[run].nxlang
        shown = {name: value for name, value in values.items()
                 if value_group(name, nxlang) == _SCOPES[scope]}
        return {"variables": [{"name": name, "value": _shown(value), "variablesReference": 0}
                              for name, value in sorted(shown.items())]}

    def _locals(self, frame: int) -> list:
        """Returns the variables of a frame's locals: a Python function's, as
        recorded, or a screen event's or function's, under their nxlang names."""
        frames = self._frames()
        place = frames[frame - 1] if 0 < frame <= len(frames) else None
        if isinstance(place, PythonPlace):
            variables = []
            for name, text, entries in place.local_values:
                reference = 0
                if entries:
                    reference = _ENTRIES + len(self._entries)
                    self._entries.append(entries)
                variables.append({"name": name, "value": text, "variablesReference": reference})
            return variables
        if place is None or isinstance(place, str):
            return []
        step = self._timeline.step(self._position)
        values = self._timeline.values_at(self._position)
        names = self._timeline.runs[step.run].local_names.get(place.owner, {})
        return [{"name": name, "value": _shown(value), "variablesReference": 0}
                for name, value in sorted((name, values.get(variable))
                                          for variable, name in names.items())]

    def _continue(self, arguments: dict) -> dict:
        if self._live is not None:
            found = None
            if self._position is not None:
                self._timeline.catch_up()
                found = self._timeline.next_breakpoint(self._position, self._breakpoints)
            if found is not None:
                self._stop_at(found, "breakpoint")
            else:
                # Said too, for a continue VS Code did not ask for itself, as
                # the side bar's Resume.
                self._event("continued", {"threadId": _THREAD, "allThreadsContinued": True})
                self._after.append(self._live.resume)
            return {"allThreadsContinued": True}
        self._forward(self._timeline.next_breakpoint(self._position, self._breakpoints),
                      "breakpoint")
        return {"allThreadsContinued": True}

    def _live_step(self, into: bool = False, out: bool = False):
        """Steps forward in a simulation: through what was recorded, then on
        past the present, letting the simulation go on until the step ends."""
        start = self._position
        if start is None:
            self._after.append(lambda: self._live.resume(lambda position: True))
            return
        self._timeline.catch_up()
        found = self._timeline.next_line(start, into, out)
        if found is not None:
            self._stop_at(found, "step")
            return
        timeline = self._timeline
        self._after.append(lambda: self._live.resume(
            lambda position: timeline.step_stops(start, position, into, out)))

    def _reverse_continue(self, arguments: dict) -> dict:
        if self._live is not None:
            if self._position is not None:
                found = self._timeline.next_breakpoint(self._position, self._breakpoints,
                                                       backward=True)
                self._stop_at(self._timeline.first if found is None else found, "breakpoint")
            return {}
        found = self._timeline.next_breakpoint(self._position, self._breakpoints, backward=True)
        failed = [position for position, _ in self._failures if position < self._position]
        if failed and (found is None or failed[-1] > found):
            self._stop_at(failed[-1], "exception", self._failure_at(failed[-1]))
        elif found is not None:
            self._stop_at(found, "breakpoint")
        else:
            self._stop_at(0, "entry")
        return {}

    def _next(self, arguments: dict) -> dict:
        if self._live is not None:
            self._live_step()
        else:
            self._forward(self._timeline.next_line(self._position), "step")
        return {}

    def _step_in(self, arguments: dict) -> dict:
        if self._live is not None:
            self._live_step(into=True)
        else:
            self._forward(self._timeline.next_line(self._position, into=True), "step")
        return {}

    def _step_out(self, arguments: dict) -> dict:
        if self._live is not None:
            self._live_step(out=True)
        else:
            self._forward(self._timeline.next_line(self._position, out=True), "step")
        return {}

    def _step_back(self, arguments: dict) -> dict:
        if self._position is None:
            return {}
        found = self._timeline.previous_line(self._position)
        self._stop_at(self._timeline.first if found is None else found, "step")
        return {}

    def _pause(self, arguments: dict) -> dict:
        if self._live is not None:
            self._live.pause()
        return {}

    def _press(self, arguments: dict):
        """A press on the simulator's panel, at the page's pixel (x, y)."""
        x, y = int(arguments["x"]), int(arguments["y"])
        return self._action(arguments, lambda simulation: simulation.press(
            simulation.component_at(x, y), x, y),
            touch=lambda simulation: looks.touch_refusal(simulation, "press", x, y))

    def _move(self, arguments: dict):
        """The press moving on the panel. Only the latest move waiting counts."""
        x, y = int(arguments["x"]), int(arguments["y"])
        return self._action(arguments, lambda simulation: simulation.move(x, y), "move",
                            lambda simulation: looks.touch_refusal(simulation, "move", x, y))

    def _release(self, arguments: dict):
        return self._action(arguments, lambda simulation: simulation.release())

    def _serial(self, arguments: dict):
        """Sends the instruction `text` to the simulator, to the screen on
        the screen port, or to both, depending on `to`, such as
        ["simulator", "screen"]. Without `to`, the instruction goes to the
        simulator alone. The screen gets it first, because sending to the
        screen does not wait for the simulation's thread."""
        text = str(arguments["text"])
        to = _destinations(arguments.get("to"))
        self._simulation_only()
        if "simulator" in to:
            self._running_simulation()
        if "screen" in to:
            self._send_to_screen(text, arguments.get("agent") is True)
        if "simulator" not in to:
            return {}
        return self._action(arguments, lambda simulation: simulation.serial_input(text))

    def _start_screen_again(self, arguments: dict) -> dict:
        """Starts the screen on the screen port again by sending it `rest`.
        The Start the screen again button sends this request. While the
        bridge runs, the bridge sends `rest` (Bridge.start_screen_again), so
        that both ports follow the screen's rate, and the program on the MCU
        port receives the screen's start-up bytes. An agent never reaches the
        screen."""
        self._simulation_only()
        bridge = self._bridge
        if bridge is None:
            self._send_to_screen("rest", arguments.get("agent") is True)
            return {}
        if arguments.get("agent") is True:
            raise NxwrightError("an agent cannot start the real screen again. Only the user "
                                "can, from the Simulator section")
        self._screen_received(b"rest" + END)
        bridge.start_screen_again()
        return {}

    def _send_to_screen(self, text: str, agent: bool):
        """Writes the instruction `text` to the screen on the screen port, in
        the project's encoding, followed by FF FF FF, and logs it. An agent
        never reaches the screen: only the user sends it instructions."""
        if agent:
            raise NxwrightError("an agent cannot send instructions to the real screen on the "
                                "screen port. Only the user can, from the Simulator section")
        if not self._screen_link.state()["connected"]:
            raise NxwrightError("no screen is connected on the screen port")
        if self._bridge is not None:
            raise NxwrightError("the MCU port is joined to the screen, so only the program on "
                                "it sends the screen instructions")
        encoding = self._encoding()
        if encoding is None:
            raise NxwrightError("the app has not started yet, so the project's encoding is not "
                                "known: try again once it has")
        try:
            data = TextCodec(encoding).encode_keeping_bytes(text, "the instruction") + END
        except NxwrightError:
            self._log_output("SCR RECV: <nothing: instruction %r incompatible with project "
                             "encoding %s>" % (text, encoding))
            return
        # Logged first, as the screen may answer before the write returns.
        self._log_output("SCR RECV: %s" % shown_instruction(text, self._log_formats["received"],
                                                           encoding))
        problem = self._screen_link.send(data)
        if problem:
            self._log_output(problem, "console")

    def _start_again(self, arguments: dict):
        return self._action(arguments, lambda simulation: simulation.start_again())

    def _gpio_input(self, arguments: dict):
        """Sets the level outside the screen gives a GPIO pin, `pin` 0 to 7,
        `level` 0 or 1, in turn with the presses (Simulation.set_input)."""
        pin, level = arguments.get("pin"), arguments.get("level")
        checked_level(pin, level)
        return self._action(arguments, lambda simulation: simulation.set_input(pin, level))

    def _gpio_inputs(self, arguments: dict):
        """Sets the levels outside the screen gives several GPIO pins at the
        same moment, `levels` by name, {"pio2": 0, "pio5": 0}, as one action,
        so that nothing runs between them (Simulation.set_inputs)."""
        levels = checked_levels(levels_by_name(arguments.get("levels")))
        return self._action(arguments, lambda simulation: simulation.set_inputs(levels))

    def _action(self, arguments: dict, work, kind: str = None, touch=None):
        """Has the simulation's thread do `work(simulation)` in turn, a move
        (`kind`) replacing one still waiting. Answers at once, or, given
        `handled`, once the thread has handled it (_HandledAction). An
        agent's action (`agent`) must be handled, so that its reply can say
        whether it was done. An agent's touch is refused when
        `touch(simulation)` says why the screen cannot take it
        (looks.touch_refusal); the user's own touches on the panel are not
        checked. While the debugger holds the simulation stopped, a handled
        action is refused rather than left waiting."""
        live = self._running_simulation()
        handled, agent = arguments.get("handled") is True, arguments.get("agent") is True
        if agent and not handled:
            raise NxwrightError("an agent's action is answered once handled, so that the answer "
                                "says whether it was done: give `handled` too")
        reply = _Reply(self, self._request) if handled else None
        action = _HandledAction(work, reply, self._link, agent, arguments.get("allowed") is True,
                                self._reply_settled, touch if agent else None)
        if reply is not None:
            # Kept before the look at whether the simulation is stopped: a
            # stop told after that look still answers it (interrupt).
            self._wait_for_reply(action)
            if live.stopped:
                reply.send(error="the simulation is stopped in the debugger, so it handles no "
                                 "action until the debugger lets it go on")
                self._reply_settled(action)
                return _LATER
        # An agent's moves replace only each other: one refused, as while a
        # serial port is connected, never drops the user's own move with it.
        replaced = live.act(action, kind if kind is None or not agent else "agent " + kind)
        if isinstance(replaced, _HandledAction) and action.take_replies_of(replaced):
            self._wait_for_reply(action)
        if live.over:
            # The thread ended as the action was given: none will answer it.
            action.end()
        return _LATER if handled else {}

    def _components(self, arguments: dict):
        """The components of the page shown (looks.components)."""
        return self._look(lambda simulation: {"components": looks.components(simulation)})

    def _values(self, arguments: dict):
        """Values, those of `names` or all (looks.values)."""
        names = arguments.get("names")
        if names is not None and (not isinstance(names, list)
                                  or not all(isinstance(name, str) for name in names)):
            raise NxwrightError('values are asked for by their names, as {"names": ["t0.txt", '
                                '"sys0"]}')
        return self._look(lambda simulation: {"values": looks.values(simulation, names)})

    def _log(self, arguments: dict):
        """The log's lines after the line numbered `after`, 0 unless given
        (looks.log)."""
        after = arguments.get("after", 0)
        return self._look(lambda simulation: {"lines": looks.log(simulation, after)})

    def _screen(self, arguments: dict):
        """What the screen shows (looks.screen): its text layout, the page
        shown, and, unless `picture` is false, a PNG picture of it, in base64."""
        picture = arguments.get("picture", True)
        if not isinstance(picture, bool):
            raise NxwrightError("picture is true or false")

        def read(simulation):
            with self._pictures_lock:
                shown = looks.screen(simulation, self._previews, self._pictures, picture)
            if "png" in shown:
                shown["png"] = base64.b64encode(shown["png"]).decode("ascii")
            return shown
        return self._look(read)

    def _look(self, read):
        """Has the simulation's thread answer with `read(simulation)`, which
        changes nothing (LiveSimulation.look)."""
        live = self._running_simulation()
        look = _Look(read, _Reply(self, self._request), self._reply_settled)
        self._wait_for_reply(look)
        live.look(look)
        if live.over:
            # The thread ended as the look was given: none will take it.
            look.end()
        return _LATER

    def _wait_for_reply(self, waiting):
        with self._waiting_lock:
            self._waiting_replies.add(waiting)

    def _reply_settled(self, waiting):
        with self._waiting_lock:
            self._waiting_replies.discard(waiting)

    def _replies_waiting(self) -> list:
        with self._waiting_lock:
            return list(self._waiting_replies)

    def _end_replies_waiting(self):
        """Answers each action and look still waiting: the simulation ended."""
        for waiting in self._replies_waiting():
            waiting.end()

    def _serial_ports(self, arguments: dict) -> dict:
        """What the side bar offers: the computer's ports, the rates, and the
        state of the MCU port (`state`) and of the screen port (`screen`)."""
        self._simulation_only()
        return {"ports": port_names(), "rates": RATES, "state": self._link.state(),
                "screen": self._screen_link.state(), **self._bridge_state()}

    def _serial_port(self, arguments: dict) -> dict:
        """Connects the port `name` at `baud`, or disconnects when `name` is
        empty. Answers with the port's state."""
        self._simulation_only()
        if arguments.get("name"):
            self._refuse_while_joined()
            self._link.connect(*_port_settings(arguments))
        else:
            self._link.disconnect()
        return {"state": self._link.state()}

    def _screen_port(self, arguments: dict) -> dict:
        """Connects the screen port `name` at `baud`, or disconnects when
        `name` is empty. Connecting sends the screen nothing. Answers with
        the port's state."""
        self._simulation_only()
        if arguments.get("name"):
            self._refuse_while_joined()
            self._screen_link.connect(*_port_settings(arguments))
        else:
            self._screen_link.disconnect()
            self._screen_replies.stop()
        return {"state": self._screen_link.state()}

    def _find_screen(self, arguments: dict):
        """Finds the rate of the screen on the port `name`, by sending it
        `connect` at each rate (serial_port.screen_rate), then connects the
        screen port at that rate. It takes seconds, so it runs on its own
        thread, and answers with the port's state once done."""
        self._simulation_only()
        name = arguments.get("name")
        if not isinstance(name, str) or not name:
            raise NxwrightError("Find needs the name of the port the screen is on")
        self._refuse_while_joined()
        with self._finding_lock:
            if self._finding:
                raise NxwrightError("Find is already looking for a screen")
            self._finding = True
        reply = _Reply(self, self._request)

        def find():
            try:
                self._screen_link.find_and_connect(name, screen_rate)
                # The session ended while Find was looking for the screen.
                if self.finished:
                    self._screen_link.disconnect(quietly=True)
            finally:
                with self._finding_lock:
                    self._finding = False
                reply.send({"state": self._screen_link.state()})
        threading.Thread(target=find, name="finding the screen", daemon=True).start()
        return _LATER

    def _join_ports(self, arguments: dict) -> dict:
        """Joins the MCU port to the screen port when `on` is true (Bridge),
        or back to the simulation when it is false. If `simulator` is given
        too, the simulation also receives what the MCU sends. `simulator` is
        "listens" if the screen answers the MCU, or "answers" if the
        simulation does.
        Both ports must be connected to join them. Answers with the bridge's
        state (_bridge_state)."""
        self._simulation_only()
        on, simulator = arguments.get("on"), arguments.get("simulator")
        if not isinstance(on, bool):
            raise NxwrightError('`on` must be true or false, not %r' % (on,))
        if simulator not in (None, "listens", "answers"):
            raise NxwrightError('`simulator` must be "listens" or "answers", or not given, not %r'
                                % (simulator,))
        if not on:
            with self._bridge_lock:
                bridge, self._bridge = self._bridge, None
                self._bridge_simulator = None
            if bridge is not None:
                bridge.stop()
                self._mcu_instructions.stop()
                self._log_output("MCU port joined to the simulator again", "console")
                self._event("nxwright/bridgeState", self._bridge_state())
            return self._bridge_state()
        mcu, screen = self._link.state(), self._screen_link.state()
        if not (mcu["connected"] and screen["connected"]):
            raise NxwrightError("both the MCU port and the screen port must be connected "
                                "to join them")
        with self._bridge_lock:
            started = None
            if self._bridge is None:
                self._bridge = started = Bridge(
                    self._link, self._screen_link,
                    lambda line: self._log_output(line, "console"), self._bridge_ended,
                    screen_answers=simulator != "answers")
            else:
                self._bridge.set_screen_answers(simulator != "answers")
            self._bridge_simulator = simulator
        self._log_output("MCU port %s joined to %s" % (mcu["name"], _joined_to(screen["name"],
                                                                               simulator)),
                         "console")
        self._event("nxwright/bridgeState", self._bridge_state())
        if started is not None:
            started.start()
        return self._bridge_state()

    def _bridge_state(self) -> dict:
        """Returns whether the bridge runs (`bridged`), and what the simulation
        does meanwhile (`simulator`): "listens", "answers", or None if it
        takes no part."""
        bridged = self._bridge is not None
        return {"bridged": bridged, "simulator": self._bridge_simulator if bridged else None}

    def _refuse_while_joined(self):
        """Raises NxwrightError while the bridge joins the two ports, so that
        neither is connected again or changes its rate. The other port would
        keep its old rate, and the line would stop working with nothing in
        the log. Closing either port ends the bridge."""
        if self._bridge is not None:
            raise NxwrightError("the MCU port is joined to the screen: join it back to the "
                                "simulator, or close a port, before connecting one")

    def _bridge_ended(self, why: str):
        """Ends the bridge, closing both ports, for `why`: a write not taken
        in time, or a port that closed (Bridge's `ended`)."""
        with self._bridge_lock:
            bridge, self._bridge = self._bridge, None
            self._bridge_simulator = None
        if bridge is None:
            return
        bridge.stop()
        self._mcu_instructions.stop()
        self._log_output("the bridge ended, and closed both ports: %s" % why, "console")
        self._event("nxwright/bridgeState", self._bridge_state())
        self._link.disconnect()
        self._screen_link.disconnect()

    def _mcu_bytes(self, data: bytes):
        """Hands what arrives on the MCU port to the simulation's queue. While
        the bridge runs, the bytes go to the screen and to the log, and to the
        simulation only if it listens or answers."""
        bridge = self._bridge
        if bridge is not None:
            bridge.from_mcu(data)
            self._mcu_instructions.add(data)
            if self._bridge_simulator is None:
                return
        self._live.act(lambda simulation: simulation.serial_received(data))

    def _screen_bytes(self, data: bytes):
        """Logs what arrives on the screen port, and while the bridge runs,
        hands it to the MCU."""
        bridge = self._bridge
        if bridge is not None:
            bridge.from_screen(data)
        self._screen_replies.add(data)

    def _simulation_sends(self, data: bytes):
        """The simulation's `sending`: what it sends goes to the MCU port.
        While the bridge joins that port to the screen, it goes nowhere,
        unless the simulation answers the MCU in place of the screen."""
        if self._bridge is not None and self._bridge_simulator != "answers":
            return None
        return self._link.send(data)

    def _screen_received(self, instruction: bytes):
        """Logs an instruction that the MCU, or the Start the screen again
        button, sent to the screen through the bridge. It uses the form
        `logReceived` sets, or hexadecimal before the app has started."""
        encoding = self._encoding()
        form = self._log_formats["received"] if encoding is not None else "hex"
        self._log_output("SCR RECV: %s" % shown(instruction, form, encoding))

    def _screen_sent(self, reply: bytes):
        """Logs a reply from the screen on the screen port (LoggedPieces),
        in the form `logSent` sets. Before the app has started, the reply
        shows in hexadecimal, because the project's encoding is not known
        yet."""
        encoding = self._encoding()
        form = self._log_formats["sent"] if encoding is not None else "hex"
        self._log_output("SCR SEND: %s" % shown(reply, form, encoding))

    def _encoding(self):
        """Returns the project's encoding, or None before the app has started."""
        simulation = self._live.simulation if self._live is not None else None
        return simulation.encoding if simulation is not None else None

    def _serial_news(self, kind: str, body):
        """Handles a notice from the MCU port (SerialLink's `notify`), on any thread."""
        if kind == "state":
            self._event("nxwright/serialState", body)
            if not body["connected"] and self._bridge is not None:
                self._bridge_ended("MCU port %s closed" % body["name"])
        elif kind == "log":
            self._log_output(body, "console")

    def _screen_news(self, kind: str, body):
        """Handles a notice from the screen port (SerialLink's `notify`), on any
        thread."""
        if kind == "state":
            self._event("nxwright/screenState", body)
            if not body["connected"] and self._bridge is not None:
                self._bridge_ended("screen port %s closed" % body["name"])
        elif kind == "log":
            self._log_output(body, "console")

    def _log_output(self, line: str, category: str = "stdout"):
        """Writes `line` to the Debug Console, after the simulation's time, in
        the output category `category`. The log uses "stdout" for data that
        crosses a serial line, and "console" for what happens to a port, such
        as connecting or being lost."""
        simulation = self._live.simulation if self._live is not None else None
        time = simulation.clock if simulation is not None else 0
        self._event("output", {"category": category, "output": _log_line(time, line)})

    def _simulation_only(self) -> LiveSimulation:
        if self._live is None:
            raise NxwrightError("only a simulation takes what happens to the screen")
        return self._live

    def _running_simulation(self) -> LiveSimulation:
        """The simulation, refused once its thread has ended, as after a start
        that failed: what it is given would wait for an answer forever."""
        live = self._simulation_only()
        if live.over:
            raise NxwrightError("the simulation has ended")
        return live

    def _disconnect(self, arguments: dict) -> dict:
        if self._live is not None:
            self._live.end()
            with self._bridge_lock:
                bridge, self._bridge = self._bridge, None
            if bridge is not None:
                bridge.stop()
            self._link.disconnect(quietly=True)
            self._screen_link.disconnect(quietly=True)
            self._screen_replies.stop()
            self._mcu_instructions.stop()
        self._end_replies_waiting()
        self.finished = True
        return {}

    def _forward(self, target, reason: str):
        """Moves forward to `target`, a position or None for past the end.
        Where the test failed on the way, it stops there instead, as a
        debugger stops on an exception even while stepping over it. Past
        the end, the session ends."""
        failed = [position for position, _ in self._failures
                  if self._position < position and (target is None or position <= target)]
        if failed:
            self._stop_at(failed[0], "exception", self._failure_at(failed[0]))
        elif target is not None:
            self._stop_at(target, reason)
        else:
            self._event("terminated")

    def _failure_at(self, position: int) -> str:
        return next(message for failed, message in self._failures if failed == position)

    def _stop_at(self, position: int, reason: str, description: str = None):
        self._position = position
        self._entries = []
        body = {"reason": reason, "threadId": _THREAD, "allThreadsStopped": True}
        if description:
            body["description"] = body["text"] = description
        self._event("stopped", body)


class _Reply:
    """The reply to a request, sent once, from whichever thread sends it
    first: the simulation's, as it handles an action or takes a look, or the
    adapter's, as the simulation stops or ends."""

    def __init__(self, adapter: DebugAdapter, request: dict):
        self._adapter, self._request = adapter, request
        self._lock = threading.Lock()
        self._sent = False

    def send(self, body: dict = None, error: str = None):
        """Sends the reply: `body`, or the refusal `error`. A reply already
        sent is not sent again."""
        with self._lock:
            if self._sent:
                return
            self._sent = True
        self._adapter._respond(self._request, error is None, body, error)


class _HandledAction:
    """An action for the simulation's thread, with the replies that wait
    until it is handled: its own, when `reply` is given, and those of moves
    it replaced in the queue, which never run. An agent's action (`agent`)
    is refused while a serial port is connected, unless the user `allowed`
    the agent. It is refused too when `touch(simulation)` gives why the
    screen cannot take it. Both are checked on the thread, as the action is
    about to run, so that a port connected, or a press made, while it
    waited counts. `settled(self)` is called once no reply waits on it."""

    def __init__(self, work, reply, link, agent: bool, allowed: bool, settled, touch=None):
        self._work, self._link = work, link
        self._agent, self._allowed = agent, allowed
        self._settled = settled
        self._touch = touch
        self._lock = threading.Lock()
        self._replies = [] if reply is None else [reply]
        self._own = reply is not None
        self._started = self._finished = self._dropped = False
        self._refusal = None

    def __call__(self, simulation):
        with self._lock:
            if self._dropped:
                return
            self._started = True
        state = self._link.state()
        if self._agent and not self._allowed and state["connected"]:
            self._finish("the serial port %s is connected, so what the app sends reaches a "
                         "device, and the user has not allowed an agent to act on this "
                         "simulation" % state["name"])
            return
        refusal = self._touch(simulation) if self._touch is not None else None
        if refusal is not None:
            self._finish(refusal)
            return
        self._work(simulation)
        self._finish()

    def _finish(self, refusal: str = None):
        with self._lock:
            self._finished, self._refusal = True, refusal
            replies, self._replies = self._replies, []
        for reply in replies:
            reply.send(error=refusal)
        self._settled(self)

    def take_replies_of(self, replaced) -> bool:
        """Takes the replies of `replaced`, a move this one replaced in the
        queue. Returns whether any reply now waits on this one."""
        with replaced._lock:
            replies, replaced._replies = replaced._replies, []
        replaced._settled(replaced)
        with self._lock:
            if not self._finished:
                self._replies.extend(replies)
                return bool(self._replies)
            refusal = self._refusal
        for reply in replies:
            reply.send(error=refusal)
        return False

    def interrupt(self, reason: str, error: str = None):
        """The debugger stopped the simulation, for `reason`, as the stopped
        event gives it, such as "breakpoint": the replies are sent now,
        rather than once the user lets it go on. An agent's own action not
        yet begun is then not done at all. One begun finishes later, but for
        an error in its code, which ends it there: its reply gives `error`,
        the error in words, and that the simulation waits on the debugger."""
        with self._lock:
            if self._finished:
                return
            begun = self._started
            if not begun and self._own:
                self._dropped = True
            replies, self._replies = self._replies, []
        how = _STOPPED_HOW.get(reason, "stopped")
        if begun and reason == "exception":
            refusal = ("the simulation stopped on an error in the code while handling it, so "
                       "it goes no further: %s. It handles no action until the debugger lets "
                       "it go on" % error)
        elif begun:
            refusal = ("the simulation stopped in the debugger while handling it, %s; it "
                       "finishes once the debugger lets it go on" % how)
        else:
            refusal = ("the simulation stopped in the debugger, %s, before handling it, so it "
                       "was not done" % how)
        for reply in replies:
            reply.send(error=refusal)
        self._settled(self)

    def end(self):
        """The simulation ended before handling it."""
        with self._lock:
            self._dropped = True
            replies, self._replies = self._replies, []
        for reply in replies:
            reply.send(error="the simulation ended before handling it")
        self._settled(self)


class _Look:
    """A look at what the simulation holds, `read(simulation)`, sent as its
    reply. `settled(self)` is called once it is answered."""

    def __init__(self, read, reply: _Reply, settled):
        self._read, self._reply, self._settled = read, reply, settled

    def __call__(self, simulation):
        try:
            if simulation is None:
                raise NxwrightError("the app is still starting")
            body = self._read(simulation)
        except NxwrightError as error:
            self._reply.send(error=str(error))
        except Exception as error:
            traceback.print_exc(file=sys.stderr)
            self._reply.send(error="%s: %s" % (type(error).__name__, error))
        else:
            self._reply.send(body)
        self._settled(self)

    def interrupt(self, reason: str, error: str = None):
        """A look is taken while the simulation is stopped too: it waits on."""

    def end(self):
        self._reply.send(error="the simulation ended")
        self._settled(self)


class _StoppingResult(unittest.TextTestResult):
    """A test result that also keeps, for each failure or error, its
    exception and a one-line message: `stopped`, [(exception, message)]."""

    def __init__(self, *arguments, **keywords):
        super().__init__(*arguments, **keywords)
        self.stopped = []

    def addError(self, test, err):
        super().addError(test, err)
        self._note(err)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._note(err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._note(err)

    def _note(self, err):
        message = traceback.format_exception_only(err[0], err[1])[-1].strip()
        self.stopped.append((err[1], message))


def run_test(folder: Path, test: str, recorder: Recorder) -> tuple:
    """Runs the test `test` of the test folder `folder`, as `nxwright test`
    would, recording its runs and its Python lines into `recorder`. Returns
    what it printed and its result, and [(position, message)], where it
    failed or stopped with an error, in order. The folder is the top of the
    import path, so its modules import each other by name."""
    folder = folder.resolve()
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    output = io.StringIO()
    tracer = PythonTracer(recorder, folder)
    # The protocol owns standard output: what the test prints goes to the console.
    with contextlib.redirect_stdout(output):
        # Loaded before tracing, so that importing the test's module makes no steps.
        suite = unittest.TestLoader().loadTestsFromName(test)
        runner = unittest.TextTestRunner(stream=output, verbosity=2, resultclass=_StoppingResult)
        with recording(recorder), tracer.tracing():
            result = runner.run(suite)
    failures = []
    for exception, message in result.stopped:
        position = tracer.step_of(exception)
        if position is None:
            # It never reached the test's code: it stops at the last step, if any.
            position = len(recorder.steps) - 1
        if position >= 0:
            failures.append((position, message))
    return output.getvalue(), sorted(failures, key=lambda failure: failure[0])


def _shown(value) -> str:
    """Returns a value as the debugger shows it: text in quotation marks."""
    return '"%s"' % value.replace('"', '\\"') if isinstance(value, str) else repr(value)


def _log_line(time: int, text: str) -> str:
    """A line of the simulator's log, with the simulation's time in seconds."""
    return "%9.3f s  %s\n" % (time / 1000, text)


def _joined_to(screen: str, simulator) -> str:
    """Returns what the MCU port is joined to, for the log: the screen port
    `screen`, and also the simulator if `simulator` is not None
    (DebugAdapter._join_ports)."""
    if simulator is None:
        return "screen port %s" % screen
    return "screen port %s and to the simulator, with the %s answering" % (
        screen, "simulator" if simulator == "answers" else "screen")


def _destinations(to) -> set:
    """Returns where a typed instruction goes, from a request's `to`: a
    list of "simulator" and "screen", ["simulator"] when not given."""
    if to is None:
        return {"simulator"}
    if not isinstance(to, list) or not to or not set(to) <= {"simulator", "screen"}:
        raise NxwrightError('`to` must be ["simulator"], ["screen"], or ["simulator", '
                            '"screen"], not %r' % (to,))
    return set(to)


def _port_settings(settings) -> tuple:
    """Returns a serial port's (name, rate) from {"name": ..., "baud": ...},
    the rate optional."""
    if not isinstance(settings, dict) or not isinstance(settings.get("name"), str) or \
            not isinstance(settings.get("baud", 0), int):
        raise NxwrightError('a serial port is given as {"name": "COM4", "baud": 115200}')
    return settings["name"], settings.get("baud")


def serve(input_stream, output_stream) -> int:
    """Answers the debugger's messages read from the binary `input_stream`,
    writing to `output_stream`, until disconnect or the end of the input.
    Returns 0."""
    adapter = DebugAdapter(lambda message: write_message(output_stream, message))
    while not adapter.finished:
        message = read_message(input_stream)
        if message is None:
            break
        adapter.handle(message)
    return 0
