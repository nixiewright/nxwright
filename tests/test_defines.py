"""Defines: app.toml's [defines] table, nxlang code using its names as
constants, --define on build and compile, and placeholders in app.toml and
the page files (nxwright/source/defines.py)."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.container import HmiContainer
from nxwright.language_server.page_editing import properties
from nxwright.source.defines import overriding_defines
from nxwright.source.folder_index import FolderIndex
from nxwright.source.page_edits import attribute_edits
from nxwright.source.project_files import extract
from nxwright.source.source_folder import (folder_reader, parse_app, read_app,
                                           read_page_components)
from nxwright.testing import SourceFolderRunner
from nxwright.testing.simulation import Simulation
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware

DEFINES = '\n[defines]\nLIMIT = 30\nTITLE = "Living room"\n'

# Code of page0 using the defines.
CODE = """on page0.load:
  sys0 = LIMIT
  print TITLE
"""


def run(arguments: list) -> tuple:
    """Runs the nxwright command, and returns its exit code and what it
    printed to standard error."""
    errors = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(errors):
        code = main(arguments)
    return code, errors.getvalue()


def page_bytes(project: Path) -> bytes:
    """Returns the bytes of page0's block in the project file `project`."""
    return HmiContainer.from_file(project).blocks["0.pa"]


class DefinesTestCase(unittest.TestCase):
    """A new folder in nxlang whose app.toml declares LIMIT and TITLE, and
    whose page0 uses them."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        self.assertEqual(run(["new", str(self.source), "--screen", "NX4832T035", "--language",
                              "nxlang", "--name", "app"])[0], 0)
        self.app = self.source / "app.toml"
        self.app.write_text(self.app.read_text(encoding="utf-8") + DEFINES, encoding="utf-8",
                            newline="\n")
        (self.source / "pages" / "page0.nx").write_text(CODE, encoding="utf-8", newline="\n")
        self.project = self.folder / "app.HMI"

    def tearDown(self):
        self._folder.cleanup()

    def build(self, *options: str) -> tuple:
        """Builds the folder, and returns the exit code and standard error."""
        return run(["build", "--overwrite", "--no-backup", str(self.source), str(self.project),
                    *options])

    def built_page(self, *options: str) -> bytes:
        """Builds the folder, and returns page0's block."""
        code, errors = self.build(*options)
        self.assertEqual((code, errors), (0, ""))
        return page_bytes(self.project)


