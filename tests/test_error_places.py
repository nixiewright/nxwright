"""The place an error comes from, as its message gives it (place_text): the
file, then a colon and the line, written so that a terminal or a code editor
can open the file. A command shows the file under the folder as the user gave
it on the command line, and a test's runner shows it under the folder's full
path."""
import contextlib
import io
from pathlib import Path
import shutil
import unittest

from nxwright import NxwrightError, after_start, place_text
from nxwright.cli import main
from nxwright.testing import SourceFolderRunner
from tests.test_folder_check import FolderTestCase, edited_app
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware


class PlaceTextTest(unittest.TestCase):

    def test_a_file_and_a_line(self):
        self.assertEqual(place_text("pages/home.nx", 12), "pages/home.nx:12")

    def test_a_file_without_a_line(self):
        self.assertEqual(place_text("app.toml"), "app.toml")
        # A finding without a line has line 0.
        self.assertEqual(place_text("app.toml", 0), "app.toml")

    def test_under_a_folder(self):
        self.assertEqual(place_text("pages/home.nx", 12, "demo"),
                         "%s:12" % Path("demo", "pages", "home.nx"))
        self.assertEqual(place_text("app.toml", folder=Path("demo")),
                         str(Path("demo", "app.toml")))


class ErrorTextTest(unittest.TestCase):

    def test_a_file_and_a_line_start_the_message(self):
        self.assertEqual(str(NxwrightError("no good", file="pages/a.nx", line=3)),
                         "pages/a.nx:3: no good")
        self.assertEqual(str(NxwrightError("no good", file="app.toml")), "app.toml: no good")

    def test_a_line_without_a_file(self):
        # A line of code that is checked outside any file.
        self.assertEqual(str(NxwrightError("no good", line=3)), "line 3: no good")

    def test_a_file_set_afterwards_is_not_shown(self):
        # The reason already gives the file. A file set afterwards is data for
        # a code editor, so the message gains neither the file nor the folder.
        error = NxwrightError("app.toml: no good")
        error.file = "app.toml"
        self.assertEqual(str(error.in_folder("demo")), "app.toml: no good")

    def test_a_folder_shows_the_file_under_it(self):
        error = NxwrightError("no good", file="pages/a.nx", line=3).in_folder("demo")
        self.assertEqual(str(error), "%s:3: no good" % Path("demo", "pages", "a.nx"))
        # The first folder given stays.
        self.assertEqual(str(error.in_folder("other")),
                         "%s:3: no good" % Path("demo", "pages", "a.nx"))

    def test_in_file_keeps_the_folder(self):
        error = NxwrightError("no good", line=3).in_folder("demo").in_file("pages/a.nx")
        self.assertEqual(str(error), "%s:3: no good" % Path("demo", "pages", "a.nx"))

    def test_in_file_keeps_the_key(self):
        error = NxwrightError("no good", key="rotation").in_file("app.toml")
        self.assertEqual((error.key, str(error)), ("rotation", "app.toml: no good"))

    def test_a_place_with_the_event_or_function_of_its_line(self):
        error = NxwrightError("no value")
        error.at_place("pages/a.nx", 3, "go.down")
        self.assertEqual((str(error), error.reason, error.file, error.line),
                         ("pages/a.nx:3 (go.down): no value", "no value", "pages/a.nx", 3))


class RunnerTest(FolderTestCase):
    """A test has no command line, so the runner's errors show the file under
    the source folder's full path."""

    def test_an_error_in_the_macros(self):
        self.write("macros.nx", "macro m:\n  bogus.txt = 1\n")
        with self.assertRaises(NxwrightError) as raised:
            SourceFolderRunner(self.root).macros()
        self.assertTrue(str(raised.exception).startswith(
            "%s:2: " % (self.root.resolve() / "macros.nx")), str(raised.exception))

    def test_an_error_in_a_page_file(self):
        self.write("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n")
        with self.assertRaises(NxwrightError) as raised:
            SourceFolderRunner(self.root).runnable_page("page0")
        self.assertTrue(str(raised.exception).startswith(
            "%s:2: " % (self.root.resolve() / "pages" / "page0.nx")), str(raised.exception))


