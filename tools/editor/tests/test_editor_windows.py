"""Finding one of the dedicated Editor's windows by its automation ID, or
one shown over its simulator, and telling its question to save
(tools/editor/editor_windows.py). It needs neither the Editor nor
pywinauto, only Windows, as the tool does."""
from _ctypes import COMError
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import unittest
from unittest import mock

from tools.editor import editor_windows
from tools.editor.editor_windows import (DIALOG_CLASS, PROGRESS_FORM, CompileWatch, NotAnswered,
                                         class_name, compile_ended, compiled_file_size,
                                         control_text, crash_dialog_shown, empty_control,
                                         explorer_windows_on,
                                         inner_window, is_locked_listing, is_save_question,
                                         is_work_copy, listed_page, on_a_screen,
                                         rich_edit_texts, shown_project, shown_windows,
                                         shows_project, sole_window_with_id, where_raised,
                                         window_with_id,
                                         windows_matching, windows_over_simulator)

# The COMError a window being made or torn down gave when its automation ID
# was read, as the tool's simulate stopped with it.
_GONE = COMError(-2146233083, None, (None, None, None, 0, None))
# Windows' window styles.
_WS_POPUP, _WS_CHILD, _WS_VISIBLE = 0x80000000, 0x40000000, 0x10000000


class Info:
    """A window's UI Automation information, as `window_with_id` reads it."""

    def __init__(self, automation_id: str):
        self.automation_id = automation_id


class Unreadable:
    """A window's information whose automation ID cannot be read."""

    @property
    def automation_id(self):
        raise _GONE


def unopenable(window):
    """A window whose information cannot be read at all."""
    raise _GONE


class WindowWithIdTest(unittest.TestCase):

    def test_the_window_with_the_id(self):
        infos = {1: Info("main"), 2: Info("apprun"), 3: Info("apprun")}
        self.assertIs(window_with_id([1, 2, 3], "apprun", infos.__getitem__), infos[2])
        self.assertIsNone(window_with_id([1], "apprun", infos.__getitem__))

    def test_a_window_that_cannot_tell_its_id_is_skipped(self):
        # As a window being made or torn down beside the simulator's: it is
        # not the simulator, and the simulator is still found.
        infos = {1: Unreadable(), 2: Info("apprun")}
        self.assertIs(window_with_id([1, 2], "apprun", infos.__getitem__), infos[2])
        read = {3: Info("apprun")}
        self.assertIs(window_with_id([4, 3], "apprun",
                                     lambda window: read[window] if window in read
                                     else unopenable(window)), read[3])


class SoleWindowWithIdTest(unittest.TestCase):
    """The Editor's main window, found when it alone shows its ID: two were
    seen for a moment, within one Editor's process, while another Editor
    simulated and while `open` opened a project."""

    def test_the_window_alone(self):
        infos = {1: Info("form"), 2: Info("main")}
        self.assertIs(sole_window_with_id([1, 2], "main", infos.__getitem__), infos[2])

    def test_none_while_two_show_or_none(self):
        infos = {1: Info("main"), 2: Info("main")}
        self.assertIsNone(sole_window_with_id([1, 2], "main", infos.__getitem__))
        self.assertIsNone(sole_window_with_id([], "main", infos.__getitem__))

    def test_a_window_being_torn_down_is_skipped(self):
        infos = {1: Unreadable(), 2: Info("main")}
        self.assertIs(sole_window_with_id([1, 2], "main", infos.__getitem__), infos[2])


class WindowsMatchingTest(unittest.TestCase):

    def test_every_window_that_matches(self):
        infos = {1: Info("form"), 2: Info("main"), 3: Info("form")}
        self.assertEqual(list(windows_matching([1, 2, 3], infos.__getitem__,
                                               lambda info: info.automation_id == "form")),
                         [infos[1], infos[3]])
        self.assertEqual(list(windows_matching([1, 2], infos.__getitem__)), [infos[1], infos[2]])
        self.assertEqual(list(windows_matching([1, 2, 3], matches=lambda window: window != 2)),
                         [1, 3])

    def test_a_window_being_made_or_torn_down_is_skipped(self):
        # As the Editor's windows were, right after a compile, while the
        # tool looked for its message forms: one could not be read at all,
        # and one could not tell its ID.
        infos = {1: Unreadable(), 3: Info("form")}
        self.assertEqual(list(windows_matching(
            [1, 2, 3], lambda window: infos[window] if window in infos else unopenable(window),
            lambda info: info.automation_id == "form")), [infos[3]])