class BuildTest(DefinesTestCase):

    def test_the_code_takes_the_defaults(self):
        page = self.built_page()
        self.assertIn(b"sys0=30", page)
        self.assertIn(b'print "Living room"', page)

    def test_define_gives_new_values(self):
        page = self.built_page("--define", "LIMIT=-5", "--define", "TITLE=Lab")
        self.assertIn(b"sys0=-5", page)
        self.assertIn(b'print "Lab"', page)

    def test_a_text_is_quoted_as_code_writes_it(self):
        page = self.built_page("--define", 'TITLE=say "hi" \\')
        self.assertIn(b'print "say \\"hi\\" \\\\"', page)
        self.assertIn(b'print ""', self.built_page("--define", "TITLE="))

    def test_a_text_with_a_line_break_is_refused(self):
        code, errors = self.build("--define", "TITLE=two\nlines")
        self.assertEqual(code, 1)
        self.assertIn("app.toml the define TITLE of [defines]: a quoted text cannot contain a "
                      "line break", errors)

    def test_the_values_last_only_for_the_command(self):
        self.built_page("--define", "LIMIT=40")
        self.assertIn(b"sys0=30", self.built_page())
        self.assertEqual(read_app(self.source)["defines"], {"LIMIT": 30, "TITLE": "Living room"})

    def test_define_refuses_what_the_table_does_not_allow(self):
        for options, message in [
                (["--define", "SPEED=3"], "--define SPEED: app.toml's [defines] does not "
                                          "declare SPEED (it declares LIMIT, TITLE)"),
                (["--define", "LIMIT=3", "--define", "LIMIT=4"], "--define LIMIT: given twice"),
                (["--define", "LIMIT"], "--define LIMIT: give a value, as in --define "
                                        "LIMIT=VALUE"),
                (["--define", "LIMIT=3.5"], "--define LIMIT=3.5: LIMIT is a number, so its "
                                            "value must be a whole number, such as 30 or -5")]:
            with self.subTest(options=options):
                code, errors = self.build(*options)
                self.assertEqual(code, 1)
                self.assertIn(message, errors)

    def test_a_define_cannot_share_a_constants_name(self):
        program = self.source / "program.nx"
        program.write_text("const LIMIT = 3\n" + program.read_text(encoding="utf-8"),
                           encoding="utf-8", newline="\n")
        code, errors = self.build()
        self.assertEqual(code, 1)
        self.assertIn("app.toml the define LIMIT of [defines]: LIMIT is already a constant",
                      errors)

    def test_a_number_past_32_bits_keeps_its_low_32_bits_as_a_constant_does(self):
        self.app.write_text(self.app.read_text(encoding="utf-8").replace(
            "LIMIT = 30", "LIMIT = 4294967295"), encoding="utf-8", newline="\n")
        self.assertIn(b"sys0=-1", self.built_page())

    def test_a_new_page_keeps_the_table(self):
        self.assertEqual(run(["new-page", str(self.source), "second"])[0], 0)
        text = self.app.read_text(encoding="utf-8")
        self.assertTrue(text.endswith('[defines]\nLIMIT = 30\nTITLE = "Living room"\n'), text)


class CompileTest(DefinesTestCase):
    """compile, with stand-in firmware that the tests make."""

    def compile(self, source: Path, *options: str) -> tuple:
        firmware = self.folder / "firmware.tft"
        firmware.write_bytes(made_tft("T"))
        with stand_in_firmware(self.folder / "cache"):
            return run(["compile", str(source), str(self.folder / "app.tft"), "--firmware",
                        str(firmware), "--overwrite", "--no-backup", *options])

    def test_define_reaches_the_build(self):
        self.assertEqual(self.compile(self.source, "--project-file", str(self.project),
                                      "--define", "LIMIT=40"), (0, ""))
        self.assertIn(b"sys0=40", page_bytes(self.project))

    def test_define_is_refused_with_a_project_file(self):
        self.built_page()
        code, errors = self.compile(self.project, "--define", "LIMIT=40")
        self.assertEqual(code, 1)
        self.assertIn("--define changes the defines of a source folder, and %s is a "
                      "project file, which has none" % self.project, errors)


class TableTest(unittest.TestCase):
    """The [defines] table, as parse_app reads it."""

    APP = ('format = 1\nlanguage = "nxlang"\nscreen = "NX4832T035"\nrotation = 0\n'
           'encoding = "iso-8859-1"\npages = ["page0"]\npictures = []\nfonts = []\n')

    def defines(self, table: str) -> dict:
        return parse_app(self.APP + "\n[defines]\n" + table)["defines"]

    def test_whole_numbers_and_texts(self):
        self.assertEqual(self.defines('A = 1\nB = -2\nC = ""\n_d1 = "x"\n'),
                         {"A": 1, "B": -2, "C": "", "_d1": "x"})
        self.assertEqual(parse_app(self.APP)["defines"], {})

    def test_other_values_and_names_are_refused(self):
        for table, message in [
                ("A = true\n", "app.toml: the define A must be a whole number or a text"),
                ("A = 1.5\n", "app.toml: the define A must be a whole number or a text"),
                ("A = [1]\n", "app.toml: the define A must be a whole number or a text"),
                ('"1A" = 1\n', "app.toml: invalid define name: 1A. Use letters, digits, and "
                               "_, and do not start with a digit"),
                ('"A-B" = 1\n', "app.toml: invalid define name: A-B. Use letters, digits, "
                                "and _, and do not start with a digit")]:
            with self.subTest(table=table), self.assertRaises(NxwrightError) as raised:
                self.defines(table)
            self.assertEqual(str(raised.exception), message)

    def test_a_new_value_applies_within_the_command_only(self):
        with overriding_defines({"A": "7", "B": "new"}):
            self.assertEqual(self.defines('A = 1\nB = "old"\n'), {"A": 7, "B": "new"})
        self.assertEqual(self.defines('A = 1\nB = "old"\n'), {"A": 1, "B": "old"})




