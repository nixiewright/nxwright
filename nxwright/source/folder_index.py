"""The names of a source folder, and where each one is, read for a code editor.

The index reads a source folder's app.toml, its page files
(`pages/<page>.page.toml`), and its .nx files: each page's own file, the files it
includes, and program.nx with the files it includes. It reads them line by
line and skips what it cannot read, so a half-typed file keeps the rest of
its names. The build, by contrast, stops at the first mistake.

A place is a span of one line of a file of the folder: the file's path within
the folder, with "/", the line, and the columns of the span's first character
and of the character after it. Lines and columns count from 0, as code
editors count them, and a column is a position in the line's Python string.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re
import tomllib

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.nxlang import PARAMETER, is_constant_line, token_spans
from nxwright.language.resource_names import LISTS
from nxwright.project.resources import PICTURE_SUFFIXES
from nxwright.project.screen_models import model_named
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.nx_files import (EVENT_HEADING, FUNCTION_HEADING, INCLUDE, MACRO_HEADING,
                                      resolve)
from nxwright.source.page_source import KEY_LINE, page_nx_path, page_toml_path
from nxwright.source.source_folder import NXLANG, picture_file

APP_FILE = "app.toml"
PROGRAM_FILE = "program.nx"
# The lists of app.toml that name the folder's pages, pictures, fonts,
# animations, videos, and sounds.
APP_LISTS = ("pages",) + tuple(LISTS.values())
# A TOML table's header, `[page]` or `[[component]]`.
_TABLE_HEADER = re.compile(r"\s*\[")
_PLAIN_STRING = re.compile(r'"([^"\\]*)"')


@dataclass(frozen=True)
class Place:
    """A span of one line of a file of the source folder (see the module's description)."""
    path: str
    line: int
    start: int
    end: int

    def holds(self, line: int, column: int) -> bool:
        """True when the column `column` of line `line` is in the span or just
        after it, where a cursor at the end of a name stands."""
        return line == self.line and self.start <= column <= self.end


def file_start(path: str) -> Place:
    """Returns the place at the start of the file `path`."""
    return Place(path, 0, 0, 0)


def page_of(path: str):
    """Returns the page whose .page.toml file is `path`, or None."""
    match = re.fullmatch(r"pages/([^/]+)\.page\.toml", path)
    return match[1] if match else None


def picture_of(path: str):
    """Returns the name of the picture whose file is `path`, or None."""
    match = re.fullmatch(r"pictures/(.+)(?:%s)" % "|".join(map(re.escape, PICTURE_SUFFIXES)),
                         path)
    return match[1] if match else None


@dataclass
class PageObject:
    """The page itself, or one of its components, as its table in the page
    file gives it."""
    name: str
    place: Place            # of the name, in the table's `name = "..."` line
    type: str = ""          # its type, such as "text", from the `type = "..."` line
    first_line: int = 0     # the table's header line
    last_line: int = 0      # the table's last line


@dataclass
class Block:
    """An event or a function of a .nx file, or a macro of macros.nx: its
    heading, and the lines up to the next heading."""
    name: str               # the object an event belongs to, or the function's or macro's name
    place: Place            # of that name, in the heading
    is_function: bool
    event: str = ""         # for an event, its name, such as "up"
    is_macro: bool = False
    end_line: int = 0       # the block's last line
    parameters: dict = field(default_factory=dict)  # {name: Place}, for a function
    locals: dict = field(default_factory=dict)      # {name: Place} of the first `var` of each


@dataclass
class NxFileNames:
    """The names one .nx file defines, and the files it includes."""
    path: str
    lines: list
    includes: list = field(default_factory=list)    # [(Place of the written path, its path)]
    constants: dict = field(default_factory=dict)   # {name: Place}
    globals: dict = field(default_factory=dict)     # {name: Place} of `int` declarations
    blocks: list = field(default_factory=list)      # [Block], in file order

    def block_at(self, line: int):
        """Returns the Block holding line `line`, or None before the first heading."""
        for block in self.blocks:
            if block.place.line <= line <= block.end_line:
                return block
        return None

    def functions(self) -> dict:
        """Returns {name: Place} of the functions the file defines."""
        return {block.name: block.place for block in self.blocks if block.is_function}


def line_tokens(line: str) -> list:
    """Returns the tokens of a line of code as nxlang reads them, as (kind,
    text, start, end) with columns in the line (see token_spans in nxlang.py).
    The line's comment is left out, and a string that is not closed runs to
    the end of the line."""
    try:
        indent, code, _ = split_line(line, 0)
    except NxwrightError:
        indent = line[:len(line) - len(line.lstrip(" \t"))]
        code = line[len(indent):]
    offset = len(indent)
    return [(kind, text, start + offset, end + offset)
            for kind, text, start, end in token_spans(code)]


def find_source_folder(path: Path, read):
    """Returns the source folder holding the file `path`: the nearest folder
    above it holding an app.toml, which `read(path)` returns the text of.
    Returns None when there is none."""
    for folder in path.parents:
        if read(folder / APP_FILE) is not None:
            return folder
    return None


def text_on_disk(path: Path):
    """The text of the file `path`, with LF line endings, or None when it
    cannot be read: FolderIndex's reader of a folder on disk, given each
    file's whole path."""
    try:
        return path.read_bytes().decode("utf-8-sig").replace("\r\n", "\n")
    except (OSError, UnicodeDecodeError):
        return None


class FolderIndex:
    """The names of the source folder `root`, read through `read(path)`,
    which returns a file's text with LF line endings, or None for a file that
    cannot be read.

    Attributes:
      - pages, pictures, fonts, animations, videos, sounds: the names
        app.toml lists, in order.
      - app_entries: {(list, name): Place} of each name in app.toml's lists,
        `list` being one of APP_LISTS.
      - page_objects: {page: [PageObject]}, the page first, then its components.
      - page_files: {page: [path]}, each page's .nx files: its own and those it
        includes, directly or not.
      - program_files: program.nx and the files it includes.
    """

    def __init__(self, root: Path, read):
        self.root = root
        self._read = read
        self._texts = {}
        self._nx_files = {}
        self.app_entries = self._read_app()
        (self.pages, self.pictures, self.fonts, self.animations, self.videos,
         self.sounds) = ([name for (list_name, name) in self.app_entries if list_name == kind]
                         for kind in APP_LISTS)
        self.page_objects = {page: self._read_page_objects(page) for page in self.pages}
        self.page_files = {page: self._closure(page_nx_path(page)) for page in self.pages}
        self.program_files = self._closure(PROGRAM_FILE)

    def uses_nxlang(self) -> bool:
        """Whether app.toml says the folder's code is in nxlang. One that does
        not read, as while it is half typed, says it is not."""
        return self._app_settings().get("language") == NXLANG

    def screen_series(self):
        """The series of the screen model app.toml names, as "K", or None
        when it names none nxwright knows, as while it is half typed."""
        screen = self._app_settings().get("screen")
        try:
            return model_named(screen).series if isinstance(screen, str) else None
        except NxwrightError:
            return None

    def _app_settings(self) -> dict:
        """app.toml's settings, or none when it does not read."""
        try:
            return tomllib.loads("\n".join(self.lines(APP_FILE) or []))
        except tomllib.TOMLDecodeError:
            return {}

    def picture_path(self, picture: str) -> str:
        """Returns the path, within the folder, of the picture `picture`'s
        file, its PNG or its JPEG (source_folder.picture_file)."""
        return picture_file(picture, lambda path: (self.root / path).is_file())

    def lines(self, path: str):
        """Returns the lines of the folder's file `path`, or None when it cannot be read."""
        if path not in self._texts:
            text = self._read(self.root / path)
            self._texts[path] = None if text is None else text.split("\n")
        return self._texts[path]

    def event_blocks(self, page: str, name: str) -> dict:
        """Returns {path: [block]} of the events of the object `name` that
        have code in the .nx files of `page`, in the page's file order, for
        the files that contain some. The page's files are those the index
        could read (page_files)."""
        found = {}
        for path in self.page_files.get(page, []):
            blocks = [block for block in self.nx_file(path).blocks
                      if not block.is_function and block.name == name]
            if blocks:
                found[path] = blocks
        return found

    def nx_file(self, path: str):
        """Returns the NxFileNames of the folder's .nx file `path`, or None
        when it cannot be read."""
        if path not in self._nx_files:
            lines = self.lines(path)
            self._nx_files[path] = None if lines is None else _read_nx_file(path, lines)
        return self._nx_files[path]

    def macros(self) -> dict:
        """Returns {name: Place of it in its heading} of the macros of
        macros.nx; none when the folder has no macros.nx."""
        nx_file = self.nx_file(MACROS_PATH)
        return {} if nx_file is None else {block.name: block.place for block in nx_file.blocks
                                           if block.is_macro}

    def pages_using(self, path: str) -> list:
        """Returns the pages whose code includes the .nx file `path`, or is it."""
        return [page for page, files in self.page_files.items() if path in files]

    def visible_files(self, path: str) -> list:
        """Returns the .nx files whose constants, functions, and `int`
        globals code in the .nx file `path` may use: for each page using it,
        that page's files, then program.nx and the files it includes."""
        files = []
        pages = self.pages_using(path)
        for page in pages:
            files.extend(self.page_files[page])
        if not pages and path not in self.program_files:
            files.extend(self._closure(path))
        files.extend(self.program_files)
        return list(dict.fromkeys(files))

    def names_of(self, kind: str) -> list:
        """Returns the names of the folder's resources of `kind`, such as
        PICTURE (resource_names.py), in order."""
        return getattr(self, LISTS[kind])

    def type_at(self, page: str, line: int):
        """Returns the type of the table of `page`'s page file that holds
        `line`, such as "text", or None outside a named table."""
        return next((page_object.type for page_object in self.page_objects.get(page, [])
                     if page_object.first_line <= line <= page_object.last_line), None)

    def objects_named(self, name: str, pages) -> list:
        """Returns the places of the objects called `name` on `pages`."""
        return [page_object.place for page_object in self.page_objects_named(name, pages)]

    def page_objects_named(self, name: str, pages) -> list:
        """Returns the PageObjects called `name` on `pages`."""
        return [page_object for page in pages
                for page_object in self.page_objects.get(page, []) if page_object.name == name]

    def code_files(self) -> list:
        """Returns every .nx file of the folder's pages and program, each
        once, and macros.nx when the folder has it."""
        files = [path for paths in self.page_files.values() for path in paths]
        macros = [MACROS_PATH] if self.lines(MACROS_PATH) is not None else []
        return list(dict.fromkeys(files + self.program_files + macros))

    def _read_app(self) -> dict:
        """Reads the names of app.toml's lists, with their places. A list may
        span lines; a name is any plain string after the list's key."""
        entries, key = {}, None
        for number, line in enumerate(self.lines(APP_FILE) or []):
            match = KEY_LINE.match(line)
            rest_start = match.start(2) if match else 0
            if match:
                key = match[1]
            elif _TABLE_HEADER.match(line):
                key = None
            if key not in APP_LISTS:
                continue
            for string in _PLAIN_STRING.finditer(line, rest_start):
                entries.setdefault((key, string[1]),
                                   Place(APP_FILE, number, string.start(1), string.end(1)))
        return entries

    def _read_page_objects(self, page: str) -> list:
        """Reads each table of a page file that has a `name = "..."` line."""
        path = page_toml_path(page)
        lines = self.lines(path) or []
        objects, table = [], None
        for number, line in enumerate(lines + ["["]):    # "[" ends the last table
            if _TABLE_HEADER.match(line):
                if table is not None and table.place is not None:
                    table.last_line = number - 1
                    objects.append(table)
                table = PageObject("", None, first_line=number)
                continue
            match = KEY_LINE.match(line)
            string = _PLAIN_STRING.match(match[2].strip()) if match else None
            if table is None or string is None:
                continue
            if match[1] == "name":
                start = line.index('"', match.start(2)) + 1
                table.name = string[1]
                table.place = Place(path, number, start, start + len(string[1]))
            elif match[1] == "type":
                table.type = string[1]
        return objects

    def unread_code_files(self, page: str) -> list:
        """Returns the .nx files of `page`'s code that cannot be read, which
        page_files leaves out: its own file, which a page without code
        lacks, and the files its readable files include."""
        own = page_nx_path(page)
        unread = [] if self.nx_file(own) is not None else [own]
        for path in self.page_files.get(page, []):
            for _, included in self.nx_file(path).includes:
                if self.nx_file(included) is None and included not in unread:
                    unread.append(included)
        return unread

    def _closure(self, path: str) -> list:
        """Returns `path` and every .nx file it includes, directly or not,
        leaving out the files that cannot be read."""
        found = []

        def visit(current: str):
            nx_file = self.nx_file(current)
            if nx_file is None or current in found:
                return
            found.append(current)
            for _, included in nx_file.includes:
                visit(included)
        visit(path)
        return found


def _read_nx_file(path: str, lines: list) -> NxFileNames:
    """Reads the names a .nx file defines, line by line. macros.nx holds
    macros' headings alone, which no other file holds."""
    names = NxFileNames(path, lines)
    block = None
    is_macros = path == MACROS_PATH
    for number, line in enumerate(lines):
        heading = (MACRO_HEADING.fullmatch(line) if is_macros
                   else EVENT_HEADING.fullmatch(line) or FUNCTION_HEADING.fullmatch(line))
        if heading:
            if block is not None:
                block.end_line = number - 1
            is_function = not is_macros and line.startswith("function")
            block = Block(heading[1], Place(path, number, heading.start(1), heading.end(1)),
                          is_function=is_function,
                          event="" if is_function or is_macros else heading[2],
                          is_macro=is_macros)
            if block.is_function:
                block.parameters = _parameters(path, number, line)
            names.blocks.append(block)
            continue
        _read_code_line(names, block, number, line)
    if block is not None:
        block.end_line = len(lines) - 1
    return names


def _parameters(path: str, number: int, heading: str) -> dict:
    """Returns {name: Place} of the parameters in a function's heading."""
    opening, closing = heading.find("("), heading.find(")")
    if opening < 0:
        return {}
    inside = heading[opening + 1:closing if closing > opening else len(heading)]
    found = {}
    for part in re.finditer(r"[^,]+", inside):
        parameter = PARAMETER.fullmatch(part[0])
        if parameter:
            start = opening + 1 + part.start() + parameter.start(1)
            found.setdefault(parameter[1], Place(path, number, start, start + len(parameter[1])))
    return found


def _read_code_line(names: NxFileNames, block, number: int, line: str):
    """Adds what a line other than a heading defines: an include, a constant,
    `int` globals, or a local of `block`."""
    tokens = line_tokens(line)
    if not tokens:
        return
    first = tokens[0][1]
    code = line[tokens[0][2]:]
    include = INCLUDE.match(code)
    if include:
        start = tokens[0][2] + include.start(1)
        try:
            included = resolve(names.path, include[1], number + 1)
        except NxwrightError:
            return
        names.includes.append((Place(names.path, number, start, start + len(include[1])),
                               included))
    elif is_constant_line(code) and len(tokens) > 1 and tokens[1][0] == "name":
        names.constants.setdefault(tokens[1][1], _token_place(names.path, number, tokens[1]))
    elif first == "int":
        # int a=0, b=1: each name right after `int` or a comma.
        for previous, token in zip(tokens, tokens[1:]):
            if token[0] == "name" and previous[1] in ("int", ","):
                names.globals.setdefault(token[1], _token_place(names.path, number, token))
    elif first == "var" and block is not None and len(tokens) > 1 and tokens[1][0] == "name":
        block.locals.setdefault(tokens[1][1], _token_place(names.path, number, tokens[1]))


def _token_place(path: str, number: int, token: tuple) -> Place:
    return Place(path, number, token[2], token[3])
