"""The match check's rules at the least and the most value that fits in
each attribute's bytes, so that no rule refuses a value without one of the
reasons the compile allows (tft/reasons.py), and against the ranges nxwright's
build checks, which must be the attributes' entries.

On each series a module takes, the check must take each attribute a page
file sets at the least and the most that fit in its bytes, as one byte
stores 0 to 255, unless the attribute's rule names a reason on that series.
A method, such as a data record's insert, which code calls and no page file
sets, and a text, which has no highest, are not checked.

Each component is a type at its defaults (test_type_defaults.py), then at
each other sta nxwright gives its type, as most variants of a type differ by
their sta, such as a text with a picture behind it, which has a pic's
entry. The page is the blank one of each series' base folder, at each sta
too. A variant whose sta nxwright's build refuses, or the check refuses,
is left out. The check's refusal of the sta is found anyway, as the sta is
checked at its limits like any attribute. Any other need of a variant that
the check refuses as it is built, such as its place, must be explained as a
refusal at a limit is.
"""
import struct
from typing import TYPE_CHECKING
import unittest

from nxwright import NxwrightError
from nxwright.project.attribute_descriptions import describe
from nxwright.project.attribute_ranges import range_on_every_series, ranges_on_series
from nxwright.project.attribute_values import number_from_bytes, number_to_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_block import Attribute
from nxwright.project.page_text import is_string_attribute

from nxwright.tft import component_types, frame
from nxwright.tft.component_types import (PAGE_BACKGROUND_ENTRY, SERIES_WRITTEN_AS_P, ObjectPlace,
                                   first_entries, object_module, p_table, page_entry, page_sta)
from nxwright.tft.matching import Need, matched_rules, project_needs, refusal_reasons, unmatched
from tests.tft.test_type_defaults import component_types_with_modules, one_component
from tests.tft.unit_inputs import page, project_of

if TYPE_CHECKING:
    from nxwright.tft.project import Project

# Attributes the project file stores but derives from others, which no page
# file sets (matching.py), and the object's name, a text.
_NOT_SET = ("type", "id", "endx", "endy", "objname")
# An entry: the object's base, the value or its place, its highest, its
# lowest, its owner, and its code (component_types.packed_entries).
_ENTRY = struct.Struct("<IiiiII")


def _component_entries(project: "Project", component) -> dict:
    """Returns {attribute: (lowest, highest)} of the entries of `component`,
    the first component of page0, in `project`."""
    described = object_module(component)
    if project.settings.model.series in SERIES_WRITTEN_AS_P:
        return {name: (lowest, highest) for name, _, highest, lowest, _
                in p_table(described, component, project).values()}
    # The places of its texts and buffer give values, not the limits read here.
    place = ObjectPlace(0, 1, first_entries(project)[(0, "c0")], 0, 0, text_place=0,
                        text_places={}, buffer_place=0, load_place=0)
    data = described.data(component, project, place)
    numbers = {}
    for item in component.items:
        if isinstance(item, Attribute):
            try:
                numbers[item.name] = described.attribute_place(item.name)
            except KeyError:
                continue
    return _unpacked(data, numbers)


