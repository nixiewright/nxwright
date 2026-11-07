"""Replacing an earlier dump (project/dumper.py, replace_dump). Every test deletes only
in a temporary folder of its own. refuse_folder_to_delete_from is checked on paths
that never touch the disk."""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main, refuse_unless_replacing
from nxwright.project.dumper import (ProjectDumper, refuse_folder_to_delete_from, replace_dump,
                                     replace_dump_files)
from nxwright.project.project_writer import ProjectWriter
from tests.test_project_writer import write_small_project


def files_in(folder: Path) -> dict:
    """Returns {relative path: bytes} of every file under `folder`."""
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


class ReplaceDumpTestCase(unittest.TestCase):
    """A small project, its dump in the folder `dump`, and a second project with
    its second page removed."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.project = write_small_project(self.folder)
        self.dump = self.folder / "dump"
        ProjectDumper(self.project, self.dump).dump()
        edited = self.folder / "edited-dump"
        ProjectDumper(self.project, edited).dump()
        (edited / "pages" / "01-second.txt").unlink()
        self.smaller = self.folder / "smaller.HMI"
        ProjectWriter(self.project, edited, self.smaller).write()

    def tearDown(self):
        self._folder.cleanup()

    def run_command(self, *arguments) -> tuple:
        """Runs nxwright with no terminal, and returns (its exit code, what it printed
        to standard error)."""
        errors = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(errors):
            code = main([str(argument) for argument in arguments])
        return code, errors.getvalue()


class ReplaceTest(ReplaceDumpTestCase):

    def test_a_page_the_new_project_lacks_leaves_no_file(self):
        replace_dump(self.smaller, self.dump)
        self.assertFalse((self.dump / "pages" / "01-second.txt").exists())
        self.assertTrue((self.dump / "pages" / "00-first.txt").is_file())

    def test_the_result_is_what_a_new_dump_writes(self):
        replace_dump(self.smaller, self.dump)
        fresh = self.folder / "fresh"
        ProjectDumper(self.smaller, fresh).dump()
        self.assertEqual(files_in(self.dump), files_in(fresh))

    def test_a_file_the_user_added_at_the_top_stays(self):
        (self.dump / "notes.txt").write_text("keep", encoding="utf-8")
        replace_dump(self.smaller, self.dump)
        self.assertEqual((self.dump / "notes.txt").read_text(encoding="utf-8"), "keep")

    def test_a_folder_inside_a_dump_folder_stays(self):
        inner = self.dump / "pages" / "kept"
        inner.mkdir()
        (inner / "notes.txt").write_text("keep", encoding="utf-8")
        replace_dump(self.smaller, self.dump)
        self.assertEqual((inner / "notes.txt").read_text(encoding="utf-8"), "keep")

    def test_macros_the_new_project_lacks_leave_no_file(self):
        (self.dump / "macros.s").write_bytes(b"a\r\n1\r\nsys0=1\r\n")
        replace_dump(self.smaller, self.dump)
        self.assertFalse((self.dump / "macros.s").exists())

    def test_a_failed_dump_leaves_the_old_one_as_it_was(self):
        broken = self.folder / "broken.HMI"
        broken.write_bytes(b"not a project")
        before = files_in(self.dump)
        with self.assertRaises(NxwrightError):
            replace_dump(broken, self.dump)
        self.assertEqual(files_in(self.dump), before)

    def test_an_error_while_writing_does_not_point_at_the_temporary_folder(self):
        with mock.patch.object(ProjectDumper, "_write_pages", side_effect=NxwrightError("broken")):
            with self.assertRaises(NxwrightError) as raised:
                replace_dump(self.smaller, self.dump)
        self.assertEqual(str(raised.exception), "broken")

    def test_a_dump_folder_that_is_a_link_is_refused_before_anything_changes(self):
        elsewhere = self.folder / "elsewhere"
        elsewhere.mkdir()
        (elsewhere / "notes.txt").write_text("keep", encoding="utf-8")
        (self.dump / "videos").rename(self.folder / "videos-moved")
        try:
            os.symlink(elsewhere, self.dump / "videos", target_is_directory=True)
        except OSError:
            self.skipTest("this system does not allow making a link")
        before = files_in(self.dump)
        with self.assertRaisesRegex(NxwrightError, "is a link to another folder"):
            replace_dump(self.smaller, self.dump)
        self.assertEqual(files_in(self.dump), before)
        self.assertEqual((elsewhere / "notes.txt").read_text(encoding="utf-8"), "keep")

    def test_no_temporary_folder_stays_beside_the_dump(self):
        before = sorted(path.name for path in self.folder.iterdir())
        replace_dump(self.smaller, self.dump)
        self.assertEqual(sorted(path.name for path in self.folder.iterdir()), before)

    def test_a_file_named_differently_only_in_case_gives_one_right_file(self):
        new = self.folder / "new"
        (new / "pages").mkdir(parents=True)
        (new / "pages" / "00-First.txt").write_text("new", encoding="utf-8")
        old = self.folder / "old"
        (old / "pages").mkdir(parents=True)
        (old / "pages" / "00-first.txt").write_text("old", encoding="utf-8")
        replace_dump_files(new, old)
        (file,) = (old / "pages").iterdir()
        self.assertEqual(file.name.lower(), "00-first.txt")
        self.assertEqual(file.read_text(encoding="utf-8"), "new")


class CommandTest(ReplaceDumpTestCase):

    def test_a_dump_into_a_new_folder_needs_no_flag(self):
        code, _ = self.run_command("dump", self.smaller, self.folder / "new")
        self.assertEqual(code, 0)
        self.assertTrue((self.folder / "new" / "project.txt").is_file())

    def test_with_no_terminal_and_no_flag_it_refuses_and_changes_nothing(self):
        before = files_in(self.dump)
        code, said = self.run_command("dump", self.smaller, self.dump)
        self.assertEqual(code, 1)
        self.assertIn("pass --overwrite to replace it", said)
        self.assertEqual(files_in(self.dump), before)

    def test_the_flag_replaces_the_dump(self):
        code, _ = self.run_command("dump", self.smaller, self.dump, "--overwrite")
        self.assertEqual(code, 0)
        self.assertFalse((self.dump / "pages" / "01-second.txt").exists())

    def test_a_folder_that_is_not_a_dump_is_refused_even_with_the_flag(self):
        other = self.folder / "other"
        (other / "pages").mkdir(parents=True)
        (other / "app.toml").write_text("format = 1\n", encoding="utf-8")
        (other / "pages" / "first.nx").write_text("keep", encoding="utf-8")
        before = files_in(other)
        code, said = self.run_command("dump", self.smaller, other, "--overwrite")
        self.assertEqual(code, 1)
        self.assertIn("is not empty", said)
        self.assertEqual(files_in(other), before)

    def test_an_older_project_txt_counts_as_not_a_dump(self):
        (self.dump / "project.txt").write_text("dump format        3\n", encoding="utf-8")
        before = files_in(self.dump)
        code, _ = self.run_command("dump", self.smaller, self.dump, "--overwrite")
        self.assertEqual(code, 1)
        self.assertEqual(files_in(self.dump), before)

    def test_the_prompt_decides(self):
        refuse_unless_replacing(self.dump, lambda question: "y", "dump folder", "written")
        with self.assertRaisesRegex(NxwrightError, "was not replaced; nothing was written"):
            refuse_unless_replacing(self.dump, lambda question: "n", "dump folder", "written")


class DeletionGateTest(unittest.TestCase):
    """refuse_folder_to_delete_from, on paths that never touch the disk."""

    def test_refused(self):
        for path in (PureWindowsPath(""), PureWindowsPath("."), PureWindowsPath(".."),
                     PureWindowsPath("a\\..\\b"), PureWindowsPath("C:\\"), PureWindowsPath("C:"),
                     PureWindowsPath("C:leaf"), PureWindowsPath("\\leaf"),
                     PureWindowsPath("\\\\server\\share"),
                     PureWindowsPath("\\\\server\\share\\"), PurePosixPath(""),
                     PurePosixPath("."), PurePosixPath(".."), PurePosixPath("a/../b"),
                     PurePosixPath("/")):
            with self.subTest(path=repr(path)):
                with self.assertRaises(NxwrightError):
                    refuse_folder_to_delete_from(path)

    def test_allowed(self):
        for path in (PureWindowsPath("dump"), PureWindowsPath(".\\dump"),
                     PureWindowsPath("a\\dump"), PureWindowsPath("C:\\a\\dump"),
                     PureWindowsPath("\\\\server\\share\\dump"), PurePosixPath("dump"),
                     PurePosixPath("./dump"), PurePosixPath("/a/dump")):
            with self.subTest(path=repr(path)):
                refuse_folder_to_delete_from(path)


if __name__ == "__main__":
    unittest.main()
