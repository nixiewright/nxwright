"""Drives the dedicated Nextion Editor: the Editor this tool starts, apart
from any the user has open, and reuses at each run (README.md). The
environment variable NXWRIGHT_EDITOR_NAME names it, so that each agent
drives an Editor of its own; with no name, it is the shared one. `status`,
and a command that stops, say which.

    python tools/editor/editor.py open <project.HMI>
    python tools/editor/editor.py screenshot <file.png>
    python tools/editor/editor.py attributes <page> <component>
    python tools/editor/editor.py simulate <file.png> [--send <instruction>] [--touch <steps>]
    python tools/editor/editor.py compile
    python tools/editor/editor.py tft <folder>
    python tools/editor/editor.py catalog <file.json> [--variant <name>] [--known <file.json>]
    python tools/editor/editor.py status
    python tools/editor/editor.py hold <name> [--minutes <n>]
    python tools/editor/editor.py release <name>

Every command but `hold` and `release` takes `--as <name>`, its holder's.
Run it with the tool's own Python (bootstrap.py makes it). Each command takes
the lock on the dedicated Editor first (dedicated.py). While one holder holds
the Editor across its commands, another's are refused, exiting with 3. Actions go through UI
Automation. Where it cannot act, window messages go to the dedicated Editor's
own controls: clicks and scrolls on the Page panel's list and the attribute
grid's rows, the component list's own messages, characters typed in the
simulator's instruction box, and presses on the simulator's screen. Either
way the user's mouse and keyboard are not used, and the user's own Editors
are never touched. A control not
where the tool expects it, a question the Editor asks that this does not
know, or the Editor's crash dialog stops the command, which says what it found.
"""
import argparse
import ctypes
import gc
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import winreg

# Run as a script, so the folder above tools/ is put first on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image  # noqa: E402
from pywinauto import Application, Desktop  # noqa: E402
from pywinauto.application import ProcessNotFoundError  # noqa: E402
from pywinauto.controls.uiawrapper import UIAWrapper  # noqa: E402
from pywinauto.findwindows import ElementAmbiguousError, ElementNotFoundError  # noqa: E402
from pywinauto.timings import TimeoutError as WaitTimeout  # noqa: E402
from pywinauto.uia_defines import IUIA, NoPatternInterfaceError  # noqa: E402
from pywinauto.uia_element_info import UIAElementInfo  # noqa: E402
import pywintypes  # noqa: E402
from _ctypes import COMError  # noqa: E402
import win32com.client  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402
import win32ui  # noqa: E402

from nxwright import NxwrightError  # noqa: E402
from nxwright.project.container import HmiContainer  # noqa: E402
from nxwright.project.device_settings import HEADER_SIZE, read_device_settings  # noqa: E402
from tools.editor.catalog import known_rows, type_name  # noqa: E402
from tools.editor.dedicated import (HOLD_MINUTES, MOST_HOLD_MINUTES, Busy,  # noqa: E402
                                    HoldRefused, Lock, Recorded, Shown, check_hold,
                                    editor_name, editor_words, private_memory,
                                    process_started, read_placement, read_recorded, read_shown,
                                    records_folder, release_hold, renew_hold, standing_hold,
                                    starting_placement, still_running, take_hold,
                                    write_placement, write_recorded, write_shown)
from tools.editor.editor_windows import (DIALOG_CLASS, MESSAGE_FORM,  # noqa: E402
                                         PROGRESS_FORM, TFT_OUTPUT_FORM, CompileWatch,
                                         NotAnswered, class_name, compiled_file_size,
                                         control_text, crash_dialog_shown, empty_control,
                                         explorer_windows_on, inner_window, is_locked_listing,
                                         is_save_question, is_work_copy, listed_page,
                                         rich_edit_texts, shown_project, shows_project,
                                         shown_windows,
                                         sole_window_with_id, where_raised, window_with_id,
                                         windows_matching, windows_over_simulator)
from tools.editor import watchdog  # noqa: E402
from tools.editor.instructions import InstructionError, typed_lines  # noqa: E402
from tools.editor.touches import (Picture, Press, Release, StepError, Wait,  # noqa: E402
                                  parse_steps)

# How long the Editor may take to show its main window, and a dialog, in seconds.
STARTING_WAIT = 90
DIALOG_WAIT = 15
# The automation ID of the Editor's main window.
_MAIN_ID = "main"
# The exit code of a command refused as another holder holds the Editor, so
# that a script may wait and try again. Not 2, which argparse gives a
# command written wrong, that trying again would not mend.
HELD = 3
# How long a project may take to open, in seconds.
OPENING_WAIT = 60
# How long a compile may take, in seconds. One of 250 pages took 4 s.
COMPILING_WAIT = 120
# Where the controls the tool finds lie: the automation IDs of the controls
# from the main window down to each, one level at a time (_found). UI
# Automation finds a control among another's children in about 0.1 s, where
# a search of all the main window's descendants took 1.5 s. The main
# toolbar's ID, gongju0, is the Event panel's toolbar's too, so only its path
# tells the two apart, and it is never searched for by its ID alone.
_TOOLBAR = ("dockSite7", "gongju0")
# The menu bar. Its File menu lists its items only once it is open.
_MENU_BAR = ("dockSite7", "bar5")
# The Output panel's rich edit control, where a compile writes what it
# counted and what it refused.
_OUTPUT_PANEL = ("dockSite4", "bar3", "panelDockContainer7", "textbianyi")
# The Attribute panel, and the Page panel.
_ATTRIBUTE_PANEL = ("dockSite2", "bar4", "panelDockContainer6", "objatt2")
_PAGE_PANEL = ("dockSite2", "bar8", "panelDockContainer2", "pageadmin1")
# How long a wait pauses between two looks, in seconds.
_LOOK_PAUSE = 0.1
# How long the crash check waits for a button to answer, in seconds. The
# crash dialog's buttons answer at once, so a busy Editor costs this at most
# for each of its windows that does not answer, on each look that checks.
_CRASH_CHECK_WAIT = 1
# The most private memory the dedicated Editor may hold as `open` starts, in
# bytes. The Editor is a 32-bit program, and keeps the memory each project
# takes until it ends: one ran out of memory at 1369 MB. A project of 144
# components took about 80 MB an open, and a small one about 6 MB. Past this
# much, `open` starts a fresh Editor. The limit is set late, so that restarts
# are rare, with room left for a few large projects.
MOST_EDITOR_MEMORY = 1100 * 2 ** 20
# How long the Editor may take to end once asked to close, in seconds. It
# took from 2.5 to 7 s.
CLOSING_WAIT = 60
# How a fresh Editor's main window is shown once placed, when the placement
# recorded is maximized or minimized. Minimized, it is not activated, so that
# it takes nothing the user types.
_QUIET_SHOW = {win32con.SW_SHOWMAXIMIZED: win32con.SW_SHOWMAXIMIZED,
               win32con.SW_SHOWMINIMIZED: win32con.SW_SHOWMINNOACTIVE}
