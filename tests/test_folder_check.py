"""nxwright check: the build's errors with their places, the warnings the
build does not give, and each page's measures against its limits."""
import contextlib
import io
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

import tomli_w

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.source.folder_check import check_folder
from nxwright.source.lint import ERROR, WARNING, Finding
from nxwright.project.component_defaults import defaults_from_toml
from nxwright.source.page_source import page_file_text, page_table_at_screen
from nxwright.source.project_files import build
from nxwright.source.device_keys import DEVICE_KEYS
from nxwright.source.source_folder import (export_dump, folder_reader, new_source_folder,
                                           page_toml_components, read_page_components,
                                           read_page_toml)
from tests.test_build_checks import add_component


def edited_app(app_text: str, edit) -> str:
    """Returns app.toml's text once `edit` has changed its data, a dict, in
    place. It is edited as data, not as text, as tomli-w lays its lists out
    its own way."""
    app = tomllib.loads(app_text)
    edit(app)
    return tomli_w.dumps(app)


def edited_page_file(page_text: str, edit) -> str:
    """Returns a page file's text once `edit` has changed its tables in place:
    a list of dicts, the page's first. It is written as the build writes a
    page file (page_source.page_file_text)."""
    data = tomllib.loads(page_text)
    tables = [data["page"]] + data.get("component", [])
    edit(tables)
    return page_file_text(tables)


def fonts_first(app_text: str, names: list) -> str:
    """Returns app.toml's text with `names` listed before the folder's other
    fonts, each once, so that its components' font 0 is the first of them:
    a folder `nxwright new` starts already holds Noto Sans."""
    def listed(app: dict):
        app["fonts"] = list(names) + [name for name in app["fonts"] if name not in names]
    return edited_app(app_text, listed)


class FolderTestCase(unittest.TestCase):
    """A source folder started as `nxwright new` starts one, in nxlang, with
    a second page, "second", and a text component "title" on each page."""
    language = "nxlang"

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name) / "app"
        new_source_folder(self.root, DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1"),
                          self.language)
        self.write("pages/second.page.toml",
                   self.text("pages/page0.page.toml").replace('name = "page0"', 'name = "second"'))
        self.write("pages/second.nx", "")
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app["pages"].append("second")))
        for page in ("page0", "second"):
            add_component(self.root / "pages" / ("%s.page.toml" % page), "title", "x")

    def tearDown(self):
        self._folder.cleanup()

    def text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8")

    def write(self, path: str, text: str):
        (self.root / path).parent.mkdir(parents=True, exist_ok=True)
        (self.root / path).write_text(text, encoding="utf-8", newline="\n")

    def check(self, pages: list = None):
        return check_folder(folder_reader(self.root), lambda path: (self.root / path).is_file(),
                            pages)

    def findings(self) -> list:
        return self.check().findings()

    def use_screen(self, model: str, rotation: int = 0):
        """Sets app.toml's screen to `model` at `rotation`, and gives each
        page that screen's size, as `nxwright device` does."""
        self.write("app.toml", edited_app(self.text("app.toml"), lambda app: app.update(
            screen=model, rotation=rotation)))
        width, height = DeviceSettings(model_named(model), rotation, "iso-8859-1").page_size
        for page in ("page0", "second"):
            path = "pages/%s.page.toml" % page
            self.write(path, re.sub(r"(?m)^w = \d+\nh = \d+$", "w = %d\nh = %d" % (width, height),
                                    self.text(path), count=1))


