"""Locked pages: a project file built from a folder in nxlang has its pages
locked, with no password, to show in the Nextion Editor that it is not meant
for editing (project/page_header.py, with_lock)."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from nxwright.cli import main
from nxwright.project.container import HmiContainer
from nxwright.project.page_block import parse_page
from nxwright.project.page_header import NO_LOCK_PASSWORD, page_header_of
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import read_app
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware

PASSWORD_HASH = "a1b2c3d4"


def run(arguments: list) -> int:
    """Runs the nxwright command, and returns its exit code."""
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        return main(arguments)


def headers_of(project: Path) -> dict:
    """Returns {page name: PageHeader} of the project file `project`."""
    container = HmiContainer.from_file(project)
    pages = [parse_page(data) for name, data in container.blocks.items() if name.endswith(".pa")]
    return {page.name: page_header_of(page) for page in pages}


class LockedPagesTestCase(unittest.TestCase):
    """A new folder of two pages, in the language LANGUAGE."""

    LANGUAGE = "nxlang"

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        self.assertEqual(run(["new", str(self.source), "--screen", "NX4832T035", "--language",
                              self.LANGUAGE, "--name", "app"]), 0)
        self.assertEqual(run(["new-page", str(self.source), "second"]), 0)
        self.project = self.folder / "app.HMI"

    def tearDown(self):
        self._folder.cleanup()

    def add_to_page_table(self, page: str, *lines: str):
        """Adds `lines` to the [page] table of `page`'s page file."""
        path = self.source / "pages" / (page + ".page.toml")
        text = path.read_text(encoding="utf-8")
        added = "".join(line + "\n" for line in lines)
        self.assertIn("[page]\n", text)
        path.write_text(text.replace("[page]\n", "[page]\n" + added, 1), encoding="utf-8",
                        newline="\n")

    def build_headers(self, *options: str) -> dict:
        self.assertEqual(run(["build", "--overwrite", "--no-backup", str(self.source),
                              str(self.project), *options]), 0)
        return headers_of(self.project)


class NxlangBuildTest(LockedPagesTestCase):

    def test_every_page_is_locked_with_no_password(self):
        headers = self.build_headers()
        self.assertEqual(sorted(headers), ["page0", "second"])
        for name, header in headers.items():
            with self.subTest(page=name):
                self.assertIs(header.locked, True)
                self.assertEqual(header.lock_password_hash, NO_LOCK_PASSWORD)

    def test_no_lock_leaves_the_pages_unlocked(self):
        for name, header in self.build_headers("--no-lock").items():
            with self.subTest(page=name):
                self.assertIs(header.locked, False)

    def test_the_source_folder_does_not_change(self):
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        self.build_headers()
        self.assertEqual({path: path.read_bytes() for path in self.source.rglob("*")
                          if path.is_file()}, before)

    def test_it_overrides_locked_false(self):
        self.add_to_page_table("second", "locked = false")
        self.assertIs(self.build_headers()["second"].locked, True)

    def test_a_page_keeps_another_lock_value(self):
        self.add_to_page_table("second", "locked = 2")
        self.assertEqual(self.build_headers()["second"].locked, 2)

    def test_a_locked_page_keeps_its_password(self):
        self.add_to_page_table("second", "locked = true",
                               'lock_password_hash = "%s"' % PASSWORD_HASH)
        header = self.build_headers()["second"]
        self.assertIs(header.locked, True)
        self.assertEqual(header.lock_password_hash.hex(), PASSWORD_HASH)

    def test_an_unlocked_page_with_a_password_stays_unlocked(self):
        # Locking it would bring back a password the user may have forgotten.
        self.add_to_page_table("second", 'lock_password_hash = "%s"' % PASSWORD_HASH)
        header = self.build_headers()["second"]
        self.assertIs(header.locked, False)
        self.assertEqual(header.lock_password_hash.hex(), PASSWORD_HASH)

    def test_a_project_extracted_into_a_new_folder_keeps_the_locks(self):
        self.build_headers()
        recovered = self.folder / "recovered"
        extract(self.project, recovered)
        self.assertEqual(read_app(recovered)["language"], "nextion")
        for page in ("page0", "second"):
            self.assertIn("locked = true", (recovered / "pages" / (page + ".page.toml"))
                          .read_text(encoding="utf-8"))
        again = self.folder / "again.HMI"
        build(recovered, again)
        self.assertEqual(again.read_bytes(), self.project.read_bytes())


class StrictBuildTest(LockedPagesTestCase):

    LANGUAGE = "nextion"

    def test_the_pages_stay_unlocked_with_or_without_the_flag(self):
        for options in ((), ("--no-lock",)):
            for name, header in self.build_headers(*options).items():
                with self.subTest(options=options, page=name):
                    self.assertIs(header.locked, False)

    def test_a_locked_page_stays_locked_with_the_flag(self):
        self.add_to_page_table("second", "locked = true")
        headers = self.build_headers("--no-lock")
        self.assertIs(headers["second"].locked, True)
        self.assertIs(headers["page0"].locked, False)


class CompileTest(LockedPagesTestCase):
    """compile with --project-file, with firmware of the tests' own."""

    def compile(self, name: str, *options: str) -> Path:
        """Compiles the folder into the TFT file `name`, and returns it."""
        firmware = self.folder / "firmware.tft"
        firmware.write_bytes(made_tft("T"))
        tft = self.folder / name
        with stand_in_firmware(self.folder / "cache"):
            self.assertEqual(run(["compile", str(self.source), str(tft), "--firmware",
                                  str(firmware), "--overwrite", "--no-backup", "--project-file",
                                  str(self.project), *options]), 0)
        return tft

    def test_the_project_file_is_locked_and_the_tft_file_is_the_same(self):
        locked = self.compile("locked.tft")
        self.assertIs(headers_of(self.project)["page0"].locked, True)
        unlocked = self.compile("unlocked.tft", "--no-lock")
        self.assertIs(headers_of(self.project)["page0"].locked, False)
        self.assertEqual(locked.read_bytes(), unlocked.read_bytes())

    def test_no_lock_has_no_effect_on_a_compile_from_a_project_file(self):
        self.build_headers()
        firmware = self.folder / "firmware.tft"
        firmware.write_bytes(made_tft("T"))
        with stand_in_firmware(self.folder / "cache"):
            self.assertEqual(run(["compile", str(self.project), str(self.folder / "from.tft"),
                                  "--firmware", str(firmware), "--no-lock"]), 0)
        self.assertIs(headers_of(self.project)["page0"].locked, True)


if __name__ == "__main__":
    unittest.main()
