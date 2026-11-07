"""Reading the firmware (tft/firmware.py): from a TFT file the tests make,
from the installed Nextion Editor where there is one, and the search
through the sources, with stand-ins for the firmware, the cache, and the
installed Nextion Editor (tests/tft/stand_in_firmware.py)."""
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError

from nxwright.tft import firmware as tft_firmware, firmware_versions
from nxwright.tft.firmware import (find_firmware, firmware_from_editor_folder, firmware_from_tft,
                            installed_editor_folder, installed_firmware, zero_firmware)
from nxwright.tft.tft_file import firmware_names
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware, write_editor_folder

# Where Nextion offers the installer of the Nextion Editor 1.68.2.
INSTALLER = "https://nextion.tech/download/nextion-setup-v1-68-2.exe"
# The real program_version, which stand_in_firmware replaces, for the tests
# of how a folder's version is read.
REAL_PROGRAM_VERSION = tft_firmware.program_version
# Some tests need pefile, which nxwright does not install on Windows, because
# Windows' own functions read a program's version.
NO_PEFILE = importlib.util.find_spec("pefile") is None


class FromTftTest(unittest.TestCase):

    def test_its_files_and_version(self):
        firmware = firmware_from_tft(made_tft("T", version=(1, 69, 0)), "a.tft", "T")
        self.assertEqual(firmware.version, (1, 69, 0))
        self.assertEqual(list(firmware.files), list(firmware_names("T")))
        self.assertEqual(firmware.files["input.bin"], b"input" * 3)

    def test_another_series_is_refused(self):
        with self.assertRaisesRegex(NxwrightError, "a.tft is a TFT file of the P series"):
            firmware_from_tft(made_tft("P"), "a.tft", "T")

    def test_zeros_of_its_sizes(self):
        firmware = firmware_from_tft(made_tft("P"), "a.tft", "P")
        zeros = zero_firmware(firmware)
        self.assertEqual(zeros.version, firmware.version)
        self.assertEqual({name: len(data) for name, data in zeros.files.items()},
                         {name: len(data) for name, data in firmware.files.items()})
        self.assertEqual(set(b"".join(zeros.files.values())), {0})


