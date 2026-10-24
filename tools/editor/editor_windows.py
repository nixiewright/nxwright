"""Listing the dedicated Editor's windows, finding one by its automation
ID, finding one shown over its simulator, telling its crash dialog and its
question to save, finding a file dialog's controls,
reading its component list and its Output panel, a TFT file's size among
it, finding the Explorer windows it opens on a TFT file's folder, and saying
where reading one failed, apart from pywinauto, so that their tests need
neither it nor the Editor (tests/test_editor_windows.py).

As Open is pressed over changes not saved, the Editor asks whether to save
them before its file dialog shows. The question is a window of its own,
owned by the main window, of the automation ID MESSAGE_FORM, as its other
messages are. UI Automation lists only its title, "Confirm", and its
buttons, Yes, No, and Cancel. What it asks is in a rich edit control,
whose text Windows' WM_GETTEXT gives (rich_edit_texts). The main window's
toolbar's Save button is enabled while there are changes not saved.
(Worked out from the Editor 3.1.73.)

The Attribute panel's component list lists the page shown and its
components: "home(Page)", "t0(Text)". On a page not locked, one of them is
always picked: the page itself as the project opens or the page shows, then
the last one picked. Showing the list's drop-down and hiding it unpicked
keeps that one. A page locked in the Editor cannot be shown. A click on its
row in the Page panel shows a padlock in its place. The list then lists the
page's components, as for any page, but picks none of them. (Worked out from
the Editor 3.1.73.)"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import re
import traceback
import urllib.parse
import urllib.request

from _ctypes import COMError

# The automation ID of the Editor's message windows, its question to save among them.
MESSAGE_FORM = "MessageForm"
# What the class name of a rich edit control holds, a Windows Forms one's too.
_RICH_EDIT = "RichEdit"
# What the class name of a button holds, in capitals: "Button" for Windows'
# own, "WindowsForms10.BUTTON.app..." for a Windows Forms one.
_BUTTON = "BUTTON"
_WM_SETTEXT, _WM_GETTEXT, _WM_GETTEXTLENGTH = 0x000C, 0x000D, 0x000E
_user32 = ctypes.WinDLL("user32")
_SMTO_ABORTIFHUNG = 0x0002
_user32.SendMessageTimeoutW.restype = wintypes.LPARAM
_user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                        wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                        ctypes.POINTER(ctypes.c_size_t)]
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_ENUM_WINDOWS = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_user32.EnumChildWindows.argtypes = [wintypes.HWND, _ENUM_WINDOWS, wintypes.LPARAM]
_user32.EnumWindows.argtypes = [_ENUM_WINDOWS, wintypes.LPARAM]
_user32.IsWindowVisible.argtypes = [wintypes.HWND]
_user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
_user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.MonitorFromRect.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD]
_user32.MonitorFromRect.restype = wintypes.HMONITOR
_MONITOR_DEFAULTTONULL = 0
_user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_user32.GetWindow.restype = wintypes.HWND
_user32.GetDlgCtrlID.argtypes = [wintypes.HWND]
_GW_OWNER = 4
# Windows' class of dialogs, the file dialog's among them.
DIALOG_CLASS = "#32770"
# The main window's title, naming the project shown.
_TITLE = re.compile(r"Nextion Editor\((.+)\)")
# How the component list names the page among its items: "home(Page)".
_PAGE_ITEM = "(Page)"
# The title of the window a compile shows while it runs.
PROGRESS_FORM = "progform"
# What the class names hold of a tooltip, a Windows Forms one's too, and of
# the shadow Windows draws under a tooltip or a menu, a window of its own.
_TOOLTIP_OR_SHADOW = ("tooltips_class32", "SysShadow")
# The automation ID of a code editor's word list, as the simulator's
# instruction box opens it as one types. It is kept shown off the screen, and
# moves on it while open, with a tip, a window it owns.
_WORD_LIST = "ListMessage"
# The errors on which the Editor 3.1.73's compile stopped, writing no last
# line: one of its own, after refusing a QR code's temporary need, or a
# command or a system variable the screen's series lacks; and its refusal
# of a video made for another rotation than the project's.
_EDITOR_STOPPED = ("Error:Destination array was not long enough",
                   "The direction of the file is inconsistent with the current engineering "
                   "display direction")
# The last line of the Output panel once a compile has ended: "Compile
# Successful! 0 Errors, 0 Warnings,File Size:790,508", or "Error:Compile
# failed! 1 Errors, 0 Warnings,".
_COMPILE_ENDED = re.compile(r"(Compile Successful!|Error:Compile failed!)")
# The end of that last line once a compile has succeeded: the TFT file's size.
_FILE_SIZE = re.compile(r"Compile Successful!.*File Size:([\d,]+)\s*$")
# The automation ID of the window File > TFT file output shows. Its title is
# "About", in the Editor 3.1.73.
TFT_OUTPUT_FORM = "output"


def window_with_id(windows: list, automation_id: str, info_of):
    """Returns the UI Automation information of the first of `windows` whose
    automation ID is `automation_id`, as `info_of(window)` gives it, or None.
    A window that cannot be read is skipped (windows_matching)."""
    return next(windows_matching(windows, info_of,
                                 lambda info: info.automation_id == automation_id), None)


def sole_window_with_id(windows: list, automation_id: str, info_of):
    """Returns the UI Automation information of the one window of `windows`
    whose automation ID is `automation_id`, or None while there is none, or
    more than one: within one Editor's process, two windows of the main
    window's ID were seen for a moment, while another Editor simulated and
    while `open` opened a project. A window that cannot be read is skipped
    (windows_matching)."""
    found = list(windows_matching(windows, info_of,
                                  lambda info: info.automation_id == automation_id))
    return found[0] if len(found) == 1 else None


def windows_matching(windows: list, info_of=None, matches=None):
    """Yields, in order, `info_of(window)` for each of `windows` for which
    `matches` of it holds, or for each of them when `matches` is None. With
    no `info_of`, it yields the windows themselves.

    A window being made or torn down may raise a COMError when asked for its
    information, or by `matches` when that reads it. Windows were seen to
    beside the simulator's window, and among the Editor's windows right
    after a compile. Such a window is skipped, as it is not the one wanted,
    or not yet: the caller waiting for it looks again."""
    for window in windows:
        try:
            info = window if info_of is None else info_of(window)
            found = matches is None or matches(info)
        except COMError:
            continue
        if found:
            yield info


def shown_windows(pid: int) -> list:
    """Returns the handles of the shown top-level windows of the process
    `pid`, front first, whatever window owns each. UI Automation lists a
    window under its owner, and the Editor's file dialog may belong to a
    hidden window of the Editor's, where a search from the main window
    misses it: Windows' own list holds it."""
    shown = []

    @_ENUM_WINDOWS
    def collect(window, _):
        owner = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == pid and _user32.IsWindowVisible(window):
            shown.append(window)
        return True
    _user32.EnumWindows(collect, 0)
    return shown


