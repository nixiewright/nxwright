"""The simulator's running of an app (testing/simulation.py): program.nx,
pages and their changes, presses, timers, and the simulation's time."""
from collections import Counter
from datetime import datetime
import os
from pathlib import Path
import tomllib
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION, EDITOR_SYSTEM_VARIABLES
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.testing.preview import Previews
from nxwright.project.page_text import is_string_attribute
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.attribute_descriptions import code_cannot_change, describe
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.drawing.data_record_drawing import UNOPENED
from nxwright.source.device_keys import DEVICE_KEYS
from nxwright.drawing.number_drawing import number_text
from nxwright.drawing.page_drawing import DrawingResources, draw_page
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.source.page_source import Component
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import folder_reader, read_folder_source
from nxwright.testing import (SourceFolderRunner, editor_machine, folder_resources,
                              simulation as simulation_module)
from nxwright.testing.recording import Recorder, TrackedValues
from nxwright.testing.moves import STEP as MOVE_STEP
from nxwright.testing.opening_effects import STEP
from nxwright.testing.serial_line import MOST_WAITING
from nxwright.testing.screen_text import screen_text
from nxwright.testing.simulation import SYSTEM_START, Simulation, StartProgress
from tests.test_folder_check import FolderTestCase, edited_app, fonts_first
from tests.test_page_drawing import differing_pixels, screen_drawing
from tests.test_project_writer import edit_text
from tests.test_zi_font import gb2312_font, grid_font, utf8_fixture


def table(name: str, kind: str, **values) -> str:
    lines = ["[[component]]", 'name = "%s"' % name, 'type = "%s"' % kind]
    for key, value in values.items():
        lines.append("%s = %s" % (key, '"%s"' % value if isinstance(value, str) else value))
    return "\n".join(lines) + "\n"


def placed(name: str, kind: str, x: int, y: int, **values) -> str:
    return table(name, kind, x=x, y=y, w=100, h=50, **values)


def assert_recorded_alike(test: unittest.TestCase, actions):
    """Asserts that a recorded simulation of `test.root`, doing
    `actions(simulation)`, records the same steps whether a step compares
    only the names set or removed since the last and the values changed in
    place, as the recorder does, or every value."""
    def recorded(tracked) -> list:
        recorder = Recorder()
        with mock.patch.object(editor_machine, "TrackedValues", tracked), \
                mock.patch.object(simulation_module, "TrackedValues", tracked):
            actions(Simulation(test.root, recorder=recorder))
        return [(step.place, step.changes) for step in recorder.steps]
    everything = recorded(lambda values: dict(values))
    test.assertGreater(len(everything), 5)
    test.assertEqual(recorded(TrackedValues), everything)


class SimulationTestCase(FolderTestCase):
    """Two pages, "page0" and "second", written by each test."""

    def page(self, name: str, components: list, code: str = ""):
        head = ('[page]\nname = "%s"\ntype = "page"\nx = 0\ny = 0\nw = 800\nh = 480\n' % name)
        self.write("pages/%s.page.toml" % name, head + "".join("\n" + text for text in components))
        self.write("pages/%s.nx" % name, code)

    def program(self, code: str):
        """Writes program.nx: the declaration of sys0 to sys2, as `nxwright
        new` starts a program, then `code`."""
        self.write("program.nx", EDITOR_PROGRAM_DECLARATION + "\n" + code)

    def drawn_at(self, simulation: Simulation, name: str) -> tuple:
        """Where `simulation` draws its component `name`: its x and y, which
        differ from those code reads while it slides in as its page opens."""
        values = next(component for component in simulation.components()
                      if component.name == name).values
        return values["x"], values["y"]


class StartTest(SimulationTestCase):

    def test_a_run_is_named_after_the_app(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(name="Kitchen clock")))
        recorder = Recorder()
        Simulation(self.root, recorder=recorder)
        self.assertEqual(recorder.runs[0].title, "simulation of Kitchen clock")

    def test_the_system_variables_start_as_the_editors_simulator_showed(self):
        # Read in the Editor's simulator, on an Intelligent screen, and
        # scache, bcpu, tpdir, runmod, portbusy, tprc, and aph in a second
        # probe. Reading one the simulator lacked stopped the run.
        expected = dict({"usize": 0, "volume": 100, "appid": 0, "addr": 0, "audio0": 0,
                         "audio1": 0, "eql": 7, "eqm": 7, "eqh": 7, "scache": 0, "bcpu": 0,
                         "tpdir": 0, "runmod": 0, "portbusy": 0, "tprc": 0, "aph": 127},
                        **{"eq%d" % band: 7 for band in range(10)})
        globals_ = Simulation(self.root).globals
        self.assertEqual({name: globals_.get(name) for name in expected}, expected)

    def test_it_starts_only_the_editors_system_variables(self):
        self.assertLessEqual(set(SYSTEM_START), EDITOR_SYSTEM_VARIABLES)

    def test_dims_sets_dim_at_once(self):
        # dims sets the current backlight too, as the vendor's instruction
        # set says, and the Nextion Editor's simulator set it so. The panel is
        # dimmed by dim (debug_adapter/adapter.py).
        self.program("dims = 32\npage page0\n")
        simulation = Simulation(self.root)
        self.assertEqual((simulation.globals["dim"], simulation.globals["dims"]), (32, 32))

    def test_a_new_folder_sends_the_start_up_bytes_at_each_start(self):
        # The screen's start-up code and its "ready" come from a printh line
        # of program.nx, which a new folder has, as the Nextion Editor's new
        # project has. Since the Nextion Editor's version 1.65, the screen
        # does not send them itself (the vendor's instruction set).
        start_up = bytes.fromhex("00 00 00 ff ff ff 88 ff ff ff")
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.start_again()
        simulation.serial_input("rest")
        self.assertEqual(sent, [start_up] * 3)
        # A start page does not run program.nx's code.
        sent.clear()
        Simulation(self.root, start_page="second", sending=sent.append)
        self.assertEqual(sent, [])
        # Without the line, the screen sends nothing as it starts.
        self.program("page page0\n")
        sent.clear()
        Simulation(self.root, sending=sent.append)
        self.assertEqual(sent, [])

    def test_a_start_again_that_does_not_build_leaves_the_app_as_it_was(self):
        # An edit that does not build: the start again is refused, and the
        # app runs on as it was, until a start again that builds.
        self.program("int count=0\n\npage page0\n")
        self.page("page0", [placed("b0", "button", 0, 0)], "on b0.down:\n  count=count+1\n")
        self.page("second", [])
        simulation = Simulation(self.root)
        simulation.press("b0", 10, 10)
        simulation.release()
        simulation.advance(5000)

        def state():
            return (simulation.page, simulation.values(), list(simulation.log),
                    screen_text(simulation.drawing_inputs(), []), simulation.macros,
                    simulation.starts)

        before = state()
        self.write("pages/page0.nx", "on b0.down:\n  count=count+\n")
        with self.assertRaisesRegex(NxwrightError,
                                    "^pages/page0.nx line 2: the line ends too early$"):
            simulation.start_again()
        # The clock too: rtc0 to rtc6 are among the values.
        self.assertEqual(state(), before)
        simulation.press("b0", 10, 10)
        self.assertEqual(simulation.globals["count"], 2)
        simulation.release()
        self.write("pages/page0.nx", "on b0.down:\n  count=count+1\n")
        simulation.start_again()
        self.assertEqual(simulation.globals["count"], 0)

    def test_a_rest_whose_folder_does_not_build_stops_the_code(self):
        # `rest` reads the folder anew, as a start again does. When it no
        # longer builds, the code that ran `rest` stops with the refusal,
        # and the app is left as that code left it.
        self.program("int count=0\n\npage page0\n")
        self.page("page0", [placed("b0", "button", 0, 0)],
                  "on b0.down:\n  count=count+1\n  rest\n")
        self.page("second", [])
        simulation = Simulation(self.root)
        self.write("pages/second.nx", "on second.load:\n  count=count+\n")
        with self.assertRaisesRegex(NxwrightError, "pages/second.nx line 2"):
            simulation.press("b0", 10, 10)
        self.assertEqual((simulation.page, simulation.globals["count"]), ("page0", 1))
        self.assertIn("b0", screen_text(simulation.drawing_inputs(), []))
        self.assertNotIn("rest: the screen starts again", [line for _, line in simulation.log])

    def test_appid_is_kept_when_the_app_starts_again(self):
        # As a screen keeps it through a restart, so that program.nx may
        # open the page it gives. The Nextion Editor's simulator does not
        # keep it: there, appid reads 0 whatever code stores.
        self.program("page appid&0x000000FF\n")
        self.page("page0", [])
        self.page("second", [])
        simulation = Simulation(self.root)
        self.assertEqual(simulation.page, "page0")
        simulation.serial_input("appid=appid&0xFFFFFF00|1")
        simulation.start_again()
        self.assertEqual((simulation.page, simulation.globals["appid"]), ("second", 1))
        simulation.serial_input("appid=0x0100")
        simulation.serial_input("rest")
        self.assertEqual((simulation.page, simulation.globals["appid"]), ("page0", 0x0100))
        # A new simulation starts it at 0.
        self.assertEqual(Simulation(self.root).globals["appid"], 0)

    def test_appid_opens_its_page_from_nxlang_too(self):
        # nxlang passes a command's arguments on as written. The spaces by
        # their operators, which the Nextion Editor refuses, are dropped.
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(language="nxlang")))
        self.program("page appid & 0xFF\n")
        self.page("page0", [])
        self.page("second", [])
        simulation = Simulation(self.root)
        simulation.serial_input("appid=1")
        simulation.start_again()
        self.assertEqual(simulation.page, "second")

    def test_the_crc_starts_off(self):
        # crcval reads -1 until crcrest 1, as in a freshly started Nextion
        # Editor's simulator, at each start.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        self.assertEqual(simulation.globals["crcval"], -1)
        sent.clear()
        simulation.serial_input("crcrest 1,0x010000")
        self.assertEqual(sent, [bytes.fromhex("1a ff ff ff")])
        simulation.serial_input("crcrest 1,0xFFFF")
        self.assertEqual(simulation.globals["crcval"], 0xFFFF)
        simulation.start_again()
        self.assertEqual(simulation.globals["crcval"], -1)

    def test_each_file_is_parsed_twice_at_most(self):
        # Each page's compile needs every page's file, for the names its code
        # may use. Parsed again for each page, that work would grow with the
        # square of the number of pages. Each test's folder is new, so the
        # compile cache holds nothing of it yet.
        self.program("page page0\n")
        for name in ("page0", "second", "third"):
            self.page(name, [placed("title", "text", 0, 0, txt=name)])
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("third")))
        parsed = Counter()
        loads = tomllib.loads

        def counted(text, **keywords):
            parsed[text] += 1
            return loads(text, **keywords)

        with mock.patch.object(tomllib, "loads", counted):
            Simulation(self.root)
        self.assertEqual(len(parsed), 5)    # app.toml, defaults.toml, and the three pages'
        self.assertLessEqual(max(parsed.values()), 2)

    def test_tells_each_page_before_it_compiles_then_the_app(self):
        self.program('include "values.nx"\n\npage page0\n')
        self.write("values.nx", "const START = 1\n")
        self.page("page0", [], 'include "lib/shared.nx"\n')
        self.write("pages/lib/shared.nx", "const LIMIT = 3\n")
        told = []
        simulation = Simulation(self.root, starting=told.append)
        root = self.root.resolve()
        # A page's files come as code_files lists them: what it includes first.
        expected = [
            StartProgress(1, 2, "page0", [str(root / "pages/lib/shared.nx"),
                                          str(root / "pages/page0.nx")]),
            StartProgress(2, 2, "second", [str(root / "pages/second.nx")]),
            StartProgress(2, 2, None, [str(root / "program.nx"), str(root / "values.nx")])]
        self.assertEqual(told, expected)
        simulation.start_again()
        self.assertEqual(told, expected * 2)

    def test_a_start_page_runs_no_code_of_program_nx(self):
        self.program("page page0\n")
        told = []
        Simulation(self.root, start_page="second", starting=told.append)
        self.assertEqual((told[-1].page, told[-1].files), (None, []))


class PageLifeTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program("int count=0\n\nsys0 = 5\npage page0\n")
        self.page("page0", [placed("title", "text", 0, 0, txt="title"),
                            placed("go", "button", 0, 100),
                            placed("slot", "text", 0, 200, txt="page0 slot"),
                            placed("kept", "text", 200, 0, txt="kept", vscope=1)], """\
on page0.load:
  prints "l",0

on page0.unload:
  prints "U",0

on go.down:
  title.txt = "changed"
  kept.txt = "changed"
  prints "1",0
  page second
  prints "2",0
  slot.txt = "after"
""")
        self.page("second", [placed("title", "text", 0, 0, txt="second"),
                             placed("copy", "text", 0, 100, txt="?"),
                             placed("box", "text", 0, 200, txt="second box"),
                             placed("back", "button", 200, 0)], """\
on second.load:
  prints "L",0
  copy.txt = page0.kept.txt

on second.loadend:
  prints "E",0

on back.up:
  page page0
""")

    def test_the_recording_is_the_same_when_steps_compare_only_what_changed(self):
        # Page changes in the middle of events, with values kept and lost.
        assert_recorded_alike(self, lambda simulation: (
            simulation.press("go"), simulation.press("back"), simulation.press("go")))

    def test_a_global_component_stays_hidden_across_pages(self):
        # An app's screen in use on the hardware hides global buttons once,
        # and relies on them staying hidden after another page.
        simulation = Simulation(self.root)
        for text in ("vis kept,0", "vis title,0", "tsw kept,0"):
            simulation.serial_input(text)
        simulation.press("go")
        simulation.press("back")
        simulation.release()
        self.assertEqual(simulation.page, "page0")
        self.assertEqual(simulation.hidden(), {"kept"})          # title, local, shows again
        # kept still takes no touch: a press there goes to the page.
        self.assertEqual(simulation.component_at(210, 10), "page0")

    def test_vis_255_and_tsw_255_are_kept_by_each_global_component(self):
        # As the Nextion Editor's simulator ran it: back on page0 after
        # another page, the local components showed and took touches again,
        # and those of global scope kept what `vis 255,0` and `tsw 255,0` gave
        # them, as a named `vis` or `tsw` leaves them.
        simulation = Simulation(self.root)
        for text in ("vis 255,0", "page second", "page page0"):
            simulation.serial_input(text)
        self.assertEqual(simulation.hidden(), {"kept"})
        simulation = Simulation(self.root)
        for text in ("tsw 255,0", "page second", "page page0"):
            simulation.serial_input(text)
        simulation.press("kept")
        self.assertIsNone(simulation.pressed())
        simulation.press("title")
        self.assertEqual(simulation.pressed(), "title")

    def test_vis_255_and_tsw_255_on_another_page_leave_this_pages_globals(self):
        # As the Nextion Editor's simulator ran it: run on another page, they
        # left page0's components of global scope showing and taking touches.
        simulation = Simulation(self.root)
        for text in ("page second", "vis 255,0", "tsw 255,0", "page page0"):
            simulation.serial_input(text)
        self.assertEqual(simulation.hidden(), set())
        simulation.press("kept")
        self.assertEqual(simulation.pressed(), "kept")

    def test_an_event_a_typed_line_runs_is_recorded_as_a_press_is(self):
        # Each of its statements is a step, at which the debugger stops for
        # a breakpoint (debug_adapter/live.py). The typed line is no level of
        # its own: the event is the outermost frame.
        for name, act in (("pressed", lambda simulation: simulation.press("go")),
                          ("typed", lambda simulation: simulation.serial_input("click go,1"))):
            with self.subTest(name):
                recorder = Recorder()
                simulation = Simulation(self.root, recorder=recorder)
                before = len(recorder.steps)
                act(simulation)
                first = next(step for step in recorder.steps[before:]
                             if step.place.owner == "go.down")
                self.assertEqual([frame.owner for frame in first.frames], ["go.down"])

    def test_loading_while_the_new_page_load_event_runs(self):
        # Until its load event ends, the screen still shows the old page.
        seen = []
        recorder = Recorder()
        simulations = []
        recorder.watch = lambda position, step: seen.append(
            (step.place.owner, simulations[0].loading)) if simulations else None
        simulations.append(Simulation(self.root, recorder=recorder))
        simulations[0].press("go")
        self.assertEqual([entry for entry in seen if entry[0].startswith("second.")],
                         [("second.load", True), ("second.load", True), ("second.loadend", False)])
        self.assertFalse(simulations[0].loading)

    def test_starts_and_pages_entered(self):
        # A drawing is drawn over what follows from them: black after a
        # start, and the screen as it was for a page without background.
        simulation = Simulation(self.root)
        self.assertEqual((simulation.starts, simulation.entered), (1, 1))
        simulation.press("go")
        self.assertEqual((simulation.starts, simulation.entered), (1, 2))
        simulation.start_again()
        self.assertEqual((simulation.starts, simulation.entered), (2, 3))

    def test_the_page_left_is_shown_as_its_code_left_it(self):
        # Before a page changes, the screen still shows the page left, with
        # what its event changed: the next page may be drawn over it.
        seen = []
        simulations = []

        def leaving():
            simulation = simulations[0]
            seen.append((simulation.page, simulation.components()[1].values["txt"]))
        simulations.append(Simulation(self.root, leaving=leaving))
        self.assertEqual(seen, [])          # the first page leaves none
        simulations[0].press("go")
        self.assertEqual(seen, [("page0", "changed")])

    def test_a_page_named_by_a_value(self):
        # `page` takes a page's number from a variable, as a dialog going
        # back to the page that opened it does.
        self.page("page0", [placed("back", "button", 0, 0), table("returnPage", "variable")], """\
on back.down:
  returnPage.val = 1
  page returnPage.val
""")
        self.page("second", [])
        simulation = Simulation(self.root)
        simulation.press("back")
        self.assertEqual(simulation.page, "second")

    def test_a_page_named_by_an_expression(self):
        # Computed from left to right: the Nextion Editor's simulator opened
        # page 1 for `page sys0+1` with sys0 at 0. A number no page has
        # answers 0x03 and changes nothing, as it answered with sys0 at 4.
        self.page("second", [])
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        sent.clear()
        for line in ("sys0=4", "page sys0+1"):
            simulation.serial_input(line)
        self.assertEqual((simulation.page, sent), ("page0", [bytes.fromhex("03 ff ff ff")]))
        for line in ("sys0=0", "page sys0+1"):
            simulation.serial_input(line)
        self.assertEqual(simulation.page, "second")

    def test_program_nx_then_the_page_it_opens(self):
        simulation = Simulation(self.root)
        self.assertEqual((simulation.page, simulation.globals["sys0"]), ("page0", 5))
        self.assertEqual(simulation.globals["sent"], [("l", 0)])

    def test_a_page_change_in_the_middle_of_an_event(self):
        simulation = Simulation(self.root)
        simulation.press("go")
        self.assertEqual(simulation.page, "second")
        # The old page's unload, the new page's load and loadend, as the
        # Editor's simulator sent them; the rest of the event does not run.
        self.assertEqual([text for text, _ in simulation.globals["sent"]],
                         ["l", "1", "U", "L", "E"])
        values = simulation.values()
        self.assertEqual((values["box.txt"], values["copy.txt"]), ("second box", "changed"))

    def test_local_components_start_again_and_global_ones_keep(self):
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.press("back")
        simulation.release()
        values = simulation.values()
        self.assertEqual((simulation.page, values["title.txt"], values["kept.txt"]),
                         ("page0", "title", "changed"))

    def test_a_release_after_a_page_change_runs_nothing(self):
        # go's press opens second, which has a "title" too: it is not released.
        self.write("pages/second.nx", self.text("pages/second.nx") +
                   "\non title.up:\n  prints \"released\",0\n")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.release()
        self.assertNotIn(("released", 0), simulation.globals["sent"])

    def test_serial_input_before_any_page(self):
        self.program("int count=0\n")
        simulation = Simulation(self.root)
        simulation.serial_input("count=4")
        self.assertEqual((simulation.page, simulation.globals["count"]), (None, 4))

    def test_a_start_page_with_values(self):
        simulation = Simulation(self.root, "second", {"page0.kept.txt": "given", "count": 3})
        values = simulation.values()
        self.assertEqual((values["copy.txt"], values["count"]), ("given", 3))
        self.assertEqual(simulation.globals["sys0"], 0)

    def test_where_a_press_lands(self):
        simulation = Simulation(self.root)
        self.assertEqual(simulation.component_at(10, 110), "go")
        self.assertEqual(simulation.component_at(500, 400), "page0")
        simulation.fields["page0"]["vis go"] = 0
        self.assertEqual(simulation.component_at(10, 110), "page0")
        simulation.fields["page0"]["vis go"] = 1
        # A component whose touches are off still takes the press, which
        # then runs nothing (TouchCaptureTest).
        simulation.fields["page0"]["touch 255"] = 0
        self.assertEqual(simulation.component_at(10, 110), "go")


class KeyboardTest(SimulationTestCase):
    """A text bound to the keypad (`key` 2), and the keypad: a page whose
    page file says it is the system page "keypad", reading and writing its
    caller's field by the page number and component ID the screen gives it."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("field", "text", 0, 0, txt="1.25", key=2, vscope=1),
                            placed("edit", "button", 0, 100)], """\
on edit.down:
  field.txt = "2.5"
  click field,0
""")
        self.write("pages/keypad.page.toml", '[page]\nname = "keypad"\ntype = "page"\n'
                   'system_page = "keypad"\nx = 0\ny = 0\nw = 800\nh = 480\n\n'
                   + table("loadpageid", "variable", vscope=1) + "\n"
                   + table("loadcmpid", "variable", vscope=1) + "\n"
                   + placed("show", "text", 0, 0, txt="") + "\n"
                   + placed("ok", "button", 0, 100) + "\n"
                   + table("kind", "variable") + "\n"
                   + table("byName", "variable", sta=1))
        self.write("pages/keypad.nx", """\
on keypad.load:
  show.txt = p[loadpageid.val].b[loadcmpid.val].txt
  kind.val = p[loadpageid.val].b[loadcmpid.val].type
  byName.txt = p[0].field.txt

on ok.down:
  p[loadpageid.val].b[loadcmpid.val].txt = "7"
  page loadpageid.val
""")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("keypad")))

    def test_a_bound_field_whose_touches_are_off_opens_no_keyboard(self):
        simulation = Simulation(self.root)
        simulation.serial_input("tsw field,0")
        simulation.press("field")
        simulation.release()
        self.assertEqual(simulation.page, "page0")

    def test_a_click_on_a_bound_field_opens_its_keyboard(self):
        simulation = Simulation(self.root)
        simulation.press("edit")
        self.assertEqual(simulation.page, "keypad")
        values = simulation.values()
        # The caller's page number and the field's ID, which the keypad reads
        # the field by: its text, and its type, a text's 116.
        self.assertEqual((values["loadpageid.val"], values["loadcmpid.val"]), (0, 1))
        self.assertEqual((values["show.txt"], values["kind.val"]), ("2.5", 116))
        # A page's index with a component's name, as the vendor's p[dp].n0.val.
        self.assertEqual(values["byName.txt"], "2.5")
        simulation.press("ok")
        self.assertEqual((simulation.page, simulation.values()["field.txt"]), ("page0", "7"))

    def test_a_component_of_the_page_shown_by_its_id(self):
        simulation = Simulation(self.root)
        simulation.serial_input('b[1].txt="by id"')
        self.assertEqual(simulation.values()["field.txt"], "by id")

    def test_a_tap_on_a_bound_field_opens_its_keyboard(self):
        simulation = Simulation(self.root)
        simulation.press("field")
        self.assertEqual(simulation.page, "page0")      # on its release
        simulation.release()
        self.assertEqual((simulation.page, simulation.values()["show.txt"]), ("keypad", "1.25"))

    def test_the_two_other_stock_keyboards(self):
        # The Editor marks its speed dial keyboard 3 and its Chinese input 4,
        # the `key` that opens each.
        page0, keypad = self.root / "pages/page0.page.toml", self.root / "pages/keypad.page.toml"
        originals = {path: path.read_text(encoding="utf-8") for path in (page0, keypad)}
        for key, system_page in ((3, "speed-dial"), (4, "chinese-input")):
            with self.subTest(system_page=system_page):
                try:
                    edit_text(page0, "key = 2", "key = %d" % key)
                    edit_text(keypad, 'system_page = "keypad"', 'system_page = "%s"' % system_page)
                    simulation = Simulation(self.root)
                    simulation.press("field")
                    simulation.release()
                    self.assertEqual((simulation.page, simulation.values()["show.txt"]),
                                     ("keypad", "1.25"))
                finally:
                    for path, text in originals.items():
                        path.write_text(text, encoding="utf-8", newline="\n")


class DrawingCommandsTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("sample", "text", 0, 0, txt="sample"),
                            placed("paint", "button", 0, 100),
                            placed("change", "button", 0, 200),
                            placed("away", "button", 0, 300),
                            table("count", "variable")], """\
on paint.down:
  fill 0,0,50,50,RED
  vis sample,0

on change.down:
  sample.txt = "new"
  count.val = 3
  vis sample,1

on away.down:
  page second
