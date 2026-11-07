"""A component's key, read back from the lines it adds at the end of its
Touch Release event (tft/decompiling/objects.py, key_values), through
the decoders of the types with a key (decompiling/component_types/).

The probes of keys keep their fixtures through the stand-in encoder, so
their pieces hold no real code. So each test has the compile write the
probe's pages in memory, nxwright's keyboard page among them, and decodes
that user code. The probes beside the Chinese keyboard are not made in
memory, so a key of 4 is not among them.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import KEYBOARD_PAGES
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values, key_values
from tools.tft.probing import key_probes
from tests.tft.t_components import made_in_memory
from tests.tft.unit_inputs import probe_facts

# The types with a key whose decoders the decompiler has.
_KEYED = ("text", "number", "xfloat")
# The lines a key adds: the keyboard page's loadpageid and loadcmpid set,
# then the page opened (component_types.key_lines).
_KEY_LINES = 3


def _decoded(probe) -> tuple:
    """Returns (the Project of facts of `probe`'s pages, and the decoded file
    of the user code the compile writes for them)."""
    project = probe_facts(probe)
    return project, decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                      "iso-8859-1")


class KeyTest(unittest.TestCase):

    def test_each_keyed_component(self):
        # Each component of a type with a decoder, in each probe of keys
        # made in memory, comes back with its key when the key opens a
        # keyboard page, and with the blocks its lines take. A key of no
        # keyboard, 0 or 5, adds no lines, and comes back as no key.
        keyed = unkeyed = 0
        for probe in key_probes.PROBES:
            if not made_in_memory(probe):
                continue
            project, decoded = _decoded(probe)
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name not in _KEYED:
                        continue
                    values = decoded_values(each, decoded_page, decoded)
                    key = number_from_bytes(page_object.attribute("key"))
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        if key in KEYBOARD_PAGES:
                            self.assertEqual(values.attributes["key"], key)
                            self.assertEqual(values.added, {"up": (0, _KEY_LINES)})
                        else:
                            self.assertNotIn("key", values.attributes)
                            self.assertEqual(values.added, {})
                    keyed += key in KEYBOARD_PAGES
                    unkeyed += key not in KEYBOARD_PAGES
        # The text on the keypad, the number on the keyboard, the xfloat on
        # the speed dial, and a number and a text on two pages; and 13
        # without a keyboard's key: a text and a number of keys 0 and 5,
        # and the keyboard pages' own texts.
        self.assertEqual((keyed, unkeyed), (5, 13))

    def test_the_component_s_own_code_stays(self):
        # The text on the keypad's own `sys0=7` comes before its key's lines,
        # which are all the key takes.
        probe = next(probe for probe in key_probes.PROBES
                     if probe.name == "key-text-on-the-keypad")
        _, decoded = _decoded(probe)
        text = decoded.pages[0].objects[1]
        self.assertEqual(len(text.events["up"].blocks), 1 + _KEY_LINES)
        self.assertEqual(decoded_values(text, decoded.pages[0], decoded).added,
                         {"up": (0, _KEY_LINES)})

    def test_a_local_component_s_own_lines(self):
        # The same lines in a local text's code are its own: nxwright's
        # build takes a key on a global component alone.
        probe = next(probe for probe in key_probes.PROBES
                     if probe.name == "key-text-on-the-keypad")
        _, decoded = _decoded(probe)
        text = decoded.pages[0].objects[1]
        text.record = text.record[:2] + bytes(1) + text.record[3:]
        self.assertEqual(key_values(text, decoded.pages[0], decoded), (None, 0))

    def test_lines_short_of_a_key(self):
        # Without the page opened at the end, the lines are no key's.
        probe = next(probe for probe in key_probes.PROBES
                     if probe.name == "key-text-on-the-keypad")
        _, decoded = _decoded(probe)
        text = decoded.pages[0].objects[1]
        up = text.events["up"]
        text.events["up"] = CodeRun(up.place, up.blocks[:-1])
        values = decoded_values(text, decoded.pages[0], decoded)
        self.assertNotIn("key", values.attributes)
        self.assertEqual(values.added, {})


if __name__ == "__main__":
    unittest.main()
