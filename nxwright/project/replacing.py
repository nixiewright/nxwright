"""Replacing an existing file with a new one, for the commands that write a
project file (nxwright build and write), a TFT file (nxwright compile and
rescue), or a page file (nxwright page).

Each command replaces only a file of its own kind (is_project_file,
is_page_file), so that a mistyped output, such as a file of the source folder,
is refused. The new file is written beside the existing one first, and replaces
it only once it is written in full (written_beside), so a write that fails
leaves the existing file as it was.

A backup is a copy of the file about to be replaced. It sits beside that file,
and its name adds the time to the file's name, such as
app.HMI.2026-11-06-143205.bak. A project file or a TFT file gets a backup when
it changed since nxwright last wrote it (written_files.py), unless the user
turns that off.
"""
from contextlib import contextmanager, suppress
from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import secrets
import shutil

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer
from nxwright.project.stamp import block_stamp
from nxwright.project.written_files import record_hash, recorded_hash

# The bytes a page file's stamp covers end at its byte 21 (stamp.py).
_SHORTEST_PAGE_FILE = 22
# What follows `<file's name>.` in a backup's name, with its optional number.
_BACKUP_ENDING = re.compile(r"\d{4}-\d{2}-\d{2}-\d{6}(-\d+)?\.bak")


@contextmanager
def held_by_the_nextion_editor(project: Path):
    """Raises NxwrightError, with advice, for a refusal of the project file
    `project` itself ("Permission denied"): the Nextion Editor 1.68.2 kept a
    project it had open from being read or written. A read-only file is
    refused alike, so the advice says "if". A refusal of another file keeps
    its own words."""
    try:
        yield
    except PermissionError as error:
        refused = {Path(name).resolve() for name in (error.filename, error.filename2) if name}
        if project.resolve() not in refused:
            raise
        raise NxwrightError("%s: %s; if the Nextion Editor has the project open, it keeps the "
                            "file from being read or written: close it there, then try again"
                            % (project, error.strerror)) from None


def is_project_file(path: Path) -> bool:
    """Tells whether `path` is a file holding a valid project directory, the
    only kind of file nxwright build and write replace. Raises
    NxwrightError, with advice, when the Nextion Editor keeps it from being
    read."""
    with held_by_the_nextion_editor(path):
        if not path.is_file():
            return False
        try:
            return HmiContainer.from_file(path).directory_checksum_is_valid()
        except NxwrightError:
            return False


def is_page_file(path: Path) -> bool:
    """Tells whether `path` is a file holding a page file: its first 4 bytes
    are the stamp its other bytes give (stamp.block_stamp). It is the only
    kind of file nxwright page replaces."""
    if not path.is_file():
        return False
    data = path.read_bytes()
    return len(data) >= _SHORTEST_PAGE_FILE and \
        block_stamp(data) == int.from_bytes(data[:4], "little")


@contextmanager
def written_beside(output: Path, keep_backup: bool = False):
    """Gives the path to write the new file at: `<name>.<random>.partial`, in
    the same folder as `output`, so that the replace stays on one drive. Once
    the with block ends without an error, the new file replaces `output`. An
    error while writing or checking the new file leaves `output` as it was, and
    the .partial file is removed either way.

    With `keep_backup`, `output` is first copied to a backup if it may contain
    work found nowhere else (_backup_of), and the new file is recorded as what
    nxwright last wrote there. If the backup cannot be written, this raises
    NxwrightError and leaves `output` as it was. If the replace fails, the
    backup is removed again. Nothing removes older backups."""
    written = output.with_name("%s.%s.partial" % (output.name, secrets.token_hex(4)))
    try:
        yield written
        new_hash = _hash_of(written) if keep_backup else None
        backup = _backup_of(output, new_hash) if keep_backup else None
        try:
            os.replace(written, output)
        except OSError:
            if backup is not None:
                with suppress(OSError):
                    backup.unlink()
            raise
        if keep_backup:
            record_hash(output, new_hash)
    finally:
        written.unlink(missing_ok=True)


def _hash_of(path: Path) -> str:
    with open(path, "rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _newest_backup(output: Path):
    """Returns the newest backup of `output` in its own folder, or None,
    going by the time each was modified, which is when it was made. Names are
    compared as plain text, so that a name containing a character such as `[`
    matches only itself. A file with another name is never a backup of
    `output`, and neither is a folder. For backups with the same time, the
    longer name is the newer, since its number was added later."""
    prefix = output.name + "."
    found = [path for path in output.parent.iterdir()
             if path.name.startswith(prefix) and
             _BACKUP_ENDING.fullmatch(path.name[len(prefix):]) and path.is_file()]
    return max(found, default=None,
               key=lambda path: (path.stat().st_mtime_ns, len(path.name), path.name))


def _free_backup_path(output: Path) -> Path:
    """Returns a backup's path for `output` that no file has, adding a number
    when another backup was made in the same second."""
    stem = "%s.%s" % (output.name, datetime.now().strftime("%Y-%m-%d-%H%M%S"))
    path = output.with_name(stem + ".bak")
    number = 0
    while path.exists():
        number += 1
        path = output.with_name("%s-%d.bak" % (stem, number))
    return path


def _backup_of(output: Path, new_hash: str):
    """Copies `output` to a backup if it may contain work found nowhere else.
    `new_hash` is the hash of the file about to replace `output`. Returns the
    backup's path, or None if no backup is needed, because `output` does not
    exist, or has the same bytes as the new file, as what nxwright last wrote
    there, or as its newest backup."""
    if not output.exists():
        return None
    old_hash = _hash_of(output)
    if old_hash in (new_hash, recorded_hash(output)):
        return None
    newest = _newest_backup(output)
    if newest is not None and _hash_of(newest) == old_hash:
        return None
    backup = _free_backup_path(output)
    # An error from opening `output` itself passes through unchanged, because
    # held_by_the_nextion_editor gives its own advice for that error.
    with open(output, "rb") as old:
        try:
            with written_beside(backup) as partial, open(partial, "wb") as copy:
                shutil.copyfileobj(old, copy)
        except OSError as error:
            raise NxwrightError("%s was not replaced, because its backup could not be written "
                                "(%s); to replace it without one, pass --no-backup, or turn off "
                                "the nxwright.backups setting in VS Code"
                                % (output, error)) from None
    return backup
