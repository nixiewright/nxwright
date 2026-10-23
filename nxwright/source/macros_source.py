"""A project's macros, in the Editor's block of them and in a source folder.

The Editor 1.68.2 keeps the macros, which `call <name>` runs, in a block of
the project file, comcode.sn (format.md): each macro in its tab's order, its
name, then its number of lines, then its lines, each line ending in CR LF,
in UTF-8 whatever the project's encoding. A project without macros has no
such block.

A source folder keeps them in macros.nx: each macro under a heading,
`macro <name>:`, its lines indented by two spaces, as an event's are
(nx_files.py). Comment lines right above a heading are the macro's comment.
The build puts them first in the macro's code, marked as an event's comment
is, and extracting moves them back. A folder without macros has no
macros.nx.

A macro's name is letters, digits, underscores, and spaces, starting with a
letter or an underscore, and not ending with a space: what the Editor's tab
was seen to take. Renaming a macro there, it refused a hyphen, a digit
first, and a name another macro has. Names are told apart by case.
"""
import re

from nxwright import MissingFileError, NxwrightError
from nxwright.language.code_checks import ObjectNames
from nxwright.language.code_preprocessor import preprocess, preprocess_with_places
from nxwright.language.nxlang import Macro
from nxwright.source.editor_code_merge import keep_comfortable_blocks
from nxwright.source.nx_files import (CODE_INDENT, EVENT_COMMENT_MARKER, blank_lines_dropped,
                                      macro_blocks)

MACROS_PATH = "macros.nx"
MACRO_NAME = re.compile(r"[A-Za-z_](?:[A-Za-z0-9_ ]*[A-Za-z0-9_])?")
# The end of each of the block's lines.
_LINE_END = "\r\n"


def check_macro_name(name: str):
    """Raises NxwrightError for a macro name nxwright cannot tell the Editor
    takes (MACRO_NAME)."""
    if not MACRO_NAME.fullmatch(name):
        raise NxwrightError("%s: a macro's name is letters, digits, underscores, and spaces, "
                            "starting with a letter or an underscore, as the Nextion Editor "
                            "takes it" % name)


def macros_from_block(block: bytes) -> tuple:
    """Returns ([(name, [line])] of the macros of a comcode.sn block, in their
    order; the warnings of the blank lines it dropped, one per macro). The
    tab drops a blank line, so only a block written by hand holds one. The
    build drops them too, so macros.nx could not give them back. Raises
    NxwrightError for a block that is not one, a name nxwright cannot take
    (check_macro_name), and a name twice."""
    try:
        text = block.decode("utf-8")
    except UnicodeDecodeError:
        raise NxwrightError("the macros are not in UTF-8, as the Nextion Editor "
                            "stores them") from None
    if text and not text.endswith(_LINE_END):
        raise NxwrightError("the macros' block does not end with a line end")
    lines = text.split(_LINE_END)[:-1]
    macros, warnings, position = [], [], 0
    while position < len(lines):
        name, count = lines[position], lines[position + 1] if position + 1 < len(lines) else ""
        if not (count.isascii() and count.isdigit()):
            raise NxwrightError("macro %s: its count of lines is not a number" % name)
        # The spaces and tabs ending a line are dropped, as the build drops them.
        body = [line.rstrip(" \t") for line in lines[position + 2:position + 2 + int(count)]]
        if len(body) < int(count):
            raise NxwrightError("the macros' block is cut short, in macro %s" % name)
        kept = [line for line in body if line.strip()]
        if len(kept) < len(body):
            warnings.append(blank_lines_dropped("macro %s" % name, len(body) - len(kept)))
        check_macro_name(name)
        if name in (taken for taken, _ in macros):
            raise NxwrightError("the macros' block holds the macro %s twice" % name)
        macros.append((name, kept))
        position += 2 + int(count)
    return macros, warnings


def block_from_macros(macros: list) -> bytes:
    """Returns the comcode.sn block of `macros`, [(name, [line])]."""
    return "".join(name + _LINE_END + str(len(lines)) + _LINE_END
                   + "".join(line + _LINE_END for line in lines)
                   for name, lines in macros).encode("utf-8")


