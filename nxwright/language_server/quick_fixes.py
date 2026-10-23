"""The quick fixes the language server offers on the build's refusals: for a
refusal with one sure fix, the edit that makes it, which a code editor
offers on the problem and applies in one step.

The refusal says what its fix changes, as data (`NxwrightError.fix`), which
the problem carries to the editor and the editor hands back with its code
action request. Its kinds:
  - in the problem's line, a text replaced by another, its "text" and its
    "new": a command in small letters ("small-letters"), a space for the tab
    after `int` ("tab-after-int"), a hex constant's digits in pairs
    ("hex-pairs"), and a signed hex constant as its decimal ("hex-sign");
  - "declare": the program variable "variable", sys0 to sys2, declared in
    program.nx;
  - in the problem's page file, of its component "component": its vscope set
    to 1, global, for the keyboard it is bound to ("global"), or each of its
    sides under 2 set to 2 ("least-size").

Each fix is worked out from the folder's files as the server reads them, an
open file as the editor holds it, and offered only while what its refusal
names still holds, so a problem fixed by hand since offers nothing. An edit
in a line applies only where its text stands once in the line, as a whole
word, outside quoted texts: a line nxlang rewrote, or one changed since,
gets no edit where it would go wrong."""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import outside_strings, program_int_variables
from nxwright.language_server.page_editing import properties
from nxwright.source.page_edits import attribute_edits
from nxwright.testing.preview import page_of_file
from nxwright.project.editor_limits import LEAST_SIDE
from nxwright.project.page_header import SYSTEM_PAGES

PROGRAM = "program.nx"
# What each fix in a line is called, as the editor lists it, from its text
# and the text it puts in its place.
_LINE_FIX_TITLES = {
    "small-letters": lambda text, new: "Write %s in small letters" % new,
    "tab-after-int": lambda text, new: "Put a space after int",
    "hex-pairs": lambda text, new: "Write %s as %s" % (text, new),
    "hex-sign": lambda text, new: "Write %s as %s" % (text, new),
}
_WORD_CHARACTER = re.compile(r"\w")
# A line of program.nx that is no code: blank, a comment, or an include.
_NOT_CODE = re.compile(r"\s*(//.*|include\b.*)?$")


def quick_fix(index, read, path: str, line: int, fix: dict):
    """Returns (its title, {path within the folder: [TextEdit]}, their columns
    Python's, whether an editor may apply it without asking) of the quick
    fix `fix` of a problem on line `line`, from 0, of the folder's file
    `path`; None where it no longer applies, or applies in no one place.
    `read(path)` gives a file's text as the server holds it. A fix in code
    keeps its meaning, so it may be applied without asking; a fix of a page
    file changes how a component looks or works, so the user chooses it."""
    kind = fix.get("kind")
    try:
        if kind in _LINE_FIX_TITLES:
            made = _line_fix(read, path, line, kind, fix["text"], fix["new"])
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
