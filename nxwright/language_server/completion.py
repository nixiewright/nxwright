"""What a code editor offers while typing: names that can come next, and the
parameters of the function being called.

In a .nx file:
  - after `t0.`: the attributes of `t0`'s type, as the folder's defaults.toml
    lists them, for each page using the file that has a `t0`, each with its
    description as documentation (attributes.py);
  - after `settings.`: the components of that page;
  - after `call `: the folder's macros;
  - elsewhere: the components of the pages using the file, the locals and
    parameters of the event or function, the constants, functions, and
    `int` globals the code may use, and the system variables. In macros.nx,
    Editor code in either language, no constant or function of nxlang.
Nothing is offered inside a string or a comment.
In a page file, after a picture or font attribute's opening quotation mark:
the folder's pictures or fonts.

Inside a call's parentheses, the parameter hint gives the function's
heading and which parameter is being typed.
"""
from dataclasses import dataclass
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.resource_names import NOUNS
from nxwright.language_server.attributes import attribute_markdown, type_defaults
from nxwright.project.editor_language import EDITOR_SYSTEM_VARIABLES, SERIES_LACKED_VARIABLES
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.folder_index import FolderIndex, Place, line_tokens, page_of
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.page_source import reference_kind

# The protocol's numbers for kinds of completion.
FUNCTION, FIELD, VARIABLE, CLASS, PROPERTY, FILE, CONSTANT = 3, 5, 6, 7, 10, 17, 21
_AFTER_PAGE_COMPONENT = re.compile(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)\.\w*$")
_AFTER_NAME = re.compile(r"([A-Za-z_]\w*)\.\w*$")
_AFTER_DOT_OR_BRACKET = re.compile(r"[.\]]\w*$")
_OPEN_VALUE = re.compile(r'\s*([A-Za-z0-9_]+)\s*=\s*"[^"]*$')
# `call` and the start of a macro's name, which may hold spaces.
_AFTER_CALL = re.compile(r"\s*call\s+([A-Za-z0-9_ ]*)")


@dataclass(frozen=True)
class Item:
    """A name to offer: its text, its kind, a few words about it, and its
    documentation, as Markdown, or "". `replaces` is the text it takes the
    place of, when not the word at the cursor: a macro's name holds spaces."""
    label: str
    kind: int
    detail: str = ""
    documentation: str = ""
    replaces: Place = None


@dataclass
class Signature:
    """A function's heading, its parameters as written in it, and which one
    the cursor is in."""
    label: str
    parameters: list
    active: int


def completions(index: FolderIndex, path: str, line: int, column: int) -> list:
    """Returns the Items to offer at a place, without repeats."""
    lines = index.lines(path) or []
    before = lines[line][:column] if line < len(lines) else ""
    if page_of(path):
        found = _in_page_file(index, path, line, before)
    elif path.endswith(".nx") and index.nx_file(path) and _in_code(before):
        found = _in_code_line(index, path, line, before)
    else:
        found = []
    return list(dict.fromkeys(found))


def _in_page_file(index: FolderIndex, path: str, line: int, before: str) -> list:
    """Offers the names of the resources whose ID the attribute being given
    holds, for its table's type."""
    value = _OPEN_VALUE.fullmatch(before)
    if value is None:
        return []
    kind = reference_kind(TYPES_BY_NAME.get(index.type_at(page_of(path), line)), value[1])
    return [Item(name, FILE, NOUNS[kind]) for name in index.names_of(kind)] if kind else []


def _in_code(before: str) -> bool:
    """True when the end of `before` is code, not a string or a comment."""
    try:
        _, _, comment = split_line(before, 0)
    except NxwrightError:
        return False    # a string not closed yet
    return not comment.lstrip().startswith("//")