def macros_to_source(macros: list) -> str:
    """Returns macros.nx for `macros`, [(name, [line])], as an extract writes
    it: a macro's first lines marked as its comment go back above its
    heading."""
    texts = []
    for name, lines in macros:
        comment = []
        while lines and lines[0].startswith(EVENT_COMMENT_MARKER):
            comment.append("//" + lines[0][len(EVENT_COMMENT_MARKER):])
            lines = lines[1:]
        texts.append("\n".join(comment + ["macro %s:" % name]
                               + [CODE_INDENT + line for line in lines]) + "\n")
    return "\n".join(texts)


def read_macros_text(read):
    """Returns the text of the macros.nx of the source folder whose files
    `read(path)` returns, or None when it has none."""
    try:
        return read(MACROS_PATH)
    except MissingFileError:
        return None


def callable_macros(text) -> frozenset:
    """Returns the names a `call` may name, those of the macros macros.nx's
    `text` holds: none when the folder has no macros.nx, `text` None. None
    when the file does not read, so that calls go unchecked while the build
    of the macros says what is wrong, once."""
    if text is None:
        return frozenset()
    try:
        return frozenset(macro_blocks(text, MACROS_PATH))
    except NxwrightError:
        return None


def followed_macros(read) -> dict:
    """Returns the macros of the source folder whose files `read(path)`
    returns, as the compiler follows them where nxlang code calls one
    (nxlang.Macro): {name: Macro}. None are returned when the folder has no
    macros.nx, or when the file does not read: the build of the macros then
    says what is wrong, once."""
    try:
        text = read_macros_text(read)
        blocks = macro_blocks(text, MACROS_PATH) if text is not None else {}
    except NxwrightError:
        return {}
    return {name: Macro(MACROS_PATH, block.number, tuple(block.code_lines()))
            for name, block in blocks.items()}


def compiled_macros(text: str, names, page_objects: dict, page_globals: dict,
                    variables: frozenset, absent_attributes: dict = None, screen=None) -> dict:
    """Returns {name: [(line number, Editor code line)]} of macros.nx's
    `text`, in its order: each macro's code turned into Editor syntax and
    checked as a page's is (code_preprocessor.py), its comment first, as
    lines of no number. `names` resolves resources' names. `page_objects`,
    {page: {object name: type}}, and `page_globals`, {page: the names of its
    components of global scope}, None for a page whose file does not read,
    hold what a macro reaches, and `absent_attributes`, {page: {name:
    {attribute: why}}}, the attributes their components lack. `variables`
    are program.nx's int variables. With `screen`, the folder's
    ScreenModel, no line may use a command or a system variable its series
    lacks.
    Raises NxwrightError naming macros.nx and the line at fault."""
    objects = ObjectNames(frozenset(), page_objects, None, page_globals, absent_attributes)
    blocks = macro_blocks(text, MACROS_PATH)
    macros = {}
    for name, block in blocks.items():
        try:
            check_macro_name(name)
        except NxwrightError as error:
            raise NxwrightError(str(error), file=MACROS_PATH, line=block.number) from None
        try:
            code = preprocess_with_places(block.code_lines(), names, objects, variables,
                                          frozenset(blocks), screen)
        except NxwrightError as error:
            raise error.in_file(MACROS_PATH) from None
        macros[name] = [(None, line) for line in block.marked_comment()] + code
    return macros


def block_of_compiled(macros: dict) -> bytes:
    """Returns the comcode.sn block of macros compiled_macros returns."""
    return block_from_macros([(name, [line for _, line in lines])
                              for name, lines in macros.items()])


def keep_comfortable_macros(fresh: str, old: str, names) -> str:
    """Returns `fresh`, macros.nx as an extract writes it, with each macro's
    block taken from `old` instead when its code turns into the same Editor
    code, as for events (editor_code_merge.keep_comfortable_blocks)."""
    def editor_code(_, block) -> list:
        try:
            return block.marked_comment() + preprocess(block.code_lines(), names)
        except NxwrightError as error:
            raise error.in_file(MACROS_PATH) from None
    old_end = []
    return keep_comfortable_blocks(macro_blocks(fresh, MACROS_PATH),
                                   macro_blocks(old, MACROS_PATH, old_end), editor_code,
                                   lambda name: "macro %s:" % name, old_end)