class WindowsTestCase(unittest.TestCase):
    """Makes real windows of this process, destroyed after each test."""

    def setUp(self):
        user32 = ctypes.WinDLL("user32")
        self._create = user32.CreateWindowExW
        self._create.restype = wintypes.HWND
        self._create.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                 wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                 wintypes.HINSTANCE, wintypes.LPVOID]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        self._destroy = user32.DestroyWindow

    def create(self, kind: str, text: str, style: int = 0, parent=None, control_id=None):
        """Returns a new window, `parent` its parent or its owner, and
        `control_id` its control ID when it is a child. A shown one is placed
        off the screen, so that no one sees it."""
        window = self._create(0, kind, text, style, -20000, -20000, 200, 100,
                              parent, control_id, None, None)
        self.addCleanup(self._destroy, window)
        return window


class WhereRaisedTest(unittest.TestCase):
    """A Windows or UI Automation error names no window, so the tool says
    where in its own code it was raised."""

    def test_the_tools_innermost_function(self):
        def unreadable(window):
            raise ValueError("gone")
        try:
            window_with_id([1], "apprun", unreadable)
        except ValueError as error:
            where = where_raised(error)
        # window_with_id calls windows_matching, which called `unreadable`.
        self.assertRegex(where, r"^windows_matching \(editor_windows\.py:\d+\)$")

    def test_none_of_its_own(self):
        try:
            raise OSError("elsewhere")
        except OSError as error:
            self.assertEqual(where_raised(error), "")


class ShownWindowsTest(WindowsTestCase):
    """The Editor's file dialog may belong to a hidden window of the
    Editor's, rather than to its main window. Here, this process stands in
    for the Editor."""

    def test_a_dialog_owned_by_a_hidden_window(self):
        hidden_owner = self.create("STATIC", "hidden")
        dialog = self.create(DIALOG_CLASS, "Open", _WS_POPUP | _WS_VISIBLE, hidden_owner)
        self.create(DIALOG_CLASS, "unshown", _WS_POPUP, hidden_owner)
        self.create("STATIC", "shown, no dialog", _WS_POPUP | _WS_VISIBLE)
        dialogs = [window for window in shown_windows(os.getpid())
                   if class_name(window) == DIALOG_CLASS]
        self.assertEqual(dialogs, [dialog])
        self.assertNotIn(hidden_owner, shown_windows(os.getpid()))
        self.assertNotIn(dialog, shown_windows(os.getppid()))


class OnAScreenTest(unittest.TestCase):
    """Whether a window's place meets one of the computer's screens: the
    Editor keeps some message windows of its own parked off every screen."""

    def test_a_place_on_the_first_screen(self):
        # The first screen always holds the point (0, 0).
        self.assertTrue(on_a_screen((0, 0, 200, 100)))

    def test_a_place_off_every_screen(self):
        self.assertFalse(on_a_screen((-20000, -20000, -19800, -19900)))

    def test_a_place_of_no_size(self):
        self.assertFalse(on_a_screen((10, 10, 10, 50)))
        self.assertFalse(on_a_screen((10, 10, 50, 10)))


