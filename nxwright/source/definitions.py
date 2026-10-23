"""Where the name at a place of a source folder's file is defined: what a code
editor opens on Ctrl+click.

In a .nx file:
  - a component, as `title` in `title.txt`, `vis title,1`, or the heading
    `on title.up:`, is defined by its table in its page's .page.toml file. In a
    file several pages include, it may be a different component on each:
    every page's is returned.
  - `settings` in `settings.t0.txt` is the page's own table, and `t0` the
    component's table in that page's file.
  - a function, constant, local, parameter, or `int` global is defined by
    its declaration. A bare name is a local, a constant, or a global, which
    never share a name (docs/language.md, Names); failing those, a component,
    and failing that a page, as in `page settings`, defined by both its files.
  - an include's path opens that file, `@pic(...)` the picture, and
    `@font(...)`, `@animation(...)`, `@video(...)`, and `@sound(...)` the
    name's entry in app.toml, their files not being text.
  - the name a `call` gives, as `my name` in `call my name`, is defined by
    its macro's heading in macros.nx. In macros.nx, Editor code in either
    language, no constant or function of nxlang defines a name.
In a page's .page.toml file, a resource attribute's value opens the same:
a picture or font attribute's, or a `vid`, by its component's type.
In app.toml, a name in the `pages` or `pictures` list opens its file.

A name chosen at run time, as `b` in `b[3].txt`, has no definition, nor has
a system variable or a command.
"""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import command_word, split_line
from nxwright.language.resource_names import LISTS, PICTURE, REFERENCE
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.folder_index import (APP_FILE, FolderIndex, file_start, line_tokens,
                                          page_of)
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.nx_files import EVENT_HEADING
from nxwright.source.page_source import page_nx_path, page_toml_path, reference_kind

# A page file's line `key = "value"`.
_STRING_VALUE = re.compile(r'\s*([A-Za-z0-9_]+)\s*=\s*"([^"\\]*)"')


def definitions(index: FolderIndex, path: str, line: int, column: int) -> list:
    """Returns the places defining the name at column `column` of line `line`
    of the folder's file `path`, without repeats. Returns [] where there is no
    name, or nothing in the folder defines it."""
    if path == APP_FILE:
        found = _in_app(index, line, column)
    elif page_of(path):
        found = _in_page_file(index, path, line, column)
    elif path.endswith(".nx"):
        found = _in_code(index, path, line, column)
    else:
        found = []
    return list(dict.fromkeys(found))


def _in_app(index: FolderIndex, line: int, column: int) -> list:
    """Returns the definitions of a name in one of app.toml's lists."""
    for (list_name, name), place in index.app_entries.items():
        if place.holds(line, column):
            if list_name == "pages":
                return [file_start(page_toml_path(name))]
            if list_name == "pictures":
                return [file_start(index.picture_path(name))]
    return []


def _in_page_file(index: FolderIndex, path: str, line: int, column: int) -> list:
    """Returns the definitions of a resource attribute's value in a page file."""
    lines = index.lines(path) or []
    match = _STRING_VALUE.match(lines[line]) if line < len(lines) else None
    if match is None or not match.start(2) <= column <= match.end(2):
        return []
    object_type = TYPES_BY_NAME.get(index.type_at(page_of(path), line))
    return _resource(index, reference_kind(object_type, match[1]), match[2])


def _resource(index: FolderIndex, kind, name: str) -> list:
    """Returns the definition of a resource of `kind`, by name: a picture's
    file, or another's name in app.toml."""
    if kind == PICTURE and name in index.pictures:
        return [file_start(index.picture_path(name))]
    entry = index.app_entries.get((LISTS[kind], name)) if kind and kind != PICTURE else None
    return [entry] if entry else []


