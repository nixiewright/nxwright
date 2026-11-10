"""Removing a resource from a source folder (`nxwright remove`): a picture, a
font, an animation, a video, or a sound, its files, and its name in
app.toml.

A removal does not look at the rest of the folder, unless it is checked
(`nxwright remove --checked`). After an unchecked removal, a page file or
code that used the resource by name no longer builds, and a number that
gave a later resource's ID stands for another resource. Every removal is
refused for a kind or a name the folder does not have.

A checked removal is also refused, writing nothing, while the folder uses
the resource by its name, or uses a number from its ID to the last ID of its
kind. Those numbers count because a removal gives each later resource of
its kind an ID one lower: a name follows its resource, but a number would
silently stand for another resource. The uses looked for are:
  - by name, wherever the language server's Find All References finds it
    (references.py), from its name in app.toml;
  - in a page file, an attribute that takes a resource of its kind,
    whether written there or left to the defaults, such as a text's `font`
    of 0;
  - in code, a number written there or given by an nxlang constant, where
    a resource of its kind is taken (_uses_in_code).
A number that code computes, or keeps in a variable, is not seen. The
checks that `nxwright check` runs come first, because a file they cannot
read could hide a use.

A removal can instead leave a placeholder in the resource's place
(remove_keeping_ids), so that no ID changes. When it is checked, it fails
only while the folder uses the resource itself. removal_report gives what a
removal would affect, writing nothing.

The language server's index imports source_folder.py, so this module, which
only the command imports, stands apart from it.
"""
import dataclasses
from dataclasses import dataclass
from pathlib import Path
import tomllib

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.resource_names import LISTS, NOUNS
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.folder_index import APP_FILE, FolderIndex, text_on_disk
from nxwright.source.references import references
from nxwright.source.folder_check import check_folder
from nxwright.source.defines import placeholder_name
from nxwright.source.page_source import page_data, page_toml_path, reference_kind
from nxwright.source.resource_adding import Slot, add_placeholder
from nxwright.source.resource_numbers import code_lines, resource_numbers
from nxwright.source.source_folder import (app_text_in, delete_files, folder_lister,
                                           folder_reader, number_in_table, read_app,
                                           read_folder_source, resource_file_paths)

# The kinds the command takes, by the word it takes them as: "picture".
KINDS = {noun: kind for kind, noun in NOUNS.items()}


@dataclass(frozen=True)
class ResourceUse:
    """A place where a folder uses a resource: line `line`, counted from 1,
    of the folder's file `path`, whose text is `text`; or, for a number a
    component leaves to the defaults, a sentence saying so. `by` is "name"
    or "number". `of` is "itself" when it stands for the resource, by its
    name or its own ID, and "later" when it is the ID of a later resource of
    its kind, which a removal would change."""
    path: str
    line: int
    text: str
    by: str
    of: str

    def __str__(self):
        return "%s line %d: %s" % (self.path, self.line, self.text)


def remove_resource(source_folder: Path, kind: str, name: str, checked: bool = False) -> tuple:
    """Removes the resource `name` of `kind`, one of the words in KINDS, from
    the source folder (see the module's docstring). Returns (the paths
    deleted, a sentence for each file that could not be deleted). Raises
    NxwrightError, writing nothing, for a kind or a name the folder does not
    have. With `checked`, also raises it for a folder whose checks find an
    error, and for a resource the folder uses, listing each use."""
    source_folder = Path(source_folder)
    listed, uses = _list_and_uses(source_folder, kind, name, checked)
    _refuse_for(kind, name, uses)
    return remove_resource_files(source_folder, listed, name)


def removal_report(source_folder: Path, kind: str, name: str) -> dict:
    """Returns what removing the resource `name` of `kind` would affect,
    writing nothing: {"kind", "name", "id", "encoding" (the folder's),
    "last" (whether it is the last of its kind), "later" (the names of the
    later ones), "uses"}, each use {"path", "line", "text", "by", "of"}
    (ResourceUse). Raises NxwrightError as remove_resource does, but not for
    the uses."""
    source_folder = Path(source_folder)
    _, names, uses = resource_uses(source_folder, kind, name)
    place = names.index(name)
    return {"kind": kind, "name": name, "id": place,
            "encoding": read_app(source_folder).get("encoding"),
            "last": place == len(names) - 1, "later": names[place + 1:],
            "uses": [dataclasses.asdict(use) for use in uses]}