class CommandTestCase(FolderTestCase):
    """Tests that run commands on a source folder given by a relative path,
    "app"."""

    def run_in_parent(self, arguments: list) -> tuple:
        """Runs the command line `arguments` from the folder that contains
        "app", and returns its exit code, its standard output, and its error
        output."""
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.chdir(self.root.parent), contextlib.redirect_stdout(output), \
                contextlib.redirect_stderr(errors):
            code = main(arguments)
        return code, output.getvalue(), errors.getvalue()


class CommandLineTest(CommandTestCase):
    """An error at a line of a page's code, as each command prints it."""

    def setUp(self):
        super().setUp()
        self.write("pages/page0.nx", "on page0.load:\n  bogus.txt = 1\n")
        self.place = "%s:2: " % Path("app", "pages", "page0.nx")
        self.reason = "`bogus` is neither a page nor a component of this page"

    def test_a_command_with_one_folder(self):
        code, _, errors = self.run_in_parent(["build", "app", "app.HMI"])
        self.assertEqual((code, errors), (1, "nxwright build: %s%s\n" % (self.place, self.reason)))

    def test_check(self):
        _, output, _ = self.run_in_parent(["check", "app"])
        self.assertEqual(output, "%s:2: error: %s\n"
                         % (Path("app", "pages", "page0.nx"), self.reason))

    def test_check_gives_a_file_without_a_line_once(self):
        self.write("pages/page0.nx", "")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(defines={"LIMIT": 3})))
        self.write("program.nx", "const LIMIT = 3\n" + self.text("program.nx"))
        _, output, _ = self.run_in_parent(["check", "app"])
        self.assertEqual(output, "%s: error: in `[defines]`, `LIMIT`: `LIMIT` already exists as "
                                 "a constant, it cannot be redefined\n" % Path("app", "app.toml"))

    def test_compile(self):
        with stand_in_firmware(self.root.parent / "cache"):
            (self.root.parent / "firmware.tft").write_bytes(made_tft("T"))
            code, _, errors = self.run_in_parent(["compile", "app", "app.tft", "--firmware",
                                                  "firmware.tft"])
        self.assertEqual((code, errors),
                         (1, "nxwright compile: %s%s\n" % (self.place, self.reason)))

    def test_diff_gives_each_side_its_own_folder(self):
        # The second side has the error, so the place is under that folder.
        shutil.copytree(self.root, self.root.parent / "other")
        self.write("pages/page0.nx", "")
        code, _, errors = self.run_in_parent(["diff", "app", "other"])
        self.assertEqual((code, errors),
                         (1, "nxwright diff: %s:2: %s\n"
                          % (Path("other", "pages", "page0.nx"), self.reason)))