class ErrorPlaceTest(FolderTestCase):

    def test_a_page_file(self):
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n  bogus.txt = 1\n")
        self.assertEqual(self.findings(), [Finding("pages/page0.nx", 3, ERROR,
                                                   "bogus is neither on this page nor a page")])

    def test_an_included_file(self):
        self.write("pages/lib/show.nx", "function show():\n  bogus.txt = 1\n")
        self.write("pages/page0.nx", 'include "lib/show.nx"\non page0.load:\n  show()\n')
        self.assertEqual(self.findings(), [Finding("pages/lib/show.nx", 2, ERROR,
                                                   "bogus is neither on this page nor a page")])

    def test_program_nx(self):
        self.write("program.nx", "int counter=0\nint __bad=0\n")
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line), ("program.nx", 2))
        self.assertTrue(finding.message.startswith("int __bad may not start with '__'"))

    def test_a_system_variable_the_series_lacks(self):
        self.use_screen("NX4832K035")
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n  sys0 = volume\n")
        self.assertEqual(self.findings(), [Finding(
            "pages/page0.nx", 3, ERROR, "sys0=volume: the NX4832K035 lacks volume, and the "
                                        "Nextion Editor refuses to compile it for its series "
                                        "(\"Do not support such variable for this series "
                                        "device\")")])

    def test_a_table_of_a_page_file(self):
        self.write("pages/second.page.toml", self.text("pages/second.page.toml").replace(
            "w = 100", 'w = "x"'))
        [finding] = self.findings()
        header = self.text("pages/second.page.toml").split("\n").index("[[component]]") + 1
        self.assertEqual((finding.file, finding.line), ("pages/second.page.toml", header))
        self.assertIn("w must be a number", finding.message)

    def test_a_table_whose_name_is_a_list(self):
        # As a table being typed may hold: the table's own error, at its
        # header, where Python's TypeError stopped the check.
        self.write("pages/second.page.toml", self.text("pages/second.page.toml")
                   + '\n[[component]]\nname = ["odd"]\ntype = "text"\n')
        [finding] = self.findings()
        lines = self.text("pages/second.page.toml").split("\n")
        header = len(lines) - lines[::-1].index("[[component]]")
        self.assertEqual((finding.file, finding.line), ("pages/second.page.toml", header))
        self.assertIn("name must be a plain name", finding.message)
        with self.assertRaisesRegex(NxwrightError, "name must be a plain name"):
            build(self.root, Path(self._folder.name) / "out.HMI")

    def test_a_name_longer_than_the_editor_keeps(self):
        add_component(self.root / "pages" / "page0.page.toml", "abcdefghijklmno", "x")
        [finding] = self.findings()
        last_header = max(number for number, line in
                          enumerate(self.text("pages/page0.page.toml").split("\n"), start=1)
                          if line == "[[component]]")
        self.assertEqual((finding.file, finding.line), ("pages/page0.page.toml", last_header))

    def test_a_page_past_a_cap(self):
        # On the line of the first component past the cap: the sixth waveform.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "".join(
            '\n[[component]]\nname = "s%d"\ntype = "waveform"\nx = 0\ny = 0\nw = 100\nh = 50\n'
            % number for number in range(6)))
        [finding] = self.findings()
        last_header = max(number for number, line in
                          enumerate(self.text("pages/page0.page.toml").split("\n"), start=1)
                          if line == "[[component]]")
        self.assertEqual((finding.file, finding.line), ("pages/page0.page.toml", last_header))
        self.assertIn("component s5: the page holds 6 waveforms", finding.message)

    def test_a_type_the_series_refuses(self):
        # At the component's table, as the page's other limits.
        self.use_screen("NX4832F035")
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "gm0"\ntype = "gmov"\nx = 0\ny = 0\nw = 80\n'
                   'h = 60\n')
        [finding] = self.findings()
        last_header = max(number for number, line in
                          enumerate(self.text("pages/page0.page.toml").split("\n"), start=1)
                          if line == "[[component]]")
        self.assertEqual((finding.file, finding.line), ("pages/page0.page.toml", last_header))
        self.assertIn("component gm0: the NX4832F035 lacks the type gmov", finding.message)

    def test_a_line_the_editors_compile_refuses(self):
        # nxlang hands an escape and a variable's attribute on as written, and
        # the refusal names the nxlang line.
        with open(self.root / "pages" / "page0.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "va0"\ntype = "variable"\nsta = 1\n')
        for code, words in (('title.txt = "a\\nb"', "Improper use of escape characters"),
                            ("sys0 = va0.val", "Invalid Variables"),
                            ("cls 1, 2", "Invalid number of arguments"),
                            ("zork 1", "Invalid command")):
            with self.subTest(code=code):
                self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n  %s\n" % code)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line), ("pages/page0.nx", 3))
                self.assertIn(words, finding.message)

    def test_a_file_problem_without_a_line(self):
        self.write("pages/page0.page.toml", "[page]\nname = \"other\"\n")
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line), ("pages/page0.page.toml", 0))

    def test_in_file_keeps_the_type_and_the_line(self):
        class Special(NxwrightError):
            pass
        error = Special("no good", line=3).in_file("pages/a.nx", shown="a.nx")
        self.assertIsInstance(error, Special)
        self.assertEqual((str(error), error.reason, error.file, error.line),
                         ("a.nx line 3: no good", "no good", "pages/a.nx", 3))


