"""Tests of the build's check of each page's memory, as the Editor's compile
counts it (nxwright/project/page_memory.py, on the table the probe measured
on the Editor 3.1.73): the build refuses a page the compile would refuse,
`nxwright check` reports it at the page file, and `nxwright build` prints
each page's memory."""
import contextlib
import io
from pathlib import Path
import re
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.source.folder_check import check_folder
from nxwright.source.lint import ERROR, WARNING, Finding
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_reader, new_source_folder
from nxwright.source.keyboard_adding import add_keyboard
from tests.test_folder_check import edited_app, edited_page_file

OVERFLOW = ("its memory, %d + %d = %d bytes, passes the %s's %d, and the Nextion Editor's compile "
            "refuses it (\"Memory overflow\")")


class MemoryTestCase(unittest.TestCase):
    """A source folder started as `nxwright new` starts one, on a screen of
    `model`, in `language`: its page0 holds no component."""
    model, language = "NX4832T035", "nextion"

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name) / "app"
        new_source_folder(self.root, DeviceSettings(model_named(self.model), 0, "iso-8859-1"),
                          self.language)

    def tearDown(self):
        self._folder.cleanup()

    def write(self, path: str, text: str):
        (self.root / path).write_text(text, encoding="utf-8", newline="\n")

    def add(self, page: str, kind: str, name: str, **values):
        """Adds a component to a page file, placed at the page's corner."""
        def added(tables: list):
            tables.append({"name": name, "type": kind, "x": 0, "y": 0, "w": 100, "h": 30,
                           **values})
        path = self.root / "pages" / ("%s.page.toml" % page)
        path.write_text(edited_page_file(path.read_text(encoding="utf-8"), added),
                        encoding="utf-8", newline="\n")

    def add_page(self, page: str):
        """Adds a page with no component, after page0."""
        self.write("pages/%s.page.toml" % page,
                   (self.root / "pages" / "page0.page.toml").read_text(encoding="utf-8")
                   .replace('name = "page0"', 'name = "%s"' % page))
        self.write("pages/%s.nx" % page, "")
        app = self.root / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                  lambda data: data["pages"].append(page)),
                       encoding="utf-8", newline="\n")

    def built(self):
        """Builds the folder; returns what build returns, its memory."""
        return build(self.root, Path(self._folder.name) / "built.HMI")

    def findings(self) -> list:
        return check_folder(folder_reader(self.root),
                            lambda path: (self.root / path).is_file()).findings()

    def run_build(self) -> tuple:
        """Runs `nxwright build`; returns its exit code, output, and errors."""
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(["build", str(self.root), str(Path(self._folder.name) / "built.HMI"),
                         "--overwrite"])
        return code, output.getvalue(), errors.getvalue()


class BasicScreenTest(MemoryTestCase):
    """An NX4832T035, of 3,584 bytes."""

    def test_the_overflow_seen(self):
        # Four texts of txt_maxl 1,000: the Editor's compile said
        # "Error:Page:p26 Error! Memory overflow:16+4072=4088".
        for number in range(4):
            self.add("page0", "text", "t%d" % number, txt_maxl=1000)
        message = OVERFLOW % (16, 4072, 4088, "NX4832T035", 3584)
        with self.assertRaisesRegex(NxwrightError, "^page0.page.toml: " + re.escape(message)):
            self.built()
        self.assertEqual(self.findings(), [Finding("pages/page0.page.toml", 0, ERROR,
                                                   "page0.page.toml: " + message)])

    def test_a_qr_codes_temporary_need(self):
        # The page leaves 3,336 of the screen's memory; a QR code of txt_maxl
        # 192 needs 3,382: "temporary use of QR code(-46)".
        self.add("page0", "qr-code", "q0", txt_maxl=192)
        with self.assertRaisesRegex(NxwrightError, re.escape(
                "page0.page.toml: q0 needs 3382 bytes of temporary memory, where the page leaves "
                "3336 of the NX4832T035's 3584: 46 missing")):
            self.built()

    def test_just_enough_for_a_qr_codes_need(self):
        # Its need, 2,823 bytes, and a text leaving 2,824; then, 4 bytes
        # longer, 2,820.
        self.add("page0", "qr-code", "q0", txt_maxl=154)
        self.add("page0", "text", "t0", txt_maxl=542)
        self.assertEqual(self.built().totals, {"page0": 16 + 744})
        path = self.root / "pages" / "page0.page.toml"
        path.write_text(edited_page_file(path.read_text(encoding="utf-8"),
                                         lambda tables: tables[2].update(txt_maxl=546)),
                        encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, "where the page leaves 2820 of the "
                                                   "NX4832T035's 3584: 3 missing"):
            self.built()

    def test_a_text_bound_to_the_keypad(self):
        # A keyboard binds only a component of global scope, which keeps
        # nothing on its page here. Global memory: 4 bytes, three ints of 4,
        # the text's 20, and the keypad page's 8.
        add_keyboard(self.root, "keypad")
        self.add("page0", "text", "t0", vscope=1, key=2)
        memory = self.built()
        self.assertEqual((memory.unmeasured, memory.totals),
                         (None, {"page0": 44 + 20, "keybdB": 44 + 752}))


