"""A component that lacks an attribute of its type (tft/project.py): the
compile reads it with that attribute at the type's default.

A component has every attribute of its type unless its table in the page
file sets `defaults = false` and leaves one out. The tests make such a
component by removing attributes from one that a page file gives, then
read it from a Project of its page (tests/tft/unit_inputs.py).
"""
from dataclasses import replace
import unittest

from nxwright.project.page_block import Attribute
from nxwright.tft import component_types
from nxwright.tft.matching import project_needs
from tools.tft.probing.gmov_probes import gmov_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tests.tft.unit_inputs import page, project_of, without_attribute


def _project(component: str, *missing: str, series: str = "T"):
    """Returns a Project of a page that has one component, which lacks the
    attributes `missing`. `component` is the component, written the way it
    is in a page file."""
    made = page(component, series=series)
    lacking = made.objects[1]
    for name in missing:
        lacking = without_attribute(lacking, name)
    return project_of(replace(made, objects=[made.objects[0], lacking]), series=series, fonts=0)


def _names(page_object) -> list:
    return [item.name for item in page_object.items if isinstance(item, Attribute)]


class MissingAttributeTest(unittest.TestCase):

    def test_it_has_its_type_s_default(self):
        # By default, a gmov's from is 0, a text's sta is 1, and its txt_maxl is 10.
        gmov_object = _project(gmov_component(), "from", series="P").pages[0].objects[1]
        self.assertEqual(component_types.attribute_number(gmov_object, "from"), 0)
        text_object = _project(text_component(), "sta", "txt_maxl").pages[0].objects[1]
        self.assertEqual(component_types.attribute_number(text_object, "sta"), 1)
        self.assertEqual(component_types.attribute_number(text_object, "txt_maxl"), 10)

    def test_it_is_described_as_the_component_that_has_it(self):
        # What describes a text depends on its sta and its style, so the test
        # leaves both out.
        whole = _project(text_component()).pages[0].objects[1]
        lacking = _project(text_component(), "sta", "style").pages[0].objects[1]
        self.assertIs(component_types.object_module(lacking),
                      component_types.object_module(whole))

    def test_the_default_comes_after_the_attributes_it_has(self):
        whole = _project(text_component()).pages[0].objects[1]
        lacking = _project(text_component(), "sta", "font").pages[0].objects[1]
        names = [name for name in _names(whole) if name not in ("sta", "font")]
        self.assertEqual(_names(lacking), names + ["sta", "font"])

    def test_a_component_with_every_attribute_is_kept_as_it_is(self):
        made = page(text_component())
        self.assertEqual(_names(project_of(made, fonts=0).pages[0].objects[1]),
                         _names(made.objects[1]))

    def test_an_attribute_its_type_lacks_stays_missing(self):
        # A timer has no position on the page, so its type has no x.
        timer_object = _project(timer_component(), "tim").pages[0].objects[1]
        self.assertEqual(component_types.attribute_number(timer_object, "tim"), 400)
        self.assertIsNone(timer_object.attribute("x"))

    def test_the_page_too(self):
        made = page()
        lacking = replace(made, objects=[without_attribute(made.objects[0], "sta")])
        self.assertEqual(
            component_types.attribute_number(project_of(lacking, fonts=0).pages[0].objects[0],
                                             "sta"), 1)

    def test_its_needs_are_those_of_the_component_that_has_it(self):
        # The attribute is filled in at its type's default, and an attribute
        # at its default adds no need.
        def needs(project) -> list:
            return [(need.kind, need.subject, need.value, need.where)
                    for need in project_needs(project)]
        self.assertEqual(needs(_project(gmov_component(), "from", series="P")),
                         needs(_project(gmov_component(), series="P")))
