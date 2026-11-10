"""Numbers that stand for resources in a source folder: where its code or
page files give a picture, font, animation, video, or sound by its ID, as
`p0.pic=7`, rather than by name, as `@pic(logo)`.

code_lines compiles the folder's code to strict Nextion syntax, the same way
the build does, and gives each line with the file and line it comes from.
resource_numbers finds the numbers that stand for resources in one such line.
Removing a resource uses the two to find numbers that the removal would make
stand for another resource (resource_removal.py). placed_numbers finds where
each such number appears in one file's own text, so that the language server
can show the resource's name beside it, and as_name gives the text that writes
the number as that name.

Pages have IDs too: a page's ID is its place in app.toml's `pages`.
page_numbers finds the page IDs that one line gives as numbers: the argument
of `page`, and each number given to `dp` or compared with it. Deleting a page
uses code_lines and page_numbers to find the numbers that the deletion would
make stand for another page (page_removal.py). placed_page_numbers finds
where `page` is given a number in one file's own text, and
page_number_as_name gives the page's name to write in its place. """
import dataclasses
from dataclasses import dataclass
import re
import tomllib

from nxwright import NxwrightError
from nxwright.language.code_checks import PICTURE_ARGUMENTS, XSTR_FONT_ARGUMENT
from nxwright.language.code_lines import command_arguments, command_word, split_line
from nxwright.language.code_preprocessor import Owner, preprocess_with_places, with_own_attributes
from nxwright.language.nxlang import STRING_LITERAL, compile_program
from nxwright.language.resource_names import FONT, LISTS, PICTURE, SOUND, ResourceNames
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.asset_names_in_code import line_with_asset_names
from nxwright.source.folder_index import PROGRAM_FILE, FolderIndex, Place
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.nx_files import read_event_label
from nxwright.source.page_source import page_toml_path, reference_kind

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
# An attribute given a lone number, or compared with one, in strict Nextion syntax:
# the object, or a page and its object, the attribute, the operator, and the
# number, ending the line or the condition; then the same compared the
# other way round.
_GIVEN_NUMBER = re.compile(r"(?<![\w.\]])([A-Za-z_]\w*)\.([A-Za-z_]\w*)(?:\.([A-Za-z_]\w*))?"
                           r"(?:==|!=|<=|>=|<|>|=)(%s)(?=$|\)|&&|\|\|)" % _NUMBER)
_COMPARED_NUMBER = re.compile(r"(?<=[(&|])(%s)(?:==|!=|<=|>=|<|>)([A-Za-z_]\w*)\.([A-Za-z_]\w*)"
                              r"(?:\.([A-Za-z_]\w*))?(?![\w.])" % _NUMBER)
# A number standing alone in a line of a file's own text, not part of a
# name or of another number.
_WHOLE_NUMBER = re.compile(r"(?<![\w.])(?:0x[0-9A-Fa-f]+|\d+)(?![\w.])")
# The system variable `dp`, the current page's ID, given a number or
# compared with one, as in `dp==1`. The second pattern finds a number on the
# left of the comparison, as in `2!=dp`.
_DP_NUMBER = re.compile(r"(?<![\w.])dp(?:==|!=|<=|>=|<|>|=)(%s)(?=$|\)|&&|\|\|)" % _NUMBER)
_NUMBER_DP = re.compile(r"(?<=[(&|])(%s)(?:==|!=|<=|>=|<|>)dp(?![\w.])" % _NUMBER)
# A name that code can use unchanged, as in `page settings`.
_CODE_NAME = re.compile(r"[A-Za-z_]\w*")
# The kind of a PlacedNumber that gives a page's ID.
PAGE = "page"
# A page file's attribute given a number: its name, then the number.
_PAGE_FILE_NUMBER = re.compile(r"\s*([A-Za-z_]\w*)\s*=\s*(\d+)\s*(?:#.*)?$")
PAGE_FILE_SUFFIX = ".page.toml"


class _NamesStandingForNone(ResourceNames):
    """A folder's resource names, each standing for the ID of no resource:
    code read with them keeps as numbers only those it writes."""

    def id_of(self, kind: str, name: str) -> int:
        super().id_of(kind, name)
        return _NO_RESOURCE


@dataclass(frozen=True)
class PlacedNumber:
    """A number of a file's own text that stands for the resource of `kind`
    ("pic", "font", ...) whose ID is `id`, at `place`."""
    place: Place
    kind: str
    id: int