""")
        self.page("second", [])

    def test_what_is_painted_and_drawn_again(self):
        simulation = Simulation(self.root)
        simulation.press("paint")
        # The button pressed is drawn again, then its event paints.
        self.assertEqual(simulation.painted(), [("redraw", "paint"), ("fill", 0, 0, 50, 50, 63488)])
        self.assertEqual(simulation.hidden(), {"sample"})
        simulation.release()
        simulation.press("change")
        # A variable, with no place, is not drawn again; and sample's two
        # changes draw it again once.
        self.assertEqual(simulation.painted()[2:], [("redraw", "paint"), ("redraw", "change"),
                                                    ("redraw", "sample")])
        self.assertEqual(simulation.components()[1].values["txt"], "new")

    def test_a_component_moved_leaves_its_old_place(self):
        # The page's background comes back where a component that code moved
        # or resized was, as the Editor's simulator drew it (fixtures/
        # drawing-assumptions/, page31 and page33). The first `x` comes from
        # the page file, code never having set it.
        simulation = Simulation(self.root)
        simulation.serial_input("sample.x=50")
        simulation.serial_input("sample.y=40")
        left = [("left", "sample", (0, 0, 100, 50)), ("left", "sample", (50, 0, 100, 50))]
        self.assertEqual(simulation.painted(), left + [("redraw", "sample")])
        # None for the place it holds, another attribute, or a component
        # hidden or with no place.
        for line in ("sample.x=50", 'sample.txt="moved"', "count.val=4", "vis sample,0",
                     "sample.x=0"):
            simulation.serial_input(line)
        self.assertEqual([entry for entry in simulation.painted() if entry[0] == "left"], left)

    def test_a_component_sliding_in_leaves_no_place(self):
        # It is drawn where its opening effect slides it, not at its `x`. The
        # slide's end puts its `x` back.
        self.page("second", [placed("slid", "text", 0, 0, effect=1, time=1000)])
        simulation = Simulation(self.root)
        simulation.serial_input("page second")
        simulation.serial_input("slid.x=50")
        self.assertEqual([entry for entry in simulation.painted() if entry[0] == "left"], [])
        simulation.advance(1000)
        simulation.serial_input("slid.x=60")
        self.assertEqual([entry for entry in simulation.painted() if entry[0] == "left"],
                         [("left", "slid", (0, 0, 100, 50))])

    def test_what_no_longer_shows_is_forgotten(self):
        fill = ("fill", 0, 0, 5, 5, 0)
        for painted, kept in (
                ([fill, ("redraw", "a"), ("redraw", "b"), ("redraw", "a")],
                 [fill, ("redraw", "b"), ("redraw", "a")]),
                ([fill, ("redraw", "a"), fill, ("redraw", "a")],
                 [fill, ("redraw", "a"), fill, ("redraw", "a")]),
                ([fill, ("cls", 0), fill], [("cls", 0), fill]),
                ([fill, ("redraw", "page0"), fill], [fill]),
                ([fill, ("ref", "0")], []),
                # Stopped: the marks wait, in order, and the stop is kept.
                ([fill, ("ref_stop",), ("redraw", "a"), ("redraw", "b"), ("redraw", "a")],
                 [fill, ("ref_stop",), ("redraw", "a"), ("redraw", "b"), ("redraw", "a")]),
                ([fill, ("ref_stop",), ("redraw", "page0"), fill],
                 [fill, ("ref_stop",), ("redraw", "page0"), fill]),
                ([fill, ("ref_stop",), ("ref", "page0"), ("redraw", "a")],
                 [("ref_stop",), ("redraw", "a")]),
                ([("ref_stop",), ("redraw", "t0"), ("redraw", "t1"), ("redraw", "t0"), ("cls", 0)],
                 [("ref_stop",), ("redraw", "t0"), ("redraw", "t1"), ("cls", 0)]),
                # Moved twice: both places it left get the background back.
                ([fill, ("left", "a", (0, 0, 9, 9)), ("redraw", "a"),
                  ("left", "a", (5, 0, 9, 9)), ("redraw", "a")],
                 [fill, ("left", "a", (0, 0, 9, 9)), ("left", "a", (5, 0, 9, 9)),
                  ("redraw", "a")]),
                # Moved away from one place twice: it gets it back once.
                ([fill, ("left", "a", (0, 0, 9, 9)), ("redraw", "a"),
                  ("left", "a", (0, 0, 9, 9)), ("redraw", "a")],
                 [fill, ("left", "a", (0, 0, 9, 9)), ("redraw", "a")]),
                # A place left waits on a stop a cls cuts, as the marks do.
                ([("ref_stop",), ("left", "a", (0, 0, 9, 9)), ("redraw", "a"), ("cls", 0)],
                 [("ref_stop",), ("left", "a", (0, 0, 9, 9)), ("redraw", "a"), ("cls", 0)])):
            with self.subTest(painted=painted):
                self.assertEqual(simulation_module._compacted(painted, "page0"), kept)

    def test_records_keep_their_last_entries(self):
        simulation = Simulation(self.root)
        simulation.globals["sent"] = [("x", 0)] * 300
        simulation.press("change")
        self.assertEqual(len(simulation.globals["sent"]), simulation_module._MOST_KEPT)

    def test_every_component_at_once_then_one(self):
        simulation = Simulation(self.root)
        every = {"sample", "paint", "change", "away", "count"}
        for text, hidden, pressed in (("vis 255,0", every, "page0"),
                                      ("vis paint,1", every - {"paint"}, "paint"),
                                      ("vis 255,1", set(), "paint"),
                                      # Its touches off, it still takes the press.
                                      ("tsw paint,0", set(), "paint"),
                                      ("tsw 255,1", set(), "paint")):
            with self.subTest(text=text):
                simulation.serial_input(text)
                self.assertEqual(simulation.hidden(), hidden)
                self.assertEqual(simulation.component_at(10, 110), pressed)

    def test_the_button_held_down(self):
        simulation = Simulation(self.root)
        simulation.press("change")
        self.assertEqual(simulation.pressed(), "change")
        simulation.release()
        self.assertIsNone(simulation.pressed())
        # A press that changes page leaves nothing held on the new page.
        simulation.press("away")
        self.assertIsNone(simulation.pressed())

    def test_a_new_page_clears_what_was_painted(self):
        simulation = Simulation(self.root)
        simulation.press("paint")
        simulation.press("away")
        self.assertEqual((simulation.page, simulation.painted()), ("second", []))

    def test_the_page_is_drawn_once_its_load_event_ends(self):
        # The page is drawn over what its load event painted or changed. What
        # its loadend event changes is drawn again over the page.
        self.page("second", [placed("early", "text", 0, 0), placed("late", "text", 0, 100)], """\
on second.load:
  fill 0,0,50,50,RED
  early.pco = 5

on second.loadend:
  late.pco = 5
""")
        simulation = Simulation(self.root)
        simulation.press("away")
        self.assertEqual(simulation.painted(), [("redraw", "late")])
        # The same for the page the app starts on.
        self.assertEqual(Simulation(self.root, "second").painted(), [("redraw", "late")])


class SliderAndWaveformTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program("int seen=0, slides=0\n\npage page0\n")
        self.page("page0", [table("level", "slider", x=0, y=0, w=200, h=40, wid=20, hig=20,
                                  val=0, minval=0, maxval=100),
                            table("chart", "waveform", x=0, y=100, w=4, h=50, ch=2),
                            placed("plot", "button", 300, 0),
                            table("wide", "slider", x=100, y=300, w=400, h=40, val=0)], """\
on level.slide:
  seen = level.val
  slides = slides + 1

on level.up:
  seen = seen + 1000

on plot.down:
  add chart.id,0,10
  add chart.id,0,20
  add chart.id,1,5
  add chart.id,0,30
  add chart.id,0,40
  add chart.id,0,50
""")
        self.page("second", [])

    def test_dragging_a_slider(self):
        simulation = Simulation(self.root)
        # The knob's middle goes under the pointer: 10 pixels in, 180 of travel.
        simulation.press("level", 100, 20)
        self.assertEqual(simulation.values()["level.val"], 50)
        simulation.move(190, 20)
        simulation.move(190, 25)        # no change of value: no slide event
        simulation.move(500, 20)        # past the end: the end
        self.assertEqual((simulation.values()["level.val"], simulation.globals["slides"]),
                         (100, 1))
        simulation.release()
        self.assertEqual(simulation.globals["seen"], 1100)

    def test_a_slider_whose_touches_are_off_does_not_move(self):
        simulation = Simulation(self.root)
        simulation.serial_input("tsw level,0")
        simulation.press("level", 100, 20)
        simulation.move(190, 20)
        simulation.release()
        self.assertEqual((simulation.values()["level.val"], simulation.globals["slides"],
                          simulation.globals["seen"]), (0, 0, 0))

    def test_a_press_puts_the_knob_where_the_editors_simulator_does(self):
        # Its round knob as wide as the slider is high, 40: the Editor's
        # simulator gave 78 for this press too (tools/editor/README.md).
        simulation = Simulation(self.root)
        simulation.press("wide", 400, 320)
        self.assertEqual(simulation.values()["wide.val"], 78)

    def test_a_waveforms_points(self):
        simulation = Simulation(self.root)
        simulation.press("plot", 300, 0)
        # Four columns wide: channel 0 keeps its latest four.
        self.assertEqual(simulation.waves(), {"chart": {0: [20, 30, 40, 50], 1: [5]}})
        # The points are kept apart: the record, which the recorder would
        # copy at each step, stays empty.
        self.assertEqual(simulation.globals["waveform"], [])
        simulation.serial_input("cle chart.id,0")
        self.assertEqual(simulation.waves(), {"chart": {1: [5]}})


class SliderPressTest(SimulationTestCase):
    """Presses on sliders whose `maxval` is 1000, so that a pixel moves
    `val` by about 5, each giving the `val` the Nextion Editor's simulator
    gave for it."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        across = dict(x=100, w=241, h=26, val=0, maxval=1000)
        upright = dict(y=20, h=241, val=0, maxval=1000, mode=1)
        self.page("page0", [table("round26", "slider", y=20, **across),
                            table("square26", "slider", y=70, psta=2, **across),
                            table("round25", "slider", y=120, **dict(across, h=25)),
                            table("upRound41", "slider", x=400, w=41, **upright),
                            table("upRound40", "slider", x=450, w=40, **upright),
                            table("upRound26", "slider", x=500, w=26, **upright),
                            table("upSquare40", "slider", x=550, w=40, psta=2, **upright)])
        self.page("second", [])

    def test_a_round_knob_of_an_even_size_counts_one_less(self):
        # A knob 26 long, round, travels 216 pixels, as one 25 long does.
        # A square one travels 215.
        presses = [("round26", 213, 33, 468), ("square26", 213, 83, 465),
                   ("round25", 213, 132, 468)]
        self.assert_presses(presses)

    def test_an_upright_slider_counts_from_its_bottom_row(self):
        presses = [("upRound41", 420, 141, 495), ("upRound41", 420, 61, 895),
                   ("upRound41", 420, 221, 95), ("upRound40", 470, 141, 495),
                   ("upRound26", 513, 141, 495), ("upSquare40", 570, 141, 493)]
        self.assert_presses(presses)

    def assert_presses(self, presses: list):
        for name, x, y, value in presses:
            with self.subTest(slider=name, x=x, y=y):
                simulation = Simulation(self.root)
                simulation.press(name, x, y)
                simulation.release()
                self.assertEqual(simulation.values()[name + ".val"], value)


class KnobAtThePressTest(SimulationTestCase):
    """A slider's knob after a press, as the Nextion Editor's simulator drew
    it: centred under the touch, its round knob 40 drawn 39, until code stores
    its `val`. scrolled() gives the knob's start along the track, from its
    start, or its bottom when upright."""

    def setUp(self):
        super().setUp()
        self.program("int slides=0\n\npage page0\n")
        self.page("page0", [table("s40", "slider", x=10, y=20, w=400, h=40, val=50),
                            table("sv", "slider", x=600, y=20, w=40, h=400, mode=1, val=50)],
                  "on s40.slide:\n  slides=slides+1\n")
        self.page("second", [])

    def pressed(self, name: str, x: int, y: int) -> Simulation:
        simulation = Simulation(self.root)
        simulation.press(name, x, y)
        simulation.release()
        return simulation

    def test_the_knob_stays_under_the_press_until_code_stores_val(self):
        # From x 81, where val 20 would place it from x 82.
        simulation = self.pressed("s40", 100, 40)
        self.assertEqual((simulation.scrolled()["s40"], simulation.values()["s40.val"]), (71, 20))
        simulation.serial_input("ref s40")
        self.assertEqual(simulation.scrolled()["s40"], 71)
        simulation.serial_input("s40.val=s40.val")
        self.assertNotIn("s40", simulation.scrolled())

    def test_an_upright_knob_counts_from_the_bottom(self):
        # Its top at y 81, under a press at y 100.
        self.assertEqual(self.pressed("sv", 620, 100).scrolled()["sv"], 400 - 39 - (81 - 20))

    def test_the_knob_stays_on_the_track(self):
        self.assertEqual(self.pressed("s40", 15, 40).scrolled()["s40"], 0)
        self.assertEqual(self.pressed("s40", 405, 40).scrolled()["s40"], 400 - 39)

    def test_a_press_that_keeps_val_still_moves_the_knob(self):
        # val 50 places the knob from 180 along; a press at x 208 keeps 50,
        # and puts the knob from 179. A move keeping val runs no slide.
        simulation = Simulation(self.root)
        simulation.serial_input("ref s40")
        before = len(simulation.painted())
        simulation.press("s40", 208, 40)
        self.assertEqual((simulation.values()["s40.val"], simulation.scrolled()["s40"]), (50, 179))
        self.assertIn(("redraw", "s40"), simulation.painted()[before:])
        simulation.move(209, 40)
        self.assertEqual((simulation.values()["s40.val"], simulation.scrolled()["s40"],
                          simulation.globals["slides"]), (50, 180, 0))

    def test_a_page_entered_again_places_the_knob_by_val(self):
        simulation = self.pressed("s40", 100, 40)
        for line in ("page second", "page page0"):
            simulation.serial_input(line)
        self.assertNotIn("s40", simulation.scrolled())
        simulation = self.pressed("s40", 100, 40)
        simulation.serial_input("rest")
        self.assertNotIn("s40", simulation.scrolled())


class QrCodeTest(SimulationTestCase):

    def test_a_text_code_sets_draws_its_code(self):
        self.program("page page0\n")
        self.page("page0", [table("code", "qr-code", x=0, y=0, w=120, h=120, dis=4,
                                  txt="short", txt_maxl=10),
                            placed("change", "button", 300, 0)], """\
on change.down:
  code.txt = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
""")
        simulation = Simulation(self.root)
        simulation.press("change")
        page, code, _ = simulation.components()
        # Cut to txt_maxl, as the Editor's simulator draws it.
        cut = Component("code", "qr-code", dict(code.values, txt="ABCDEFGHIJ"))
        self.assertEqual(self.code_picture(page, code), self.code_picture(page, cut))
        self.assertNotEqual(self.code_picture(page, code),
                            self.code_picture(page, Component("code", "qr-code",
                                                              dict(code.values, txt="short"))))

    def code_picture(self, page: Component, code: Component) -> list:
        """The pictures of `code`'s modules in its drawing."""
        drawing = draw_page([page, code], DrawingResources())
        return [shape["image"] for shape in drawing["shapes"] if shape["kind"] == "text"]


class NumberTest(SimulationTestCase):

    def test_a_value_code_sets_is_written_out(self):
        self.program("page page0\n")
        self.page("page0", [table("count", "number", x=0, y=0, w=120, h=40, format=1),
                            placed("change", "button", 300, 0)], """\
on change.down:
  count.val = -1234
""")
        simulation = Simulation(self.root)
        simulation.press("change")
        page, count, _ = simulation.components()
        self.assertEqual(number_text(count.values), "-1,234")
        # Drawn as the simulator's panel draws it, in the folder's font.
        drawing = Previews().drawing_of(self.root, simulation.app, [page, count])
        self.assertEqual([shape["kind"] for shape in drawing["shapes"]
                          if shape["component"] == "count"], ["colour", "text"])


class TouchCaptureTest(SimulationTestCase):
    """Touch capture components, as a probe of this page showed the Editor's
    simulator running them: each event adds a mark to `log`, a touch
    capture's with the `val` it saw."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [
            placed("log", "text", 0, 400, txt="", txt_maxl=200),
            placed("b0", "button", 0, 0), placed("t1", "text", 200, 0),
            placed("t2", "text", 400, 0), placed("b1", "button", 0, 100),
            table("tc0", "touch-capture"), table("tc1", "touch-capture"),
            placed("num", "text", 600, 0, txt="", txt_maxl=10)], """\
on page0.load:
  vis t1,0
  tsw t2,0

on page0.down:
  log.txt+="P "

on page0.up:
  log.txt+="p "

on b0.down:
  log.txt+="X "

on b0.up:
  log.txt+="x "

on t2.down:
  log.txt+="T "

on b1.down:
  log.txt+="K "
  click b0,1

on tc0.down:
  covx tc0.val,num.txt,0,0
  log.txt+="A"+num.txt+" "

on tc1.down:
  covx tc1.val,num.txt,0,0
  log.txt+="B"+num.txt+" "

on tc1.up:
  covx tc1.val,num.txt,0,0
  log.txt+="b"+num.txt+" "
""")

    def tap(self, x: int, y: int) -> str:
        """Taps the screen at (x, y), as the simulator's panel does, and
        returns what the tap added to the log."""
        simulation = Simulation(self.root)
        simulation.press(simulation.component_at(x, y), x, y)
        simulation.release()
        return simulation.values()["log.txt"]

    def test_a_list_takes_the_touch_before_the_captures_release(self):
        # As the Nextion Editor's simulator ran them: a combo box's item,
        # chosen as the touch ends, is the touch capture's to read in its
        # Touch Release event.
        self.page("page0", [
            table("tc0", "touch-capture"),
            table("cb0", "combo-box", x=100, y=60, w=200, h=40, txt="a", path="a\\r\\nb"),
            placed("num", "text", 600, 0, txt="", txt_maxl=10)], """\
on tc0.up:
  covx cb0.val,num.txt,0,0
""")
        simulation = Simulation(self.root)
        for y in (80, 170):
            simulation.press("cb0", 200, y)
            simulation.release()
        self.assertEqual(simulation.values()["num.txt"], "1")

    def test_a_data_records_choice_is_the_captures_to_read(self):
        # As the Nextion Editor's simulator ran it: a tap on the second
        # record, x, the older, chose it before the touch capture's Touch
        # Release event read it.
        self.page("page0", [
            table("tc0", "touch-capture"),
            table("d0", "data-record", x=420, y=20, w=360, h=240, path="sd0/1.data",
                  dir="a^b", format="100^100"),
            placed("num", "text", 600, 400, txt="", txt_maxl=10)], """\
on tc0.up:
  covx d0.val,num.txt,0,0
""")
        simulation = Simulation(self.root)
        for record in ("x^1", "y^2"):
            simulation.serial_input('d0.insert("%s")' % record)
        simulation.press("d0", 470, 100)
        simulation.release()
        self.assertEqual(simulation.values()["num.txt"], "0")

    def test_a_data_record_held_still_is_not_drawn_again_until_the_release(self):
        # As the Nextion Editor's simulator drew one held over a `fill`
        # (tests/fixtures/drawing-assumptions/, page45): `left` 1 shows its
        # scroll bar's thumb only while a touch scrolls it.
        self.page("page0", [table("d0", "data-record", x=420, y=20, w=360, h=240,
                                  path="sd0/1.data", dir="a^b", format="100^100")])
        simulation = Simulation(self.root)
        for record in ("x^1", "y^2"):
            simulation.serial_input('d0.insert("%s")' % record)
        marks = len(simulation.painted())
        simulation.press("d0", 470, 100)
        self.assertEqual((simulation.drawing_inputs().pressed, simulation.painted()[marks:]),
                         (None, []))
        simulation.release()
        self.assertEqual(simulation.painted()[-1], ("redraw", "d0"))

    def test_the_last_touch_capture_runs_before_the_component_touched(self):
        # Only tc1, the page's last, runs: tc0 does not.
        self.assertEqual(self.tap(10, 10), "B2 X b2 x ")

    def test_a_touch_on_the_page_or_a_hidden_component_gives_the_page(self):
        self.assertEqual(self.tap(700, 300), "B0 P b0 p ")
        self.assertEqual(self.tap(210, 10), "B0 P b0 p ")      # on t1, hidden

    def test_a_component_whose_touches_are_off_takes_the_touch_and_nothing_runs(self):
        simulation = Simulation(self.root)
        self.assertEqual(simulation.component_at(410, 10), "t2")
        self.assertEqual(self.tap(410, 10), "")

    def test_a_click_runs_no_touch_capture(self):
        self.assertEqual(self.tap(10, 110), "B5 K X b5 ")

    def test_a_swallowed_press_leaves_no_earlier_press_to_release(self):
        simulation = Simulation(self.root)
        simulation.press(simulation.component_at(10, 10), 10, 10)       # b0, never released
        simulation.press(simulation.component_at(410, 10), 410, 10)     # t2, touches off
        simulation.release()
        self.assertEqual(simulation.values()["log.txt"], "B2 X ")

    def test_every_components_touches_off_turns_the_pages_own_off_too(self):
        # As the Nextion Editor's simulator ran it: after `tsw 255,0`, a press
        # on the page ran nothing, as on a component whose touches are off.
        self.write("pages/page0.nx", self.text("pages/page0.nx").replace(
            "  tsw t2,0\n", "  tsw 255,0\n"))
        self.assertEqual(self.tap(700, 300), "")
        self.assertEqual(self.tap(10, 10), "")

    def test_tsw_does_not_turn_a_touch_capture_off(self):
        self.write("pages/page0.nx", self.text("pages/page0.nx").replace(
            "  tsw t2,0\n", "  tsw t2,0\n  tsw tc1,0\n"))
        self.assertEqual(self.tap(10, 10), "B2 X b2 x ")

    def test_a_touch_capture_changing_page_stops_the_components_events(self):
        self.page("second", [placed("jump", "button", 0, 0), table("watch", "touch-capture")],
                  "on jump.down:\n  sys0=7\n\non jump.up:\n  sys0=8\n\n"
                  "on watch.down:\n  page page0\n")
        simulation = Simulation(self.root, "second")
        simulation.press("jump", 10, 10)
        simulation.release()
        self.assertEqual((simulation.page, simulation.globals["sys0"]), ("page0", 0))


class ToggleTest(SimulationTestCase):
    """A press flips a checkbox's, radio's, dual-state button's, and
    switch's `val` before its down event, as in the Editor's simulator."""

    def setUp(self):
        super().setUp()
        self.program("int seen=0\n\npage page0\n")
        widgets = [table("tick", "checkbox", x=0, y=0, w=40, h=40, val=0),
                   table("first", "radio", x=0, y=60, w=40, h=40, val=0),
                   table("second", "radio", x=60, y=60, w=40, h=40, val=1),
                   table("twin", "dual-state-button", x=0, y=120, w=100, h=40, val=0),
                   table("lever", "switch", x=0, y=180, w=100, h=40, val=0)]
        self.page("page0", widgets, "".join(
            "on %s.down:\n  seen = %s.val\n" % (name, name)
            for name in ("tick", "first", "second", "twin", "lever")))

    def test_a_press_flips_val_before_its_down_event(self):
        simulation = Simulation(self.root)
        for name in ("tick", "first", "twin", "lever"):
            with self.subTest(component=name):
                simulation.press(name)
                self.assertEqual(simulation.globals["seen"], 1)
                simulation.release()
                self.assertEqual(simulation.fields["page0"][name + ".val"], 1)
                simulation.press(name)
                simulation.release()
                self.assertEqual(simulation.fields["page0"][name + ".val"], 0)

    def test_a_touch_capture_sees_the_flipped_val(self):
        # The Editor's simulator flipped the checkbox before the touch
        # capture's Touch Press event ran: it read the new value.
        self.page("page0", [table("tick", "checkbox", x=0, y=0, w=40, h=40, val=0),
                            table("catch", "touch-capture")],
                  "on catch.down:\n  seen = tick.val\n")
        simulation = Simulation(self.root)
        simulation.press("tick")
        self.assertEqual(simulation.globals["seen"], 1)

    def test_radios_are_not_grouped(self):
        simulation = Simulation(self.root)
        simulation.press("first")
        simulation.release()
        self.assertEqual(simulation.fields["page0"]["second.val"], 1)
        simulation.press("second")
        self.assertEqual(simulation.globals["seen"], 0)


class ButtonValTest(SimulationTestCase):
    """A button's `val` is 1 while it is pressed, and 0 once released, each
    set before its event runs, as the Editor's simulator showed."""

    def test_val_while_pressed(self):
        self.program("int seen=0,after=0\n\npage page0\n")
        self.page("page0", [table("b0", "button", x=0, y=0, w=100, h=40)],
                  "on b0.down:\n  seen = b0.val\non b0.up:\n  after = b0.val\n")
        simulation = Simulation(self.root)
        simulation.press("b0")
        self.assertEqual((simulation.globals["seen"], simulation.fields["page0"]["b0.val"]),
                         (1, 1))
        simulation.release()
        self.assertEqual((simulation.globals["after"], simulation.fields["page0"]["b0.val"]),
                         (0, 0))

    def test_a_click_sets_val_before_its_event(self):
        # As the Nextion Editor's simulator ran it: `click b0,1` sets `val` to
        # 1 before the Touch Press event, `click b0,0` to 0.
        self.program("int seen=0,after=0\n\npage page0\n")
        self.page("page0", [table("b0", "button", x=0, y=0, w=100, h=40)],
                  "on b0.down:\n  seen = b0.val\non b0.up:\n  after = b0.val+10\n")
        simulation = Simulation(self.root)
        simulation.serial_input("click b0,1")
        self.assertEqual((simulation.globals["seen"], simulation.fields["page0"]["b0.val"]),
                         (1, 1))
        simulation.serial_input("click b0,0")
        self.assertEqual((simulation.globals["after"], simulation.fields["page0"]["b0.val"]),
                         (10, 0))

    def test_a_press_that_changes_page_leaves_val_0(self):
        # As the Nextion Editor's simulator ran it: a button of global scope
        # whose press changed page read 0 on the new page, while still pressed
        # and after, and its Touch Release event did not run.
        self.program("int after=0\n\npage page0\n")
        self.page("page0", [table("b0", "button", x=0, y=0, w=100, h=40, vscope=1)],
                  "on b0.down:\n  page page1\non b0.up:\n  after=5\n")
        self.page("page1", [])
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("page1")))
        simulation = Simulation(self.root)
        simulation.press("b0")
        self.assertEqual((simulation.page, simulation.fields["page0"]["b0.val"]), ("page1", 0))
        simulation.release()
        self.assertEqual((simulation.fields["page0"]["b0.val"], simulation.globals["after"]),
                         (0, 0))


