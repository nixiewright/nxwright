"""What each attribute of each component type is, in nxwright's own words:
its description, its choices, whether code can change it, how the
Attributes section treats it, and whether it is a method code calls. They
are written by hand in `attribute_descriptions.toml`, beside this module,
whose opening comment gives its form. The language server shows them in
hovers, in completion, and in the Attributes section.

An attribute's choices are the few numbers its value may take, each with a
label, such as a text's `sta`: 0 a crop of a picture, 1 a colour. Code can
change an attribute when the Editor's Attribute panel shows its name green;
an attribute the panel never showed counts as one code can change, so that
the build refuses no code that may be valid.

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

from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.object_types import TYPES_BY_NAME

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
# compile an assignment to either (worked out from the Editor 3.1.73).
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


def described_by_type(type_name: str, attribute: str) -> bool:
    """Whether the type `type_name` ("text") describes `attribute` in words
    of its own, rather than taking the common description."""
    return "description" in _tables().get(type_name, {}).get(attribute, {})


def type_has(type_name: str, name: str) -> bool:
    """Whether code may give `name` after a component of the type `type_name`
    ("text"), as the Editor 3.1.73 compiled it: an attribute of the type, as
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
