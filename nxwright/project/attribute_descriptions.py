"""What each attribute of each component type is, in nxwright's own words:
its description, its choices, whether code can change it, how the
Attributes section treats it, and whether it is a method code calls. They
are written by hand in `attribute_descriptions.toml`, beside this module,
whose opening comment gives its form. The language server shows them in
hovers, in completion, and in the Attributes section.

An attribute's choices are the few numbers its value may take, each with a
label. For example, a text's `sta` is 0 for a crop of a picture, and 1 for a
colour. The build refuses any other value in a page file or in defaults.toml
(allowed_number_bytes).

Code can change an attribute when the Nextion Editor's Attribute panel shows
its name in green. An attribute the panel never showed is treated as one code
can change, so that the build does not refuse code that may be valid.

What the screen keeps of a number code stores is given by `code_range`, the
lowest and highest it takes, refusing others, or by `code_wraps`, the bytes
it keeps of any number, as the Editor's simulator kept them
(tests/test_stored_numbers.py). An attribute with neither keeps any number.
A common entry's range holds for every type having the attribute, a
gauge's `bco` among them, which the probe did not try.
"""
from dataclasses import dataclass
import functools
from pathlib import Path
import tomllib

from nxwright import NxwrightError
from nxwright.project.attribute_ranges import attribute_range
from nxwright.project.attribute_values import number_to_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME

DESCRIPTIONS_FILE = Path(__file__).resolve().parent / "attribute_descriptions.toml"
# The table holding the attributes that mean the same on every type having them.
COMMON = "common"
# The keys saying what the screen keeps of a number code stores. A type's
# entry of these alone adds them to the common entry.
_CODE_KEYS = ("code_range", "code_wraps")
# The bytes each `code_wraps` keeps, as (bits, whether signed).
WRAPS = {"u8": (8, False), "u16": (16, False), "s16": (16, True)}
# How the Attributes section treats an attribute: listed with a field to
# edit, listed with its value only, left out unless the page file gives it,
# or left out whatever the page file gives. The last is for an attribute the
# page preview shows by other means, as a lock, and one with no known
# effect.
SHOWN, VALUE_ONLY, HIDDEN, NEVER_SHOWN = "shown", "value-only", "hidden", "never-shown"
TREATMENTS = (SHOWN, VALUE_ONLY, HIDDEN, NEVER_SHOWN)
# Attributes of every component that code cannot change, which page files
# keep as a table's place, its type, and its name, so that no description
# lists them. The Editor refused to compile an assignment to each.
_FIXED_ON_EVERY_TYPE = ("id", "type", "objname")
# A placed component's right and bottom edges, which page files leave out as
# x + w and y + h tell them. Code reads them, and the Editor refused to
# compile an assignment to either (worked out from the Editor 1.68.2).
_FIXED_WHERE_PLACED = ("endx", "endy")


@dataclass(frozen=True)
class AttributeDescription:
    """One attribute of one type: its description, its choices as {number:
    label}, empty when it has none, whether code can change it, how the
    Attributes section treats it, one of TREATMENTS, whether it is a
    method, which code calls, as d0.insert("a^b"), rather than sets; and
    what the screen keeps of a number code stores, as the module's
    docstring says: `code_range`, (lowest, highest), or `code_wraps`, a key
    of WRAPS, or neither, None."""
    description: str
    choices: dict
    code_can_change: bool
    properties: str
    method: bool = False
    code_range: tuple = None
    code_wraps: str = None

    def kept(self, value: int):
        """What the screen keeps of `value`, a number code stores: `value`
        cut to its bytes, where it wraps; None, where its range refuses it;
        else `value`."""
        if self.code_wraps is not None:
            bits, signed = WRAPS[self.code_wraps]
            value %= 2 ** bits
            return value - 2 ** bits if signed and value >= 2 ** (bits - 1) else value
        if self.code_range is not None and not self.code_range[0] <= value <= self.code_range[1]:
            return None
        return value


