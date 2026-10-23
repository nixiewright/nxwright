"""Renaming a name of a source folder: what a code editor's Rename Symbol does.

Components, functions, constants, locals, parameters, and macros can be
renamed. The rename changes every place Find All References lists
(source/references.py): the definition, such as a component's `name = "t0"` in its
page file, and each use, such as `t0.txt`, `settings.t0.txt` on another page,
`vis t0,1`, and the heading `on t0.up:`; a macro's heading and each `call`
of it. Strings and comments are not changed, nor are Python tests naming the
old name. A new name is letters, digits, and underscores: a macro's too,
though its old name may hold spaces.

The rename is refused when the folder built before it and would not after
it, which covers the build's rules for names (their length, a leading "__" in nxlang,
keywords, a name already taken). In a folder that does not build, it goes
ahead without that check.
"""
import re

from nxwright import NxwrightError
from nxwright.source.folder_index import APP_FILE, FolderIndex
from nxwright.source.references import references, targets_at
from nxwright.source.folder_check import check_folder

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def rename(index: FolderIndex, path: str, line: int, column: int, new_name: str,
           read, exists) -> dict:
    """Returns {file: [(Place, new text)]}, the edits renaming the name at a
    place to `new_name`. `read(path)` returns a file of the folder, raising
    NxwrightError for a missing one, and `exists(path)` tells which exist.

    Raises NxwrightError saying why a rename is refused."""
    targets = targets_at(index, path, line, column)
    if not targets:
        raise NxwrightError("there is no name to rename here")
    pages = {objects[0].place for objects in index.page_objects.values() if objects}
    if any(target.end == 0 or target.path == APP_FILE or target in pages for target in targets):
        raise NxwrightError("pages, pictures, fonts, animations, videos, sounds, and files "
                            "are renamed by hand")
    if not _NAME.fullmatch(new_name):
        raise NxwrightError("%r is not a name" % new_name)
    edits = {}
    for place in references(index, path, line, column, with_declarations=True):
        edits.setdefault(place.path, []).append((place, new_name))
    if not check_folder(read, exists).errors():
        texts = {file: _edited(read(file), file_edits) for file, file_edits in edits.items()}
        errors = check_folder(lambda file: texts[file] if file in texts else read(file),
                              exists).errors()
        if errors:
            place = "%s line %d" % (errors[0].file, errors[0].line) if errors[0].line \
                else errors[0].file
            raise NxwrightError("the folder would not build after the rename: %s: %s"
                                % (place, errors[0].message))
    return edits


def _edited(text: str, edits: list) -> str:
    """Returns `text` with each (Place, new text) of `edits` applied."""
    lines = text.split("\n")
    for place, new_text in sorted(edits, key=lambda edit: (edit[0].line, edit[0].start),
                                  reverse=True):
        line = lines[place.line]
        lines[place.line] = line[:place.start] + new_text + line[place.end:]
    return "\n".join(lines)
