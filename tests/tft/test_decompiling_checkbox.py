"""The checkbox's decoder (tft/decompiling/component_types/checkbox.py):
each checkbox of each probe of T, K, and F that keeps its whole user code,
decoded from that user code (decoded_file.decoded_user_code), against the
probe's own checkbox, and the code its down event starts with. A
checkbox's effect is kept only as whether it has one, and its borderw and
borderc only at a style of 1.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.checkbox_probes import checkbox_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the checkbox's decoder gives that its record keeps as the
# Nextion Editor's defaults when the checkbox has none: its aph and
# its sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# The attributes the file always keeps of a checkbox, but its effect, and
# its border's, which it keeps at a style of 1 alone.
_ALWAYS = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "style", "bco", "pco", "val")
_BORDER = ("borderw", "borderc")


def _decoded(project):
    """Returns the decoded file of the user code the compile writes for
    `project`, on T."""
    return decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")


class CheckboxTest(unittest.TestCase):

    def test_each_checkbox(self):
        boxes = effects = bordered = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name != "checkbox":
                        continue
                    values = decoded_values(each, decoded_page, decoded)
                    attributes = dict(values.attributes)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether it has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        border = _BORDER if attributes["style"] == 1 else ()
                        self.assertEqual(sorted(attributes), sorted(_ALWAYS + border))
                        self.assertEqual(attributes, {
                            name: (_RECORD_DEFAULTS[name] if page_object.attribute(name) is None
                                   else number_from_bytes(page_object.attribute(name)))
                            for name in attributes})
                        # The 4 blocks that switch its val start its down event.
                        self.assertEqual(values.added, {"down": (4, 0)})
                    boxes += 1
                    effects += has_effect(page_object)
                    bordered += attributes["style"] == 1
        # 23 checkboxes, of which 1 has an effect and 1 a border of style 1.
        self.assertEqual((boxes, effects, bordered), (23, 1, 1))

    def test_a_border_with_an_effect(self):
        # The compile writes a checkbox of style 1, a borderw of 3 and a
        # borderc of 1234, unchecked, with an effect of 3 and without one.
        for effect in (0, 3):
            decoded = _decoded(project_of(page(checkbox_component(
                style=1, borderw=3, borderc=1234, val=0, effect=effect))))
            values = decoded_values(decoded.pages[0].objects[1], decoded.pages[0], decoded)
            with self.subTest(effect=effect):
                self.assertEqual({name: values.attributes[name] for name in
                                  ("style", "borderw", "borderc", "val")},
                                 {"style": 1, "borderw": 3, "borderc": 1234, "val": 0})
                self.assertEqual(values.attributes["effect"] != 0, effect != 0)
                self.assertEqual(values.added, {"down": (4, 0)})

    def test_a_down_event_without_its_switch(self):
        decoded = _decoded(project_of(page(checkbox_component())))
        box = decoded.pages[0].objects[1]
        down = box.events["down"]
        box.events["down"] = type(down)(down.place, down.blocks[1:])
        self.assertRaises(DecodeError, decoded_values, box, decoded.pages[0], decoded)

    def test_entries_of_no_variant(self):
        decoded = _decoded(project_of(page(checkbox_component())))
        box = decoded.pages[0].objects[1]
        box.entries = box.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, box, decoded.pages[0], decoded)


if __name__ == "__main__":
    unittest.main()
