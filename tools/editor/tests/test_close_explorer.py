"""Closing the Explorer window the Editor opens on the folder of the TFT file
it wrote, as the tool's tft command does (tools/editor/editor.py), against
stand-ins for Windows' shell windows. It needs neither the Editor nor a
window, only the tool's packages."""
from pathlib import Path
import unittest
from unittest import mock

from tools.editor import editor


class _ShellWindow:
    """A stand-in for one of Shell.Application's windows: an Explorer window
    on `location`, or, with `location` None, another kind of shell window,
    which has no LocationURL, so that reading it raises AttributeError, as
    win32com does: "<unknown>.LocationURL"."""

    def __init__(self, handle, location=None):
        self.handle, self.location, self.quit = handle, location, False

    @property
    def HWND(self):
        if self.handle is None:
            raise AttributeError("<unknown>.HWND")
        return self.handle

    @property
    def LocationURL(self):
        if self.location is None:
            raise AttributeError("<unknown>.LocationURL")
        return self.location

    def Quit(self):
        self.quit = True


class CloseExplorerTest(unittest.TestCase):

    def test_a_shell_window_without_a_location_is_skipped(self):
        other = _ShellWindow(1)
        explorer = _ShellWindow(2, "file:///C:/out")
        with mock.patch.object(editor, "_explorer_windows",
                               return_value={1: other, 2: explorer}), \
                mock.patch.object(editor.watchdog, "progress"):
            self.assertTrue(editor._close_explorer_on(Path(r"C:\out"), set()))
        self.assertTrue(explorer.quit)
        self.assertFalse(other.quit)

    def test_a_shell_window_without_a_handle_is_left_out(self):
        listed = [_ShellWindow(None), _ShellWindow(2, "file:///C:/out")]
        shell = mock.Mock()
        shell.Windows.return_value = listed
        with mock.patch.object(editor.win32com.client, "Dispatch", return_value=shell):
            self.assertEqual(editor._explorer_windows(), {2: listed[1]})


if __name__ == "__main__":
    unittest.main()