class FindTest(unittest.TestCase):
    """find_firmware's order of the sources: a named TFT file or Nextion
    Editor folder, then the cache, then the installed Nextion Editor."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.cache = self.folder / "cache"

    def tearDown(self):
        self._folder.cleanup()

    def tft(self, series: str = "T", version: tuple = (1, 68, 2)) -> Path:
        file = self.folder / ("%s-%d.tft" % (series, version[1]))
        file.write_bytes(made_tft(series, version=version))
        return file

    def cached(self, series: str) -> set:
        """The names of the cache's firmware files of 1.68.2 for `series`."""
        folder = self.cache / "firmware" / "1.68.2"
        return {name for name in firmware_names(series) if (folder / name).exists()}

    def test_a_named_tft_serves_and_is_cached(self):
        with stand_in_firmware(self.cache):
            found = find_firmware("T", named_tft=self.tft())
            self.assertEqual(found.source, "the TFT file %s" % self.tft())
            self.assertEqual(found.firmware.version, (1, 68, 2))
            self.assertEqual(self.cached("T"), set(firmware_names("T")))
            # The next search, with nothing named, takes the cache.
            again = find_firmware("T")
            self.assertTrue(again.source.startswith("the cache, "))
            self.assertEqual(again.firmware, found.firmware)

    def test_a_named_source_that_fails_its_hash_stops_the_search(self):
        with stand_in_firmware(self.cache):
            firmware_versions.MATCHED_VERSIONS[(1, 68, 2)]["input.bin"] = "0" * 64
            with self.assertRaisesRegex(NxwrightError, r"T-68\.tft: its input\.bin is not the "
                                                       r"Nextion Editor 1\.68\.2's"):
                find_firmware("T", named_tft=self.tft())
            self.assertEqual(self.cached("T"), set())

    def test_both_named_are_refused(self):
        with stand_in_firmware(self.cache):
            with self.assertRaisesRegex(NxwrightError, "not both"):
                find_firmware("T", named_tft=self.tft(), named_folder=self.folder)

    def test_a_named_folder_serves_and_caches_every_series(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache):
            found = find_firmware("T", named_folder=editor)
            self.assertEqual(found.source, "the Nextion Editor folder %s" % editor)
            for series in "TKFPE":
                self.assertEqual(self.cached(series), set(firmware_names(series)))

    def test_a_named_folder_that_fails_stops_the_search(self):
        editor = write_editor_folder(self.folder / "editor")
        (editor / "asp0.dll").write_bytes(b"another file")
        with stand_in_firmware(self.cache):
            with self.assertRaisesRegex(NxwrightError, r"editor: its asp0\.dll is not the Nextion "
                                                       r"Editor 1\.68\.2's"):
                find_firmware("T", named_folder=editor)
            self.assertFalse(self.cache.exists())
            (editor / "asp0.dll").unlink()
            with self.assertRaisesRegex(NxwrightError, r"editor's asp0\.dll could not be read"):
                find_firmware("T", named_folder=editor)

    def test_the_installed_editor_serves_and_caches_every_series(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache, installed=editor):
            found = find_firmware("P")
            self.assertEqual(found.source, "the installed Nextion Editor, %s" % editor)
            self.assertEqual(self.cached("T"), set(firmware_names("T")))

    def test_the_cache_comes_before_the_installed_editor(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache, installed=editor):
            find_firmware("T")
            self.assertTrue(find_firmware("T").source.startswith("the cache, "))

    def test_a_damaged_cache_file_is_skipped(self):
        # As a write that broke off leaves it: it fails its hash.
        with stand_in_firmware(self.cache):
            find_firmware("T", named_tft=self.tft())
            cached = self.cache / "firmware" / "1.68.2" / "asp0.dll"
            cached.write_bytes(cached.read_bytes()[:2])
            found = find_firmware("T")
            self.assertIsNone(found.firmware)
            self.assertEqual(found.skipped, (
                "the cache's firmware of the Nextion Editor 1.68.2: its asp0.dll is not the "
                "Nextion Editor 1.68.2's", "no Nextion Editor is installed"))
            # A later source writes the file again.
            find_firmware("T", named_tft=self.tft())
            self.assertTrue(find_firmware("T").source.startswith("the cache, "))

    def test_nothing_serves(self):
        with stand_in_firmware(self.cache):
            found = find_firmware("K")
        self.assertEqual((found.firmware, found.source), (None, ""))
        self.assertEqual(found.skipped, (
            "the cache has no firmware of the Nextion Editor 1.68.2 for this series",
            "no Nextion Editor is installed"))

    def test_the_cache_off(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(None, installed=editor):
            found = find_firmware("T")
            self.assertEqual(found.source, "the installed Nextion Editor, %s" % editor)
            self.assertEqual(found.skipped, ("the cache is turned off (NXWRIGHT_CACHE)",))
            self.assertFalse(self.cache.exists())

    def test_an_older_installed_editor_is_skipped(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache, installed=editor, installed_version=(1, 67, 0)):
            found = find_firmware("T")
        self.assertIsNone(found.firmware)
        self.assertIn("the installed Nextion Editor is 1.67.0, but nxwright takes only the firmware "
                      "of the Nextion Editor 1.68.2. You can install the Nextion Editor 1.68.2 "
                      "from %s" % INSTALLER,
                      found.skipped)

    def test_an_installed_editor_missing_a_file_is_skipped(self):
        editor = write_editor_folder(self.folder / "editor")
        (editor / "asp0.dll").unlink()
        with stand_in_firmware(self.cache, installed=editor):
            found = find_firmware("T")
        self.assertIsNone(found.firmware)
        self.assertRegex(found.skipped[-1], r"^the installed Nextion Editor's asp0\.dll could not "
                                            r"be read: ")

    def test_a_later_installed_editor_is_skipped(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache, installed=editor, installed_version=(1, 69, 0)):
            found = find_firmware("T")
            self.assertFalse((self.cache / "firmware" / "1.69.0").exists())
        self.assertIsNone(found.firmware)
        self.assertIn("the installed Nextion Editor is 1.69.0, but nxwright takes only the firmware "
                      "of the Nextion Editor 1.68.2. You can install the Nextion Editor 1.68.2 "
                      "from %s" % INSTALLER,
                      found.skipped)

    def test_a_named_source_of_another_version_is_refused(self):
        tft = self.folder / "later.tft"
        tft.write_bytes(made_tft("T", version=(1, 69, 0)))
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache, installed_version=(1, 67, 0)):
            with self.assertRaisesRegex(NxwrightError, r"^%s was made by the Nextion Editor "
                                                       r"1\.69\.0, but nxwright takes only"
                                                       % re.escape(str(tft))):
                find_firmware("T", named_tft=tft)
            with self.assertRaisesRegex(NxwrightError, r"^the Nextion Editor in %s is 1\.67\.0, "
                                                       r"but nxwright takes only"
                                                       % re.escape(str(editor))):
                find_firmware("T", named_folder=editor)
        self.assertFalse((self.cache / "firmware").exists())

    def test_a_folder_s_version_off_windows_comes_from_its_program(self):
        # Read with pefile, where Windows' own functions are not there, so a
        # later version's folder is refused off Windows as on Windows.
        editor = write_editor_folder(self.folder / "editor")
        (editor / "asp0.dll").write_bytes(b"another version's file")
        with stand_in_firmware(self.cache), mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(tft_firmware, "program_version", REAL_PROGRAM_VERSION), \
                mock.patch.object(tft_firmware, "_version_from_resource",
                                  lambda program: (1, 69, 0, 12)):
            self.assertEqual(firmware_from_editor_folder(editor, "T", "it").version, (1, 69, 0))
            with self.assertRaisesRegex(NxwrightError, r"is 1\.69\.0, but nxwright"):
                find_firmware("T", named_folder=editor)

    def test_pefile_missing_says_how_to_install_it(self):
        with mock.patch.dict(sys.modules, {"pefile": None}):
            with self.assertRaisesRegex(NxwrightError, r"reading a Nextion Editor's version off "
                                                       r"Windows needs pefile, which installing "
                                                       r"nxwright installs: python -m pip install "
                                                       r"pefile"):
                tft_firmware._version_from_resource(self.folder / "Nextion Editor.exe")

    @unittest.skipIf(NO_PEFILE, "pefile is not installed here")
    def test_a_folder_without_its_program_off_windows_is_refused(self):
        editor = write_editor_folder(self.folder / "editor")
        with stand_in_firmware(self.cache), mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(tft_firmware, "program_version", REAL_PROGRAM_VERSION):
            with self.assertRaisesRegex(NxwrightError, r"Nextion Editor\.exe has no version that "
                                                       r"could be read"):
                firmware_from_editor_folder(editor, "T", "it")


@unittest.skipIf(installed_editor_folder() is None, "the Nextion Editor is not installed here")
class InstalledTest(unittest.TestCase):

    def test_the_installed_firmware(self):
        firmware = installed_firmware("T")
        self.assertEqual(list(firmware.files), list(firmware_names("T")))
        self.assertEqual(len(firmware.version), 3)

    @unittest.skipIf(NO_PEFILE, "pefile is not installed here")
    def test_pefile_reads_the_version_windows_reads(self):
        program = installed_editor_folder() / "Nextion Editor.exe"
        self.assertEqual(tft_firmware._version_from_resource(program),
                         tft_firmware.program_version(program))


if __name__ == "__main__":
    unittest.main()
