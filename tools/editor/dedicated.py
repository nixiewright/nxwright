"""The records of the dedicated Editor: the Nextion Editor the tool starts and
drives (README.md). The environment variable NXWRIGHT_EDITOR_NAME names it,
so that each agent drives its own; with no name, it is the shared one.

Its records live in the user's local data folder, in
%LOCALAPPDATA%\\nxwright\\editor-<name>\\, or %LOCALAPPDATA%\\nxwright\\editor\\
for the shared Editor:
  - editor.json, the dedicated Editor's process: its ID, when it started,
    and its program. A process ID alone could name a later process, once
    the Editor has ended; the start time tells them apart.
  - lock, held by the one command driving the Editor, and holder.json, which
    says which process holds it. Windows lets no other process read a
    file's locked part, so the holder is told in a file of its own.
  - hold.json, a hold across commands: a holder's name, which its commands
    give, and until when anyone else's are refused. Each command is a
    process of its own, so the lock cannot span a probe of several; a hold
    ends by its holder's release or its time.
  - work\\, the copies of the projects the Editor opens.
  - shown.json, the copy the tool last opened, with its screen's size. The
    Editor keeps the project it shows locked, even against reading, so the
    size is read from the copy before the Editor opens it.
  - placement.json, where the Editor's main window last was, and its size.
    The Editor starts filling the screen, so a fresh one the tool starts is
    given that placement instead, which the user chose: the shared
    Editor's, until a named Editor has one of its own.

This module needs no pywinauto, so its tests run with nxwright's own
Python. It needs Windows, as the tool does.
"""
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import msvcrt
import os
from pathlib import Path
import re
import time

# The environment variable that names the dedicated Editor to drive.
EDITOR_NAME = "NXWRIGHT_EDITOR_NAME"
# A name becomes part of a folder whose copies the tool writes over. These
# characters alone can never lead that folder out of nxwright's own.
_NAME = re.compile(r"[A-Za-z0-9_-]{1,32}")


def editor_name(environment=None):
    """Returns the name of the dedicated Editor to drive, as EDITOR_NAME in
    `environment`, os.environ unless given, says, or None for the shared
    Editor, when it is unset or empty. records_folder checks it."""
    return (os.environ if environment is None else environment).get(EDITOR_NAME) or None


def editor_words(name) -> str:
    """The words naming the Editor that `name` names, as the tool's messages
    say them."""
    return "the shared Editor" if name is None else "%s's Editor" % name


def records_folder(name=None, local=None) -> Path:
    """Returns the folder of the records of the Editor `name` names, or of
    the shared Editor for None, made if missing. `local` is the user's local
    data folder, LOCALAPPDATA's unless given. Raises ValueError for a name
    of other characters than letters, digits, "-", and "_", or of more than
    32, before any folder is made."""
    if name is not None and not _NAME.fullmatch(name):
        raise ValueError("%s %r is no name of an Editor: it takes letters, digits, \"-\", and "
                         "\"_\", at most 32" % (EDITOR_NAME, name))
    local = os.environ.get("LOCALAPPDATA") if local is None else local
    if not local:
        raise RuntimeError("LOCALAPPDATA is not set, so the dedicated Editor's records "
                           "have no place")
    folder = Path(local) / "nxwright" / ("editor" if name is None else "editor-" + name)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


@dataclass
class Recorded:
    """The dedicated Editor's process, as editor.json records it."""
    pid: int
    started: int        # when it started, as Windows counts: 100 ns steps since 1601
    program: str