class WindowsOverSimulatorTest(WindowsTestCase):
    """The windows the Editor shows over its simulator, such as File Header
    Data Error. Here, this process stands in for the Editor. Its windows are
    placed off the screen, so that no one sees them, and on_a_screen is made
    to take any place but in the last test."""

    def over(self, simulator, before, ids=None) -> list:
        """windows_over_simulator, each window's automation ID from `ids`,
        or "" for one it does not give; None for one whose information
        cannot be read, as one being made or torn down."""
        ids = ids or {}
        return windows_over_simulator(os.getpid(), simulator, before,
                                      lambda window: unopenable(window) if window in ids
                                      and ids[window] is None else Info(ids.get(window, "")))

    def test_a_window_shown_anew(self):
        main = self.create("STATIC", "main", _WS_POPUP | _WS_VISIBLE)
        simulator = self.create("STATIC", "simulator", _WS_POPUP | _WS_VISIBLE)
        self.create("STATIC", PROGRESS_FORM, _WS_POPUP | _WS_VISIBLE)
        self.create("STATIC", "unshown", _WS_POPUP)
        message = self.create("STATIC", "", _WS_POPUP | _WS_VISIBLE)
        with mock.patch("tools.editor.editor_windows.on_a_screen", return_value=True):
            self.assertEqual(self.over(simulator, {main}), [message])
            self.assertEqual(self.over(simulator, {main, message}), [])

    def test_no_word_list(self):
        # The instruction box's word list, which typing opens, and the tip it
        # owns: they move on the screen from their place off it, and close
        # at Escape.
        simulator = self.create("STATIC", "simulator", _WS_POPUP | _WS_VISIBLE)
        words = self.create("STATIC", "", _WS_POPUP | _WS_VISIBLE)
        self.create("STATIC", "", _WS_POPUP | _WS_VISIBLE, words)
        message = self.create("STATIC", "", _WS_POPUP | _WS_VISIBLE)
        with mock.patch("tools.editor.editor_windows.on_a_screen", return_value=True):
            self.assertEqual(self.over(simulator, set(), {words: "ListMessage"}), [message])

    def test_one_that_cannot_tell_its_id_left_to_the_next_look(self):
        # It may be the word list, being made: the next look tells.
        simulator = self.create("STATIC", "simulator", _WS_POPUP | _WS_VISIBLE)
        unread = self.create("STATIC", "", _WS_POPUP | _WS_VISIBLE)
        with mock.patch("tools.editor.editor_windows.on_a_screen", return_value=True):
            self.assertEqual(self.over(simulator, set(), {unread: None}), [])
            self.assertEqual(self.over(simulator, set()), [unread])

    def test_no_tooltip(self):
        # As one a toolbar button of the simulator shows under a resting cursor.
        ctypes.WinDLL("comctl32").InitCommonControls()     # registers tooltips_class32
        simulator = self.create("STATIC", "simulator", _WS_POPUP | _WS_VISIBLE)
        self.create("tooltips_class32", "Run all commands", _WS_POPUP | _WS_VISIBLE)
        with mock.patch("tools.editor.editor_windows.on_a_screen", return_value=True):
            self.assertEqual(self.over(simulator, set()), [])

    def test_none_off_every_screen(self):
        # As the message windows the Editor keeps parked.
        simulator = self.create("STATIC", "simulator", _WS_POPUP | _WS_VISIBLE)
        self.create("STATIC", "parked", _WS_POPUP | _WS_VISIBLE)
        self.assertEqual(self.over(simulator, set()), [])


class CrashDialogTest(WindowsTestCase):
    """The Editor's unhandled exception dialog: a shown window of its process
    with Continue and Quit buttons, whose texts .NET writes with their &
    marks. Here, this process stands in for the Editor."""

    def test_a_window_with_continue_and_quit(self):
        dialog = self.create("STATIC", "Microsoft .NET Framework", _WS_POPUP | _WS_VISIBLE)
        self.create("BUTTON", "&Continue", _WS_CHILD, dialog)
        self.create("BUTTON", "&Quit", _WS_CHILD, dialog)
        self.assertTrue(crash_dialog_shown(os.getpid(), 5))

    def test_none_without_both_buttons_shown(self):
        one_button = self.create("STATIC", "one button", _WS_POPUP | _WS_VISIBLE)
        self.create("BUTTON", "&Continue", _WS_CHILD, one_button)
        hidden = self.create("STATIC", "hidden", _WS_POPUP)
        self.create("BUTTON", "Continue", _WS_CHILD, hidden)
        self.create("BUTTON", "Quit", _WS_CHILD, hidden)
        labels = self.create("STATIC", "labels, not buttons", _WS_POPUP | _WS_VISIBLE)
        self.create("STATIC", "Continue", _WS_CHILD, labels)
        self.create("STATIC", "Quit", _WS_CHILD, labels)
        self.assertFalse(crash_dialog_shown(os.getpid(), 5))

    def test_a_window_that_does_not_answer_is_not_it(self):
        # The dialog runs a message loop of its own, so its buttons answer.
        # Here the Editor is busy, as just after it wrote a TFT file.
        busy = self.create("STATIC", "busy", _WS_POPUP | _WS_VISIBLE)
        busy_buttons = {self.create("BUTTON", "&Continue", _WS_CHILD, busy),
                        self.create("BUTTON", "&Quit", _WS_CHILD, busy)}
        answer = editor_windows.control_text

        def control_text(control, seconds):
            if control in busy_buttons:
                raise NotAnswered("a control did not answer within %d s" % seconds)
            return answer(control, seconds)
        with mock.patch.object(editor_windows, "control_text", control_text):
            self.assertFalse(crash_dialog_shown(os.getpid(), 5))
            dialog = self.create("STATIC", "Microsoft .NET Framework", _WS_POPUP | _WS_VISIBLE)
            self.create("BUTTON", "&Continue", _WS_CHILD, dialog)
            self.create("BUTTON", "&Quit", _WS_CHILD, dialog)
            self.assertTrue(crash_dialog_shown(os.getpid(), 5))


