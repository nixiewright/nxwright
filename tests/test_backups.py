"""Backups: what replacing a project file or a TFT file keeps of the old one
(project/replacing.py, project/written_files.py), and --no-backup on the commands
that replace one. Each test has a cache folder of its own, so that the record of
what nxwright wrote starts empty."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project import replacing
from nxwright.project.replacing import written_beside
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware


def run(arguments: list) -> tuple:
    """Runs the nxwright command; returns its exit code and its error output."""
    errors = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(errors):
        code = main(arguments)
    return code, errors.getvalue()


def backups_in(folder: Path) -> list:
    """Returns the names in `folder` ending in .bak, sorted."""
    return sorted(path.name for path in folder.iterdir() if path.name.endswith(".bak"))


class OwnCacheMixin:
    """Points NXWRIGHT_CACHE at a temporary folder, apart from the test's files."""

    def use_own_cache(self):
        cache = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(cache.cleanup)
        self.cache = Path(cache.name)
        patch = mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": str(self.cache)})
        patch.start()
        self.addCleanup(patch.stop)


class WrittenBesideTest(OwnCacheMixin, unittest.TestCase):
    """written_beside on stand-in files. The output starts with no record."""

    def setUp(self):
        self.use_own_cache()
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.output = self.folder / "app.HMI"
        self.output.write_bytes(b"old")

    def replace(self, new: bytes, keep_backup: bool = True):
        with written_beside(self.output, keep_backup=keep_backup) as written:
            written.write_bytes(new)

    def make_backup(self, name: str, time: int, content: bytes = b"backup") -> Path:
        """Writes a stand-in backup called `name`, last modified at `time`."""
        path = self.folder / name
        path.write_bytes(content)
        os.utime(path, (time, time))
        return path

    def test_a_file_with_no_record_gets_a_backup_with_the_time_in_its_name(self):
        self.replace(b"new")
        self.assertEqual(self.output.read_bytes(), b"new")
        names = backups_in(self.folder)
        self.assertEqual(len(names), 1)
        self.assertRegex(names[0], r"^app\.HMI\.\d{4}-\d{2}-\d{2}-\d{6}\.bak$")
        self.assertEqual((self.folder / names[0]).read_bytes(), b"old")

    def test_a_file_nxwright_wrote_gets_no_backup(self):
        self.output.unlink()
        for content in (b"first", b"second", b"third", b"fourth"):
            self.replace(content)
        self.assertEqual(self.output.read_bytes(), b"fourth")
        self.assertEqual(backups_in(self.folder), [])

    def test_a_file_changed_elsewhere_gets_a_backup_every_time(self):
        # No backup is ever removed, however many there are.
        when = datetime(2026, 11, 6, 14, 32, 5)
        with mock.patch.object(replacing, "datetime") as clock:
            clock.now.return_value = when
            for number in range(8):
                self.output.write_bytes(b"edited elsewhere %d" % number)
                self.replace(b"built %d" % number)
        names = backups_in(self.folder)
        self.assertEqual(len(names), 8)
        self.assertIn("app.HMI.2026-11-06-143205.bak", names)
        self.assertIn("app.HMI.2026-11-06-143205-7.bak", names)

    def test_builds_after_a_change_elsewhere_do_not_push_out_its_backup(self):
        self.output.unlink()
        self.replace(b"built")
        self.output.write_bytes(b"edited elsewhere")
        for number in range(8):
            self.replace(b"built %d" % number)
        names = backups_in(self.folder)
        self.assertEqual(len(names), 1)
        self.assertEqual((self.folder / names[0]).read_bytes(), b"edited elsewhere")

    def test_a_backup_is_left_off_unless_asked_for(self):
        self.replace(b"new", keep_backup=False)
        self.assertEqual(self.output.read_bytes(), b"new")
        self.assertEqual(backups_in(self.folder), [])

    def test_a_write_without_a_backup_is_not_recorded(self):
        self.replace(b"new", keep_backup=False)
        self.replace(b"newer")
        self.assertEqual(len(backups_in(self.folder)), 1)

    def test_a_new_file_has_nothing_to_back_up(self):
        self.output.unlink()
        self.replace(b"new")
        self.assertEqual(backups_in(self.folder), [])

    def test_the_same_bytes_as_the_new_file_add_no_backup(self):
        self.replace(b"old")
        self.assertEqual(backups_in(self.folder), [])

    def test_the_same_bytes_as_the_newest_backup_add_no_backup(self):
        self.replace(b"new")
        # The file goes back to what the newest backup has.
        self.output.write_bytes(b"old")
        self.replace(b"newer")
        self.assertEqual(len(backups_in(self.folder)), 1)

    def test_the_same_bytes_as_an_older_backup_are_kept_again(self):
        self.make_backup("app.HMI.2026-01-01-000000.bak", 1000, b"old")
        self.make_backup("app.HMI.2026-01-02-000000.bak", 2000, b"middle")
        self.replace(b"new")
        self.assertEqual(len(backups_in(self.folder)), 3)

    def test_the_newest_backup_goes_by_its_time_and_not_its_name(self):
        self.make_backup("app.HMI.2026-01-09-000000.bak", 1000, b"older")
        self.make_backup("app.HMI.2026-01-01-000000.bak", 2000, b"old")
        self.replace(b"new")
        self.assertEqual(len(backups_in(self.folder)), 2)

    def test_a_numbered_backup_with_the_same_time_counts_as_the_newer(self):
        self.make_backup("app.HMI.2026-01-01-000000-1.bak", 1000, b"newer")
        self.make_backup("app.HMI.2026-01-01-000000.bak", 1000, b"older")
        self.output.write_bytes(b"newer")
        self.replace(b"new")
        self.assertEqual(len(backups_in(self.folder)), 2)

    def test_a_file_with_a_similar_name_is_not_a_backup(self):
        # Each has the old file's bytes, so it would stop the backup if it counted.
        for name in ("app.HMI.bak", "other.HMI.2026-01-01-000000.bak",
                     "app[1].HMI.2026-01-01-000000.bak", "app.HMI.2026-01-01.bak",
                     "app.HMI.2026-01-01-000000.bak.txt", "xapp.HMI.2026-01-01-000000.bak",
                     "app.HMI.2026-01-01-000000-x.bak", "app.tft.2026-01-01-000000.bak"):
            self.make_backup(name, 5000, b"old")
        (self.folder / "app.HMI.2026-01-01-000001.bak").mkdir()
        before = backups_in(self.folder)
        self.replace(b"new")
        self.assertEqual(len(backups_in(self.folder)), len(before) + 1)

    def test_a_name_with_a_bracket_matches_exactly(self):
        output = self.folder / "app[1].HMI"
        output.write_bytes(b"old")
        self.make_backup("app1.HMI.2026-01-01-000000.bak", 5000, b"old")
        with written_beside(output, keep_backup=True) as written:
            written.write_bytes(b"new")
        self.assertEqual(sum(1 for name in backups_in(self.folder)
                             if name.startswith("app[1]")), 1)

    def test_a_moved_file_has_no_record_so_it_gets_a_backup(self):
        self.output.unlink()
        self.replace(b"built")
        moved = self.folder / "moved.HMI"
        self.output.rename(moved)
        with written_beside(moved, keep_backup=True) as written:
            written.write_bytes(b"new")
        self.assertEqual(len(backups_in(self.folder)), 1)

    def test_with_the_cache_off_each_change_gets_a_backup(self):
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": "off"}):
            self.output.unlink()
            for number in range(4):
                self.replace(b"built %d" % number)
        self.assertEqual(len(backups_in(self.folder)), 3)

    def test_a_record_that_cannot_be_used_does_not_fail_the_replace(self):
        # A file where the record's folder should be.
        blocked = self.folder / "not-a-folder"
        blocked.write_bytes(b"")
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": str(blocked)}):
            self.replace(b"new")
        self.assertEqual(self.output.read_bytes(), b"new")
        self.assertEqual(len(backups_in(self.folder)), 1)

    def test_a_failure_while_writing_the_new_file_adds_no_backup(self):
        with self.assertRaisesRegex(ValueError, "while writing"):
            with written_beside(self.output, keep_backup=True) as written:
                written.write_bytes(b"new")
                raise ValueError("while writing")
        self.assertEqual(self.output.read_bytes(), b"old")
        self.assertEqual([path.name for path in self.folder.iterdir()], ["app.HMI"])

    def test_a_backup_that_cannot_be_written_stops_the_replace(self):
        real_open = open

        def refusing_open(path, *rest, **options):
            if str(path).endswith(".partial") and ".bak." in str(path):
                raise OSError(28, "No space left on device", str(path))
            return real_open(path, *rest, **options)

        with mock.patch("builtins.open", refusing_open), \
                self.assertRaisesRegex(NxwrightError, "No space left on device.*--no-backup"):
            self.replace(b"new")
        self.assertEqual(self.output.read_bytes(), b"old")
        self.assertEqual([path.name for path in self.folder.iterdir()], ["app.HMI"])

    def test_a_replace_that_fails_takes_its_backup_away_and_keeps_the_record(self):
        self.output.unlink()
        self.replace(b"built")
        self.output.write_bytes(b"edited elsewhere")
        real_replace = os.replace

        def refusing_replace(source, target):
            if Path(target) == self.output:
                raise PermissionError(13, "Permission denied", str(source), None, str(target))
            real_replace(source, target)

        with mock.patch("os.replace", refusing_replace), self.assertRaises(PermissionError):
            self.replace(b"new")
        self.assertEqual(self.output.read_bytes(), b"edited elsewhere")
        self.assertEqual(backups_in(self.folder), [])
        # The record still gives "built", so the next replace keeps the edits.
        self.replace(b"new")
        self.assertEqual(len(backups_in(self.folder)), 1)


