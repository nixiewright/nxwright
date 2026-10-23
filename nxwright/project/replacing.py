"""Replacing an existing file with a new one, for the commands that write a
project file (nxwright build and write) or a page file (nxwright page).

Each replaces only a file of its own kind (is_project_file, is_page_file),
so that a mistyped output, such as a file of the source folder, is refused.
The new file is written beside the existing one first, and replaces it only
once it is written in full (written_beside). So a write that fails leaves
the existing file as it was.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import secrets

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer
from nxwright.project.stamp import block_stamp

# The bytes a page file's stamp covers end at its byte 21 (stamp.py).
_SHORTEST_PAGE_FILE = 22


@contextmanager
def held_by_the_nextion_editor(project: Path):
    """Raises NxwrightError, with advice, for a refusal of the project file
    `project` itself ("Permission denied"): the Nextion Editor 3.1.73 kept a
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
def written_beside(output: Path):
    """Gives the path to write the new file at: beside `output`, as
    `<name>.<random>.partial`, in the same folder, so that the replace stays
    on one drive. Once the with block ends without an error, the new file
    replaces `output`. Whatever happens, the .partial file is gone
    afterwards, so an error while writing or checking the new file leaves
    `output` as it was."""
    written = output.with_name("%s.%s.partial" % (output.name, secrets.token_hex(4)))
    try:
        yield written
        os.replace(written, output)
    finally:
        written.unlink(missing_ok=True)
