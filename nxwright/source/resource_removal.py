"""Removing a resource from a source folder (`nxwright remove`): a picture, a
font, an animation, a video, or a sound, its files, and its name in
app.toml.

A removal gives each later resource of its kind an ID one lower. A name
follows its resource, but a number standing for an ID does not: it would
then stand for another resource, without a word. So the removal is refused,
writing nothing, while the folder uses the resource by its name, or by a
number from its ID to the last ID of its kind:
  - by name, wherever the language server's Find All References finds it
    (references.py), from its name in app.toml;
  - by number, in a page file, an attribute taking a resource of its kind,
    written there or left to the defaults, as a text's `font` of 0; and in
    code, a number written there or given by an nxlang constant, where a
    resource of its kind is taken (_uses_in_code).
A number code computes, or keeps in a variable, is not seen. The folder's
checks run first, as `nxwright check` runs them, as a file they cannot read
could hide a use.

The language server's index imports source_folder.py, so this module, which
only the command imports, stands apart from it.
"""
import dataclasses
from pathlib import Path
import re
import tomllib

from nxwright import NxwrightError
from nxwright.language.code_checks import PICTURE_ARGUMENTS, XSTR_FONT_ARGUMENT
from nxwright.language.code_lines import command_arguments, command_word, split_line
from nxwright.language.code_preprocessor import Owner, preprocess_with_places, with_own_attributes
from nxwright.language.nxlang import STRING_LITERAL, compile_program
from nxwright.language.resource_names import (FONT, LISTS, NOUNS, PICTURE, SOUND,
                                              ResourceNames)
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.folder_index import (APP_FILE, PROGRAM_FILE, FolderIndex,
                                          text_on_disk)
from nxwright.source.references import references
from nxwright.source.folder_check import check_folder
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.page_source import page_toml_path, reference_kind
from nxwright.source.source_folder import (RESOURCE_FILES, app_text, folder_reader, number_in_table,
                                           read_app, read_folder_source)

# The kinds the command takes, by the word it takes them as: "picture".
KINDS = {noun: kind for kind, noun in NOUNS.items()}
# The ID of no resource, as a picture attribute holds it when it shows none.
_NO_RESOURCE = 65535
# The arguments giving a resource by its ID, by command: {command: [(kind,
# argument, counted from 0)]}. xstr's background, its argument 6, is a
# picture only while its `sta`, argument 9, is 0 or 2, and `play` takes a
# sound (the vendor's instruction set).
_RESOURCE_ARGUMENTS = {**{command: [(PICTURE, argument)]
                          for command, argument in PICTURE_ARGUMENTS.items()},
                       "xstr": [(FONT, XSTR_FONT_ARGUMENT)], "play": [(SOUND, 1)]}
_XSTR_BACKGROUND, _XSTR_STA, _XSTR_PICTURE_STAS = 6, 9, (0, 2)
# A number as code writes one: decimal, or hex after 0x.
_NUMBER = r"-?(?:0x[0-9A-Fa-f]+|\d+)"
# An attribute given a lone number, or compared with one, in Editor code:
# the object, or a page and its object, the attribute, the operator, and the
# number, ending the line or the condition; then the same compared the
# other way round.
_GIVEN_NUMBER = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?"
                           r"(?:==|!=|<=|>=|<|>|=)(%s)(?=$|\)|&&|\|\|)" % _NUMBER)
_COMPARED_NUMBER = re.compile(r"(?<=[(&|])(%s)(?:==|!=|<=|>=|<|>)([A-Za-z_]\w*)\.([A-Za-z_]\w*)"
                              r"(?:\.([A-Za-z_]\w*))?(?![\w.])" % _NUMBER)


class _NamesStandingForNone(ResourceNames):
    """A folder's resource names, each standing for the ID of no resource:
    code read with them keeps as numbers only those it writes."""

    def id_of(self, kind: str, name: str) -> int:
        super().id_of(kind, name)
        return _NO_RESOURCE