# The uninstall entries of the registry, where the Editor's installer records its folder.
_UNINSTALL_KEYS = (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                   r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
# A window's picture drawn as the screen shows it, DirectComposition included.
_PW_RENDERFULLCONTENT = 2
# The control IDs of a Windows file dialog's file name box, its Open button,
# and its Cancel button (editor_windows.inner_window).
_FILE_NAME_BOX, _OPEN_BUTTON, _CANCEL_BUTTON = 1148, 1, 2
# The File menu's item that writes the project's TFT file.
_TFT_MENU_ITEM = "TFT file output"
# In the window that item shows (editor_windows.TFT_OUTPUT_FORM): the box of
# the folder to write in, the Output button, and the label giving the file's
# name, the project's own, ending in .tft.
_TFT_FOLDER_BOX = "1001"
_TFT_OUTPUT_BUTTON = "buttonX2"
_TFT_FILE_NAME = "label1"
# How long the TFT output window may take to show once its menu item is
# pressed, in seconds, before the press is taken for lost; and how many times
# the item is pressed in all (_open_tft_output).
_PRESS_SHOWS = 5
_TFT_PRESSES = 3
# How long the Editor may take to open an Explorer window on the folder once
# it has written the TFT file, in seconds. It took about 2 s.
_EXPLORER_WAIT = 10


class EditorError(Exception):
    """Something the command stops on, and reports."""


class WindowOverSimulator(EditorError):
    """A window the Editor shows over its simulator, waiting for an answer
    (editor_windows.windows_over_simulator). The simulator neither runs nor
    closes until it has one, so both are left for the user."""


def main(arguments=None) -> int:
    """Runs one command, from `arguments` or the command line, under the
    lock. Returns 0, 1 when it stopped, saying why on standard error, or
    HELD when another holder holds the Editor, so that a script may wait."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    holding = argparse.ArgumentParser(add_help=False)
    holding.add_argument("--as", dest="holder", metavar="NAME",
                         help="whose command this is, for a hold across commands")
    opening = commands.add_parser("open", parents=[holding],
                                  help="open a copy of a project in the dedicated Editor")
    opening.add_argument("project", type=Path)
    shot = commands.add_parser("screenshot", parents=[holding],
                               help="a picture of the dedicated Editor's window")
    shot.add_argument("file", type=Path)
    reading = commands.add_parser("attributes", parents=[holding],
                                  help="a component's attributes, values, and "
                                  "hints, as the Editor shows them, as JSON")
    reading.add_argument("page")
    reading.add_argument("component")
    simulating = commands.add_parser("simulate", parents=[holding],
                                     help="a picture of the Editor's simulator, "
                                     "started on the project shown")
    simulating.add_argument("file", type=Path)
    simulating.add_argument("--send", metavar="INSTRUCTION",
                            help="an instruction to run in the simulator before the picture")
    simulating.add_argument("--hex", action="store_true",
                            help="type the instruction's lines as hexadecimal bytes, which the "
                            "simulator sends as they are, without the FF FF FF it ends a line "
                            "with otherwise")
    simulating.add_argument("--touch", metavar="STEPS",
                            help="touches on the simulator's screen, after the instruction: "
                            "steps separated by semicolons, each press X,Y, release, wait MS, "
                            "or picture FILE")
    commands.add_parser("compile", parents=[holding],
                        help="compile the project shown, and print the Editor's Output panel, "
                        "after a line naming the project")
    writing = commands.add_parser("tft", parents=[holding],
                                  help="compile the project shown, and write its TFT file in a "
                                  "folder, through File > TFT file output; print the file's path, "
                                  "then the Editor's Output panel")
    writing.add_argument("folder", type=Path)
    listing = commands.add_parser("catalog", parents=[holding],
                                  help="every attribute of every component of the "
                                  "project shown, with values, hints, and whether code can "
                                  "change it, as JSON")
    listing.add_argument("file", type=Path)
    listing.add_argument("--variant", default="defaults",
                         help="the name the catalog goes by once merged with others")
    listing.add_argument("--known", type=Path, metavar="CATALOG",
                         help="an earlier catalog: the rows whose hint it holds are not clicked")
    commands.add_parser("status", parents=[holding],
                        help="say whether the dedicated Editor runs, what it shows, and who "
                        "holds it")
    commands.add_parser("close-simulator", parents=[holding],
                        help="close a simulator left open in the dedicated Editor")
    commands.add_parser("close-file-dialog", parents=[holding],
                        help="cancel a file dialog left open in the dedicated Editor")
    taking = commands.add_parser("hold", help="hold the dedicated Editor across this holder's "
                                 "commands, refusing anyone else's, until release or its time")
    taking.add_argument("name", help="the holder, whose commands give it with --as")
    taking.add_argument("--minutes", type=int, default=HOLD_MINUTES,
                        help="how long it lasts, renewed by each of its commands: %d at most"
                        % MOST_HOLD_MINUTES)
    releasing = commands.add_parser("release", help="end a hold, given its holder's name")
    releasing.add_argument("name")
    options = parser.parse_args(arguments)
    if getattr(options, "hex", False) and not options.send:
        parser.error("--hex types the lines of --send, which was not given")
    name = editor_name()
    # Every stop names the Editor, so that a command run without the name,
    # which drives the shared Editor, says so.
    stopped = "Stopped, on %s:" % editor_words(name)
    try:
        try:
            folder = records_folder(name)
        except ValueError as error:
            # A name refused names no Editor.
            stopped = "Stopped:"
            raise EditorError(str(error)) from None
        # A call into the Editor that never returns stops the command, and
        # so frees the lock (watchdog.py).
        with Lock(folder, " ".join(sys.argv[1:] if arguments is None else arguments)), \
                watchdog.watched():
            if options.command == "status":
                hold = standing_hold(folder)
                print(status(folder, name) + ("" if hold is None else "\n" + hold.told()))
                return 0
            if options.command == "hold":
                try:
                    hold = take_hold(folder, options.name, options.minutes)
                except ValueError as error:
                    raise EditorError(str(error)) from None
                print(hold.told())
                return 0
            if options.command == "release":
                release_hold(folder, options.name)
                print("No one holds %s" % editor_words(name))
                return 0
            hold = check_hold(folder, options.holder)
            try:
                _run_on_dedicated_editor(options, folder)
            finally:
                # Renewed as it ends too, as a command, such as a catalog,
                # may take longer than the hold's minutes.
                if hold is not None:
                    renew_hold(hold, folder)
        return 0
    except HoldRefused as error:
        print("%s %s; try again once it is released" % (stopped, error), file=sys.stderr)
        return HELD
    except (Busy, EditorError) as error:
        print("%s %s" % (stopped, error), file=sys.stderr)
        return 1
    except (ElementNotFoundError, ElementAmbiguousError, WaitTimeout,
            NoPatternInterfaceError) as error:
        # A control not where the tool expects it: the Editor changed, or
        # shows something else. Its criteria say which control.
        print("%s a control was not found as expected: %s: %s"
              % (stopped, type(error).__name__, error), file=sys.stderr)
        return 1
    except (OSError, RuntimeError, ProcessNotFoundError, pywintypes.error, COMError) as error:
        # Windows' own refusals: a file, a process, a window's picture, or a
        # press UI Automation could not make. They name no window, so the
        # tool's own code reading one is named.
        where = where_raised(error)
        print("%s %s: %s%s" % (stopped, type(error).__name__, error,
                               ", in " + where if where else ""), file=sys.stderr)
        return 1


def _run_on_dedicated_editor(options, folder: Path):
    """Runs the command `options` names, but for status, hold, and release,
    on the dedicated Editor, started if need be, under the lock. close-simulator
    and close-file-dialog start no Editor."""
    if options.command == "close-simulator":
        print(close_simulator(folder))
        return
    if options.command == "close-file-dialog":
        print(close_file_dialog(folder))
        return
    # Before attaching to the Editor, which a fresh one replaces. A path
    # that is no file is refused by open_project, before the Editor is
    # touched.
    if options.command == "open" and options.project.is_file():
        held = close_if_full(folder)
        if held is not None:
            print("Closed the dedicated Editor, which held %d MB; a fresh one opens "
                  "the project" % (held // 2 ** 20))
    editor = dedicated_editor(folder)
    try:
        _run_command(options, editor, folder)
    finally:
        # A fresh Editor takes the placement recorded once the command is
        # done, even one that stopped: given then, it held
        # (give_back_placement).
        if editor.fresh:
            give_back_placement(editor, folder)


def _run_command(options, editor: "DedicatedEditor", folder: Path):
    """Runs the command `options` names, but for status, close-simulator, and
    close-file-dialog, on the dedicated Editor `editor`, printing what it gives."""
    if options.command == "open":
        print("Opened %s" % open_project(editor, folder, options.project))
    elif options.command == "attributes":
        # Hints may be in any language, which Windows' console may not encode.
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(attributes(editor, options.page, options.component),
                         ensure_ascii=False, indent=2))
    elif options.command == "catalog":
        known = set()
        if options.known:
            known = known_rows(json.loads(options.known.read_text(encoding="utf-8")))
        found = catalog(editor, options.variant, known)
        options.file.parent.mkdir(parents=True, exist_ok=True)
        options.file.write_text(json.dumps(found, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        print("Saved %s" % options.file)
    elif options.command == "compile":
        # Page names may be in any language, which Windows' console may not encode.
        sys.stdout.reconfigure(encoding="utf-8")
        project = shown_project(editor.main_window().window_text())
        output = compile_shown(editor)
        print("Compiled %s" % project)
        print(output.replace("\r\n", "\n").rstrip("\n"))
    elif options.command == "tft":
        # Page names may be in any language, which Windows' console may not encode.
        sys.stdout.reconfigure(encoding="utf-8")
        file, output = write_tft(editor, options.folder)
        print("Wrote %s" % file)
        print(output.replace("\r\n", "\n").rstrip("\n"))
    elif options.command == "simulate":
        for picture in simulate(editor, folder, options.file, options.send,
                                options.touch, options.hex):
            print("Saved %s" % picture)
    else:
        screenshot(editor.main_window(), options.file)
        print("Saved %s" % options.file)


class DedicatedEditor:
    """The dedicated Editor, attached to through UI Automation. `fresh` is
    whether this command started it."""

    def __init__(self, recorded: Recorded, fresh: bool = False):
        self.recorded, self.fresh = recorded, fresh
        self.app = Application(backend="uia").connect(process=recorded.pid)
        self.main_handle = None
        self._main_window = None
        self._component_list = None
        # The controls found along their paths, by path (control).
        self._controls = {}

    def main_window(self):
        """The main window's wrapper, once it alone shows its ID
        (sole_window_with_id). It is found once per command, as the
        component list is: each search through UI Automation took some 3.5 s
        beside other Editors, and the Editor keeps one main window for as
        long as it runs."""
        if self._main_window is None:
            info = _wait_for(lambda: sole_window_with_id(
                Desktop(backend="uia").windows(process=self.recorded.pid, visible_only=True),
                _MAIN_ID, lambda window: window.element_info),
                STARTING_WAIT, "the Editor's main window to show alone")
            self.main_handle = info.handle
            self._main_window = self.app.window(handle=self.main_handle).wrapper_object()
        return self._main_window

    def control(self, path: tuple, anywhere: bool = True):
        """The control at the end of `path`, from the main window (_found).
        It is found once per command, as the Editor keeps its panels and
        toolbars for as long as it runs."""
        if path not in self._controls:
            self._controls[path] = _found(self.main_window(), path, anywhere)
        return self._controls[path]

    def component_list(self):
        """The Attribute panel's component list. It is found once per
        command."""
        if self._component_list is None:
            self._component_list = _required(_only_match(
                self.control(_ATTRIBUTE_PANEL), "descendants", automation_id="comboBox1"),
                auto_id="comboBox1")
        return self._component_list

    def stop_if_blocked(self, when: str):
        """Raises EditorError when a window of the Editor's blocks its main
        window: its unhandled exception dialog, or a question it asks. Both
        are modal, so they disable the main window. This check is quick
        enough for every step of a loop: the windows are only looked
        through once the main window is disabled."""
        if self.main_handle is None:
            self.main_window()
        if win32gui.IsWindowEnabled(self.main_handle):
            return
        self.stop_on_crash()
        _stop_on_dialog(self.main_window(), when)
        raise EditorError("a window of the Editor's blocks its main window %s" % when)

    def stop_on_crash(self):
        """Raises EditorError when the Editor shows .NET's unhandled
        exception dialog, a window with Continue and Quit buttons, which the
        user should see and answer (editor_windows.crash_dialog_shown).
        .NET shows that dialog modal, so it disables the main window: while
        the main window is enabled, the dialog cannot show, and is not
        looked for. Windows' own window for a program that has stopped
        working, which a crash outside .NET's handling shows, does not
        disable the main window, and is not looked for either. The dialog
        runs a message loop of its own, so a window whose buttons do not
        answer within _CRASH_CHECK_WAIT, as when the Editor is busy, is not
        it, and is passed over."""
        if self.main_handle is None:
            self.main_window()
        if win32gui.IsWindowEnabled(self.main_handle):
            return
        if crash_dialog_shown(self.recorded.pid, _CRASH_CHECK_WAIT):
            raise EditorError("the Editor shows its unhandled exception dialog; it is "
                              "left open, for whoever reads this to see")


def close_if_full(folder: Path):
    """Closes the dedicated Editor when it holds more than
    MOST_EDITOR_MEMORY, so that the next command starts a fresh one, and
    returns the memory it held, in bytes; else returns None. Only an Editor
    with nothing in the way is closed: no window over its main window, such
    as a question, a dialog, or the simulator, and no changes not saved.
    Otherwise it is left as it is, for the command's own checks to report.

    The Editor ends only once no UI Automation client holds any of its
    elements. Asked to close while this process held one, it ran on until
    the process ended. So the elements read here are let go of first, and
    the close is asked for by window message."""
    recorded = read_recorded(folder)
    if recorded is None or not still_running(recorded):
        return None
    held = private_memory(recorded.pid)
    if held is None or held <= MOST_EDITOR_MEMORY:
        return None
    handle = _closable_main_window(recorded)
    if handle is None:
        return None
    # Its elements went out of use as _closable_main_window returned; a
    # collection lets go of those that refer to each other too.
    gc.collect()
    # The fresh Editor takes the place this one has now (dedicated_editor).
    write_placement(folder, win32gui.GetWindowPlacement(handle))
    win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
    _wait_for(lambda: not still_running(recorded), CLOSING_WAIT, "the Editor to close")
    return held


def _closable_main_window(recorded: Recorded):
    """Returns the handle of the main window of the Editor `recorded` when
    nothing is in the way of closing it (close_if_full), else None. A window
    over the main window is modal, so it disables the main window."""
    editor = DedicatedEditor(recorded)
    main = editor.main_window()
    if not win32gui.IsWindowEnabled(main.handle) or _toolbar_button(editor, "Save").is_enabled():
        return None
    return main.handle


def dedicated_editor(folder: Path) -> DedicatedEditor:
    """Returns the dedicated Editor, started and recorded when the one
    recorded no longer runs, its `fresh` then true. An Editor running
    already has its main window's placement recorded, as the user left it
    (dedicated.py, placement.json), which give_back_placement gives a fresh
    one."""
    recorded = read_recorded(folder)
    fresh = recorded is None or not still_running(recorded)
    if fresh:
        recorded = _start_editor()
        write_recorded(folder, recorded)
    editor = DedicatedEditor(recorded, fresh)
    handle = editor.main_window().handle
    if not fresh:
        seen = win32gui.GetWindowPlacement(handle)
        if seen != read_placement(folder):
            write_placement(folder, seen)
    return editor


def give_back_placement(editor: DedicatedEditor, folder: Path):
    """Gives a fresh Editor's main window the placement recorded, shown as it
    was but not activated where Windows has a way: its own, or the shared
    Editor's while it has none (dedicated.starting_placement). A window
    gone, as when the Editor crashed, is left.

    A fresh Editor shows its window maximized. Leaving that state, its
    window takes back the size it keeps for it, whatever size comes with
    the change: a placement given to the maximized window ended at the
    Editor's own size, while one given to it once restored held. So the
    window is first restored, then placed, then shown as recorded."""
    placement = starting_placement(folder, records_folder())
    handle = editor.main_handle
    if placement is None:
        return
    flags, show, minimized, maximized, normal = placement
    try:
        if win32gui.GetWindowPlacement(handle)[1] == win32con.SW_SHOWMAXIMIZED:
            win32gui.ShowWindow(handle, win32con.SW_SHOWNOACTIVATE)
        win32gui.SetWindowPlacement(handle, (flags, win32con.SW_SHOWNOACTIVATE, minimized,
                                             maximized, normal))
        if show in _QUIET_SHOW:
            win32gui.ShowWindow(handle, _QUIET_SHOW[show])
    except pywintypes.error:
        # The window went away, at any of these steps. Called after a
        # command, this must not hide what the command reported.
        return


def _start_editor() -> Recorded:
    """Starts an Editor, asking Windows not to activate its window. The
    Editor still takes the foreground when it starts, once."""
    program = editor_program()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = win32con.SW_SHOWNOACTIVATE
    process = subprocess.Popen([str(program)], cwd=str(program.parent), startupinfo=startup)
    started = process_started(process.pid)
    if started is None:
        raise EditorError("the Editor ended as it started (%s)" % program)
    return Recorded(process.pid, started, str(program))


def editor_program() -> Path:
    """Returns the Editor's program: NXWRIGHT_EDITOR's, or the one its
    installer recorded in the registry."""
    if os.environ.get("NXWRIGHT_EDITOR"):
        program = Path(os.environ["NXWRIGHT_EDITOR"])
        if not program.is_file():
            raise EditorError("NXWRIGHT_EDITOR names no file: %s" % program)
        return program
    for key_path in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    with winreg.OpenKey(key, winreg.EnumKey(key, index)) as entry:
                        try:
                            if winreg.QueryValueEx(entry, "DisplayName")[0] != "Nextion Editor":
                                continue
                            folder = winreg.QueryValueEx(entry, "InstallLocation")[0]
                        except OSError:
                            continue
                        program = Path(folder) / "Nextion Editor.exe"
                        if program.is_file():
                            return program
        except OSError:
            continue
    raise EditorError("the Nextion Editor is not installed; NXWRIGHT_EDITOR may name its program")


def open_project(editor: DedicatedEditor, folder: Path, project: Path) -> Path:
    """Opens a copy of `project` in the dedicated Editor, through its
    toolbar's Open button and the file dialog, and returns the copy's path.
    Records the copy, with its screen's size, as the project shown
    (dedicated.py, shown.json)."""
    project = project.resolve()
    if not project.is_file():
        raise EditorError("%s is not a file" % project)
    work = folder / "work"
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before pressing Open")
    # Changes not saved make the Editor ask to save them before its file
    # dialog shows (editor_windows.py). The tool never saves: it drops
    # changes to a copy of its own, and leaves anyone else's to them.
    unsaved = _toolbar_button(editor, "Save").is_enabled()
    shown = shown_project(main.window_text())
    if unsaved and not is_work_copy(shown, work):
        raise EditorError("the project shown, %s, has changes not saved, and is not a copy "
                          "this tool opened: save or drop them in the Editor first"
                          % (shown or "which the Editor's title does not name"))
    copy = _fresh_copy(project, work)
    # Read now: once the Editor shows the copy, it lets no one read it.
    screen = _screen_size(copy)
    pressing_failed = _press_in_background(_toolbar_button(editor, "Open"))
    dialog = _wait_for_file_dialog(main, unsaved, pressing_failed)
    try:
        _file_dialog_control(dialog, "Edit", _FILE_NAME_BOX).set_edit_text(str(copy))
        _file_dialog_control(dialog, "Button", _OPEN_BUTTON).invoke()
    except Exception:
        # Left up, the dialog this command showed would stop every later one.
        try:
            _cancel_file_dialog(dialog)
        except (ElementNotFoundError, COMError):
            pass    # already closing: the error that stopped the open is the one to say
        raise
    _wait_for(lambda: _opened(editor, copy), OPENING_WAIT, "the project to open")
    write_shown(folder, Shown(str(copy), screen))
    return copy


def _wait_for_file_dialog(main, unsaved: bool, pressing_failed: list):
    """Waits for the file dialog that pressing Open shows, and returns it.
    When there were changes not saved, `unsaved`, the Editor's question to
    save them, asked before the dialog shows, is answered No, once. Any
    other message of the Editor's stops the command, quoting it,
    unanswered. `pressing_failed` holds what went wrong pressing Open."""
    answered = None
    deadline = time.monotonic() + DIALOG_WAIT
    while time.monotonic() < deadline:
        watchdog.progress()
        file_dialogs = _dialogs(main, _is_file_dialog)
        if file_dialogs:
            return file_dialogs[0]
        for form in _message_forms(main):
            if form.handle == answered:
                continue            # still closing
            names = {part.element_info.name for part in form.descendants()
                     if part.element_info.control_type in ("Pane", "Text")}
            buttons = {button.element_info.name: button
                       for button in form.descendants(control_type="Button")}
            if unsaved and answered is None and is_save_question(names, set(buttons)):
                # No opens the file dialog, which is modal: pressed in the
                # background, as Open is.
                _press_in_background(buttons["No"])
                answered = form.handle
            else:
                raise EditorError("the Editor asks %r: %s; it is left unanswered"
                                  % (form.element_info.name, _words_of(form)))
        time.sleep(_LOOK_PAUSE)
    raise EditorError("waited %d s for the file dialog%s" % (
        DIALOG_WAIT, "; pressing Open failed: %r" % pressing_failed[0]
        if pressing_failed else ""))


def _screen_size(project: Path):
    """The (width, height) of the screen of the project file `project`, at
    its rotation, as its manifest gives them; None when nxwright cannot read
    them, as for a screen model it does not know."""
    try:
        manifest = HmiContainer.from_file(project).blocks.get("main.HMI", b"")
        settings = read_device_settings(manifest) if len(manifest) >= HEADER_SIZE else None
    except (OSError, NxwrightError):
        return None
    return None if settings is None else settings.page_size


def _toolbar_button(editor: DedicatedEditor, name: str):
    """The main toolbar's button named `name`: Open, Debug, and the others.
    It is found by its whole path. Two buttons are named Open: the
    toolbar's, and the component list's drop-down, which crashes the Editor
    when no project is open. And once one is, the Event panel holds a
    toolbar with the main toolbar's ID too, gongju0."""
    def button():
        try:
            toolbar = editor.control(_TOOLBAR, anywhere=False)
        except ElementNotFoundError:
            return None         # not shown yet, as just after the Editor starts
        return _only_match(toolbar, "children", name=name, control_type="Button")
    try:
        return _wait_for(button, DIALOG_WAIT, "the toolbar's %s button" % name)
    except EditorError:
        raise EditorError("the toolbar's %s button was not found" % name) from None


def _press_in_background(button) -> list:
    """Presses `button` through UI Automation, on a thread of its own: a
    button that opens a modal window may answer only once that closes.
    Returns the list where the thread puts what went wrong, if anything, for
    the report."""
    failed = []

    def press():
        try:
            button.invoke()
        except Exception as error:
            failed.append(error)
    threading.Thread(target=press, daemon=True).start()
    return failed


def _fresh_copy(project: Path, work: Path) -> Path:
    """Copies `project` into `work`, over the earlier copy of the same name.
    The Editor keeps the project it shows locked, so when that copy is the
    one shown, the next name free takes it: "demo (2).HMI". Only one
    project is open at a time, so each project needs two names at most."""
    work.mkdir(exist_ok=True)
    # Read first, so that a refusal below is the copy's, not the project's.
    data = project.read_bytes()
    for number in range(1, 10):
        name = project.name if number == 1 else "%s (%d)%s" % (project.stem, number,
                                                               project.suffix)
        try:
            (work / name).write_bytes(data)
            return work / name
        except PermissionError:
            continue
    raise EditorError("no copy of %s could be written in %s" % (project.name, work))


def _opened(editor: DedicatedEditor, copy: Path) -> bool:
    """Whether the main window shows `copy` open, with no dialog left: the
    title alone already names a copy opened again. The Editor asking to
    save the project open before is answered No; any other question it
    asks stops the command, quoting it, as does any message of its own."""
    editor.stop_on_crash()
    main = editor.main_window()
    dialogs = _dialogs(main)
    forms = _message_forms(main)
    if not dialogs and not forms and shows_project(main.window_text(), copy):
        return True
    for form in forms:
        raise EditorError("the Editor asks %r: %s; it is left unanswered"
                          % (form.element_info.name, _words_of(form)))
    # The file dialog may still be closing: it asks nothing. Windows hides a
    # dialog before it destroys its controls, so one without a file name box
    # that no longer shows is a file dialog torn down as it was read.
    for dialog in windows_matching(dialogs, matches=lambda dialog: not _is_file_dialog(dialog)
                                   and _shown(dialog.handle)):
        words = _words_of(dialog)
        buttons = {button.element_info.name: button for button in dialog.children()
                   if button.element_info.control_type == "Button"}
        if "save" in words.lower() and "No" in buttons:
            buttons["No"].invoke()
        else:
            raise EditorError("the Editor asks %r: %s; it is left unanswered"
                              % (dialog.element_info.name, words))
    return False


def _stop_on_dialog(main, when: str):
    """Raises EditorError when a dialog of the Editor's, whatever window
    owns it (_dialogs), or a message of the Editor's over the main window is
    open, such as one a stopped command left: it is shown, unanswered."""
    for dialog in [*_dialogs(main), *_message_forms(main)]:
        raise EditorError("a dialog is open %s, %r: %s; it is left as it is"
                          % (when, dialog.element_info.name, _words_of(dialog)))


def _dialogs(main, matches=None) -> list:
    """The dialogs of the Editor whose main window is `main`: its process's
    shown windows of the dialog class, whatever window owns them, as the
    file dialog may belong to a hidden one (editor_windows.shown_windows).
    With `matches`, those it holds for. One being made or torn down is
    skipped (editor_windows.windows_matching)."""
    return list(windows_matching([handle for handle in shown_windows(main.element_info.process_id)
                                  if class_name(handle) == DIALOG_CLASS], _wrapped, matches))


def _message_forms(main) -> list:
    """The Editor's own message windows over the main window, such as its
    question to save (editor_windows.py): shown windows the main window
    owns, of their automation ID. The others it owns, its docking frames,
    are left out. One being made or torn down is skipped
    (editor_windows.windows_matching)."""
    owned = [handle for handle in shown_windows(main.element_info.process_id)
             if win32gui.GetWindow(handle, win32con.GW_OWNER) == main.handle]
    return list(windows_matching(owned, _wrapped,
                                 lambda form: form.element_info.automation_id == MESSAGE_FORM))


def _wrapped(handle) -> UIAWrapper:
    """The UI Automation wrapper of a window, by its handle. Making it reads
    the window, which may raise a COMError for one being made or torn down."""
    return UIAWrapper(UIAElementInfo(handle))


def _cancel_file_dialog(dialog):
    """Closes a file dialog, `dialog`, as its Cancel button does."""
    _file_dialog_control(dialog, "Button", _CANCEL_BUTTON).invoke()


def _is_file_dialog(dialog) -> bool:
    """Whether `dialog` is a file dialog: it holds a file name box."""
    return inner_window(dialog.handle, "Edit", _FILE_NAME_BOX) is not None


def _file_dialog_control(dialog, window_class: str, control_id: int):
    """The control of the file dialog `dialog` of this window class and
    control ID (editor_windows.inner_window). Raises ElementNotFoundError,
    naming them, when it has none."""
    handle = inner_window(dialog.handle, window_class, control_id)
    if handle is None:
        raise ElementNotFoundError({"class_name": window_class, "control_id": control_id})
    return _wrapped(handle)


def _descendant(window, control_type: str, automation_id: str):
    """The first control of `window` of this type and automation ID, or None."""
    return next((control for control in window.descendants(control_type=control_type)
                 if control.element_info.automation_id == automation_id), None)


def _control(window, control_type: str, automation_id: str):
    """The first control of `window` of this type and automation ID. Raises
    ElementNotFoundError, naming them, when it has none, as a search by
    pywinauto's criteria does."""
    control = _descendant(window, control_type, automation_id)
    if control is None:
        raise ElementNotFoundError({"control_type": control_type, "auto_id": automation_id})
    return control


def _only_match(parent, scope: str, **properties):
    """Returns the one control of `parent`, a wrapper, among its "children"
    or its "descendants" (`scope`), whose UI Automation properties are those
    given: automation_id, name, or control_type, such as "Button". UI
    Automation searches inside Windows, in one call, where pywinauto's
    child_window walks the controls from here, one call each, and took 3.4 s
    to find a toolbar button. Returns None when none matches. Raises
    ElementAmbiguousError when several do, as pywinauto does."""
    iuia = IUIA()
    ids = {"automation_id": iuia.UIA_dll.UIA_AutomationIdPropertyId,
           "name": iuia.UIA_dll.UIA_NamePropertyId,
           "control_type": iuia.UIA_dll.UIA_ControlTypePropertyId}
    conditions = [iuia.iuia.CreatePropertyCondition(
        ids[key], iuia.known_control_types[value] if key == "control_type" else value)
        for key, value in properties.items()]
    condition = conditions[0]
    for other in conditions[1:]:
        condition = iuia.iuia.CreateAndCondition(condition, other)
    found = parent.element_info.element.FindAll(iuia.tree_scope[scope], condition)
    if found.Length > 1:
        raise ElementAmbiguousError("%d controls match %r" % (found.Length, properties))
    return UIAWrapper(UIAElementInfo(found.GetElement(0))) if found.Length else None


def _found(window, path: tuple, anywhere: bool = True):
    """Returns the control at the end of `path`, the automation IDs of the
    controls from `window`, a wrapper, down to it: each step the one child of
    the control before with its ID (_only_match). The Editor's panels can be
    docked elsewhere, as every Nextion Editor of the Windows user shares its
    layout. So when a step finds no such child, and `anywhere` is true, the
    control is searched for by its own ID among all of `window`'s
    descendants, which is slower. Raises ElementNotFoundError when there is
    none, and ElementAmbiguousError when several match."""
    control = window
    for automation_id in path:
        control = _only_match(control, "children", automation_id=automation_id)
        if control is None:
            break
    else:
        return control
    if not anywhere:
        raise ElementNotFoundError({"auto_id": automation_id})
    return _required(_only_match(window, "descendants", automation_id=path[-1]),
                     auto_id=path[-1])


def _required(control, **criteria):
    """Returns `control`, which a search found, or raises
    ElementNotFoundError, naming the `criteria` it was searched by, when it
    found none."""
    if control is None:
        raise ElementNotFoundError(criteria)
    return control


def _words_of(dialog) -> str:
    """The texts a dialog or a message of the Editor's shows, joined: those
    UI Automation lists, then those of its rich edit controls, which say
    what a message asks (editor_windows.py)."""
    texts = [text.element_info.name for text in dialog.descendants(control_type="Text")]
    try:
        texts += rich_edit_texts(dialog.handle, DIALOG_WAIT)
    except NotAnswered as error:
        raise EditorError("the Editor did not answer a window message: %s" % error) from None
    return " ".join(text for text in texts if text)


def _wait_for(found, seconds: float, what: str, stop=None):
    """Returns found()'s first true result within `seconds`, or raises
    EditorError. `stop`, when given, is called before each look, and raises
    to end the wait sooner, as when a window shows over the simulator."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        watchdog.progress()
        if stop is not None:
            stop()
        result = found()
        if result:
            return result
        time.sleep(_LOOK_PAUSE)
    raise EditorError("waited %d s for %s" % (seconds, what))


def screenshot(window, file: Path):
    """Saves a picture of `window` as PNG, drawn by the window itself, so
    that windows over it do not show. A minimized window is first restored,
    without being activated."""
    file.parent.mkdir(parents=True, exist_ok=True)
    _picture(window.handle)[0].save(file)


def _picture(handle: int):
    """Returns a picture of a window, drawn by the window itself, and the
    window's top left corner on the screen, (image, left, top)."""
    if win32gui.IsIconic(handle):
        win32gui.ShowWindow(handle, win32con.SW_SHOWNOACTIVATE)
    left, top, right, bottom = win32gui.GetWindowRect(handle)
    width, height = right - left, bottom - top
    window_dc = win32gui.GetWindowDC(handle)
    source = win32ui.CreateDCFromHandle(window_dc)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        if not ctypes.windll.user32.PrintWindow(handle, memory.GetSafeHdc(),
                                                _PW_RENDERFULLCONTENT):
            raise EditorError("Windows could not draw the window's picture")
        image = Image.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True),
                                 "raw", "BGRX", 0, 1)
        return image, left, top
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(handle, window_dc)