class ScrollingTextTest(SimulationTestCase):
    """A scrolling text moving on the simulation's clock (scrolling_texts.py,
    and test_scrolling_texts.py for its steps against the Editor's), in the
    font a new folder starts with, Noto Sans at 24 pixels."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=200, h=30, tim=500,
                                  dis=10)])

    def test_it_starts_outside_and_steps_on_the_clock(self):
        simulation = Simulation(self.root)
        values = simulation.values()
        # Moving right to left, as by default: just outside on the right.
        self.assertEqual((values["st.vvs0"], values["st.vvs1"], simulation.next_due()),
                         (300, 32767, 500))
        simulation.globals["painted"] = []
        simulation.advance(500)
        self.assertEqual((simulation.scrolled(), simulation.next_due()), ({"st": 290}, 1000))
        self.assertEqual(simulation.painted(), [("redraw", "st")])

    def test_its_texts_width_and_height(self):
        # vvs2 and vvs3 hold its text's width and height in pixels, as code
        # read them in the Editor's simulator: 88 and 24 for "abcdefghij" in
        # Noto Sans at 24 pixels.
        self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=200, h=30,
                                  txt="abcdefghij", txt_maxl=20)])
        values = Simulation(self.root).values()
        self.assertEqual((values["st.vvs2"], values["st.vvs3"]), (88, 24))

    def test_its_texts_width_in_a_gb2312_font(self):
        # 中 two pixels wide, and a one, as gb2312_glyphs draws them, in a
        # font 2 pixels tall.
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(encoding="gb2312")))
        (self.root / "fonts" / "NotoSans24.zi").write_bytes(gb2312_font())
        self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=200, h=30, txt="中a",
                                  txt_maxl=20)])
        values = Simulation(self.root).values()
        self.assertEqual((values["st.vvs2"], values["st.vvs3"]), (3, 2))

    def test_its_texts_width_in_other_two_byte_fonts(self):
        # A pair two pixels wide, and an ascii character one, as grid_glyphs
        # draws them, each pair found at its place in its grid.
        for encoding, text in (("big5", "中a"), ("shift-jis", "亜a"),
                               ("ks_c_5601-1987", "가a")):
            with self.subTest(encoding=encoding):
                self.write("app.toml", edited_app(self.text("app.toml"),
                                                  lambda app: app.update(encoding=encoding)))
                (self.root / "fonts" / "NotoSans24.zi").write_bytes(grid_font(encoding))
                self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=200, h=30,
                                          txt=text, txt_maxl=20)])
                values = Simulation(self.root).values()
                self.assertEqual((values["st.vvs2"], values["st.vvs3"]), (3, 2))

    def test_a_character_its_font_lacks(self):
        # Measured as the screen draws it: as the font's first character,
        # the space, where it measured as nothing.
        widths = []
        for text in ("a\tb", "a b"):
            self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=200, h=30,
                                      txt=text, txt_maxl=20)])
            widths.append(Simulation(self.root).values()["st.vvs2"])
        self.assertEqual(widths[0], widths[1])

    def test_code_stops_and_starts_it(self):
        simulation = Simulation(self.root)
        simulation.serial_input("st.en=0")
        self.assertIsNone(simulation.next_due())
        simulation.advance(2000)
        self.assertEqual(simulation.scrolled(), {"st": 300})
        simulation.serial_input("st.en=1")
        self.assertEqual(simulation.next_due(), 2500)
        simulation.advance(500)
        self.assertEqual(simulation.scrolled(), {"st": 290})

    def test_it_stops_while_the_screen_sleeps(self):
        simulation = Simulation(self.root)
        simulation.serial_input("sleep=1")
        simulation.advance(2000)
        self.assertEqual((simulation.scrolled(), simulation.next_due()), ({"st": 300}, None))
        # Woken at 2000, it counts its 500 ms again from then.
        simulation.serial_input("sleep=0")
        self.assertEqual(simulation.next_due(), 2500)
        simulation.advance(500)
        self.assertEqual(simulation.scrolled(), {"st": 290})

    def test_a_new_way_across_the_line_turns_it_at_its_next_step(self):
        # As the Nextion Editor's simulator moved one, with a `tim` of a
        # second. That replaces an earlier reading, when the text seemed to
        # turn at once: there, each turn came within a tick of a step. Turned
        # from across to up or down, or back, the text stayed as it was until
        # its next step. That step put it where it comes round once it has
        # gone out, a pixel in from where it starts as its page opens, and
        # moved it no further.
        simulation = Simulation(self.root)
        simulation.advance(500)
        simulation.serial_input("st.dir=2")
        values = simulation.values()
        self.assertEqual((values["st.vvs0"], values["st.vvs1"], simulation.next_due()),
                         (290, 32767, 1000))
        simulation.advance(500)
        # Moving down now: from above, as high as its font, 24 pixels.
        values = simulation.values()
        self.assertEqual((values["st.vvs0"], values["st.vvs1"], simulation.next_due()),
                         (32767, -24, 1500))
        simulation.serial_input("st.dir=1")
        simulation.advance(500)
        self.assertEqual(simulation.scrolled(), {"st": 299})

    def test_a_stopped_text_does_not_turn(self):
        # In the Nextion Editor's simulator, a stopped text turned down
        # stayed across. Started again, it turned at its first step.
        simulation = Simulation(self.root)
        simulation.serial_input("st.en=0")
        simulation.serial_input("st.dir=2")
        simulation.advance(2000)
        self.assertEqual(simulation.scrolled(), {"st": 300})
        simulation.serial_input("st.en=1")
        simulation.advance(500)
        self.assertEqual(simulation.scrolled(), {"st": -24})

    def test_drawn_in_its_old_way_until_it_turns(self):
        # Code reads the `dir` it stored, but the text shows as it was.
        simulation = Simulation(self.root)
        simulation.advance(500)

        def text_shape() -> dict:
            return next(shape for shape in screen_drawing(simulation)["shapes"]
                        if shape["kind"] == "text")
        before = text_shape()
        simulation.serial_input("st.dir=2")
        self.assertEqual((simulation.values()["st.dir"], text_shape()), (2, before))

    def test_a_new_way_along_the_same_line_keeps_its_place(self):
        # As the Nextion Editor's simulator moved one: turned from left to
        # right to right to left, it went back from where it was. Here, the
        # other way round, from the component's middle, so that no step takes
        # it past the component's end.
        simulation = Simulation(self.root)
        simulation.advance(5000)
        simulation.serial_input("st.dir=0")
        self.assertEqual((simulation.scrolled(), simulation.next_due()), ({"st": 200}, 5500))
        simulation.advance(500)
        self.assertEqual(simulation.scrolled(), {"st": 210})

    def test_its_tim_and_en_set_again_keep_its_count(self):
        # As the Nextion Editor's simulator moved one: code setting its `tim`
        # to its own value, or `en` to 1, every 50 ms left it stepping every
        # `tim`, where a timer counts again. A new `tim` set the next step
        # that long after the last, at once when that time had passed.
        simulation = Simulation(self.root)
        simulation.advance(300)
        simulation.serial_input("st.tim=500")
        simulation.serial_input("st.en=1")
        self.assertEqual(simulation.next_due(), 500)
        simulation.serial_input("st.tim=1000")
        self.assertEqual(simulation.next_due(), 1000)
        simulation.serial_input("st.tim=200")
        simulation.advance(1)
        self.assertEqual((simulation.scrolled(), simulation.next_due()), ({"st": 290}, 500))

    def test_a_new_text_is_measured_again(self):
        font = Path(__file__).resolve().parent / "fixtures" / "fonts" / "NotoSans20.zi"
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "NotoSans20.zi").write_bytes(font.read_bytes())
        self.write("app.toml", fonts_first(self.text("app.toml"), ["NotoSans20"]))
        self.page("page0", [table("st", "scrolling-text", x=100, y=0, w=100, h=30, tim=500,
                                  dis=50, dir="\\u0000", txt="LR", txt_maxl=20,
                                  font="NotoSans20")])
        simulation = Simulation(self.root)
        # "LR" is 17 pixels wide: it starts at 100 - 17 - 1, left to right.
        self.assertEqual(simulation.scrolled(), {"st": 82})
        simulation.serial_input('st.txt="Left to right"')
        simulation.advance(1500)
        # Past 199 at its third step, it starts again at 100 less the new
        # text's 81 pixels.
        self.assertEqual(simulation.scrolled(), {"st": 19})

    def hello_and_a_small_font(self, **values) -> Simulation:
        """A simulation of "Hello" moving left to right, 10 pixels every
        100 ms, at x 100, 400 wide, as the Nextion Editor's simulator ran it:
        44 by 24 pixels in font 0. Font 1 is 16 pixels high. `values` change
        the scrolling text's own."""
        font = Path(__file__).resolve().parent / "fixtures" / "fonts" / "Sans16.zi"
        (self.root / "fonts" / "Sans16.zi").write_bytes(font.read_bytes())
        self.write("app.toml", edited_app(self.text("app.toml"), lambda app: app.update(
            fonts=list(dict.fromkeys(app["fonts"] + ["Sans16"])))))
        self.page("page0", [table("st", "scrolling-text", **dict(
            dict(x=100, y=20, w=400, h=40, tim=100, dis=10, dir=0, txt="Hello", txt_maxl=20),
            **values))])
        return Simulation(self.root)

    def test_a_new_font_is_measured_at_the_next_step(self):
        # In the Nextion Editor's simulator, a new font left `vvs2` and
        # `vvs3` as they were. The text's next step measured it, then moved
        # it: put just before the component's end, it came round at 100
        # less the new width, 29.
        simulation = self.hello_and_a_small_font()
        simulation.serial_input("st.vvs0=495")
        simulation.serial_input("st.font=1")
        values = simulation.values()
        self.assertEqual((values["st.vvs0"], values["st.vvs2"], values["st.vvs3"]),
                         (495, 44, 24))
        simulation.advance(100)
        values = simulation.values()
        self.assertEqual((values["st.vvs0"], values["st.vvs2"], values["st.vvs3"]),
                         (71, 29, 16))

    def test_a_turn_places_it_by_its_new_size(self):
        # The step that turns it measures it first: turned down after a new
        # font, it came in from 16 pixels above, its new height, not 24.
        simulation = self.hello_and_a_small_font()
        simulation.serial_input("st.font=1")
        simulation.serial_input("st.dir=2")
        simulation.advance(100)
        self.assertEqual(simulation.scrolled(), {"st": 20 - 16})

    def test_a_stopped_text_is_not_measured_again(self):
        # In the Nextion Editor's simulator, a stopped text kept its size
        # through a new `txt`, a `ref`, and a new `vvs0`. `en` 1 left it so
        # until the next step, which measured "Hello there", 93 pixels wide.
        simulation = self.hello_and_a_small_font()
        for line in ("st.en=0", 'st.txt="Hello there"', "ref st", "st.vvs0=200"):
            simulation.serial_input(line)
        simulation.advance(1000)
        simulation.serial_input("st.en=1")
        values = simulation.values()
        self.assertEqual((values["st.vvs2"], values["st.vvs3"]), (44, 24))
        simulation.advance(100)
        values = simulation.values()
        self.assertEqual((values["st.vvs0"], values["st.vvs2"]), (210, 93))

    def test_drawn_across_its_way_by_its_kept_size(self):
        # As the Nextion Editor's simulator drew a stopped text: in its new
        # font, or with its new text, at once, but centred across its way by
        # the size kept from its last measuring. Moving across, "Hello" in
        # the font 16 pixels high stood centred as one 24 high. Moving down,
        # "Hello there" stood centred as "Hello", 44 pixels wide.
        fixtures = Path(__file__).resolve().parent / "fixtures" / "scrolling-text"
        for picture, values, lines in (
                ("new-font-stopped.png", {}, ("st.en=0", "st.vvs0=470", "st.font=1")),
                ("new-text-stopped-down.png", {"dir": 2, "h": 200},
                 ("st.en=0", "st.vvs1=120", 'st.txt="Hello there"'))):
            with self.subTest(picture=picture):
                simulation = self.hello_and_a_small_font(**values)
                for line in lines:
                    simulation.serial_input(line)
                drawn = paint_drawing(screen_drawing(simulation))
                shot = read_picture((fixtures / picture).read_bytes())
                box = dict(x=100, y=20, w=400, h=values.get("h", 40))
                differing = differing_pixels(drawn, shot, box, 2)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_measured_as_laid_out(self):
        # As the Nextion Editor's simulator measured and drew four stopped
        # texts, in Noto Sans at 24 pixels: `vvs2` and `vvs3` count `spax`
        # between characters, `spay` between lines, and the lines `isbr` wraps
        # at the component's width, as the text is drawn. Each text is placed
        # across its way by that size.
        texts = {"gA": dict(x=100, y=10, w=400, h=40, dir=0, spax=5, txt="Hello"),
                 "gB": dict(x=100, y=60, w=400, h=100, dir=2, spax=5, txt="Hello"),
                 "gC": dict(x=100, y=170, w=400, h=100, dir=0, spay=4,
                            txt="Hello\\r\\nWorld"),
                 "gD": dict(x=550, y=10, w=100, h=200, dir=2, isbr=1,
                            txt="Hello there friend")}
        self.page("page0", [table(name, "scrolling-text", txt_maxl=40, **values)
                            for name, values in texts.items()])
        simulation = Simulation(self.root)
        values = simulation.values()
        self.assertEqual({name: (values[name + ".vvs2"], values[name + ".vvs3"])
                          for name in texts},
                         {"gA": (64, 24), "gB": (64, 24), "gC": (50, 52), "gD": (98, 48)})
        for line in ("gA.en=0", "gA.vvs0=200", "gB.en=0", "gB.vvs1=80", "gC.en=0",
                     "gC.vvs0=200", "gD.en=0", "gD.vvs1=40"):
            simulation.serial_input(line)
        drawn = paint_drawing(screen_drawing(simulation))
        shot = read_picture((Path(__file__).resolve().parent / "fixtures" / "scrolling-text" /
                             "spaced-and-wrapped.png").read_bytes())
        for name, place in texts.items():
            with self.subTest(component=name):
                differing = differing_pixels(drawn, shot, place, 2)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class SlidingTextTest(SimulationTestCase):
    """Sliding texts scrolled by code and by touches, on the page the
    Editor's simulator ran (fixtures/sliding-text/scrolled.page.toml), and
    test_sliding_texts.py for their drawing against the Editor's."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        fixtures = Path(__file__).resolve().parent / "fixtures"
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "NotoSans20.zi").write_bytes(
            (fixtures / "fonts" / "NotoSans20.zi").read_bytes())
        self.write("app.toml", fonts_first(self.text("app.toml"), ["NotoSans20"]))
        folder = fixtures / "sliding-text"
        self.write("pages/page0.page.toml",
                   (folder / "scrolled.page.toml").read_text(encoding="utf-8"))
        self.write("pages/page0.nx", (folder / "scrolled.nx").read_text(encoding="utf-8"))
        self.readings = tomllib.loads((folder / "readings.toml").read_text(encoding="utf-8"))

    def scrolled(self, simulation: Simulation, attribute: str = "val_y") -> dict:
        values = simulation.values()
        return {name: values[name + "." + attribute] for name in ("sa", "sb", "sc", "sd", "se")}

    def test_as_the_editors_simulator_scrolled_them(self):
        simulation = Simulation(self.root)
        self.assertEqual(self.scrolled(simulation, "maxval_y"),
                         self.readings["scrolled"]["maxval_y"])
        for button, picture in (("b25", "scrolled-25.png"), ("b1000", "scrolled-1000.png")):
            simulation.press(button)
            simulation.release()
            self.assertEqual(self.scrolled(simulation),
                             self.readings["scrolled"]["val_y"][picture], button)

    def test_a_drag_scrolls_the_lines_as_far_as_a_touch_may(self):
        simulation = Simulation(self.root)
        simulation.press("sa", 100, 100)
        simulation.move(100, 70)
        self.assertEqual(simulation.values()["sa.val_y"], 30)
        simulation.move(100, 0)
        self.assertEqual(simulation.values()["sa.val_y"], 50)
        simulation.release()
        self.assertEqual((simulation.values()["sa.val_y"], simulation.pressed()), (50, None))

    def test_held_it_is_drawn_as_held_only_once_a_touch_scrolls_it(self):
        # As `left` 1 says, "while scrolling": held still, the Nextion
        # Editor's simulator neither drew its scroll bar's thumb nor drew it
        # again (tests/fixtures/drawing-assumptions/, page44).
        simulation = Simulation(self.root)
        marks = len(simulation.painted())
        simulation.press("sa", 100, 100)
        self.assertEqual((simulation.pressed(), simulation.drawing_inputs().pressed,
                          simulation.painted()[marks:]), ("sa", None, []))
        simulation.move(100, 70)
        self.assertEqual((simulation.drawing_inputs().pressed, simulation.painted()[-1]),
                         ("sa", ("redraw", "sa")))
        simulation.release()
        self.assertIsNone(simulation.drawing_inputs().pressed)

    def test_lines_that_fit_do_not_move(self):
        simulation = Simulation(self.root)
        simulation.press("se", 100, 300)
        simulation.move(100, 250)
        simulation.release()
        self.assertEqual(simulation.values()["se.val_y"], 0)

    def test_a_new_text_is_laid_out_again(self):
        simulation = Simulation(self.root)
        simulation.serial_input("sa.val_y=40")
        simulation.serial_input('sa.txt="one\\rtwo"')
        # Two lines fit: none scrolls, and code may push them up one line.
        values = simulation.values()
        self.assertEqual((values["sa.maxval_y"], values["sa.val_y"]), (0, 20))

    def test_a_start_page_opens_from_the_values_given(self):
        # Its lines are laid out from the text given, as from its page file's.
        simulation = Simulation(self.root, "page0", {"sa.txt": ""})
        self.assertEqual(simulation.values()["sa.maxval_y"], 0)


class Utf8SlidingTextTest(SimulationTestCase):
    """Sliding texts in a utf-8 folder, in a font of Cyrillic letters
    (test_zi_font.py's NotoSans20-cyrillic). Their lines are laid out from
    the advances of the font's characters, one per code point, so that code
    reads `maxval_y` as the screen works it out."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "Cyrillic.zi").write_bytes(utf8_fixture("NotoSans20-cyrillic"))
        self.write("app.toml", fonts_first(
            self.text("app.toml").replace('"iso-8859-1"', '"utf-8"'), ["Cyrillic"]))

    def test_lines_wrapped_by_the_fonts_advances(self):
        # Ж is 13 pixels wide: three fit in a line 45 pixels wide, inside
        # a border of 2 or none. So twelve wrap into four lines, as split.
        sliding = ('[[component]]\nname = "%s"\ntype = "sliding-text"\nfont = "Cyrillic"\n'
                   'x = 10\ny = %d\nw = 45\nh = 50\nisbr = 1\nspax = 0\ntxt = "%s"\n')
        self.page("page0", [sliding % ("wrapped", 10, "Ж" * 12),
                            sliding % ("split", 100, "\\r".join(["ЖЖЖ"] * 4))])
        values = Simulation(self.root).values()
        self.assertGreater(values["wrapped.maxval_y"], 0)
        self.assertEqual(values["wrapped.maxval_y"], values["split.maxval_y"])

    def test_a_font_is_decoded_again_only_once_its_file_changes(self):
        # A utf-8 font takes some 20 ms to decode, and a sliding text reads
        # its font at each layout: two texts and a change of one's text
        # decode it once. A font file changed is read again.
        sliding = ('[[component]]\nname = "%s"\ntype = "sliding-text"\nfont = "Cyrillic"\n'
                   'x = 10\ny = %d\nw = 45\nh = 50\ntxt = "ЖЖЖ"\n')
        self.page("page0", [sliding % ("one", 10), sliding % ("two", 100)])
        font = self.root / "fonts" / "Cyrillic.zi"
        with mock.patch.object(folder_resources, "decode_font",
                               wraps=folder_resources.decode_font) as decode:
            simulation = Simulation(self.root)
            simulation.serial_input('one.txt="ЖЖЖЖЖЖ"')
            self.assertEqual(decode.call_count, 1)
            stamp = font.stat().st_mtime_ns + 10 ** 9
            os.utime(font, ns=(stamp, stamp))
            simulation.serial_input('one.txt="Ж"')
            self.assertEqual(decode.call_count, 2)


class ComboBoxTest(SimulationTestCase):
    """A combo box opened, chosen from, and set by code, on the page the
    Editor's simulator ran (fixtures/combo-box/events.page.toml), against
    what it logged (readings.toml), and test_combo_boxes.py for its drawing."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        fixtures = Path(__file__).resolve().parent / "fixtures"
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "NotoSans20.zi").write_bytes(
            (fixtures / "fonts" / "NotoSans20.zi").read_bytes())
        self.write("app.toml", fonts_first(self.text("app.toml"), ["NotoSans20"]))
        folder = fixtures / "combo-box"
        self.write("pages/page0.page.toml",
                   (folder / "events.page.toml").read_text(encoding="utf-8"))
        self.write("pages/page0.nx", (folder / "events.nx").read_text(encoding="utf-8"))
        self.readings = tomllib.loads((folder / "readings.toml").read_text(encoding="utf-8"))

    def tap(self, simulation: Simulation, x: int, y: int):
        simulation.press(simulation.component_at(x, y), x, y)
        simulation.release()

    def test_touches_as_the_editors_simulator_took_them(self):
        for number, run in enumerate(self.readings["run"]):
            with self.subTest(run=number):
                simulation = Simulation(self.root)
                for x, y in run["taps"]:
                    self.tap(simulation, x, y)
                self.assertEqual(simulation.values()["log.txt"], run["log"])

    def test_code_as_the_editors_simulator_took_it(self):
        for code in self.readings["code"]:
            with self.subTest(code=code["instructions"]):
                simulation = Simulation(self.root)
                for instruction in code["instructions"]:
                    simulation.serial_input(instruction)
                values = simulation.values()
                self.assertEqual((values["cb.val"], values["cb.txt"]), (code["val"], code["txt"]))

    def test_the_open_list_belongs_to_its_box(self):
        simulation = Simulation(self.root)
        # ua lies under where the list opens, before cb in ID order; ub after it.
        self.assertEqual([simulation.component_at(370, y) for y in (200, 250, 284)],
                         ["ua", "ub", "page0"])
        self.tap(simulation, 370, 41)
        self.assertEqual([simulation.component_at(370, y) for y in (200, 250, 284, 300)],
                         ["cb", "ub", "cb", "page0"])

    def test_code_opens_and_scrolls_the_list(self):
        simulation = Simulation(self.root)
        simulation.serial_input("cb.down=1")
        self.assertEqual(simulation.scrolled(), {"cb": 0})
        simulation.serial_input("cb.val=5")
        # The last four of six items show the sixth.
        self.assertEqual((simulation.scrolled(), simulation.values()["cb.txt"]),
                         ({"cb": 2}, "140V"))
        simulation.serial_input("cb.down=0")
        self.assertEqual(simulation.scrolled(), {})

    def test_a_start_page_opens_from_the_values_given(self):
        # The list shows as the page opens, as from its page file's `down`.
        simulation = Simulation(self.root, "page0", {"cb.down": 1})
        self.assertEqual(simulation.scrolled(), {"cb": 0})

    def test_a_drag_scrolls_the_list_and_chooses_nothing(self):
        simulation = Simulation(self.root)
        self.tap(simulation, 370, 41)
        simulation.press("cb", 370, 200)
        # Up by two items' length, 50 pixels each: two later items come in.
        simulation.move(370, 100)
        self.assertEqual(simulation.scrolled(), {"cb": 2})
        simulation.move(370, 0)
        self.assertEqual(simulation.scrolled(), {"cb": 2})
        simulation.release()
        values = simulation.values()
        self.assertEqual((values["cb.down"], values["cb.val"], simulation.scrolled()),
                         (1, 0, {"cb": 2}))
        # A tap now chooses from the scrolled list: its first item shown is the third.
        self.tap(simulation, 370, 100)
        self.assertEqual((simulation.values()["cb.val"], simulation.values()["cb.txt"]),
                         (2, "80V"))
        # A drag from the box itself scrolls nothing.
        self.tap(simulation, 370, 41)
        simulation.press("cb", 370, 41)
        simulation.move(370, -60)
        self.assertEqual(simulation.scrolled(), {"cb": 2})


class DataRecordTouchTest(SimulationTestCase):
    """Taps on data records, on the page the Editor's simulator ran
    (fixtures/data-record/touches.page.toml), against what it logged
    (readings.toml), and test_data_records.py for the rows they land on."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        fixtures = Path(__file__).resolve().parent / "fixtures"
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "NotoSans20.zi").write_bytes(
            (fixtures / "fonts" / "NotoSans20.zi").read_bytes())
        self.write("app.toml", fonts_first(self.text("app.toml"), ["NotoSans20"]))
        folder = fixtures / "data-record"
        self.write("pages/page0.page.toml",
                   (folder / "touches.page.toml").read_text(encoding="utf-8"))
        self.write("pages/page0.nx", (folder / "touches.nx").read_text(encoding="utf-8"))
        self.readings = tomllib.loads((folder / "readings.toml").read_text(encoding="utf-8"))

    def tap(self, simulation: Simulation, x: int, y: int):
        simulation.press(simulation.component_at(x, y), x, y)
        simulation.release()

    def test_taps_as_the_editors_simulator_took_them(self):
        for number, run in enumerate(self.readings["touches"]):
            with self.subTest(run=number):
                simulation = Simulation(self.root)
                for x, y in run["taps"]:
                    self.tap(simulation, x, y)
                self.assertEqual(simulation.values()["log.txt"], run["log"])

    def test_a_touch_chooses_nothing_with_dis_0(self):
        simulation = Simulation(self.root)
        simulation.serial_input("da.dis=0")
        self.tap(simulation, 100, 58)
        self.assertEqual((simulation.values()["da.val"], simulation.values()["log.txt"]),
                         (-1, "ad-1 au-1 "))

    def test_a_drag_scrolls_the_records(self):
        # Assumed: the Editor tool cannot drag the Editor's simulator, so no
        # probe showed it.
        simulation = Simulation(self.root)
        simulation.press("db", 400, 150)
        simulation.move(400, 110)
        simulation.release()
        values = simulation.values()
        self.assertEqual((values["db.val_y"], values["db.val"]), (40, -1))


