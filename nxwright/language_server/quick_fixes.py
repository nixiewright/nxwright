"""The quick fixes the language server offers on the build's refusals. A
refusal gets a quick fix when one edit is sure to correct it. A code editor
offers that edit on the problem, and the user applies it in one step. One
fix is not sure: the fix for an unknown name writes the name that was
probably meant, which is a guess.

A refusal carries what its fix changes as data (`NxwrightError.fix`). The
problem passes that data to the code editor, which hands it back with its
request for code actions. The data's "kind" is one of:
  - a replacement of the text "text" by the text "new" in the problem's
    line:
      - "small-letters" writes a command in small letters;
      - "tab-after-int" writes a space in place of the tab after `int`;
      - "hex-pairs" writes a hex constant's digits in pairs;
      - "hex-sign" writes a signed hex constant as a decimal number;
      - "name-meant" writes the name that was probably meant in place of an
        unknown name, such as `title` for `Title`;
  - "declare", which declares the program variable "variable", one of sys0
    to sys2, in program.nx;
  - a change to the component "component" in the problem's page file:
      - "global" sets its vscope to 1, global, for the keyboard it is bound
        to;
      - "least-size" sets each of its sides under 2 to 2.

The server works out each fix from the folder's files, and from the code
editor's text for a file that is open. It offers a fix only while what the
refusal reported is still true, so a problem that was corrected by hand
since then gets no fix. The server replaces a text in a line only if the
text appears exactly once in the line, as a whole word outside quoted
texts. That way, a line that nxlang rewrote, or that changed after the
refusal, never gets an edit in the wrong place."""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import outside_strings, program_int_variables
from nxwright.language_server.page_editing import properties
from nxwright.source.page_edits import attribute_edits
from nxwright.testing.preview import page_of_file
from nxwright.project.editor_limits import LEAST_SIDE
from nxwright.project.page_header import SYSTEM_PAGES

PROGRAM = "program.nx"
# The title a code editor shows for each fix in a line, made from the text
# that the fix replaces and the text that it writes.
_LINE_FIX_TITLES = {
    "small-letters": lambda text, new: "Write %s in small letters" % new,
    "tab-after-int": lambda text, new: "Put a space after int",
    "hex-pairs": lambda text, new: "Write %s as %s" % (text, new),
    "hex-sign": lambda text, new: "Write %s as %s" % (text, new),
    "name-meant": lambda text, new: "Change %s to %s" % (text, new),
}
# The fixes in a line that are a guess at what was meant. They change what
# the code means, so an editor offers them and never applies them unasked.
_GUESSED_FIXES = frozenset({"name-meant"})
_WORD_CHARACTER = re.compile(r"\w")
# A line of program.nx that is no code: blank, a comment, or an include.
_NOT_CODE = re.compile(r"\s*(//.*|include\b.*)?$")


def quick_fix(index, read, path: str, line: int, fix: dict):
    """Returns the quick fix `fix` for a problem on line `line` of the
    folder's file `path`, or None if the fix no longer applies or there is
    not exactly one place to apply it. Lines are counted from 0.

    The fix is returned as (title, {path within the folder: [TextEdit]},
    whether a code editor may apply it without asking). Each TextEdit gives
    its range in Python columns. `read(path)` returns the text the server
    has for a file.

    A code editor may apply a fix without asking when the fix keeps the
    code's meaning. The user chooses the other fixes: one that guesses the
    name that was meant, and one that edits a page file, because that edit
    changes how a component looks or works."""
    kind = fix.get("kind")
    try:
        if kind in _LINE_FIX_TITLES:
            made = _line_fix(read, path, line, kind, fix["text"], fix["new"])
            if kind in _GUESSED_FIXES:
                return None if made is None else (*made, False)
        elif kind == "declare":
            made = _declaration(read, fix["variable"])
        elif kind in ("global", "least-size"):
            made = _page_file_fix(index, read, path, kind, fix["component"])
            return None if made is None else (*made, False)
        else:
            return None
    except NxwrightError:
        return None     # the file no longer reads as the fix needs it
    return None if made is None else (*made, True)