class CheckTest(FolderTestCase):

    def test_a_clean_folder(self):
        self.assertEqual(self.findings(), [])

    def test_files_saved_with_a_byte_order_mark(self):
        # VS Code's "UTF-8 with BOM" starts a file with the bytes EF BB BF.
        # The file reads as it would without them.
        self.write("pages/page0.nx", "on page0.load:\n  title.txt = \"a\"\n")
        for path in ("app.toml", "pages/page0.nx", "pages/page0.page.toml"):
            (self.root / path).write_bytes(b"\xef\xbb\xbf" + (self.root / path).read_bytes())
        self.assertEqual(self.findings(), [])

    def test_the_first_error_of_each_page(self):
        self.write("pages/page0.nx", "on page0.load:\n  one.txt = 1\n  two.txt = 1\n")
        self.write("pages/second.nx", "on second.load:\n  three.txt = 1\n")
        self.assertEqual([(finding.file, finding.line) for finding in self.findings()],
                         [("pages/page0.nx", 2), ("pages/second.nx", 2)])

    def test_a_half_typed_page_file_does_not_hide_the_other_pages(self):
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "[[component\n")
        self.write("pages/second.nx", "on second.load:\n  bogus.txt = 1\n")
        self.assertEqual([finding.file for finding in self.findings()],
                         ["pages/page0.page.toml", "pages/second.nx"])

    def test_a_half_typed_page_file_gives_other_pages_no_false_errors(self):
        # While page0's file does not read, its names are unknown, so the
        # references to it are not checked. One to a page that does not exist still is.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + "[[component\n")
        self.write("pages/second.nx", 'on second.load:\n  page0.title.txt = "a"\n'
                                      '  page0.bco = 0\n  nothing.title.txt = "b"\n')
        findings = self.findings()
        self.assertEqual([finding.file for finding in findings],
                         ["pages/page0.page.toml", "pages/second.nx"])
        self.assertEqual((findings[1].line, findings[1].message),
                         (4, "nothing is neither on this page nor a page"))

    def test_an_error_every_page_depends_on_comes_alone(self):
        self.write("pages/page0.nx", "on page0.load:\n  one.txt = 1\n")
        self.write("app.toml", self.text("app.toml").replace("format = 1", "format = 9"))
        [finding] = self.findings()
        self.assertEqual(finding.file, "app.toml")

    def test_a_missing_picture(self):
        app = edited_app(self.text("app.toml"), lambda app: app.update(pictures=["logo"]))
        self.write("app.toml", app)
        # At the line of its name.
        line = next(number for number, text in enumerate(app.splitlines(), 1) if '"logo"' in text)
        missing = "pictures/logo.png, .jpg, .jpeg, .bmp, or .gif is missing"
        self.assertEqual(self.findings(), [Finding("app.toml", line, ERROR, missing)])

    def test_some_pages(self):
        self.write("pages/page0.nx", "on page0.load:\n  one.txt = 1\n")
        self.write("pages/second.nx", "on second.load:\n  two.txt = 1\n")
        result = self.check(["second"])
        self.assertEqual(list(result.page_findings), ["second"])

    def test_measures(self):
        self.write("pages/page0.nx", "function inner():\n  sys0 = 1\n\nfunction outer():\n"
                                     "  inner()\n\non page0.load:\n  var n = sys0 + 1\n  outer()\n")
        measures = self.check().measures["page0"]
        self.assertEqual(measures.chain, ["page0.load", "outer", "inner"])
        # The page, its title, and the hotspots of the two call depths.
        self.assertEqual(measures.objects, 4)
        self.assertGreater(measures.globals_used, 0)