class GeneratedGlobalsTest(MemoryTestCase):
    """An NX4832T035 folder in nxlang, whose locals are each an `int` of
    program.s, 4 bytes of global memory."""
    language = "nxlang"

    def test_counted_from_program_s_as_built(self):
        # sys0 to sys2 and 900 locals: 4 bytes and 903 ints of 4.
        self.write("pages/page0.page.toml", edited_page_file(
            (self.root / "pages" / "page0.page.toml").read_text(encoding="utf-8"),
            lambda tables: tables[0].update(events=["load"])))
        self.write("pages/page0.nx", "on page0.load:\n" + "".join(
            "  var v%d = sys0 + %d\n  sys1 = v%d\n" % (number, number, number)
            for number in range(900)))
        with self.assertRaisesRegex(NxwrightError, re.escape(
                OVERFLOW % (4 + 4 * 903, 20, 3636, "NX4832T035", 3584))):
            self.built()


class IntelligentScreenTest(MemoryTestCase):
    """An NX8048P050, of 524,288 bytes."""
    model = "NX8048P050"

    def test_the_overflow_seen_builds_here(self):
        # A page of 76 bytes and four texts of 88 and txt_maxl 1,000 plus 1,
        # rounded up to 4; and global memory of 4 and three ints.
        for number in range(4):
            self.add("page0", "text", "t%d" % number, txt_maxl=1000)
        output = Path(self._folder.name) / "built.HMI"
        self.assertEqual(self.run_build(), (0, "page0: %d of 524288 bytes\nWrote %s\n"
                                            % (16 + 76 + 4 * 1092, output), ""))

    def test_a_global_component_counts_in_every_page(self):
        # A text of global scope keeps 4 bytes on its page, and 96 in global memory.
        self.add_page("second")
        self.add("page0", "text", "t0", vscope=1)
        self.assertEqual(self.built().totals, {"page0": 16 + 96 + 80, "second": 16 + 96 + 76})

    def test_what_the_table_did_not_measure(self):
        # A sliding text's path, whose use is not known, was measured empty
        # alone: the folder builds, counted without it, and the build says so.
        self.add("page0", "sliding-text", "st0", path="x")
        warning = ("memory counted without page0.st0, as the memory of a sliding-text whose "
                   "path is not '' was not measured")
        self.assertEqual(self.built().warning, warning)
        output = Path(self._folder.name) / "built.HMI"
        self.assertEqual(self.run_build(), (0, "page0: at least %d of 524288 bytes\nWrote %s\n"
                                            % (16 + 76, output),
                                            "nxwright build: warning: %s\n" % warning))
        self.assertEqual(self.findings(), [Finding("pages/page0.page.toml", 0, WARNING,
                                                   warning, "memory-not-checked")])

    def test_refused_around_what_the_table_did_not_measure(self):
        # Nine texts of 88 and txt_maxl 60,000 plus 1, rounded up to 4, pass
        # the screen's memory without the sliding text the table did not
        # measure.
        self.add("page0", "sliding-text", "st0", path="x")
        for number in range(9):
            self.add("page0", "text", "t%d" % number, txt_maxl=60000)
        message = ("page0.page.toml: its memory, at least 16 + 540904 = 540920 bytes, passes the "
                   "NX8048P050's 524288, and the Nextion Editor's compile refuses it (\"Memory "
                   "overflow\")")
        with self.assertRaisesRegex(NxwrightError, "^" + re.escape(message)):
            self.built()
        warning = ("memory counted without page0.st0, as the memory of a sliding-text whose "
                   "path is not '' was not measured")
        # The errors first, as check_folder gives them.
        self.assertEqual(self.findings(), [
            Finding("pages/page0.page.toml", 0, ERROR, message),
            Finding("pages/page0.page.toml", 0, WARNING, warning, "memory-not-checked")])


if __name__ == "__main__":
    unittest.main()