# The Page panel's list, at 96 DPI: each page a row this high, the first's
# centre this far below the list's top, clicked this far from its left (seen
# on the Editor 3.1.73). The list shows UI Automation no items, so a page is
# picked by a click at its row.
_PAGE_ROW = 20
_PAGE_FIRST = 10
_PAGE_X = 40
# How long a posted click may take to show its page, or its hint, in seconds.
_SHOW_WAIT = 1.0
# A mouse wheel's notch, as Windows counts it.
_WHEEL_NOTCH = 120
# How long a value read must hold still to be taken as final, in seconds.
_SETTLE = 0.2
# How long the tool waits after posting a press or a release to the
# simulator's screen, in seconds. A press and its release posted 1 ms apart
# ran nothing; 5 ms apart or more ran as a tap.
_TOUCH_PAUSE = 0.05


def attributes(editor: DedicatedEditor, page: str, component: str) -> dict:
    """Returns the attributes of `component` of `page` in the project the
    dedicated Editor shows, as its Attribute panel shows them: {"page",
    "component", "type", "attributes": [{"name", "value", "hint"}]}. The
    page's own attributes come with `component` the page's name."""
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before reading attributes")
    if "(" not in main.window_text():
        # The component list crashes the Editor when no project is open.
        raise EditorError("no project is open; open one first")
    show_page(editor, page)
    kind = pick_component(editor, component)
    return {"page": page, "component": component, "type": kind,
            "attributes": _grid_rows(editor)}


