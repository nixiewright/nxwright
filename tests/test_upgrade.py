"""nxwright upgrade: converting a source folder to the current format.

nxwright has no step yet, so the tests of how steps run stand in a later
format and steps of their own, patched in."""
import contextlib
import io
from pathlib import Path
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.source import source_folder, upgrade
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase


def _files(folder: Path) -> dict:
    return {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*")
            if path.is_file()}


class UpgradeTest(SourceFolderTestCase):

    def test_a_current_folder_is_left_as_it_is(self):
        before = _files(self.source)
        self.assertEqual(upgrade.upgrade(self.source), [])
        self.assertEqual(_files(self.source), before)

    def test_an_app_toml_saved_with_a_byte_order_mark(self):
        # As VS Code's "UTF-8 with BOM" saves it: the mark is not TOML.
        path = self.source / "app.toml"
        path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
        self.assertEqual(upgrade.folder_format(self.source), 1)

    def test_a_folder_in_a_newer_format_is_refused(self):
        edit_text(self.source / "app.toml", "format = 1", "format = 2")
        before = _files(self.source)
        with self.assertRaisesRegex(NxwrightError, "source format 2, which needs a newer "
                                                   "nxwright; this one reads format 1"):
            upgrade.upgrade(self.source)
        self.assertEqual(_files(self.source), before)

    def test_the_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["upgrade", str(self.source)]), 0)
        self.assertIn("already in the current source format", output.getvalue())


class StepTest(SourceFolderTestCase):
    """Format 3 stands in for the current format, with steps that record their
    order, from a folder in format 1."""

    def setUp(self):
        super().setUp()
        self.ran = []

    def step(self, to: int):
        def convert(folder: Path):
            self.ran.append(to)
            edit_text(folder / "app.toml", "format = %d" % (to - 1), "format = %d" % to)
        return convert

    def test_every_step_runs_in_order(self):
        with mock.patch.object(upgrade, "SOURCE_FORMAT", 3), \
                mock.patch.dict(upgrade.MIGRATIONS, {1: self.step(2), 2: self.step(3)}):
            self.assertEqual(upgrade.upgrade(self.source), [2, 3])
        self.assertEqual(self.ran, [2, 3])
        self.assertIn("format = 3", (self.source / "app.toml").read_text(encoding="utf-8"))

    def test_a_missing_step_is_refused(self):
        with mock.patch.object(upgrade, "SOURCE_FORMAT", 2), \
                mock.patch.dict(upgrade.MIGRATIONS, {}, clear=True):
            with self.assertRaisesRegex(NxwrightError, "no step converts source format 1 to 2"):
                upgrade.upgrade(self.source)

    def test_a_folder_in_an_older_format_points_to_upgrade(self):
        with mock.patch.object(source_folder, "SOURCE_FORMAT", 2):
            self.assert_export_refused("source format 1; nxwright upgrade converts it to format 2")


if __name__ == "__main__":
    unittest.main()
