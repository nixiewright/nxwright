"""The numbers that stand for resources in a source folder's files, kept
for the language server's inlay hints and code actions.

Finding which of a file's numbers stand for resources compiles the code of
each page that uses the file (source/resource_numbers.py, placed_numbers).
The editor requests inlay hints whenever the view scrolls, and code actions
whenever the cursor moves, so the cache keeps the numbers instead of finding
them again for each request.

Along with the numbers, the cache keeps what it read from each file while
finding them. Each request reads those files again, and if any of them has
changed, the cache reads the folder afresh. Reading the files costs little
next to compiling, and it lets the cache see a change made outside the
editor even when the editor does not report it.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.source.folder_index import FolderIndex
from nxwright.source.resource_numbers import placed_numbers
from nxwright.source.source_folder import read_folder_source


class ResourceNumberCache:
    """Keeps the numbers that stand for resources in the files of each source
    folder, reading the files through `texts` (file_texts.FileTexts)."""

    def __init__(self, texts):
        self._texts = texts
        self._folders = {}      # {root: _KeptFolder}

    def numbers_of(self, root: Path, path: str):
        """Returns (FolderIndex, FolderSource, PlacedNumbers) for `path`, a
        page file or a .nx file in the source folder `root`. Returns None
        when the folder cannot be read."""
        kept = self._folders.get(root)
        if kept is None or kept.changed():
            kept = self._folders[root] = _KeptFolder(root, self._texts.folder_reader(root))
        return kept.numbers_of(path)


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

    def numbers_of(self, path: str):
        """Returns (FolderIndex, FolderSource, PlacedNumbers) for the file
        `path`, or None when the folder could not be read."""
        if self.folder is None:
            return None
        if path not in self._numbers:
            self._numbers[path] = placed_numbers(self.folder, self.index, path)
        return self.index, self.folder, self._numbers[path]

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
