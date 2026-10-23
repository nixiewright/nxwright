"""nxwright check: the build's errors with their places, the warnings the
build does not give, and each page's measures against its limits."""
import contextlib
import io
from pathlib import Path
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
from nxwright.source.page_source import page_file_text
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_reader, new_source_folder
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
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832K035")))
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
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(screen="NX4832F035")))
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


if __name__ == "__main__":
    unittest.main()
