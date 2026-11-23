"""nxwright: a toolchain for Nextion Editor projects (.HMI).

The package has seven parts:
  - project: reading and writing the Editor's project files, and their dumps.
  - source: the source folder, the text form of a project kept in version control.
  - language: the code in a source folder, turned into code the Editor accepts.
  - drawing: a page and its components as the screen shows them, for the page
    preview and the simulator.
  - testing: running a screen's code on a PC, for its tests, and its whole
    app, for the simulator.
  - language_server: answers to a code editor's questions about a source folder,
    such as where a name is defined.
  - debug_adapter: the debugger of a test and its screen code, and of a
    simulation of the app, for a code editor.
"""
import importlib.metadata
from pathlib import Path


def installed_version():
    """Returns nxwright's version as installed, such as "0.1.0", from the
    package's metadata, which pyproject.toml gives. Returns None when
    nxwright runs from a copy of its source that is not installed."""
    try:
        return importlib.metadata.version("nxwright")
    except importlib.metadata.PackageNotFoundError:
        return None


def place_text(file: str, line: int = None, folder=None) -> str:
    """Returns a place as text, such as "demo\\pages\\home.nx:12" on Windows.
    A place is the file and the line that an error comes from, and a terminal
    or a code editor can open the file from this text.
    `file` is the file's path within its source folder, such as
    "pages/home.nx". `line` counts from 1, and a place without a line is the
    file alone. `folder` is the source folder as the user gave it, such as
    "demo". Without it, the text gives the path within the folder."""
    shown = file if folder is None else str(Path(folder) / file)
    return "%s:%d" % (shown, line) if line else shown


class NxwrightError(ValueError):
    """Raised when a project file, dump, or source folder holds something nxwright does not
    understand or cannot accept.

    An error from a file of a source folder may say where it comes from:
      - `file`: the file's path within the folder, such as "pages/lib/frame.nx";
      - `line`: the line, counted from 1;
      - `table`: which table of the file the error is about. For a page's
        .page.toml file, it is the table's number, counted from 0 for the
        [page] table. For app.toml, it is the table's name, such as "mcu";
      - `key`: the key the error is about, such as "rotation".
    A code editor reads these attributes to show the error in the file. When
    `file` and `line` are given to the constructor, they also start the
    message, as in "pages/home.nx:12: unknown name `speed`" (place_text), and
    `reason` is the message without them. A `file` set on the error afterwards
    is only data for a code editor, and the message does not show it.

    `folder` is the source folder as the user gave it, such as "demo". It is
    None until in_folder sets it, and the message then shows the file under
    that folder, as in "demo\\pages\\home.nx:12: unknown name `speed`".

    `owner` is the event or function that contains the line where a test run
    stopped, and None for any other error. The message gives it after the
    place, as in "pages/home.nx:12 (minutesNow): rtc3 has no value".

    A refusal with one sure fix may carry it as `fix`, a dict of plain
    values saying what to change, which a code editor offers as a quick fix
    (language_server/quick_fixes.py)."""

    def __init__(self, reason: str = "", file: str = None, line: int = None,
                 fix: dict = None, key: str = None):
        super().__init__(reason)
        self.reason, self.file, self.line, self.table = reason, file, line, None
        self.fix, self.key = fix, key
        self.folder = self.owner = None
        self._shows_file = file is not None

    def __str__(self):
        if self._shows_file:
            place = place_text(self.file, self.line, self.folder)
            if self.owner is not None:
                place = "%s (%s)" % (place, self.owner)
            return "%s: %s" % (place, self.reason)
        if self.line is not None:
            # A line of code that is checked outside any file.
            return "line %d: %s" % (self.line, self.reason)
        return self.reason

    def in_file(self, file: str) -> "NxwrightError":
        """Returns a copy of this error for the source folder's file `file`.
        The copy has this error's type, line, table, key, fix, and folder, and
        its message starts with the place."""
        located = type(self)(self.reason)
        located.file, located._shows_file = file, True
        located.line, located.table, located.fix = self.line, self.table, self.fix
        located.key = self.key
        located.folder = self.folder
        return located

    def at_place(self, file: str, line: int, owner: str = None):
        """Sets this error's place to `file` and `line`, and its `owner` to
        the event or function that contains the line. Its message then starts
        with the place and the owner. The method changes the error itself, so
        that the error keeps its class and that class's own attributes, such
        as a CompileRefusal's `code`."""
        self.file, self.line, self.owner = file, line, owner
        self._shows_file = True

    def in_folder(self, folder) -> "NxwrightError":
        """Sets this error's folder to `folder`, the source folder as the user
        gave it, and returns the error. Its message then shows its file under
        that folder. An error that already has a folder keeps it: a command
        that reads two folders, such as `nxwright diff`, sets the right one
        first."""
        if self.folder is None:
            self.folder = folder
        return self


def after_start(start: str, message: str) -> str:
    """Returns `message` after `start` and a colon, or `message` alone when
    `start` is empty. `start` is the text that a checking function was given
    to start its messages with, such as the name of a file of a dump folder.
    It is empty when the function's caller sets the error's place itself."""
    return "%s: %s" % (start, message) if start else message


def listed_in_words(names: list) -> str:
    """Returns `names` joined as a list in words, for a message: "a", "a and
    b", "a, b, and c"."""
    if len(names) < 3:
        return " and ".join(names)
    return "%s, and %s" % (", ".join(names[:-1]), names[-1])


class MissingFileError(NxwrightError):
    """Raised for a file of a source folder that is not there, so that a file
    a folder may lack, such as macros.nx, is told apart from one that does
    not read."""