def describe(type_name: str, attribute: str):
    """Returns the AttributeDescription of `attribute` for components of the
    type `type_name`, named as the component defaults name types ("text"),
    or None when the file describes neither. The type's own entry comes
    first, then the common one; a type's entry of _CODE_KEYS alone takes
    the common one's words. The caller makes sure the type has the
    attribute."""
    tables = _tables()
    own = tables.get(type_name, {}).get(attribute)
    common = tables.get(COMMON, {}).get(attribute)
    if own is not None and "description" not in own and common is not None:
        entry = {key: value for key, value in common.items() if key not in _CODE_KEYS}
        entry.update(own)
    else:
        entry = own or common
    if entry is None:
        return None
    code_range = entry.get("code_range")
    return AttributeDescription(
        entry["description"], {int(number): label for number, label
                               in entry.get("choices", {}).items()},
        entry["code_can_change"], entry.get("properties", SHOWN), entry.get("method", False),
        tuple(code_range) if code_range is not None else None, entry.get("code_wraps"))


def allowed_number_bytes(object_type: int, attribute: str, value: int, width: int,
                         where: str) -> bytes:
    """Returns `value` as the `width` bytes stored for the number attribute
    `attribute` of a component of type `object_type`. Raises NxwrightError if
    the value is outside the attribute's range (attribute_ranges.attribute_range)
    or its choices, or does not fit in `width` bytes. The error starts with
    `where`, which must end with the attribute's name, such as
    "defaults.toml: [text.attributes] vscope"."""
    allowed = attribute_range(object_type, attribute)
    if allowed is not None and value not in allowed:
        raise NxwrightError("%s must be from %d to %d" % (where, allowed.start, allowed.stop - 1))
    try:
        stored = number_to_bytes(value, width)
    except OverflowError:
        raise NxwrightError("%s does not fit in %d bytes" % (where, width)) from None
    # The Nextion Editor's compile takes some values outside an attribute's
    # choices. The build still rejects them, because such a value has no
    # meaning, and the Nextion Editor's Attribute panel cannot set it.
    described = describe(TYPE_NAMES.get(object_type, ""), attribute)
    if described is not None and described.choices and value not in described.choices:
        chosen = ["%d (%s)" % item for item in sorted(described.choices.items())]
        listed = (" or ".join(chosen) if len(chosen) < 3
                  else "%s, or %s" % (", ".join(chosen[:-1]), chosen[-1]))
        raise NxwrightError("%s must be %s" % (where, listed))
    return stored


def described_by_type(type_name: str, attribute: str) -> bool:
    """Whether the type `type_name` ("text") describes `attribute` in words
    of its own, rather than taking the common description."""
    return "description" in _tables().get(type_name, {}).get(attribute, {})


def type_has(type_name: str, name: str) -> bool:
    """Whether code may give `name` after a component of the type `type_name`
    ("text"), as the Editor 1.68.2 compiled it: an attribute of the type, as
    nxwright's component defaults list them, methods included; `id`, `type`,
    or `objname`; or `endx` or `endy`, on a type with a place on the screen.
    Every other name the Editor knows it refused, on every type and every
    series ("Invalid Variables"), and names differ by their letters' case.
    `objname` it refused too on the Basic, Enhanced, and Discovery series,
    which this does not tell."""
    attributes = _attribute_names(type_name)
    if attributes is None:
        return False
    return (name in attributes or name in _FIXED_ON_EVERY_TYPE
            or (name in _FIXED_WHERE_PLACED and "x" in attributes))


@functools.cache
def _attribute_names(type_name: str):
    """The attributes nxwright's component defaults list for the type, a
    frozenset, or None for a type they do not hold."""
    defaults = nxwright_defaults().get(TYPES_BY_NAME.get(type_name))
    return None if defaults is None else frozenset(defaults.names())


def code_cannot_change(type_name: str, attribute: str) -> bool:
    """Whether code cannot change `attribute` of a component of the type
    `type_name` ("text"), so that the Editor refuses to compile an
    assignment to it, saying "Assignment operation failed": `id`, `type`,
    `objname`, `endx`, or `endy`, or an attribute of the type, as
    nxwright's component defaults list them, that its description marks. A
    name the type does not have (type_has) is none."""
    if not type_has(type_name, attribute):
        return False
    if attribute in _FIXED_ON_EVERY_TYPE + _FIXED_WHERE_PLACED:
        return True
    described = describe(type_name, attribute)
    return described is not None and not described.code_can_change


@functools.cache
def _tables() -> dict:
    """The file's tables, read once."""
    return tomllib.loads(DESCRIPTIONS_FILE.read_text(encoding="utf-8"))
