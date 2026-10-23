"""One layout for .nx files, as `nxwright format` writes them, in either
language. It follows the demo's code:
  - Each block's lines are indented two spaces more than its head, under the
    two spaces of an event's or a function's code.
  - "{" ends the line of if, else, while, for, and switch: `if (a == 1) {`,
    `} else if (b) {`, `} else {`. A case is indented one step inside its
    switch, and its code one step more.
  - One space around binary operators and assignments, after commas and
    semicolons, and between if, while, for, or switch and its "(". No space
    just inside parentheses, around a dot, or after a minus or "!" before a
    value.
  - One blank line between the file's head (its includes and constants) and
    its first event or function, and between events and functions. No blank
    line right after a heading. A run of blank lines becomes one. A comment
    above no heading stays where it is, a blank line around it (nx_files.py).
  - No spaces or tabs at the end of a line.
Left as written: a command's arguments (in `printh 0d 0a`, the spaces
matter), strings, comments with the spaces before them, `int` declarations,
labels, and any line that is not code nxlang can read. A comment line inside
an event or a function takes the indentation of the code around it.
macros.nx, which is Editor code in either language, is laid out as the
Editor's own language, its macros as events (format_macros).

The formatter only lays text out. Whether the result still compiles to the
same Editor code is for its caller to check (source/formatting.py): the
build copies indentation into the project, so formatting changes a
project's bytes, though never what its code does.
"""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import LABEL, command_word, split_line
from nxwright.language.nxlang import FUNCTION_SIGNATURE, PARAMETER, tokenize
from nxwright.source.nx_files import CODE_INDENT, event_blocks, macro_blocks

_HEAD = re.compile(r"(if|while|for|switch)\s*\((.*)\)")
_ELSE_IF = re.compile(r"else\s+if\s*\((.*)\)")
_CASE = re.compile(r"case\b\s*(.*?)\s*:")
_DEFAULT = re.compile(r"default\s*:")
_LEADING_WORD = re.compile(r"(var|return|const)\b\s*(.*)")
_INCLUDE = re.compile(r'include\s+("[^"]*")')
# Words nxlang reads before a line could be a command.
_NXLANG_WORDS = {"var", "return", "const", "include", "case", "default", "break", "continue",
                 "switch"}
# The kinds of the tokens after which a "-" is a subtraction rather than a
# minus sign: values, the form '&name&' among them.
_VALUES = {"name", "number", "string", "reference", "own"}


def format_code(text: str, nxlang: bool, program: bool = False) -> str:
    """Returns a .nx file's text laid out as the module describes. `nxlang`
    says the folder's language; `program` that the file is program.nx, whose
    code stands at the left margin with no headings.

    Raises NxwrightError for a file whose events cannot be read, which the
    build refuses too."""
    if program:
        return _join_sections([_format_body(text.split("\n"), "", nxlang)])
    head, end = [] if nxlang else None, []
    blocks = event_blocks(text, "file", head, end)
    return _join_sections([_format_body([line for _, line in head or []], "", nxlang)]
                          + _formatted_blocks(blocks.values(), nxlang) + [_comment_section(end)])


def format_macros(text: str) -> str:
    """Returns macros.nx's text laid out as the module describes, as the
    Editor's own language whatever the folder's: each macro under its
    heading, its code as an event's.

    Raises NxwrightError for a file whose macros cannot be read, which the
    build refuses too."""
    end = []
    blocks = macro_blocks(text, "file", end)
    return _join_sections(_formatted_blocks(blocks.values(), False) + [_comment_section(end)])


def _formatted_blocks(blocks, nxlang: bool) -> list:
    """Returns each block laid out, as sections of lines: the comment above
    no heading before it, if any, then its comment, its heading, and its
    body."""
    sections = []
    for block in blocks:
        sections.append(_comment_section(block.detached))
        sections.append([line.rstrip() for _, line in block.comment]
                        + [_format_heading(block.heading)]
                        + _format_body([line for _, line in block.lines], CODE_INDENT, nxlang))
    return sections


def _comment_section(lines: list) -> list:
    """Returns comment lines above no heading, (line number, text), laid out:
    one blank line between their groups, and none around them."""
    section = []
    for _, line in lines:
        if line.strip() or (section and section[-1]):
            section.append(line.rstrip())
    while section and not section[-1]:
        section.pop()
    return section


def _join_sections(sections: list) -> str:
    """Joins the file's head and blocks with one blank line between them."""
    kept = [section for section in sections if section]
    return "\n\n".join("\n".join(section) for section in kept) + "\n" if kept else ""


def _format_heading(heading: str) -> str:
    """Returns a heading laid out: a function's, with its parameters and
    result spaced as `function name(a: number, b: text) -> text:`."""
    match = FUNCTION_SIGNATURE.fullmatch(heading)
    if match is None:
        return heading.rstrip()
    parts = [part for part in match[2].split(",")] if match[2].strip() else []
    parameters = [PARAMETER.fullmatch(part) for part in parts]
    if not all(parameters):
        return heading.rstrip()
    result = " -> %s" % match[3] if match[3] else ""
    return "function %s(%s)%s:" % (match[1], ", ".join("%s: %s" % (p[1], p[2])
                                                     for p in parameters), result)