class RichEditTextTest(WindowsTestCase):
    """An Editor's message says what it asks in a rich edit control, which
    UI Automation does not list as a text. Here, a window of this process
    holds one, beside a label."""

    def setUp(self):
        super().setUp()
        ctypes.WinDLL("riched20")       # registers the RichEdit20W class
        self.window = self.create("STATIC", "MessageForm")

    def child(self, kind: str, text: str):
        self.create(kind, text, _WS_CHILD, self.window)

    def test_the_text_of_its_rich_edit_controls(self):
        self.child("STATIC", "Confirm")
        self.child("RichEdit20W", "Save the changes to demo.HMI?")
        self.assertEqual(rich_edit_texts(self.window, 5), ["Save the changes to demo.HMI?"])

    def test_none(self):
        self.child("STATIC", "Confirm")
        self.assertEqual(rich_edit_texts(self.window, 5), [])

    def test_one_control_read_and_emptied(self):
        # As the Output panel is emptied before a compile, then read.
        output = self.create("RichEdit20W", "Available Memory:3584", _WS_CHILD, self.window)
        self.assertEqual(control_text(output, 5), "Available Memory:3584")
        empty_control(output, 5)
        self.assertEqual(control_text(output, 5), "")


class CompileEndedTest(unittest.TestCase):
    """The Output panel's last line says whether a compile has ended, as the
    Editor 1.68.2 wrote it."""

    def test_succeeded_or_failed(self):
        self.assertTrue(compile_ended("Available Memory:3584\r\nGlobal Memory:16\r\n"
                                      "Page:page0 Memory Occupied:16+20=36\r\nFile Check Finish"
                                      "\r\nCompile Successful! 0 Errors, 0 Warnings,File Size:"
                                      "368,840\r\n"))
        self.assertTrue(compile_ended("Error:p09.c0.staOut of range\r\n"
                                      "Error:Compile failed! 1 Errors, 0 Warnings,"))

    def test_not_yet(self):
        self.assertFalse(compile_ended(""))
        self.assertFalse(compile_ended("Available Memory:3584\r\nGlobal Memory:16\r\n"))


class CompiledFileSizeTest(unittest.TestCase):
    """The TFT file's size, which the Output panel's last line gives once a
    compile has succeeded, as the Editor 1.68.2 wrote it while writing the
    demo's TFT file."""

    def test_the_size_of_a_compile_that_succeeded(self):
        self.assertEqual(compiled_file_size(
            "Page:settings Memory Occupied:968+5236=6204\r\nFile Check Finish\r\n"
            "Compile Successful! 0 Errors, 11 Warnings,File Size:1,637,140\r\n"), 1637140)

    def test_none_otherwise(self):
        self.assertIsNone(compiled_file_size(""))
        self.assertIsNone(compiled_file_size("Error:p09.c0.staOut of range\r\n"
                                             "Error:Compile failed! 1 Errors, 0 Warnings,"))
        # The size of an earlier line counts for nothing.
        self.assertIsNone(compiled_file_size("Compile Successful! 0 Errors, 0 Warnings,"
                                             "File Size:368,840\r\nError:Compile failed!"))


class ExplorerWindowsOnTest(unittest.TestCase):
    """The Explorer windows the Editor opened on its TFT file's folder: those
    on that folder that were not open before, by their file URLs."""

    def test_those_opened_on_the_folder(self):
        folder = Path(r"C:\Users\dev\tft out")
        now = {1: "file:///C:/Users/dev/tft%20out", 2: "file:///c:/users/DEV/TFT%20OUT",
               3: "file:///C:/Users/dev", 4: ""}
        # 1 was open before. 2 shows the folder, in other letter cases.
        self.assertEqual(explorer_windows_on({1}, now, folder), [2])

    def test_none_when_none_opened(self):
        self.assertEqual(explorer_windows_on(set(), {}, Path(r"C:\out")), [])