def _page_entries(project: "Project", page_object) -> dict:
    """Returns {attribute: (lowest, highest)} of the entries of page0 of
    `project`, `page_object`: on T, K, and F, its vscope, its place and size, its
    sta, and its background's, its bco's or its pic's (frame.py)."""
    if project.settings.model.series in SERIES_WRITTEN_AS_P:
        return _unpacked(frame._p_page_entries(page_object, 0, 0, project),
                         component_types.p_page_named_entries(page_object))
    numbers = {"vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "sta": page_entry(page_object, 23)}
    background = frame._BACKGROUND_NAMES.get(page_sta(page_object))
    if background:
        numbers[background] = page_entry(page_object, PAGE_BACKGROUND_ENTRY)
    return _unpacked(frame._page_entries(page_object, 0, 0, project), numbers)


def _unpacked(data: bytes, numbers: dict) -> dict:
    """Returns {attribute: (lowest, highest)} of the entries in `data` that
    `numbers` gives by attribute."""
    found = {}
    for name, number in numbers.items():
        if (number + 1) * _ENTRY.size <= len(data):
            _, _, highest, lowest, _, _ = _ENTRY.unpack_from(data, number * _ENTRY.size)
            found[name] = (lowest, highest)
    return found


def _fitting(width: int) -> tuple:
    """Returns the least and the most number that fits in an attribute of
    `width` bytes, as nxwright reads it (attribute_values.number_from_bytes):
    4 bytes signed, fewer unsigned."""
    if width == 4:
        return -(1 << 31), (1 << 31) - 1
    return 0, (1 << (8 * width)) - 1


def _refusals(project: "Project", page_object, type_name: str, rules: list) -> list:
    """Returns (subject, series, end) for each attribute of `page_object`
    with an entry that the check refuses at the least or the most that fits
    in its bytes."""
    entries = (_page_entries(project, page_object) if type_name == "page"
               else _component_entries(project, page_object))
    attributes = {item.name: item.value for item in page_object.items
                  if isinstance(item, Attribute)}
    type_number = page_object.attribute("type")[0]
    settings = project.settings
    refused = []
    for name, default in nxwright_defaults()[type_number].attributes:
        description = describe(type_name, name)
        if (name in _NOT_SET or name not in entries or is_string_attribute(type_number, name)
                or (description is not None and description.method)):
            continue
        least, most = _fitting(len(default))
        for end, value in (("lowest", least), ("highest", most)):
            context = dict(attributes, **{name: number_to_bytes(value, len(default))})
            need = Need("attribute", "%s.%s" % (type_name, name), context[name],
                        context=context, series=settings.model.series,
                        encoding=settings.encoding, model=settings.model.name,
                        rotation=settings.rotation)
            if not any(rule.matches(need) for rule in rules):
                refused.append((need.subject, settings.model.series, end))
    return refused


class LimitsTest(unittest.TestCase):
    maxDiff = None

    def test_each_rule_takes_what_fits_in_its_bytes_or_gives_its_reason(self):
        rules = matched_rules()
        refused = set()
        for type_name, series, project, page_object, as_built in _each_variant(rules):
            refused.update(_refusals(project, page_object, type_name, rules))
            refused.update((need.subject, series, "as built") for need in as_built)
        unexplained = sorted(refusal for refusal in refused if not refusal_reasons(
            Need("attribute", refusal[0], series=refusal[1]), rules))
        self.assertEqual(unexplained, [])

    def test_nxwright_s_ranges_are_the_entries(self):
        # nxwright's build refuses a value past an attribute's range
        # (project/attribute_ranges.toml), which must be the
        # attribute's entry on each series nxwright writes its type for.
        differ = set()
        for type_name, series, project, page_object, _ in _each_variant(matched_rules()):
            entries = (_page_entries(project, page_object) if type_name == "page"
                       else _component_entries(project, page_object))
            on_series = ranges_on_series(type_name, series)
            for name, entry in entries.items():
                checked = range_on_every_series(type_name, name) or on_series.get(name)
                if checked is not None and checked != entry:
                    differ.add((type_name, name, series, checked, entry))
        self.assertEqual(sorted(differ), [])


def _each_variant(rules: list):
    """Yields (type name, series, project, its page or component, the needs
    the check refuses in it) for each variant of each type on each series
    that a module writes it for (_variants)."""
    for type_name, series_list in ([("page", frame.SERIES)]
                                   + [(name, module.SERIES)
                                      for name, module in component_types_with_modules()]):
        for series in series_list:
            for project, as_built in _variants(type_name, series, rules):
                objects = project.pages[0].objects
                yield (type_name, series, project,
                       objects[0] if type_name == "page" else objects[1], as_built)


def _variants(type_name: str, series: str, rules: list) -> list:
    """Returns (project, the needs the check refuses in it) for each project
    whose entries of `type_name` are checked on `series`: one of a component
    of the type at its defaults, or of the blank page, then one at each
    other sta the compile gives the type. One that nxwright's build refuses is
    left out, as a gauge at its default sta of 3 on T, K, and F, and so is
    one whose sta the check refuses."""
    defaults = dict(nxwright_defaults()[TYPES_BY_NAME[type_name]].attributes)
    other_stas = ([sta for sta in sorted(describe(type_name, "sta").choices)
                   if sta != number_from_bytes(defaults["sta"])] if "sta" in defaults else [])
    variants = []
    for sta in [None] + other_stas:
        try:
            if type_name == "page":
                project = _page_project(series, sta)
            else:
                project = one_component(type_name, series, "" if sta is None else
                                        "sta = %d\n" % sta)
        except NxwrightError:
            continue
        refused = unmatched(project_needs(project), rules)
        if not any(need.subject == "%s.sta" % type_name for need in refused):
            variants.append((project, refused))
    return variants


def _page_project(series: str, sta: int = None) -> "Project":
    """Returns a Project of facts (unit_inputs.project_of) on `series`, of
    page0 of its base folder, nxwright's new project, at `sta`, or at its
    default when it is None. It has no resource, as the match check reads
    each resource's block, which such a Project has not."""
    attributes = "" if sta is None else "sta = %d\n" % sta
    return project_of(page(series=series, attributes=attributes), series=series, fonts=0)


if __name__ == "__main__":
    unittest.main()