class CommandTest(FolderTestCase):

    def run_check(self) -> tuple:
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(["check", str(self.root)])
        return code, output.getvalue(), errors.getvalue()

    def test_a_clean_folder(self):
        self.assertEqual(self.run_check(), (0, "0 errors, 0 warnings\n", ""))

    def test_errors_and_warnings(self):
        self.write("pages/page0.nx", "const UNUSED = 1\n\non page0.load:\n  bogus.txt = 1\n")
        code, output, errors = self.run_check()
        self.assertEqual(code, 1)
        self.assertEqual(output, "pages/page0.nx line 4: error: bogus is neither on this page "
                                 "nor a page\npages/page0.nx line 1: warning: constant UNUSED "
                                 "is not used\n")
        self.assertEqual(errors, "nxwright check: 1 errors, 1 warnings\n")


class NxlangWarningTest(FolderTestCase):

    def warnings(self) -> list:
        return [(finding.file, finding.line, finding.rule) for finding in self.findings()
                if finding.severity == WARNING]

    def test_an_unused_constant(self):
        self.write("pages/page0.nx", "const USED = 1\nconst UNUSED = 2\n\non page0.load:\n"
                                     "  sys0 = USED\n")
        self.assertEqual(self.warnings(), [("pages/page0.nx", 2, "unused-constant")])

    def test_the_form_of_an_own_attribute_is_no_use_of_a_constant(self):
        # '&bco&' names the page's bco, not the constant bco.
        self.write("pages/page0.nx", "const bco = 2\n\non page0.load:\n  '&bco&' = 1\n")
        self.assertEqual(self.warnings(), [("pages/page0.nx", 1, "unused-constant")])

    def test_a_constant_of_program_nx(self):
        self.write("program.nx", "const SPEED = 3\n" + self.text("program.nx"))
        self.assertEqual(self.warnings(), [("program.nx", 1, "unused-constant")])
        self.write("pages/second.nx", "on second.load:\n  sys0 = SPEED\n")
        self.assertEqual(self.warnings(), [])

    def test_a_library_constant_is_left_alone(self):
        self.write("pages/lib/values.nx", "const LIMIT = 4\n")
        self.write("pages/page0.nx", 'include "lib/values.nx"\n')
        self.assertEqual(self.warnings(), [])

    def test_a_number_past_32_bits(self):
        # The build keeps its low 32 bits, and warns, as a C compiler does.
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 0x0100000005\n")
        self.write("program.nx", "int big=0x1FFFFFFFF\n" + self.text("program.nx"))
        self.assertEqual(self.warnings(), [("pages/page0.nx", 2, "number-past-32-bits"),
                                           ("program.nx", 1, "number-past-32-bits")])
        self.assertEqual([finding.message for finding in self.findings()],
                         ["0x0100000005 does not fit in 32 bits: its low 32 bits are kept, "
                          "0x00000005",
                          "0x1FFFFFFFF does not fit in 32 bits: its low 32 bits are kept, "
                          "0xFFFFFFFF"])

    def test_a_decimal_number_past_32_bits(self):
        # Its value changes, so it is warned of from 2147483648 on, unlike a
        # hexadecimal number. A minus sign is read: -2147483648 fits, and a
        # minus after an operand subtracts. printh's bytes are not numbers.
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 2147483648\n"
                                     "  sys0 = -2147483648\n  sys0 = 2-2147483648\n"
                                     "  printh 4294967296\n")
        self.write("program.nx", "int big=-4294967297\n" + self.text("program.nx"))
        self.assertEqual(self.warnings(), [("pages/page0.nx", 2, "number-past-32-bits"),
                                           ("pages/page0.nx", 4, "number-past-32-bits"),
                                           ("program.nx", 1, "number-past-32-bits")])
        self.assertEqual([finding.message for finding in self.findings()],
                         ["2147483648 does not fit in 32 bits: its low 32 bits are kept, "
                          "-2147483648",
                          "2147483648 does not fit in 32 bits: its low 32 bits are kept, "
                          "-2147483648",
                          "-4294967297 does not fit in 32 bits: its low 32 bits are kept, -1"])

    def test_an_unused_function(self):
        self.write("pages/page0.nx", "function used():\n  sys0 = 1\n\nfunction unused():\n"
                                     "  sys0 = 2\n\non page0.load:\n  used()\n")
        self.assertEqual(self.warnings(), [("pages/page0.nx", 4, "unused-function")])


