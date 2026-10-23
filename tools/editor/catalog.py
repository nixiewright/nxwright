"""The catalog of the Editor's attributes: what `editor.py catalog` reads of a
project's components, merged over the variants of the project, and compared
with nxwright's component defaults (README.md). It drives no Editor and
imports no pywinauto, so that its tests run with nxwright's own Python.

A catalog, as `editor.py catalog` writes it, is JSON:

    {"variant": "defaults",
     "objects": [{"page": "page0", "component": "t0", "type": 116,
                  "attributes": [{"name": "sta", "value": "solid color",
                                  "hint": "...", "code_can_change": true}]}]}

A row read with `--known` and found there has no hint of its own: its hint
is None. The rows `type`, `id`, and `objname` are not attributes of the file.

A merged catalog is {type name: {attribute: Seen}}, the type named as
nxwright's component defaults name it ("scrolling-text").
"""
from dataclasses import dataclass, field
import re

from nxwright.project.component_defaults import PLACEMENT_ATTRIBUTES
from nxwright.project.object_types import TYPE_NAMES

# The Attribute panel's rows that are not attributes of the project file.
STRUCTURAL_ROWS = ("type", "id", "objname")
# A hint's list of choices: numbered labels after its last colon, such as
# "0-crop image;1-solid color". At least two make a list.
_CHOICES = re.compile(r":\s*(\d+-[^;]*(?:;\s*\d+-[^;]*)+)\s*$")
_CHOICE = re.compile(r"\s*(\d+)-(.*)")
# An attribute line of a dump's object, as `  sta = 1`, or `  sta:u8 = 1`.
_DUMP_ATTRIBUTE = re.compile(r"(\s+)([A-Za-z0-9_]+)((?::u\d+)? = )(.*)")
# A choice stored as a one-byte string, as a scrolling text's `dir = "\x01"`.
_ONE_BYTE = re.compile(r'"\\x[0-9a-fA-F]{2}"')


@dataclass
class Seen:
    """What the catalogs showed of one attribute of one type: its hint, the
    variants under which its name showed green or black, and the values it
    showed."""
    hint: str = None
    green: list = field(default_factory=list)
    black: list = field(default_factory=list)
    values: list = field(default_factory=list)


@dataclass
class Comparison:
    """A merged catalog against nxwright's component defaults, each by type
    name: the attributes nxwright lists that the Editor never showed; those
    the Editor showed that nxwright does not list; those whose name showed
    in both colours; and the defaults that differ, as (attribute, the
    Editor's value, nxwright's value)."""
    never_shown: dict = field(default_factory=dict)
    not_in_defaults: dict = field(default_factory=dict)
    both_colours: dict = field(default_factory=dict)
    different_defaults: dict = field(default_factory=dict)


def choices_of(hint: str) -> dict:
    """Returns the numbered choices a hint lists, {number: label}, or {} when
    it lists none. "Background fill:0-crop image;1-solid color" gives
    {0: "crop image", 1: "solid color"}; "Opaqueness(0-127)" gives {}."""
    found = _CHOICES.search(hint or "")
    if not found:
        return {}
    choices = {}
    for part in found[1].split(";"):
        number, label = _CHOICE.fullmatch(part).groups()
        choices[int(number)] = label.strip()
    return choices


def type_name(entry: dict) -> str:
    """The name nxwright gives an object's type, from its catalog entry."""
    return TYPE_NAMES.get(entry["type"], "type %d" % entry["type"])


def known_rows(catalog: dict) -> set:
    """The (type name, attribute) pairs whose hint `catalog` holds: what
    `editor.py catalog --known` need not click again."""
    return {(type_name(entry), row["name"]) for entry in catalog["objects"]
            for row in entry["attributes"] if row["hint"] is not None}


def merge(catalogs: list) -> dict:
    """Merges catalogs, in order: for each type and attribute, the first hint
    found, the variants under which its name showed in each colour, and the
    values it showed."""
    merged = {}
    for catalog in catalogs:
        for entry in catalog["objects"]:
            for row in entry["attributes"]:
                if row["name"] in STRUCTURAL_ROWS:
                    continue
                seen = merged.setdefault(type_name(entry), {}).setdefault(row["name"], Seen())
                if seen.hint is None:
                    seen.hint = row["hint"]
                colour = seen.green if row["code_can_change"] else seen.black
                if catalog["variant"] not in colour:
                    colour.append(catalog["variant"])
                if row["value"] not in seen.values:
                    seen.values.append(row["value"])
    return merged


def compare(merged: dict, defaults_catalog: dict, defaults: dict) -> Comparison:
    """Compares `merged` with nxwright's component defaults, `defaults` as
    component_defaults.toml reads ({type name: {"attributes": {...}}}). The
    defaults are compared on `defaults_catalog`, the catalog of the project
    as built, whose components all have their type's defaults. A choice
    attribute's shown label is turned back into its number. Placement
    attributes differ from one component to the next, and are left out."""
    comparison = Comparison()
    for name, table in defaults.items():
        listed = table["attributes"]
        # A type no catalogued component has shows none of its attributes.
        shown = merged.get(name, {})
        never = [attribute for attribute in listed if attribute not in shown]
        extra = [attribute for attribute in shown if attribute not in listed]
        both = {attribute: seen for attribute, seen in shown.items()
                if seen.green and seen.black}
        for found, key in ((never, "never_shown"), (extra, "not_in_defaults"),
                           (both, "both_colours")):
            if found:
                getattr(comparison, key)[name] = found
    for entry in defaults_catalog["objects"]:
        name = type_name(entry)
        listed = defaults.get(name, {}).get("attributes", {})
        for row in entry["attributes"]:
            attribute = row["name"]
            if attribute not in listed or attribute in PLACEMENT_ATTRIBUTES:
                continue
            hint = merged.get(name, {}).get(attribute, Seen()).hint
            if not _same(row["value"], listed[attribute], choices_of(hint)):
                differing = comparison.different_defaults.setdefault(name, [])
                found = (attribute, row["value"], listed[attribute])
                if found not in differing:
                    differing.append(found)
    return comparison