class CompileWatchTest(unittest.TestCase):
    """A compile that stops on an error of the Editor's own writes no last
    line, as the Editor 1.68.2 did after refusing a QR code's need, or a
    command: "Error:Destination array was not long enough. ...". Its end
    shows as its progress window goes, or as that error shows, the text then
    staying as it is."""

    ENDED_ON_ITS_OWN = ("Available Memory:3584\r\nGlobal Memory:1624\r\n"
                        "Error:Destination array was not long enough.")

    def test_its_last_line(self):
        self.assertTrue(CompileWatch().look("Compile Successful! 0 Errors", True, 0))

    def test_its_progress_window_gone_and_the_text_settled(self):
        watch = CompileWatch(settled=1)
        self.assertFalse(watch.look("", False, 0))                    # not begun
        self.assertFalse(watch.look("Available Memory:3584", True, 1))
        self.assertFalse(watch.look(self.ENDED_ON_ITS_OWN, False, 2))  # just changed
        self.assertFalse(watch.look(self.ENDED_ON_ITS_OWN, False, 2.5))
        self.assertTrue(watch.look(self.ENDED_ON_ITS_OWN, False, 3))

    def test_no_sign_that_it_ran(self):
        # Neither its progress window nor the Editor's own error: only the
        # last line ends the wait.
        begun = "Available Memory:3584\r\nGlobal Memory:1624"
        watch = CompileWatch(settled=1)
        self.assertFalse(watch.look(begun, False, 0))
        self.assertFalse(watch.look(begun, False, 5))

    def test_a_temporary_need_refused(self):
        # A compile of a few small pages, whose progress window came and went
        # between two looks: the Editor's own error, after it refused a QR
        # code's need, shows that it ran.
        refused = ("Available Memory:3584\r\nGlobal Memory:16\r\n"
                   "Page:p010 Memory Occupied:16+3568=3584\r\nError:Page:p010 The remaining "
                   "memory is not enough to run the temporary use of QR code(-851),please "
                   "decrease the value of txt_maxl to reduce the comsuption of the memory.\r\n"
                   "Error:Destination array was not long enough.")
        watch = CompileWatch(settled=1)
        self.assertFalse(watch.look(refused, False, 0))
        self.assertTrue(watch.look(refused, False, 1))

    def test_commands_refused(self):
        # A basic screen's compile refusing a command and a system variable,
        # as a probe saw it: the Editor's own error after them, and no last
        # line.
        refused = ("Error:Do not support such instruction for this series device:newfile\r\n"
                   "Error:Do not support such variable for this series device:rtc0\r\n"
                   "Error:Destination array was not long enough. Check destIndex and length, "
                   "and the array's lower bounds.")
        watch = CompileWatch(settled=1)
        self.assertFalse(watch.look(refused, False, 0))
        self.assertTrue(watch.look(refused, False, 1))

    def test_a_video_made_for_another_rotation(self):
        # An Intelligent screen's compile refusing a video made for rotation
        # 0 in a project turned to 90 degrees, as a probe saw it: that line
        # alone, and no last line.
        refused = ("Error:Video ID0The direction of the file is inconsistent with the current "
                   "engineering display direction")
        watch = CompileWatch(settled=1)
        self.assertFalse(watch.look(refused, False, 0))
        self.assertTrue(watch.look(refused, False, 1))