class _Block:
    """An open block while laying a body out: a switch's cases indent its code."""

    def __init__(self, is_switch: bool):
        self.is_switch, self.in_case = is_switch, False


def _format_body(lines: list, base: str, nxlang: bool) -> list:
    """Returns the lines of an event's or function's body, or of a file's
    head, laid out under the indentation `base`."""
    out, stack = [], []

    def depth() -> int:
        return sum(1 + (block.is_switch and block.in_case) for block in stack)

    def emit(code: str, comment: str, extra: int = 0):
        out.append([depth() + extra, code, comment])

    for line in lines:
        if not line.strip():
            if out and out[-1] is not None:
                out.append(None)    # a blank line; runs of them become one
            continue
        try:
            _, code, comment = split_line(line, 0)
        except NxwrightError:
            emit(line.strip(), "")  # a string not closed: as written
            continue
        for piece, piece_comment in _pieces(code, comment):
            previous = out[-1] if out else None
            if piece == "{":
                # "{" joins its head, unless a comment stands between them.
                if previous and previous[1] and not previous[2] and not piece_comment:
                    previous[1] += " {"
                else:
                    emit("{", piece_comment)
                stack.append(_Block(previous is not None and previous[1].startswith("switch")))
            elif piece == "}":
                if stack:
                    stack.pop()
                emit("}", piece_comment)
            elif piece.startswith("else") and previous and previous[1] == "}" and not previous[2]:
                previous[1] += " " + _format_statement(piece, nxlang)
                previous[2] = piece_comment
            elif (_CASE.fullmatch(piece) or _DEFAULT.fullmatch(piece)) and stack \
                    and stack[-1].is_switch:
                stack[-1].in_case = False
                # Comment lines right above a label are about it: they take its place.
                above = len(out)
                while above > 0 and out[above - 1] is not None and not out[above - 1][1]:
                    above -= 1
                    out[above][0] = depth()
                emit(_format_statement(piece, nxlang), piece_comment)
                stack[-1].in_case = True
            elif not piece:
                emit("", piece_comment.strip())     # a comment line
            else:
                emit(_format_statement(piece, nxlang), piece_comment)
    while out and out[-1] is None:
        out.pop()
    return ["" if item is None else (base + "  " * item[0] + item[1] + item[2]).rstrip()
            for item in out]


def _pieces(code: str, comment: str) -> list:
    """Returns a line's code split at its braces, as (code, comment), the
    line's comment going with its last piece: `} else {` gives "}", "else",
    and "{"."""
    pieces = []
    if code.startswith("}"):
        pieces.append("}")
        code = code[1:].strip(" \t")
    if code.endswith("{") and code != "{":
        pieces += [code[:-1].rstrip(" \t"), "{"]
    elif code or not pieces:
        pieces.append(code)
    return [(piece, comment if position == len(pieces) - 1 else "")
            for position, piece in enumerate(pieces)]


def _format_statement(code: str, nxlang: bool) -> str:
    """Returns one statement laid out, or as written when it is not code
    nxlang can read."""
    head = _HEAD.fullmatch(code)
    else_if = _ELSE_IF.fullmatch(code)
    case = _CASE.fullmatch(code)
    leading = _LEADING_WORD.fullmatch(code) if nxlang else None
    include = _INCLUDE.fullmatch(code)
    try:
        if head:
            return "%s (%s)" % (head[1], _spaced(head[2]))
        if else_if:
            return "else if (%s)" % _spaced(else_if[1])
        if code == "else":
            return code
        if case and nxlang:
            return "case %s:" % _spaced(case[1])
        if _DEFAULT.fullmatch(code):
            return "default:"
        if include:
            return "include " + include[1]
        if leading:
            return leading[1] + (" " + _spaced(leading[2]) if leading[2] else "")
        if re.match(r"int\b", code) or LABEL.fullmatch(code):
            return code     # a declaration or a label: left as written
        word = command_word(code)
        if word is not None and not (nxlang and word in _NXLANG_WORDS):
            return word + " " + code[len(word):].strip(" \t")
        return _spaced(code)
    except NxwrightError:
        return code


def _spaced(code: str) -> str:
    """Returns an expression or assignment with the module's spacing.
    Raises NxwrightError for text that is no code."""
    tokens = tokenize(code, 0)
    out = ""
    for position, (kind, text) in enumerate(tokens):
        previous = tokens[position - 1] if position else None
        if previous is None:
            space = False
        elif text in (")", "]", ",", ";", ".", "++", "--"):
            space = False
        elif previous[1] in ("(", "[", ".") or _is_sign(tokens, position - 1):
            space = False
        elif text in ("(", "[") and previous[0] in ("name", "reference"):
            space = False   # a call, or an index
        else:
            space = True
        out += (" " if space else "") + text
    return out


def _is_sign(tokens: list, position: int) -> bool:
    """True when the token at `position` is a minus sign or a "!" before a
    value, rather than an operator between two."""
    if position < 0 or tokens[position][1] not in ("-", "!"):
        return False
    if position == 0 or tokens[position][1] == "!":
        return True
    before = tokens[position - 1]
    return before[0] not in _VALUES and before[1] not in (")", "]", "++", "--")