def _same(shown: str, stored, choices: dict) -> bool:
    """Whether the Attribute panel's `shown` value is the project's `stored`
    one, as the panel shows values: a choice by its label; no picture
    (65535), and an empty text, as "(null)"; no keyboard (255) as "None"; a
    32-bit number with its top bit set as a negative one; and a choice the
    project stores as a one-byte string, by that byte's number."""
    shown = _as_stored(shown, choices)
    if isinstance(stored, str) and len(stored) == 1:
        stored = ord(stored)
    if shown == "(null)":
        return stored in (65535, "")
    if shown == "None":
        return stored == 255
    if re.fullmatch(r"-?\d+", shown) and isinstance(stored, int):
        return int(shown) % 2 ** 32 == stored % 2 ** 32
    return shown == str(stored)


def _as_stored(shown: str, choices: dict) -> str:
    """A value as the project stores it: a choice's number for its label."""
    for number, label in choices.items():
        if label == shown:
            return str(number)
    return shown


def most_choices(merged: dict) -> int:
    """The highest choice number any attribute's hint lists, or -1."""
    numbers = [number for seen_by_type in merged.values() for seen in seen_by_type.values()
               for number in choices_of(seen.hint)]
    return max(numbers, default=-1)


def variant_settings(merged: dict, defaults_catalog: dict, choice: int) -> dict:
    """The values of variant `choice`: {component: {attribute: choice}} for
    every attribute, of every component of `defaults_catalog`, whose hint
    lists that choice."""
    settings = {}
    for entry in defaults_catalog["objects"]:
        for row in entry["attributes"]:
            seen = merged.get(type_name(entry), {}).get(row["name"])
            if seen is not None and choice in choices_of(seen.hint):
                settings.setdefault(entry["component"], {})[row["name"]] = choice
    return settings


def with_values(dump_page: str, settings: dict) -> str:
    """A dump's page file, `dump_page`, with the attributes `settings` gives
    ({component: {attribute: number}}) set to those numbers. A choice stored
    as a one-byte string takes that byte. An attribute the object's block
    does not hold, or holds as another string, is left as it is."""
    lines = []
    component = None
    for line in dump_page.split("\n"):
        if line.startswith("object "):
            component = line.split()[2] if len(line.split()) > 2 else None
        else:
            found = _DUMP_ATTRIBUTE.fullmatch(line)
            wanted = settings.get(component, {})
            if found and found[2] in wanted:
                number = wanted[found[2]]
                if re.fullmatch(r"-?\d+", found[4]):
                    line = "%s%s%s%d" % (found[1], found[2], found[3], number)
                elif _ONE_BYTE.fullmatch(found[4]):
                    line = '%s%s%s"\\x%02x"' % (found[1], found[2], found[3], number)
        lines.append(line)
    return "\n".join(lines)


def copied_hints(merged: dict, describe) -> list:
    """The (type name, attribute) pairs whose description in nxwright's own
    words, `describe(type name, attribute)`, equals the Editor's hint, once
    letter case, spaces, and a full stop at the end are set aside, or equals
    the hint without its choices. A tripwire for a hint pasted by mistake: a
    hint lightly reworded passes it."""
    def plain(text: str) -> str:
        return " ".join((text or "").lower().split()).rstrip(".")
    found = []
    for name, attributes in merged.items():
        for attribute, seen in attributes.items():
            described = describe(name, attribute)
            if described is None or not seen.hint:
                continue
            hints = {plain(seen.hint), plain(_CHOICES.sub("", seen.hint))}
            if plain(described.description) in hints:
                found.append((name, attribute))
    return found


def report_markdown(merged: dict, comparison: Comparison) -> str:
    """The comparison and the merged catalog as Markdown, for people to read.
    It quotes the Editor's hints, so it stays out of the repository."""
    parts = ["# The Editor's attributes against nxwright's defaults", ""]
    sections = (("Never shown by the Editor", comparison.never_shown),
                ("Shown by the Editor, not in nxwright's defaults", comparison.not_in_defaults))
    for title, found in sections:
        parts += ["## %s" % title, ""]
        parts += ["- %s: %s" % (name, ", ".join("`%s`" % a for a in attributes))
                  for name, attributes in sorted(found.items())] or ["None."]
        parts.append("")
    parts += ["## Shown in both colours", ""]
    parts += ["- %s `%s`: green under %s; black under %s"
              % (name, attribute, ", ".join(seen.green), ", ".join(seen.black))
              for name, both in sorted(comparison.both_colours.items())
              for attribute, seen in both.items()] or ["None."]
    parts += ["", "## Defaults that differ", ""]
    parts += ["- %s `%s`: the Editor shows %r, nxwright stores %r" % (name, *found)
              for name, differing in sorted(comparison.different_defaults.items())
              for found in differing] or ["None."]
    parts += ["", "## Every attribute", ""]
    for name, attributes in sorted(merged.items()):
        parts += ["### %s" % name, "", "| Attribute | Code can change | Values seen | Hint |",
                  "| --- | --- | --- | --- |"]
        for attribute, seen in attributes.items():
            colour = ("both" if seen.green and seen.black else
                      "yes" if seen.green else "no")
            parts.append("| `%s` | %s | %s | %s |" % (
                attribute, colour, ", ".join(seen.values).replace("|", "\\|"),
                (seen.hint or "").replace("|", "\\|")))
        parts.append("")
    return "\n".join(parts)