class CommandsTest(OwnCacheMixin, SourceFolderTestCase):
    """The commands that replace a file, on the small test project."""

    def setUp(self):
        self.use_own_cache()
        super().setUp()

    def built_then_changed_elsewhere(self) -> tuple:
        """Builds a project with the command, then changes the file, as a save in
        the Nextion Editor would, and the folder, so that the next build differs.
        Returns the file and its bytes."""
        built = self.folder / "built.HMI"
        self.assertEqual(run(["build", "--overwrite", str(self.source), str(built)])[0], 0)
        changed = built.read_bytes() + b"\0"
        built.write_bytes(changed)
        program = self.source / "program.nx"
        program.write_text(program.read_text(encoding="utf-8") + "sys0=1\n", encoding="utf-8",
                           newline="\n")
        return built, changed

    def test_build_keeps_a_file_changed_elsewhere(self):
        built, changed = self.built_then_changed_elsewhere()
        self.assertEqual(run(["build", "--overwrite", str(self.source), str(built)]), (0, ""))
        names = backups_in(self.folder)
        self.assertEqual(len(names), 1)
        self.assertTrue(re.fullmatch(r"built\.HMI\.[\d-]+\.bak", names[0]), names[0])
        self.assertEqual((self.folder / names[0]).read_bytes(), changed)

    def test_build_keeps_no_backup_of_its_own_file(self):
        built = self.folder / "built.HMI"
        program = self.source / "program.nx"
        for _ in range(3):
            self.assertEqual(run(["build", "--overwrite", str(self.source), str(built)]), (0, ""))
            program.write_text(program.read_text(encoding="utf-8") + "sys0=1\n", encoding="utf-8",
                               newline="\n")
        self.assertEqual(backups_in(self.folder), [])

    def test_no_backup_on_build(self):
        built, _ = self.built_then_changed_elsewhere()
        self.assertEqual(run(["build", "--overwrite", "--no-backup", str(self.source),
                              str(built)]), (0, ""))
        self.assertEqual(backups_in(self.folder), [])

    def test_a_failed_build_makes_no_backup(self):
        built, changed = self.built_then_changed_elsewhere()
        (self.source / "program.nx").write_text("this is not code\n", encoding="utf-8",
                                                newline="\n")
        code, _ = run(["build", "--overwrite", str(self.source), str(built)])
        self.assertEqual(code, 1)
        self.assertEqual(built.read_bytes(), changed)
        self.assertEqual(backups_in(self.folder), [])

    def edited_dump(self):
        edit_text(self.dump / "pages" / "01-second.txt", 'txt = "bye"', 'txt = "goodbye"')

    def test_write_keeps_a_file_with_no_record(self):
        self.edited_dump()
        old = self.project.read_bytes()
        output = str(self.project)
        self.assertEqual(run(["write", "--overwrite", output, str(self.dump), output]), (0, ""))
        names = backups_in(self.folder)
        self.assertEqual(len(names), 1)
        self.assertEqual((self.folder / names[0]).read_bytes(), old)

    def test_no_backup_on_write(self):
        self.edited_dump()
        output = str(self.project)
        self.assertEqual(run(["write", "--overwrite", "--no-backup", output, str(self.dump),
                              output]), (0, ""))
        self.assertEqual(backups_in(self.folder), [])

    def test_a_failed_write_makes_no_backup(self):
        old = self.project.read_bytes()
        (self.dump / "pages" / "01-second.txt").write_text("this is not a page\n",
                                                           encoding="utf-8", newline="\n")
        output = str(self.project)
        code, _ = run(["write", "--overwrite", output, str(self.dump), output])
        self.assertEqual(code, 1)
        self.assertEqual(self.project.read_bytes(), old)
        self.assertEqual(backups_in(self.folder), [])

    def test_page_makes_no_backup(self):
        page_file = self.folder / "second.page"
        arguments = ["page", "--overwrite", str(self.dump), "1", str(page_file)]
        self.assertEqual(run(arguments), (0, ""))
        self.edited_dump()
        self.assertEqual(run(arguments), (0, ""))
        self.assertEqual(backups_in(self.folder), [])