class DataRecordTest(SimulationTestCase):
    """A data record's file, made as its page opens, its records drawn, and
    its values following code's calls (test_data_records.py for the
    calls and the drawing against the Editor's)."""
    language = "nextion"
    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "data-record"

    def setUp(self):
        super().setUp()
        # As small.data's data record: lenth 31, dez 2, maxval 10.
        self.page("page0", [table("d0", "data-record", x=10, y=10, w=380, h=200,
                                  path="sd0/d.data", lenth=31, dez=2, maxval=10, dir="A^B")])

    def test_a_missing_file_is_made_as_the_page_opens(self):
        simulation = Simulation(self.root)
        self.assertEqual(simulation.globals["file contents"]["sd0/d.data"],
                         (self.FIXTURES / "small.data").read_bytes())
        self.assertEqual((simulation.values()["d0.qty"], simulation.listings()), (0, {"d0": []}))

    def test_on_a_card_given_a_folder(self):
        card = Path(self._folder.name) / "card"
        card.mkdir()
        Simulation(self.root, cards={"sd0/": card})
        self.assertEqual((card / "d.data").read_bytes(),
                         (self.FIXTURES / "small.data").read_bytes())

    def test_a_file_the_folder_will_not_give_is_left_as_it_was(self):
        # As one another program holds: not taken for a missing one.
        card = Path(self._folder.name) / "card"
        card.mkdir()
        three = (self.FIXTURES / "three.data").read_bytes()
        (card / "d.data").write_bytes(three)
        with mock.patch.object(simulation_module.FolderCards, "read",
                               side_effect=OSError("held")):
            simulation = Simulation(self.root, cards={"sd0/": card})
            self.assertEqual(simulation.listings(), {"d0": []})
        self.assertEqual((card / "d.data").read_bytes(), three)
        self.assertEqual(simulation.values()["d0.qty"], 0)

    def test_code_calls_its_methods(self):
        simulation = Simulation(self.root)
        for text in ("a^1", "b^2", "c^3", "d^4", "e^5", "f^6", "g^7"):
            simulation.serial_input('d0.insert("%s")' % text)
        simulation.serial_input("d0.val=1")
        values = simulation.values()
        # Seven rows and the titles', 32 high, past 198 inside a 3D edge.
        self.assertEqual((values["d0.qty"], values["d0.txt"], values["d0.maxval_y"]),
                         (7, "b^2", 8 * 32 + 1 - 198))
        self.assertEqual(simulation.listings()["d0"][:2], ["a^1", "b^2"])

    def test_code_changing_the_table(self):
        simulation = Simulation(self.root)
        for text in ("a^1", "b^2", "c^3", "d^4", "e^5", "f^6", "g^7"):
            simulation.serial_input('d0.insert("%s")' % text)
        simulation.serial_input("d0.val=1")
        # A new `dir` leaves `maxval_y` as it was, as the Editor's simulator
        # did, until another change works it out again. Without titles, the
        # top record takes their row: a row fewer.
        simulation.serial_input('d0.dir=""')
        self.assertEqual(simulation.values()["d0.maxval_y"], 8 * 32 + 1 - 198)
        simulation.serial_input("d0.hig=40")
        self.assertEqual(simulation.values()["d0.maxval_y"], 7 * 40 + 1 - 198)
        simulation.serial_input('d0.path="sd0/e.data"')
        values = simulation.values()
        self.assertEqual((values["d0.qty"], values["d0.val"], values["d0.txt"],
                          values["d0.maxval_y"], simulation.listings()["d0"]),
                         (0, -1, "", 0, []))

    def test_code_scrolling_the_table(self):
        # As the Editor's simulator kept them: `val_y` up to 32 pixels past
        # `maxval_y`, a value below 0 as code set it, and `val_x` from 0 to
        # `maxval_x`, which counts the last column's line, `gdh` wide.
        simulation = Simulation(self.root)
        for text in ("a^1", "b^2", "c^3", "d^4", "e^5", "f^6", "g^7"):
            simulation.serial_input('d0.insert("%s")' % text)
        simulation.serial_input("d0.val_y=500")
        self.assertEqual(simulation.values()["d0.val_y"], 8 * 32 + 1 - 198 + 32)
        simulation.serial_input("d0.val_y=-5")
        self.assertEqual(simulation.values()["d0.val_y"], -5)
        simulation.serial_input("d0.val_x=500")
        self.assertEqual(simulation.values()["d0.val_x"], 0)
        simulation.serial_input('d0.format="200^200"')
        simulation.serial_input("d0.val_x=500")
        self.assertEqual(simulation.values()["d0.val_x"], 400 + 1 - 378)
        simulation.serial_input("d0.gdh=3")
        self.assertEqual(simulation.values()["d0.maxval_x"], 400 + 3 - 378)
        simulation.serial_input("d0.val_x=-5")
        self.assertEqual(simulation.values()["d0.val_x"], 0)

    def test_a_file_the_page_opens_on(self):
        # The file's own header governs, whatever the data record's attributes.
        simulation = Simulation(self.root)
        simulation.globals["file contents"]["sd0/d.data"] = \
            (self.FIXTURES / "three.data").read_bytes()
        simulation.serial_input("page page0")
        self.assertEqual((simulation.values()["d0.qty"], simulation.listings()),
                         (3, {"d0": ["a^1^x", "b^2^y", "c^3^z"]}))


class DataFileHoldingTestCase(SimulationTestCase):
    """A simulation of data records, and the 0x06 answers it sends."""
    language = "nextion"

    def started(self) -> tuple:
        sent = []
        return Simulation(self.root, sending=sent.append), sent

    def refusals(self, sent: list) -> int:
        refusals = sent.count(bytes.fromhex("06 ff ff ff"))
        sent.clear()
        return refusals


class SharedDataFileTest(DataFileHoldingTestCase):
    """Data records naming one file, as the Nextion Editor's simulator ran
    them: the first to open it holds it, across pages, until code changes
    its `path`; the others open nothing, and answer 0x06 twice as their page
    opens (test_data_records.py for their methods and their drawing)."""

    def setUp(self):
        super().setUp()
        self.page("page0", [self.record("d0", 10), self.record("d1", 270),
                            self.record("d2", 530)])
        self.page("second", [self.record("d3", 10)])

    def record(self, name: str, x: int, **values) -> str:
        return table(name, "data-record", x=x, y=10, w=250, h=140, path="sd0/1.data",
                     dir="A^B", dez=2, mode=1, **values)

    def test_as_the_page_opens(self):
        simulation, sent = self.started()
        listings = simulation.listings()
        self.assertEqual((listings["d0"], listings["d1"], listings["d2"]),
                         ([], UNOPENED, UNOPENED))
        self.assertEqual((simulation.values()["d1.qty"], self.refusals(sent)), (0, 4))

    def test_across_pages(self):
        simulation, sent = self.started()
        simulation.serial_input('d0.insert("a^1")')
        self.refusals(sent)
        # d0 holds the file after its page is left, and opens it again.
        simulation.serial_input("page second")
        self.assertEqual((simulation.listings()["d3"], self.refusals(sent)), (UNOPENED, 2))
        simulation.serial_input("page page0")
        self.assertEqual((simulation.listings()["d0"], self.refusals(sent)), (["a^1"], 4))
        # Once d0 names another file, d3 opens it.
        simulation.serial_input('d0.path="sd0/2.data"')
        simulation.serial_input("page second")
        self.assertEqual((simulation.listings()["d3"], self.refusals(sent)), (["a^1"], 0))

    def test_a_global_records_path_set_from_another_page(self):
        # page0's d0, named so by the code of another page, lets its file go
        # and holds the new one as itself: back on page0, it opens that, and
        # d1 opens the file d0 let go.
        self.page("page0", [self.record("d0", 10, vscope=1), self.record("d1", 270)])
        simulation, sent = self.started()
        simulation.serial_input("page second")
        simulation.serial_input('page0.d0.path="sd0/2.data"')
        simulation.serial_input("page page0")
        listings = simulation.listings()
        self.assertEqual((listings["d0"], listings["d1"]), ([], []))

    def test_records_of_an_empty_path(self):
        # Assumed: records whose path code has yet to set shut no one out.
        self.page("page0", [table(name, "data-record", x=10 + 260 * place, y=10, w=250, h=140,
                                  path="", mode=1) for place, name in enumerate(("d0", "d1"))])
        simulation, sent = self.started()
        self.assertEqual((simulation.listings()["d1"], self.refusals(sent)), ([], 0))

    def test_a_path_naming_a_held_file(self):
        simulation, sent = self.started()
        simulation.serial_input('d1.path="sd0/own.data"')
        self.assertEqual(simulation.listings()["d1"], [])
        self.refusals(sent)
        simulation.serial_input('d1.path="sd0/1.data"')
        self.assertEqual((simulation.listings()["d1"], self.refusals(sent)), (UNOPENED, 1))


class MostDataFilesHeldTest(DataFileHoldingTestCase):
    """Data records each naming a file of its own, as the Nextion Editor's
    simulator ran them: at most 8 files are held at once, across pages. A
    record finding 8 held by others opens nothing, as if its file were held."""

    def setUp(self):
        super().setUp()
        self.page("page0", [self.record("d%d" % place, 10 + 155 * (place % 5),
                                        10 + 200 * (place // 5))
                            for place in range(10)])
        self.page("second", [self.record("d10", 10, 10)])

    def record(self, name: str, x: int, y: int) -> str:
        return table(name, "data-record", x=x, y=y, w=150, h=140, path="sd0/%s.data" % name,
                     dir="A^B", dez=2, mode=1)

    def test_as_the_page_opens(self):
        # The first 8 in ID order.
        simulation, sent = self.started()
        listings = simulation.listings()
        self.assertEqual([listings["d%d" % place] for place in range(10)],
                         [[]] * 8 + [UNOPENED] * 2)
        self.assertEqual(self.refusals(sent), 4)

    def test_across_pages(self):
        # page0's records hold their files on another page, and open them again.
        simulation, sent = self.started()
        self.refusals(sent)
        simulation.serial_input("page second")
        self.assertEqual((simulation.listings()["d10"], self.refusals(sent)), (UNOPENED, 2))
        simulation.serial_input("page page0")
        listings = simulation.listings()
        self.assertEqual(([listings["d%d" % place] for place in (0, 7, 8, 9)],
                          self.refusals(sent)), ([[], [], UNOPENED, UNOPENED], 4))

    def test_a_place_a_new_path_frees(self):
        # d0 lets its file go, d8 opens one in its place, then d9 finds 8 held.
        simulation, sent = self.started()
        self.refusals(sent)
        simulation.serial_input('d0.path=""')
        simulation.serial_input('d8.path="sd0/new8.data"')
        self.assertEqual((simulation.listings()["d8"], self.refusals(sent)), ([], 0))
        simulation.serial_input('d9.path="sd0/new9.data"')
        self.assertEqual((simulation.listings()["d9"], self.refusals(sent)), (UNOPENED, 1))


class DataRecordOfInit1Test(DataFileHoldingTestCase):
    """A data record whose `init` is 1, as the Nextion Editor's simulator ran
    it: it opens no file until code sets its `path`, and then works as at 0
    (test_data_records.py for its methods)."""

    def setUp(self):
        super().setUp()
        self.page("page0", [self.record("d0", 10, init=1)])
        self.page("second", [])
        self.card = Path(self._folder.name) / "card"
        self.card.mkdir()
        self.three = (DataRecordTest.FIXTURES / "three.data").read_bytes()
        (self.card / "1.data").write_bytes(self.three)

    def record(self, name: str, x: int, **values) -> str:
        return table(name, "data-record", x=x, y=10, w=250, h=140, path="sd0/1.data",
                     dir="A^B", dez=2, mode=1, **values)

    def started(self) -> tuple:
        sent = []
        return Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append), sent

    def shown(self, simulation: Simulation) -> tuple:
        """d0's records, as drawn, then its `qty`, `val`, and `txt`."""
        values = simulation.values()
        return simulation.listings()["d0"], values["d0.qty"], values["d0.val"], values["d0.txt"]

    def test_as_the_page_opens(self):
        # Its titles alone: the file neither read nor held, and no 0x06.
        simulation, sent = self.started()
        self.assertEqual((self.shown(simulation), self.refusals(sent)), (([], 0, -1, ""), 0))
        self.assertEqual(simulation.globals["data files held"], {})

    def test_another_record_naming_its_file_opens_it(self):
        self.page("page0", [self.record("d0", 10, init=1), self.record("d1", 270)])
        simulation, _ = self.started()
        listings = simulation.listings()
        self.assertEqual((listings["d0"], listings["d1"]), ([], ["a^1^x", "b^2^y", "c^3^z"]))

    def test_a_missing_file_is_not_made(self):
        (self.card / "1.data").unlink()
        simulation, sent = self.started()
        self.assertEqual((self.shown(simulation), self.refusals(sent)), (([], 0, -1, ""), 0))
        self.assertFalse((self.card / "1.data").exists())

    def test_its_methods_change_nothing(self):
        # Each counts as done.
        simulation, sent = self.started()
        simulation.serial_input("bkcmd=3")
        sent.clear()
        for line in ('d0.insert("d^4")', 'd0.up("e^5",0)', "d0.delete(0,1)", "d0.clear()"):
            simulation.serial_input(line)
        self.assertEqual(b"".join(sent), bytes.fromhex("01 ff ff ff") * 4)
        self.assertEqual(self.shown(simulation), ([], 0, -1, ""))
        self.assertTrue((self.card / "1.data").read_bytes() == self.three, "the file changed")

    def test_its_page_opening_again(self):
        simulation, _ = self.started()
        simulation.serial_input("page second")
        simulation.serial_input("page page0")
        self.assertEqual(self.shown(simulation), ([], 0, -1, ""))

    def test_a_path_code_sets_is_opened_as_at_0(self):
        # The same file, kept across pages; then a new file, made.
        simulation, _ = self.started()
        simulation.serial_input('d0.path="sd0/1.data"')
        three = ["a^1^x", "b^2^y", "c^3^z"]
        self.assertEqual(self.shown(simulation)[:2], (three, 3))
        simulation.serial_input("page second")
        simulation.serial_input("page page0")
        self.assertEqual(self.shown(simulation)[:2], (three, 3))
        simulation.serial_input('d0.path="sd0/2.data"')
        simulation.serial_input('d0.insert("d^4")')
        self.assertEqual(self.shown(simulation)[:2], (["d^4"], 1))
        self.assertTrue((self.card / "2.data").exists())

    def test_a_start_again_opens_nothing_again(self):
        simulation, _ = self.started()
        simulation.serial_input('d0.path="sd0/1.data"')
        simulation.start_again()
        self.assertEqual(self.shown(simulation), ([], 0, -1, ""))


class OutsideTest(SimulationTestCase):
    """What reaches outside the screen: recorded, and logged."""

    def setUp(self):
        super().setUp()
        self.program("int n=0\n\npage page0\n")
        self.page("page0", [placed("title", "text", 0, 0, txt="title", txt_maxl=8),
                            placed("save", "button", 0, 100),
                            placed("load", "button", 0, 200),
                            placed("pins", "button", 0, 300),
                            placed("again", "button", 200, 0)], """\
on save.down:
  n = 258
  wepo n,4
  wepo title.txt,10
  prints "ok",0

on load.down:
  title.txt = ""
  repo title.txt,10
  repo n,4
  get title.txt
  touch_j

on pins.down:
  cfgpio 1,0,save
  pio2 = 1
  n = pio1

on again.down:
  rest
""")
        self.page("second", [])

    def test_the_eeprom_written_and_read_back(self):
        simulation = Simulation(self.root)
        simulation.press("save")
        simulation.press("load")
        values = simulation.values()
        self.assertEqual((values["title.txt"], values["n"]), ("title", 258))
        self.assertEqual(values["eeprom"][4:19], bytes([2, 1, 0, 0, 0, 0]) + b"title\0\0\0\0")
        self.assertEqual([line for _, line in simulation.log], [
            "EEPROM: wrote 02 01 00 00 at 4",
            "EEPROM: wrote 74 69 74 6c 65 00 00 00 00 at 10",
            "sends 6f 6b",
            "EEPROM: read 'title' at 10", "EEPROM: read 258 at 4",
            "sends 70 74 69 74 6c 65 ff ff ff (get)",
            "not simulated: touch_j"])

    def test_the_eeprom_from_a_file_and_after_starting_again(self):
        # Starting again is a power cycle, as `rest` is: the EEPROM keeps
        # what the app wrote. No file is written without one named.
        before = sorted(self.root.parent.iterdir())
        simulation = Simulation(self.root, eeprom=bytes([0, 0, 0, 0, 7]))
        simulation.press("load")
        self.assertEqual(simulation.values()["n"], 7)
        simulation.press("save")
        simulation.start_again()
        self.assertEqual(simulation.globals["eeprom"][4:8], bytes([2, 1, 0, 0]))
        self.assertIn("started again, the EEPROM kept", [line for _, line in simulation.log])
        self.assertEqual(sorted(self.root.parent.iterdir()), before)

    def test_the_eeprom_kept_in_its_file(self):
        # As the Nextion Editor's simulator kept its EEPROM in its file: each
        # write, from code or typed on the serial line, reaches the file at
        # once, whole, and the next simulation starts from it. A file that
        # does not exist is made, empty.
        path = self.root.parent / "eeprom.bin"
        eeprom, made = simulation_module.read_eeprom_file(path)
        self.assertTrue(made)
        self.assertEqual(path.read_bytes(), bytes(editor_machine.EEPROM_SIZE))
        simulation = Simulation(self.root, eeprom=eeprom, eeprom_file=path)
        simulation.press("save")
        self.assertEqual(path.read_bytes()[4:8], bytes([2, 1, 0, 0]))
        simulation.serial_input("wepo 9,20")
        self.assertEqual(path.read_bytes()[20], 9)
        simulation.start_again()
        self.assertEqual(simulation.globals["eeprom"][20], 9)
        eeprom, made = simulation_module.read_eeprom_file(path)
        self.assertFalse(made)
        again = Simulation(self.root, eeprom=eeprom, eeprom_file=path)
        again.press("load")
        self.assertEqual(again.values()["n"], 258)

    def test_a_write_the_eeprom_file_refuses(self):
        # Logged, the simulation goes on, and the next write puts the whole
        # EEPROM in the file.
        path = self.root.parent / "eeprom.bin"
        path.write_bytes(bytes(editor_machine.EEPROM_SIZE))
        os.chmod(path, 0o444)
        try:
            simulation = Simulation(self.root, eeprom=path.read_bytes(), eeprom_file=path)
            simulation.press("save")
        finally:
            os.chmod(path, 0o666)
        self.assertTrue(any("could not be written" in line for _, line in simulation.log))
        self.assertEqual(path.read_bytes(), bytes(editor_machine.EEPROM_SIZE))
        simulation.serial_input("wepo 9,20")
        data = path.read_bytes()
        self.assertEqual((data[4], data[20]), (2, 9))

    def test_an_eeprom_file_that_will_not_do(self):
        # A file longer than the EEPROM, which writing it back would cut, and
        # one in a folder there is not: the launch stops, and nothing is
        # written.
        path = self.root.parent / "eeprom.bin"
        path.write_bytes(bytes(editor_machine.EEPROM_SIZE + 1))
        with self.assertRaisesRegex(NxwrightError, "1025 bytes"):
            simulation_module.read_eeprom_file(path)
        self.assertEqual(len(path.read_bytes()), editor_machine.EEPROM_SIZE + 1)
        with self.assertRaisesRegex(NxwrightError, "cannot be made"):
            simulation_module.read_eeprom_file(self.root.parent / "absent" / "eeprom.bin")

    def test_rest_starts_again_keeping_the_eeprom(self):
        simulation = Simulation(self.root)
        simulation.press("save")
        simulation.press("again")
        self.assertEqual((simulation.page, simulation.globals["n"]), ("page0", 0))
        self.assertEqual(simulation.starts, 2)      # its first page is drawn over black
        self.assertEqual(simulation.globals["eeprom"][4], 2)

    def test_what_the_screen_sends_goes_to_sending_in_order(self):
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.press("save")
        simulation.press("load")
        for text in ("printh 0d 0a", "xyz"):
            simulation.serial_input(text)
        # prints, get's reply, printh, and the failure code of an instruction
        # it does not know, which bkcmd 2 sends.
        self.assertEqual(sent, [b"ok", b"\x70title\xff\xff\xff", b"\r\n", b"\x00\xff\xff\xff"])

    def test_a_file_stream_of_any_name_typed_in(self):
        # Opening a file stores no new name of the app, so the screen
        # answers with success; so it answered for a file the card lacks,
        # opening nothing, which is recorded.
        self.page("page0", [placed("title", "text", 0, 0), table("fs0", "file-stream")])
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        for text in ("bkcmd=3", 'fs0.open("sd0/a.txt")'):
            simulation.serial_input(text)
        self.assertEqual(sent[-1], b"\x01\xff\xff\xff")
        self.assertIsNone(simulation.globals["open file fs0"])
        self.assertEqual(simulation.values()["file errors"], [("open", "sd0/a.txt")])

    def test_what_could_not_be_sent_is_logged(self):
        simulation = Simulation(self.root, sending=lambda data: "not sent")
        simulation.press("save")
        self.assertEqual([line for _, line in simulation.log][-2:], ["sends 6f 6b", "not sent"])

    def test_bytes_from_the_serial_line_in_the_project_encoding(self):
        simulation = Simulation(self.root)
        simulation.serial_received('title.txt="é"'.encode("iso-8859-1") + b"\xff\xff\xff")
        self.assertEqual(simulation.values()["title.txt"], "é")
        # Bytes a project in utf-8 cannot read are an invalid instruction.
        self.write("app.toml", self.text("app.toml").replace("iso-8859-1", "utf-8"))
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_received(b"title.txt=\"\xe9\"\xff\xff\xff")
        self.assertEqual(sent, [b"\x00\xff\xff\xff"])
        self.assertEqual([line for _, line in simulation.log][0],
                         "receives 74 69 74 6c 65 2e 74 78 74 3d 22 e9 22, which utf-8 cannot read")

    def test_the_serial_line_cuts_its_pieces_into_instructions(self):
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        # One instruction across two pieces, then two in one.
        for piece in (b'title.txt="a', b'b"\xff\xff\xffget title.txt\xff\xff\xffn=', b"3"):
            simulation.serial_received(piece)
        self.assertEqual(simulation.values()["title.txt"], "ab")
        self.assertEqual(sent, [b"\x70ab\xff\xff\xff"])
        self.assertEqual([line for _, line in simulation.log],
                         ['receives title.txt="ab"', "receives get title.txt",
                          "sends 70 61 62 ff ff ff (get)"])

    def test_bytes_never_ended_are_dropped_and_logged(self):
        simulation = Simulation(self.root)
        simulation.serial_received(b"x" * (MOST_WAITING + 1))
        simulation.serial_received(b"n=4\xff\xff\xff")
        self.assertEqual([line for _, line in simulation.log],
                         ["serial line: dropped %d bytes with no FF FF FF after them"
                          % (MOST_WAITING + 1), "receives n=4"])

    def test_the_recording_is_the_same_when_steps_compare_only_what_changed(self):
        # Records, the EEPROM, a typed instruction, and starting again.
        assert_recorded_alike(self, lambda simulation: (
            [simulation.press(button) for button in ("save", "load", "pins")],
            simulation.serial_input('title.txt="typed"'), simulation.press("again")))

    def test_gpio(self):
        # pio2, a pull-up input since power-on, keeps its level, and pio1, a
        # pull-up input nothing drives, reads 1 (GpioTest).
        simulation = Simulation(self.root)
        simulation.press("pins")
        self.assertEqual([line for _, line in simulation.log], [
            "GPIO: pin 1 set to mode 0, for save", "GPIO: pio2 is an input, and keeps its level",
            "GPIO: pio1 read as 1"])

    def test_serial_input(self):
        simulation = Simulation(self.root)
        for text in ('title.txt="typed"', "get title.txt", "nothing.txt=1", "xyz",
                     "bkcmd=3", "n=1"):
            simulation.serial_input(text)
        self.assertEqual(simulation.values()["title.txt"], "typed")
        self.assertEqual([line for _, line in simulation.log], [
            'receives title.txt="typed"', "receives get title.txt",
            "sends 70 74 79 70 65 64 ff ff ff (get)",
            "receives nothing.txt=1", "sends 1a ff ff ff",
            "receives xyz", "sends 00 ff ff ff",
            "receives bkcmd=3", "sends 01 ff ff ff",
            "receives n=1", "sends 01 ff ff ff"])

    def test_the_logs_formats(self):
        # By default what the screen receives shows as text, and what it
        # sends in hexadecimal. As text, the FF FF FF ending them is left
        # out, and a byte that is no character shows as \xNN.
        received = ["74 69 74 6c 65 2e 74 78 74 3d 22 74 79 70 65 64 22 ff ff ff",
                    "67 65 74 20 74 69 74 6c 65 2e 74 78 74 ff ff ff",
                    "62 6b 63 6d 64 3d 33 ff ff ff"]
        for formats, lines in (
                ({"received": "hex", "sent": "text"},
                 ["receives " + received[0], "receives " + received[1], "sends ptyped (get)",
                  "receives " + received[2], r"sends \x01"]),
                ({"received": "both", "sent": "both"},
                 ['receives title.txt="typed" (%s)' % received[0],
                  "receives get title.txt (%s)" % received[1],
                  "sends ptyped (70 74 79 70 65 64 ff ff ff) (get)",
                  "receives bkcmd=3 (%s)" % received[2], r"sends \x01 (01 ff ff ff)"])):
            with self.subTest(formats=formats):
                simulation = Simulation(self.root, log_formats=formats)
                for text in ('title.txt="typed"', "get title.txt", "bkcmd=3"):
                    simulation.serial_input(text)
                self.assertEqual([line for _, line in simulation.log], lines)

    def test_the_editors_serial_answers(self):
        # As the Editor's simulator answered, page 1 having a load event.
        self.write("pages/second.nx", 'on second.load:\n  prints "L",0\n')
        simulation = Simulation(self.root)
        sent = []
        for text, answer in (('title.txt="typed"', []),
                             ("get title.txt", ["sends 70 74 79 70 65 64 ff ff ff (get)"]),
                             ("get n", ["sends 71 00 00 00 00 ff ff ff (get)"]),
                             ("xyz", ["sends 00 ff ff ff"]),
                             ("bkcmd=3", ["sends 01 ff ff ff"]),
                             ('title.txt="again"', ["sends 01 ff ff ff"]),
                             ("sendme", ["sends 66 00 ff ff ff (sendme)"]),
                             ("page second", ["sends 4c"])):
            with self.subTest(text=text):
                before = len(simulation.log)
                simulation.serial_input(text)
                sent = [line for _, line in simulation.log[before:]]
                self.assertEqual(sent, ["receives " + text] + answer)

    def test_covx_to_hex_of_an_odd_length_answers_1b(self):
        # As the Editor's simulator answered, leaving the text as it was: an
        # odd length is not a whole number of bytes.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_input("bkcmd=3")
        simulation.serial_input("covx 255,title.txt,3,2")
        self.assertEqual((sent[-1], simulation.values()["title.txt"]),
                         (b"\x1b\xff\xff\xff", "title"))
        simulation.serial_input("covx 255,title.txt,2,2")
        self.assertEqual((sent[-1], simulation.values()["title.txt"]), (b"\x01\xff\xff\xff", "FF"))

    def test_a_text_the_encoding_cannot_write_is_logged(self):
        simulation = Simulation(self.root)
        simulation.serial_input('prints "\u0101",0')
        self.assertEqual([line for _, line in simulation.log][-1],
                         "sends '\u0101', which iso-8859-1 cannot write")

    def test_a_page_change_typed(self):
        simulation = Simulation(self.root)
        simulation.serial_input("page second")
        self.assertEqual(simulation.page, "second")

    def test_rest_typed_starts_again_at_once(self):
        simulation = Simulation(self.root)
        simulation.serial_input("n=5")
        simulation.serial_input("rest")
        self.assertEqual(simulation.globals["n"], 0)
        self.assertIn("rest: the screen starts again", [line for _, line in simulation.log])

    def test_a_press_before_any_page(self):
        self.program("int n=0\n")
        simulation = Simulation(self.root)
        self.assertIsNone(simulation.component_at(0, 0))
        simulation.press(None)
        simulation.release()
        self.assertIsNone(simulation.page)


READY, DONE = b"\xfe\xff\xff\xff", b"\xfd\xff\xff\xff"
N_IS_0 = b"\x71\x00\x00\x00\x00\xff\xff\xff"


class TransparentDataTest(SimulationTestCase):
    """addt and wept take their data from the serial line, as the Nextion
    Editor's simulator took it, but for the bytes after the data, which are
    instructions again."""

    def setUp(self):
        super().setUp()
        self.program("int n=0\n\npage page0\n")
        self.page("page0", [table("chart", "waveform", x=0, y=100, w=20, h=50, ch=1),
                            placed("go", "button", 300, 0),
                            placed("none", "button", 300, 200)], """\
on go.down:
  addt chart.id,0,2

on none.down:
  wept 4,0
""")
        self.page("second", [])
        self.sent = []

    def simulation(self, **given) -> Simulation:
        simulation = Simulation(self.root, sending=self.sent.append, **given)
        self.assertEqual(simulation.values()["chart.id"], 1)
        return simulation

    def test_addt_takes_its_points_from_the_serial_line(self):
        simulation = self.simulation()
        simulation.serial_received(b"addt 1,0,3\xff\xff\xff\x0a\xff")
        self.assertEqual(self.sent, [READY])
        # FF is data. The bytes after the third are an instruction.
        simulation.serial_received(b"\x14get n\xff\xff\xff")
        self.assertEqual(self.sent, [READY, DONE, N_IS_0])
        self.assertEqual(simulation.waves(), {"chart": {0: [10, 255, 20]}})
        self.assertEqual([line for _, line in simulation.log], [
            "receives addt 1,0,3",
            "addt: the next 3 bytes are points of channel 0 of the waveform of ID 1",
            "sends fe ff ff ff", "sends fd ff ff ff", "receives get n",
            "sends 71 00 00 00 00 ff ff ff (get)"])

    def test_addt_run_by_code(self):
        simulation = self.simulation()
        simulation.press("go")
        simulation.serial_received(b"\x05\x06")
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.waves(), {"chart": {0: [5, 6]}})

    def test_wept_writes_the_eeprom_and_its_file(self):
        path = self.root.parent / "eeprom.bin"
        simulation = self.simulation(eeprom_file=path)
        simulation.serial_received(b"wept 10,3\xff\xff\xffABC")
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.globals["eeprom"][10:13], b"ABC")
        self.assertEqual(path.read_bytes()[10:13], b"ABC")
        self.assertIn("EEPROM: wrote 41 42 43 at 10", [line for _, line in simulation.log])
        # A range past the EEPROM's last byte is taken, and writes nothing.
        simulation.serial_received(b"wept 1023,3\xff\xff\xffXYZ")
        self.assertEqual(self.sent, [READY, DONE] * 2)
        self.assertEqual(simulation.globals["eeprom"][1023], 0)
        self.assertEqual([line for _, line in simulation.log][-1],
                         "wept: the EEPROM has no byte 1024, so nothing was written")

    def test_refusals_start_no_transfer(self):
        simulation = self.simulation()
        # The wrong count of arguments, as the Nextion Editor's simulator
        # answered: "Invalid number of arguments".
        for text in ("addt 9,0,3", "addt 1,5,3", "addt 1,0,1025", "wept -1,3", "addt 1,0",
                     "wept 0", "get n"):
            simulation.serial_received(text.encode() + b"\xff\xff\xff")
        self.assertEqual(self.sent, [b"\x12\xff\xff\xff"] * 3 + [b"\x1d\xff\xff\xff"]
                         + [b"\x1e\xff\xff\xff"] * 2 + [N_IS_0])
        simulation.serial_received(b"addt 1,0,1024\xff\xff\xff")
        self.assertEqual(self.sent[-1], READY)

    def test_a_count_of_0_answers_at_once(self):
        simulation = self.simulation()
        simulation.serial_received(b"addt 1,0,0\xff\xff\xffget n\xff\xff\xff")
        self.assertEqual(self.sent, [READY, DONE, N_IS_0])
        # A transfer of 0 bytes that code starts ends the one under way, and
        # writes nothing: what follows is an instruction again.
        simulation.serial_received(b"wept 0,3\xff\xff\xff")
        simulation.press("none")
        simulation.serial_received(b"get n\xff\xff\xff")
        self.assertEqual(self.sent[3:], [READY, READY, DONE, N_IS_0])
        log = [line for _, line in simulation.log]
        self.assertIn("serial line: the transfer under way ends, 3 bytes short", log)
        self.assertFalse([line for line in log if line.startswith("EEPROM")])

    def test_ready_and_done_whatever_bkcmd_asks(self):
        simulation = self.simulation()
        simulation.serial_received(b"bkcmd=0\xff\xff\xffwept 0,1\xff\xff\xff\x07")
        self.assertEqual(self.sent, [READY, DONE])

    def test_a_start_empties_the_line(self):
        simulation = self.simulation()
        # A transfer under way ends: what follows is an instruction.
        simulation.serial_received(b"addt 1,0,3\xff\xff\xff\x01")
        simulation.start_again()
        simulation.serial_received(b"n=5\xff\xff\xff")
        self.assertEqual(simulation.globals["n"], 5)
        # The bytes of an instruction not yet ended are dropped.
        simulation.serial_received(b"n=")
        simulation.start_again()
        simulation.serial_received(b"6\xff\xff\xff")
        self.assertEqual((simulation.globals["n"], self.sent[-1]), (0, b"\x00\xff\xff\xff"))
        # So are the instructions after `rest` in its piece.
        simulation.serial_received(b"n=4\xff\xff\xffrest\xff\xff\xffn=7\xff\xff\xff")
        log = [line for _, line in simulation.log]
        self.assertIn("receives n=4", log)
        self.assertNotIn("receives n=7", log)

    def test_a_typed_instruction_in_a_transfer_is_data(self):
        simulation = self.simulation()
        simulation.serial_received(b"addt 1,0,9\xff\xff\xff")
        simulation.serial_input("get n")
        # Text the project's encoding cannot store arrives not at all.
        simulation.serial_input('n="Ж"')
        self.assertEqual(self.sent, [READY])
        simulation.serial_received(b"\x01")
        self.assertEqual(self.sent, [READY, DONE])
        self.assertEqual(simulation.waves(), {"chart": {0: list(b"get n\xff\xff\xff\x01")}})
        log = [line for _, line in simulation.log]
        self.assertIn("receives get n as bytes, not as an instruction", log)
        self.assertIn("receives nothing: the instruction: iso-8859-1 cannot store 'Ж'", log)


