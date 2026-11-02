"""Saving the project shown, as the tool's save command does
(tools/editor/editor.py), against stand-ins for the Editor's windows. It
needs neither the Editor nor a window, only the tool's packages."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


class Untouchable:
    """A stand-in for the dedicated Editor that fails any use."""

    def __getattr__(self, name):
        raise AssertionError("the Editor was touched: %s" % name)


class SaveTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())

    def test_an_existing_output_file_is_refused_before_the_editor_is_touched(self):
        output = self.folder / "saved.HMI"
        output.write_bytes(b"someone's project")
        with self.assertRaisesRegex(editor.EditorError, "exists already"):
            editor.save_project(Untouchable(), self.folder, output)
        self.assertEqual(output.read_bytes(), b"someone's project")

    def test_the_command_refuses_an_existing_output_file_before_starting_an_editor(self):
        # Through the command's own path, which starts or attaches to the
        # dedicated Editor for every other command.
        output = self.folder / "saved.HMI"
        output.write_bytes(b"someone's project")
        options = SimpleNamespace(command="save", output=output)
        with mock.patch.object(editor, "dedicated_editor", side_effect=AssertionError(
                "an Editor was started or attached to")), \
                mock.patch.object(editor, "close_if_full", side_effect=AssertionError(
                    "an Editor was looked at")):
            with self.assertRaisesRegex(editor.EditorError, "exists already"):
                editor._run_on_dedicated_editor(options, self.folder)
        self.assertEqual(output.read_bytes(), b"someone's project")

    def test_the_saved_copy_takes_a_name_free_in_the_work_folder(self):
        work = self.folder / "work"
        work.mkdir()
        shown = work / "demo.HMI"
        self.assertEqual(editor._saved_name(work, shown), work / "demo (saved).HMI")
        (work / "demo (saved).HMI").write_bytes(b"")
        self.assertEqual(editor._saved_name(work, shown), work / "demo (saved 2).HMI")


class SaveAsDialogTest(unittest.TestCase):

    def test_the_save_as_dialog_is_a_file_dialog(self):
        # The Open dialog's file name box is control 1148, and the Save As
        # dialog's is control 1001, as the Nextion Editor 1.68.2 shows them.
        for box in (1148, 1001):
            with self.subTest(box=box), \
                    mock.patch.object(editor, "inner_window",
                                      side_effect=lambda handle, kind, number:
                                      7 if (kind, number) == ("Edit", box) else None):
                self.assertTrue(editor._is_file_dialog(mock.Mock(handle=1)))
        with mock.patch.object(editor, "inner_window", return_value=None):
            self.assertFalse(editor._is_file_dialog(mock.Mock(handle=1)))


if __name__ == "__main__":
    unittest.main()
