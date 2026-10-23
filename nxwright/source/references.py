"""Where a name of a source folder is used: what a code editor lists for Find
All References.

A place uses a name when Ctrl+click there would open the name's definition
(definitions.py), so the two can never disagree. The search reads each
place where the name's text stands as a whole word, in the folder's .nx
files, its page files, and app.toml, and keeps those whose definitions
include the name's. An included file is used by the include lines that
name it, however each writes its path.

On a definition itself, such as a component's table or a constant's `const`
line, the name is the one defined there.
"""
import re

from nxwright.source.definitions import definitions
from nxwright.source.folder_index import (APP_FILE, FolderIndex, Place, file_start,
                                          picture_of)
from nxwright.source.page_source import page_toml_path


def targets_at(index: FolderIndex, path: str, line: int, column: int) -> list:
    """Returns the places defining the name at a place: its definitions, or
    the place itself when it is a definition that no lookup reaches, such as
    a component's name in its table."""
    found = definitions(index, path, line, column)
    if found:
        return found
    for place in _declarations_without_lookup(index):
        if place.path == path and place.holds(line, column):
            return [place]
    return []


def references(index: FolderIndex, path: str, line: int, column: int,
               with_declarations: bool) -> list:
    """Returns the places using the name at a place, in file order, and with
    `with_declarations`, the places defining it first. Returns [] where there
    is no name."""
    targets = targets_at(index, path, line, column)
    found = [target for target in targets if with_declarations and target.end > 0]
    texts = set()
    for target in targets:
        if target.end > 0:
            texts.add(index.lines(target.path)[target.line][target.start:target.end])
        elif picture_of(target.path):
            texts.add(picture_of(target.path))
    for file in _searched_files(index):
        for number, text in enumerate(index.lines(file) or []):
            for place in _occurrences(file, number, text, texts):
                # A definition defines itself: it is listed only with the declarations.
                if place in found or place in targets:
                    continue
                if set(definitions(index, file, number, place.start)) & set(targets):
                    found.append(place)
    for file in index.code_files():
        for place, included in index.nx_file(file).includes:
            if file_start(included) in targets and place not in found:
                found.append(place)
    return found


def _declarations_without_lookup(index: FolderIndex) -> list:
    """Returns the definitions that no Ctrl+click reaches from where they
    stand: each object's name in its page file, and each name in app.toml."""
    places = [page_object.place for objects in index.page_objects.values()
              for page_object in objects]
    return places + list(index.app_entries.values())


def _searched_files(index: FolderIndex) -> list:
    pages = [page_toml_path(page) for page in index.pages]
    return index.code_files() + pages + [APP_FILE]


def _occurrences(file: str, number: int, text: str, names) -> list:
    """Returns the places in line `text` where one of `names` stands as a
    whole word, not part of a longer name or path."""
    return [Place(file, number, match.start(), match.end())
            for name in names
            for match in re.finditer(r"(?<![\w/])%s(?![\w/])" % re.escape(name), text)]
