"""Renaming a page: `nxwright rename <folder> page`, and the edits the
language server's rename makes for one (source/page_renaming.py)."""
import contextlib
import io
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.source.folder_check import check_folder
from nxwright.source.page_renaming import rename_page
from nxwright.source.page_source import page_nx_path, page_toml_path
from nxwright.source.source_folder import folder_reader

DEMO = Path(__file__).resolve().parent.parent / "examples" / "thermostat" / "app"


class PageRenamingTest(unittest.TestCase):
    """Works on a copy of the demo. The demo's shared file pages/lib/frame.nx
    shows the page settings with `page settings`."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / "app"
        shutil.copytree(DEMO, self.source)

    def files(self) -> dict:
        return {str(path.relative_to(self.source)): path.read_bytes()
                for path in self.source.rglob("*") if path.is_file()}

    def text(self, path: str) -> str:
        return (self.source / path).read_text(encoding="utf-8")

    def pages(self) -> list:
        return tomllib.loads(self.text("app.toml"))["pages"]

    def builds(self) -> bool:
        return not check_folder(folder_reader(self.source),
                                lambda path: (self.source / path).exists()).errors()

    def test_a_page_and_each_use_of_its_name_are_renamed(self):
        written = rename_page(self.source, "settings", "config")
        self.assertEqual(written, ["pages/config.page.toml", "pages/config.nx",
                                   "pages/lib/frame.nx", "app.toml"])
        # The page keeps its place, and so its ID.
        self.assertEqual(self.pages(), ["home", "schedule", "day", "config"])
        self.assertFalse((self.source / "pages/settings.page.toml").exists())
        self.assertFalse((self.source / "pages/settings.nx").exists())
        self.assertIn('name = "config"', self.text("pages/config.page.toml"))
        self.assertIn("on config.load:", self.text("pages/config.nx"))
        self.assertIn("page config", self.text("pages/lib/frame.nx"))
        # Pictures whose names contain the old name, such as settings/normal, keep their
        # names.
        self.assertIn('"settings/normal"', self.text("app.toml"))
        self.assertTrue(self.builds())

    def test_a_change_of_letter_case_alone(self):
        rename_page(self.source, "settings", "Settings")
        self.assertEqual(self.pages(), ["home", "schedule", "day", "Settings"])
        listed = {path.name for path in (self.source / "pages").iterdir()}
        self.assertLessEqual({"Settings.page.toml", "Settings.nx"}, listed)
        self.assertNotIn("settings.nx", listed)
        self.assertTrue(self.builds())

    def test_refusals_write_nothing(self):
        before = self.files()
        for page, new_name, message in (
                ("nowhere", "config", "no page named nowhere"),
                ("settings", "settings", "named settings already"),
                ("settings", "HOME", "a page named home already"),
                ("settings", "two words", "not a valid page name"),
                ("settings", "1st", "starts with a digit"),
                ("settings", "a_name_too_long", "the Nextion Editor keeps 14")):
            with self.subTest(new_name=new_name):
                with self.assertRaisesRegex(NxwrightError, message):
                    rename_page(self.source, page, new_name)
        self.assertEqual(self.files(), before)

    def test_a_folder_with_an_error_is_refused(self):
        with (self.source / "pages/home.nx").open("a", encoding="utf-8") as code:
            code.write("\non home.load:\n  nosuch.txt=\"x\"\n")
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "the folder's checks find an error"):
            rename_page(self.source, "settings", "config")
        self.assertEqual(self.files(), before)

    def test_a_rename_the_build_would_refuse_writes_nothing(self):
        # A component of the page home already has the name.
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "would not build after the rename"):
            rename_page(self.source, "settings", "navHome")
        self.assertEqual(self.files(), before)

    def test_a_failed_write_puts_the_files_back(self):
        before = self.files()
        with mock.patch("nxwright.source.page_renaming.write_texts",
                        side_effect=OSError("disk full")):
            with self.assertRaisesRegex(OSError, "disk full"):
                rename_page(self.source, "settings", "config")
        self.assertEqual(self.files(), before)

    def test_a_page_whose_name_is_not_plain(self):
        # Turns the page day into a page named a:b, written the way extract writes
        # one. The page's file names are encoded, its event headings quote the name,
        # and frame.nx shows the page by its ID.
        for old_path, new_path in ((page_toml_path("day"), page_toml_path("a:b")),
                                   (page_nx_path("day"), page_nx_path("a:b"))):
            (self.source / old_path).rename(self.source / new_path)
        page_file = self.source / page_toml_path("a:b")
        page_file.write_text(page_file.read_text(encoding="utf-8").replace(
            'name = "day"', 'name = "a:b"', 1), encoding="utf-8")
        nx_file = self.source / page_nx_path("a:b")
        nx_file.write_text(nx_file.read_text(encoding="utf-8").replace("on day.", 'on "a:b".'),
                           encoding="utf-8")
        app = self.source / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace('    "day",\n', '    "a:b",\n'),
                       encoding="utf-8")
        frame = self.source / "pages/lib/frame.nx"
        frame.write_text(frame.read_text(encoding="utf-8").replace("page day", "page 2"),
                         encoding="utf-8")
        self.assertTrue(self.builds())
        rename_page(self.source, "a:b", "day")
        self.assertEqual(self.pages(), ["home", "schedule", "day", "settings"])
        self.assertIn('name = "day"', self.text("pages/day.page.toml"))
        self.assertFalse((self.source / page_toml_path("a:b")).exists())
        self.assertTrue(self.builds())

    def test_the_command_line(self):
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            code = main(["rename", str(self.source), "page", "settings", "config"])
        self.assertEqual(code, 0)
        self.assertIn("Renamed the page settings to config", printed.getvalue())
        self.assertEqual(self.pages(), ["home", "schedule", "day", "config"])


if __name__ == "__main__":
    unittest.main()
