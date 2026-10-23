"""The text of a source folder's files, as the language server reads them:
the editor's while a file is open in it, saved or not, as pygls keeps it in
its workspace; else the file's on disk. Both with LF line endings, which the
folder's readers expect. Also the file: URIs that name the files to the
editor.
"""
import os
from pathlib import Path

from pygls.uris import from_fs_path, to_fs_path

from nxwright import MissingFileError, NxwrightError


class FileTexts:
    """The texts of files, through the pygls Workspace `workspace_of()`
    returns, which pygls makes as the editor initializes the server; or from
    disk alone without one, as in a test."""

    def __init__(self, workspace_of=None):
        self._workspace_of = workspace_of

    def open_paths(self) -> list:
        """Returns the paths of the files open in the editor."""
        return [path for path, _ in self._open().values()]

    def read(self, path: Path):
        """Returns the text of the file at `path`: the editor's while it is
        open, else the file's on disk. Returns None when the file is neither
        open nor readable as UTF-8."""
        try:
            return self._text(path)
        except (OSError, UnicodeDecodeError):
            return None

    def folder_reader(self, root: Path):
        """Returns read(path), which returns the text of a file of the source
        folder `root`, by its path within the folder, as `read` does. Like
        the build's reader, it raises NxwrightError for a file whose bytes
        are not UTF-8, and MissingFileError for a file it cannot open."""
        def read(path: str) -> str:
            try:
                return self._text(root / path)
            except UnicodeDecodeError:
                raise NxwrightError("%s is not UTF-8 text" % path) from None
            except OSError:
                raise MissingFileError("%s is missing" % path) from None
        return read

    def _text(self, path: Path) -> str:
        """Returns the text of the file at `path`: the editor's while it is
        open, else the file's on disk. Raises OSError for a file it cannot
        open, and UnicodeDecodeError for one whose bytes are not UTF-8."""
        found = self._open().get(_key(path))
        if found is not None:
            return found[1]
        return _with_lf(path.read_bytes().decode("utf-8-sig"))

    def unsaved(self, path: Path) -> bool:
        """Returns whether the file at `path` is open with other text than its
        file on disk: changes a command rewriting the file would lose."""
        found = self._open().get(_key(path))
        if found is None:
            return False
        try:
            return found[1] != _with_lf(path.read_bytes().decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            return True

    def _open(self) -> dict:
        """Returns {_key(path): (path, text)} of the files open in the editor,
        files alone: an editor's untitled texts have no path."""
        if self._workspace_of is None:
            return {}
        found = {}
        for uri, document in self._workspace_of().text_documents.items():
            path = path_of(uri)
            if path is not None:
                found[_key(path)] = (path, _with_lf(document.source))
        return found


def uri_of(path: Path) -> str:
    """Returns the file: URI of the absolute path `path`, as pygls writes one."""
    return from_fs_path(str(path))


def path_of(uri: str):
    """Returns the Path a file: URI names, or None for a URI of another
    scheme, as an editor's untitled text has."""
    path = to_fs_path(uri)
    return Path(path) if path is not None else None


def _key(path: Path) -> str:
    """Returns the form of `path` that compares equal for every way of writing
    it: Windows ignores the case of names, and the editor may write the drive
    letter in either case."""
    return os.path.normcase(os.path.abspath(path))


def _with_lf(text: str) -> str:
    return text.replace("\r\n", "\n")
