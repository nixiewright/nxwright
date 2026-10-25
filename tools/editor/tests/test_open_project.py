"""Opening a project through the file dialog, as the tool's open command
does (tools/editor/editor.py), against stand-ins for the Editor's windows.
It needs neither the Editor nor a window, only the tool's packages."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


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
                    mock.patch.object(editor, "_wait_for", side_effect=wait_for), \
                    mock.patch.object(editor, "_cancel_file_dialog") as cancel:
                with self.assertRaisesRegex(editor.EditorError, "the project to open"):
                    editor.open_project(dedicated, Path(folder), project)
        cancel.assert_called_once_with(dialog)


if __name__ == "__main__":
    unittest.main()