class EditorLanguageWarningTest(FolderTestCase):
    language = "nextion"

    def test_left_to_right(self):
        self.write("pages/page0.nx", "on page0.load:\n  sys0=sys1+sys2*2\n  sys0=sys1*2+1\n")
        self.assertEqual(self.findings(), [Finding(
            "pages/page0.nx", 2, WARNING,
            "the Nextion Editor computes this from left to right, as sys0=(sys1+sys2)*2",
            "left-to-right")])

    def test_left_to_right_leaves_the_lines_comment_out(self):
        self.write("pages/page0.nx", "on page0.load:\n  sys0=sys1+sys2*2 // scaled\n")
        self.assertEqual(self.findings(), [Finding(
            "pages/page0.nx", 2, WARNING,
            "the Nextion Editor computes this from left to right, as sys0=(sys1+sys2)*2",
            "left-to-right")])

    def test_hex_written_0X_is_not_computed_otherwise(self):
        # A switch writes 0X10 as 0x10, which computes the same.
        self.write("pages/page0.nx", "on page0.load:\n  sys0=0X10\n  sys0=0X10+sys1*2\n")
        self.assertEqual(self.findings(), [Finding(
            "pages/page0.nx", 3, WARNING,
            "the Nextion Editor computes this from left to right, as sys0=(0x10+sys1)*2",
            "left-to-right")])

    def test_left_to_right_in_program_nx(self):
        self.write("program.nx", self.text("program.nx") + "sys0=sys1-sys2-1\nsys0=sys1-2*3\n")
        lines = self.text("program.nx").split("\n")
        self.assertEqual([(finding.line, finding.rule) for finding in self.findings()],
                         [(lines.index("sys0=sys1-2*3") + 1, "left-to-right")])


class EventNeverRunsTest(FolderTestCase):
    """An event its component's type lacks, which the build takes, and the
    Nextion Editor keeps, but whose code the screen never runs: the Nextion
    Editor's simulator never ran a page's `postinit`."""
    language = "nextion"

    def list_events(self, page: str, events: dict):
        """Gives the tables of `page` named in `events` those event lists."""
        def edit(tables: list):
            for table in tables:
                if table["name"] in events:
                    table["events"] = events[table["name"]]
        path = "pages/%s.page.toml" % page
        self.write(path, edited_page_file(self.text(path), edit))

    def test_a_page_event_the_type_lacks(self):
        self.list_events("page0", {"page0": ["load", "postinit"]})
        self.write("pages/page0.nx", "on page0.load:\n  sys0=1\n\non page0.postinit:\n  sys0=2\n")
        self.assertEqual(self.findings(), [Finding(
            "pages/page0.nx", 4, WARNING,
            "page0, of type page, has no postinit event, so the screen never runs this code; "
            "its events are load, loadend, down, up, and unload. The Nextion Editor's "
            "Postinitialize Event is loadend", "event-never-runs")])

    def test_a_components_event_the_type_lacks(self):
        self.list_events("second", {"title": ["down", "up", "timer"]})
        self.write("pages/second.nx", "on title.down:\n  sys0=1\n\non title.timer:\n  sys0=2\n")
        self.assertEqual([(finding.file, finding.line, finding.rule, finding.message)
                          for finding in self.findings()],
                         [("pages/second.nx", 4, "event-never-runs",
                           "title, of type text, has no timer event, so the screen never runs "
                           "this code; its events are down and up")])

    def test_a_type_that_is_no_plain_name(self):
        # As a page file being typed may hold: the build's error alone, not a crash.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\nname = "odd"\ntype = ["text"]\n')
        self.write("pages/page0.nx", "on odd.down:\n  sys0=1\n")
        self.assertEqual([finding.severity for finding in self.findings()], [ERROR])


