"""Renaming a resource of a source folder (`nxwright rename`). The resource's
files move to the new name, and its name in app.toml changes where it
stands, so that its ID stays the same. Each use of its name that Find All
References finds (references.py) changes too, such as `pic = "logo"` in a
page file or `@pic(logo)` in code.

Every edit is worked out before anything is written. The files are then
moved, and app.toml and the files that use the name are written. If any step
fails, everything is put back as it was.

A rename does not run the folder's checks, unless it is a checked rename
(`nxwright rename --checked`). A checked rename runs them before the edits,
because an error could hide a use of the name, and again on the folder as
the edits would leave it. If either run finds an error, nothing is written.
"""
import codecs
from pathlib import Path

from nxwright import NxwrightError
from nxwright.language.resource_names import LISTS
from nxwright.source.folder_check import check_folder
from nxwright.source.folder_index import APP_FILE, FolderIndex, text_on_disk
from nxwright.source.references import references, text_with_edits
from nxwright.source.resource_adding import Slot, check_resource_name
from nxwright.source.resource_removal import KINDS
from nxwright.source.source_folder import (app_text_in, folder_file_exists, folder_lister,
                                           folder_reader, put_back, read_app,
                                           resource_file_paths)

# The suffix of a file's temporary name while its name changes only in letter
# case, such as from `logo.png` to `Logo.png` on a file system that ignores
# letter case.
_RENAMING_SUFFIX = ".renaming"


def rename_resource(source_folder: Path, kind: str, name: str, new_name: str,
                    checked: bool = False) -> list:
    """Renames the resource `name` of `kind`, a word of KINDS, to `new_name`,
    as the module's docstring says. Returns the paths, within the folder, of
    the files written: those moved, under their new names, and those edited.

    Raises NxwrightError, writing nothing, for a kind or a name the folder
    does not have, a new name that is the old one, that another resource of
    its kind has in any letter case, or that app.toml may not contain, and a
    file already where a moved one would go. With `checked`, also raises it
    for a folder whose checks find an error, before or after the edits. A
    failure while moving or writing puts back what was done, and is raised."""
    source_folder = Path(source_folder)
    if kind not in KINDS:
        raise NxwrightError("%s is not a kind of resource: %s" % (kind, ", ".join(KINDS)))
    listed = LISTS[KINDS[kind]]
    app = read_app(source_folder)
    if name not in app[listed]:
        raise NxwrightError("the folder has no %s named %s" % (kind, name))
    if new_name == name:
        raise NxwrightError("the %s is named %s already" % (kind, name))
    check_resource_name(source_folder, app, listed, new_name, Slot(name))
    read, exists = folder_reader(source_folder), folder_file_exists(source_folder)
    lister = folder_lister(source_folder)
    if checked:
        check_builds(read, exists, lister, "the folder's checks find an error, so its uses of "
                                           "%s %s cannot all be found" % (kind, name))
    moves = [(old, listed + "/" + new_name + old[len(listed) + 1 + len(name):])
             for old in resource_file_paths(source_folder, listed, name)]
    for old, new in moves:
        target = source_folder / new
        if target.exists() and not target.samefile(source_folder / old):
            raise NxwrightError("%s is already there, though app.toml does not list it" % target)
    texts = _edited_texts(source_folder, read, listed, name, new_name)
    renamed = [new_name if known == name else known for known in app[listed]]
    texts[APP_FILE] = app_text_in(source_folder, dict(app, **{listed: renamed}))
    if checked:
        check_builds(*as_renamed(read, exists, lister, texts, moves),
                     "the folder would not build after the rename")
    move_files(source_folder, moves)
    try:
        write_texts(source_folder, texts)
    except Exception:
        move_files(source_folder, [(new, old) for old, new in reversed(moves)])
        raise
    return [new for _, new in moves] + list(texts)


def check_builds(read, exists, lister, why: str):
    """Raises NxwrightError, saying `why`, when the folder's checks, reading
    it through `read`, `exists`, and `lister`, find an error."""
    errors = check_folder(read, exists, listed=lister).errors()
    if errors:
        first = errors[0]
        raise NxwrightError("%s: %s: %s" % (why, first.place, first.message))


def _edited_texts(source_folder: Path, read, listed: str, name: str, new_name: str) -> dict:
    """Returns {path: its new text} for each file holding a use of the
    resource `name` of `listed` by name, the uses given `new_name`."""
    index = FolderIndex(source_folder, text_on_disk)
    entry = index.app_entries[(listed, name)]
    edits = {}
    for place in references(index, entry.path, entry.line, entry.start, False):
        if place.path != APP_FILE:
            edits.setdefault(place.path, []).append((place, new_name))
    return {path: text_with_edits(read(path), file_edits) for path, file_edits in edits.items()}


def as_renamed(read, exists, lister, texts: dict, moves: list) -> tuple:
    """Returns (read, exists, lister) of the folder as the rename would leave
    it: the files of `texts` holding their new texts, and each file of
    `moves`, (old path, new path), at its new path."""
    moved = {new: old for old, new in moves}
    gone = {old for old, _ in moves} - set(moved)

    def read_renamed(path: str) -> str:
        return texts[path] if path in texts else read(moved.get(path, path))

    def exists_renamed(path: str) -> bool:
        return path in moved or (path not in gone and exists(path))

    def list_renamed(folder: str) -> list:
        names = [file for file in lister(folder) if "%s/%s" % (folder, file) not in gone]
        names += [new.rpartition("/")[2] for new in moved if new.rpartition("/")[0] == folder]
        return sorted(set(names))

    return read_renamed, exists_renamed, list_renamed


def move_files(source_folder: Path, moves: list):
    """Renames each file of `moves`, (old path, new path), making the folders
    a new path needs. A change of letter case alone goes through a
    temporary name first, because file names may ignore letter case. If a
    rename fails, the files already renamed are put back, and the error is
    raised."""
    done = []
    try:
        for old, new in moves:
            source, target = source_folder / old, source_folder / new
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.samefile(source):
                passing = source.with_name(source.name + _RENAMING_SUFFIX)
                source.rename(passing)
                try:
                    passing.rename(target)
                except Exception:
                    passing.rename(source)
                    raise
            else:
                source.rename(target)
            done.append((old, new))
    except Exception:
        for old, new in reversed(done):
            (source_folder / new).rename(source_folder / old)
        raise


def write_texts(source_folder: Path, texts: dict):
    """Writes each file of `texts`, {path: its new text}, keeping its line
    endings and any byte order mark. If a write fails, the files already
    written are put back as they were, and the error is raised."""
    before = {path: (source_folder / path).read_bytes() for path in texts}
    # Each file is noted before it is written, so that one whose own write
    # fails partway is put back too.
    touched = []
    try:
        for path, text in texts.items():
            touched.append((source_folder / path, before[path]))
            (source_folder / path).write_bytes(_encoded_like(text, before[path]))
    except Exception:
        put_back(touched)
        raise


def _encoded_like(text: str, original: bytes) -> bytes:
    """Returns `text`, whose lines end in LF, encoded in UTF-8 as the file
    `original` was: with CRLF line endings, and a byte order mark, where it
    had them."""
    if b"\r\n" in original:
        text = text.replace("\n", "\r\n")
    data = text.encode("utf-8")
    return codecs.BOM_UTF8 + data if original.startswith(codecs.BOM_UTF8) else data