def code_lines(folder, index: FolderIndex, only: str = None) -> dict:
    """Returns {(path, line number from 1): [(the page, or None outside a
    page's code, a line in strict Nextion syntax)]}: the folder's code as the
    build reads it, but with its names standing for no resource, so that only
    the numbers it writes, and those nxlang's constants give, are left. A file
    several pages include is read for each of them. With `only`, a path, only
    that file's lines, and only the pages that use it are read."""
    folder = dataclasses.replace(folder, names=_NamesStandingForNone.of_app(folder.app))
    places = {}
    pages = folder.app["pages"] if only is None else index.pages_using(only)
    for page in pages:
        object_names = [page_object.name for page_object in index.page_objects[page]]
        paths = [path for path in index.page_files[page] if only is None or path == only]
        # Asking for all of the page's files in one call compiles the page only once.
        sections = folder.editor_code_of_files(page, paths)
        for path in paths:
            for title, lines in sections[path]:
                # An event's own attributes, such as '&pic&', are read the way the
                # Nextion Editor reads them.
                label = read_event_label(title)
                owner = Owner.among(label.name, object_names) if label else None
                for number, code in lines:
                    read = with_own_attributes(code, owner) if owner else code
                    places.setdefault((path, number), []).append((page, read))
    if only is None or only == PROGRAM_FILE:
        program = list(enumerate(folder.program.split("\n"), start=1))
        if folder.declared is not None:
            program = compile_program(program, folder.declared)
        for number, code in preprocess_with_places(program, folder.names):
            places.setdefault((PROGRAM_FILE, number), []).append((None, code))
    if only is None or only == MACROS_PATH:
        for lines in folder.compiled_macros().values():
            for number, code in lines:
                places.setdefault((MACROS_PATH, number), []).append((None, code))
    return places


def resource_numbers(page_objects: dict, page, code: str) -> list:
    """Returns (kind, number) for each number that stands for a resource in
    `code`, the code part of one line in strict Nextion syntax. The line is in
    an event of `page`, or outside any page when `page` is None. The numbers
    come in this order: a command's argument that takes a resource, then each
    number given to an attribute that takes one, then each number compared
    with such an attribute. `page_objects` gives the types of each page's
    objects."""
    found = []
    word = command_word(code)
    if word in _RESOURCE_ARGUMENTS:
        arguments = command_arguments(code[len(word):].strip())
        given = list(_RESOURCE_ARGUMENTS[word])
        if word == "xstr" and _literal(arguments, _XSTR_STA) in _XSTR_PICTURE_STAS:
            given.append((PICTURE, _XSTR_BACKGROUND))
        found += [(taken, _literal(arguments, argument)) for taken, argument in given
                  if _literal(arguments, argument) is not None]
    # A quoted text names nothing: it is emptied before an attribute is sought.
    code = STRING_LITERAL.sub('""', code)
    for match in _GIVEN_NUMBER.finditer(code):
        first, second, third, number = match.groups()
        found.append((_attribute_kind(page_objects, page, first, second, third), _value(number)))
    for match in _COMPARED_NUMBER.finditer(code):
        number, first, second, third = match.groups()
        found.append((_attribute_kind(page_objects, page, first, second, third), _value(number)))
    return [(kind, value) for kind, value in found if kind is not None and value is not None]


def placed_numbers(folder, index: FolderIndex, path: str) -> list:
    """Returns the PlacedNumbers of the folder's file `path`, a page file or a
    .nx file, in their order. In code, a number is found only where its text
    appears once in its line, as a whole word, outside quoted texts and
    comments, so that an edit can replace it at one exact place. A number that
    nxlang gives through a constant, or whose text appears twice in the line,
    is left out. In a page file, each attribute written there with a number is
    placed. Code that does not compile gives none."""
    if path.endswith(PAGE_FILE_SUFFIX):
        return _placed_in_page_file(index, path)
    try:
        places = code_lines(folder, index, path)
    except NxwrightError:
        return []
    lines = index.lines(path) or []
    found = []
    for (file, number), compiled in sorted(places.items()):
        if file != path or not 0 < number <= len(lines):
            continue
        numbers = dict.fromkeys(pair for page, code in compiled
                                for pair in resource_numbers(folder.page_objects, page,
                                                             _code_part(code)))
        for kind, value in numbers:
            span = _only_place(lines[number - 1], value)
            if span is not None:
                found.append(PlacedNumber(Place(path, number - 1, *span), kind, value))
    return sorted(found, key=lambda placed: (placed.place.line, placed.place.start))


def as_name(folder, index: FolderIndex, placed: PlacedNumber):
    """Returns the text that writes `placed` as its resource's name, or None
    where the number cannot be written as a name. In a page file, the text is
    the name in quotes. In code, it is `@pic(name)` or the like, and only
    where the number can mean nothing but that resource, by the same rule that
    `nxwright extract` uses to write names (asset_names_in_code.py). An ID
    past the last one of its kind gives None."""
    names = folder.app.get(LISTS[placed.kind], [])
    if not 0 <= placed.id < len(names):
        return None
    name = names[placed.id]
    if placed.place.path.endswith(PAGE_FILE_SUFFIX):
        return '"%s"' % name
    line = index.lines(placed.place.path)[placed.place.line]
    reference = "@%s(%s)" % (placed.kind, name)
    rewritten = line_with_asset_names(line, ResourceNames.of_app(folder.app))
    if rewritten == line[:placed.place.start] + reference + line[placed.place.end:]:
        return reference
    return None


