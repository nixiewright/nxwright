"""Comfortable code, turned into the syntax the Nextion Editor accepts.

Comfortable code is Editor code written more freely: `if (a == 1) {` rather
than `if(a==1)` with "{" on the next line. The Editor rejects spaces inside
expressions, a space between "if", "while" or "for" and "(", "{" on the line
of its "if", and "else" anywhere but right after "}" on the same line.
docs/source-folder.md lists what the Editor accepts, as compiling test pages
showed.

Rules, applied line by line; strings ("...") never change, and "//" comments
change only by losing the spaces that end them:
  - "@pic(name)", "@font(name)", "@animation(name)", "@video(name)", and
    "@sound(name)" become the ID of that resource.
  - Leading indentation is kept, and so is a trailing comment with the spaces
    before it.
  - The spaces and tabs ending a line are dropped, as the Editor's compile
    drops them.
  - A command line keeps the space after its first word and any spaces between
    arguments (printh separates bytes with them); spaces next to commas and
    operators are removed, as the Editor refuses those by an operator. A
    command line is one whose first word is followed by a space and then by
    something other than an assignment, such as "covx a,b,0,0" or "cls
    BLACK"; "if", "while", "for", "else", and "int" are not commands.
  - In any other code line every space and tab is removed, except one space
    in "else if". A line starting with "int" is a declaration, left as written.
  - "if(...) {", "while(...) {", "for(...) {" and "}else ... {" lose their "{",
    which goes on its own line at the same indentation.
  - "} else" becomes "}else". An "else" line right after a "}" line is joined
    to it.
  - Blank lines are dropped.
Code already in Editor syntax comes out unchanged, but for the spaces and tabs
ending its lines.

Each line is first checked for what the Nextion Editor refuses
(code_checks.py), as the Nextion Editor reads it. Given the object whose
event holds the code (Owner), its own attributes written '&name&' are
replaced first (with_own_attributes). The helpers that read a line are
code_lines.py's.
"""
from dataclasses import dataclass
import re

from nxwright import NxwrightError
from nxwright.language.code_checks import (ObjectNames, check_labels, check_line, check_own_forms,
                                           check_without_owner)
from nxwright.language.code_lines import (OWN_ATTRIBUTE, compact, forms_without_spaces,
                                          is_declaration, outside_strings, split_line)
from nxwright.language.resource_names import REFERENCE, ResourceNames
from nxwright.project.screen_models import ScreenModel

_ELSE_WORD = re.compile(r"else\b")


@dataclass(frozen=True)
class Owner:
    """The object whose event holds a line of code: its name, and its ID,
    its place in its page counted from 0 for the page itself. The line may
    name the owner's attributes as '&name&' (with_own_attributes)."""
    name: str
    id: int

    @staticmethod
    def among(name: str, object_names: list):
        """Returns the Owner named `name` among a page's object names in ID
        order, the page's first; None when the page has no such object."""
        return Owner(name, object_names.index(name)) if name in object_names else None


def preprocess(lines: list, names: ResourceNames = None, objects: ObjectNames = None,
               variables: frozenset = None, macros: frozenset = None,
               screen: ScreenModel = None, owner: Owner = None) -> list:
    """Returns `lines`, a list of (line number, text), as lines of text in
    Editor syntax.
    `names` resolves "@pic(...)" and the other resources' names; without it
    they are refused.
    With `objects`, every reference must name an object that exists.
    With `variables`, program.nx's int variables, a line may name sys0,
    sys1, or sys2 only when they are among them.
    With `macros`, the names of the folder's macros, a `call` must name one.
    With `screen`, the folder's screen model, a line may use no command or
    system variable its series lacks (code_checks.series_lacks).
    With `owner`, the lines are an event's, of that object: a line is
    checked as the Editor reads it (with_own_attributes). Without one, the
    form '&name&' is refused outside a quoted text, which the Editor refuses
    in program.s and in macros.

    Raises NxwrightError naming the line number of anything it cannot turn
    into Editor syntax.
    """
    return [text for _, text in preprocess_with_places(lines, names, objects, variables, macros,
                                                       screen, owner)]


def preprocess_with_places(lines: list, names: ResourceNames = None,
                           objects: ObjectNames = None, variables: frozenset = None,
                           macros: frozenset = None, screen: ScreenModel = None,
                           owner: Owner = None) -> list:
    """Returns what preprocess does, each line as (line number, text): the
    number of the line it comes from. An "else" joined to the "}" before it
    keeps the "}"'s line."""
    out = []        # [indentation, code, comment, line number] per output line
    for number, text in lines:
        if not text.strip():
            continue
        indent, code, comment = split_line(text, number)
        code = _resolve_references(code, names, number)
        check_own_forms(code, number)
        # The checks read the line as the Editor does, its forms' spaces
        # dropped and its form '&name&' replaced; the line given back is the
        # line as written.
        forms = forms_without_spaces(code)
        if owner is None:
            check_without_owner(forms, number)
            read = code
        else:
            read = with_own_attributes(forms, owner)
        try:
            check_line(read, objects, variables, macros, screen, number)
        except NxwrightError as error:
            if read == code:
                raise
            raise type(error)("%s, as the Nextion Editor reads it: %s" % (code, error.reason),
                              line=number) from None
        if is_declaration(code):
            out.append([indent, code, comment, number])
            continue
        opens_block = code.endswith("{") and code != "{"
        if opens_block:
            code = code[:-1].rstrip()
        code = compact(code)
        if _ELSE_WORD.match(code) and out and out[-1][1] == "}":
            # "else" goes right after the "}" that closes the previous block,
            # before any comment on that line.
            out[-1][1] += code
            out[-1][2] += comment
        else:
            out.append([indent, code, comment, number])
        if opens_block:
            out.append([indent, "{", "", number])
    check_labels([(number, code) for _, code, _, number in out])
    # The spaces and tabs ending a line are dropped, as the Nextion Editor's
    # compile drops them. split_line gives them with the comment.
    return [(number, (indent + code + comment).rstrip(" \t"))
            for indent, code, comment, number in out]


def with_own_attributes(text: str, owner: Owner) -> str:
    """Returns `text`, code of an event of the object `owner`, as the Editor
    reads it: each '&name&' replaced, in a quoted text too, by the owner's
    ID for `id`, and by the owner's name, a dot, and the name for any other
    name."""
    def replace(match) -> str:
        return str(owner.id) if match[1] == "id" else "%s.%s" % (owner.name, match[1])
    return OWN_ATTRIBUTE.sub(replace, text)


def _resolve_references(code: str, names, number: int) -> str:
    """Replaces "@pic(name)" and the other resources' names outside strings
    with IDs."""
    def resolve(match) -> str:
        if names is None:
            raise NxwrightError("%s needs the app's resource names" % match[0], line=number)
        try:
            return str(names.id_of(match[1], match[2].strip()))
        except NxwrightError as error:
            # The type tells an unknown name apart from other problems.
            raise type(error)(str(error), line=number) from None
    return outside_strings(code, lambda part: REFERENCE.sub(resolve, part))