def place_in_line(line: str, text: str):
    """Returns the column where `text` stands once in `line`, as a whole word
    outside quoted texts, or None. Where `text` starts or ends with a letter,
    digit, or underscore, no such character may stand just before or after
    it, so that `0x123` is not found in `0x1234`."""
    # Each character outside quoted texts marked, the line keeping its length.
    marked = outside_strings(line, lambda part: "\0" * len(part))
    places = []
    start = line.find(text)
    while start >= 0:
        end = start + len(text)
        if (all(marked[column] == "\0" for column in range(start, end))
                and not (_WORD_CHARACTER.match(text[0]) and start > 0
                         and _WORD_CHARACTER.match(line[start - 1]))
                and not (_WORD_CHARACTER.match(text[-1]) and end < len(line)
                         and _WORD_CHARACTER.match(line[end]))):
            places.append(start)
        start = line.find(text, start + 1)
    return places[0] if len(places) == 1 else None


def _line_fix(read, path: str, line: int, kind: str, text: str, new: str):
    """Returns the fix replacing `text` with `new` in line `line` of `path`."""
    lines = read(path).split("\n")
    column = place_in_line(lines[line], text) if line < len(lines) else None
    if column is None:
        return None
    edit = _edit(line, column, line, column + len(text), new)
    return _LINE_FIX_TITLES[kind](text, new), {path: [edit]}


def _declaration(read, variable: str):
    """Returns the fix declaring `variable` in program.nx, before its first
    line of code other than an include, and before the comment lines
    directly above it, so that their comment stays with its line."""
    text = read(PROGRAM)
    if variable in program_int_variables(text):
        return None
    title, declaration = "Declare %s in program.nx" % variable, "int %s=0" % variable
    lines = text.split("\n")
    first = next((number for number, line in enumerate(lines) if not _NOT_CODE.match(line)),
                 None)
    if first is None and lines[-1] != "":
        # No code to go before, and no line ending at the end: after the last line.
        end = (len(lines) - 1, len(lines[-1]))
        return title, {PROGRAM: [_edit(*end, *end, "\n" + declaration)]}
    if first is None:
        place = len(lines) - 1      # at the end, which a line ending closes
    else:
        place = first
        while place > 0 and lines[place - 1].lstrip().startswith("//"):
            place -= 1
    return title, {PROGRAM: [_edit(place, 0, place, 0, declaration + "\n")]}


def _page_file_fix(index, read, path: str, kind: str, component: str):
    """Returns the fix of the component `component` of the page file `path`:
    made global for its keyboard, or each side under LEAST_SIDE made it."""
    page = page_of_file(path)
    if page is None or not path.endswith(".page.toml"):
        return None
    values = {attribute["name"]: attribute["value"]
              for attribute in properties(index, read, page, component)["attributes"]}
    if kind == "global":
        if values.get("key") not in SYSTEM_PAGES.values() or values.get("vscope") == 1:
            return None
        changes, title = {"vscope": "1"}, "Make %s global, as its keyboard needs" % component
    else:
        changes = {side: str(LEAST_SIDE) for side in ("w", "h")
                   if isinstance(values.get(side), int) and values[side] < LEAST_SIDE}
        if not changes:
            return None
        title = "Make %s %s" % (component, " and ".join(
            {"w": "%d pixels wide", "h": "%d pixels high"}[side] % LEAST_SIDE
            for side in changes))
    return title, {path: attribute_edits(index, read, page, component, changes)}


def _edit(line: int, start: int, end_line: int, end: int, text: str) -> dict:
    """The protocol's TextEdit replacing a range of Python columns with `text`."""
    return {"range": {"start": {"line": line, "character": start},
                      "end": {"line": end_line, "character": end}},
            "newText": text}