def remove_resource(source_folder: Path, kind: str, name: str) -> tuple:
    """Removes the resource `name` of `kind`, a word of KINDS, from the source
    folder, as the module's docstring says; returns what
    remove_resource_files returns. Raises NxwrightError,
    writing nothing, for a kind or a name the folder does not have, a folder
    whose checks find an error, and a resource the folder uses, naming each
    place."""
    source_folder = Path(source_folder)
    if kind not in KINDS:
        raise NxwrightError("%s is not a kind of resource: %s" % (kind, ", ".join(KINDS)))
    listed = LISTS[KINDS[kind]]
    names = read_app(source_folder)[listed]
    if name not in names:
        raise NxwrightError("the folder has no %s named %s" % (kind, name))
    read = folder_reader(source_folder)
    errors = check_folder(read, lambda path: (source_folder / path).is_file()).errors()
    if errors:
        first = errors[0]
        raise NxwrightError("the folder's checks find an error, so its uses of %s %s cannot "
                            "all be found: %s: %s" % (kind, name, first.place, first.message))
    index = FolderIndex(source_folder, text_on_disk)
    folder = read_folder_source(read)
    ids = range(names.index(name), len(names))
    uses = (_uses_by_name(index, listed, name)
            + _uses_in_page_files(folder, index, KINDS[kind], ids)
            + _uses_in_code(folder, index, KINDS[kind], ids))
    if uses:
        raise NxwrightError("%s %s is used, so it stays:\n%s"
                            % (kind, name, "\n".join("  " + use for use in uses)))
    return remove_resource_files(source_folder, listed, name)


def remove_resource_files(source_folder: Path, listed: str, name: str) -> tuple:
    """Takes the resource `name` out of app.toml's list `listed`, then
    deletes each of its files: those of its name with one of its kind's
    suffixes (RESOURCE_FILES), each by its own path; no folder. Returns (the
    paths deleted, those that could not be, a sentence each), within the
    folder. app.toml goes first, so that a file left behind is one no list
    names, never a name whose file is gone. It checks no use of the
    resource: remove_resource does, before."""
    app = read_app(source_folder)
    app[listed] = [listed_name for listed_name in app[listed] if listed_name != name]
    (source_folder / "app.toml").write_text(app_text(app), encoding="utf-8", newline="\n")
    removed, left = [], []
    for suffix in RESOURCE_FILES[listed]:
        relative = "%s/%s%s" % (listed, name, suffix)
        path = source_folder / relative
        if not path.is_file():
            continue
        try:
            path.unlink()
        except OSError as error:
            left.append("%s: %s" % (relative, error.strerror or error))
        else:
            removed.append(relative)
    return removed, left


def _place(index: FolderIndex, path: str, number: int) -> str:
    """How a use is named: "path line N: the line", N counted from 1."""
    return "%s line %d: %s" % (path, number, index.lines(path)[number - 1].strip())


def _uses_by_name(index: FolderIndex, listed: str, name: str) -> list:
    """The places outside app.toml that Find All References finds for the
    resource `name` of app.toml's list `listed`."""
    entry = index.app_entries[(listed, name)]
    return [_place(index, place.path, place.line + 1)
            for place in references(index, entry.path, entry.line, entry.start, False)
            if place.path != APP_FILE]


def _uses_in_page_files(folder, index: FolderIndex, kind: str, ids: range) -> list:
    """The page files' attributes taking a resource of `kind` that hold a
    number of `ids`, written there or left to the defaults."""
    uses = []
    for page in folder.app["pages"]:
        path = page_toml_path(page)
        lines = index.lines(path)
        data = tomllib.loads("\n".join(lines))
        components = data.get("component", [])
        for table in [data.get("page", {})] + (components if isinstance(components, list) else []):
            object_type = TYPES_BY_NAME.get(table.get("type"))
            if object_type is None:
                continue
            defaults = folder.defaults.get(object_type)
            for attribute in dict.fromkeys([*table, *(defaults.names() if defaults else [])]):
                if reference_kind(object_type, attribute) != kind:
                    continue
                value = number_in_table(table, folder.defaults, attribute)
                if isinstance(value, int) and value in ids:
                    uses.append(_page_file_use(index, path, table, attribute, value))
    return uses


def _page_file_use(index: FolderIndex, path: str, table: dict, attribute: str,
                   value: int) -> str:
    """Names where a page file's `table` gives `attribute` the number `value`:
    its own line, or the table's name line when the defaults give it."""
    lines = index.lines(path)
    name = table.get("name")
    name_line = next((number for number, line in enumerate(lines)
                      if line.strip() == 'name = "%s"' % name), 0)
    if attribute in table:
        given = next((number for number in range(name_line, len(lines))
                      if lines[number].split("=")[0].strip() == attribute), name_line)
        return _place(index, path, given + 1)
    return ("%s line %d: %s leaves out its %s, so it takes %d from the defaults"
            % (path, name_line + 1, name, attribute, value))


