"""Screen copies made from pictures, kept between builds.

Making a picture's screen copy from its file (screen_copy.py) is slow: the
Editor's arithmetic and compression, in Python, pixel by pixel. So screen
copies are kept in a cache, one file per user, and taken from there by later
builds. An entry is used only while everything that made it is unchanged:
  - the bytes of the picture's file, a PNG or a JPEG;
  - the screen's picture format and rotation;
  - the encoder: the source of ENCODER_MODULES, and the version of Pillow,
    which decodes the picture, by their hash.
A change to the encoder, or another Pillow, makes every older entry unused,
with nothing to update by hand. Each entry also keeps the hash of its screen
copy, checked when read.

The cache is a SQLite file, pictures.sqlite, in the user's local application
data: %LOCALAPPDATA%\\nxwright on Windows, $XDG_CACHE_HOME/nxwright (by
default ~/.cache/nxwright) elsewhere. The environment variable NXWRIGHT_CACHE
names another folder, or turns the cache off with "off". Past MOST_BYTES of
screen copies, those used longest ago are removed down to KEPT_BYTES, and the
file is compacted.

A cache never makes a build fail: one that cannot be opened, read, or written
is left aside with a warning, and screen copies are made as without it.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sqlite3
import sys
import time

import PIL

import nxwright
from nxwright.project import pictures, screen_copy
from nxwright.project.pictures import read_picture
from nxwright.project.screen_copy import ScreenPixels, encode_screen_copy, stored_pixels

# The modules whose code decides a screen copy's bytes. A test checks that it
# holds every nxwright module they import.
ENCODER_MODULES = (nxwright, pictures, screen_copy, sys.modules[__name__])
MOST_BYTES = 1 << 30
KEPT_BYTES = 768 << 20
FILE_NAME = "pictures.sqlite"
_OFF = "off"
# An entry is found by the hash of its picture's file, `png_hash`, a PNG's or
# a JPEG's: the column keeps its first name, so that existing caches serve.
_SCHEMA = """CREATE TABLE IF NOT EXISTS screen_copies (
    png_hash TEXT, kind INTEGER, rotation INTEGER, fingerprint TEXT,
    width INTEGER, height INTEGER, block BLOB, block_hash TEXT, last_used REAL,
    PRIMARY KEY (png_hash, kind, rotation, fingerprint))"""


@dataclass
class MadeScreenCopy:
    """A picture's screen copy, with the picture's size. `pixels` are those
    encoded, for a screen copy made now; None for one taken from the cache."""
    width: int
    height: int
    block: bytes
    pixels: ScreenPixels = None


def make_screen_copy(picture: bytes, kind: int, rotation: int, cache=None) -> MadeScreenCopy:
    """Returns the screen copy of format `kind` and rotation `rotation` for the
    picture file `picture`, from `cache` (a PictureCache, or None) when it
    has it. One made now is added to the cache. Raises NxwrightError for data
    Pillow does not read as a picture, or a picture the format cannot store."""
    made = cache.get(picture, kind, rotation) if cache is not None else None
    if made is None:
        image = read_picture(picture)
        pixels = stored_pixels(image, kind)
        made = MadeScreenCopy(image.width, image.height, encode_screen_copy(pixels, kind, rotation),
                              pixels)
        if cache is not None:
            cache.add(picture, kind, rotation, made)
    return made


class PictureCache:
    """The cache file at `path`. Entries added are written by `save`, in one
    transaction. Raises sqlite3.Error when the file cannot be opened, and
    `save` when it cannot be written; `opened_cache` turns both into
    warnings. A failed read is a warning, once, and a miss."""

    def __init__(self, path: Path, fingerprint: str):
        self.fingerprint = fingerprint
        self._connection = sqlite3.connect(str(path), timeout=30)
        try:
            self._connection.execute(_SCHEMA)
            self._connection.commit()
        except sqlite3.Error:
            # Such as a file that is not a database: no one else will close it.
            self._connection.close()
            raise
        self._added = []    # rows to insert
        self._used = []     # keys of the entries read
        self._unreadable = False

    def get(self, picture: bytes, kind: int, rotation: int):
        """Returns the MadeScreenCopy kept for these, or None. An entry whose
        screen copy no longer matches its hash is not used."""
        if self._unreadable:
            return None
        key = (_hash(picture), kind, rotation, self.fingerprint)
        try:
            row = self._connection.execute(
                "SELECT width, height, block, block_hash FROM screen_copies WHERE png_hash = ? "
                "AND kind = ? AND rotation = ? AND fingerprint = ?", key).fetchone()
        except sqlite3.Error as error:
            self._unreadable = True
            _warn("cannot be read (%s); pictures are encoded without it" % error)
            return None
        if row is None or _hash(row[2]) != row[3]:
            return None
        self._used.append(key)
        return MadeScreenCopy(row[0], row[1], row[2])

    def add(self, picture: bytes, kind: int, rotation: int, made: MadeScreenCopy):
        """Notes a screen copy made now, to be written by `save`."""
        self._added.append((_hash(picture), kind, rotation, self.fingerprint, made.width, made.height,
                            made.block, _hash(made.block)))

    def save(self):
        """Writes the entries added and when the ones read were used, then
        keeps the cache under its size."""
        now = time.time()
        with self._connection:
            self._connection.executemany(
                "INSERT OR REPLACE INTO screen_copies VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [row + (now,) for row in self._added])
            self._connection.executemany(
                "UPDATE screen_copies SET last_used = ? WHERE png_hash = ? AND kind = ? AND "
                "rotation = ? AND fingerprint = ?", [(now,) + key for key in self._used])
        self._added, self._used = [], []
        self._keep_under(MOST_BYTES, KEPT_BYTES)

    def _keep_under(self, most: int, kept: int):
        """Past `most` bytes of screen copies, removes those used longest ago
        until under `kept`, then compacts the file so that it shrinks too."""
        total = self.size()
        if total <= most:
            return
        removed = []
        for rowid, length in self._connection.execute(
                "SELECT rowid, length(block) FROM screen_copies ORDER BY last_used"):
            if total < kept:
                break
            removed.append((rowid,))
            total -= length
        with self._connection:
            self._connection.executemany("DELETE FROM screen_copies WHERE rowid = ?", removed)
        self._connection.execute("VACUUM")

    def size(self) -> int:
        """Returns the bytes of the screen copies the cache holds."""
        return self._connection.execute(
            "SELECT coalesce(sum(length(block)), 0) FROM screen_copies").fetchone()[0]

    def close(self):
        self._connection.close()


@contextmanager
def opened_cache():
    """Opens the user's picture cache for a build, and yields it, or None
    when it is off or cannot be opened. Saves what was added on leaving,
    even when the build failed, since the screen copies made are good.
    A failure of the cache, at any point, is a warning: the build goes on
    without it, or, when saving, is already done."""
    cache = None
    try:
        folder = cache_folder()
        if folder is not None and _FINGERPRINT is not None:
            folder.mkdir(parents=True, exist_ok=True)
            cache = PictureCache(folder / FILE_NAME, _FINGERPRINT)
    except (sqlite3.Error, OSError) as error:
        _warn("cannot be opened (%s); pictures are encoded without it" % error)
    try:
        yield cache
    finally:
        # Only the cache's own errors are caught here: the build's pass through.
        if cache is not None:
            try:
                cache.save()
            except (sqlite3.Error, OSError) as error:
                _warn("cannot be written (%s); the next build encodes these pictures "
                      "again" % error)
            finally:
                cache.close()


def cache_folder():
    """Returns the folder of the user's cache, or None when NXWRIGHT_CACHE
    turns it off."""
    named = os.environ.get("NXWRIGHT_CACHE")
    if named:
        return None if named.lower() == _OFF else Path(named)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        return (Path(local) if local else Path.home() / "AppData" / "Local") / "nxwright"
    shared = os.environ.get("XDG_CACHE_HOME")
    return (Path(shared) if shared else Path.home() / ".cache") / "nxwright"


def encoder_fingerprint():
    """Returns the hash of ENCODER_MODULES' source and Pillow's version, or
    None when some of the source cannot be read, such as in an installation
    without source files. Pillow's version is in it as another release may
    decode a picture a level otherwise, as JPEG decoders do."""
    digest = hashlib.sha256(PIL.__version__.encode("ascii"))
    try:
        for module in ENCODER_MODULES:
            digest.update(Path(module.__file__).read_bytes())
    except (OSError, TypeError, AttributeError):
        return None
    return digest.hexdigest()


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# Taken once, as this module is imported, so that it describes the code this
# process runs: a source file changed later, while the process runs, must not
# give the screen copies the old code makes the new code's fingerprint.
_FINGERPRINT = encoder_fingerprint()


def _warn(what: str):
    print("nxwright: the picture cache %s" % what, file=sys.stderr)
