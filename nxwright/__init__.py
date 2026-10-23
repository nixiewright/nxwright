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


def installed_version():
    """Returns nxwright's version as installed, such as "0.1.0", from the
    package's metadata, which pyproject.toml gives. Returns None when
    nxwright runs from a copy of its source that is not installed."""
    try:
        return importlib.metadata.version("nxwright")
    except importlib.metadata.PackageNotFoundError:
        return None


class NxwrightError(ValueError):
    """Raised when a project file, dump, or source folder holds something nxwright does not
    understand or cannot accept.

    An error from a file of a source folder may say where it comes from, so
    that a code editor can show it there:
      - `file`: the file's path within the folder, such as "pages/lib/frame.nx";
      - `line`: the line, counted from 1;
      - `table`: for a page's .page.toml file, which of its tables, counted from 0
        for the [page] table.
    Given to the constructor, `file` and `line` start the message, as in
    "pages/home.nx line 12: unknown name speed". `reason` is the message
    without them.

    A refusal with one sure fix may carry it as `fix`, a dict of plain
    values saying what to change, which a code editor offers as a quick fix
    (language_server/quick_fixes.py)."""

    def __init__(self, reason: str = "", file: str = None, line: int = None,
                 fix: dict = None):
        message = reason
        if line is not None:
            message = "line %d: %s" % (line, message)
        if file is not None:
            message = "%s %s" % (file, message)
        super().__init__(message)
        self.reason, self.file, self.line, self.table = reason, file, line, None
        self.fix = fix

    def in_file(self, file: str, shown: str = None) -> "NxwrightError":
        """Returns this error as raised from the folder's file `file`: of the
        same type, keeping its line, table, and fix, with its message after
        the file's name, or after `shown` when the message names it
        otherwise."""
        located = type(self)("%s %s" % (shown or file, self))
        located.reason, located.file = self.reason, file
        located.line, located.table, located.fix = self.line, self.table, self.fix
        return located


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
