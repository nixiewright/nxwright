"""The project file and the source folder describe the same screen."""
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest

from nxwright.source.formatting import format_folder
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import folder_reader
from screen import APP, PROJECT


def _files(folder: Path) -> list:
    return sorted(path.relative_to(folder) for path in folder.rglob("*") if path.is_file())


class ProjectMatchesSourceTest(unittest.TestCase):

    def test_building_the_source_folder_gives_the_project_file(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "built.HMI"
            build(APP, output)
            self.assertTrue(output.read_bytes() == PROJECT.read_bytes(),
                            "the build differs from %s; build it again" % PROJECT.name)

    def test_the_code_is_formatted(self):
        # nxwright format would change nothing.
        self.assertEqual(format_folder(folder_reader(APP)), {})

    def test_names_fit_the_editor(self):
        # The Editor keeps 14 bytes of a page's or component's name, and
        # cuts the rest when it opens the project: code naming it then fails.
        for path in sorted((APP / "pages").glob("*.toml")):
            with open(path, "rb") as file:
                page = tomllib.load(file)
            for table in [page["page"]] + page.get("component", []):
                with self.subTest(page=path.stem, name=table["name"]):
                    self.assertLessEqual(len(table["name"].encode("latin-1")), 14)

    def test_extracting_the_project_changes_nothing(self):
        # As after a save in the Editor: every file of the source folder stays.
        with tempfile.TemporaryDirectory() as folder:
            copy = Path(folder) / "app"
            shutil.copytree(APP, copy)
            extract(PROJECT, copy)
            self.assertEqual(_files(copy), _files(APP))
            for relative in _files(APP):
                with self.subTest(file=str(relative)):
                    self.assertEqual((copy / relative).read_bytes(), (APP / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