def _in_code(index: FolderIndex, path: str, line: int, column: int) -> list:
    """Returns the definitions of the name at a place of a .nx file."""
    nx_file = index.nx_file(path)
    if nx_file is None or line >= len(nx_file.lines):
        return []
    text = nx_file.lines[line]
    heading = EVENT_HEADING.fullmatch(text)
    if heading:
        if heading.start(1) <= column <= heading.end(1):
            return index.objects_named(heading[1], index.pages_using(path))
        return []
    block = nx_file.block_at(line)
    if block is not None and block.place.line == line:
        # A function's heading: its name and parameters define themselves.
        return [place for place in [block.place, *block.parameters.values()]
                if place.holds(line, column)]
    for place, included in nx_file.includes:
        if place.holds(line, column):
            return [file_start(included)] if index.nx_file(included) else []
    called = _called_macro(text, column)
    if called is not None:
        # Its name may hold spaces, so it is read whole, not as tokens.
        place = index.macros().get(called)
        return [place] if place else []
    tokens = line_tokens(text)
    at = _token_at(tokens, column)
    if at is None:
        return []
    kind, token = tokens[at][0], tokens[at][1]
    if kind == "reference":
        reference = REFERENCE.fullmatch(token)
        return _resource(index, reference[1], reference[2])
    if kind != "name":
        return []
    chain, position = dotted_names(tokens, at)
    if len(chain) == 1:
        return _bare_name(index, path, line, chain[0])
    if len(chain) == 2 and position == 0:
        return (index.objects_named(chain[0], index.pages_using(path))
                or _page_table(index, chain[0]))
    if len(chain) == 3 and position == 0:
        return _page_table(index, chain[0])
    if len(chain) == 3 and position == 1:
        return index.objects_named(chain[1], [chain[0]])
    return []


def _called_macro(text: str, column: int):
    """Returns the name a `call <name>` line gives a macro, when `column`
    is in the name; else None."""
    try:
        indent, code, _ = split_line(text, 0)
    except NxwrightError:
        return None     # a string not closed yet
    if command_word(code) != "call":
        return None
    name = code[len("call"):].strip()
    start = len(indent) + code.index(name, len("call"))
    return name if name and start <= column <= start + len(name) else None


def _token_at(tokens: list, column: int):
    """Returns the index of the token at `column`, or of the one ending
    there, or None."""
    for at, (_, _, start, end) in enumerate(tokens):
        if start <= column < end:
            return at
    for at, (_, _, _, end) in enumerate(tokens):
        if end == column:
            return at
    return None


def dotted_names(tokens: list, at: int) -> tuple:
    """Returns (names, position) of the dotted names around token `at`, as
    `settings.t0.txt` gives (["settings", "t0", "txt"], 1) for `t0`. A chain
    with brackets, chosen at run time, gives ([], 0)."""
    first = at
    while first >= 2 and tokens[first - 1][1] == "." and tokens[first - 2][0] == "name":
        first -= 2
    last = at
    while (last + 2 < len(tokens) and tokens[last + 1][1] == "."
           and tokens[last + 2][0] == "name"):
        last += 2
    before = tokens[first - 1][1] if first >= 1 else ""
    after = tokens[last + 1][1] if last + 1 < len(tokens) else ""
    if before == "." or after in (".", "["):
        return [], 0
    return [tokens[n][1] for n in range(first, last + 1, 2)], (at - first) // 2


def _bare_name(index: FolderIndex, path: str, line: int, name: str) -> list:
    """Returns the definitions of a name written without a dot."""
    block = index.nx_file(path).block_at(line)
    if block is not None and (name in block.locals or name in block.parameters):
        return [block.locals.get(name) or block.parameters[name]]
    found = []
    for visible in index.visible_files(path):
        nx_file = index.nx_file(visible)
        # macros.nx is Editor code in either language: no constant or
        # function of nxlang reaches it.
        for names in (nx_file.constants, nx_file.functions()) if path != MACROS_PATH else ():
            if name in names:
                found.append(names[name])
        if visible in index.program_files and name in nx_file.globals:
            found.append(nx_file.globals[name])
    if found:
        return found
    return index.objects_named(name, index.pages_using(path)) or _page(index, name)


def _page(index: FolderIndex, name: str) -> list:
    """Returns the definitions of a page named alone, as in `page settings`:
    its own table, and its own .nx file."""
    if name not in index.pages:
        return []
    return _page_table(index, name) + [file_start(page_nx_path(name))]


def _page_table(index: FolderIndex, name: str) -> list:
    """Returns the place of a page's own table, the first of its page file."""
    return index.objects_named(name, [name])[:1] if name in index.pages else []
