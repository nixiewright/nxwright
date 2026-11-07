"""The variable's decoder (tft/decompiling/component_types/variable.py):
each variable of each probe of T, K, and F that keeps its whole user code,
decoded from that user code (decoded_file.decoded_user_code), against the
probe's own variable (unit_inputs.probe_facts).
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import probe_facts, user_code_of

# What a variable's decoder gives, of one of a number, its sta 0, and of one
# of a text, its sta 1: the attributes its file keeps.
_KEPT = {0: ("vscope", "sta", "val"), 1: ("vscope", "sta", "txt", "txt_maxl")}


def _variables() -> list:
    """Returns (the probe's name, the ObjectValues of each of its
    variables, that variable's page object) of every probe of T, K, and F
    whose fixtures keep its whole user code, and whose pages are made in
    memory."""
    found = []
    for probe in _probes_keeping_their_user_code():
        if not made_in_memory(probe):
            continue
        project = probe_facts(probe)
        decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                    "iso-8859-1")
        for page, made in zip(decoded.pages, project.pages):
            found += [(probe.name, decoded_values(each, page, decoded), page_object)
                      for each, page_object in zip(page.objects[1:], made.objects[1:])
                      if each.type_name == "variable"]
    return found


class VariableTest(unittest.TestCase):

    def test_each_variable(self):
        # Each variable's vscope, its sta, and its val, or its txt and
        # txt_maxl, as its page gives them. A global variable's memory lies
        # in the int area, and every other's in its page's memory.
        counts = {0: 0, 1: 0, "global": 0}
        for name, values, page_object in _variables():
            sta = number_from_bytes(page_object.attribute("sta") or b"\x00")
            with self.subTest(name, variable=page_object.attribute("objname")):
                expected = {each: number_from_bytes(page_object.attribute(each))
                            for each in _KEPT[sta] if each != "txt"}
                if sta == 1:
                    expected["txt"] = page_object.attribute("txt") or b""
                self.assertEqual(values.attributes, expected)
                self.assertEqual(values.added, {})
            counts[sta] += 1
            counts["global"] += expected["vscope"]
        # Variables of a number and of a text, and global ones among them.
        self.assertGreaterEqual(counts[0], 10)
        self.assertGreaterEqual(counts[1], 5)
        self.assertGreaterEqual(counts["global"], 1)

    def test_entries_its_variant_does_not_have(self):
        # A variable of a number has 11 entries, and one of a text 12. One
        # entry fewer is no variable the compile writes.
        probe = next(probe for probe in _probes_keeping_their_user_code()
                     if probe.name == "variable-two")
        decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
        page = decoded.pages[0]
        variable = next(each for each in page.objects if each.type_name == "variable")
        variable.entries = variable.entries[:-1]
        with self.assertRaises(DecodeError) as raised:
            decoded_values(variable, page, decoded)
        self.assertIn("entries", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