def remove_keeping_ids(source_folder: Path, kind: str, name: str,
                       checked: bool = False) -> tuple:
    """Removes the resource `name` of `kind`, writing a placeholder into its
    place (resource_adding.add_placeholder), so that no later resource's ID
    changes. Returns (the placeholder's name, the old files deleted, a
    sentence for each that could not be). Raises NxwrightError, writing
    nothing, in the same cases as remove_resource, except that with
    `checked` only uses of the resource itself count, by name or by its own
    ID."""
    source_folder = Path(source_folder)
    listed, uses = _list_and_uses(source_folder, kind, name, checked)
    _refuse_for(kind, name, [use for use in uses if use.of == "itself"])
    slot = Slot(name)
    placeholder = add_placeholder(source_folder, listed, slot)
    return placeholder, slot.deleted, slot.left


def _refuse_for(kind: str, name: str, uses: list):
    """Raises NxwrightError naming each of `uses`, if there are any."""
    if uses:
        raise NxwrightError("%s %s is used, so it stays:\n%s"
                            % (kind, name, "\n".join("  %s" % use for use in uses)))


def _list_and_uses(source_folder: Path, kind: str, name: str, checked: bool) -> tuple:
    """Returns (the name of app.toml's list of the kind, the uses of the
    resource `name` of `kind` that stop a removal). With `checked`, the uses
    are those resource_uses finds. Without `checked`, the folder is not
    searched, and the list of uses is empty. Raises NxwrightError for a kind
    or a name the folder does not have, and with `checked` for a folder
    whose checks find an error."""
    if checked:
        listed, _, uses = resource_uses(source_folder, kind, name)
        return listed, uses
    return _list_with(source_folder, kind, name)[0], []


def _list_with(source_folder: Path, kind: str, name: str) -> tuple:
    """Returns (the name of app.toml's list for the kind, the names in that
    list), where `kind` is a word of KINDS. Raises NxwrightError for a kind
    that is not in KINDS, and for a list that does not have `name`."""
    if kind not in KINDS:
        raise NxwrightError("%s is not a kind of resource: %s" % (kind, ", ".join(KINDS)))
    listed = LISTS[KINDS[kind]]
    names = read_app(source_folder)[listed]
    if name not in names:
        raise NxwrightError("the folder has no %s named %s" % (kind, name))
    return listed, names


def resource_uses(source_folder: Path, kind: str, name: str) -> tuple:
    """Returns (the name of app.toml's list of the kind, the names in that
    list, the uses) of the resource `name` of `kind`, a word of KINDS. The
    uses are ResourceUse records, by its name, and by a number from its ID
    to the last ID of its kind. The folder's checks run first. Raises
    NxwrightError for a kind or a name the folder does not have, and a
    folder whose checks find an error."""
    listed, names = _list_with(source_folder, kind, name)
    read = folder_reader(source_folder)
    errors = check_folder(read, lambda path: (source_folder / path).is_file(),
                          listed=folder_lister(source_folder)).errors()
    if errors:
        first = errors[0]
        raise NxwrightError("the folder's checks find an error, so its uses of %s %s cannot "
                            "all be found: %s: %s" % (kind, name, first.place, first.message))
    index = FolderIndex(source_folder, text_on_disk)
    folder = read_folder_source(read)
    own = names.index(name)
    ids = range(own, len(names))
    uses = (_uses_by_name(index, listed, name)
            + _uses_in_page_files(folder, index, KINDS[kind], ids, own, name)
            + _uses_in_code(folder, index, KINDS[kind], ids, own))
    return listed, names, uses


def remove_resource_files(source_folder: Path, listed: str, name: str) -> tuple:
    """Takes the resource `name` out of app.toml's list `listed`, then
    deletes each of its files (source_folder.resource_file_paths), by its
    own path, and never a folder (source_folder.delete_files). Returns (the
    paths deleted, a sentence for each file that could not be deleted), all
    paths within the folder.

    app.toml is written first, so that a failure can leave a file that
    app.toml does not list, but never a listed name whose file is gone. The
    function does not check whether the folder uses the resource: a checked
    remove_resource does that first."""
    app = read_app(source_folder)
    paths = resource_file_paths(source_folder, listed, name)
    app[listed] = [listed_name for listed_name in app[listed] if listed_name != name]
    (source_folder / "app.toml").write_text(app_text_in(source_folder, app), encoding="utf-8",
                                            newline="\n")
    return delete_files(source_folder, paths)