def where_raised(error: BaseException) -> str:
    """Returns where in this tool's own code `error` was raised, as
    "function (file.py:line)", its innermost frame there, or "" when it
    passed through none. A Windows or UI Automation error names no window,
    so this says which code was reading one."""
    tool = Path(__file__).resolve().parent
    frames = [frame for frame in traceback.extract_tb(error.__traceback__)
              if Path(frame.filename).resolve().parent == tool]
    if not frames:
        return ""
    return "%s (%s:%d)" % (frames[-1].name, Path(frames[-1].filename).name, frames[-1].lineno)


def class_name(window) -> str:
    """The class name of the window `window`, such as DIALOG_CLASS."""
    name = ctypes.create_unicode_buffer(256)
    _user32.GetClassNameW(window, name, len(name))
    return name.value


def on_a_screen(rectangle: tuple) -> bool:
    """Whether `rectangle`, (left, top, right, bottom) in screen pixels, has
    a size and meets one of the computer's screens. The Editor keeps some
    message windows of its own shown, but parked off every screen."""
    left, top, right, bottom = rectangle
    if right <= left or bottom <= top:
        return False
    place = wintypes.RECT(left, top, right, bottom)
    return bool(_user32.MonitorFromRect(ctypes.byref(place), _MONITOR_DEFAULTTONULL))


