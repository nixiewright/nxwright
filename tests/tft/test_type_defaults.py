"""Each component type at nxwright's defaults, in the match check and in its
module.

The check makes a need of an attribute only when it is away from nxwright's
default, so it never sees a default. So a component of each type, left at
nxwright's defaults but for the place a type with one must give, has to
pass the check on each series of its module's SERIES. Its module must also
describe it by those defaults: a variant whose sta and style, where it has
them, are the component's, not another variant's that it falls back to.

What fails today is listed below, each case by the line of the plan's
Checklist that takes it up. A case that no longer fails must be taken off
the list, so that the test checks it from then on.
"""
from functools import lru_cache
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME

from nxwright.tft import component_types
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tests.tft.unit_inputs import page, project_of

# The place given to a component whose type has one, as nxwright's build
# asks a page file for it.
_PLACE = {"x": 10, "y": 10, "w": 60, "h": 60}

# The types whose defaults nxwright's build refuses on a series, so that no
# such component reaches the check: a gauge's sta of 3, nothing behind it,
# which the Nextion Editor's compile refuses on T, K, and F ("Out of range").
_REFUSED_BY_THE_BUILD = {("gauge", "T"), ("gauge", "K"), ("gauge", "F")}

# What fails today, by the line of the plan's Checklist that takes it up:
# nothing.
_KNOWN_FAILURES = {}


def component_types_with_modules() -> list:
    """Returns (type's name, its module) for each component type nxwright has a
    module for, by name."""
    return [(name, component_types.type_module(name)) for name in sorted(TYPES_BY_NAME)
            if component_types.type_module(name) is not None]


def component_text(type_name: str, attributes: str = "") -> str:
    """Returns one component, c0, of the type `type_name`, in a page file's
    form: at nxwright's defaults but for its place, when its type has one,
    and `attributes`, lines of a page file such as "sta = 1\\n"."""
    names = nxwright_defaults()[TYPES_BY_NAME[type_name]].names()
    place = "".join("%s = %d\n" % item for item in _PLACE.items() if item[0] in names)
    return '\n[[component]]\nname = "c0"\ntype = "%s"\n%s%s' % (type_name, place, attributes)


@lru_cache(maxsize=None)
def one_component(type_name: str, series: str, attributes: str = ""):
    """Returns a Project of facts (unit_inputs.project_of) on `series`, of
    page0 of its base folder with one component (component_text). It holds
    no resource, as the match check reads each resource's block, which such
    a Project has not. Raises NxwrightError when nxwright's build refuses
    the page. Kept, as the tests of the rules' limits take the same
    components."""
    return project_of(page(component_text(type_name, attributes), series=series),
                      series=series, fonts=0)


def misread(page_object) -> list:
    """Returns the attributes, of sta and style, by which what describes
    `page_object` (component_types.object_module) differs from it, as a
    variant of another sta that its module fell back to."""
    described = component_types.object_module(page_object)
    return [name for name in ("sta", "style")
            if hasattr(described, name) and page_object.attribute(name) is not None
            and getattr(described, name) != number_from_bytes(page_object.attribute(name))]


class DefaultsTest(unittest.TestCase):

    def test_types_are_named_as_nxwright_names_them(self):
        # Each module's type is one of nxwright's, so none is left out above.
        named = {name.replace("-", "_") for name in TYPE_NAMES.values()}
        modules = {path.stem for path in Path(component_types.__file__).parent.glob("*.py")
                   if path.stem != "__init__"}
        self.assertEqual(modules - named, set())

    def test_each_type_at_its_defaults(self):
        rules = matched_rules()
        refused, failing = set(), {}
        for type_name, module in component_types_with_modules():
            for series in module.SERIES:
                try:
                    project = one_component(type_name, series)
                except NxwrightError:
                    refused.add((type_name, series))
                    continue
                left = unmatched(project_needs(project), rules)
                wrong = misread(project.pages[0].objects[1])
                if left or wrong:
                    failing[(type_name, series)] = ([need.described() for need in left], wrong)
        self.assertEqual(refused, _REFUSED_BY_THE_BUILD)
        self.assertEqual(failing.keys() - _KNOWN_FAILURES.keys(), set(), failing)
        self.assertEqual(_KNOWN_FAILURES.keys() - failing.keys(), set(),
                         "these pass now, so take them off _KNOWN_FAILURES")


if __name__ == "__main__":
    unittest.main()
