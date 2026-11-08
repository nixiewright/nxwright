"""Renaming a name of a source folder: what a code editor's Rename Symbol does.

Pages, components, functions, constants, locals, parameters, and macros can be
renamed. The rename changes every place that Find All References lists
(source/references.py). For a component, that is its definition, such as
`name = "t0"` in its page file, and each use, such as `t0.txt`,
`settings.t0.txt` on another page, `vis t0,1`, and the heading `on t0.up:`.
For a macro, it is the macro's heading and each `call` of it. Strings,
comments, and Python tests that use the old name are not changed. A new name
may contain only letters, digits, and underscores, even for a macro whose old
name contains spaces.

Renaming a page also moves its files and changes its entry in app.toml
(source/page_renaming.py). A page's new name must be one that
`nxwright new-page` would take. Unlike other new names, it may contain
hyphens.

The rename is rejected when the folder built before it and would not build
after it. That check covers the build's rules for names (their length, a
leading "__" in nxlang, keywords, a name already taken). In a folder that does
not build, a page's rename is rejected, and any other rename goes ahead
without the check.
"""
import re

from nxwright import NxwrightError
from nxwright.source.folder_index import APP_FILE, FolderIndex
from nxwright.source.references import references, targets_at, text_with_edits
from nxwright.source.folder_check import check_folder
from nxwright.source.page_renaming import page_rename
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import folder_lister

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def rename(index: FolderIndex, path: str, line: int, column: int, new_name: str,
           read, exists) -> dict:
    """Returns the changes that rename the name at a place to `new_name`, as
    {"edits": {file: [(Place, new text)]}, "moves": [(old path, new path)]}.
    Only a page's rename moves files, and its edits are keyed by each file's
    path before the moves. `read(path)` returns a file of the folder, raising
    NxwrightError for a missing one, and `exists(path)` returns whether a file
    exists.

    Raises NxwrightError saying why a rename is refused."""
    targets = targets_at(index, path, line, column)
    if not targets:
        raise NxwrightError("there is no name to rename here")
    page = _page_named(index, targets)
    if page is not None:
        moves, edits = page_rename(index, read, exists, folder_lister(index.root), page,
                                   new_name)
        return {"edits": edits, "moves": moves}
    if any(target.end == 0 or target.path == APP_FILE for target in targets):
        raise NxwrightError("pictures, fonts, animations, videos, and sounds are renamed with "
                            "nxwright rename or from the Media section, and files by hand")
    if not _NAME.fullmatch(new_name):
        raise NxwrightError("%r is not a name" % new_name)
    edits = {}
    for place in references(index, path, line, column, with_declarations=True):
        edits.setdefault(place.path, []).append((place, new_name))
    listed = folder_lister(index.root)
    if not check_folder(read, exists, listed=listed).errors():
        texts = {file: text_with_edits(read(file), file_edits)
                 for file, file_edits in edits.items()}
        errors = check_folder(lambda file: texts[file] if file in texts else read(file),
                              exists, listed=listed).errors()
        if errors:
            place = "%s line %d" % (errors[0].file, errors[0].line) if errors[0].line \
                else errors[0].file
            raise NxwrightError("the folder would not build after the rename: %s: %s"
                                % (place, errors[0].message))
    return {"edits": edits, "moves": []}


def _page_named(index: FolderIndex, targets: list):
    """Returns the page whose name `targets` define, or None. A target defines
    a page's name if it is the name in the page's `[page]` table, or if it is
    the whole page file. Go to Definition on a page's name in app.toml or in
    code can lead to the whole file."""
    for page, objects in index.page_objects.items():
        if objects and objects[0].place in targets:
            return page
        if any(target.path == page_toml_path(page) and target.end == 0 for target in targets):
            return page
    return None
