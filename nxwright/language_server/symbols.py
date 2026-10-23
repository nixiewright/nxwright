"""The symbols of a source folder: the outline of one file, and the names a
search across the folder finds.

A .nx file's outline lists its constants, `int` globals, functions, and
events, as `on save.up`; macros.nx's, its macros, as `macro my name`. A page
file's outline lists the page, holding its components, each with its type.
The search finds pages, components, functions, macros, and constants.
"""
from dataclasses import dataclass, field

from nxwright.source.folder_index import FolderIndex, Place, page_of

# The protocol's numbers for kinds of symbol.
CLASS, FIELD, FUNCTION, VARIABLE, CONSTANT, EVENT = 5, 8, 12, 13, 14, 24


@dataclass
class Symbol:
    """A named thing of a file: its name's place, and the lines it spans."""
    name: str
    kind: int
    place: Place
    first_line: int
    last_line: int
    detail: str = ""
    children: list = field(default_factory=list)


def file_symbols(index: FolderIndex, path: str) -> list:
    """Returns the Symbols of the outline of the folder's file `path`."""
    if page_of(path):
        return _page_symbols(index, page_of(path))
    nx_file = index.nx_file(path) if path.endswith(".nx") else None
    if nx_file is None:
        return []
    symbols = [Symbol(name, kind, place, place.line, place.line)
               for names, kind in ((nx_file.constants, CONSTANT), (nx_file.globals, VARIABLE))
               for name, place in names.items()]
    for block in nx_file.blocks:
        if block.is_function:
            name = block.name
        elif block.is_macro:
            name = "macro " + block.name
        else:
            name = "on %s.%s" % (block.name, block.event)
        symbols.append(Symbol(name, FUNCTION if block.is_function or block.is_macro else EVENT,
                              block.place, block.place.line, block.end_line))
    return sorted(symbols, key=lambda symbol: symbol.first_line)


def _page_symbols(index: FolderIndex, page: str) -> list:
    objects = index.page_objects.get(page, [])
    if not objects:
        return []
    symbols = [Symbol(page_object.name, FIELD, page_object.place, page_object.first_line,
                      page_object.last_line, page_object.type) for page_object in objects]
    page_symbol = symbols[0]
    page_symbol.kind = CLASS
    page_symbol.last_line = symbols[-1].last_line
    page_symbol.children = symbols[1:]
    return [page_symbol]


def folder_symbols(index: FolderIndex, query: str) -> list:
    """Returns (Symbol, container) for the pages, components, functions,
    macros, and constants whose name holds `query`, ignoring case. The
    container is the page a component belongs to, or the file a function,
    macro, or constant is in."""
    query = query.lower()
    found = []
    for page, objects in index.page_objects.items():
        for position, page_object in enumerate(objects):
            symbol = Symbol(page_object.name, CLASS if position == 0 else FIELD,
                            page_object.place, page_object.first_line, page_object.last_line,
                            page_object.type)
            found.append((symbol, "" if position == 0 else page))
    for path in index.code_files():
        nx_file = index.nx_file(path)
        for name, place in nx_file.constants.items():
            found.append((Symbol(name, CONSTANT, place, place.line, place.line), path))
        for block in nx_file.blocks:
            if block.is_function or block.is_macro:
                found.append((Symbol(block.name, FUNCTION, block.place, block.place.line,
                                     block.end_line), path))
    return [(symbol, container) for symbol, container in found if query in symbol.name.lower()]