class NxlangEventNeverRunsTest(EventNeverRunsTest):
    """The same in nxlang, where an event may be in a file the page includes."""
    language = "nxlang"

    def test_preinit(self):
        self.list_events("page0", {"page0": ["load", "preinit"]})
        self.write("pages/page0.nx", "on page0.preinit:\n  sys0 = 2\n")
        self.assertEqual([(finding.line, finding.rule) for finding in self.findings()],
                         [(1, "event-never-runs")])
        self.assertTrue(self.findings()[0].message.endswith(
            "The Nextion Editor's Preinitialize Event is load"), self.findings()[0].message)

    def test_a_function_beside_a_table_with_no_name(self):
        # As a table being typed may be: the build's error alone, no warning
        # taking the function for the nameless table's event.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml")
                   + '\n[[component]]\ntype = "text"\n')
        self.write("pages/page0.nx", "function helper():\n  sys0 = 1\n")
        self.assertEqual([finding.rule for finding in self.findings()
                          if finding.rule == "event-never-runs"], [])

    def test_in_a_file_two_pages_include(self):
        # Warned once, in the file holding it.
        for page in ("page0", "second"):
            self.list_events(page, {"title": ["down", "up", "timer"]})
            self.write("pages/%s.nx" % page, 'include "lib/events.nx"\n')
        self.write("pages/lib/events.nx", "on title.timer:\n  sys0 = 2\n")
        self.assertEqual([(finding.file, finding.line, finding.rule)
                          for finding in self.findings()],
                         [("pages/lib/events.nx", 1, "event-never-runs")])