class ReparseModeTest(SimulationTestCase):
    """Protocol reparse mode, as the Nextion Editor's simulator ran it: with
    `recmod` not 0, every byte of the serial line goes into the buffer that
    code reads."""

    def setUp(self):
        super().setUp()
        self.program("int n=0\n\npage page0\n")
        self.page("page0", [placed("n0", "number", 0, 0), placed("n1", "number", 0, 50),
                            placed("t0", "text", 0, 100, txt="", txt_maxl=20),
                            placed("read", "button", 300, 0),
                            placed("crc", "button", 300, 100),
                            placed("mode", "button", 300, 200),
                            placed("off", "button", 300, 300),
                            placed("copy", "button", 300, 400)], """\
on read.down:
  n0.val=usize
  n1.val=u[0]
  ucopy t0.txt,0,3,0
  udelete 2

on crc.down:
  crcrest 1,0xFFFF
  crcputu 0,3
  n0.val=crcval

on mode.down:
  recmod=1

on off.down:
  recmod=0

on copy.down:
  ucopy n1.val,0,4,0
""")
        self.page("second", [])
        self.sent = []
        self.simulation = Simulation(self.root, sending=self.sent.append)

    def test_a_typed_click_whose_event_turns_the_mode_on_answers_first(self):
        # As the Nextion Editor's simulator answered: with bkcmd 3, the
        # click's success, as a typed click answers before its event runs;
        # then the next instruction goes into the buffer, unanswered.
        self.sent.clear()
        for line in ("bkcmd=3", "click mode,1", "get n"):
            self.simulation.serial_input(line)
        self.assertEqual(self.sent, [b"\x01\xff\xff\xff"] * 2)
        self.assertEqual(self.simulation.values()["serial buffer"], b"get n\xff\xff\xff")

    def test_the_end_of_the_mode_empties_the_buffer(self):
        # The Nextion Editor's simulator kept nothing of the buffer once the
        # mode ended, by its text or by code. While the mode was off, ucopy
        # copied nothing: a number given 12345 kept it.
        simulation = self.simulation
        simulation.serial_received(b"recmod=1\xff\xff\xffABCD"
                                   b"DRAKJHSUYDGBNCJHGJKSHBDN\xff\xff\xff")
        self.assertEqual(simulation.globals["serial buffer"], b"")
        simulation.press("mode")
        simulation.serial_received(b"EFGH")
        simulation.press("off")
        self.assertEqual(simulation.globals["serial buffer"], b"")
        simulation.serial_input("n1.val=12345")
        simulation.press("copy")
        self.assertEqual(simulation.values()["n1.val"], 12345)

    def test_every_byte_goes_into_the_buffer_until_the_text_ending_the_mode(self):
        simulation = self.simulation
        # recmod=1 does not answer its success: the line takes bytes by then.
        simulation.serial_received(b"bkcmd=3\xff\xff\xffrecmod=1\xff\xff\xffget 1\xff\xff\xff")
        simulation.serial_input('n=1')
        self.assertEqual(simulation.globals["serial buffer"], b"get 1\xff\xff\xffn=1\xff\xff\xff")
        self.assertEqual(self.sent, [b"\x01\xff\xff\xff"])
        simulation.press("read")
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["n1.val"], values["t0.txt"]), (14, 103, "get"))
        self.assertEqual(simulation.globals["serial buffer"], b"t 1\xff\xff\xffn=1\xff\xff\xff")
        simulation.serial_received(b"DRAKJHSUYDGBNCJHGJKSHBDN\xff\xff\xffget recmod\xff\xff\xff")
        self.assertEqual(self.sent[1:], [N_IS_0])
        self.assertIn("recmod: protocol reparse mode ends", [line for _, line in simulation.log])

    def test_crcputu_adds_bytes_that_arrived(self):
        # The CRC of "get", as the Nextion Editor's simulator gave it.
        simulation = self.simulation
        simulation.serial_received(b"recmod=1\xff\xff\xffget 1\xff\xff\xff")
        simulation.press("crc")
        self.assertEqual(simulation.values()["n0.val"], 26859)

    def test_reads_while_the_mode_is_off(self):
        # Each read answers 0x1A, and gives 0. ucopy and udelete run.
        self.simulation.press("read")
        self.assertEqual(self.sent, [b"\x1a\xff\xff\xff"] * 2)
        self.assertEqual(self.simulation.values()["n0.val"], 0)

    def test_code_turning_the_mode_on_drops_an_instruction_not_ended(self):
        self.simulation.serial_received(b"ab")
        self.simulation.press("mode")
        self.simulation.serial_received(b"cd\xff\xff\xff")
        self.assertEqual(self.simulation.globals["serial buffer"], b"cd\xff\xff\xff")

    def test_a_start_value_turns_the_mode_on(self):
        simulation = Simulation(self.root, "page0", {"recmod": 1}, sending=self.sent.append)
        simulation.serial_received(b"get 1\xff\xff\xff")
        self.assertEqual((simulation.globals["serial buffer"], self.sent),
                         (b"get 1\xff\xff\xff", []))

    def test_the_buffer_keeps_1024_bytes(self):
        # The screen's serial buffer, as the vendor gives it. Past it, the
        # bytes are dropped, and the screen answers 0x24 once for each piece
        # that overflowed.
        simulation = self.simulation
        simulation.serial_received(b"recmod=1\xff\xff\xff" + b"x" * 1030)
        simulation.serial_received(b"yz")
        self.assertEqual(simulation.globals["serial buffer"], b"x" * 1024)
        self.assertEqual(self.sent, [b"\x24\xff\xff\xff"] * 2)
        self.assertEqual([line for _, line in simulation.log][-2:],
                         ["serial line: the serial buffer overflowed, 2 bytes of protocol "
                          "reparse mode dropped", "sends 24 ff ff ff"])

    def test_a_start_empties_the_buffer_and_ends_the_mode(self):
        simulation = self.simulation
        simulation.serial_received(b"recmod=1\xff\xff\xffab")
        simulation.start_again()
        self.assertEqual((simulation.globals["serial buffer"], simulation.globals["recmod"]),
                         (b"", 0))
        simulation.serial_received(b"get recmod\xff\xff\xff")
        self.assertEqual(self.sent, [N_IS_0])


class AddressModeTest(SimulationTestCase):
    """Address mode, as the Nextion Editor's simulator ran it: with `addr`
    set, an instruction of the serial line runs only after the screen's
    address, low byte first, or FF FF."""

    def setUp(self):
        super().setUp()
        self.program("int n=0\n\npage page0\n")
        self.page("page0", [])
        self.page("second", [])
        self.sent = []
        self.simulation = Simulation(self.root, sending=self.sent.append)

    def test_an_instruction_counts_only_with_the_screens_address(self):
        simulation = self.simulation
        simulation.serial_received(b"addr=258\xff\xff\xff")
        simulation.serial_received(b"\x02\x01get n\xff\xff\xff\x01\x02get n\xff\xff\xff"
                                   b"\xff\xffget n\xff\xff\xffget n\xff\xff\xff")
        # The answers carry no address.
        self.assertEqual(self.sent, [N_IS_0, N_IS_0])
        log = [line for _, line in simulation.log]
        self.assertIn("addr: address mode is on, for the address 258", log)
        self.assertIn("serial line: dropped 01 02 67 65 74 20 6e, without the screen's address",
                      log)
        self.assertIn("serial line: dropped 67 65 74 20 6e, without the screen's address", log)
        # addr=0, sent with the address, ends the mode.
        simulation.serial_received(b"\x02\x01addr=0\xff\xff\xffget n\xff\xff\xff")
        self.assertEqual(self.sent, [N_IS_0] * 3)

    def test_a_typed_instruction_reaches_the_screen(self):
        simulation = self.simulation
        simulation.serial_input("addr=258")
        simulation.serial_input("get n")
        simulation.serial_input("addr=0")
        simulation.serial_received(b"get n\xff\xff\xff")
        self.assertEqual(self.sent, [N_IS_0] * 2)

    def test_an_address_out_of_range_leaves_the_mode_off(self):
        self.simulation.serial_input("addr=100")
        self.simulation.serial_received(b"get n\xff\xff\xff")
        self.assertEqual(self.sent, [b"\x1c\xff\xff\xff", N_IS_0])

    def test_a_start_sets_addr_to_0(self):
        simulation = self.simulation
        simulation.serial_input("addr=258")
        simulation.start_again()
        simulation.serial_received(b"get n\xff\xff\xff")
        self.assertEqual((simulation.globals["addr"], self.sent), (0, [N_IS_0]))

    def test_a_start_value_turns_the_mode_on(self):
        simulation = Simulation(self.root, "page0", {"addr": 258}, sending=self.sent.append)
        simulation.serial_received(b"get n\xff\xff\xff\x02\x01get n\xff\xff\xff")
        self.assertEqual(self.sent, [N_IS_0])


class GpioTest(SimulationTestCase):
    """The GPIO pins, as the vendor describes them:
    an input reads its level, 1 when nothing drives it, and a bound pin's
    edges run its component's Press and Release events."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program("int n=0,ups=0\npage page0\n")
        self.page("page0", [placed("b0", "button", 0, 0)],
                  "on b0.down:\n  n=n+1\n\non b0.up:\n  ups=ups+1\n")
        self.page("second", [placed("b0", "button", 0, 0)])

    def read(self, simulation: Simulation, pin: int) -> int:
        simulation.serial_input("n=pio%d" % pin)
        return simulation.globals["n"]

    def test_an_input_nothing_drives_reads_1(self):
        # Every pin is a pull-up input at power-on.
        simulation = Simulation(self.root)
        self.assertEqual([self.read(simulation, pin) for pin in range(8)], [1] * 8)

    def test_a_level_set_reads_back(self):
        simulation = Simulation(self.root)
        simulation.set_input(0, 0)
        self.assertEqual(self.read(simulation, 0), 0)
        self.assertEqual(simulation.pins()[0], {"mode": 0, "component": None, "level": 0})

    def test_a_write_to_an_input_changes_nothing(self):
        simulation = Simulation(self.root)
        simulation.serial_input("pio3=0")
        self.assertEqual(self.read(simulation, 3), 1)
        self.assertNotIn(("write", "pio3", 0), simulation.values()["gpio"])
        self.assertIn("GPIO: pio3 is an input, and keeps its level",
                      [line for _, line in simulation.log])

    def test_an_output_reads_what_was_written(self):
        simulation = Simulation(self.root)
        for line in ("cfgpio 1,2,0", "pio1=0"):
            simulation.serial_input(line)
        simulation.set_input(1, 1)
        self.assertEqual(self.read(simulation, 1), 0)
        # The pins' view shows what the output reads, not the level outside.
        self.assertEqual(simulation.pins()[1], {"mode": 2, "component": None, "level": 0})

    def test_a_bound_pin_runs_press_and_release(self):
        simulation = Simulation(self.root)
        simulation.serial_input("cfgpio 2,1,b0")
        simulation.set_input(2, 0)
        self.assertEqual((simulation.globals["n"], simulation.globals["ups"]), (1, 0))
        simulation.set_input(2, 0)              # no edge
        simulation.set_input(2, 1)
        self.assertEqual((simulation.globals["n"], simulation.globals["ups"]), (1, 1))
        self.assertEqual(simulation.pins()[2], {"mode": 1, "component": "b0", "level": 1})

    def test_a_pin_bound_by_id(self):
        simulation = Simulation(self.root)
        simulation.serial_input("cfgpio 2,1,1")     # b0, after the page itself
        simulation.set_input(2, 0)
        self.assertEqual(simulation.globals["n"], 1)

    def test_binding_runs_nothing(self):
        simulation = Simulation(self.root)
        simulation.set_input(2, 0)
        simulation.serial_input("cfgpio 2,1,b0")
        self.assertEqual(simulation.globals["n"], 0)
        simulation.set_input(2, 1)
        self.assertEqual(simulation.globals["ups"], 1)

    def test_a_page_change_ends_the_binding_and_keeps_the_modes(self):
        simulation = Simulation(self.root)
        for line in ("cfgpio 2,1,b0", "cfgpio 1,2,0", "page second", "page page0"):
            simulation.serial_input(line)
        simulation.set_input(2, 0)
        self.assertEqual(simulation.globals["n"], 0)
        self.assertEqual([simulation.pins()[pin] for pin in (1, 2)],
                         [{"mode": 2, "component": None, "level": 1},
                          {"mode": 1, "component": None, "level": 0}])

    def test_levels_outlive_a_start_again_and_rest(self):
        simulation = Simulation(self.root)
        simulation.set_input(4, 0)
        simulation.start_again()
        self.assertEqual(self.read(simulation, 4), 0)
        simulation.serial_input("rest")
        self.assertEqual(self.read(simulation, 4), 0)

    def test_starting_levels(self):
        simulation = Simulation(self.root, inputs={"pio6": 0})
        self.assertEqual(self.read(simulation, 6), 0)
        # A pio start value gives the level too, at the launch alone.
        simulation = Simulation(self.root, values={"pio5": 0})
        self.assertEqual(self.read(simulation, 5), 0)
        simulation.set_input(5, 1)
        simulation.start_again()
        self.assertEqual(self.read(simulation, 5), 1)

    def test_two_starting_levels_of_one_pin_must_agree(self):
        simulation = Simulation(self.root, inputs={"pio1": 0}, values={"pio1": 0})
        self.assertEqual(self.read(simulation, 1), 0)
        with self.assertRaisesRegex(NxwrightError, "pio1 starts at 0 in the inputs, and at 1"):
            Simulation(self.root, inputs={"pio1": 0}, values={"pio1": 1})

    def test_a_cfgpio_out_of_range_changes_no_pin(self):
        # A pin past io7, a mode past 4, and PWM, which io4 to io7 alone take.
        simulation = Simulation(self.root)
        for line in ("cfgpio 9,2,0", "cfgpio 0,5,0", "cfgpio 0,3,0"):
            simulation.serial_input(line)
        self.assertEqual([pin["mode"] for pin in simulation.pins()], [0] * 8)

    def test_a_basic_screen_takes_no_level(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        simulation = Simulation(self.root)
        self.assertIsNone(simulation.pins())
        with self.assertRaisesRegex(NxwrightError, "no GPIO"):
            simulation.set_input(0, 0)
        with self.assertRaisesRegex(NxwrightError, "no GPIO"):
            Simulation(self.root, inputs={"pio0": 0})

    def test_a_level_is_0_or_1_of_a_pin_from_0_to_7(self):
        simulation = Simulation(self.root)
        with self.assertRaisesRegex(NxwrightError, "0 or 1"):
            simulation.set_input(0, 2)
        with self.assertRaisesRegex(NxwrightError, "pio0 to pio7"):
            Simulation(self.root, inputs={"pio8": 0})


class SeveralGpioInputsTest(SimulationTestCase):
    """Several GPIO inputs set in one step, as buttons pressed together:
    every level changes before any bound pin's event runs, and the events
    run in pin order."""
    language = "nextion"

    def bound(self, code: str, *bindings: str) -> Simulation:
        """A simulation of page0, whose buttons b0 and b1 have `code`, with
        the pins bound by `bindings`, such as "cfgpio 2,1,b0"."""
        self.program("int n=0,m=0\npage page0\n")
        self.page("page0", [placed("b0", "button", 0, 0), placed("b1", "button", 0, 100)],
                  code)
        self.page("second", [placed("b0", "button", 0, 0)])
        simulation = Simulation(self.root)
        for line in bindings:
            simulation.serial_input(line)
        return simulation

    def test_each_event_reads_the_other_pins_new_level(self):
        simulation = self.bound("on b0.down:\n  n=pio3\n\non b1.down:\n  m=pio2\n",
                                "cfgpio 2,1,b0", "cfgpio 3,1,b1")
        simulation.set_inputs({2: 0, 3: 0})
        self.assertEqual((simulation.globals["n"], simulation.globals["m"]), (0, 0))
        self.assertEqual([pin["level"] for pin in simulation.pins()], [1, 1, 0, 0, 1, 1, 1, 1])

    def test_the_events_run_in_pin_order(self):
        simulation = self.bound("on b0.down:\n  n=n*10+1\n\non b1.down:\n  n=n*10+2\n",
                                "cfgpio 5,1,b0", "cfgpio 2,1,b1")
        simulation.set_inputs({5: 0, 2: 0})
        self.assertEqual(simulation.globals["n"], 21)
        # Rising, each runs its Release event, which these buttons lack.
        simulation.set_inputs({5: 1, 2: 1})
        self.assertEqual(simulation.globals["n"], 21)

    def test_an_event_changing_the_page_ends_a_later_pins_binding(self):
        simulation = self.bound("on b0.down:\n  n=n+1\n\non b1.down:\n  page second\n",
                                "cfgpio 5,1,b0", "cfgpio 2,1,b1")
        simulation.set_inputs({2: 0, 5: 0})
        self.assertEqual((simulation.page, simulation.globals["n"]), ("second", 0))

    def test_an_event_binding_a_later_pin_again_runs_nothing_for_it(self):
        # Even bound to the same component: a binding made after a change
        # of level sees no edge.
        for again in ("cfgpio 5,1,b0", "cfgpio 5,1,b1"):
            with self.subTest(again=again):
                simulation = self.bound("on b0.down:\n  n=n+1\n\non b1.down:\n  m=m+1\n  %s\n"
                                        % again, "cfgpio 5,1,b0", "cfgpio 2,1,b1")
                simulation.set_inputs({2: 0, 5: 0})
                self.assertEqual((simulation.globals["m"], simulation.globals["n"]), (1, 0))

    def test_an_error_in_an_event_leaves_no_later_event_waiting(self):
        # b1's event divides by sys0, which is 0, so pin 5's event never runs
        # in that step. It does not run in the next step either, whose own
        # pin, 6, is bound to nothing.
        simulation = self.bound("on b0.down:\n  n=n+1\n\non b1.down:\n  m=1/sys0\n",
                                "cfgpio 5,1,b0", "cfgpio 2,1,b1")
        with self.assertRaises(ZeroDivisionError):
            simulation.set_inputs({2: 0, 5: 0})
        simulation.set_inputs({6: 0})
        self.assertEqual(simulation.globals["n"], 0)

    def test_one_wrong_entry_changes_no_level(self):
        simulation = self.bound("")
        for levels, said in (({2: 0, 3: 2}, "0 or 1"), ({2: 0, 8: 0}, "from 0 to 7"),
                             ({}, "at least one")):
            with self.subTest(levels=levels):
                with self.assertRaisesRegex(NxwrightError, said):
                    simulation.set_inputs(levels)
                self.assertEqual([pin["level"] for pin in simulation.pins()], [1] * 8)

    def test_a_basic_screen_takes_no_level(self):
        self.bound("")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        with self.assertRaisesRegex(NxwrightError, "no GPIO"):
            Simulation(self.root).set_inputs({0: 0})


class TimeTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program("int ticks=0, other=0\n\npage page0\n")
        self.page("page0", [placed("go", "button", 0, 0), placed("nap", "button", 0, 100),
                            placed("start", "button", 0, 200),
                            table("tick", "timer", tim=500),
                            table("idle", "timer", tim=100, en=0)], """\
on tick.timer:
  ticks = ticks + 1

on idle.timer:
  other = other + 1

on go.down:
  delay = 1200

on nap.down:
  sleep = 1

on start.down:
  idle.en = 1
""")
        self.page("second", [table("away", "timer", tim=100)], """\
on away.timer:
  other = other + 1
