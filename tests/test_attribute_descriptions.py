"""nxwright's descriptions of the attributes (nxwright/project/attribute_descriptions.py):
one for every attribute of every type the component defaults list, each
well formed, and the file shipped with the package."""
from pathlib import Path
import re
import tomllib
import unittest

from nxwright.project.attribute_descriptions import (COMMON, DESCRIPTIONS_FILE, TREATMENTS,
                                                     code_cannot_change, describe, type_has)
from nxwright.project.component_defaults import DEFAULTS_FILE

DEFAULTS = tomllib.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
TABLES = tomllib.loads(DESCRIPTIONS_FILE.read_text(encoding="utf-8"))


class AttributeDescriptionsTest(unittest.TestCase):

    def test_every_attribute_of_every_type_is_described(self):
        for type_name, table in DEFAULTS.items():
            for attribute in table["attributes"]:
                with self.subTest(type=type_name, attribute=attribute):
                    found = describe(type_name, attribute)
                    self.assertIsNotNone(found)
                    self.assertTrue(found.description.strip())
                    self.assertIsInstance(found.code_can_change, bool)

    def test_each_entry_names_a_type_and_an_attribute_it_has(self):
        everywhere = {attribute for table in DEFAULTS.values() for attribute in table["attributes"]}
        for type_name, entries in TABLES.items():
            for attribute in entries:
                with self.subTest(type=type_name, attribute=attribute):
                    if type_name == COMMON:
                        self.assertIn(attribute, everywhere)
                    else:
                        self.assertIn(type_name, DEFAULTS)
                        self.assertIn(attribute, DEFAULTS[type_name]["attributes"])

    def test_each_entry_is_well_formed(self):
        for type_name, entries in TABLES.items():
            for attribute, entry in entries.items():
                with self.subTest(type=type_name, attribute=attribute):
                    self.assertLessEqual(set(entry), {"description", "choices", "code_can_change",
                                                      "properties", "method", "code_range",
                                                      "code_wraps"})
                    for number, label in entry.get("choices", {}).items():
                        self.assertTrue(number.isdigit(), number)
                        self.assertTrue(label.strip())
                    self.assertIn(entry.get("properties", "shown"), TREATMENTS)

    def test_descriptions_say_what_the_attribute_does(self):
        # A description says what the attribute does on the screen and in
        # the simulator. It names the Nextion Editor only for what concerns
        # the Editor alone: its panel, its design view, its Create Group
        # command, and where the Editor shows the attribute.
        concerning_the_editor_alone = re.compile(
            r"[Tt]he Nextion Editor's (panel|design view|Create Group)|In the Nextion Editor, it is")
        for type_name, entries in TABLES.items():
            for attribute, entry in entries.items():
                with self.subTest(type=type_name, attribute=attribute):
                    text = concerning_the_editor_alone.sub("", entry.get("description", ""))
                    self.assertNotIn("Nextion Editor", text)

    def test_a_types_own_entry_comes_before_the_common_one(self):
        # A page's x is always 0, which code cannot change; a component's can.
        self.assertFalse(describe("page", "x").code_can_change)
        self.assertTrue(describe("text", "x").code_can_change)
        self.assertEqual(describe("text", "sta").choices[1], "a colour")
        self.assertEqual(describe("text", "lockobj").properties, "never-shown")
        # A hotspot draws nothing, so its opacity, drag, and opening effect
        # have no known effect.
        for attribute in ("aph", "drag", "effect", "first", "time"):
            self.assertEqual(describe("hotspot", attribute).properties, "never-shown")
        self.assertEqual(describe("text", "txt").properties, "shown")
        self.assertIsNone(describe("text", "no-such-attribute"))

    def test_the_methods(self):
        # The names code calls, as d0.insert("a^b"); a page's up, the page a
        # swipe opens, is none.
        methods = {(type_name, attribute) for type_name, table in DEFAULTS.items()
                   for attribute in table["attributes"] if describe(type_name, attribute).method}
        self.assertEqual(methods, {("data-record", "insert"), ("data-record", "delete"),
                                   ("data-record", "up"), ("data-record", "clear"),
                                   ("file-browser", "up"), ("file-stream", "open"),
                                   ("file-stream", "read"), ("file-stream", "write"),
                                   ("file-stream", "close"), ("file-stream", "find")})

    def test_a_types_names(self):
        # As the Editor 3.1.73 compiled them: a type's attributes, id,
        # type, and objname, and endx and endy where it has a place; none
        # other, and names differ by their letters' case.
        for type_name, name in (("number", "val"), ("number", "id"), ("timer", "type"),
                                ("timer", "objname"), ("page", "endx"), ("text", "endy"),
                                ("data-record", "insert")):
            with self.subTest(type=type_name, name=name):
                self.assertTrue(type_has(type_name, name))
        for type_name, name in (("number", "vall"), ("number", "txt"), ("number", "Val"),
                                ("timer", "endx"), ("variable", "endy"), ("no-such-type", "id")):
            with self.subTest(type=type_name, name=name):
                self.assertFalse(type_has(type_name, name))
        # Code cannot assign endx or endy, as id, type, and objname.
        self.assertTrue(code_cannot_change("text", "endx"))
        self.assertTrue(code_cannot_change("page", "endy"))
        self.assertFalse(code_cannot_change("timer", "endx"))

    def test_the_package_ships_the_file(self):
        project = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml")
                                .read_text(encoding="utf-8"))
        shipped = project["tool"]["setuptools"]["package-data"]["nxwright.project"]
        self.assertIn(DESCRIPTIONS_FILE.name, shipped)


if __name__ == "__main__":
    unittest.main()
