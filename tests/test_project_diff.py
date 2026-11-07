"""nxwright diff: what differs between a source folder and a project file, or two
project files (source/project_diff.py)."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.container import HmiContainer
from nxwright.source.project_diff import diff_projects
from nxwright.source.project_files import build
from nxwright.source.source_folder import add_page
from tests.test_container import build_project
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase

THERMOSTAT = Path(__file__).resolve().parents[1] / "examples" / "thermostat"


class DiffTest(SourceFolderTestCase):
    """The small project's source folder, and the project file nxwright builds from it."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", 'events = []', 'events = ["down"]')
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=1\n",
                                                         encoding="utf-8", newline="\n")
        (self.source / "program.nx").write_text("int sys0=0\npage 0\n", encoding="utf-8",
                                                newline="\n")
        self.built = self.folder / "built.HMI"
        build(self.source, self.built, lock_pages=True)

    def diff(self, first: Path, second: Path, **options) -> list:
        """Returns the lines of the diff, and checks that it gave no warning."""
        lines, warnings = diff_projects(first, second, **options)
        self.assertEqual(warnings, [])
        return lines

    def test_a_folder_and_its_own_project_do_not_differ(self):
        self.assertEqual(self.diff(self.source, self.built), [])

    def test_an_nxlang_folder_and_its_own_project_do_not_differ(self):
        self.assertEqual(self.diff(THERMOSTAT / "app", THERMOSTAT / "thermostat.HMI"), [])

    def test_an_edited_event(self):
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=2\n",
                                                         encoding="utf-8", newline="\n")
        lines = self.diff(self.source, self.built)
        source, built = str(self.source), str(self.built)
        self.assertIn("--- %s/pages/first.nx" % source, lines)
        self.assertIn("+++ %s/pages/first.nx" % built, lines)
        self.assertIn("-  sys0=2", lines)
        self.assertIn("+  sys0=1", lines)

    def test_the_first_line_says_how_the_sides_are_shown(self):
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=2\n",
                                                         encoding="utf-8", newline="\n")
        self.assertIn("as nxwright extract writes them", self.diff(self.source, self.built)[0])

    def test_an_added_page(self):
        name = add_page(self.source)
        lines = self.diff(self.source, self.built)
        self.assertIn("--- %s/pages/%s.page.toml" % (self.source, name), lines)

    def test_a_changed_picture(self):
        pictures = self.source / "pictures"
        (pictures / "picture-0000.png").write_bytes((pictures / "picture-0001.png").read_bytes())
        lines = self.diff(self.source, self.built)
        self.assertIn("Binary files %s/pictures/picture-0000.png and "
                      "%s/pictures/picture-0000.png differ" % (self.source, self.built), lines)

    def test_a_lock_is_a_difference_and_no_lock_hides_it(self):
        unlocked = self.folder / "unlocked.HMI"
        build(self.source, unlocked)
        self.assertIn("+++ %s/pages/first.page.toml" % unlocked, self.diff(self.source, unlocked))
        self.assertEqual(self.diff(self.source, unlocked, lock_pages=False), [])

    def test_two_project_files(self):
        other = self.folder / "other.HMI"
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=2\n",
                                                         encoding="utf-8", newline="\n")
        build(self.source, other, lock_pages=True)
        lines = self.diff(self.built, other)
        self.assertIn("-  sys0=1", lines)
        self.assertIn("+  sys0=2", lines)

    def test_content_nxwright_does_not_know_gives_a_warning_and_a_diff(self):
        container = HmiContainer.from_file(self.built)
        blocks = dict(container.blocks)
        blocks["2.xb"] = b"?"
        unknown = self.folder / "unknown.HMI"
        unknown.write_bytes(build_project([(block, data, 0) for block, data in blocks.items()]))
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=2\n",
                                                         encoding="utf-8", newline="\n")
        lines, warnings = diff_projects(self.source, unknown)
        self.assertTrue(warnings)
        self.assertTrue(all(warning.startswith(str(unknown)) for warning in warnings), warnings)
        self.assertIn("+  sys0=1", lines)

    def test_a_file_differing_only_in_its_last_line_end_is_reported(self):
        from nxwright.source.project_diff import _folder_diff
        first, second = self.folder / "first", self.folder / "second"
        for folder, text in ((first, "a\n"), (second, "a")):
            folder.mkdir()
            (folder / "program.nx").write_text(text, encoding="utf-8", newline="\n")
        self.assertEqual(_folder_diff(first, second, "one", "two"),
                         ["Files one/program.nx and two/program.nx differ"])

    def test_the_sides_stay_as_they_were(self):
        before = {path: path.read_bytes() for path in self.folder.rglob("*") if path.is_file()}
        diff_projects(self.source, self.built)
        self.assertEqual({path: path.read_bytes() for path in self.folder.rglob("*")
                          if path.is_file()}, before)

    def test_a_path_that_is_neither_is_refused(self):
        other = self.folder / "notes.txt"
        other.write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "neither a source folder nor a project file"):
            diff_projects(self.source, other)

    def run_command(self, *arguments) -> tuple:
        out, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(errors):
            code = main(["diff"] + [str(argument) for argument in arguments])
        return code, out.getvalue(), errors.getvalue()

    def test_the_command_exits_with_0_when_the_two_differ(self):
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0=2\n",
                                                         encoding="utf-8", newline="\n")
        code, out, _ = self.run_command(self.source, self.built)
        self.assertEqual(code, 0)
        self.assertIn("+  sys0=1", out)

    def test_the_command_says_when_there_is_no_difference(self):
        code, out, _ = self.run_command(self.source, self.built)
        self.assertEqual(code, 0)
        self.assertIn("No differences", out)

    def test_the_command_builds_without_locks_when_told(self):
        unlocked = self.folder / "unlocked.HMI"
        build(self.source, unlocked)
        code, out, _ = self.run_command(self.source, unlocked, "--no-lock")
        self.assertEqual(code, 0)
        self.assertIn("No differences", out)


if __name__ == "__main__":
    unittest.main()
