"""Closing a message the dedicated Editor shows, as the tool's close-message
command does (tools/editor/editor.py), against stand-ins for the Editor's
windows. It needs neither the Editor nor a window, only the tool's
packages."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from tools.editor import editor


def _message(handle: int, title: str) -> SimpleNamespace:
    """A stand-in for a message window of `handle`, titled `title`."""
    return SimpleNamespace(handle=handle, element_info=SimpleNamespace(name=title))


class CloseMessageTest(unittest.TestCase):

    def close(self, forms: list, dialogs: list, running: bool = True, stays: set = ()) -> tuple:
        """Runs close_message with the Editor showing its own message
        `forms` and the `dialogs`, which are no file dialogs, or which a
        callable `dialogs` gives as _dialogs would. Each window sent
        WM_CLOSE goes, but those in `stays`. Returns what it said, and the
        windows it sent WM_CLOSE."""
        sent = []
        main = SimpleNamespace()
        listed = [] if callable(dialogs) else dialogs
        texts = {window.handle: "text of %d" % window.handle for window in forms + listed}
        found = dialogs if callable(dialogs) else (lambda main, matches=None: dialogs)
        with mock.patch.object(editor, "read_recorded",
                               return_value=SimpleNamespace(pid=7) if running else None), \
                mock.patch.object(editor, "still_running", return_value=running), \
                mock.patch.object(editor, "DedicatedEditor",
                                  return_value=SimpleNamespace(main_window=lambda: main)), \
                mock.patch.object(editor, "_message_forms", return_value=forms), \
                mock.patch.object(editor, "_dialogs", side_effect=found), \
                mock.patch.object(editor, "_words_of", side_effect=lambda w: texts[w.handle]), \
                mock.patch.object(editor.win32gui, "PostMessage",
                                  side_effect=lambda handle, *rest: sent.append(handle)), \
                mock.patch.object(editor.win32gui, "IsWindow",
                                  side_effect=lambda handle: handle in stays), \
                mock.patch.object(editor, "_LOOK_PAUSE", 0), \
                mock.patch.object(editor, "DIALOG_WAIT", 0.01):
            said = editor.close_message(Path("records"))
        return said, sent

    def test_each_message_is_closed_and_its_words_given(self):
        said, sent = self.close([_message(1, "Nextion Editor")], [_message(2, "Open")])
        self.assertEqual(sent, [1, 2])
        self.assertEqual(said, "Closed 2 messages:\n"
                               "- 'Nextion Editor': text of 1\n"
                               "- 'Open': text of 2")

    def test_no_message(self):
        self.assertEqual(self.close([], [])[0], "No message is open.")

    def test_no_editor_running(self):
        self.assertEqual(self.close([], [], running=False),
                         ("The dedicated Editor is not running, so no message is open.", []))

    def test_a_message_that_stays_up_is_said(self):
        said, _ = self.close([_message(1, "Nextion Editor")], [], stays={1})
        self.assertEqual(said, "Closed 0 messages, and 1 stayed open:\n"
                               "- 'Nextion Editor': text of 1 (still open)")

    def test_file_dialogs_are_left_to_close_file_dialog(self):
        # The dialogs close_message asks for are those its filter takes,
        # which is every dialog but a file dialog.
        asked = []
        self.close([], lambda main, matches=None: asked.append(matches) or [])
        file_dialog, message = _message(1, "Open"), _message(2, "Open")
        with mock.patch.object(editor, "_is_file_dialog", side_effect=lambda w: w.handle == 1):
            self.assertEqual([asked[0](window) for window in (file_dialog, message)],
                             [False, True])


if __name__ == "__main__":
    unittest.main()
