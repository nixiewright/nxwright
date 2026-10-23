"""What the language server says of an attribute: its description, choices,
whether code can change it, and what numbers code may store in it, from
nxwright's descriptions (`nxwright/project/attribute_descriptions.py`), for
the types a source folder's components have.

An attribute is one of a component type's, as the folder's own
`defaults.toml` lists them, or nxwright's when the folder's cannot be read.
"""
from nxwright import NxwrightError
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source.folder_index import FolderIndex
from nxwright.project.attribute_descriptions import describe
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml


def type_defaults(index: FolderIndex) -> dict:
    """Returns the folder's component defaults, {type number: TypeDefaults}:
    its defaults.toml, or nxwright's own when the folder's cannot be read."""
    lines = index.lines("defaults.toml")
    if lines is not None:
        try:
            return defaults_from_toml("\n".join(lines), "defaults.toml")
        except NxwrightError:
            pass    # a half-edited file: nxwright's own still name the attributes
    return defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), str(DEFAULTS_FILE))


def has_attribute(defaults: dict, type_name: str, attribute: str) -> bool:
    """Whether components of the type `type_name` ("text") have `attribute`,
    as `defaults`, which type_defaults returns, list them."""
    found = defaults.get(TYPES_BY_NAME.get(type_name))
    return found is not None and attribute in found.names()


def attribute_markdown(type_name: str, attribute: str):
    """Returns the Markdown describing `attribute` of the type `type_name`:
    its description, its choices, and whether code can change it. None when
    nxwright has no description of it."""
    described = describe(type_name, attribute)
    if described is None:
        return None
    parts = ["`%s` of a %s: %s" % (attribute, type_name, described.description)]
    if described.choices:
        parts.append("\n".join("- %d: %s" % (number, label)
                               for number, label in sorted(described.choices.items())))
    parts.append(" ".join(filter(None, (_whether_code_can_change(described),
                                        _what_code_may_store(described)))))
    return "\n\n".join(filter(None, parts))


def _whether_code_can_change(described) -> str:
    """The sentence saying whether code can change an attribute; "" for a
    method, which code calls and never changes."""
    if described.method:
        return ""
    return ("Can be changed in code." if described.code_can_change
            else "Cannot be changed in code.")


# How a wrapping attribute's line says what the screen keeps, with a stored
# number and what it reads (attribute_descriptions.WRAPS).
_KEPT_BYTES = {"u8": ("its last byte", -1, 255), "u16": ("its last 2 bytes", -1, 65535),
               "s16": ("its last 2 bytes, signed", 40000, -25536)}


def _what_code_may_store(described) -> str:
    """The sentences saying what numbers code may store in an attribute, as
    the running screen keeps them (code_range, code_wraps); "" where code
    cannot change it, where it keeps any number, or where its choices say
    the same already."""
    if not described.code_can_change:
        return ""
    if described.code_wraps is not None:
        bytes_kept, stored, read = _KEPT_BYTES[described.code_wraps]
        return "Code may store any number. The screen keeps %s: %d reads %d." % (
            bytes_kept, stored, read)
    if described.code_range is None or (
            described.choices and described.code_range == (min(described.choices),
                                                            max(described.choices))):
        return ""
    low, high = described.code_range
    taken = "only %d" % low if low == high else "%d to %d" % (low, high)
    return "Code may store %s. The screen refuses other numbers." % taken


def attribute_tooltip(type_name: str, attribute: str) -> str:
    """Returns the plain text describing `attribute` of the type `type_name`,
    as attribute_markdown does, for a tooltip; "" when nxwright has no
    description of it."""
    described = describe(type_name, attribute)
    if described is None:
        return ""
    lines = [described.description]
    lines += ["%d: %s" % (number, label) for number, label in sorted(described.choices.items())]
    lines.append(_whether_code_can_change(described))
    lines.append(_what_code_may_store(described))
    return "\n".join(filter(None, lines))