class FileContentTest(CommandTestCase):
    """An error about what a file of the folder contains starts with that
    file, and with the line when the code can find one. `nxwright build` and
    `nxwright check` give the same place."""

    APP = Path("app", "app.toml")
    PAGE = Path("app", "pages", "page0.page.toml")

    def line_of(self, path: str, text: str) -> int:
        """Returns the line, from 1, of the folder's file `path` that is `text`."""
        return self.text(path).split("\n").index(text) + 1

    def assert_both_print(self, expected: str):
        """Asserts that `nxwright build` stops with the error `expected`, its
        place and its message, and that `nxwright check` reports the same
        place and message as its one error."""
        code, _, errors = self.run_in_parent(["build", "app", "app.HMI"])
        self.assertEqual((code, errors), (1, "nxwright build: %s\n" % expected))
        _, output, _ = self.run_in_parent(["check", "app"])
        found = [line.replace(": error: ", ": ", 1) for line in output.split("\n")
                 if ": error: " in line]
        self.assertEqual(found, [expected])

    def add_component(self, table: str):
        self.write("pages/page0.page.toml",
                   self.text("pages/page0.page.toml") + "\n[[component]]\n" + table)

    def test_a_key_of_app_toml(self):
        self.write("app.toml", self.text("app.toml").replace("format = 1\n",
                                                             "format = 1\ncolour = 1\n"))
        self.assert_both_print("%s:2: unknown key `colour`" % self.APP)

    def test_a_key_of_a_table_of_app_toml(self):
        self.write("app.toml", self.text("app.toml")
                   + '\n[mcu]\nemulator = "../mcu/main.py"\nwait = -1\n')
        self.assert_both_print("%s:%d: wait in [mcu] must be a number of seconds, 0 or more, "
                               "such as 10" % (self.APP, self.line_of("app.toml", "wait = -1")))

    def test_a_define(self):
        self.write("app.toml", self.text("app.toml") + "\n[defines]\nLIMIT = true\n")
        self.assert_both_print("%s:%d: the define LIMIT must be a whole number or a text"
                               % (self.APP, self.line_of("app.toml", "LIMIT = true")))

    def test_an_error_that_is_not_about_one_key_has_no_line(self):
        self.write("app.toml", self.text("app.toml").replace("format = 1\n", ""))
        self.assert_both_print("%s: `format` must be 1" % self.APP)

    def test_an_app_toml_that_is_not_toml(self):
        self.write("app.toml", self.text("app.toml") + "colour = = 1\n")
        line = self.line_of("app.toml", "colour = = 1")
        self.assert_both_print("%s:%d: Invalid value (at line %d, column 10)"
                               % (self.APP, line, line))

    def test_a_value_given_on_the_command_line_has_no_place(self):
        code, _, errors = self.run_in_parent(["build", "app", "app.HMI", "--define", "LIMIT=3"])
        self.assertEqual((code, errors),
                         (1, "nxwright build: --define LIMIT: app.toml's [defines] does not "
                             "declare LIMIT (it declares none)\n"))

    def test_defaults_toml(self):
        self.write("defaults.toml", "[nothing]\nevents = []\n\n" + self.text("defaults.toml"))
        self.assert_both_print("%s: [nothing] is not a component type's defaults"
                               % Path("app", "defaults.toml"))

    def test_a_table_of_a_page_file(self):
        self.add_component('name = "t0"\ntype = "text"\nx = 0\ny = 0\nw = 50\nh = 20\nfoo = 1\n')
        header = self.line_of("pages/page0.page.toml", 'name = "t0"') - 1
        self.assert_both_print("%s:%d: object 2: unknown attribute foo" % (self.PAGE, header))

    def test_a_component_past_the_screen(self):
        self.use_screen("NX4832T035")
        self.add_component('name = "t0"\ntype = "text"\nx = 300\ny = 0\nw = 50\nh = 20\n')
        header = self.line_of("pages/page0.page.toml", 'name = "t0"') - 1
        self.assert_both_print("%s:%d: component `t0` reaches past the screen, which is 320 by "
                               "480 at this rotation" % (self.PAGE, header))

    def test_a_type_the_series_refuses(self):
        self.use_screen("NX4832F035")
        self.add_component('name = "gm0"\ntype = "gmov"\nx = 0\ny = 0\nw = 80\nh = 60\n')
        header = self.line_of("pages/page0.page.toml", 'name = "gm0"') - 1
        self.assert_both_print("%s:%d: component `gm0` is of type `gmov`, which is not "
                               "available on the NX4832F035" % (self.PAGE, header))

    def test_a_page_file_without_its_page_table(self):
        self.write("pages/page0.page.toml", 'name = "page0"\n')
        self.assert_both_print("%s: the [page] table is missing" % self.PAGE)

    def test_an_event_that_the_page_file_does_not_list(self):
        self.write("pages/page0.nx", "on title.slide:\n  sys0 = 1\n")
        self.assert_both_print("%s: title.slide is not an event listed in the page's "
                               ".page.toml file" % Path("app", "pages", "page0.nx"))

    def test_a_character_the_encoding_cannot_store_in_a_page_s_code(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'type = "page"\n', 'type = "page"\nevents = ["load"]\n', 1))
        self.write("pages/page0.nx", 'on page0.load:\n  print "温"\n')
        self.assert_both_print("%s: page0.load: iso-8859-1 cannot store '温'"
                               % Path("app", "pages", "page0.nx"))

    def test_a_character_the_encoding_cannot_store_in_program_nx(self):
        self.write("program.nx", self.text("program.nx") + '\nprint "温"\n')
        self.assert_both_print("%s: iso-8859-1 cannot store '温'" % Path("app", "program.nx"))


class StartOfAMessageTest(unittest.TestCase):

    def test_a_message_after_the_start_its_caller_gives(self):
        self.assertEqual(after_start("pages/00-home.txt", "no good"), "pages/00-home.txt: no good")

    def test_a_message_without_a_start(self):
        self.assertEqual(after_start("", "no good"), "no good")