""")

    def test_a_start_page_with_a_timer_turned_off(self):
        simulation = Simulation(self.root, "page0", {"tick.en": 0})
        simulation.advance(1600)
        self.assertEqual(simulation.globals["ticks"], 0)

    def test_timers_run_in_time(self):
        simulation = Simulation(self.root)
        simulation.advance(1600)
        self.assertEqual((simulation.clock, simulation.globals["ticks"]), (1600, 3))
        # A timer that is off, and one of a page not shown, do not run.
        self.assertEqual(simulation.globals["other"], 0)

    def test_a_timer_turned_on(self):
        simulation = Simulation(self.root)
        simulation.advance(50)
        simulation.press("start")
        simulation.advance(250)
        self.assertEqual(simulation.globals["other"], 2)

    def test_a_delay_lets_time_pass(self):
        simulation = Simulation(self.root)
        simulation.advance(100)
        simulation.press("go")
        self.assertEqual((simulation.clock, simulation.globals["ticks"]), (1300, 0))
        # The timer that fell due during the delay runs once.
        simulation.advance(0)
        self.assertEqual(simulation.globals["ticks"], 1)
        simulation.advance(500)
        self.assertEqual(simulation.globals["ticks"], 2)

    def test_the_real_time_clock_runs_with_the_simulation(self):
        simulation = Simulation(self.root, time=datetime(2000, 1, 1, 13, 59, 58))
        clock = ["rtc%d" % index for index in range(7)]
        self.assertEqual([simulation.values()[name] for name in clock],
                         [2000, 1, 1, 13, 59, 58, 6])       # a Saturday
        simulation.advance(2500)
        self.assertEqual([simulation.values()[name] for name in clock[3:6]], [14, 0, 0])
        simulation.serial_input("rtc3=8")
        simulation.serial_input("rtc1=13")      # no 13th month: ignored
        simulation.advance(60_000)
        self.assertEqual([simulation.values()[name] for name in clock[1:6]], [1, 1, 8, 1, 0])
        simulation.start_again()
        self.assertEqual(simulation.values()["rtc3"], 8)

    def test_sleeping_and_waking(self):
        simulation = Simulation(self.root)
        simulation.press("nap")
        self.assertTrue(simulation.asleep)
        simulation.press("start")
        self.assertTrue(simulation.asleep)      # thup is 0: a press does nothing
        # The timers stop while the screen sleeps.
        simulation.advance(2000)
        self.assertEqual(simulation.globals["ticks"], 0)
        simulation.release()
        simulation.globals["thup"] = 1
        # The touch wakes it as it ends, as the Editor's simulator sent 0x68
        # for the release, still asleep, then 0x87.
        simulation.press("start")
        self.assertTrue(simulation.asleep)
        simulation.release()
        self.assertFalse(simulation.asleep)
        simulation.advance(150)
        self.assertEqual(simulation.globals["other"], 0)    # the waking touch ran nothing
        # Awake, they count again from the waking.
        simulation.advance(400)
        self.assertEqual(simulation.globals["ticks"], 1)

    def test_woken_by_the_code_the_screen_is_idle_from_then(self):
        # Its thsp counts from the waking, as the Nextion Editor's simulator
        # counted it.
        simulation = Simulation(self.root, values={"thsp": 2})
        simulation.advance(2100)
        self.assertTrue(simulation.asleep)
        simulation.serial_input("sleep=0")
        self.assertFalse(simulation.asleep)
        simulation.advance(1000)
        self.assertFalse(simulation.asleep)

    def test_sleeping_when_idle(self):
        simulation = Simulation(self.root, values={"thsp": 2})
        simulation.advance(1900)
        self.assertFalse(simulation.asleep)
        simulation.advance(200)
        self.assertTrue(simulation.asleep)


class TouchCoordinatesTest(SimulationTestCase):
    """A press at a pixel of the page, as the simulator's panel makes one:
    tch0 to tch3, and what sendxy sends. The Editor's simulator showed each,
    a page's events printing tch0 to tch3, its Simulator Return list showing
    what it sent."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        # Each event keeps what it read of the touch coordinates.
        self.page("page0", [placed("go", "button", 100, 100)], """\
on go.down:
  sys0 = tch0
  sys1 = tch1

on go.up:
  sys2 = tch0
""")

    def test_a_touch_puts_its_place_in_tch0_to_tch3(self):
        simulation = Simulation(self.root)
        simulation.press("go", 120, 130)
        self.assertEqual([simulation.globals[name] for name in ("sys0", "sys1")], [120, 130])
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(4)],
                         [120, 130, 120, 130])
        simulation.move(150, 140)
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(4)],
                         [150, 140, 150, 140])
        # Released: tch0 and tch1 are 0, its up event reading them so; tch2
        # and tch3 keep the last place.
        simulation.release()
        self.assertEqual(simulation.globals["sys2"], 0)
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(4)],
                         [0, 0, 150, 140])

    def test_a_touch_stays_on_the_screen(self):
        # The screen's 800 by 480, turned on its side: the panel may report
        # a move past its edge, where a screen's touch never goes.
        self.write("app.toml", self.text("app.toml").replace("rotation = 0", "rotation = 90"))
        simulation = Simulation(self.root)
        simulation.press("go", 120, 130)
        simulation.move(-20, 900)
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(2)], [0, 799])

    def test_without_screen_settings_a_touch_stays_within_two_bytes(self):
        # A folder of a screen nxwright does not know gives no screen
        # settings in app.toml, so its screen's size is not known.
        app = "".join(line for line in self.text("app.toml").splitlines(keepends=True)
                      if line.split("=")[0].strip() not in DEVICE_KEYS)
        self.write("app.toml", app)
        simulation = Simulation(self.root)
        simulation.press("go", 120, 130)
        simulation.move(-20, 70_000)
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(2)],
                         [0, 0xFFFF])

    def test_a_press_by_name_alone_has_no_place(self):
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.release()
        self.assertEqual([simulation.globals["tch%d" % index] for index in range(4)], [0] * 4)

    def test_sendxy_sends_each_press_and_release(self):
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.press("go", 120, 130)
        self.assertEqual(sent, [])      # sendxy 0, the default: nothing
        simulation.release()
        simulation.serial_input("sendxy=1")
        simulation.press("go", 300, 400)
        simulation.release()
        self.assertEqual(sent, [b"\x67\x01\x2c\x01\x90\x01\xff\xff\xff",
                                b"\x67\x01\x2c\x01\x90\x00\xff\xff\xff"])
        self.assertIn("sends 67 01 2c 01 90 01 ff ff ff",
                      [line for _, line in simulation.log])

    def test_a_touch_while_asleep_sends_0x68_and_wakes_the_screen_as_it_ends(self):
        # As the Editor's simulator did, sendxy 0: 0x86 as it fell asleep by
        # thsp, 0x68 for the press and for the release, then 0x87 as it woke.
        sent = []
        simulation = Simulation(self.root, values={"thsp": 2, "thup": 1}, sending=sent.append)
        simulation.advance(2100)
        simulation.press("go", 120, 130)
        self.assertTrue(simulation.asleep)
        simulation.release()
        self.assertFalse(simulation.asleep)
        self.assertEqual(sent, [b"\x86\xff\xff\xff", b"\x68\x00\x78\x00\x82\x01\xff\xff\xff",
                                b"\x68\x00\x78\x00\x82\x00\xff\xff\xff", b"\x87\xff\xff\xff"])
        # The touch ran nothing.
        self.assertEqual([simulation.globals[name] for name in ("sys0", "sys2")], [0, 0])

    def test_with_thup_0_a_touch_while_asleep_leaves_it_asleep(self):
        sent = []
        simulation = Simulation(self.root, values={"thsp": 2}, sending=sent.append)
        simulation.advance(2100)
        simulation.press("go", 120, 130)
        simulation.release()
        self.assertTrue(simulation.asleep)
        self.assertEqual(sent[1:], [b"\x68\x00\x78\x00\x82\x01\xff\xff\xff",
                                    b"\x68\x00\x78\x00\x82\x00\xff\xff\xff"])

    def test_sleep_set_by_code_sends_nothing(self):
        # As the Editor's simulator showed, and the vendor's instruction set
        # says: 0x86 and 0x87 come only when the screen sleeps or wakes by
        # itself.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_input("sleep=1")
        simulation.serial_input("sleep=0")
        self.assertEqual(sent, [])


class SendKeyTest(SimulationTestCase):
    """A component's `sendkey`, the Editor's "Send Component ID" ticks of its
    events: 0x65 sent on a press when it has 2, on a release when it has 1,
    with the page's ID and the component's, as the Editor's simulator sent
    them for buttons of sendkey 0 to 3, its IDs 1 to 4."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("b%d" % key, "button", 20 + 190 * key, 100, sendkey=key)
                            for key in range(4)], """\
on b3.down:
  printh 0a
""")

    def tap(self, simulation: Simulation, name: str):
        simulation.press(name, 30, 110)
        simulation.release()

    def test_each_tick_sends_its_touch_event(self):
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        for key in range(4):
            self.tap(simulation, "b%d" % key)
        self.assertEqual(sent, [bytes.fromhex(data) for data in (
            "65 00 02 00 ff ff ff", "65 00 03 01 ff ff ff",
            "65 00 04 01 ff ff ff", "0a", "65 00 04 00 ff ff ff")])

    def test_after_the_touchs_place_and_before_the_events(self):
        # Assumed: in the order the screen's own data comes, as sendxy's.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_input("sendxy=1")
        simulation.press("b3", 30, 110)
        self.assertEqual([data[0] for data in sent], [0x67, 0x65, 0x0A])

    def test_the_page_sends_as_id_0(self):
        # Assumed, as the page takes a touch as a component does.
        self.page("page0", [], "")
        self.write("pages/page0.page.toml",
                   self.text("pages/page0.page.toml") + "sendkey = 3\n")
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        self.tap(simulation, "page0")
        self.assertEqual(sent, [bytes.fromhex("65 00 00 01 ff ff ff"),
                                bytes.fromhex("65 00 00 00 ff ff ff")])

    def test_nothing_without_a_touch(self):
        # Assumed: a component whose touches are off runs nothing, and a
        # click runs no touch capture; neither sends.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_input("tsw b3,0")
        self.tap(simulation, "b3")
        simulation.serial_input("tsw b3,1")
        simulation.serial_input("click b2,1")
        self.assertEqual([data for data in sent if data[:1] == b"\x65"], [])


class OpeningEffectsSimulationTest(SimulationTestCase):
    """Components sliding in as their page opens, in the simulator, as the
    Editor's simulator showed (test_common_attributes.py for the slides):
    drawn where they are, those waiting their turn hidden, while code reads
    their own `x` and `y`."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0)], "on go.up:\n  page second\n")
        # a from the left, 1000 ms; then b from the right, 500 ms.
        self.page("second", [placed("a", "text", 420, 80, effect=3, time=1000, first=10),
                             placed("b", "text", 100, 300, effect=4, time=500)])

    def opened(self) -> Simulation:
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.release()
        self.assertEqual(simulation.page, "second")
        return simulation

    def test_the_components_slide_in_as_their_page_opens(self):
        simulation = self.opened()
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.hidden()),
                         ((-100, 80), {"b"}))
        self.assertEqual(simulation.next_due(), simulation.clock + STEP)
        simulation.advance(500)
        self.assertEqual(self.drawn_at(simulation, "a"), (160, 80))   # halfway from x -100
        # As code reads it, `x` keeps its value.
        self.assertEqual(simulation.values()["a.x"], 420)
        simulation.advance(500)
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.hidden()), ((420, 80), set()))
        self.assertEqual(self.drawn_at(simulation, "b"), (800, 300))     # past the page's width
        simulation.advance(500)
        self.assertEqual((self.drawn_at(simulation, "b"), simulation.next_due()),
                         ((100, 300), None))

    def test_a_slide_marks_its_steps_only_while_something_painted_shows(self):
        # With nothing painted, the drawing would be the same: no marks.
        simulation = self.opened()
        simulation.advance(1500)
        self.assertEqual(simulation.drawing_inputs().painted, [])
        # Over a fill, each step gives back the page's background in the box
        # a was drawn in at the step before, then draws a again, over it.
        simulation = self.opened()
        simulation.serial_input("fill 0,0,800,480,0")
        simulation.advance(STEP)
        first = self.drawn_at(simulation, "a")
        simulation.advance(STEP)
        painted = simulation.drawing_inputs().painted
        self.assertEqual([entry[0] for entry in painted], ["fill", "left", "redraw"])
        self.assertEqual((painted[1][:2], painted[1][2][:2], painted[2]),
                         (("left", "a"), first, ("redraw", "a")))

    def test_nothing_slides_in_on_a_basic_screen(self):
        # As the Nextion Editor's simulator showed on an NX4832T035: a button
        # with effect 3 and time 60000 was in its place at once, and 2 s
        # later, where an NX8048P050 slid it in. A Basic, Enhanced, or
        # Discovery screen does not hold `effect`. So each component is drawn
        # in its place at once, and none waits its turn hidden: on a start
        # page, on a page code opens, and at a ref_star after a hold.
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        held = Simulation(self.root)
        for line in ("ref_stop", "page second", "ref_star"):
            held.serial_input(line)
        for opened_by, simulation in (("start", Simulation(self.root, "second")),
                                      ("code", self.opened()), ("ref_star", held)):
            with self.subTest(opened_by=opened_by):
                self.assertEqual((self.drawn_at(simulation, "a"), self.drawn_at(simulation, "b"),
                                  simulation.hidden(), simulation.next_due()),
                                 ((420, 80), (100, 300), set(), None))

    def test_values_given_to_a_start_page_set_its_slides(self):
        # a slides in to the x given; b, its effect given as none, is in its
        # place at once, with no slide to wait for.
        simulation = Simulation(self.root, "second", {"a.x": 200, "b.effect": 0})
        self.assertEqual((self.drawn_at(simulation, "a"), self.drawn_at(simulation, "b"),
                          simulation.hidden()), ((-100, 80), (100, 300), set()))
        simulation.advance(1000)
        self.assertEqual(self.drawn_at(simulation, "a"), (200, 80))

    def test_code_hiding_a_component_ends_its_slide(self):
        # Hidden and shown again, it is in its place at once.
        simulation = self.opened()
        simulation.serial_input("vis b,0")
        simulation.serial_input("vis b,1")
        self.assertEqual((self.drawn_at(simulation, "b"), simulation.hidden()),
                         ((100, 300), set()))

    def test_the_slides_start_once_the_load_event_ends(self):
        # A move in the load event is where its component slides to; loadend
        # runs during the slides, so its move goes back at the slide's end.
        self.page("second", [placed("a", "text", 420, 80, effect=3, time=1000, first=10),
                             placed("b", "text", 100, 300, effect=4, time=500)],
                  "on second.load:\n  a.x=200\n\non second.loadend:\n  b.x=50\n")
        simulation = self.opened()
        simulation.advance(500)
        self.assertEqual(self.drawn_at(simulation, "a"), (50, 80))     # halfway from x -100
        simulation.advance(1000)
        values = simulation.values()
        self.assertEqual((self.drawn_at(simulation, "a"), values["a.x"], values["b.x"]),
                         ((200, 80), 200, 100))

    def test_a_page_entered_while_ref_stop_holds_slides_in_at_ref_star(self):
        # The Nextion Editor's simulator started the slide of a page entered
        # after ref_stop at ref_star, however long the hold. Under the hold,
        # nothing waits to slide.
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second"):
            simulation.serial_input(line)
        simulation.advance(5000)
        self.assertEqual((simulation.hidden(), simulation.next_due()), (set(), None))
        simulation.serial_input("ref_star")
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.hidden()),
                         ((-100, 80), {"b"}))
        simulation.advance(1500)
        self.assertEqual((self.drawn_at(simulation, "a"), self.drawn_at(simulation, "b")),
                         ((420, 80), (100, 300)))
        # A later ref_star starts nothing again.
        simulation.serial_input("ref_star")
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.next_due()),
                         ((420, 80), None))

    def test_under_a_hold_loadend_runs_and_a_move_is_slid_to(self):
        # As the Nextion Editor's simulator ran them: the loadend event ran as
        # the load event ended, before ref_star, and a text code moved under
        # the hold slid to its new place once ref_star came.
        self.page("second", [placed("a", "text", 420, 80, effect=3, time=1000, first=10),
                             placed("b", "text", 100, 300, effect=4, time=500)],
                  "on second.loadend:\n  sys2=1\n")
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "a.x=200"):
            simulation.serial_input(line)
        self.assertEqual(simulation.values()["sys2"], 1)
        simulation.advance(5000)
        simulation.serial_input("ref_star")
        simulation.advance(500)
        self.assertEqual(self.drawn_at(simulation, "a"), (50, 80))     # halfway from x -100
        simulation.advance(500)
        self.assertEqual(self.drawn_at(simulation, "a"), (200, 80))

    def test_a_hold_on_a_page_entered_without_one_starts_no_slide(self):
        # Only slides a held page change left waiting start at ref_star.
        simulation = self.opened()
        simulation.advance(1500)
        for line in ("ref_stop", "ref_star"):
            simulation.serial_input(line)
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.next_due()),
                         ((420, 80), None))

    def test_only_the_page_shown_at_ref_star_slides_in(self):
        # Entered under the hold, then left for page0, which has no slide:
        # ref_star slides nothing in.
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "page page0", "ref_star"):
            simulation.serial_input(line)
        self.assertEqual((simulation.page, simulation.hidden(), simulation.next_due()),
                         ("page0", set(), None))

    def test_a_start_drops_the_slides_waiting_for_ref_star(self):
        # `rest` starts again on page0, the hold gone: the page entered
        # after it slides in at once, and a ref_star then starts nothing.
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "rest", "page second"):
            simulation.serial_input(line)
        simulation.advance(1500)
        simulation.serial_input("ref_star")
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.next_due()),
                         ((420, 80), None))

    def test_a_load_event_letting_the_hold_go_slides_its_page_in_at_once(self):
        # Its ref_star comes before the page is drawn: the slides start once
        # the load event ends, as for any page.
        self.page("second", [placed("a", "text", 420, 80, effect=3, time=1000, first=10),
                             placed("b", "text", 100, 300, effect=4, time=500)],
                  "on second.load:\n  ref_star\n")
        simulation = Simulation(self.root)
        for line in ("ref_stop", "page second"):
            simulation.serial_input(line)
        self.assertEqual((self.drawn_at(simulation, "a"), simulation.hidden()),
                         ((-100, 80), {"b"}))

    def test_a_slide_puts_back_a_component_code_moved(self):
        # The Editor's simulator slid it on, and the slide's end put its `x`
        # back, as code then read it; its `y` is assumed alike.
        simulation = self.opened()
        simulation.serial_input("a.x=10")
        simulation.serial_input("a.y=5")
        simulation.advance(500)
        values = simulation.values()
        self.assertEqual((self.drawn_at(simulation, "a"), values["a.x"], values["a.y"]),
                         ((160, 80), 10, 5))
        simulation.advance(500)
        values = simulation.values()
        self.assertEqual((self.drawn_at(simulation, "a"), values["a.x"], values["a.y"]),
                         ((420, 80), 420, 80))


class DragTest(SimulationTestCase):
    """A component whose `drag` is 1 carried by a touch that moves, assumed:
    the Editor tool cannot drag the Editor's simulator."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("t0", "text", 100, 100, drag=1),
                            placed("t1", "text", 300, 100),
                            placed("s0", "slider", 100, 300, drag=1),
                            placed("h0", "hotspot", 500, 300, drag=1),
                            placed("e0", "text", 420, 200, drag=1, effect=3, time=1000)], """\
on t0.up:
  covx t0.x,t1.txt,0,0
""")

    def drag(self, simulation: Simulation, name: str, start: tuple, end: tuple):
        simulation.press(name, *start)
        simulation.move(*end)
        simulation.release()

    def at(self, simulation: Simulation, name: str) -> tuple:
        values = simulation.values()
        return values[name + ".x"], values[name + ".y"]

    def test_the_touch_carries_it(self):
        simulation = Simulation(self.root)
        self.drag(simulation, "t0", (120, 110), (170, 140))
        # Its x and y change, as its release event read.
        self.assertEqual((self.at(simulation, "t0"), simulation.values()["t1.txt"]),
                         ((150, 130), "150"))

    def test_it_stays_on_the_screen(self):
        simulation = Simulation(self.root)
        self.drag(simulation, "t0", (120, 110), (1200, 900))
        self.assertEqual(self.at(simulation, "t0"), (700, 430))      # 800 - 100, 480 - 50
        self.drag(simulation, "t0", (720, 440), (-500, -500))
        self.assertEqual(self.at(simulation, "t0"), (0, 0))

    def test_what_is_not_dragged(self):
        # A component of drag 0; a slider, which follows a press itself; and
        # a hotspot, whose drag the Editor's panel never shows.
        simulation = Simulation(self.root)
        self.drag(simulation, "t1", (310, 110), (360, 160))
        self.drag(simulation, "s0", (110, 310), (180, 360))
        self.drag(simulation, "h0", (510, 310), (560, 360))
        self.assertEqual([self.at(simulation, name) for name in ("t1", "s0", "h0")],
                         [(300, 100), (100, 300), (500, 300)])
        self.assertNotEqual(simulation.values()["s0.val"], 0)

    def test_a_drag_ends_a_slide_in(self):
        # e0 slides in from the left as the page opens; the touch lands
        # where its x and y say, and the drag puts it in its place at once.
        simulation = Simulation(self.root)
        self.assertNotEqual(self.drawn_at(simulation, "e0"), (420, 200))
        simulation.press("e0", 430, 210)
        simulation.move(440, 220)
        self.assertEqual((self.drawn_at(simulation, "e0"), self.at(simulation, "e0")),
                         ((430, 210), (430, 210)))


class RefStopTest(SimulationTestCase):
    """Between `ref_stop` and `ref_star`, as the Nextion Editor's simulator
    showed (fixtures/drawing-assumptions/, page7): a component code changes
    is drawn as it was, and one `vis` hides still shows, until `ref_star`;
    one `vis` shows is drawn at once. Code reads the current values."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("n0", "number", 0, 0), placed("n1", "number", 0, 60)])
        self.simulation = Simulation(self.root)

    def drawn(self, name: str) -> dict:
        return next(component.values for component in self.simulation.drawing_inputs().components
                    if component.name == name)

    def drawn_hidden(self) -> set:
        return self.simulation.drawing_inputs().hidden

    def test_a_change_drawn_at_ref_star(self):
        for line in ("ref_stop", "n0.val=5"):
            self.simulation.serial_input(line)
        self.assertEqual((self.drawn("n0")["val"], self.simulation.values()["n0.val"]), (0, 5))
        self.simulation.serial_input("n1.val=6")
        self.assertEqual(self.drawn("n1")["val"], 0)
        self.simulation.serial_input("ref_star")
        self.assertEqual((self.drawn("n0")["val"], self.drawn("n1")["val"]), (5, 6))

    def test_a_hide_drawn_at_ref_star_and_a_show_at_once(self):
        for line in ("ref_stop", "vis n0,0"):
            self.simulation.serial_input(line)
        self.assertEqual((self.drawn_hidden(), self.simulation.hidden()), (set(), {"n0"}))
        self.simulation.serial_input("ref_star")
        self.assertEqual(self.drawn_hidden(), {"n0"})
        for line in ("ref_stop", "vis n0,1"):
            self.simulation.serial_input(line)
        self.assertEqual(self.drawn_hidden(), set())

    def test_without_ref_stop_drawn_at_once(self):
        for line in ("n0.val=5", "vis n1,0"):
            self.simulation.serial_input(line)
        self.assertEqual((self.drawn("n0")["val"], self.drawn_hidden()), (5, {"n1"}))

    def test_a_page_changed_shows_the_page_before_until_ref_star(self):
        # As the Nextion Editor's simulator showed (fixtures/drawing-
        # assumptions/, page30): the screen kept showing the page before, as
        # it was at ref_stop, even once code changed the new page. ref_star
        # drew the new page, with what its code painted meanwhile.
        self.page("second", [placed("t0", "text", 0, 0, txt="new")])
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "n0.val=5", "page second", 't0.txt="changed"',
                     "fill 0,0,9,9,0"):
            self.simulation.serial_input(line)
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.entry, self.drawn("n0")["val"]), ("page0", 1, 0))
        # The new page's own record waits on the hold, and code reads its values.
        self.assertEqual(self.simulation.painted(),
                         [("ref_stop",), ("redraw", "t0"), ("fill", 0, 0, 9, 9, 0)])
        self.assertEqual((self.simulation.page, self.simulation.values()["t0.txt"]),
                         ("second", "changed"))
        self.simulation.serial_input("ref_star")
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.entry, self.drawn("t0")["txt"]),
                         ("second", 2, "changed"))
        self.assertEqual(inputs.painted, [("ref_stop",), ("redraw", "t0"),
                                          ("fill", 0, 0, 9, 9, 0), ("ref_star",)])

    def test_a_touch_while_the_page_before_shows_goes_to_the_new_page(self):
        # As the Nextion Editor's simulator ran it: a touch where the new
        # page's button lay, on the page before's empty place, ran the
        # button's event.
        self.page("second", [placed("b1", "button", 300, 300)], "on b1.down:\n  sys1=sys1+1\n")
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "page second"):
            self.simulation.serial_input(line)
        name = self.simulation.component_at(350, 320)
        self.simulation.press(name, 350, 320)
        self.simulation.release()
        self.assertEqual((name, self.simulation.values()["sys1"],
                          self.simulation.drawing_inputs().page), ("b1", 1, "page0"))

    def test_a_second_page_change_keeps_the_first_page_shown(self):
        # Back to page0: still its first entry, as it showed at ref_stop.
        self.page("second", [])
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "page page0"):
            self.simulation.serial_input(line)
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.entry), ("page0", 1))
        self.simulation.serial_input("ref_star")
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.entry), ("page0", 3))

    def test_the_page_before_keeps_what_its_unload_event_painted(self):
        # Drawing commands paint at once, whatever ref_stop holds.
        self.page("page0", [placed("n0", "number", 0, 0)], "on page0.unload:\n  fill 0,0,9,9,0\n")
        self.page("second", [])
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "page second"):
            self.simulation.serial_input(line)
        self.assertEqual(self.simulation.drawing_inputs().painted,
                         [("ref_stop",), ("fill", 0, 0, 9, 9, 0)])

    def test_a_load_event_letting_the_hold_go_draws_the_new_page(self):
        self.page("second", [placed("t0", "text", 0, 0)],
                  "on second.load:\n  ref_star\n  t0.txt=\"loaded\"\n")
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", 't0.txt="changed"'):
            self.simulation.serial_input(line)
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.painted), ("second", [("redraw", "t0")]))

    def test_a_start_lets_the_page_before_go(self):
        self.page("second", [])
        self.simulation = Simulation(self.root)
        for line in ("ref_stop", "page second", "rest"):
            self.simulation.serial_input(line)
        inputs = self.simulation.drawing_inputs()
        self.assertEqual((inputs.page, inputs.entry), ("page0", self.simulation.entered))


class ReturnCodeTest(SimulationTestCase):
    """What the screen answers an instruction it refuses, as the Editor's
    simulator answered with bkcmd 3: the failure's code, the screen keeping
    what it had; and a typed click, answered before its event runs."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        (self.root / "pictures").mkdir()
        (self.root / "pictures" / "dot.png").write_bytes(
            write_png(20, 20, bytes((200, 40, 40, 255)) * 400))
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pictures"].append("dot")))
        self.program("bkcmd=3\npage page0\n")
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("n0", "number", 0, 60), placed("n1", "number", 200, 60),
                            table("p0", "picture", x=0, y=120, w=20, h=20, pic="dot"),
                            table("s0", "waveform", x=0, y=150, w=200, h=100, ch=1),
                            placed("b0", "button", 0, 260), placed("b1", "button", 200, 260),
                            placed("x0", "xfloat", 400, 60)],
                  """\
on b0.down:
  n1.val=0
  p0.pic=n1.val+9
  pic 0,0,9
  add s0.id,5,10
  n0.val=7

on b1.down:
  printh 41 42
  n0.val=9