# A text component of page0 whose x, bco, and vscope are placeholders.
COMPONENT = """
[[component]]
name = "t0"
type = "text"
x = "%LEFT%"
y = 0
w = 80
h = 30
bco = "%BCOLOR%"
vscope = "%SCOPE%"
"""


class PlaceholderTest(DefinesTestCase):
    """The folder with BCOLOR, LEFT, ROTATION, and SCOPE defined too,
    app.toml's rotation and page0's component t0 using them."""

    def setUp(self):
        super().setUp()
        self.edit("app.toml", ("rotation = 0", 'rotation = "%ROTATION%"'))
        self.app.write_text(self.app.read_text(encoding="utf-8")
                            + "BCOLOR = 1024\nLEFT = 10\nROTATION = 0\nSCOPE = 1\n",
                            encoding="utf-8", newline="\n")
        page = self.source / "pages" / "page0.page.toml"
        page.write_text(page.read_text(encoding="utf-8") + COMPONENT, encoding="utf-8",
                        newline="\n")

    def edit(self, path: str, *replaced):
        """Replaces, in the folder's file `path`, each (old, new) once."""
        file = self.source / path
        text = file.read_text(encoding="utf-8")
        for old, new in replaced:
            self.assertIn(old, text)
            text = text.replace(old, new, 1)
        file.write_text(text, encoding="utf-8", newline="\n")

    def extracted(self, *options: str) -> Path:
        """Builds the folder with `options`, and returns the folder extracted
        from the project file."""
        self.assertEqual(self.build(*options), (0, ""))
        folder = self.folder / ("extracted%d" % len(list(self.folder.glob("extracted*"))))
        extract(self.project, folder)
        return folder

    def test_placeholders_take_the_defaults_and_the_new_values(self):
        folder = self.extracted()
        page = (folder / "pages" / "page0.page.toml").read_text(encoding="utf-8")
        self.assertIn('bco = "#008200"\n', page)
        self.assertIn("x = 10\n", page)
        self.assertIn("vscope = 1\n", page)
        self.assertIn("rotation = 0\n", (folder / "app.toml").read_text(encoding="utf-8"))
        folder = self.extracted("--define", "BCOLOR=2048", "--define", "ROTATION=180")
        self.assertIn('bco = "#080000"\n',
                      (folder / "pages" / "page0.page.toml").read_text(encoding="utf-8"))
        self.assertIn("rotation = 180\n", (folder / "app.toml").read_text(encoding="utf-8"))

    def test_a_placeholder_must_name_a_define(self):
        self.edit("pages/page0.page.toml", ('bco = "%BCOLOR%"', 'bco = "%BCOLOUR%"'))
        code, errors = self.build()
        self.assertEqual(code, 1)
        self.assertIn("pages/page0.page.toml, t0: bco is %BCOLOUR%, and app.toml's [defines] "
                      "does not declare BCOLOUR", errors)

    def test_without_defines_a_placeholder_is_plain_text(self):
        self.app.write_text(self.app.read_text(encoding="utf-8").split("\n[defines]")[0]
                            .replace('"%ROTATION%"', "0") + "\n", encoding="utf-8",
                            newline="\n")
        (self.source / "pages" / "page0.nx").write_text("", encoding="utf-8")
        self.edit("pages/page0.page.toml", ('x = "%LEFT%"', "x = 10"),
                  ('bco = "%BCOLOR%"', 'txt = "%BCOLOR%"\ntxt_maxl = 10'),
                  ('vscope = "%SCOPE%"', "vscope = 0"))
        page = (self.extracted() / "pages" / "page0.page.toml").read_text(encoding="utf-8")
        self.assertIn('txt = "%BCOLOR%"\n', page)

    def test_keys_that_say_what_a_table_is_cannot_be_placeholders(self):
        for path, old, new, message in [
                ("pages/page0.page.toml", 'name = "t0"', 'name = "%TITLE%"',
                 "name is %TITLE%, but name cannot take a define's value"),
                ("app.toml", "format = 1", 'format = "%LIMIT%"',
                 "app.toml: format is %LIMIT%, but format cannot take a define's value")]:
            with self.subTest(key=old):
                self.edit(path, (old, new))
                code, errors = self.build()
                self.assertEqual(code, 1)
                self.assertIn(message, errors)
                self.edit(path, (new, old))

    def test_a_value_is_checked_as_a_written_one(self):
        self.edit("pages/page0.page.toml", ('bco = "%BCOLOR%"', 'bco = "%TITLE%"'))
        code, errors = self.build()
        self.assertEqual(code, 1)
        self.edit("pages/page0.page.toml", ('bco = "%TITLE%"', 'bco = "Living room"'))
        self.assertEqual((code, errors), self.build())

    def test_every_tool_reads_the_defaults(self):
        read = folder_reader(self.source)
        _, components = read_page_components(read, "page0")
        t0 = [component for component in components if component.name == "t0"][0]
        self.assertEqual((t0.values["bco"], t0.values["x"]), (1024, 10))
        self.assertEqual(run(["check", str(self.source)]), (0, ""))
        Simulation(self.source)
        self.assertEqual(SourceFolderRunner(self.source).run_code(
            "sys0 = LIMIT", {"sys0": 0})["sys0"], 30)

    def test_the_attributes_section_shows_the_placeholder(self):
        index = FolderIndex(self.source, folder_reader(self.source))
        shown = {entry["name"]: entry for entry in properties(
            index, folder_reader(self.source), "page0", "t0")["attributes"]}
        self.assertEqual((shown["bco"]["value"], shown["bco"]["treatment"]),
                         ("%BCOLOR%", "value-only"))
        self.assertEqual(shown["y"]["value"], 0)

    def test_an_edit_replaces_the_placeholder(self):
        index = FolderIndex(self.source, folder_reader(self.source))
        edits = attribute_edits(index, folder_reader(self.source), "page0", "t0", {"x": 15})
        self.assertEqual([edit["newText"] for edit in edits], ["x = 15\n"])

    def test_remove_sees_a_resource_used_through_a_placeholder(self):
        fonts = self.source / "fonts"
        (fonts / "Other.zi").write_bytes((fonts / "NotoSans24.zi").read_bytes())
        self.edit("app.toml", ('    "NotoSans24",\n]', '    "NotoSans24",\n    "Other",\n]'))
        self.app.write_text(self.app.read_text(encoding="utf-8") + 'FONT = "Other"\n',
                            encoding="utf-8", newline="\n")
        self.edit("pages/page0.page.toml",
                  ('vscope = "%SCOPE%"', 'vscope = "%SCOPE%"\nfont = "%FONT%"'))
        self.assertEqual(run(["remove", str(self.source), "font", "Other", "--checked"])[0], 1)
        self.edit("app.toml", ('FONT = "Other"', 'FONT = "NotoSans24"'))
        self.assertEqual(run(["remove", str(self.source), "font", "Other", "--checked"])[0], 0)
        self.assertIn('rotation = "%ROTATION%"\n', self.app.read_text(encoding="utf-8"))

    def test_commands_that_rewrite_app_toml_keep_its_placeholders(self):
        self.assertEqual(run(["new-page", str(self.source), "second"])[0], 0)
        self.assertIn('rotation = "%ROTATION%"\n', self.app.read_text(encoding="utf-8"))
        self.assertEqual(run(["device", str(self.source), "--rotation", "180"])[0], 0)
        self.assertIn("rotation = 180\n", self.app.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
