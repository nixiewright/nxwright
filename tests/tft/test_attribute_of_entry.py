"""Which attribute an entry of code is (tft/decompiling/objects.py,
attribute_of_entry), against the entry the compile gives each attribute
code can name, of each object of a type the decompiler decodes (_DECODED)
in each probe of T, K, and F that keeps its whole user code: the statement
encoder's numbers (statements.page_code_entry, component_types.code_entry),
counted from the object's first entry (component_types.first_entries).
"""
import unittest

from nxwright.project.component_defaults import nxwright_defaults

from nxwright.tft import component_types
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import _FIXED, attribute_of_entry
from nxwright.tft.statements import page_code_entry
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import probe_facts, user_code_of

# The types whose decoders the decompiler has.
_DECODED = ("page", "text", "picture", "crop", "number", "hotspot", "xfloat", "timer",
            "progress-bar", "variable", "checkbox", "radio", "qr-code", "scrolling-text", "gauge",
            "slider", "touch-capture", "waveform", "button", "dual-state-button")


def _entries(page_object, series: str) -> dict:
    """Returns {the entry within its object: the attribute's name} of each
    attribute of `page_object` that code may name, as the statement encoder
    numbers it."""
    names = nxwright_defaults()[page_object.attribute("type")[0]].names() + list(_FIXED)
    module = None if component_types.type_name(page_object) == "page" else (
        component_types.object_module(page_object))
    entries = {}
    for name in names:
        try:
            entry = (page_code_entry(page_object, name, series) if module is None
                     else component_types.code_entry(module, page_object, name, series))
        except KeyError:
            continue
        entries.setdefault(entry, name)
    return entries


class AttributeOfEntryTest(unittest.TestCase):

    def test_each_decoded_object(self):
        compared = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            firsts = component_types.first_entries(project)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(page.objects, made.objects):
                    if component_types.type_name(page_object) not in _DECODED:
                        continue
                    first = firsts[page.page_id, component_types.object_name(page_object)]
                    for entry, name in _entries(page_object, probe.base).items():
                        found = attribute_of_entry(decoded, first + entry)
                        with self.subTest(probe.name, page=page.page_id,
                                          object_id=each.object_id, attribute=name):
                            self.assertEqual((found[0].page_id, found[1].object_id, found[2]),
                                             (page.page_id, each.object_id, name))
                        compared += 1
        # The attributes of the objects of _DECODED's types.
        self.assertEqual(compared, 15224)

    def test_an_entry_no_attribute_has(self):
        # The text's entry 2 is empty, and so is every entry past the last
        # object's.
        probe = next(probe for probe in _probes_keeping_their_user_code()
                     if probe.name == "text-two")
        decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
        text = decoded.pages[0].objects[1]
        last = decoded.pages[-1].objects[-1]
        for number in (text.first_entry + 2, last.first_entry + len(last.entries)):
            with self.subTest(number):
                self.assertRaises(KeyError, attribute_of_entry, decoded, number)


if __name__ == "__main__":
    unittest.main()