""")

    def answers(self, text: str) -> tuple:
        """Sends `text` on the serial line of a new simulation; returns the
        simulation and what it sent then, in hexadecimal."""
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        sent.clear()
        simulation.serial_input(text)
        return simulation, [data.hex(" ") for data in sent]

    def test_each_refusal_answers_its_code_and_changes_nothing(self):
        waveform = Simulation(self.root).values()["s0.id"]
        # The running screen's refusals are recorded; those of the Editor's
        # compile, which a typed instruction alone meets, are not.
        for text, code, recorded in (
                ("p0.pic=9", 0x1c, True), ("t0.font=9", 0x1c, True),
                ("p0.pic=65535", 0x1c, True), ("t0.font=255", 0x1c, True),
                ("pic 0,0,9", 0x04, True), ("xpic 0,0,10,10,0,0,9", 0x04, True),
                ("picq 0,0,10,10,9", 0x04, True),
                ('xstr 0,0,50,20,9,0,63488,0,0,1,"a"', 0x05, True),
                ("add %d,5,10" % waveform, 0x12, True), ("add 99,0,10", 0x12, True),
                ("repo n0.val,99999", 0x1d, True),
                ('n0.val="a"', 0x1c, False), ("t0.txt=5", 0x1c, False),
                ("n0.val=t0.txt", 0x1c, False), ("t0.txt*=2", 0x1b, False),
                ("n0.val+=t0.txt", 0x1b, False), ("cls 1,2", 0x1e, False),
                ("fill 0,0,10", 0x1e, False), ("sendme 1", 0x1e, False),
                ("crcrest 1", 0x1e, False), ("crcputs t0.txt,0,1", 0x1e, False),
                ("crcputu 0", 0x1e, False), ('t0.txt="a\\q"', 0x20, False),
                # A name the page lacks is an unknown name first.
                ("p9.pic=9", 0x1a, False), ("t9.txt=5", 0x1a, False)):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["%02x ff ff ff" % code])
                values = simulation.values()
                self.assertEqual((values["t0.txt"], values["n0.val"], values["p0.pic"],
                                  values["t0.font"]), ("probe", 0, 0, 0))
                self.assertEqual(values.get("refusals"), [(code, text)] if recorded else None)
        # xstr paints its background before its font is found missing.
        simulation, _ = self.answers('xstr 0,0,50,20,9,0,63488,0,0,1,"a"')
        self.assertEqual([entry[0] for entry in simulation.painted()], ["xstr"])

    def test_what_the_screens_series_lacks(self):
        # Typed on an Enhanced screen, as the Editor's simulator answered: a
        # command its series lacks is an invalid instruction, and a system
        # variable an invalid name. The Editor's compile refuses them, so
        # nothing is recorded, and no file is made.
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832K035")))
        for text, code in (('newfile "sd0/a.txt",10', 0x00), ("move b0,0,0,10,10,0,100", 0x00),
                           ("get volume", 0x1a), ("n0.val=volume", 0x1a)):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["%02x ff ff ff" % code])
                values = simulation.values()
                self.assertEqual(values["n0.val"], 0)
                self.assertNotIn("refusals", values)
                self.assertNotIn("file commands", values)
        # A name in a quoted text is no variable.
        simulation, sent = self.answers('t0.txt="volume"')
        self.assertEqual((sent, simulation.values()["t0.txt"]), (["01 ff ff ff"], "volume"))

    def test_an_attribute_a_component_lacks(self):
        # Typed in the Editor's simulator, each answered 0x1A, an invalid
        # variable, reads and stores alike: a variable holding a text has no
        # val, a video playing an internal file no path (its from left at 0),
        # and an animation of from 1 no vid.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("n0", "number", 0, 60), table("va0", "variable", sta=1),
                            table("vd0", "video", x=0, y=120, w=80, h=60),
                            table("gm1", "gmov", x=100, y=120, w=80, h=60, **{"from": 1})])
        for text in ("get va0.val", "va0.val=5", "get vd0.path", "get gm1.vid"):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1a ff ff ff"])
                values = simulation.values()
                self.assertEqual(values["n0.val"], 0)
                self.assertFalse({"va0.val", "vd0.path", "gm1.vid"} & set(values))

    def test_an_attribute_a_choice_or_the_series_leaves_out(self):
        # A text of sta 3, nothing behind it, has no bco, and one of effect
        # 0 no first: a typed line naming one answers 0x1A, as the Editor's
        # simulator answered for the attributes a component lacked that it
        # tried. On a Basic screen, a text has no movex, as a typed get there
        # answered 0x1A.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20, sta=3),
                            placed("n0", "number", 0, 60)])
        for text in ("get t0.bco", "t0.bco=5", "get t0.first"):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1a ff ff ff"])
                self.assertFalse({"t0.bco", "t0.first"} & set(simulation.values()))
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        simulation, sent = self.answers("get t0.movex")
        self.assertEqual(sent, ["1a ff ff ff"])
        self.assertNotIn("t0.movex", simulation.values())

    def test_x_and_y_typed_on_a_basic_screen(self):
        # As the Nextion Editor's simulator answered on an NX4832T035: a typed
        # store of x 0x1C, x kept; reading it, its value.
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        for text in ("t0.x=5", "t0.y=5"):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1c ff ff ff"])
                self.assertEqual(simulation.values()[text[:4]], 0)
        simulation, sent = self.answers("get t0.x")
        self.assertEqual(sent, ["71 00 00 00 00 ff ff ff"])
        # A variable, which has no x, answers as for any name it lacks.
        self.page("page0", [placed("t0", "text", 0, 0), table("va0", "variable")])
        self.assertEqual(self.answers("va0.x=5")[1], self.answers("va0.vvs3=5")[1])

    def test_attributes_code_cannot_change_typed_on_a_basic_screen(self):
        # As the Nextion Editor's simulator answered on an NX4832T035. A typed
        # store of a text's spax, a bordered text's borderc, or a crop's vvs0
        # answered 0x1C, each kept. A number's spax answered 0x01, and reading
        # a text's spax gave its value. A button's first and time, its effect
        # 1, answered 0x1A, read or stored, as the screen does not hold them.
        self.page("page0", [placed("t0", "text", 0, 0), placed("t1", "text", 0, 40, style=1),
                            placed("q0", "crop", 0, 80, picc="dot"),
                            placed("n0", "number", 0, 120),
                            placed("b0", "button", 0, 160, effect=1)])
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        for text in ("t0.spax=3", "t1.borderc=5", "q0.vvs0=3"):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1c ff ff ff"])
                self.assertEqual(simulation.values()[text.partition("=")[0]], 0)
        self.assertEqual(self.answers("n0.spax=3")[1], ["01 ff ff ff"])
        self.assertEqual(self.answers("get t0.spax")[1], ["71 00 00 00 00 ff ff ff"])
        for text in ("get b0.first", "b0.first=0", "b0.time=300"):
            with self.subTest(text):
                self.assertEqual(self.answers(text)[1], ["1a ff ff ff"])

    def test_an_attribute_a_component_lacks_through_the_screens_array(self):
        # As the Editor's simulator ran it: reading or storing through b[] an
        # attribute the component lacks answers 0x1A, an invalid variable,
        # leaves the variable read into as it was, and the event goes on. b[2]
        # is t1, a text of sta 3, which has no bco.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("t1", "text", 0, 40, sta=3),
                            placed("n0", "number", 0, 80, val=7), placed("n1", "number", 0, 120),
                            placed("n2", "number", 0, 160), placed("b0", "button", 0, 200)],
                  "on b0.down:\n  n0.val=b[2].bco\n  n1.val=1\n  b[2].bco=5\n  n2.val=1\n")
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1a ff ff ff", "1a ff ff ff"])
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["n1.val"], values["n2.val"]), (7, 1, 1))
        self.assertNotIn("t1.bco", values)

    def test_an_attribute_a_component_lacks_read_in_a_condition(self):
        # As the Nextion Editor's simulator ran it: a condition reading
        # through b[] an attribute the component lacks answers 0x1A, and
        # holds, whatever it compares, and the event goes on. b[2] is t1, a
        # text of sta 3, which has no bco.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("t1", "text", 0, 40, sta=3),
                            placed("n0", "number", 0, 80), placed("n1", "number", 0, 120),
                            placed("n2", "number", 0, 160), placed("b0", "button", 0, 200)],
                  "on b0.down:\n  if(b[2].bco==0)\n  {\n    n0.val=1\n  }else\n  {\n"
                  "    n0.val=2\n  }\n  if(b[2].bco!=0)\n  {\n    n1.val=1\n  }else\n  {\n"
                  "    n1.val=2\n  }\n  n2.val=9\n")
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1a ff ff ff", "1a ff ff ff"])
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["n1.val"], values["n2.val"]), (1, 1, 9))

    def test_a_conditions_parts_are_read_until_its_result_is_known(self):
        # As the Nextion Editor's simulator ran it: && stops at a false part
        # and || at a true one, reading no further. A part whose read fails,
        # as above, counts as true. b[2] is t1, without bco.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("t1", "text", 0, 40, sta=3),
                            placed("n0", "number", 0, 80), placed("n1", "number", 0, 120),
                            placed("n2", "number", 0, 160), placed("b0", "button", 0, 200)],
                  "on b0.down:\n  n0.val=2\n  if(sys1==99&&b[2].bco==0)\n  {\n    n0.val=1\n"
                  "  }\n  n1.val=2\n  if(b[2].bco==0&&sys1==99)\n  {\n    n1.val=1\n  }\n"
                  "  n2.val=2\n  if(sys1==0||b[2].bco==7)\n  {\n    n2.val=1\n  }\n")
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1a ff ff ff"])
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["n1.val"], values["n2.val"]), (2, 2, 1))

    def test_another_pages_component_not_of_global_scope(self):
        # As the Editor's simulator ran it: on page1, reading or storing
        # through the screen's arrays an attribute of a component of page0 not
        # of global scope, or of page0 itself, answers 0x1A, an invalid
        # variable. The line changes nothing, and the event goes on. A
        # component of global scope is reached as usual.
        self.page("page0", [placed("local", "text", 0, 0, txt="loc", txt_maxl=10),
                            placed("shared", "text", 0, 40, txt="glob", txt_maxl=10, vscope=1),
                            placed("num", "number", 0, 80, val=7)])
        self.page("page1", [placed("t0", "text", 0, 0, txt="before", txt_maxl=10),
                            placed("t1", "text", 0, 40, txt_maxl=10),
                            placed("n0", "number", 0, 80, val=5),
                            placed("n1", "number", 0, 120, val=9)],
                  "on page1.loadend:\n  n0.val=p[0].b[3].val\n  t0.txt=p[0].b[1].txt\n"
                  "  n1.val=p[0].b[0].type\n  p[0].b[1].txt=\"x\"\n  p[0].b[3].val=4\n"
                  "  t1.txt=p[0].b[2].txt\n")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("page1")))
        simulation, sent = self.answers("page page1")
        self.assertEqual(sent, ["1a ff ff ff"] * 5)
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["t0.txt"], values["n1.val"], values["t1.txt"]),
                         (5, "before", 9, "glob"))
        # A typed line alike, on page1.
        sent = []
        typed = Simulation(self.root, sending=sent.append)
        typed.serial_input("page page1")
        sent.clear()
        typed.serial_input("get p[0].b[1].txt")
        typed.serial_input("get p[0].b[0].type")
        typed.serial_input("get p[0].b[2].txt")
        self.assertEqual([data.hex(" ") for data in sent],
                         ["1a ff ff ff", "1a ff ff ff", "70 67 6c 6f 62 ff ff ff"])
        # And a simulation started on page1, which stopped with a KeyError.
        started = Simulation(self.root, start_page="page1").values()
        self.assertEqual((started["n0.val"], started["t1.txt"]), (5, "glob"))

    def test_an_attribute_the_screen_does_not_hold(self):
        # As the Editor's simulator ran it on an Intelligent screen: a gauge's
        # wid, stored 2, is no attribute the screen holds, though code may
        # name it. A typed line naming it answers 0x1A, an invalid variable;
        # event code reads it as 0, a store answers 0x1C, a failed assignment,
        # and changes nothing, and b[] answers 0x1A. A text's movex and a
        # combo box's path_m, a bound, alike. The values keep the page file's,
        # which the screen draws.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            table("z0", "gauge", x=0, y=40, w=100, h=100, wid=2),
                            table("cb0", "combo-box", x=110, y=40, w=100, h=30),
                            placed("n0", "number", 0, 150, val=7),
                            placed("n1", "number", 0, 190, val=7),
                            placed("n2", "number", 0, 230, val=7), placed("b0", "button", 0, 270)],
                  "on b0.down:\n  n0.val=z0.wid\n  z0.wid=5\n  n1.val=z0.wid\n"
                  "  n2.val=b[2].wid\n")
        for text in ("get z0.wid", "z0.wid=3", "n0.val=z0.wid", "get t0.movex", "get cb0.path_m"):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1a ff ff ff"])
                values = simulation.values()
                self.assertEqual((values["z0.wid"], values["n0.val"]), (2, 7))
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1c ff ff ff", "1a ff ff ff"])
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["n1.val"], values["n2.val"], values["z0.wid"]),
                         (0, 0, 7, 2))

    def test_a_typed_assignment_code_cannot_make(self):
        # As the Nextion Editor's simulator answered: each of these, which
        # code cannot change, 0x1C, the value kept; t0.x, which it can, 0x01.
        for text, name in (("t0.w=10", "t0.w"), ("t0.id=9", "t0.id"), ("t0.type=1", "t0.type"),
                           ("n0.endx=3", "n0.endx")):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1c ff ff ff"])
                self.assertEqual(simulation.values()[name], Simulation(self.root).values()[name])
        simulation, sent = self.answers("t0.x=5")
        self.assertEqual((sent, simulation.values()["t0.x"]), (["01 ff ff ff"], 5))

    def test_an_xfloats_digits_past_what_the_screen_holds(self):
        # As the Nextion Editor's simulator answered: an xfloat's vvs1 outside
        # 0 to 8, or vvs0 outside 0 to 10, 0x1C, the value kept; at the
        # bounds, 0x01.
        for text, name in (("x0.vvs1=9", "x0.vvs1"), ("x0.vvs1=-1", "x0.vvs1"),
                           ("x0.vvs0=11", "x0.vvs0"), ("x0.vvs0=-1", "x0.vvs0")):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1c ff ff ff"])
                self.assertEqual(simulation.values()[name], Simulation(self.root).values()[name])
        for text, name, value in (("x0.vvs1=8", "x0.vvs1", 8), ("x0.vvs0=10", "x0.vvs0", 10)):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual((sent, simulation.values()[name]), (["01 ff ff ff"], value))

    def test_an_objects_name_the_screen_does_not_hold(self):
        # As the Editor's simulator ran it on an Intelligent screen: the
        # screen does not hold an object's objname, though code may read it.
        # Event code read it as 0, a number, as it reads every attribute the
        # screen does not hold, which a text refused (0x1C); through b[] it
        # answered 0x1A, and the event went on. A typed get and a typed store
        # answered 0x1A.
        self.page("page0", [placed("t0", "text", 0, 0, txt="x", txt_maxl=20),
                            placed("t1", "text", 0, 40, txt="x", txt_maxl=20),
                            placed("t2", "text", 200, 0, txt="x", txt_maxl=20),
                            placed("n0", "number", 0, 80), placed("n1", "number", 0, 120, val=7),
                            placed("n2", "number", 0, 160, val=7), placed("b0", "button", 0, 200)],
                  "on b0.down:\n  n1.val=t0.objname\n  t1.txt=b[1].objname\n"
                  "  t2.txt=t0.objname\n  n2.val=page0.objname\n  n0.val=1\n")
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1a ff ff ff", "1c ff ff ff"])
        values = simulation.values()
        self.assertEqual((values["n1.val"], values["t1.txt"], values["t2.txt"], values["n2.val"],
                          values["n0.val"]), (0, "x", "x", 0, 1))
        for text in ("get t0.objname", 't0.objname="zz"'):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["1a ff ff ff"])

    def test_an_attribute_a_basic_screen_does_not_hold(self):
        # As the Editor's simulator answered: a text's aph, stored 127, which
        # the Intelligent holds, the Basic does not: event code there read 0,
        # and a typed get answered 0x1A.
        self.page("page0", [placed("t0", "text", 0, 0, txt="probe", txt_maxl=20),
                            placed("n0", "number", 0, 40, val=7), placed("b0", "button", 0, 80)],
                  "on b0.down:\n  n0.val=t0.aph\n")
        simulation, sent = self.answers("get t0.aph")
        self.assertEqual(sent, ["71 7f 00 00 00 ff ff ff"])
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832T035")))
        simulation, sent = self.answers("get t0.aph")
        self.assertEqual(sent, ["1a ff ff ff"])
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff"])
        self.assertEqual(simulation.values()["n0.val"], 0)
        # A press on the panel runs the event on the same screen.
        simulation = Simulation(self.root)
        simulation.press("b0")
        self.assertEqual(simulation.values()["n0.val"], 0)

    def test_a_command_typed_alone(self):
        # As the Editor's simulator answered, as its compile refuses them: add
        # alone is no instruction, and cuts alone, of a form no number of
        # arguments matched, a wrong number of parameters. So did crcrest
        # alone, as a command taking two.
        for text, code in (("add", 0x00), ("cuts", 0x1e), ("crcrest", 0x1e)):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["%02x ff ff ff" % code])
                self.assertNotIn("other commands", simulation.values())

    def test_a_word_that_is_no_command(self):
        # Typed, as the Editor's simulator answered: a word in small letters
        # it does not know is an invalid instruction; one holding a capital
        # letter, and movelayer, an invalid name, as the Editor's compile
        # calls them "Invalid Variables"; and setbrush, a wrong number of
        # parameters, whatever its number.
        for text, code in (("zork 1", 0x00), ("sys0", 0x00), ("CLS 1", 0x1a), ("Zork", 0x1a),
                           ("movelayer b0,t0", 0x1a), ("setbrush 1", 0x1e)):
            with self.subTest(text):
                simulation, sent = self.answers(text)
                self.assertEqual(sent, ["%02x ff ff ff" % code])
                self.assertNotIn("refusals", simulation.values())

    def test_a_refusal_in_an_event_answers_at_once(self):
        simulation, sent = self.answers("click b0,1")
        self.assertEqual(sent, ["01 ff ff ff", "1c ff ff ff", "04 ff ff ff", "12 ff ff ff"])
        self.assertEqual(simulation.values()["n0.val"], 7)
        self.assertIn("p0.pic=n1.val+9 refused, answering 1c",
                      [line for _, line in simulation.log])

    def test_a_typed_click_answers_before_its_event(self):
        simulation, sent = self.answers("click b1,1")
        self.assertEqual(sent, ["01 ff ff ff", "41 42"])
        self.assertEqual(simulation.values()["n0.val"], 9)


class FixedAttributeTest(SimulationTestCase):
    """A typed assignment to each attribute code cannot change, on each type
    and the page, as the Nextion Editor's simulator answered all of them on
    an NX8048P050, with bkcmd 3: 0x1C, but 0x1A for those the running screen
    does not hold (ANSWERED_AS_UNKNOWN). movex and movey, which it holds on no
    type, are left out."""
    language = "nextion"
    ANSWERED_AS_UNKNOWN = {
        ("combo-box", "path_m"), ("combo-box", "drastate"), ("data-record", "init"),
        ("data-record", "autoleft"), ("file-browser", "autoleft"), ("file-browser", "buff"),
        ("file-browser", "fwarning"), ("number", "key"), ("scrolling-text", "key"),
        ("select", "txt_maxl"), ("select", "path_m"), ("sliding-text", "key"),
        ("sliding-text", "leftshow"), ("sliding-text", "path_m"), ("text", "key"),
        ("waveform", "objWid"), ("waveform", "objHig"), ("waveform", "inittrue"),
        ("xfloat", "key"), ("page", "drag"), ("page", "aph")}

    def test_each_answers_as_the_editors_simulator_did(self):
        defaults = nxwright_defaults()
        kinds = sorted(name for name in TYPES_BY_NAME if name != "page")
        components = []
        for number, kind in enumerate(kinds):
            placed_kind = "x" in defaults[TYPES_BY_NAME[kind]].names()
            components.append(table("c%d" % number, kind, **(
                {"x": 10 + number % 10 * 78, "y": 10 + number // 10 * 60, "w": 60, "h": 40}
                if placed_kind else {})))
        self.page("page0", components)
        self.program("bkcmd=3\npage page0\n")
        cases = [(name, kind, attribute)
                 for name, kind in [("c%d" % number, kind) for number, kind in enumerate(kinds)]
                 + [("page0", "page")]
                 for attribute in defaults[TYPES_BY_NAME[kind]].names()
                 if attribute not in ("movex", "movey") and code_cannot_change(kind, attribute)
                 and not describe(kind, attribute).method]
        # The probe's 170, and the 9 compared before it.
        self.assertEqual(len(cases), 179)
        self.assertLessEqual(self.ANSWERED_AS_UNKNOWN, {(kind, attribute)
                                                        for _, kind, attribute in cases})
        start = Simulation(self.root).values()
        for name, kind, attribute in cases:
            value = '"x"' if is_string_attribute(TYPES_BY_NAME[kind], attribute) else "1"
            with self.subTest(kind=kind, attribute=attribute):
                sent = []
                simulation = Simulation(self.root, sending=sent.append)
                sent.clear()
                simulation.serial_input("%s.%s=%s" % (name, attribute, value))
                self.assertEqual(sent, [bytes([0x1A if (kind, attribute) in
                                               self.ANSWERED_AS_UNKNOWN else 0x1C]) + b"\xff" * 3])
                # Refused, it keeps what it held.
                key = "%s.%s" % (name, attribute)
                self.assertEqual(simulation.values().get(key), start.get(key))


class SerialHoldTest(SimulationTestCase):
    """com_stop holds the instructions the serial line brings, unanswered,
    until com_star runs them in order, as the Editor's simulator showed:
    com_stop sent on the serial line or run by a page's code alike. Neither
    answers, whatever bkcmd asks."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("stop", "button", 0, 0), placed("go", "button", 0, 100),
                            placed("again", "button", 0, 200),
                            placed("next", "button", 0, 300)], """\
on stop.down:
  com_stop

on go.down:
  com_star
  sys1 = sys0

on again.down:
  rest

on next.down:
  page second
""")
        self.page("second", [placed("back", "button", 0, 0)], "on back.down:\n  page page0\n")

    def serial(self, simulation: Simulation, *texts: str) -> list:
        """Sends `texts` on the serial line; returns the lines they logged."""
        before = len(simulation.log)
        for text in texts:
            simulation.serial_input(text)
        return [line for _, line in simulation.log[before:]]

    def test_the_held_instructions_overflow_the_serial_buffer(self):
        # The screen's serial buffer holds 1024 bytes. Past them, as the
        # vendor says, the instructions held before are lost, and the one
        # arriving is kept. The screen answers 0x24 once for the piece.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        simulation.serial_received(b"com_stop\xff\xff\xff" + b"sys0=sys0+1\xff\xff\xff" * 73)
        self.assertEqual(sent, [])
        simulation.serial_received(b"sys0=sys0+1\xff\xff\xff" * 2)
        self.assertEqual(sent, [b"\x24\xff\xff\xff"])
        self.assertIn("serial line: the serial buffer overflowed, 1022 bytes of held "
                      "instructions dropped", [line for _, line in simulation.log])
        simulation.serial_received(b"com_star\xff\xff\xff")
        self.assertEqual(simulation.globals["sys0"], 2)

    def test_held_until_com_star_on_the_serial_line(self):
        simulation = Simulation(self.root, values={"bkcmd": 3})
        self.assertEqual(self.serial(simulation, "com_stop", "sys0=5", "get sys0"), [
            "receives com_stop", "receives sys0=5", "held: the serial line is stopped",
            "receives get sys0", "held: the serial line is stopped"])
        self.assertEqual(simulation.globals["sys0"], 0)
        self.assertEqual(self.serial(simulation, "com_star"), [
            "receives com_star", "runs sys0=5, held until com_star", "sends 01 ff ff ff",
            "runs get sys0, held until com_star", "sends 71 05 00 00 00 ff ff ff (get)"])
        self.assertEqual(simulation.globals["sys0"], 5)

    def test_held_after_com_stop_run_by_code(self):
        simulation = Simulation(self.root)
        simulation.press("stop")
        simulation.release()
        self.serial(simulation, "sys0=5")
        self.assertEqual(simulation.globals["sys0"], 0)
        self.serial(simulation, "com_star")
        self.assertEqual(simulation.globals["sys0"], 5)

    def test_com_star_run_by_code_runs_them_once_its_event_ends(self):
        simulation = Simulation(self.root)
        self.serial(simulation, "com_stop", "sys0=5")
        simulation.press("go")
        # The event read sys0 before the held instruction ran.
        self.assertEqual((simulation.globals["sys1"], simulation.globals["sys0"]), (0, 5))

    def test_what_is_assumed(self):
        # com_star with nothing held, and a second com_stop, change nothing.
        simulation = Simulation(self.root)
        self.serial(simulation, "com_star", "sys0=1", "com_stop", "com_stop", "sys0=2")
        self.assertEqual(simulation.globals["sys0"], 1)
        # A touch, and a page change, go on, leaving the held instructions waiting.
        for button in ("stop", "next"):
            simulation.press(button)
            simulation.release()
        self.assertEqual(simulation.page, "second")
        self.serial(simulation, "com_star")
        self.assertEqual(simulation.globals["sys0"], 2)

    def test_rest_drops_them_and_keeps_the_line_held(self):
        # As the Nextion Editor's simulator did: run by code while the line
        # was held, rest started the screen again without the held
        # instructions, and what came after stayed held until com_star.
        simulation = Simulation(self.root)
        self.serial(simulation, "com_stop", "sys0=3")
        simulation.press("again")
        self.assertEqual((simulation.starts, simulation.globals["sys0"]), (2, 0))
        self.serial(simulation, "sys0=4")
        self.assertEqual(simulation.globals["sys0"], 0)
        self.serial(simulation, "com_star")
        self.assertEqual(simulation.globals["sys0"], 4)
        # Starting again as power does frees the line.
        self.serial(simulation, "com_stop")
        simulation.start_again()
        self.serial(simulation, "sys0=5")
        self.assertEqual(simulation.globals["sys0"], 5)

    def test_a_held_instruction_restarting_or_stopping_again(self):
        # A held rest drops those after it; a held click whose code runs
        # com_stop holds them again.
        simulation = Simulation(self.root)
        self.serial(simulation, "com_stop", "rest", "sys0=5", "com_star")
        self.assertEqual((simulation.starts, simulation.globals["sys0"]), (2, 0))
        self.serial(simulation, "com_stop", "click stop,1", "sys0=6", "com_star")
        self.assertEqual(simulation.globals["sys0"], 0)
        self.serial(simulation, "com_star")
        self.assertEqual(simulation.globals["sys0"], 6)

    def test_code_holding_the_line_is_logged(self):
        simulation = Simulation(self.root)
        for button in ("stop", "go"):
            simulation.press(button)
        self.assertEqual([line for _, line in simulation.log], [
            "com_stop: the serial line's instructions are held",
            "com_star: the held instructions run once this event ends"])


