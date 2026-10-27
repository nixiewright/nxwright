"""Opening a project through the file dialog, as the tool's open command
does (tools/editor/editor.py), against stand-ins for the Editor's windows.
It needs neither the Editor nor a window, only the tool's packages."""
from _ctypes import COMError
import _winapi
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor

# The COMErrors UI Automation gave as a busy Editor answered the tool's
# calls in open and tft: an invalid operation, and a time-out.
_INVALID_OPERATION = COMError(-2146233079, None, (None, None, None, 0, None))
_TIME_OUT = COMError(-2146233083, None, (None, None, None, 0, None))


class Flaky:
    """An action that raises `errors` in turn, then returns "done"."""

    def __init__(self, *errors):
        self.errors, self.calls = list(errors), 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "done"


class RetriedWhileBusyTest(unittest.TestCase):

    def test_a_busy_editor_s_errors_are_retried(self):
        action = Flaky(_INVALID_OPERATION, _TIME_OUT)
        with mock.patch.object(editor, "_LOOK_PAUSE", 0):
            self.assertEqual(editor._retried_while_busy(action), "done")
        self.assertEqual(action.calls, 3)

    def test_another_error_is_raised_at_once(self):
        other = COMError(-2147467259, None, (None, None, None, 0, None))
        action = Flaky(other)
        with self.assertRaises(COMError):
            editor._retried_while_busy(action)
        self.assertEqual(action.calls, 1)

    def test_a_busy_error_past_the_wait_is_raised(self):
        action = Flaky(*[_TIME_OUT] * 1000)
        with mock.patch.object(editor, "_LOOK_PAUSE", 0.01), \
                mock.patch.object(editor, "DIALOG_WAIT", 0.05), self.assertRaises(COMError):
            editor._retried_while_busy(action)


class OpenProjectTest(unittest.TestCase):

    def test_a_dialog_left_up_when_the_project_does_not_open_is_cancelled(self):
        # The dialog takes the name and the press of Open, but the project
        # does not open in time: the dialog this command showed is
        # cancelled, as left up it would stop every later command.
        main = SimpleNamespace(window_text=lambda: "Nextion Editor")
        dedicated = SimpleNamespace(stop_on_crash=lambda: None, main_window=lambda: main)
        dialog = object()
        control = SimpleNamespace(set_edit_text=lambda text: None, invoke=lambda: None)

        def wait_for(found, seconds, what, stop=None):
            raise editor.EditorError("waited %d s for %s" % (seconds, what))
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "probe.HMI"
            project.write_bytes(b"")
            with mock.patch.object(editor, "_stop_on_dialog"), \
                    mock.patch.object(editor, "_toolbar_button",
                                      return_value=SimpleNamespace(is_enabled=lambda: False)), \
                    mock.patch.object(editor, "_fresh_copy", return_value=project), \
                    mock.patch.object(editor, "_screen_size", return_value=(320, 480)), \
                    mock.patch.object(editor, "_press_in_background", return_value=[]), \
                    mock.patch.object(editor, "_wait_for_file_dialog", return_value=dialog), \
                    mock.patch.object(editor, "_file_dialog_control", return_value=control), \
                    mock.patch.object(editor, "_is_file_dialog", return_value=True), \
                    mock.patch.object(editor, "_wait_for", side_effect=wait_for), \
                    mock.patch.object(editor, "_drop_other_copies") as drop, \
                    mock.patch.object(editor, "_cancel_file_dialog") as cancel:
                with self.assertRaisesRegex(editor.EditorError, "the project to open"):
                    editor.open_project(dedicated, Path(folder), project)
        cancel.assert_called_once_with(dialog)
        # The copies before it stay, as the Editor may still show one.
        drop.assert_not_called()

    def open_with(self, set_edit_text, invoke, still_up):
        """Runs open_project with the file dialog's name box and Open button
        acting as `set_edit_text` and `invoke`, the dialog up while
        `still_up()` holds, and the project opening at once. Returns the
        stand-in for cancelling the dialog."""
        main = SimpleNamespace(window_text=lambda: "Nextion Editor")
        dedicated = SimpleNamespace(stop_on_crash=lambda: None, main_window=lambda: main)
        control = SimpleNamespace(set_edit_text=set_edit_text, invoke=invoke)
        with tempfile.TemporaryDirectory() as folder:
            project = Path(folder) / "probe.HMI"
            project.write_bytes(b"")
            with mock.patch.object(editor, "_stop_on_dialog"), \
                    mock.patch.object(editor, "_toolbar_button",
                                      return_value=SimpleNamespace(is_enabled=lambda: False)), \
                    mock.patch.object(editor, "_fresh_copy", return_value=project), \
                    mock.patch.object(editor, "_screen_size", return_value=(320, 480)), \
                    mock.patch.object(editor, "_press_in_background", return_value=[]), \
                    mock.patch.object(editor, "_wait_for_file_dialog", return_value=object()), \
                    mock.patch.object(editor, "_file_dialog_control", return_value=control), \
                    mock.patch.object(editor, "_is_file_dialog", side_effect=lambda _: still_up()), \
                    mock.patch.object(editor, "_wait_for", return_value=True), \
                    mock.patch.object(editor, "write_shown"), \
                    mock.patch.object(editor, "_LOOK_PAUSE", 0), \
                    mock.patch.object(editor, "_drop_other_copies") as drop, \
                    mock.patch.object(editor, "_cancel_file_dialog") as cancel:
                self.assertEqual(editor.open_project(dedicated, Path(folder), project), project)
        drop.assert_called_once_with(Path(folder), project)
        return cancel

    def test_a_busy_editor_s_error_typing_the_name_is_retried(self):
        typing = Flaky(_INVALID_OPERATION)
        presses = Flaky()
        cancel = self.open_with(lambda text: typing(), presses, lambda: presses.calls == 0)
        self.assertEqual((typing.calls, presses.calls), (2, 1))
        cancel.assert_not_called()

    def test_a_press_of_open_that_took_is_not_pressed_again(self):
        # The press raises the busy Editor's error, but takes: the dialog
        # closes, and Open is not pressed again.
        presses = Flaky(_TIME_OUT)
        self.open_with(lambda text: None, presses, lambda: presses.calls == 0)
        self.assertEqual(presses.calls, 1)

    def test_a_dialog_closing_as_open_is_found_took_the_press(self):
        # The dialog closes between the look and the press, as an earlier
        # press took: its button is not found, and that is no error.
        presses = Flaky(editor.ElementNotFoundError())
        self.open_with(lambda text: None, presses, lambda: presses.calls == 0)
        self.assertEqual(presses.calls, 1)

    def test_a_press_of_open_that_did_not_take_is_pressed_again(self):
        presses = Flaky(_INVALID_OPERATION)
        self.open_with(lambda text: None, presses, lambda: presses.errors != [] or presses.calls < 2)
        self.assertEqual(presses.calls, 2)