class PageAtScreenSizeTest(FolderTestCase):
    """A page whose page file gives another place or size than its screen's,
    800 by 480 on the NX8048P050. The Nextion Editor 1.68.2 compiled such a
    page at its screen's place and size, so nxwright builds, simulates, and
    draws it so, and warns on the page file's line."""

    PATH = "pages/page0.page.toml"

    def setUp(self):
        super().setUp()
        self.built = 0

    def edit_page(self, **values):
        text = self.text(self.PATH)
        for key, value in values.items():
            text, count = re.subn(r"(?m)^%s = \d+$" % key, "%s = %d" % (key, value), text, count=1)
            self.assertEqual(count, 1, key)
        self.write(self.PATH, text)

    def built_place(self) -> dict:
        """Returns the built page's x, y, w, h, endx, and endy, from its dump."""
        self.built += 1
        dump = Path(self._folder.name) / ("dump%d" % self.built)
        export_dump(self.root, dump)
        text = next((dump / "pages").glob("*-page0.txt")).read_text(encoding="utf-8")
        page = text.split("\nobject 1 ")[0]
        return {key: int(value) for key, value in
                re.findall(r"(?m)^  (x|y|w|h|endx|endy) = (-?\d+)$", page)}

    def place_warnings(self) -> list:
        return [(finding.file, finding.line, finding.severity, finding.message)
                for finding in self.findings() if finding.rule == "page-place"]

    def test_the_build_takes_the_screens_place_and_size(self):
        self.edit_page(x=10, y=6, w=200, h=240)
        self.assertEqual(self.built_place(), {"x": 0, "y": 0, "w": 800, "h": 480,
                                              "endx": 799, "endy": 479})

    def test_a_page_at_the_screens_place_and_size_is_built_as_its_file_says(self):
        self.assertEqual(self.built_place(), {"x": 0, "y": 0, "w": 800, "h": 480,
                                              "endx": 799, "endy": 479})
        self.assertEqual(self.place_warnings(), [])

    def test_a_key_left_out_takes_the_screens_value(self):
        # Turned a quarter, the screen is 480 by 800.
        self.use_screen("NX8048P050", 90)
        self.write(self.PATH, re.sub(r"(?m)^[wh] = \d+\n", "", self.text(self.PATH), count=2))
        self.assertEqual(self.built_place(), {"x": 0, "y": 0, "w": 480, "h": 800,
                                              "endx": 479, "endy": 799})
        self.assertEqual(self.place_warnings(), [])

    def test_the_simulation_and_the_preview_take_it_too(self):
        self.edit_page(h=240)
        read = folder_reader(self.root)
        for components in (read_page_components(read, "page0")[1],
                           page_toml_components(read_page_toml(read, "page0"), "page0")):
            values = components[0].values
            self.assertEqual((values["x"], values["y"], values["w"], values["h"]),
                             (0, 0, 800, 480))

    def test_the_warning_on_each_line(self):
        self.edit_page(x=10, y=6, w=200, h=240)
        self.assertEqual(self.place_warnings(), [
            (self.PATH, line, WARNING,
             "page0's %s is %d, but the Nextion Editor makes every page fill its screen, "
             "800 by 480 at 0, 0, so the build uses %d" % (key, given, built))
            for line, key, given, built in ((4, "x", 10, 0), (5, "y", 6, 0), (6, "w", 200, 800),
                                            (7, "h", 240, 480))])

    def test_a_page_header_with_a_comment(self):
        self.write(self.PATH, self.text(self.PATH).replace("[page]", "[page]  # the first page", 1))
        self.edit_page(h=240)
        self.assertEqual([line for _, line, _, _ in self.place_warnings()], [7])

    def test_a_table_at_the_screens_place_and_size_is_kept_as_it_is(self):
        # Nothing of the table changes, so the page is built byte for byte as before.
        table = tomllib.loads(self.text(self.PATH))["page"]
        defaults = defaults_from_toml(self.text("defaults.toml"), "defaults.toml")
        self.assertEqual(page_table_at_screen(table, (800, 480), defaults), table)
        self.assertEqual(list(page_table_at_screen(table, (800, 480), defaults)), list(table))

    def test_a_value_that_is_no_number(self):
        # The build uses the screen's value in its place, so it is warned about.
        self.write(self.PATH, self.text(self.PATH).replace("h = 480", 'h = "tall"', 1))
        self.assertEqual(self.built_place()["h"], 480)
        self.assertEqual([line for _, line, _, _ in self.place_warnings()], [7])

    def test_without_a_screen(self):
        # Without the screen's settings, the page file's values are kept.
        self.write("app.toml", edited_app(self.text("app.toml"), lambda app: [
            app.pop(key, None) for key in DEVICE_KEYS]))
        self.edit_page(h=240)
        self.assertEqual(self.built_place()["h"], 240)
        self.assertEqual(self.place_warnings(), [])


class EditorLanguagePageAtScreenSizeTest(PageAtScreenSizeTest):
    language = "nextion"