def read_recorded(folder: Path):
    """Returns the Recorded process of `folder`'s editor.json, or None when
    there is none, or it cannot be read."""
    try:
        data = json.loads((folder / "editor.json").read_text(encoding="utf-8"))
        return Recorded(int(data["pid"]), int(data["started"]), str(data["program"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_recorded(folder: Path, recorded: Recorded):
    """Records `recorded` as the dedicated Editor, in `folder`'s editor.json."""
    (folder / "editor.json").write_text(json.dumps(asdict(recorded)), encoding="utf-8")


@dataclass
class Shown:
    """The copy of a project the tool last opened, as shown.json records it,
    and the (width, height) of its screen at its rotation, or None when
    nxwright could not read them from it."""
    project: str
    screen: tuple


def read_shown(folder: Path):
    """Returns the Shown project of `folder`'s shown.json, or None when there
    is none, or it cannot be read."""
    try:
        data = json.loads((folder / "shown.json").read_text(encoding="utf-8"))
        screen = data["screen"]
        return Shown(str(data["project"]),
                     None if screen is None else (int(screen[0]), int(screen[1])))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return None


def write_shown(folder: Path, shown: Shown):
    """Records `shown` as the project the tool last opened, in `folder`'s
    shown.json."""
    (folder / "shown.json").write_text(json.dumps(asdict(shown)), encoding="utf-8")


def read_placement(folder: Path):
    """Returns the dedicated Editor's main window placement that `folder`'s
    placement.json records, as Windows' GetWindowPlacement gives it: (flags,
    how it shows, its minimized place (x, y), its maximized place (x, y),
    its normal rectangle (left, top, right, bottom)). None when there is
    none, or it cannot be read."""
    try:
        flags, show, minimized, maximized, normal = json.loads(
            (folder / "placement.json").read_text(encoding="utf-8"))
        if (len(minimized), len(maximized), len(normal)) != (2, 2, 4):
            return None
        return (int(flags), int(show), tuple(map(int, minimized)), tuple(map(int, maximized)),
                tuple(map(int, normal)))
    except (OSError, ValueError, TypeError):
        return None


def write_placement(folder: Path, placement: tuple):
    """Records `placement`, as read_placement returns it, in `folder`'s
    placement.json."""
    (folder / "placement.json").write_text(json.dumps(placement), encoding="utf-8")


def starting_placement(folder: Path, shared: Path):
    """Returns the placement a fresh Editor whose records are in `folder`
    takes: its own, or else the shared Editor's, whose records are in
    `shared`, so that a named Editor's first window does not fill the
    screen. None when neither has one."""
    return read_placement(folder) or read_placement(shared)


# How long a hold lasts, in minutes, unless its `hold` says, and at most.
HOLD_MINUTES = 10
MOST_HOLD_MINUTES = 60


@dataclass
class Hold:
    """A hold on the dedicated Editor across commands (hold.json): its
    holder's name, its minutes, and since and until when, in seconds since
    the epoch."""
    holder: str
    minutes: int
    since: float
    until: float

    def told(self) -> str:
        """The hold as a refusal tells it."""
        return "%s holds the dedicated Editor, since %s, until %s" % (
            self.holder, _clock(self.since), _clock(self.until))


class HoldRefused(Exception):
    """A command refused, as another holder holds the dedicated Editor."""


def standing_hold(folder: Path, now: float = None):
    """Returns the hold that `folder`'s hold.json records, or None when there
    is none, it is past its time, or it cannot be read."""
    now = time.time() if now is None else now
    try:
        hold = Hold(**json.loads((folder / "hold.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None
    return hold if hold.until > now else None


def take_hold(folder: Path, name: str, minutes: int = HOLD_MINUTES, now: float = None) -> Hold:
    """Takes a hold for `name`, for `minutes`, or renews the one it has.
    Raises HoldRefused when another holder holds the Editor, and ValueError
    for minutes not from 1 to MOST_HOLD_MINUTES. Called under the lock, as
    every command runs."""
    if not 1 <= minutes <= MOST_HOLD_MINUTES:
        raise ValueError("a hold lasts from 1 to %d minutes, not %s" % (MOST_HOLD_MINUTES, minutes))
    now = time.time() if now is None else now
    hold = standing_hold(folder, now)
    if hold is not None and hold.holder != name:
        raise HoldRefused(hold.told())
    hold = Hold(name, minutes, now if hold is None else hold.since, now + minutes * 60)
    (folder / "hold.json").write_text(json.dumps(asdict(hold)), encoding="utf-8")
    return hold


def check_hold(folder: Path, name, now: float = None):
    """Lets a command `name` gives run: one of the holder's, renewing its
    hold for its minutes, or any when no hold stands. Returns the hold for
    the holder's command, which renews it again as it ends (renew_hold), as
    a command may take longer than the hold's minutes; None for another.
    Raises HoldRefused for another's, or for one giving no name, while a
    hold stands."""
    hold = standing_hold(folder, now)
    if hold is None:
        return None
    if hold.holder != name:
        raise HoldRefused(hold.told())
    return take_hold(folder, name, hold.minutes, now)


def renew_hold(hold: Hold, folder: Path, now: float = None):
    """Renews `hold`, which check_hold gave a command of its holder's, as
    the command ends: still under the lock, so that no one else's command
    can have run since, even if the hold lapsed meanwhile."""
    take_hold(folder, hold.holder, hold.minutes, now)


def release_hold(folder: Path, name: str, now: float = None):
    """Ends `name`'s hold, if it holds the Editor. Raises HoldRefused when
    another holds it. A name is its holder's own word: anyone giving it may
    end its hold, as one forgotten is ended so."""
    hold = standing_hold(folder, now)
    if hold is None:
        return
    if hold.holder != name:
        raise HoldRefused(hold.told())
    (folder / "hold.json").unlink(missing_ok=True)


def _clock(seconds: float) -> str:
    """A time since the epoch, as the machine's clock shows it."""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(seconds))


def still_running(recorded: Recorded, started_of=None) -> bool:
    """Whether the recorded process still runs: its ID names a process that
    started when it did. `started_of(pid)` is process_started unless given."""
    return (started_of or process_started)(recorded.pid) == recorded.started


def process_started(pid: int):
    """Returns when the process `pid` started, in 100 ns steps since 1601, or
    None when no running process has that ID, or its start cannot be read.

    Windows keeps an ended process's record, its start included, while any
    program holds a handle to it. pywinauto refuses to attach to such a
    process, so it counts as not running."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    query_limited_information, synchronize, wait_timeout = 0x1000, 0x00100000, 0x102
    handle = kernel.OpenProcess(query_limited_information | synchronize, False, pid)
    if not handle:
        return None
    try:
        # A process's handle is signalled once the process has ended.
        if kernel.WaitForSingleObject(handle, 0) != wait_timeout:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            return None
        return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


class _MemoryCounters(ctypes.Structure):
    """Windows' PROCESS_MEMORY_COUNTERS_EX: a process's memory, in bytes."""
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
        (name, ctypes.c_size_t) for name in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
            "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]


def private_memory(pid: int):
    """Returns the private memory the process `pid` holds, in bytes, as Task
    Manager shows it, or None when no process has that ID, or its memory
    cannot be read."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.K32GetProcessMemoryInfo.argtypes = [wintypes.HANDLE,
                                               ctypes.POINTER(_MemoryCounters), wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    query_limited_information = 0x1000
    handle = kernel.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return None
    try:
        counters = _MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not kernel.K32GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return None
        return counters.PrivateUsage
    finally:
        kernel.CloseHandle(handle)


class Busy(Exception):
    """Raised when another process holds the lock past the wait."""


class Lock:
    """The lock on the dedicated Editor, held by one command at a time, in a
    `with` block. A Windows lock on the lock file's first byte: Windows drops
    it when its process ends, crashed or not, so no lock is left behind.
    `wait` is how long to wait for it, in seconds; `command` says what the
    holder does, for a refusal to tell."""

    def __init__(self, folder: Path, command: str, wait: float = 30):
        self.folder, self.command, self.wait = folder, command, wait
        self._file = None

    def __enter__(self):
        self._file = open(self.folder / "lock", "a+b")
        deadline = time.monotonic() + self.wait
        while True:
            try:
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    self._file.close()
                    raise Busy("the dedicated Editor is in use: %s" % self.holder()) from None
                time.sleep(0.2)
        (self.folder / "holder.json").write_text(json.dumps(
            {"pid": os.getpid(), "command": self.command,
             "since": time.strftime("%Y-%m-%d %H:%M:%S")}), encoding="utf-8")
        return self

    def __exit__(self, *exception):
        self._file.seek(0)
        msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        self._file.close()

    def holder(self) -> str:
        """Says which process holds the lock, as holder.json records it."""
        try:
            data = json.loads((self.folder / "holder.json").read_text(encoding="utf-8"))
            return "process %s, running %r since %s" % (data["pid"], data["command"],
                                                          data["since"])
        except (OSError, ValueError, KeyError):
            return "by a process that left no record"