class SaveQuestionTest(unittest.TestCase):
    """The Editor's question to save the project shown, as Open is pressed
    over changes not saved, as a probe showed it."""

    WORK = Path(r"C:\Users\dev\AppData\Local\nxwright\editor\work")

    def test_the_project_the_main_window_names(self):
        self.assertEqual(shown_project(r"Nextion Editor(C:\work\demo (2).HMI)"),
                         r"C:\work\demo (2).HMI")
        self.assertIsNone(shown_project("Nextion Editor"))

    def test_the_title_shows_a_project_in_any_case(self):
        # Windows kept an older copy's name, k.HMI, for a copy written as K.HMI.
        title = r"Nextion Editor(%s)" % (self.WORK / "k.HMI")
        self.assertTrue(shows_project(title, self.WORK / "K.HMI"))
        self.assertTrue(shows_project(title, str(self.WORK / "k.HMI")))
        for title, project in ((title, self.WORK / "kk.HMI"), (title, self.WORK / "k"),
                               ("Nextion Editor", self.WORK / "k.HMI")):
            with self.subTest(title=title, project=project):
                self.assertFalse(shows_project(title, project))

    def test_a_copy_in_the_tools_work_folder_is_its_own(self):
        self.assertTrue(is_work_copy(str(self.WORK / "demo (2).HMI"), self.WORK))
        # Windows' paths ignore letter case.
        self.assertTrue(is_work_copy(r"c:\users\DEV\appdata\local\nxwright\editor\WORK\demo.HMI",
                                     self.WORK))
        for other in (r"C:\Projects\demo.HMI", str(self.WORK / "kept" / "demo.HMI"), None):
            with self.subTest(other=other):
                self.assertFalse(is_work_copy(other, self.WORK))

    def test_the_question_to_save(self):
        # Its question itself is not exposed: its title and buttons are.
        self.assertTrue(is_save_question({"Confirm", "X"}, {"Yes", "No", "Cancel"}))
        for names, buttons in (({"Confirm", "X"}, {"Yes", "No"}),
                               ({"Confirm", "X"}, {"Yes", "No", "Cancel", "Help"}),
                               ({"Nextion Editor", "X"}, {"Yes", "No", "Cancel"}),
                               ({"Nextion Editor", "X"}, {"OK"})):
            with self.subTest(names=names, buttons=buttons):
                self.assertFalse(is_save_question(names, buttons))

    def test_the_page_the_component_list_lists(self):
        self.assertEqual(listed_page(["home(Page)", "t0(Text)", ""]), "home")
        # No project open: the list lists nothing.
        self.assertIsNone(listed_page([]))

    def test_a_locked_page_is_listed_with_nothing_picked(self):
        # As the Editor listed a locked page's row clicked: its page and
        # components, none picked, while it showed a padlock in its place.
        items = ["second(Page)", "m0(Hotspot)", ""]
        self.assertTrue(is_locked_listing(items, ""))
        for picked in ("second(Page)", "m0(Hotspot)"):
            with self.subTest(picked=picked):
                self.assertFalse(is_locked_listing(items, picked))
        self.assertFalse(is_locked_listing([], ""))


class InnerWindowTest(WindowsTestCase):
    """A control inside a window, found by its window class and its control
    ID, as a Windows file dialog's are: its file name box is an Edit inside
    a combo box, its Open button a Button of its own."""

    def setUp(self):
        super().setUp()
        self.dialog = self.create("STATIC", "file dialog", _WS_POPUP)

    def test_at_any_depth(self):
        combo = self.create("STATIC", "combo box", _WS_CHILD, self.dialog, 1148)
        box = self.create("EDIT", "", _WS_CHILD, combo, 1148)
        button = self.create("BUTTON", "Open", _WS_CHILD, self.dialog, 1)
        self.assertEqual(inner_window(self.dialog, "Edit", 1148), box)
        self.assertEqual(inner_window(self.dialog, "Button", 1), button)

    def test_none_of_another_class_or_id(self):
        self.create("STATIC", "label", _WS_CHILD, self.dialog, 1)
        self.create("BUTTON", "Cancel", _WS_CHILD, self.dialog, 2)
        self.assertIsNone(inner_window(self.dialog, "Button", 1))


class OwnedWindowsTest(unittest.TestCase):

    def test_a_window_that_closes_as_they_are_listed_is_left_out(self):
        # Window 2 closes once listed: Windows then gives it no owner, as
        # GetWindow does for a handle of no window, and it is left out.
        owners = {1: 100, 2: None, 3: 200, 4: 100}
        user32 = mock.Mock()
        user32.GetWindow.side_effect = lambda window, _: owners[window]
        with mock.patch.object(editor_windows, "shown_windows", return_value=[1, 2, 3, 4]), \
                mock.patch.object(editor_windows, "_user32", user32):
            self.assertEqual(editor_windows.owned_windows(7, 100), [1, 4])


if __name__ == "__main__":
    unittest.main()