class TextCutTest(FolderTestCase):
    """Where nxlang puts a text that contains a component's text, or one of
    nxlang's variables with more than 255 bytes of room, into a variable
    whose room is less than its parts can take, the checks warn that the text
    may be cut (rule text-cut). Page0 has texts big, of txt_maxl 1000, mid1
    and mid2, of 200, and full, of 255. The second page has a big of its own."""

    def setUp(self):
        super().setUp()
        page0 = self.root / "pages" / "page0.page.toml"
        for name, limit in (("big", 1000), ("mid1", 200), ("mid2", 200), ("full", 255)):
            add_component(page0, name, "x", limit)
        add_component(self.root / "pages" / "second.page.toml", "big", "x", 1000)

    def cuts(self, code: str) -> list:
        """Returns the text-cut warnings of page0's code `code`."""
        self.write("pages/page0.nx", code)
        return [finding for finding in self.findings() if finding.rule == "text-cut"]

    def test_a_join_in_a_condition(self):
        self.assertEqual(self.cuts('on page0.load:\n  if (title.txt == "a" + big.txt) {\n'
                                   '    sys0 = 1\n  }\n'), [Finding(
            "pages/page0.nx", 2, WARNING,
            "this text can take 1001 bytes, as big.txt keeps up to 1000, but nxlang keeps it "
            "in a variable of 255 bytes here, so a longer text is cut. To keep it whole, put it "
            "in a variable component whose txt_maxl is at least 1001", "text-cut")])

    def test_a_local_given_a_components_text(self):
        self.assertEqual([finding.line for finding in self.cuts(
            "on page0.load:\n  var s = big.txt\n  title.txt = s\n")], [2])

    def test_two_components_together(self):
        self.assertEqual([finding.line for finding in self.cuts(
            "on page0.load:\n  if (title.txt == mid1.txt + mid2.txt) {\n    sys0 = 1\n  }\n")],
            [2])

    def test_a_component_on_another_page(self):
        self.assertEqual([finding.line for finding in self.cuts(
            'on page0.load:\n  if (title.txt == "a" + second.big.txt) {\n    sys0 = 1\n  }\n')],
            [2])

    def test_none_where_the_room_is_enough(self):
        # A component of 255 alone fits a variable of 255.
        self.assertEqual(self.cuts("on page0.load:\n  var s = full.txt\n  title.txt = s\n"), [])
        # A later statement gives the temporary room enough for both.
        self.assertEqual(self.cuts(
            'on page0.load:\n  if (title.txt == "a" + big.txt) {\n    sys0 = 1\n  }\n'
            '  if (title.txt == "%s" + title.txt) {\n    sys0 = 2\n  }\n' % ("b" * 1100)), [])

    def test_a_loop_condition_warns_once(self):
        # A while loop's condition is computed again at the end of each pass.
        self.assertEqual([finding.line for finding in self.cuts(
            'on page0.load:\n  while (title.txt == "a" + big.txt) {\n    sys0 = 1\n  }\n')],
            [2])

    def test_an_addition_counts_the_parts_it_adds(self):
        # The text the local keeps already is not counted: short texts added
        # in steps stay at 255 bytes, as the docs say.
        self.assertEqual([finding.line for finding in self.cuts(
            'on page0.load:\n  var s = "a"\n  s += mid1.txt\n  s += big.txt\n'
            '  title.txt = s\n')], [4])

    def test_a_copy_of_a_long_parameter(self):
        # The function is compiled before its caller gives words its room.
        self.assertEqual(self.cuts(
            'function show(words: text):\n  var copy = words\n  title.txt = copy\n\n'
            'on page0.load:\n  show("%s")\n' % ("a" * 400)), [Finding(
            "pages/page0.nx", 2, WARNING,
            "this text can take 400 bytes, as words keeps up to 400, but nxlang keeps it "
            "in a variable of 255 bytes here, so a longer text is cut. To keep it whole, put it "
            "in a variable component whose txt_maxl is at least 400", "text-cut")])

    def test_none_for_a_short_local_sharing_a_long_ones_variable(self):
        # The two events share a variable, which the page's load gives 400
        # bytes. The copy in the other copies one letter.
        load = 'on page0.load:\n  var msg = "%s"\n  title.txt = msg\n' % ("a" * 400)
        down = 'on title.down:\n  var s = "x"\n  var t = s\n  title.txt = t\n'
        for code in (load + "\n" + down, down + "\n" + load):
            self.assertEqual(self.cuts(code), [])

    def test_none_for_a_join_of_two_short_locals(self):
        self.assertEqual(self.cuts('on page0.load:\n  var a = "x"\n  var b = "y"\n'
                                   '  var c = a + b\n  title.txt = c\n'), [])

    def test_none_for_a_long_local_copied_in_the_same_event(self):
        self.assertEqual(self.cuts('on page0.load:\n  var s = "%s"\n  var t = s\n'
                                   '  title.txt = t\n' % ("a" * 400)), [])

    def test_none_in_a_function_the_page_never_calls(self):
        self.assertEqual(self.cuts("function unused():\n  var s = big.txt\n  title.txt = s\n\n"
                                   "on page0.load:\n  sys0 = 1\n"), [])

    def test_the_page_still_builds(self):
        self.write("pages/page0.nx", "on page0.load:\n  var s = big.txt\n  title.txt = s\n")
        self.assertEqual([finding for finding in self.findings() if finding.severity == ERROR],
                         [])


if __name__ == "__main__":
    unittest.main()