def windows_over_simulator(pid: int, simulator, before, info_of) -> list:
    """Returns the handles of the windows the Editor's process `pid` shows on
    a screen (on_a_screen), front first, but for its simulator's window
    `simulator`, its compile's progress window, tooltips and their shadows,
    the instruction box's word list and its tip (_WORD_LIST), and those in
    `before`, such as the windows it showed before the simulator started. A
    tooltip may show as the simulator shows under a resting cursor.
    `info_of(window)` gives a window's UI Automation information, read for
    its automation ID. A window that cannot give it, as one being made or
    torn down, is left out of this look, as it may be the word list: the
    caller's next look tells.

    Such a window, as the simulator's File Header Data Error, waits for an
    answer, and the simulator neither runs nor closes until it has one. The
    simulator's window still took typing meanwhile: such a window does not
    disable it, as a dialog disables the main window. So it is found by its
    showing anew. (Seen in the Nextion Editor whose program reads version
    1.68.2.3035.)"""
    found = []
    for window in shown_windows(pid):
        if window == simulator or window in before or _window_title(window) == PROGRESS_FORM \
                or any(part in class_name(window) for part in _TOOLTIP_OR_SHADOW):
            continue
        place = wintypes.RECT()
        if _user32.GetWindowRect(window, ctypes.byref(place)) and \
                on_a_screen((place.left, place.top, place.right, place.bottom)):
            found.append(window)
    # Typing in the instruction box opens its word list, and Escape closes it:
    # neither the list nor the tip it owns waits for an answer.
    ids = {}
    for window in found:
        try:
            ids[window] = info_of(window).automation_id
        except COMError:
            continue    # being made or torn down: left to the next look
    lists = {window for window, automation_id in ids.items() if automation_id == _WORD_LIST}
    return [window for window in ids if window not in lists
            and _user32.GetWindow(window, _GW_OWNER) not in lists]


def _window_title(window) -> str:
    """The title of the top-level window `window`."""
    title = ctypes.create_unicode_buffer(256)
    _user32.GetWindowTextW(window, title, len(title))
    return title.value


def shown_project(title: str):
    """Returns the project file the main window's `title` names, or None
    when it names none, as before a project is opened."""
    match = _TITLE.fullmatch(title)
    return match[1] if match else None


def is_work_copy(shown, work: Path) -> bool:
    """Whether `shown`, a project file's path or None, is one of the copies
    the tool opens, in its folder `work`: answering No to the question to
    save drops changes to it alone. Windows' paths ignore letter case."""
    if shown is None:
        return False
    folder = os.path.dirname(os.path.abspath(shown))
    return os.path.normcase(folder) == os.path.normcase(os.path.abspath(work))


class NotAnswered(Exception):
    """A window did not answer a message in the time given."""


def rich_edit_texts(handle, seconds: float) -> list:
    """Returns the texts of the rich edit controls in a window, `handle`, in
    the order Windows lists them, read through WM_GETTEXT, which works
    across processes. The Editor's messages say what they ask in one.
    Raises NotAnswered for a control that does not answer within `seconds`,
    so that an Editor that has stopped answering does not hold the caller."""
    return [control_text(control, seconds) for control in _inner_windows(handle)
            if _RICH_EDIT in class_name(control)]


def crash_dialog_shown(pid: int, seconds: float) -> bool:
    """Whether the process `pid` shows .NET's unhandled exception dialog: a
    shown window of its, with Continue and Quit buttons. The buttons' texts
    are read through WM_GETTEXT, which takes milliseconds, where reading them
    through UI Automation took a second or two. .NET writes them with their
    & marks, "&Continue", which are left out. Raises NotAnswered for a button
    that does not answer within `seconds`."""
    for window in shown_windows(pid):
        if {"Continue", "Quit"} <= {control_text(child, seconds).replace("&", "")
                                    for child in _inner_windows(window)
                                    if _BUTTON in class_name(child).upper()}:
            return True
    return False


def control_text(control, seconds: float) -> str:
    """Returns the text of a control, `control`, read through WM_GETTEXT,
    which works across processes. Raises NotAnswered when it does not
    answer within `seconds`."""
    text = ctypes.create_unicode_buffer(_sent(control, _WM_GETTEXTLENGTH, 0, 0, seconds) + 1)
    _sent(control, _WM_GETTEXT, len(text), ctypes.addressof(text), seconds)
    return text.value


def empty_control(control, seconds: float):
    """Empties the text of a control, `control`, through WM_SETTEXT, which
    works across processes. Raises NotAnswered when it does not answer
    within `seconds`."""
    empty = ctypes.create_unicode_buffer("")
    _sent(control, _WM_SETTEXT, 0, ctypes.addressof(empty), seconds)


def _sent(control, message: int, wparam: int, lparam: int, seconds: float) -> int:
    answer = ctypes.c_size_t()
    if not _user32.SendMessageTimeoutW(control, message, wparam, lparam, _SMTO_ABORTIFHUNG,
                                       int(seconds * 1000), ctypes.byref(answer)):
        raise NotAnswered("a control did not answer within %g s" % seconds)
    return answer.value