def show_page(editor: DedicatedEditor, page: str):
    """Shows `page`. When the component list lists it, it is shown already.
    Otherwise clicks are posted on the Page panel's list, row by row, until
    the component list names it: a click on the page shown changes nothing,
    but the page wanted is not that one. A page locked in the Editor cannot
    be shown (editor_windows.py), so it is refused, saying so."""
    _refuse_if_locked(editor, page)
    if _page_shown(editor) == page:
        return
    places = _page_places(editor)
    for place in places:
        editor.stop_if_blocked("while showing page %r" % page)
        if place is None:
            raise EditorError("page %r is past the Page panel's rows in sight; "
                              "scrolling the list is not done yet" % page)
        if _click_page(editor, place) == "%s(Page)" % page:
            return
        _refuse_if_locked(editor, page)
    raise EditorError("the project has no page %r among its %d" % (page, len(places)))


def _refuse_if_locked(editor: DedicatedEditor, page: str):
    """Raises EditorError when the component list lists `page` locked."""
    items = _component_names(editor.component_list().element_info.handle)
    if listed_page(items) == page and is_locked_listing(items, _component_value(editor)):
        raise EditorError("page %r is locked in the Editor, which shows a padlock in its place "
                          "and picks none of its components until it is unlocked" % page)


def _page_places(editor: DedicatedEditor) -> list:
    """Where to click each page's row in the Page panel's list: (the list's
    window, x, y) for each page, in order, or None for a row past those in
    sight."""
    panel = editor.control(_PAGE_PANEL)
    page_list = _required(_only_match(panel, "descendants", automation_id="colListBox1"),
                          auto_id="colListBox1")
    # The panel's bar ends with the number of pages.
    bar = _required(_only_match(panel, "descendants", automation_id="bar1"),
                    auto_id="bar1").children()
    counted = bar[-1].element_info.name if bar else ""
    if not counted.isdigit():
        raise EditorError("the Page panel's bar shows %r where its page count was" % counted)
    handle = page_list.element_info.handle
    scale = ctypes.windll.user32.GetDpiForWindow(handle) / 96
    height = page_list.element_info.rectangle.height()
    places = []
    for row in range(int(counted)):
        y = round((_PAGE_FIRST + row * _PAGE_ROW) * scale)
        places.append((handle, round(_PAGE_X * scale), y) if y < height else None)
    return places