class TftCommandsTest(unittest.TestCase):
    """compile and rescue, with firmware of the tests' own. stand_in_firmware
    gives them a cache folder of their own."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.firmware = self.folder / "firmware.tft"
        self.firmware.write_bytes(made_tft("T"))
        self.tft = self.folder / "app.tft"
        # A TFT file nxwright has no record of, for the commands to replace.
        self.tft.write_bytes(made_tft("T", fonts=b"other"))
        self.old = self.tft.read_bytes()

    def rescue(self, *options: str) -> int:
        with stand_in_firmware(self.folder / "cache"):
            return run(["rescue", str(self.tft), "--firmware", str(self.firmware), "--screen",
                        "NX4832T035", "--overwrite", *options])[0]

    def test_rescue_keeps_a_tft_file_with_no_record(self):
        self.assertEqual(self.rescue(), 0)
        names = backups_in(self.folder)
        self.assertEqual(len(names), 1)
        self.assertTrue(names[0].startswith("app.tft."), names[0])
        self.assertEqual((self.folder / names[0]).read_bytes(), self.old)
        # The new file is nxwright's own.
        self.assertEqual(self.rescue(), 0)
        self.assertEqual(len(backups_in(self.folder)), 1)

    def test_no_backup_on_rescue(self):
        self.assertEqual(self.rescue("--no-backup"), 0)
        self.assertNotEqual(self.tft.read_bytes(), self.old)
        self.assertEqual(backups_in(self.folder), [])

    def compile(self, source: Path, *options: str) -> int:
        with stand_in_firmware(self.folder / "cache"):
            return run(["compile", str(source), str(self.tft), "--firmware", str(self.firmware),
                        "--overwrite", *options])[0]

    def source_folder(self) -> Path:
        source = self.folder / "source"
        self.assertEqual(run(["new", str(source), "--screen", "NX4832T035", "--language",
                              "nextion", "--name", "app"])[0], 0)
        return source

    def changed_project(self, source: Path) -> tuple:
        """Writes a project file nxwright has no record of, and changes the folder
        so that the next build differs. Returns the file and its bytes."""
        project = self.folder / "app.HMI"
        self.assertEqual(run(["build", "--no-backup", str(source), str(project)])[0], 0)
        program = source / "program.nx"
        program.write_text(program.read_text(encoding="utf-8") + "sys0=1\n", encoding="utf-8",
                           newline="\n")
        return project, project.read_bytes()

    def test_compile_keeps_the_tft_and_project_files_with_no_record(self):
        source = self.source_folder()
        project, old_project = self.changed_project(source)
        self.assertEqual(self.compile(source, "--project-file", str(project)), 0)
        self.assertNotEqual(project.read_bytes(), old_project)
        names = backups_in(self.folder)
        self.assertEqual(len(names), 2)
        by_start = {name.split(".")[1]: self.folder / name for name in names}
        self.assertEqual(by_start["HMI"].read_bytes(), old_project)
        self.assertEqual(by_start["tft"].read_bytes(), self.old)

    def test_no_backup_on_compile(self):
        source = self.source_folder()
        project, _ = self.changed_project(source)
        self.assertEqual(self.compile(source, "--project-file", str(project), "--no-backup"), 0)
        self.assertEqual(backups_in(self.folder), [])


if __name__ == "__main__":
    unittest.main()