def compile_ended(output: str) -> bool:
    """Whether the Output panel's text, `output`, says that a compile has
    ended: its last line says it succeeded, or failed."""
    lines = output.strip().splitlines()
    return bool(lines) and _COMPILE_ENDED.match(lines[-1]) is not None


def compiled_file_size(output: str):
    """Returns the size in bytes of the TFT file that the Output panel's text,
    `output`, gives on its last line once a compile has succeeded, or None:
    "Compile Successful! 0 Errors, 11 Warnings,File Size:1,637,140" gives
    1637140."""
    lines = output.strip().splitlines()
    found = _FILE_SIZE.match(lines[-1]) if lines else None
    return None if found is None else int(found[1].replace(",", ""))


def explorer_windows_on(before: set, now: dict, folder: Path) -> list:
    """Returns the Explorer windows of `now`, {window: the file URL of what it
    shows}, that show `folder` and are not among `before`: those the Editor
    opened on the folder it wrote a TFT file in. A window showing no file
    URL, as a search does, is left out."""
    wanted = os.path.normcase(os.path.normpath(folder))
    opened = []
    for window, url in now.items():
        parsed = urllib.parse.urlparse(url)
        if window in before or parsed.scheme != "file":
            continue
        shown = urllib.request.url2pathname(parsed.path)
        if os.path.normcase(os.path.normpath(shown)) == wanted:
            opened.append(window)
    return opened


class CompileWatch:
    """Tells when a compile has ended, from one look at a time at its
    Output panel's text and at whether its progress window, PROGRESS_FORM,
    shows. It has ended once the text's last line says so (compile_ended);
    or, as when the Editor stops on an error and writes no such line, once
    the compile has shown that it ran, and its progress window has gone,
    and the text has stayed as it is for `settled` seconds. It shows that
    it ran by its progress window, or by an error the Editor stops on,
    _EDITOR_STOPPED: a short compile's progress window may come and go
    between two looks."""

    def __init__(self, settled: float = 1.0):
        self.settled = settled
        self._ran = False
        self._text, self._since = None, None

    def look(self, text: str, progress_shown: bool, now: float) -> bool:
        """Takes one look, at the clock's `now`, in seconds. Returns whether
        the compile has ended."""
        if compile_ended(text):
            return True
        self._ran = self._ran or progress_shown or any(stop in text for stop in _EDITOR_STOPPED)
        if text != self._text:
            self._text, self._since = text, now
        return bool(text) and self._ran and not progress_shown \
            and now - self._since >= self.settled


def is_save_question(names: set, buttons: set) -> bool:
    """Whether a message window of the Editor's, the names of whose panes
    and texts are `names`, and of whose buttons `buttons`, is the question to
    save the project shown: titled "Confirm", with Yes, No, and Cancel, and
    no other button. Another question, which might mean otherwise by No, is
    not one."""
    return "Confirm" in names and buttons == {"Yes", "No", "Cancel"}


def listed_page(items: list):
    """Returns the page the component list lists, from its `items`, or None
    when it lists none, as before a project is opened."""
    return next((item[:-len(_PAGE_ITEM)] for item in items if item.endswith(_PAGE_ITEM)),
                None)


def is_locked_listing(items: list, value: str) -> bool:
    """Whether the component list, of `items` and showing `value`, lists a
    locked page: a page's items, with none of them picked, `value` empty."""
    return listed_page(items) is not None and value == ""


def inner_window(window, window_class: str, control_id: int):
    """The first window inside the window `window`, at any depth, of the
    class `window_class` and the control ID `control_id`, or None.

    A Windows file dialog's controls are windows of their own. Its file name
    box is the Edit 1148, and its Open and Cancel buttons are the Buttons 1
    and 2. Windows lists them at once. UI Automation took 0.4 s or more to
    search the dialog, as it also reads the files the dialog lists."""
    return next((child for child in _inner_windows(window)
                 if _user32.GetDlgCtrlID(child) == control_id
                 and class_name(child) == window_class), None)


def _inner_windows(window) -> list:
    """The windows inside the window `window`, at any depth, in the order
    Windows lists them."""
    found = []

    @_ENUM_WINDOWS
    def collect(child, _):
        found.append(child)
        return True
    _user32.EnumChildWindows(window, collect, 0)
    return found
