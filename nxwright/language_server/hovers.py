"""What a code editor shows when the pointer rests on a name: its definition,
or what it stands for.

  - A component or page: its table from the page file, which gives its type,
    its place and size, and the attributes it sets.
  - A function: its heading, after the comment right above it.
  - A constant, local, parameter, or `int` global: the line declaring it.
  - A picture: the picture. A font: its height and characters, from its
    font file's header. An animation, video, or sound: its files.
  - An included file: its path.
  - A generated variable, such as `__g3_17`, in a folder in nxlang: what the
    compiler added it for.
  - An attribute, in code after a component's name and a dot, as `txt` in
    `t0.txt` or `settings.t0.txt`, or as a key of a page file's table: its
    description, choices, and whether code can change it, for each type the
    component may have (attributes.py).
The text is Markdown.
"""
import re

from nxwright import NxwrightError
from nxwright.language.nxlang import GENERATED_GLOBAL, GENERATED_NAME, GENERATED_PREFIX
from nxwright.language.resource_names import KIND_OF_LIST, NOUNS
from nxwright.language_server.attributes import (attribute_markdown, has_attribute,
                                                 type_defaults)
from nxwright.language_server.file_texts import uri_of
from nxwright.source.folder_index import (APP_FILE, FolderIndex, file_start,
                                          line_tokens, page_of, picture_of)
from nxwright.source.references import targets_at
from nxwright.project.zi_font import ONE_BYTE_ENCODINGS, UTF8, font_facts, parse_font_header
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import RESOURCE_FILES

# A page file's line giving a key, as `pic = "logo"`.
_KEY = re.compile(r"\s*([A-Za-z0-9_]+)\s*=")
# What each kind of generated component is for, by the letter after the
# generated prefix.
_GENERATED_KINDS = {"v": "a text the compiler keeps for a local, a parameter, a result, or "
                         "a switch's value",
                    "s": "a text temporary, holding part of an expression for one statement",
                    "f": "the hotspot running the page's functions of one call depth"}


def hover(index: FolderIndex, path: str, line: int, column: int):
    """Returns the Markdown text for the name at a place, or None."""
    generated = _generated(index, path, line, column)
    if generated:
        return generated
    attribute = _attribute(index, path, line, column)
    if attribute:
        return attribute
    texts = [_describe(index, target) for target in targets_at(index, path, line, column)]
    texts = [text for text in texts if text]
    return "\n\n---\n\n".join(texts) if texts else None


def _describe(index: FolderIndex, target):
    """Returns the Markdown describing what the place `target` defines."""
    picture = picture_of(target.path)
    if picture:
        return "Picture `%s`\n\n![%s](%s)" % (picture, picture, uri_of(index.root / target.path))
    if target.path == APP_FILE:
        return _app_entry(index, target)
    if target.end == 0:
        return "File `%s`" % target.path
    if target.path.endswith(".toml"):
        for objects in index.page_objects.values():
            for page_object in objects:
                if page_object.place == target:
                    lines = index.lines(target.path)
                    table = lines[page_object.first_line:page_object.last_line + 1]
                    return _code("toml", [text for text in table if text.strip()])
        return None
    lines = index.lines(target.path)
    nx_file = index.nx_file(target.path)
    shown = [lines[target.line].strip()]
    block = nx_file.block_at(target.line)
    if block is not None and block.is_function and block.place == target:
        first = target.line
        while first > 0 and lines[first - 1].startswith("//"):
            first -= 1
        shown = lines[first:target.line] + shown
    return _code("nxwright", shown)


def _app_entry(index: FolderIndex, target):
    """Returns the text for a name in one of app.toml's lists."""
    for (list_name, name), place in index.app_entries.items():
        if place == target:
            if list_name == "fonts":
                return _font(index, name)
            if list_name == "pictures":
                return _describe(index, file_start(index.picture_path(name)))
            if list_name == "pages":
                return "Page `%s`, in `%s`" % (name, page_toml_path(name))
            files = ["`%s/%s%s`" % (list_name, name, suffix)
                     for suffix in RESOURCE_FILES[list_name]]
            return "%s `%s`, in %s" % (NOUNS[KIND_OF_LIST[list_name]].capitalize(), name,
                                       " and ".join(files))
    return None


