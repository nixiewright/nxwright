"""A record of what nxwright last wrote to each project file and TFT file.

A file that still has those bytes can be written again from its source folder,
so replacing it loses nothing. A file with other bytes was changed elsewhere,
such as in the Nextion Editor, and may contain work found nowhere else. The commands
that replace a file use the record to tell the two apart (replacing.written_beside).

The record is a SQLite file, written_files.sqlite, in the same folder as the
picture cache (picture_cache.cache_folder). It stores each file's hash under the
file's full path. Losing it is safe: a file with no record counts as changed
elsewhere, which costs one backup more than needed. So if the cache is off, or the
record cannot be read or written, nxwright carries on without it and does not warn.
"""
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from nxwright.project.picture_cache import cache_folder

_FILE_NAME = "written_files.sqlite"


def _opened():
    """Returns a connection to the record, or None when the cache is off."""
    folder = cache_folder()
    if folder is None:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / _FILE_NAME)
    connection.execute("CREATE TABLE IF NOT EXISTS written (path TEXT PRIMARY KEY, hash TEXT)")
    return connection


def _key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def recorded_hash(path: Path):
    """Returns the hash of what nxwright last wrote to `path`, or None when
    there is no record of it."""
    try:
        connection = _opened()
        if connection is None:
            return None
        with closing(connection):
            row = connection.execute("SELECT hash FROM written WHERE path = ?",
                                     (_key(path),)).fetchone()
    except (sqlite3.Error, OSError):
        return None
    return row[0] if row else None


def record_hash(path: Path, file_hash: str):
    """Records `file_hash` as the hash of what nxwright just wrote to `path`."""
    try:
        connection = _opened()
        if connection is None:
            return
        # The inner `with` commits the change, and `closing` closes the file.
        with closing(connection), connection:
            connection.execute("INSERT OR REPLACE INTO written (path, hash) VALUES (?, ?)",
                               (_key(path), file_hash))
    except (sqlite3.Error, OSError):
        pass
