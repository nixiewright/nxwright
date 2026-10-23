"""The dumper, on small project files built by hand: the files it writes, and
what it refuses."""
from pathlib import Path
import tempfile
import unittest

from nxwright.project.dumper import ProjectDumper
from nxwright import NxwrightError
from tests.test_container import build_project, manifest
from tests.test_page_block import object_body, page_block, record


def font_block(height: int) -> bytes:
    """Returns a font block holding only its header: `height`, and characters 0x20
    to 0x7e. These tests do not need the glyphs."""
    header = bytearray(44)
    header[7], header[10], header[11] = height, 0x20, 0x7e
    return bytes(header)


def write_project(folder: Path, page_name: str = "main", extra_blocks=(),
                  listed=("0.pa",), pages=None) -> Path:
    """Writes a project file into `folder` and returns its path.

    `pages` maps block names to page names (default: one page "0.pa"), and
    `listed` is the manifest's resource list in ID order.
    """
    pages = pages or {"0.pa": page_name}
    blocks = [("main.HMI", manifest(*listed), 0), ("Program.s", b"//code", 0)]
    blocks += [(block_name, page_block(name, object_body(record(b"att-28"))), 0)
               for block_name, name in pages.items()]
    path = folder / "project.HMI"
    path.write_bytes(build_project(blocks + list(extra_blocks)))
    return path


class OutputFolderTest(unittest.TestCase):

    def test_refuses_non_empty_output_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / "keep.txt"
            existing.write_text("old dump")
            with self.assertRaises(NxwrightError):
                ProjectDumper(Path(folder) / "missing.HMI", Path(folder)).dump()
            self.assertEqual(existing.read_text(), "old dump")


class SmallProjectTest(unittest.TestCase):

    def test_dumps_minimal_project(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "dump"
            ProjectDumper(write_project(Path(folder), "main"), output).dump()
            self.assertTrue((output / "pages" / "00-main.txt").exists())
            self.assertEqual((output / "program.s").read_bytes(), b"//code")

    def test_refuses_page_name_with_path_characters(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "dump"
            with self.assertRaises(NxwrightError):
                ProjectDumper(write_project(Path(folder), "../evil"), output).dump()
            self.assertEqual(list((output / "pages").iterdir()), [])

    def test_files_are_numbered_by_editor_id(self):
        # The manifest order, not the block name, gives the Editor's IDs.
        with tempfile.TemporaryDirectory() as folder:
            project = write_project(
                Path(folder), pages={"0.pa": "first", "1.pa": "second"},
                extra_blocks=[("0.zi", font_block(12), 0), ("1.zi", font_block(30), 0)],
                listed=("1.pa", "0.pa", "1.zi", "0.zi"))
            output = Path(folder) / "dump"
            ProjectDumper(project, output).dump()
            self.assertEqual(sorted(path.name for path in (output / "pages").iterdir()),
                             ["00-second.txt", "01-first.txt"])
            self.assertEqual((output / "fonts" / "00.zi").read_bytes(), font_block(30))

    def test_macros_are_dumped_as_they_are(self):
        # The Editor keeps a project's macros in the block comcode.sn: each
        # macro's name, its number of lines, then its lines (format.md).
        block = b"newcall\r\n1\r\nprinth 4D\r\n"
        with tempfile.TemporaryDirectory() as folder:
            project = write_project(Path(folder), extra_blocks=[("comcode.sn", block, 0)])
            output = Path(folder) / "dump"
            ProjectDumper(project, output).dump()
            self.assertEqual((output / "macros.s").read_bytes(), block)

    def test_a_project_without_macros_dumps_none(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "dump"
            ProjectDumper(write_project(Path(folder)), output).dump()
            self.assertFalse((output / "macros.s").exists())

    def test_refuses_block_missing_from_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            project = write_project(Path(folder), extra_blocks=[("0.zi", font_block(12), 0)])
            with self.assertRaises(NxwrightError):
                ProjectDumper(project, Path(folder) / "dump").dump()

    def test_refuses_unknown_block_kind(self):
        with tempfile.TemporaryDirectory() as folder:
            project = write_project(Path(folder), "main", [("2.ib", b"?", 0)])
            with self.assertRaises(NxwrightError):
                ProjectDumper(project, Path(folder) / "dump").dump()


if __name__ == "__main__":
    unittest.main()
