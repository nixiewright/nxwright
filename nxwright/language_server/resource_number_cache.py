"""The numbers that stand for resources in a source folder's files, kept
for the language server's inlay hints and code actions. In `p0.pic=7`, the
7 stands for a picture, and its inlay hint shows that picture's name.

Finding which of a file's numbers stand for resources means compiling the
code of each page that uses the file (source/resource_numbers.py,
placed_numbers).
The editor requests inlay hints whenever the view scrolls or the text
changes, and code actions whenever the cursor moves, so the cache keeps the
numbers instead of finding them again for each request.

Along with the numbers, the cache keeps what it read from each file while
finding them. Each request reads those files again, to see whether any of
them has changed. Reading the files costs little next to compiling, and it
lets the cache see a change made outside the editor even when the editor
does not report it.

After a change, the language server checks the folder for errors and
warnings once typing pauses (live_checks.py). Until that check and the work
that follows it have ended, the change waits to be checked. What a request
gets once a file has changed depends on whether a change waits to be
checked:
  - While nothing waits to be checked, the cache reads the folder afresh and
    finds the file's numbers before the request is answered (numbers_of).
  - While a change waits to be checked, which is the case after each key
    typed, finding the numbers would hold up the check and the keys typed
    next. The request gets the numbers the cache already has
    (kept_numbers_of), but only those on lines whose text did not change,
    each placed where its line is now.

When the cache answers from the numbers it already has, it notes that the
folder's numbers are out of date, and the server finds them again in steps
once the pages are checked (step). The steps cover only the files that
requests asked about since the numbers were last found, because the editor
asks about the files it shows.
"""
import dataclasses
import difflib
from pathlib import Path
import sys
import traceback

from nxwright import NxwrightError
from nxwright.source.folder_index import FolderIndex
from nxwright.source.resource_numbers import placed_numbers, placed_numbers_in_steps
from nxwright.source.source_folder import read_folder_source


class ResourceNumberCache:
    """Keeps the numbers that stand for resources in the files of each source
    folder, reading the files through `texts` (file_texts.FileTexts)."""

    def __init__(self, texts):
        self._texts = texts
        self._folders = {}          # {root: _KeptFolder}
        self._asked = {}            # {root: {paths asked about since the numbers were found}}
        self._out_of_date = set()   # the roots whose numbers are to be found again
        self._steps = None          # the steps left of finding them again, a generator

    def numbers_of(self, root: Path, path: str):
        """Returns (FolderIndex, FolderSource, PlacedNumbers) for `path`, a
        page file or a .nx file in the source folder `root`, finding the
        numbers first if a file changed since they were found. Returns None
        when the folder cannot be read."""
        self._asked.setdefault(root, set()).add(path)
        kept = self._folders.get(root)
        if kept is None or kept.changed():
            kept = self._folders[root] = _KeptFolder(root, self._texts.folder_reader(root))
        return kept.numbers_of(path)

    def kept_numbers_of(self, root: Path, path: str):
        """Returns (FolderIndex, FolderSource, PlacedNumbers) for `path` from
        the numbers the cache already has, without finding any. Returns None
        when the cache has no numbers for `path`.

        If a file changed since the numbers were found, only the numbers on
        lines of `path` whose text did not change are returned, each placed
        where its line is now. The first of the three is then a CurrentLines,
        which gives only the files' lines as they are now.

        When a file changed, or the cache has no numbers for `path`, the call
        also marks the folder as out of date, so that `step` finds its numbers
        again."""
        self._asked.setdefault(root, set()).add(path)
        kept = self._folders.get(root)
        if kept is None:
            self._out_of_date.add(root)
            return None
        if not kept.changed():
            if not kept.has_numbers_of(path):
                self._out_of_date.add(root)
                return None
            return kept.numbers_of(path)
        self._out_of_date.add(root)
        read = self._texts.folder_reader(root)
        numbers = kept.numbers_on_unchanged_lines(path, read)
        return None if numbers is None else (CurrentLines(root, read), kept.folder, numbers)

    def waiting(self) -> bool:
        """True when a folder's numbers are to be found again."""
        return bool(self._out_of_date) or self._steps is not None

    def stop(self):
        """Stops the work of finding the numbers again, for example when a
        file changes while it runs. The folders stay out of date, so the next
        `step` starts that work over."""
        if self._steps is not None:
            self._steps.close()
            self._steps = None

    def step(self) -> bool:
        """Runs the next step of finding the numbers again for the folders
        that are out of date. A step reads a folder, or compiles one page.
        Returns True when the step finished finding a folder's numbers, so
        that the server can tell the editor to request its hints again."""
        if self._steps is None:
            self._steps = self._finding_again()
        try:
            return bool(next(self._steps))
        except StopIteration:
            self._steps = None
            return False

    def _finding_again(self):
        """Finds again the numbers of each folder that is out of date, for
        the files that requests asked about. The generator yields after each
        step: True after the last step of a folder whose numbers were found,
        and a false value after any other step.

        An unexpected error must not end the server, and must not happen
        again at every step. The cache therefore gives up on the folder
        until a request asks about it again, and the error's trace goes to
        standard error, which editors show in their log."""
        while self._out_of_date:
            root = next(iter(self._out_of_date))
            found = False
            try:
                kept = _KeptFolder(root, self._texts.folder_reader(root))
                yield
                for path in sorted(self._asked.get(root, ())):
                    yield from kept.find_numbers_in_steps(path)
                self._folders[root] = kept
                found = True
            except Exception:
                traceback.print_exc(file=sys.stderr)
            self._asked[root] = set()
            self._out_of_date.discard(root)
            yield found


