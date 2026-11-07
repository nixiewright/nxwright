"""A project's components (tft/project.py): each object of its pages as nxwright
reads it, its records as stored, its attributes found by name, and what
describes it worked out once (component_types.object_module).

Each test makes its Project in memory (tests/tft/unit_inputs.py).
"""
from dataclasses import replace
import unittest
from unittest import mock

from nxwright.project.page_block import Attribute

from nxwright.tft import component_types
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.text_probes import text_component
from tests.tft.unit_inputs import page, project_of


class ComponentTest(unittest.TestCase):

    def setUp(self):
        self.project = project_of(page(text_component("t0"), number_component("n0", y=60)))
        self.text = self.project.pages[0].objects[1]

    def test_an_attribute_by_its_name(self):
        self.assertEqual(self.text.attribute("objname"), b"t0")
        self.assertIsNone(self.text.attribute("no-such-attribute"))

    def test_the_first_of_two_records_of_one_name(self):
        # As nxwright's PageObject.attribute gives it.
        component = replace(self.text, items=[Attribute("x", b"\x01"), Attribute("x", b"\x02")])
        self.assertEqual(component.attribute("x"), b"\x01")

    def test_each_component_is_described_once(self):
        # A compile needs what describes each component again and again.
        objects = self.project.pages[0].objects
        with mock.patch.object(component_types, "type_module",
                               wraps=component_types.type_module) as found:
            described = [[component_types.object_module(page_object) for _ in range(50)]
                         for page_object in objects]
        self.assertEqual(found.call_count, len(objects))
        for each in described:
            self.assertTrue(all(one is each[0] for one in each))

    def test_another_component_made_from_one(self):
        # A component is never changed once made: another is made with
        # replace, and finds its own attributes.
        component_types.object_module(self.text)
        other = replace(self.text, items=[Attribute("objname", b"t9")] + self.text.items[1:])
        self.assertEqual(other.attribute("objname"), b"t9")
        self.assertEqual(self.text.attribute("objname"), b"t0")
        # And is described on its own.
        with mock.patch.object(component_types, "type_module",
                               wraps=component_types.type_module) as found:
            component_types.object_module(other)
        self.assertEqual(found.call_count, 1)

    def test_a_project_made_from_another_keeps_its_components(self):
        # As the frame's copy of the project, with each page at the
        # screen's place, keeps them, so they are not described again.
        other = replace(self.project, program=self.project.program + b"\n")
        self.assertTrue(all(mine is theirs for mine, theirs in
                            zip(self.project.pages[0].objects, other.pages[0].objects)))


if __name__ == "__main__":
    unittest.main()
