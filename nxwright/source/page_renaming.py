"""Renaming a page of a source folder, for `nxwright rename <folder> page`
and for the language server's rename.

The rename moves the page's page file and `.nx` file to the paths of the
new name (page_toml_path and page_nx_path). It also changes each use of the
name that Find All References finds (references.py): the name in the page's
`[page]` table, headings such as `on settings.load`, and code such as
`page settings` or `settings.t0.txt`. The page's entry in app.toml's `pages`
is changed in place, so the page keeps its ID.

The new name must be a plain name, one that `nxwright new-page` would take
(source_folder.check_new_page_name). It may also be the old name in another
letter case. The old name does not have to be plain. A page extracted from a
project can have a name such as `a:b`. Its files then have encoded names,
code cannot use its name, and its event headings quote it, as in
`on "a:b".load`. The rename changes those headings too.

The rename is rejected if the folder's checks find an error before it,
because an error could hide a use of the name, or if they would find one
after it.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.source.folder_index import FolderIndex, text_on_disk
from nxwright.source.page_source import page_nx_path, page_toml_path
from nxwright.source.references import references, text_with_edits
from nxwright.source.resource_renaming import as_renamed, check_builds, move_files, write_texts
from nxwright.source.source_folder import (check_new_page_name, folder_file_exists,
                                           folder_lister, folder_reader)


def page_rename(index: FolderIndex, read, exists, lister, page: str, new_name: str) -> tuple:
    """Returns (moves, edits), which rename the page `page` to `new_name`,
    without writing anything. `moves` lists (old path, new path) for each of
    the page's files. `edits` is {path: [(Place, new text)]}, keyed by each
    file's path before the moves. The folder is read through `read(path)`,
    `exists(path)`, and `lister(folder)`.

    Raises NxwrightError if the folder has no page `page`, if `new_name` is
    the old name or one that check_new_page_name rejects, if a file is
    already where a moved one would go, or if the folder's checks find an
    error before or after the rename."""
    if page not in index.pages:
        raise NxwrightError("the folder has no page named %s" % page)
    if new_name == page:
        raise NxwrightError("the page is named %s already" % page)
    check_new_page_name(new_name, index.pages, renamed=page)
    check_builds(read, exists, lister, "the folder's checks find an error, so the uses of the "
                                       "page %s cannot all be found" % page)
    moves = [(old, new) for old, new in ((page_toml_path(page), page_toml_path(new_name)),
                                         (page_nx_path(page), page_nx_path(new_name)))
             if exists(old)]
    for old, new in moves:
        # If only the letter case changes, and file names ignore letter case,
        # the file at the new path is the page's own file.
        if exists(new) and new.lower() != old.lower():
            raise NxwrightError("%s is already there, though app.toml does not list it" % new)
    own = index.page_objects[page][0].place
    places = references(index, own.path, own.line, own.start, with_declarations=True)
    places.append(index.app_entries[("pages", page)])
    edits = {}
    for place in dict.fromkeys(places):
        edits.setdefault(place.path, []).append((place, new_name))
    moved = dict(moves)
    texts = {moved.get(path, path): text_with_edits(read(path), file_edits)
             for path, file_edits in edits.items()}
    check_builds(*as_renamed(read, exists, lister, texts, moves),
                 "the folder would not build after the rename")
    return moves, edits


def rename_page(source_folder: Path, page: str, new_name: str) -> list:
    """Renames the page `page` of a source folder to `new_name`. Returns the
    paths, within the folder, of the files written: those moved, under their
    new names, and those edited.

    Raises NxwrightError, before writing anything, for the reasons that
    page_rename gives. If moving or writing fails, the files are put back as
    they were, and the error is raised."""
    source_folder = Path(source_folder)
    read = folder_reader(source_folder)
    moves, edits = page_rename(FolderIndex(source_folder, text_on_disk), read,
                               folder_file_exists(source_folder), folder_lister(source_folder),
                               page, new_name)
    moved = dict(moves)
    texts = {moved.get(path, path): text_with_edits(read(path), file_edits)
             for path, file_edits in edits.items()}
    move_files(source_folder, moves)
    try:
        write_texts(source_folder, texts)
    except Exception:
        move_files(source_folder, [(new, old) for old, new in reversed(moves)])
        raise
    return list(dict.fromkeys([new for _, new in moves] + list(texts)))