class WorkFolderTest(unittest.TestCase):
    """The copies an open leaves in the work folder, each test in a folder
    of its own that stands in for a dedicated Editor's."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name)
        self.work = self.folder / "work"

    def tearDown(self):
        self.temporary.cleanup()

    def files(self, *names: str) -> list:
        for name in names:
            (self.folder / name).parent.mkdir(parents=True, exist_ok=True)
            (self.folder / name).write_bytes(b"HMI")
        return [self.folder / name for name in names]

    def test_the_other_copies_go(self):
        old, older, shown = self.files("work/demo.HMI", "work/other.hmi", "work/demo (2).HMI")
        editor._drop_other_copies(self.folder, shown)
        self.assertEqual([path.exists() for path in (old, older, shown)], [False, False, True])

    def test_only_its_copies_go(self):
        # Another kind of file, a folder in the work folder, and a project
        # beside it stay.
        kept = self.files("work/notes.txt", "work/sub/inner.HMI", "beside.HMI")
        shown, = self.files("work/demo.HMI")
        editor._drop_other_copies(self.folder, shown)
        self.assertTrue(all(path.exists() for path in kept))

    def test_a_copy_still_held_is_left(self):
        held, shown = self.files("work/held.HMI", "work/demo.HMI")
        unlink = Path.unlink

        def refused(path, *arguments, **keywords):
            if path.resolve() == held.resolve():
                raise PermissionError("held by the Editor")
            return unlink(path, *arguments, **keywords)
        with mock.patch.object(Path, "unlink", refused):
            editor._drop_other_copies(self.folder, shown)
        self.assertTrue(held.exists())

    def test_a_work_folder_that_leads_elsewhere_is_left(self):
        # A junction in its place, to a folder of this test's. Unlinking the
        # junction removes the link alone.
        copy, = self.files("elsewhere/demo.HMI")
        _winapi.CreateJunction(str(copy.parent), str(self.work))
        try:
            editor._drop_other_copies(self.folder, copy.parent / "other.HMI")
            self.assertTrue(copy.exists())
        finally:
            os.unlink(self.work)

    def test_no_work_folder(self):
        editor._drop_other_copies(self.folder, self.work / "demo.HMI")


if __name__ == "__main__":
    unittest.main()
