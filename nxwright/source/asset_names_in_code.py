"""Writing names for the pictures and fonts that a project's code gives as numbers,
when a project is extracted into a source folder.

A project's code gives a picture or a font, called an asset here, by its ID, as in
`b0.pic=3`. A name such as `@pic(logo)` reads better, and follows the asset if its ID
changes. The build turns the name back into the same number, so the project does not
change.

A number becomes a name only where it can mean nothing but that asset:
  - assigned on its own to an attribute that selects a picture or a font;
  - as the picture argument of pic, picq, or xpic, or the font argument of xstr.
Any other number stays, because it may mean something else, as in `sys0=3`. A number
written in another form, such as `0x03`, also stays, because the build would write it
differently.
"""
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line
from nxwright.language.resource_names import FONT, PICTURE, ResourceNames
from nxwright.source.page_source import reference_kind

# A number in the form the build writes.
_NUMBER = re.compile(r"0|[1-9][0-9]*")
# A whole statement assigning a plain number to an attribute: what comes before the
# number, the attribute's name, and the number.
_ASSIGNMENT = re.compile(r'([^\s="]*\.([A-Za-z0-9_]+)\s*=\s*)(0|[1-9][0-9]*)')
# The commands that take an asset, the place of that argument among their arguments,
# counted from 0, and its kind.
_COMMANDS = {"pic": (2, PICTURE), "picq": (4, PICTURE), "xpic": (6, PICTURE), "xstr": (4, FONT)}


def with_asset_names(text: str, names: ResourceNames) -> str:
    """Returns `text`, the code of a .nx file as extracted from a project, with each
    number that can only mean an asset replaced by that asset's name in `names`."""
    return "\n".join(_line_with_asset_names(line, names) for line in text.split("\n"))


def _line_with_asset_names(line: str, names: ResourceNames) -> str:
    try:
        indent, code, comment = split_line(line, 0)
    except NxwrightError:
        return line
    return indent + _code_with_asset_name(code, names) + comment


def _code_with_asset_name(code: str, names: ResourceNames) -> str:
    assignment = _ASSIGNMENT.fullmatch(code)
    if assignment:
        before, attribute, number = assignment.groups()
        return before + _reference(reference_kind(None, attribute), number, names)
    command, _, arguments = code.partition(" ")
    if command not in _COMMANDS:
        return code
    place, kind = _COMMANDS[command]
    # A text may contain commas, which this split counts as separators. That does no
    # harm after the argument. A quote before it means the count cannot be trusted, so
    # the line stays as it is.
    parts = arguments.split(",")
    if place >= len(parts) or '"' in ",".join(parts[:place + 1]):
        return code
    parts[place] = _reference(kind, parts[place], names)
    return command + " " + ",".join(parts)


def _reference(kind: str, number: str, names: ResourceNames) -> str:
    """Returns the name of `kind`'s asset with the ID `number`, written for code. It
    returns `number` itself if `kind` is None, if that is not a plain number, or if no
    such asset exists."""
    if kind is None or not _NUMBER.fullmatch(number):
        return number
    name = names.name_of(kind, int(number))
    return number if name is None else "@%s(%s)" % (kind, name)