class CurrentLines:
    """The lines of the files of the source folder `root` as they are now,
    read through `read(path)`, a reader returned by FileTexts.folder_reader.
    It stands in for a FolderIndex where only a file's lines are needed, for
    example to give a place in the editor's units. Making a CurrentLines
    does not read the folder."""

    def __init__(self, root: Path, read):
        self.root, self._read = root, read

    def lines(self, path: str):
        """Returns the lines of the folder's file `path`, or None when it cannot be read."""
        try:
            return self._read(path).split("\n")
        except NxwrightError:
            return None


class _KeptFolder:
    """A source folder as `read(path)` gave it, and the numbers found in its
    files so far. `read` is a reader returned by FileTexts.folder_reader."""

    def __init__(self, root: Path, read):
        self._root, self._read = root, read
        # {path: the text read(path) returned, or the error it raised}
        self._given = {}
        self.index = FolderIndex(root, self._index_read)
        try:
            self.folder = read_folder_source(self._recorded_read)
        except NxwrightError:
            self.folder = None
        self._numbers = {}      # {path: [PlacedNumber]}
        # {path: (the file's text now, its numbers on the lines that did not change)}
        self._on_unchanged_lines = {}

    def numbers_of(self, path: str):
        """Returns (FolderIndex, FolderSource, PlacedNumbers) for the file
        `path`, or None when the folder could not be read."""
        if self.folder is None:
            return None
        if path not in self._numbers:
            self._numbers[path] = placed_numbers(self.folder, self.index, path)
        return self.index, self.folder, self._numbers[path]

    def has_numbers_of(self, path: str) -> bool:
        """Returns whether numbers_of answers for `path` without finding its
        numbers, either because they were already found or because the folder
        could not be read."""
        return self.folder is None or path in self._numbers

    def find_numbers_in_steps(self, path: str):
        """Finds the numbers of the file `path`, if they are not found yet,
        yielding after each page compiled."""
        if self.folder is not None and path not in self._numbers:
            self._numbers[path] = yield from placed_numbers_in_steps(self.folder, self.index,
                                                                     path)

    def numbers_on_unchanged_lines(self, path: str, read):
        """Returns the numbers found in the file `path`, leaving out those on
        lines whose text changed since they were found. `read(path)` gives
        the file's text as it is now, and each number is placed where its
        line is in that text. Returns None when the numbers of `path` were
        not found, or the file cannot be read now."""
        was, now = self._given.get(path), _outcome(read, path)
        if path not in self._numbers or not isinstance(was, str) or not isinstance(now, str):
            return None
        kept = self._on_unchanged_lines.get(path)
        if kept is None or kept[0] != now:
            # The lines are matched once for each text, not for each request.
            matcher = difflib.SequenceMatcher(None, was.split("\n"), now.split("\n"),
                                              autojunk=False)
            line_now = {before + offset: after + offset
                        for before, after, size in matcher.get_matching_blocks()
                        for offset in range(size)}
            numbers = [dataclasses.replace(number, place=dataclasses.replace(
                           number.place, line=line_now[number.place.line]))
                       for number in self._numbers[path] if number.place.line in line_now]
            kept = self._on_unchanged_lines[path] = (now, numbers)
        return kept[1]

    def changed(self) -> bool:
        """Returns whether any file read so far now gives a different text,
        or a different error, from the first time it was read."""
        return any(not _same(_outcome(self._read, path), given)
                   for path, given in self._given.items())

    def _recorded_read(self, path: str) -> str:
        """Reads the file `path` through `read`, and records its text or the
        error it raised. Reading the same file again gives what was recorded,
        so the index and the folder's source see the same text of each file."""
        if path not in self._given:
            self._given[path] = _outcome(self._read, path)
        outcome = self._given[path]
        if isinstance(outcome, NxwrightError):
            # Drop the traceback of the earlier raise, so that it does not grow each
            # time the error is raised again.
            raise outcome.with_traceback(None)
        return outcome

    def _index_read(self, path: Path):
        """Returns the text of the file at `path`, an absolute path within
        the folder, or None when the file cannot be read. FolderIndex reads
        files through this."""
        try:
            return self._recorded_read(path.relative_to(self._root).as_posix())
        except NxwrightError:
            return None


def _outcome(read, path: str):
    """Returns the file's text from `read(path)`, or the NxwrightError it raises."""
    try:
        return read(path)
    except NxwrightError as error:
        return error


def _same(one, other) -> bool:
    """Returns whether two results of _outcome are the same text, or errors
    of the same type and message."""
    if isinstance(one, str) or isinstance(other, str):
        return one == other
    return type(one) is type(other) and str(one) == str(other)