def use_at(index: FolderIndex, path: str, number: int, by: str, of: str) -> ResourceUse:
    """The use on line `number`, counted from 1, of the file `path`."""
    return ResourceUse(path, number, index.lines(path)[number - 1].strip(), by, of)


def _of(value: int, own: int) -> str:
    """Whether the ID `value` is the resource's own, `own`, or a later one's."""
    return "itself" if value == own else "later"


def _uses_by_name(index: FolderIndex, listed: str, name: str) -> list:
    """The places outside app.toml that Find All References finds for the
    resource `name` of app.toml's list `listed`."""
    entry = index.app_entries[(listed, name)]
    return [use_at(index, place.path, place.line + 1, "name", "itself")
            for place in references(index, entry.path, entry.line, entry.start, False)
            if place.path != APP_FILE]


def _uses_in_page_files(folder, index: FolderIndex, kind: str, ids: range, own: int,
                        name: str) -> list:
    """Returns where the page files use a resource of `kind`, in an attribute
    that takes one. A use is a number in `ids`, written in the page file or
    taken from the defaults, a use of the resource itself where it is `own`,
    its own ID; or the resource's `name`, given through a define's
    placeholder, such as "%LOGO%".
    _uses_by_name finds a name written directly in the page file."""
    uses = []
    for page in folder.app["pages"]:
        path = page_toml_path(page)
        text = "\n".join(index.lines(path))
        data = page_data(text, page, folder.app.get("defines"))
        written = tomllib.loads(text)
        for table, as_written in zip(_tables(data), _tables(written)):
            object_type = TYPES_BY_NAME.get(table.get("type"))
            if object_type is None:
                continue
            defaults = folder.defaults.get(object_type)
            for attribute in dict.fromkeys([*table, *(defaults.names() if defaults else [])]):
                if reference_kind(object_type, attribute) != kind:
                    continue
                value = number_in_table(table, folder.defaults, attribute)
                if isinstance(value, int) and value in ids:
                    uses.append(_page_file_use(index, path, table, attribute, value, "number",
                                               _of(value, own)))
                elif (placeholder_name(as_written.get(attribute)) is not None
                      and table.get(attribute) == name):
                    uses.append(_page_file_use(index, path, table, attribute, name, "name",
                                               "itself"))
    return uses


def _tables(data: dict) -> list:
    """Returns the tables of a parsed page file, the [page] table first."""
    components = data.get("component", [])
    return [data.get("page", {})] + (components if isinstance(components, list) else [])


def _page_file_use(index: FolderIndex, path: str, table: dict, attribute: str,
                   value, by: str, of: str) -> ResourceUse:
    """Returns the use where a page file's `table` gives `attribute` the
    value `value`, a number or a resource's name, `by` one or the other. Its
    place is the attribute's own line, or the table's name line, with a
    sentence saying so, when the value comes from the defaults."""
    lines = index.lines(path)
    name = table.get("name")
    name_line = next((number for number, line in enumerate(lines)
                      if line.strip() == 'name = "%s"' % name), 0)
    if attribute in table:
        given = next((number for number in range(name_line, len(lines))
                      if lines[number].split("=")[0].strip() == attribute), name_line)
        return use_at(index, path, given + 1, by, of)
    return ResourceUse(path, name_line + 1, "%s leaves out its %s, so it takes %s from the "
                       "defaults" % (name, attribute, value), by, of)


def _uses_in_code(folder, index: FolderIndex, kind: str, ids: range, own: int) -> list:
    """The lines of the folder's code where a number of `ids` stands for a
    resource of `kind`, a use of the resource itself where one of them is
    `own`, its own ID. The code is read as the build reads it, but with its
    names standing for no resource, so that only the numbers it writes, and
    those nxlang's constants give, are seen. A file several pages include is
    read for each of them (resource_numbers.code_lines)."""
    uses = []
    for (path, number), found in code_lines(folder, index).items():
        if not number:
            continue
        values = {value for page, code in found
                  for taken, value in resource_numbers(folder.page_objects, page,
                                                       split_line(code, 0)[1].strip())
                  if taken == kind and value in ids}
        if values:
            uses.append(use_at(index, path, number, "number",
                               "itself" if own in values else "later"))
    return uses