def _font(index: FolderIndex, name: str) -> str:
    try:
        block = (index.root / "fonts" / (name + ".zi")).read_bytes()
        header = parse_font_header(block)
        # A full utf-8 table's header counts every code point to U+FFFF, so
        # a utf-8 font's facts give the characters it holds, whatever its table.
        utf8 = font_facts(block) if header.encoding == UTF8 else None
    except (OSError, NxwrightError):
        return "Font `%s`" % name
    if utf8:
        return "Font `%s`: %d pixels high, %d characters in utf-8" % (name, utf8.height,
                                                                      utf8.character_count)
    # A two-byte font's header gives the range of a character's second byte
    # where a one-byte font's gives its first and last character.
    if header.encoding is not None and header.encoding not in ONE_BYTE_ENCODINGS:
        return "Font `%s`: %d pixels high, %d characters in %s" % (
            name, header.height, header.character_count, header.encoding)
    return ("Font `%s`: %d pixels high, characters %d to %d (%d characters)"
            % (name, header.height, header.first_character, header.last_character,
               header.character_count))


def _generated(index: FolderIndex, path: str, line: int, column: int):
    """Returns the text for a generated variable's name at a place, or None.
    In a folder in the Editor's own language, nothing is generated."""
    if not index.uses_nxlang():
        return None
    lines = index.lines(path) or []
    tokens = line_tokens(lines[line]) if line < len(lines) else []
    names = [text for kind, text, start, end in tokens
             if kind == "name" and start <= column <= end]
    if not names:
        return None
    number = GENERATED_GLOBAL.fullmatch(names[0])
    if number:
        page = int(number[1])
        page_name = " (`%s`)" % index.pages[page] if page < len(index.pages) else ""
        return ("A number variable the compiler added: a global of program.s, the %s of "
                "page %d%s." % (_ordinal(int(number[2]) + 1), page, page_name))
    if GENERATED_NAME.fullmatch(names[0]):
        kind = names[0][len(GENERATED_PREFIX)]
        return "A component the compiler added to the page: %s." % _GENERATED_KINDS[kind]
    return None


def _attribute(index: FolderIndex, path: str, line: int, column: int):
    """Returns the Markdown for the attribute at a place, or None. Each type
    the component may have is described once, and only a type having the
    attribute: a page's name before a dot, as in `settings.t0`, is no
    component with an attribute `t0`."""
    lines = index.lines(path) or []
    if line >= len(lines):
        return None
    page = page_of(path)
    if page is not None:
        found = _attribute_in_page_file(index, page, lines[line], line, column)
    elif path.endswith(".nx"):
        found = _attribute_in_code(index, path, lines[line], column)
    else:
        found = None
    if found is None:
        return None
    attribute, types = found
    defaults = type_defaults(index)
    texts = [attribute_markdown(type_name, attribute) for type_name in dict.fromkeys(types)
             if has_attribute(defaults, type_name, attribute)]
    texts = [text for text in texts if text]
    return "\n\n---\n\n".join(texts) if texts else None


def _attribute_in_code(index: FolderIndex, path: str, text: str, column: int):
    """Returns (the attribute, the types of the components it may belong to)
    for the name at `column` of a .nx file's line, when a component's name
    and a dot come before it, or None. The component is the named page's
    when a page's name and a dot come before it too; else it is any of the
    pages using the file."""
    tokens = line_tokens(text)
    at = next((at for at, (kind, _, start, end) in enumerate(tokens)
               if kind == "name" and start <= column <= end), None)
    if at is None or at < 2 or tokens[at - 1][1] != "." or tokens[at - 2][0] != "name":
        return None
    pages = index.pages_using(path)
    if at >= 4 and tokens[at - 3][1] == "." and tokens[at - 4][1] in index.pages:
        pages = [tokens[at - 4][1]]
    objects = index.page_objects_named(tokens[at - 2][1], pages)
    return tokens[at][1], [page_object.type for page_object in objects]


def _attribute_in_page_file(index: FolderIndex, page: str, text: str, line: int, column: int):
    """Returns (the attribute, [the type of its table's object]) for the key
    at `column` of a page file's line, or None."""
    key = _KEY.match(text)
    if key is None or not key.start(1) <= column <= key.end(1):
        return None
    for page_object in index.page_objects.get(page, []):
        if page_object.first_line < line <= page_object.last_line:
            return key[1], [page_object.type]
    return None


def _ordinal(number: int) -> str:
    suffix = "th" if 10 <= number % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(number % 10,
                                                                                   "th")
    return "%d%s" % (number, suffix)


def _code(language: str, lines: list) -> str:
    return "```%s\n%s\n```" % (language, "\n".join(lines))