def page_numbers(code: str) -> list:
    """Returns the page IDs that `code`, the code part of one line in strict
    Nextion syntax, gives as numbers: the argument of `page`, then each
    number given to `dp` or compared with it."""
    found = []
    if command_word(code) == "page":
        found.append(_literal(command_arguments(code[len("page"):].strip()), 0))
    # Quoted texts are emptied first, so that a `dp` inside one is not taken for code.
    code = STRING_LITERAL.sub('""', code)
    found += [_value(match.group(1)) for match in _DP_NUMBER.finditer(code)]
    found += [_value(match.group(1)) for match in _NUMBER_DP.finditer(code)]
    return [value for value in found if value is not None]


def placed_page_numbers(folder, index: FolderIndex, path: str) -> list:
    """Returns the PlacedNumbers, of kind PAGE, where the folder's .nx file
    `path` gives `page` a number, in the order they appear in the file. A
    number is placed only if it appears once in its line. A number given to
    `dp` is left out, since it cannot be written as a name, and a file whose
    code does not compile gives none."""
    try:
        places = code_lines(folder, index, path)
    except NxwrightError:
        return []
    lines = index.lines(path) or []
    found = []
    for (file, number), compiled in sorted(places.items()):
        if file != path or not 0 < number <= len(lines):
            continue
        values = {_literal(command_arguments(code_part[len("page"):].strip()), 0)
                  for code_part in (_code_part(code) for _, code in compiled)
                  if command_word(code_part) == "page"}
        for value in sorted(value for value in values if value is not None):
            span = _only_place(lines[number - 1], value)
            if span is not None:
                found.append(PlacedNumber(Place(path, number - 1, *span), PAGE, value))
    return found


def page_number_as_name(folder, placed: PlacedNumber):
    """Returns the name of the page whose ID `placed` gives, to write after
    `page` in place of the number. Returns None for an ID past the last page,
    and for a page whose name cannot appear in code as it is, such as `a:b`."""
    pages = folder.app["pages"]
    if not 0 <= placed.id < len(pages) or not _CODE_NAME.fullmatch(pages[placed.id]):
        return None
    return pages[placed.id]


def number_files(index: FolderIndex, app: dict) -> list:
    """Returns the folder's files that may hold numbers standing for
    resources: each page's file, then its code files, then program.nx's,
    and macros.nx, each once."""
    files = []
    for page in app["pages"]:
        files += [page_toml_path(page)] + index.page_files.get(page, [])
    files += index.program_files + ([MACROS_PATH] if index.lines(MACROS_PATH) is not None else [])
    return list(dict.fromkeys(files))


def _placed_in_page_file(index: FolderIndex, path: str) -> list:
    """The PlacedNumbers of the page file `path`: each attribute taking a
    resource, written in a table with a number."""
    lines = index.lines(path) or []
    # A file that does not read as TOML, as while it is half typed, gives none.
    try:
        tomllib.loads("\n".join(lines))
    except tomllib.TOMLDecodeError:
        return []
    found = []
    for number, line in enumerate(lines):
        match = _PAGE_FILE_NUMBER.fullmatch(line)
        if match is None:
            continue
        kind = reference_kind(_table_type(lines, number), match.group(1))
        if kind is not None:
            found.append(PlacedNumber(Place(path, number, *match.span(2)), kind,
                                      int(match.group(2))))
    return found


def _table_type(lines: list, number: int):
    """The object type of the table of a page file holding line `number`:
    the type its `type = "..."` line gives, or None."""
    for line in reversed(lines[:number + 1]):
        stripped = line.strip()
        if stripped.startswith("type ="):
            return TYPES_BY_NAME.get(stripped.split("=", 1)[1].strip().strip('"'))
        if stripped.startswith("["):
            break
    for line in lines[number + 1:]:
        stripped = line.strip()
        if stripped.startswith("["):
            break
        if stripped.startswith("type ="):
            return TYPES_BY_NAME.get(stripped.split("=", 1)[1].strip().strip('"'))
    return None


def _code_part(code: str) -> str:
    """A line in strict Nextion syntax, without its indent and comment."""
    return split_line(code, 0)[1].strip()


def _only_place(line: str, value: int):
    """Returns (start, end) of the one number of `line`'s code that is
    `value`, as a whole word outside quoted texts and the comment, or None
    where there is none or more than one."""
    try:
        indent, code, _ = split_line(line, 0)
    except NxwrightError:
        return None
    blanked = STRING_LITERAL.sub(lambda text: " " * len(text.group()), code)
    spans = [match.span() for match in _WHOLE_NUMBER.finditer(blanked)
             if _value(match.group()) == value]
    if len(spans) != 1:
        return None
    start, end = spans[0]
    return start + len(indent), end + len(indent)


def _attribute_kind(page_objects: dict, page, first: str, second: str, third):
    """Returns the kind of resource that an attribute takes, or None. The
    attribute is `first.second`, on an object of `page` or on the page named
    `first`, or `first.second.third`, on an object of another page."""
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