def _click_page(editor: DedicatedEditor, place) -> str:
    """Posts a click on a page's row, and returns what the component list
    shows once it settles: "home(Page)" when the page shows."""
    before = _component_value(editor)
    _post_click(*place)
    return _wait_for_change(lambda: _component_value(editor), before, _SHOW_WAIT)


def _page_shown(editor: DedicatedEditor) -> str:
    """The page shown: the one page among the component list's items."""
    return listed_page(_component_names(editor.component_list().element_info.handle))


def pick_component(editor: DedicatedEditor, component: str) -> str:
    """Picks `component` of the page shown in the Attribute panel's
    component list, and returns its type, as the list names it ("Text").

    UI Automation can only show the list by its Open button, and that brings
    the Editor in front of the user's window. So the list is shown and
    scrolled by its own messages. A click posted on the item then picks it,
    and commits the pick as a user's click does."""
    combo = editor.component_list()
    handle = combo.element_info.handle
    names = _component_names(handle)
    index = next((index for index, name in enumerate(names)
                  if name.split("(")[0] == component), None)
    if index is None:
        raise EditorError("the page shown has no component %r" % component)
    _sent(handle, win32con.CB_SHOWDROPDOWN, 1)
    try:
        # The drop-down list is the combo box's child only while it shows.
        dropped = _wait_for(lambda: next((child for child in combo.children()
                                          if child.element_info.control_type == "List"), None),
                            DIALOG_WAIT, "the component list to show")
        list_handle = dropped.element_info.handle
        _sent(list_handle, win32con.LB_SETTOPINDEX, index)

        def in_sight():
            # A list just dropped may not have its place yet.
            item = next((item for item in dropped.children()
                         if item.element_info.name == names[index]), None)
            area = dropped.element_info.rectangle
            place = item.element_info.rectangle if item else None
            if place and place.height() > 0 and area.top <= place.top \
                    and place.bottom <= area.bottom:
                return place
            return None
        place = _wait_for(in_sight, DIALOG_WAIT,
                          "the component list's item %r to come into sight" % names[index])
        x, y = win32gui.ScreenToClient(list_handle, ((place.left + place.right) // 2,
                                                     (place.top + place.bottom) // 2))
        _post_click(list_handle, x, y)

        def picked():
            # Committing a pick is where the Editor is known to crash.
            editor.stop_if_blocked("while picking component %r" % component)
            if _sent(handle, win32con.CB_GETDROPPEDSTATE):
                return None
            value = _component_value(editor)
            return value if value.startswith(component + "(") else None
        value = _wait_for(picked, DIALOG_WAIT, "the component to show")
    except BaseException:
        # A pick not made can leave the list showing. Hiding it by its
        # message cancels the pick. The error reported is the one that
        # stopped the pick, even when the list cannot be hidden.
        try:
            if _sent(handle, win32con.CB_GETDROPPEDSTATE):
                _sent(handle, win32con.CB_SHOWDROPDOWN, 0)
        except EditorError:
            pass
        raise
    return value[len(component) + 1:-1]


def _component_value(editor: DedicatedEditor) -> str:
    """What the component list shows: "title(Text)"."""
    return editor.component_list().iface_value.CurrentValue


def _component_names(handle: int) -> list:
    """The component list's items, as it names them ("title(Text)"), read by
    its own messages while it stays hidden."""
    names = []
    for index in range(_sent(handle, win32con.CB_GETCOUNT)):
        length = _sent(handle, win32con.CB_GETLBTEXTLEN, index)
        if length < 0:
            raise EditorError("the component list changed while it was read")
        text = ctypes.create_unicode_buffer(length + 1)
        _sent(handle, win32con.CB_GETLBTEXT, index, ctypes.addressof(text))
        names.append(text.value)
    return names


def _sent(handle: int, message: int, wparam: int = 0, lparam: int = 0) -> int:
    """Sends a message to one of the dedicated Editor's controls, and returns
    its answer. An Editor that does not answer within DIALOG_WAIT stops the
    command, rather than hold it."""
    try:
        _, answer = win32gui.SendMessageTimeout(handle, message, wparam, lparam,
                                                win32con.SMTO_ABORTIFHUNG, DIALOG_WAIT * 1000)
    except pywintypes.error as error:
        raise EditorError("the Editor did not answer a window message: %s" % error.strerror)
    # The answer comes unsigned; the combo box's error answer is -1.
    return ctypes.c_ssize_t(answer).value


def catalog(editor: DedicatedEditor, variant: str, known: set) -> dict:
    """Reads every component of every page of the project shown, the pages
    themselves included, as `attributes` does, into a catalog named
    `variant` (catalog.py), which also names the project's file, from the
    main window's title. `known` holds (type name, attribute) pairs whose
    hint is read already: their rows are not clicked."""
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before reading the catalog")
    if "(" not in main.window_text():
        # The component list crashes the Editor when no project is open.
        raise EditorError("no project is open; open one first")
    objects = []
    for number, place in enumerate(_page_places(editor)):
        editor.stop_if_blocked("while showing page %d" % number)
        if place is None:
            raise EditorError("page %d is past the Page panel's rows in sight; scrolling the "
                              "list is not done yet" % number)
        _click_page(editor, place)
        page = _page_shown(editor)
        _refuse_if_locked(editor, page)
        for item in _component_names(editor.component_list().element_info.handle):
            if not item:
                continue
            component = item.split("(")[0]
            pick_component(editor, component)
            entry = {"page": page, "component": component, "type": _grid_type(editor)}
            name = type_name(entry)
            entry["attributes"] = _grid_rows(editor, {attribute for type_known, attribute
                                                      in known if type_known == name})
            objects.append(entry)
            print("Read %s %s" % (page, component), file=sys.stderr, flush=True)
    title = main.window_text()
    return {"variant": variant, "project": title[title.index("(") + 1:title.rindex(")")],
            "objects": objects}


def _grid_type(editor: DedicatedEditor) -> int:
    """The number the component shown stores as its type: the value of the
    grid's row named type, its first."""
    grid, _, numbers = _grid(editor)
    cells = grid.children()[numbers[0]].children() if numbers else []
    if len(cells) < 2 or cells[0].iface_value.CurrentValue != "type":
        raise EditorError("the attribute grid's first row is not the component's type")
    shown = cells[1].iface_value.CurrentValue
    if not shown.isdigit():
        raise EditorError("the attribute grid shows the type %r, not a number" % shown)
    return int(shown)


def _grid_rows(editor: DedicatedEditor, known=()) -> list:
    """Each row of the attribute grid: its name, its value, whether code can
    change it, and the hint the Editor shows once a click is posted on its
    name. A row whose name is in `known` is not clicked, and has no hint. A
    row out of sight is scrolled into it first, by mouse wheel messages
    posted to the grid.

    Whether code can change an attribute shows in its name's colour, read
    before the row is clicked. The row clicked last shows white on blue
    instead, so its colour is read once another row has been clicked."""
    grid, hint_box, numbers = _grid(editor)
    handle = grid.element_info.handle
    rows = []
    for number in numbers:
        editor.stop_if_blocked("while reading the attribute grid")
        name_cell = _wait_for(lambda: _in_sight(grid, number), DIALOG_WAIT,
                              "row %d to come into sight" % number)
        name = name_cell.iface_value.CurrentValue
        colour = _name_colour(editor, name_cell)
        hint = None
        if name not in known:
            before = hint_box.iface_value.CurrentValue
            _post_click(handle, *_centre_in(handle, name_cell))
            hint = _wait_for_change(lambda: hint_box.iface_value.CurrentValue, before,
                                    _SHOW_WAIT)
        rows.append({"name": name,
                     "value": grid.children()[number].children()[1].iface_value.CurrentValue,
                     "hint": hint, "code_can_change": colour})
    # At most one row showed white on blue, being the one clicked last.
    waiting = [(row, number) for row, number in zip(rows, numbers)
               if row["code_can_change"] is None]
    if waiting and len(numbers) < 2:
        raise EditorError("the attribute grid's one row shows white on blue, so its name's "
                          "colour cannot be read")
    for row, number in waiting:
        # The row next to it, which is in sight too.
        place = numbers.index(number)
        other = numbers[place - 1] if place > 0 else numbers[place + 1]
        other_cell = _wait_for(lambda: _in_sight(grid, other), DIALOG_WAIT,
                               "row %d to come into sight" % other)
        _post_click(handle, *_centre_in(handle, other_cell))
        name_cell = _wait_for(lambda: _in_sight(grid, number), DIALOG_WAIT,
                              "row %d to come into sight" % number)

        def shown(cell=name_cell):
            # In a list, so that False, a black name, counts as found.
            colour = _name_colour(editor, cell)
            return None if colour is None else [colour]
        row["code_can_change"] = _wait_for(shown, DIALOG_WAIT, "row %s to show its name's "
                                           "colour" % row["name"])[0]
    return rows


def _grid(editor: DedicatedEditor):
    """The attribute grid, its hint box, and the indexes of its attribute
    rows among its children: those named "Row 0", "Row 1", and so on. Some
    components' grids also have a header row, which is not one."""
    panel = editor.control(_ATTRIBUTE_PANEL)
    grid = _required(_only_match(panel, "descendants", automation_id="dataGridView1"),
                     auto_id="dataGridView1")
    hint_box = _required(_only_match(panel, "descendants", automation_id="textBox1"),
                         auto_id="textBox1")
    numbers = [index for index, child in enumerate(grid.children())
               if re.fullmatch(r"Row \d+", child.element_info.name or "")]
    return grid, hint_box, numbers


def _centre_in(handle: int, cell):
    """The centre of a grid's cell, in the grid window's client area."""
    rectangle = cell.element_info.rectangle
    return win32gui.ScreenToClient(handle, ((rectangle.left + rectangle.right) // 2,
                                            (rectangle.top + rectangle.bottom) // 2))


def _name_colour(editor: DedicatedEditor, name_cell):
    """Whether an attribute's name, in the grid, shows green, which code can
    change, or black, which it cannot: True or False. None when the row shows
    white on blue, as the row clicked last does. A name neither green nor
    black, as a covered window would give, stops the command."""
    image, left, top = _picture(editor.main_handle)
    place = name_cell.element_info.rectangle
    # Inside the cell's borders.
    pixels = list(image.crop((place.left - left + 1, place.top - top + 1,
                              place.right - left - 1, place.bottom - top - 1))
                  .get_flattened_data())
    selected = sum(1 for red, green, blue in pixels if blue > 150 and red < 100)
    if selected * 2 > len(pixels):
        return None
    greens = sum(1 for red, green, blue in pixels
                 if green > 90 and green > red + 50 and green > blue + 50)
    blacks = sum(1 for red, green, blue in pixels if max(red, green, blue) < 90)
    if greens > blacks:
        return True
    if blacks > greens:
        return False
    raise EditorError("the attribute %r's name shows neither green nor black"
                      % name_cell.iface_value.CurrentValue)


def _in_sight(grid, number: int):
    """Returns row `number`'s name cell when the grid shows it whole, or
    else posts a notch of the mouse wheel to the grid, towards the row, and
    returns None. A row out of sight may have no place at all, above the
    rows in sight or below them: which one shows from the rows in sight."""
    children = grid.children()
    area = grid.element_info.rectangle

    def whole(index: int) -> bool:
        cell = children[index].children()[0].element_info.rectangle
        return cell.height() > 0 and area.top <= cell.top and cell.bottom <= area.bottom
    if whole(number):
        return children[number].children()[0]
    above = next((index for index in range(len(children))
                  if re.fullmatch(r"Row \d+", children[index].element_info.name or "")
                  and whole(index)), len(children)) > number
    notch = _WHEEL_NOTCH if above else -_WHEEL_NOTCH
    centre = _packed((area.left + area.right) // 2, (area.top + area.bottom) // 2)
    win32gui.PostMessage(grid.element_info.handle, win32con.WM_MOUSEWHEEL, _packed(0, notch),
                         centre)
    return None


def _post_click(handle: int, x: int, y: int):
    """Posts a left click at (x, y) of a window's client area: messages only,
    so the user's mouse does not move."""
    position = _packed(x, y)
    win32gui.PostMessage(handle, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, position)
    win32gui.PostMessage(handle, win32con.WM_LBUTTONUP, 0, position)


def _packed(low: int, high: int) -> int:
    """Packs two 16-bit numbers into a message's parameter, as Windows does:
    screen coordinates may be negative, on a monitor left of or above the
    main one, so each keeps its 16 bits as they are."""
    return ((high & 0xFFFF) << 16) | (low & 0xFFFF)


def _wait_for_change(read, before, seconds: float):
    """Returns read()'s value once it differs from `before` and has held
    still for _SETTLE seconds, or after `seconds` as it is: a hint may be
    the same as the row before's. The Editor writes some hints in two
    steps, the type's name first, so the first change is not the last."""
    deadline = time.monotonic() + seconds
    value = read()
    while value == before and time.monotonic() < deadline:
        watchdog.progress()
        time.sleep(0.05)
        value = read()
    settled = time.monotonic() + _SETTLE
    while time.monotonic() < settled:
        watchdog.progress()
        time.sleep(0.05)
        latest = read()
        if latest != value:
            value, settled = latest, time.monotonic() + _SETTLE
    return value


def simulate(editor: DedicatedEditor, folder: Path, file: Path, instruction: str = None,
             touches: str = None, hex_mode: bool = False) -> list:
    """Starts the Editor's simulator on the project shown, by the toolbar's
    Debug button. Sends it `instruction`, if given, as hexadecimal bytes
    when `hex_mode` (instructions.py), then touches its screen as the steps
    `touches` lists (touches.py), if given, then saves a picture of the
    simulator's window as `file`, and closes the simulator. Returns the
    pictures saved, the steps' and `file`, in order.

    The instruction's lines are checked before the simulator starts. So are
    the steps, against the screen's size `open` recorded for the project
    shown (`folder`'s shown.json).

    A window shown over the simulator once it shows, waiting for an answer,
    stops the command at once (WindowOverSimulator), and is left open with
    the simulator."""
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before pressing Debug")
    if "(" not in main.window_text():
        raise EditorError("no project is open; open one first")
    if instruction:
        try:
            typed_lines(instruction, hex_mode)
        except InstructionError as error:
            raise EditorError("--send: %s" % error) from None
    screen_size = steps = None
    if touches:
        screen_size = _shown_screen_size(folder, main)
        try:
            steps = parse_steps(touches, screen_size)
        except StepError as error:
            raise EditorError("--touch: %s" % error) from None
    if _simulator(editor) is not None:
        raise EditorError("a simulator is open already; it is left as it is: the "
                          "close-simulator command closes it")
    shown_before = frozenset(shown_windows(editor.recorded.pid))
    pressing_failed = _press_in_background(_toolbar_button(editor, "Debug"))

    def shown():
        simulator = _simulator(editor)
        if simulator is None and not win32gui.IsWindowEnabled(editor.main_handle):
            # The compile's progress window disables the main window too.
            editor.stop_on_crash()
            _stop_on_dialog(main, "while starting the simulator")
        return simulator
    try:
        simulator = _wait_for(shown, OPENING_WAIT, "the simulator (a compile that fails shows "
                              "none; the Editor's Output panel then says why)")
    except BaseException as error:
        # A simulator left open would make the next simulate refuse to start.
        _close_simulator_left(editor, shown_before)
        if pressing_failed and isinstance(error, EditorError):
            raise EditorError("%s; pressing Debug failed: %r" % (error, pressing_failed[0]))
        raise

    # Each wait on the simulator stops on a window shown over it since Debug.
    def watch():
        _stop_on_window_over(simulator, shown_before)
    try:
        # The simulator drops a close asked for while it starts. Its own
        # toolbar shows once it has started.
        _wait_for(lambda: _child(simulator, "bar1"), DIALOG_WAIT, "the simulator to start",
                  watch)
        if instruction:
            _send(simulator, instruction, hex_mode, stop=watch)
        saved = _touch(simulator, _screen_control(simulator, screen_size), steps, watch) \
            if steps else []
        watch()
        screenshot(simulator, file)
    except WindowOverSimulator:
        # The simulator cannot close before the window is answered.
        raise
    except BaseException:
        # The error reported is the one that stopped the command, even when
        # the simulator cannot be closed.
        try:
            _close_simulator(simulator, shown_before)
        except (EditorError, pywintypes.error):
            pass
        raise
    _close_simulator(simulator, shown_before)
    return saved + [file]


def compile_shown(editor: DedicatedEditor) -> str:
    """Compiles the project shown, by the toolbar's Compile button, and
    returns the Output panel's text once the compile has ended: the
    screen's memory, the global memory, each page's, and what the compile
    refused (editor_windows.CompileWatch). The panel is emptied first, so
    that the text is this compile's alone."""
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before pressing Compile")
    if "(" not in main.window_text():
        raise EditorError("no project is open; open one first")
    output = editor.control(_OUTPUT_PANEL).handle
    try:
        empty_control(output, DIALOG_WAIT)
        pressing_failed = _press_in_background(_toolbar_button(editor, "Compile"))
        return _compile_output(editor, main, output, "Compile", pressing_failed)
    except NotAnswered as error:
        raise EditorError("the Editor did not answer a window message: %s" % error) from None


def _compile_output(editor: DedicatedEditor, main, output: int, pressed: str,
                    pressing_failed: list) -> str:
    """Waits for the compile that pressing the button `pressed` started to
    end, and returns the Output panel's text, `output` being the panel's
    handle (editor_windows.CompileWatch). The Editor's crash dialog, or a
    question it asks meanwhile, stops the wait. `pressing_failed` holds what
    went wrong pressing the button, which a wait that runs out then says."""
    watch = CompileWatch()

    def ended():
        if not win32gui.IsWindowEnabled(editor.main_handle):
            editor.stop_on_crash()
            _stop_on_dialog(main, "while compiling")
        text = control_text(output, DIALOG_WAIT)
        progress_shown = any(win32gui.GetWindowText(handle) == PROGRESS_FORM
                             for handle in shown_windows(editor.recorded.pid))
        return text if watch.look(text, progress_shown, time.monotonic()) else None
    try:
        return _wait_for(ended, COMPILING_WAIT, "the compile to end")
    except EditorError as error:
        if pressing_failed:
            raise EditorError("%s; pressing %s failed: %r"
                              % (error, pressed, pressing_failed[0])) from None
        raise


def write_tft(editor: DedicatedEditor, folder: Path) -> tuple:
    """Compiles the project shown and writes its TFT file in `folder`, made
    if missing, through File > TFT file output. Returns (the file's path, the
    Output panel's text). The Editor names the file after the project. It
    compiles first, as the toolbar's Compile does, and replaces an existing
    file without asking. Once it has written the file, it opens an Explorer
    window on the folder, which is closed (_close_explorer_on). Raises
    EditorError when the compile fails, quoting the Output panel, or when no
    file of the size the panel gives shows."""
    editor.stop_on_crash()
    main = editor.main_window()
    _stop_on_dialog(main, "before writing the TFT file")
    if "(" not in main.window_text():
        raise EditorError("no project is open; open one first")
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    output = editor.control(_OUTPUT_PANEL).handle
    explorers_before = set(_explorer_windows())
    try:
        empty_control(output, DIALOG_WAIT)
        form = _open_tft_output(editor, main)
        try:
            file = folder / _control(form, "Text", _TFT_FILE_NAME).element_info.name
            written_before = _modified(file)
            box = _control(form, "Edit", _TFT_FOLDER_BOX)
            box.set_edit_text(str(folder))
            if box.get_value() != str(folder):
                raise EditorError("the TFT output window's folder box shows %r, not %s"
                                  % (box.get_value(), folder))
            pressing_failed = _press_in_background(_control(form, "Button",
                                                            _TFT_OUTPUT_BUTTON))
            text = _compile_output(editor, main, output, "Output", pressing_failed)
            size = compiled_file_size(text)
            if size is None:
                raise EditorError("the compile did not succeed, so no TFT file was written. "
                                  "The Output panel says:\n%s"
                                  % text.replace("\r\n", "\n").rstrip("\n"))
            _wait_for(lambda: _written_anew(file, written_before, size), DIALOG_WAIT,
                      "%s, of %d bytes, to be written" % (file, size))
            _wait_for(lambda: not _shown(form.handle), DIALOG_WAIT,
                      "the TFT output window to close")
        except Exception:
            # The window stays when the compile fails. Left up, it would stop
            # every later command, as it disables the main window.
            _close_window(form.handle)
            raise
    except NotAnswered as error:
        raise EditorError("the Editor did not answer a window message: %s" % error) from None
    if not _close_explorer_on(folder, explorers_before):
        print("The Explorer window the Nextion Editor opens on %s did not show within %d s: "
              "close it if it shows" % (folder, _EXPLORER_WAIT), file=sys.stderr)
    return file, text


def _open_tft_output(editor: DedicatedEditor, main):
    """Shows the window of File > TFT file output, and returns it. The File
    menu lists its items only once open, so it is opened first. Its item is
    pressed in the background, as the window it shows is modal.

    Just after `open`, while the Editor is still busy with the project, a
    press of the item can be lost: the menu closes, and no window shows. So
    when none shows within _PRESS_SHOWS while the main window stays enabled,
    as no window of the Editor's is up, File and its item are pressed again,
    _TFT_PRESSES times in all."""
    file_menu = _required(_only_match(editor.control(_MENU_BAR), "children", name="File",
                                      control_type="MenuItem"),
                          title="File", control_type="MenuItem")
    shown_before = set(shown_windows(editor.recorded.pid))

    def form():
        new = [handle for handle in shown_windows(editor.recorded.pid)
               if handle not in shown_before]
        return next(windows_matching(new, _wrapped, lambda window:
                                     window.element_info.automation_id == TFT_OUTPUT_FORM),
                    None)
    for _ in range(_TFT_PRESSES):
        pressing_failed = _press_tft_item(file_menu)
        try:
            return _wait_for(form, _PRESS_SHOWS, "the TFT output window")
        except EditorError:
            if not win32gui.IsWindowEnabled(editor.main_handle):
                break       # a window of the Editor's is up: the press took
    else:
        raise EditorError("pressed File > %s %d times, and its window did not show%s"
                          % (_TFT_MENU_ITEM, _TFT_PRESSES, "; pressing it failed: %r"
                             % pressing_failed[0] if pressing_failed else ""))
    try:
        return _wait_for(form, DIALOG_WAIT, "the TFT output window")
    except EditorError as error:
        if pressing_failed:
            raise EditorError("%s; pressing %s failed: %r"
                              % (error, _TFT_MENU_ITEM, pressing_failed[0])) from None
        raise


def _press_tft_item(file_menu) -> list:
    """Opens the File menu, unless it is open, and presses its TFT file
    output item in the background. Returns the list where the press puts
    what went wrong (_press_in_background)."""
    if not file_menu.children():
        file_menu.invoke()
    try:
        item = _wait_for(lambda: next((child for child in file_menu.children()
                                       if child.element_info.name == _TFT_MENU_ITEM), None),
                         DIALOG_WAIT, "the File menu's %s" % _TFT_MENU_ITEM)
    except Exception:
        # Pressed again, the menu closes.
        file_menu.invoke()
        raise
    return _press_in_background(item)


def _modified(file: Path):
    """The time `file` was last written, in nanoseconds, or None when it is
    missing."""
    try:
        return file.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def _written_anew(file: Path, written_before, size: int) -> bool:
    """Whether `file` was written since `written_before`, its time then
    (_modified), and has `size` bytes. A file missing for a moment, as while
    it is replaced, is not written yet."""
    try:
        state = file.stat()
    except FileNotFoundError:
        return False
    return state.st_mtime_ns != written_before and state.st_size == size


def _shown(handle: int) -> bool:
    """Whether the window `handle` still exists, and shows."""
    return bool(win32gui.IsWindow(handle) and win32gui.IsWindowVisible(handle))


def _close_window(handle: int):
    """Asks the window `handle` to close, if it still shows."""
    if _shown(handle):
        win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)


def _explorer_windows() -> dict:
    """The Explorer windows open, {window handle: Shell.Application's window},
    through Shell.Application's list of them."""
    found = {}
    try:
        listed = win32com.client.Dispatch("Shell.Application").Windows()
    except pywintypes.com_error as error:
        raise EditorError("Windows' list of Explorer windows could not be read: %s"
                          % error) from None
    for window in listed:
        try:
            found[int(window.HWND)] = window
        except pywintypes.com_error:
            continue        # closing as it is read
    return found


def _close_explorer_on(folder: Path, before: set) -> bool:
    """Closes the Explorer window the Editor opens on `folder` once it has
    written a TFT file there: one on that folder that was not open `before`
    (editor_windows.explorer_windows_on). It waits up to _EXPLORER_WAIT for
    it, and closes no other window. Returns whether it closed one."""
    deadline = time.monotonic() + _EXPLORER_WAIT
    while time.monotonic() < deadline:
        watchdog.progress()
        windows = _explorer_windows()
        locations = {}
        for handle, window in windows.items():
            try:
                locations[handle] = window.LocationURL
            except pywintypes.com_error:
                continue
        opened = explorer_windows_on(before, locations, folder)
        if opened:
            for handle in opened:
                try:
                    windows[handle].Quit()
                except pywintypes.com_error:
                    pass        # closed already
            return True
        time.sleep(_LOOK_PAUSE)
    return False


def _shown_screen_size(folder: Path, main) -> tuple:
    """The (width, height) of the screen of the project the main window
    shows, as `open` recorded it. Raises EditorError when the project shown
    is not the one recorded, or its size could not be read."""
    shown = read_shown(folder)
    # The title names the project shown, as _opened reads it.
    if shown is None or not shows_project(main.window_text(), shown.project):
        raise EditorError("--touch needs the screen's size of the project shown, which the "
                          "tool reads as its open command opens a project: open it again "
                          "with the open command")
    if shown.screen is None:
        raise EditorError("--touch needs the screen's size of %s, which nxwright could not "
                          "read: its screen model may be one nxwright does not know"
                          % shown.project)
    return shown.screen


def _screen_control(simulator, screen_size: tuple) -> int:
    """The window handle of the simulator's screen, a control of its own,
    whose client pixels are the screen's. Raises EditorError when it is not
    found, or not `screen_size`, as at a display scale that enlarges it:
    every touch would then land elsewhere."""
    panel = _child(simulator, "panel1")
    screen = _child(panel, "runscr1") if panel is not None else None
    if screen is None:
        raise EditorError("the simulator's screen was not found")
    handle = screen.element_info.handle
    width, height = win32gui.GetClientRect(handle)[2:]
    if (width, height) != tuple(screen_size):
        raise EditorError("the simulator's screen is %d by %d pixels, where the project's is "
                          "%d by %d: the touches would land elsewhere"
                          % (width, height, *screen_size))
    return handle


def _touch(simulator, handle: int, steps: list, stop) -> list:
    """Presses and releases on the simulator's screen, the control `handle`,
    as `steps` says, and saves the pictures they ask for, once the simulator
    has run what the touches before them started. A press is a mouse move
    then a left button press, posted, and a release a left button release.
    Returns the pictures saved. `stop` is called before each step, and
    raises to end the touches, as _wait_for's does."""
    saved = []
    for step in steps:
        # A wait asked for may outlast the watchdog's quiet seconds.
        watchdog.progress(step.milliseconds / 1000 if isinstance(step, Wait) else 0)
        stop()
        if isinstance(step, Press):
            position = _packed(step.x, step.y)
            win32gui.PostMessage(handle, win32con.WM_MOUSEMOVE, 0, position)
            win32gui.PostMessage(handle, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, position)
            time.sleep(_TOUCH_PAUSE)
        elif isinstance(step, Release):
            win32gui.PostMessage(handle, win32con.WM_LBUTTONUP, 0, _packed(step.x, step.y))
            time.sleep(_TOUCH_PAUSE)
        elif isinstance(step, Wait):
            time.sleep(step.milliseconds / 1000)
        elif isinstance(step, Picture):
            _send(simulator, "", stop=stop)
            screenshot(simulator, step.file)
            saved.append(step.file)
    _send(simulator, "", stop=stop)
    return saved


def _simulator(editor: DedicatedEditor):
    """The simulator's window, when it shows: a window of the dedicated
    Editor's process with the automation ID apprun. Its owner is not
    checked: it has been seen owned by the main window, and owned by
    nothing, for a reason not known. A window that cannot tell its ID is
    skipped (editor_windows.py)."""
    info = window_with_id(shown_windows(editor.recorded.pid), "apprun", UIAElementInfo)
    return UIAWrapper(info) if info is not None else None


def _child(window, automation_id: str):
    """`window`'s child with this automation ID, when it shows."""
    return next((child for child in window.children()
                 if child.element_info.automation_id == automation_id
                 and win32gui.IsWindowVisible(child.element_info.handle)), None)


def _send(simulator, instruction: str, hex_mode: bool = False, *, stop):
    """Types `instruction` in the simulator's instruction box, line by line,
    runs it, and waits until the simulator has run it. The box is set to
    take the lines as text, or as hexadecimal bytes with `hex_mode`
    (instructions.py), before them: a simulator may keep the box's choice
    from a run that stopped.

    The box is a text editor of its own, which UI Automation cannot write
    to. So each line is typed as character messages, as typing would give
    them, then Escape, which closes the box's word list if it opened, and
    Enter. All are posted, so they arrive in order. When the box's tick box
    says so, Enter runs each line as it is typed; otherwise Enter only starts
    a new line, and a click posted on Run all commands runs them all.

    The simulator answers instructions in order. So a last line, DONE_MARKER
    (instructions.py), is answered once the instruction before it has run,
    and its answer adds to the count of lines the simulator returned. The
    wait ends at the first answer: a line of the instruction that answers
    too, as get and print do, ends it at its own answer, maybe before the
    lines after it. An empty instruction types DONE_MARKER alone: the wait
    then ends once the simulator has run what came before it, such as
    touches. `stop` is as for _wait_for, in each wait."""
    box = _child(simulator, "textEditorControl1")
    if box is None:
        raise EditorError("the simulator's instruction box was not found")
    # Inside the box, the text area is the widest pane with nothing in it;
    # the other such pane is its scroll bar.
    panes = [pane for pane in box.descendants(control_type="Pane") if not pane.children()]
    if not panes:
        raise EditorError("the simulator's instruction box holds no text area")
    area = max(panes, key=lambda pane: pane.element_info.rectangle.width()).element_info.handle
    tick = _child(simulator, "checkBox1")
    if tick is None or tick.element_info.name != "Press Enter to run the last command":
        raise EditorError("the simulator's tick box for Enter was not found")
    runs_on_enter = tick.get_toggle_state() == 1
    returned = _child(simulator, "datalabelList0")
    if returned is None:
        raise EditorError("the simulator's count of returned lines was not found")
    before = _returned_lines(returned)
    _choose_input_mode(simulator, "Hex" if hex_mode else "String", stop)
    for line in typed_lines(instruction, hex_mode):
        # Windows counts characters in UTF-16 units.
        units = line.encode("utf-16-le")
        for index in range(0, len(units), 2):
            win32gui.PostMessage(area, win32con.WM_CHAR,
                                 int.from_bytes(units[index:index + 2], "little"), 1)
        for key in (win32con.VK_ESCAPE, win32con.VK_RETURN):
            win32gui.PostMessage(area, win32con.WM_KEYDOWN, key, 1)
            win32gui.PostMessage(area, win32con.WM_KEYUP, key, 0xC0000001)
    if not runs_on_enter:
        run = _child(simulator, "button1")
        if run is None or run.element_info.name != "Run all commands":
            raise EditorError("the simulator's Run all commands button was not found")
        # Pressed through UI Automation, the button ran nothing on the VM. A
        # click posted on it runs the box's instructions.
        place = run.element_info.rectangle
        x, y = win32gui.ScreenToClient(run.element_info.handle, ((place.left + place.right) // 2,
                                                                 (place.top + place.bottom) // 2))
        _post_click(run.element_info.handle, x, y)
    _wait_for(lambda: _returned_lines(returned) > before, DIALOG_WAIT,
              "the simulator to run the instruction", stop)


def _choose_input_mode(simulator, name: str, stop):
    """Sets the instruction box to take lines as `name`, "String" or "Hex",
    by the choice of that name above it. `stop` is as for _wait_for."""
    choices = [choice for choice in simulator.descendants(control_type="RadioButton")
               if choice.element_info.name == name]
    if len(choices) != 1:
        raise EditorError("the instruction box's %s choice was not found" % name)
    choices[0].select()
    # The choice reads as selected a moment after it is selected.
    _wait_for(choices[0].is_selected, _SHOW_WAIT, "the instruction box's %s choice to take"
              % name, stop)


def _returned_lines(label) -> int:
    """The count of lines the simulator returned, as its label shows it: "L:1"."""
    shown = label.element_info.name
    if not re.fullmatch(r"L:\d+", shown):
        raise EditorError("the simulator's count of returned lines shows %r" % shown)
    return int(shown[2:])


def _close_simulator_left(editor: DedicatedEditor, shown_before):
    """Closes the simulator, if one shows, once simulate stopped before it
    took the simulator in hand, as _close_simulator does. What stops this
    is dropped: the error reported is the one that stopped the command."""
    try:
        simulator = _simulator(editor)
        if simulator is not None:
            _close_simulator(simulator, shown_before)
    except (EditorError, pywintypes.error, COMError):
        pass


def _close_simulator(simulator, shown_before):
    """Closes the simulator, as its Close button does, and waits until its
    window is gone. When it does not close, the error names any window
    shown over it but those of `shown_before` (_stop_on_window_over)."""
    handle = simulator.element_info.handle
    if not win32gui.IsWindow(handle):
        return
    win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
    try:
        _wait_for(lambda: not win32gui.IsWindow(handle), DIALOG_WAIT, "the simulator to close")
    except EditorError as error:
        _stop_on_window_over(simulator, shown_before, "%s: " % error)
        raise


def _stop_on_window_over(simulator, shown_before, first: str = ""):
    """Raises WindowOverSimulator, after `first`, when the Editor shows
    windows over the simulator that are not in `shown_before`
    (editor_windows.windows_over_simulator), naming what they show. One
    window may hold another's words, as a menu's frame holds its items."""
    shown, words = False, []
    for handle in windows_over_simulator(simulator.element_info.process_id,
                                         simulator.element_info.handle, shown_before,
                                         lambda window: _wrapped(window).element_info):
        try:
            names = [control.element_info.name for control in _wrapped(handle).descendants()]
        except COMError:
            continue    # torn down: answered meanwhile
        shown = True
        words += [" ".join(name.split()) for name in names if name.strip()]
    if shown:
        raise WindowOverSimulator("%sa window shows over the simulator, waiting for an "
                                  "answer: %s. It is left open, with the simulator, which "
                                  "neither runs nor closes until it is answered"
                                  % (first, " / ".join(words) or "(no words)"))


def close_simulator(folder: Path) -> str:
    """Closes the simulator the dedicated Editor shows, if any, as its Close
    button does, and says what it found. It starts no Editor."""
    recorded = read_recorded(folder)
    if recorded is None or not still_running(recorded):
        return "No dedicated Editor runs, so no simulator is open."
    editor = DedicatedEditor(recorded)
    simulator = _simulator(editor)
    if simulator is None:
        return "No simulator is open."
    _close_simulator(simulator, frozenset({editor.main_window().element_info.handle}))
    return "Closed the simulator."


def close_file_dialog(folder: Path) -> str:
    """Cancels the file dialog the dedicated Editor shows, if any, as its
    Cancel button does, and says what it found. An `open` stopped from
    outside can leave one up, and the tool's other commands stop on it. It
    starts no Editor."""
    recorded = read_recorded(folder)
    if recorded is None or not still_running(recorded):
        return "No dedicated Editor runs, so no file dialog is open."
    dialogs = _dialogs(DedicatedEditor(recorded).main_window(), _is_file_dialog)
    if not dialogs:
        return "No file dialog is open."
    _cancel_file_dialog(dialogs[0])
    return "Cancelled the file dialog."


def status(folder: Path, name) -> str:
    """Says which Editor the tool drives, `name`'s or the shared one, whose
    records are in `folder`, whether it runs, and what its window shows."""
    recorded = read_recorded(folder)
    if recorded is None or not still_running(recorded):
        return "Not running: %s; the next command starts it." % editor_words(name)
    title = DedicatedEditor(recorded).main_window().window_text()
    return "Running: %s, as process %d: %s" % (editor_words(name), recorded.pid, title)


if __name__ == "__main__":
    sys.exit(main())
