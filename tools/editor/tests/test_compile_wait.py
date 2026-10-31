"""Waiting for a compile to end, as the tool's compile and tft commands do
(tools/editor/editor.py), against a stand-in for the Editor's Output panel.
It needs neither the Editor nor a window, only the tool's packages."""
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


class CompileWaitTest(unittest.TestCase):

    def stopped(self, panel: str, pressing_failed: list) -> str:
        """Returns the error of a wait that runs out, the Output panel showing
        `panel`, and pressing the button having failed with `pressing_failed`."""
        dedicated = SimpleNamespace(main_handle=1, recorded=SimpleNamespace(pid=1),
                                    stop_on_crash=lambda: None)

        def wait_for(found, seconds, what, stop=None):
            found()
            raise editor.EditorError("waited %d s for %s" % (seconds, what))
        with mock.patch.object(editor.win32gui, "IsWindowEnabled", return_value=True), \
                mock.patch.object(editor, "control_text", return_value=panel), \
                mock.patch.object(editor, "shown_windows", return_value=[]), \
                mock.patch.object(editor, "_wait_for", side_effect=wait_for):
            with self.assertRaises(editor.EditorError) as raised:
                editor._compile_output(dedicated, None, 2, "Compile", pressing_failed)
        return str(raised.exception)

    def test_a_wait_that_runs_out_quotes_the_output_panel(self):
        # A compile that stops on an error the tool does not know as an end
        # writes no last line, so the wait runs out. Its error then gives
        # what the Output panel says, so that the caller sees the Editor's
        # own words.
        self.assertEqual(
            self.stopped("Available Memory:3584\r\nError:a refusal the tool does not know", []),
            "waited %d s for the compile to end. The Output panel says:\n"
            "Available Memory:3584\nError:a refusal the tool does not know"
            % editor.COMPILING_WAIT)

    def test_an_empty_panel_is_not_quoted(self):
        self.assertEqual(self.stopped("", []),
                         "waited %d s for the compile to end" % editor.COMPILING_WAIT)

    def test_a_failed_press_follows_the_panel(self):
        self.assertEqual(self.stopped("Error:x", [OSError("busy")]),
                         "waited %d s for the compile to end. The Output panel says:\nError:x\n"
                         "Pressing Compile failed: OSError('busy')" % editor.COMPILING_WAIT)


if __name__ == "__main__":
    unittest.main()