class MoveTest(SimulationTestCase):
    """`move` moves a component over its time, as the Editor's simulator
    showed: the moves run in turns, one priority at a time, the highest
    first, the moves of a turn together, each over its own time; a second
    move of a turn's priority for a component is dropped; a move of no time
    ends at once; and code reads `x` and `y` where the move has them
    (moves.py)."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")

    def moves(self, code: str, **pages):
        """Writes page0, with three texts and a button `go` running `code`."""
        self.page("page0", [placed("t0", "text", 0, 40), placed("t1", "text", 0, 160),
                            placed("t2", "text", 0, 280), placed("go", "button", 600, 400),
                            placed("look", "button", 400, 400)],
                  "on go.down:\n" + "".join("  %s\n" % line for line in code.splitlines())
                  + pages.get("look", ""))
        for name, components in pages.get("others", {}).items():
            self.page(name, components)

            def listed(app: dict):
                # "second" is listed already (FolderTestCase).
                if name not in app["pages"]:
                    app["pages"].append(name)
            self.write("app.toml", edited_app(self.text("app.toml"), listed))

    def xs(self, simulation: Simulation) -> tuple:
        values = simulation.values()
        return tuple(values["%s.x" % name] for name in ("t0", "t1", "t2"))

    def test_a_move_goes_over_its_time(self):
        self.moves("move t0,0,40,600,90,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(500)
        values = simulation.values()
        self.assertEqual((values["t0.x"], values["t0.y"]), (300, 65))
        simulation.advance(500)
        values = simulation.values()
        self.assertEqual((values["t0.x"], values["t0.y"]), (600, 90))

    def test_moves_take_turns_by_priority(self):
        # As the Nextion Editor's simulator ran three: 100 first, then 95, then 90.
        self.moves("move t0,0,40,600,40,95,1000\nmove t1,0,160,600,160,90,1000\n"
                   "move t2,0,280,600,280,100,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        for advanced, places in ((500, (0, 0, 300)), (1000, (300, 0, 600)),
                                 (1000, (600, 300, 600)), (1000, (600, 600, 600))):
            simulation.advance(advanced)
            self.assertEqual(self.xs(simulation), places)

    def test_equal_priorities_run_together(self):
        # As the Nextion Editor's simulator ran two moves of 5, over 2 s and
        # 0.5 s, and one of 0: the move of 0 starts once the longer of the
        # two has ended.
        self.moves("move t0,0,40,600,40,5,2000\nmove t1,0,160,600,160,5,500\n"
                   "move t2,0,280,600,280,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        for advanced, places in ((500, (150, 600, 0)), (1500, (600, 600, 0)),
                                 (500, (600, 600, 300))):
            simulation.advance(advanced)
            self.assertEqual(self.xs(simulation), places)

    def test_a_move_of_the_turns_priority_joins_it(self):
        # Given during the turn, it starts at once, and the next turn waits
        # for it too.
        self.moves("move t0,0,40,600,40,5,1000\nmove t2,0,280,600,280,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(300)
        simulation.serial_input("move t1,0,160,600,160,5,1000")
        for advanced, places in ((700, (600, 420, 0)), (300, (600, 600, 0)),
                                 (500, (600, 600, 300))):
            simulation.advance(advanced)
            self.assertEqual(self.xs(simulation), places)

    def test_a_move_given_during_another_waits_its_turn(self):
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(500)
        simulation.serial_input("move t1,0,160,600,160,100,1000")
        simulation.advance(400)
        self.assertEqual(self.xs(simulation), (540, 0, 0))
        simulation.advance(600)
        self.assertEqual(self.xs(simulation), (600, 300, 0))

    def test_a_move_of_lower_priority_given_during_another_waits_its_turn(self):
        self.moves("move t0,0,40,600,40,50,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(300)
        simulation.serial_input("move t1,0,160,600,160,0,1000")
        simulation.advance(700)
        self.assertEqual(self.xs(simulation), (600, 0, 0))
        simulation.advance(500)
        self.assertEqual(self.xs(simulation), (600, 300, 0))

    def test_a_second_move_of_equal_priority_for_a_component_is_dropped(self):
        # Given by the same event or during the first, even when longer than
        # it, it does nothing; the log says so.
        self.moves("move t0,0,40,600,40,0,1000\nmove t0,600,40,300,40,0,3000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(2000)
        self.assertEqual(self.xs(simulation)[0], 600)
        self.assertIn("move t0 from (600, 40) to (300, 40) in 3000 ms, priority 0: dropped, "
                      "as t0 has a move of that priority", [line for _, line in simulation.log])
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(300)
        simulation.serial_input("move t0,600,40,300,40,0,3000")
        simulation.advance(2000)
        self.assertEqual(self.xs(simulation)[0], 600)

    def test_a_move_of_another_priority_for_a_component_runs_in_its_turn(self):
        # Given by the same event, the one of 100 first; given during the
        # move of 0, after it.
        self.moves("move t0,0,40,600,40,0,1000\nmove t0,600,40,300,40,100,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        for advanced, x in ((500, 450), (1000, 300)):
            simulation.advance(advanced)
            self.assertEqual(self.xs(simulation)[0], x)
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(300)
        simulation.serial_input("move t0,600,40,300,40,100,1000")
        for advanced, x in ((700, 600), (500, 450)):
            simulation.advance(advanced)
            self.assertEqual(self.xs(simulation)[0], x)

    def test_a_component_given_by_its_id_moves(self):
        self.moves("move 1,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(1000)
        self.assertEqual(self.xs(simulation), (600, 0, 0))

    def test_a_move_of_no_time_ends_within_its_code(self):
        self.moves("move t0,0,40,600,40,0,0\nsys0=t0.x")
        simulation = Simulation(self.root)
        simulation.press("go")
        self.assertEqual((simulation.globals["sys0"], self.xs(simulation)), (600, (600, 0, 0)))

    def test_a_move_of_no_time_during_another(self):
        # At once, whatever moves: the code after it reads its end. A move
        # running for its component takes it on at its next step.
        self.moves("move t1,0,160,600,160,0,2000",
                   look="on look.down:\n  move t2,0,280,600,280,100,0\n"
                        "  move t1,0,160,100,160,0,0\n  sys0=t2.x\n  sys1=t1.x\n")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(300)
        simulation.press("look")
        self.assertEqual((simulation.globals["sys0"], simulation.globals["sys1"]), (600, 100))
        simulation.advance(40)
        self.assertEqual(self.xs(simulation), (0, 102, 600))

    def test_a_move_of_no_time_in_a_test(self):
        # It needs no clock: a test's code reads its end, and it is recorded.
        self.moves("move t0,0,40,600,40,0,0\nsys0=t0.x")
        values = SourceFolderRunner(self.root).run("page0", [("go", "down")], {"sys0": 0})
        self.assertEqual(values["sys0"], 600)
        self.assertIn(("move", "t0", "0", "40", "600", "40", "0", "0"), values["other commands"])

    def test_a_test_reads_a_moves_arguments(self):
        # As the simulator reads them: an ID no component has is an error.
        self.moves("move 99,0,40,600,40,0,1000")
        values = SourceFolderRunner(self.root).run("page0", [("go", "down")])
        self.assertIn(("move", "99"), values["component errors"])

    def test_a_move_of_no_time_waits_for_ref_star(self):
        # Drawn as code's own `x` is: held back by `ref_stop`.
        self.moves("ref_stop\nmove t0,0,40,600,40,0,0")
        simulation = Simulation(self.root)
        simulation.press("go")

        def drawn_x() -> int:
            return next(component.values["x"]
                        for component in simulation.drawing_inputs().components
                        if component.name == "t0")

        self.assertEqual((drawn_x(), self.xs(simulation)[0]), (0, 600))
        simulation.serial_input("ref_star")
        self.assertEqual(drawn_x(), 600)

    def test_code_after_a_delay_reads_where_the_move_has_it(self):
        self.moves("move t0,0,40,600,40,0,1000",
                   look="on look.down:\n  delay=300\n  sys0 = t0.x\n")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(200)
        simulation.press("look")
        self.assertEqual(simulation.globals["sys0"], 300)

    def test_code_setting_its_x_does_not_stop_the_move(self):
        # Overwritten as the move goes on: code reads where the move has it.
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(500)
        simulation.serial_input("t0.x=5")
        self.assertEqual(self.xs(simulation)[0], 300)
        simulation.advance(100)
        self.assertEqual(self.xs(simulation)[0], 360)

    def test_a_moving_component_is_drawn_again_at_each_step(self):
        # Over what drawing commands painted, as any component that changes.
        self.moves("cls BLUE\nmove t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(MOVE_STEP)
        self.assertEqual(simulation.painted()[-1], ("redraw", "t0"))

    def test_a_move_over_paint_gives_back_the_background_where_it_has_been(self):
        # As a move by code: its start leaves t0's place before it, at
        # (0, 40), and each step the place the step before drew it at.
        self.moves("cls BLUE\nmove t0,0,100,600,100,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        self.assertEqual(simulation.painted(), [("cls", 31), ("left", "t0", (0, 40, 100, 50)),
                                                ("redraw", "t0")])
        simulation.advance(MOVE_STEP)
        self.assertEqual(simulation.painted()[-2:], [("left", "t0", (0, 100, 100, 50)),
                                                     ("redraw", "t0")])

    def test_a_hidden_move_over_paint_marks_nothing(self):
        # As code moving a hidden component gives back no background where
        # it was, as the Nextion Editor's simulator left the paint there
        # (tests/fixtures/drawing-assumptions/, page37).
        self.moves("vis t0,0\ncls BLUE\nmove t0,0,100,600,100,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(5 * MOVE_STEP)
        self.assertEqual([entry for entry in simulation.painted() if entry[1:2] == ("t0",)], [])

    def test_a_move_with_nothing_painted_marks_nothing_but_is_drawn(self):
        # The drawing would be the same, as for a slide; the panel is still
        # told the screen changed. (The press marks the button `go` it drew
        # pressed.)
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        changes = simulation.changes
        simulation.advance(MOVE_STEP)
        self.assertEqual(([entry for entry in simulation.painted() if entry[1] == "t0"],
                          simulation.changes > changes), ([], True))

    def test_a_move_over_a_fill_as_the_editor_draws_it(self):
        # As the Nextion Editor's simulator drew it: page0's loadend paints a
        # fill, then moves t0 from (0, 0) to (300, 250) over 3 seconds. The
        # page's background came back along its path, the edges of the band in
        # steps of about 16 ms. Where the steps fall differs, so pixels near
        # the band's slanted edges are left out: those of the lines its box's
        # top right corner, from (150, 0), and its bottom left corner, from
        # (0, 60), swept.
        self.page("page0", [table("t0", "text", x=0, y=0, w=150, h=60, sta=1, bco=63488,
                                  txt="T0", txt_maxl=10)],
                  "on page0.loadend:\n  fill 0,0,800,480,2016\n  move t0,0,0,300,250,0,3000\n")
        simulation = Simulation(self.root)
        simulation.advance(5000)
        drawn = paint_drawing(screen_drawing(simulation))
        shot = read_picture((Path(__file__).resolve().parent / "fixtures" / "moves" /
                             "over-a-fill.png").read_bytes())
        across = 300 / 250

        def near_an_edge(x: int, y: int) -> bool:
            return any(abs(x - (start_x + (y - start_y) * across)) <= 3
                       for start_x, start_y in ((150, 0), (0, 60)))
        differing = [(x, y) for x, y in differing_pixels(drawn, shot,
                                                         {"x": 0, "y": 0, "w": 800, "h": 480}, 12)
                     if not near_an_edge(x, y)]
        self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_a_long_move_keeps_what_was_painted_and_drawn_after_it(self):
        # Past the record's bound, its oldest "left" marks go first: the
        # start of the band shows the paint again, but the paint stays, and
        # so does t1, set once after it.
        self.moves("cls BLUE\nt1.txt=\"set\"\nmove t0,0,100,600,100,0,10000")
        simulation = Simulation(self.root)
        with mock.patch.object(simulation_module, "_MOST_PAINTED", 20):
            simulation.press("go")
            simulation.advance(2000)
        painted = simulation.painted()
        self.assertEqual(len(painted), 20)
        self.assertEqual(painted[:2], [("cls", 31), ("redraw", "t1")])
        self.assertEqual(painted[-1], ("redraw", "t0"))

    def test_a_move_waits_while_the_screen_sleeps(self):
        self.moves("move t0,0,40,600,40,0,1000")
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(500)
        simulation.serial_input("sleep=1")
        simulation.advance(2000)
        simulation.serial_input("sleep=0")
        simulation.advance(100)
        self.assertEqual(self.xs(simulation)[0], 360)

    def test_a_move_before_any_page_shows_is_logged(self):
        self.program("move t0,0,40,600,40,0,1000\npage page0\n")
        self.moves("")
        simulation = Simulation(self.root)
        self.assertIn("move t0: no page shows yet, so nothing moves",
                      [line for _, line in simulation.log])

    def test_a_page_change_drops_the_queue(self):
        self.moves("move t0,0,40,600,40,0,1000\npage second",
                   others={"second": [placed("b9", "button", 0, 0)]})
        simulation = Simulation(self.root)
        simulation.press("go")
        simulation.advance(2000)
        self.assertEqual(simulation.page, "second")
        self.assertNotIn("t0.x", simulation.values())

    def test_the_test_runner_records_it(self):
        self.moves("move t0,0,40,600,40,0,1000")
        values = SourceFolderRunner(self.root).run("page0", [("go", "down")])
        self.assertIn(("move", "t0", "0", "40", "600", "40", "0", "1000"),
                      values["other commands"])


class TouchDrawingTest(SimulationTestCase):
    """While thdra is 1, a held touch draws where it moves, in the colour
    thc (the vendor's instruction set, 6.5 and 6.6), as lines from each
    place it was at to the next, painted as `line` paints. A touch that
    starts on a component draws over it, and is handled as ever besides."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("b0", "button", 300, 300)], "on b0.down:\n  sys0 = 1\n")
        self.page("second", [])

    def drag(self, simulation: Simulation, component: str, *places):
        simulation.press(component, *places[0])
        for place in places[1:]:
            simulation.move(*place)
        simulation.release()

    def lines(self, simulation: Simulation) -> list:
        return [entry for entry in simulation.painted() if entry[0] == "line"]

    def test_a_touch_draws_lines_in_thc(self):
        # The press draws a dot of 2 by 2 pixels, as the Editor's simulator
        # did; then each move a line.
        simulation = Simulation(self.root, values={"thdra": 1, "thc": 63488})
        self.drag(simulation, "page0", (100, 100), (150, 120), (200, 200))
        self.assertEqual([entry for entry in simulation.painted() if entry[0] != "redraw"],
                         [("fill", 100, 100, 2, 2, 63488), ("line", 100, 100, 150, 120, 63488),
                          ("line", 150, 120, 200, 200, 63488)])

    def test_nothing_drawn_without_thdra(self):
        simulation = Simulation(self.root, values={"thc": 63488})
        self.drag(simulation, "page0", (100, 100), (150, 120))
        self.assertEqual(self.lines(simulation), [])

    def test_a_component_whose_touches_are_off_is_drawn_on(self):
        # It takes the press, and runs nothing, but the screen still draws.
        simulation = Simulation(self.root, values={"thdra": 1, "thc": 31})
        simulation.serial_input("tsw b0,0")
        simulation.press("b0", 310, 310)
        self.assertEqual(simulation.painted(), [("fill", 310, 310, 2, 2, 31)])
        self.assertEqual(simulation.globals["sys0"], 0)

    def test_nothing_drawn_while_the_screen_sleeps(self):
        # A touch on a sleeping screen only wakes it, as it ends (assumed).
        simulation = Simulation(self.root, values={"thdra": 1})
        simulation.serial_input("sleep=1")
        self.drag(simulation, "page0", (100, 100), (150, 120))
        self.assertEqual([entry for entry in simulation.painted() if entry[0] != "redraw"], [])

    def test_a_long_drag_keeps_what_was_painted_bounded(self):
        # With no event to end it, a drag still keeps only the latest painting.
        simulation = Simulation(self.root, values={"thdra": 1})
        with mock.patch.object(simulation_module, "_MOST_PAINTED", 10):
            simulation.press("page0", 0, 0)
            for x in range(1, 30):
                simulation.move(x, 0)
        self.assertEqual(len(simulation.painted()), 10)
        self.assertEqual(simulation.painted()[-1], ("line", 28, 0, 29, 0, 0))

    def test_cls_covers_the_drawing(self):
        simulation = Simulation(self.root, values={"thdra": 1})
        self.drag(simulation, "page0", (100, 100), (150, 120))
        simulation.serial_input("cls WHITE")
        self.assertEqual(simulation.painted(), [("cls", 65535)])

    def test_a_touch_on_a_component_draws_and_runs_its_events(self):
        # The dot shows over the button drawn pressed, as in the Editor's
        # simulator; the release draws the button again over it.
        simulation = Simulation(self.root, values={"thdra": 1, "thc": 31})
        simulation.press("b0", 310, 310)
        simulation.move(320, 330)
        self.assertEqual(simulation.painted(), [("redraw", "b0"), ("fill", 310, 310, 2, 2, 31),
                                                ("line", 310, 310, 320, 330, 31)])
        simulation.release()
        self.assertEqual(simulation.painted()[-1], ("redraw", "b0"))
        self.assertEqual(simulation.globals["sys0"], 1)


class SerialSleepTest(SimulationTestCase):
    """Sleeping and waking by the serial line, and the page shown on waking,
    as the Editor's simulator showed: ussp, usup, and wup."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0), placed("nap", "button", 0, 100)], """\
on nap.down:
  sleep = 1
  sleep = 0
  sys2 = 9
""")
        # Its load event says it loaded, on the serial line.
        self.page("second", [], 'on second.load:\n  prints "S",0\n')

    def test_ussp_sleeps_after_that_many_seconds_without_serial_data(self):
        sent = []
        simulation = Simulation(self.root, values={"ussp": 3}, sending=sent.append)
        simulation.advance(1000)
        simulation.serial_input("sys0=1")       # serial data: it counts again from here
        simulation.press("go")                  # a press does not
        simulation.release()
        simulation.advance(2900)
        self.assertFalse(simulation.asleep)
        simulation.advance(200)
        self.assertTrue(simulation.asleep)
        self.assertEqual(sent, [b"\x86\xff\xff\xff"])

    def test_without_usup_serial_instructions_run_while_it_sleeps(self):
        simulation = Simulation(self.root, values={"ussp": 3})
        simulation.advance(3100)
        simulation.serial_input("sys0=5")
        self.assertTrue(simulation.asleep)
        self.assertEqual(simulation.globals["sys0"], 5)

    def test_with_usup_serial_data_wakes_it_before_its_instruction_runs(self):
        sent = []
        simulation = Simulation(self.root, values={"ussp": 3, "usup": 1}, sending=sent.append)
        simulation.advance(3100)
        simulation.serial_input("get sleep")
        self.assertFalse(simulation.asleep)
        # The instruction read it awake; waking by the serial line sends no 0x87.
        self.assertEqual(sent, [b"\x86\xff\xff\xff", b"\x71\x00\x00\x00\x00\xff\xff\xff"])

    def test_woken_by_the_serial_line_it_is_idle_from_then(self):
        # As the Nextion Editor's simulator counted it.
        simulation = Simulation(self.root, values={"thsp": 2, "usup": 1})
        simulation.advance(2100)
        self.assertTrue(simulation.asleep)
        simulation.serial_input("sys0=1")
        simulation.advance(1000)
        self.assertFalse(simulation.asleep)
        simulation.advance(1100)
        self.assertTrue(simulation.asleep)

    def test_woken_by_a_touch_it_counts_ussp_from_then(self):
        # Waking starts both counts again, as the Nextion Editor's simulator
        # showed for ussp: asleep by ussp, a touch that wakes it leaves it
        # awake for ussp seconds more. Code wakes it only from the serial
        # line, as no event runs while it sleeps, and serial data starts the
        # count again anyway.
        simulation = Simulation(self.root, values={"ussp": 3, "thup": 1})
        simulation.advance(3100)
        simulation.press("go")
        simulation.release()
        simulation.advance(2000)
        self.assertFalse(simulation.asleep)
        simulation.advance(1100)
        self.assertTrue(simulation.asleep)

    def test_wup_shows_its_page_as_the_screen_wakes(self):
        # Woken by a touch: its page loads after the 0x87.
        sent = []
        simulation = Simulation(self.root, values={"thsp": 2, "thup": 1, "wup": 1},
                                sending=sent.append)
        simulation.advance(2100)
        simulation.press("go")
        simulation.release()
        self.assertEqual(simulation.page, "second")
        self.assertEqual(sent, [b"\x86\xff\xff\xff", b"\x87\xff\xff\xff", b"S"])
        # Woken by the serial line: its page loads before the instruction runs.
        sent = []
        simulation = Simulation(self.root, values={"ussp": 3, "usup": 1, "wup": 1},
                                sending=sent.append)
        simulation.advance(3100)
        simulation.serial_input("get sleep")
        self.assertEqual(simulation.page, "second")
        self.assertEqual(sent, [b"\x86\xff\xff\xff", b"S", b"\x71\x00\x00\x00\x00\xff\xff\xff"])

    def test_code_putting_the_screen_to_sleep_ends_the_event(self):
        # As the Nextion Editor's simulator ran it: `sleep=1` in an event put
        # the screen to sleep, and the rest of the event, its `sleep=0` among
        # it, did not run. So no event wakes the screen.
        sent = []
        simulation = Simulation(self.root, values={"wup": 1}, sending=sent.append)
        simulation.press("nap")
        self.assertEqual((simulation.asleep, simulation.page), (True, "page0"))
        self.assertEqual(sent, [])
        self.assertEqual(simulation.globals["sys2"], 0)

    def test_a_press_that_puts_the_screen_to_sleep_ends_as_a_sleeping_touch(self):
        # As the Nextion Editor's simulator ran it: its release sent 0x68, as
        # a touch on a sleeping screen does, and with thup 1 woke the screen,
        # sending 0x87.
        sent = []
        simulation = Simulation(self.root, values={"thup": 1}, sending=sent.append)
        simulation.press("nap", 10, 110)
        self.assertTrue(simulation.asleep)
        simulation.release()
        self.assertFalse(simulation.asleep)
        self.assertEqual(sent, [b"\x68\x00\x0a\x00\x6e\x00\xff\xff\xff", b"\x87\xff\xff\xff"])

    def test_a_click_typed_while_asleep_runs_nothing(self):
        # As the Nextion Editor's simulator ran it: the clicked event did not
        # run, and the screen slept on.
        simulation = Simulation(self.root, values={"ussp": 3})
        simulation.advance(3100)
        simulation.serial_input("click nap,1")
        self.assertTrue(simulation.asleep)
        self.assertEqual(simulation.globals["sys2"], 0)

    def test_a_page_change_in_the_wake_pages_load_runs_its_unload(self):
        # Waking runs no unload of the page it leaves. A page change in the
        # wake page's own load event is an ordinary one, and runs the wake
        # page's unload.
        self.page("second", [], "on second.load:\n  page third\n\non second.unload:\n  sys1 = 4\n")
        self.page("third", [])
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("third")))
        simulation = Simulation(self.root, values={"thsp": 2, "thup": 1, "wup": 1})
        simulation.advance(2100)
        simulation.press("go")
        simulation.release()
        self.assertEqual((simulation.page, simulation.globals["sys1"]), ("third", 4))

    def test_waking_into_the_page_wup_gives_runs_no_unload(self):
        # As the Nextion Editor's simulator ran it: woken by a touch into the
        # page wup gives, the old page's unload event did not run, where a
        # page command runs it.
        self.page("page0", [placed("go", "button", 0, 0)], "on page0.unload:\n  sys1 = 4\n")
        simulation = Simulation(self.root, values={"thsp": 2, "thup": 1, "wup": 1})
        simulation.advance(2100)
        simulation.press("go")
        simulation.release()
        self.assertEqual((simulation.page, simulation.globals["sys1"]), ("second", 0))


class JumpsTest(SimulationTestCase):
    """return in a page's events, and return, goto, and labels typed on the
    serial line, in an app in the Editor's language, as the Editor's
    simulator ran them."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program("int left=0,loaded=0,ended=0\npage 0\n")
        self.page("page0", [placed("go", "button", 0, 0)], """\
on page0.unload:
  left=1
  return
  left=2

on go.down:
  page second
""")
        self.page("second", [], """\
on second.load:
  loaded=1
  return
  loaded=2

on second.loadend:
  ended=1
""")

    def test_a_return_in_unload_or_load(self):
        # One in the old page's unload: the page still changes. One in the new
        # page's load: its loadend does not run either.
        simulation = Simulation(self.root)
        simulation.press("go")
        self.assertEqual(simulation.page, "second")
        self.assertEqual([simulation.globals[name] for name in ("left", "loaded", "ended")],
                         [1, 1, 0])
        # Started on that page, alike.
        simulation = Simulation(self.root, start_page="second")
        self.assertEqual([simulation.globals[name] for name in ("loaded", "ended")], [1, 0])

    def test_typed_on_the_serial_line(self):
        # return and goto are invalid instructions, a label an invalid variable.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        for text in ("return", "goto later", "later:"):
            simulation.serial_input(text)
        self.assertEqual(sent, [b"\x00\xff\xff\xff", b"\x00\xff\xff\xff", b"\x1a\xff\xff\xff"])

    def test_typed_code_nxwright_refuses_is_an_invalid_instruction(self):
        # Refused code and a line nxwright cannot read are errors of nxwright,
        # as an invalid page is, but each answers 0x00, not that page's 0x03.
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        for text in ("sys0=0x0100000000", "covx sys0,sys1,0,3", "sys0 = = 2"):
            simulation.serial_input(text)
        self.assertEqual(sent, [b"\x00\xff\xff\xff"] * 3)



class NxlangDataRecordCallTest(SimulationTestCase):
    """A data record's call in nxlang whose argument the Editor would not take
    as written, text joined: nxlang computes it first, so the folder builds,
    and the call runs."""

    def setUp(self):
        super().setUp()
        self.page("page0", [table("d0", "data-record", x=10, y=10, w=380, h=200,
                                  path="sd0/d.data", lenth=31, dez=2, maxval=10, dir="A^B"),
                            placed("t0", "text", 10, 250, txt="42")],
                  'on page0.load:\n  d0.insert("Total^" + t0.txt)\n')

    def test_built_and_run(self):
        self.assertEqual(self.findings(), [])
        # The simulator compiles the page through the test runner.
        self.assertEqual(Simulation(self.root).listings()["d0"], ["Total^42"])
        # The editing help shows the code as the build compiles it.
        [(_, lines)] = read_folder_source(folder_reader(self.root)).editor_code(
            "page0", "pages/page0.nx")
        self.assertEqual([line for _, line in lines],
                         ['__s0.txt="Total^"+t0.txt', "d0.insert(__s0.txt)"])

    def test_extracting_keeps_the_source(self):
        before = self.text("pages/page0.nx")
        project = self.root.parent / "project.HMI"
        build(self.root, project)
        extract(project, self.root)
        self.assertEqual(self.text("pages/page0.nx"), before)


if __name__ == "__main__":
    unittest.main()