def _in_code_line(index: FolderIndex, path: str, line: int, before: str) -> list:
    after_call = _AFTER_CALL.fullmatch(before)
    if after_call:
        typed = Place(path, line, after_call.start(1), len(before))
        return [Item(name, FUNCTION, "macro", replaces=typed) for name in index.macros()]
    pages = index.pages_using(path)
    after_page = _AFTER_PAGE_COMPONENT.search(before)
    if after_page and after_page[1] in index.pages:
        return _attributes(index, index.page_objects_named(after_page[2], [after_page[1]]))
    after_name = _AFTER_NAME.search(before)
    if after_name:
        name = after_name[1]
        found = _attributes(index, index.page_objects_named(name, pages))
        if name in index.pages:
            found += [Item(page_object.name, FIELD, page_object.type)
                      for page_object in index.page_objects[name][1:]]
        return found
    if _AFTER_DOT_OR_BRACKET.search(before):
        return []
    return _names_in_scope(index, path, line, pages)


def _names_in_scope(index: FolderIndex, path: str, line: int, pages: list) -> list:
    found = [Item(page_object.name, FIELD, page_object.type)
             for page in pages for page_object in index.page_objects[page][1:]]
    block = index.nx_file(path).block_at(line)
    if block is not None:
        found += [Item(name, VARIABLE, "local") for name in block.locals]
        found += [Item(name, VARIABLE, "parameter") for name in block.parameters]
    for visible in index.visible_files(path):
        nx_file = index.nx_file(visible)
        if path != MACROS_PATH:
            found += [Item(name, CONSTANT, visible) for name in nx_file.constants]
            found += [Item(name, FUNCTION, visible) for name in nx_file.functions()]
        if visible in index.program_files:
            found += [Item(name, VARIABLE, "int, " + visible) for name in nx_file.globals]
    # Those the screen's series lacks are left out, as the build refuses them.
    lacked = SERIES_LACKED_VARIABLES.get(index.screen_series(), frozenset())
    found += [Item(name, VARIABLE, "system variable")
              for name in sorted(EDITOR_SYSTEM_VARIABLES - lacked)]
    found += [Item(page, CLASS, "page") for page in index.pages]
    return found


def _attributes(index: FolderIndex, page_objects: list) -> list:
    """Returns the attributes of the types of `page_objects`."""
    defaults = type_defaults(index)
    found = []
    for page_object in page_objects:
        found_defaults = defaults.get(TYPES_BY_NAME.get(page_object.type))
        if found_defaults is not None:
            found += [Item(name, PROPERTY, page_object.type,
                           attribute_markdown(page_object.type, name) or "")
                      for name in found_defaults.names()]
    return found


def signature(index: FolderIndex, path: str, line: int, column: int):
    """Returns the Signature of the function whose call's parentheses hold the
    place, or None."""
    lines = index.lines(path) or []
    if not path.endswith(".nx") or line >= len(lines) or not _in_code(lines[line][:column]):
        return None
    tokens = line_tokens(lines[line][:column])
    depth, commas = 0, 0
    for at in range(len(tokens) - 1, -1, -1):
        text = tokens[at][1]
        if text == ")":
            depth += 1
        elif text == "(" and depth > 0:
            depth -= 1
        elif text == "," and depth == 0:
            commas += 1
        elif text == "(":
            name = tokens[at - 1][1] if at > 0 and tokens[at - 1][0] == "name" else None
            return _signature_of(index, path, name, commas) if name else None
    return None


def _signature_of(index: FolderIndex, path: str, name: str, active: int):
    for visible in index.visible_files(path):
        place = index.nx_file(visible).functions().get(name)
        if place is not None:
            heading = index.lines(visible)[place.line].strip()
            label = heading[len("function"):].strip().rstrip(":").strip()
            # Every parameter keeps its place, even half-typed, since the
            # active one is counted by commas.
            inside = label[label.find("(") + 1:label.rfind(")")]
            parameters = [part.strip() for part in inside.split(",")] if inside.strip() else []
            return Signature(label, parameters, active)
    return None
