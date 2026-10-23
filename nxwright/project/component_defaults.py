"""Component types: the attributes and events a newly added component of each
type has. Their readable names are project/object_types.py's.

The defaults come from a sample project with one newly added component of each
type (see `nxwright defaults`). They are written as TOML, one table per type name:

  [button]
  events = [
      "down",
      "up",
  ]

  [button.attributes]
  vscope = 0
  ...

The attributes are in stored order, with their default values as numbers or
strings. Attributes that are always derived ("type", "id", "objname", "endx",
"endy") are not listed.
"""
from dataclasses import dataclass
import functools
from pathlib import Path
import tomllib

import tomli_w

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes, number_to_bytes
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.page_block import Attribute, Event
from nxwright.project.page_text import expected_width, is_string_attribute, text_form_number

# What the Editor names a newly added component of each type, followed by a
# number, as in the page of tests/fixtures/every-component: t0 for a text,
# wav0 for an audio component. Pages are not named so.
NAME_PREFIXES = {
    0: "s", 1: "h", 2: "gm", 3: "v", 4: "wav", 5: "tc", 51: "tm", 52: "va", 53: "bt", 54: "n",
    55: "g", 56: "c", 57: "r", 58: "qr", 59: "x", 60: "exp", 61: "cb", 62: "slt", 63: "fs",
    65: "fbrowser", 66: "data", 67: "sw", 68: "select", 98: "b", 106: "j", 109: "m", 112: "p",
    113: "q", 116: "t", 122: "z",
}
# Attributes every object derives, never stored as defaults.
DERIVED_ATTRIBUTES = ("type", "id", "objname", "endx", "endy")
# Where a component sits: differs between components of one type, and is
# written in page files even when equal to the default.
PLACEMENT_ATTRIBUTES = ("x", "y", "w", "h")
_ENCODING = "latin-1"


@dataclass
class TypeDefaults:
    """What a newly added component of one type has."""
    attributes: list    # (name, stored bytes) in stored order, derived ones left out
    events: list        # event names, in stored order

    def names(self) -> list:
        """Returns the attribute names, in stored order."""
        return [name for name, _ in self.attributes]


def defaults_from_pages(pages: list) -> dict:
    """Returns {type number: TypeDefaults} from the pages of a sample project.

    Raises NxwrightError when two components of one type differ in anything
    but their name, ID, and placement.
    """
    found = {}
    for page in pages:
        for page_object in page.objects:
            object_type = page_object.attribute("type")[0]
            defaults = TypeDefaults(
                [(item.name, item.value) for item in page_object.items
                 if isinstance(item, Attribute) and item.name not in DERIVED_ATTRIBUTES],
                [item.name for item in page_object.items if isinstance(item, Event)])
            earlier = found.setdefault(object_type, defaults)
            if _without_placement(earlier) != _without_placement(defaults):
                raise NxwrightError("the sample has two components of type %s that differ"
                                    % TYPE_NAMES.get(object_type, object_type))
    return found


def _without_placement(defaults: TypeDefaults) -> tuple:
    """Returns (attributes, events) without x, y, w, and h, which may differ
    between two components of one type."""
    return ([(name, value) for name, value in defaults.attributes
             if name not in PLACEMENT_ATTRIBUTES],
            defaults.events)


def defaults_to_toml(defaults: dict, header: str) -> str:
    """Returns `defaults` ({type number: TypeDefaults}) as the TOML text this
    module describes, starting with `header` as comment lines.

    Raises NxwrightError for a type with no readable name in TYPE_NAMES.
    """
    tables = {}
    for object_type in sorted(defaults):
        name = TYPE_NAMES.get(object_type)
        if name is None:
            raise NxwrightError("type %d has no readable name" % object_type)
        type_defaults = defaults[object_type]
        tables[name] = {"events": type_defaults.events,
                        "attributes": {attribute: _value(attribute, value, object_type)
                                       for attribute, value in type_defaults.attributes}}
    comments = "\n".join("# " + line if line else "#" for line in header.split("\n"))
    return comments + "\n\n" + tomli_w.dumps(tables)


# nxwright's own component defaults, copied into the source folder by every extract.
DEFAULTS_FILE = Path(__file__).resolve().parent / "component_defaults.toml"


@functools.cache
def nxwright_defaults() -> dict:
    """Returns nxwright's own component defaults (DEFAULTS_FILE), read once,
    as defaults_from_toml returns them."""
    return defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), str(DEFAULTS_FILE))


def defaults_from_toml(text: str, source: str) -> dict:
    """Returns {type number: TypeDefaults} read from TOML that defaults_to_toml
    wrote. `source` names the file in errors.

    Raises NxwrightError when the text does not hold valid defaults.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s: %s" % (source, error)) from None
    defaults = {}
    for name, table in data.items():
        object_type = TYPES_BY_NAME.get(name)
        if object_type is None or not isinstance(table, dict) or set(table) != {"events", "attributes"}:
            raise NxwrightError("%s: [%s] is not a component type's defaults" % (source, name))
        if not isinstance(table["attributes"], dict):
            raise NxwrightError("%s: [%s] attributes must be a table" % (source, name))
        attributes = [(attribute, _bytes(attribute, value, object_type, source, name))
                      for attribute, value in table["attributes"].items()]
        events = table["events"]
        if not isinstance(events, list) or not all(isinstance(event, str) for event in events):
            raise NxwrightError("%s: [%s] events must be a list of names" % (source, name))
        defaults[object_type] = TypeDefaults(attributes, events)
    return defaults


def _value(attribute: str, value: bytes, object_type: int):
    """Returns an attribute's stored bytes as its TOML value: a string, or a
    little-endian number of the attribute's expected width."""
    if is_string_attribute(object_type, attribute):
        return value.decode(_ENCODING)
    if len(value) != expected_width(object_type, attribute):
        raise NxwrightError("type %s: attribute %s has an unexpected size"
                            % (TYPE_NAMES.get(object_type, object_type), attribute))
    return number_from_bytes(value)


def _text_bytes(text: str, where: str) -> bytes:
    """Returns the bytes a text of the file holds, each written as the
    character of its value, U+0000 to U+00FF (_ENCODING). Raises
    NxwrightError, naming `where`, for another character, which is no byte."""
    try:
        return text.encode(_ENCODING)
    except UnicodeEncodeError as error:
        raise NxwrightError("%s holds U+%04X, where the file writes each byte of a text as a "
                            "character from U+0000 to U+00FF"
                            % (where, ord(text[error.start]))) from None


def _bytes(attribute: str, value, object_type: int, source: str, type_name: str) -> bytes:
    """Returns an attribute's TOML value as its stored bytes: the reverse of _value."""
    where = "%s: [%s.attributes] %s" % (source, type_name, attribute)
    if is_string_attribute(object_type, attribute):
        if not isinstance(value, str):
            raise NxwrightError("%s must be a string" % where)
        return _text_bytes(value, where)
    if isinstance(value, str):
        number = text_form_number(object_type, attribute, value,
                                  lambda text: _text_bytes(text, where))
        value = value if number is None else number
    width = expected_width(object_type, attribute)
    if width is None or not isinstance(value, int) or isinstance(value, bool):
        raise NxwrightError("%s must be a number of a known width" % where)
    try:
        return number_to_bytes(value, width)
    except OverflowError:
        raise NxwrightError("%s does not fit in %d bytes" % (where, width)) from None