def _uses_in_code(folder, index: FolderIndex, kind: str, ids: range) -> list:
    """The lines of the folder's code where a number of `ids` stands for a
    resource of `kind`. The code is read as the build reads it, but with its
    names standing for no resource, so that only the numbers it writes, and
    those nxlang's constants give, are seen. A file several pages include is
    read for each of them."""
    folder = dataclasses.replace(folder, names=_NamesStandingForNone.of_app(folder.app))
    places = {}         # {(path, line number): [(the page, or None, a line of Editor code)]}
    for page in folder.app["pages"]:
        object_names = [page_object.name for page_object in index.page_objects[page]]
        for path in index.page_files[page]:
            for title, lines in folder.editor_code(page, path):
                # An event's own attributes, as '&pic&', read as the Editor reads them.
                owner = Owner.among(title[3:].split(".")[0], object_names) \
                    if title.startswith("on ") else None
                for number, code in lines:
                    read = with_own_attributes(code, owner) if owner else code
                    places.setdefault((path, number), []).append((page, read))
    program = list(enumerate(folder.program.split("\n"), start=1))
    if folder.declared is not None:
        program = compile_program(program, folder.declared)
    for number, code in preprocess_with_places(program, folder.names):
        places.setdefault((PROGRAM_FILE, number), []).append((None, code))
    for lines in folder.compiled_macros().values():
        for number, code in lines:
            places.setdefault((MACROS_PATH, number), []).append((None, code))
    return [_place(index, path, number) for (path, number), found in places.items()
            if number and any(_takes_a_number(folder.page_objects, page,
                                              split_line(code, 0)[1].strip(), kind, ids)
                              for page, code in found)]


def _takes_a_number(page_objects: dict, page, code: str, kind: str, ids: range) -> bool:
    """Whether a line's code part, in Editor syntax, of an event of `page`
    (None outside a page), gives a number of `ids` where a resource of
    `kind` is taken."""
    word = command_word(code)
    if word in _RESOURCE_ARGUMENTS:
        arguments = command_arguments(code[len(word):].strip())
        given = list(_RESOURCE_ARGUMENTS[word])
        if word == "xstr" and _literal(arguments, _XSTR_STA) in _XSTR_PICTURE_STAS:
            given.append((PICTURE, _XSTR_BACKGROUND))
        if any(taken == kind and _literal(arguments, argument) in ids for taken, argument in given):
            return True
    # A quoted text names nothing: it is emptied before an attribute is sought.
    code = STRING_LITERAL.sub('""', code)
    for match in _GIVEN_NUMBER.finditer(code):
        first, second, third, number = match.groups()
        if _attribute_kind(page_objects, page, first, second, third) == kind \
                and _value(number) in ids:
            return True
    for match in _COMPARED_NUMBER.finditer(code):
        number, first, second, third = match.groups()
        if _attribute_kind(page_objects, page, first, second, third) == kind \
                and _value(number) in ids:
            return True
    return False


def _attribute_kind(page_objects: dict, page, first: str, second: str, third):
    """The kind of resource the attribute `first.second`, or
    `first.second.third` of another page, takes, or None: of an object of
    `page`, or of the page so named."""
    if third is not None:
        on_page, name, attribute = first, second, third
    elif page is not None and first in (page_objects.get(page) or {}):
        on_page, name, attribute = page, first, second
    else:
        on_page, name, attribute = first, first, second
    type_name = (page_objects.get(on_page) or {}).get(name)
    object_type = TYPES_BY_NAME.get(type_name) if type_name else None
    return reference_kind(object_type, attribute) if object_type is not None else None


def _literal(arguments: list, place: int):
    """A command's argument `place` when it is a lone number, else None."""
    return _value(arguments[place].strip()) if place < len(arguments) else None


def _value(text: str):
    """The value of a number as code writes it, or None for anything else."""
    if not re.fullmatch(_NUMBER, text):
        return None
    return int(text, 16) if "x" in text else int(text)
