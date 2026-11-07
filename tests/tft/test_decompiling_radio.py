"""The radio's decoder (tft/decompiling/component_types/radio.py): each
radio of each probe of T, K, and F that keeps its whole user code, decoded
from that user code (decoded_file.decoded_user_code), against the probe's
own radio, and the code its down event starts with. A radio's effect is
kept only as whether it has one.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.radio_probes import radio_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the radio's decoder gives that its record keeps as the
# Nextion Editor's defaults when the radio has none: its aph and
# its sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# Every attribute the file keeps of a radio, but its effect.
_GIVEN = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "bco", "pco", "val")


def _decoded(project):
    """Returns the decoded file of the user code the compile writes for
    `project`, on T."""
    return decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")


class RadioTest(unittest.TestCase):

    def test_each_radio(self):
        radios = effects = chosen = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name != "radio":
                        continue
                    values = decoded_values(each, decoded_page, decoded)
                    attributes = dict(values.attributes)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether it has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        self.assertEqual(sorted(attributes), sorted(_GIVEN))
                        self.assertEqual(attributes, {
                            name: (_RECORD_DEFAULTS[name] if page_object.attribute(name) is None
                                   else number_from_bytes(page_object.attribute(name)))
                            for name in attributes})
                        # The 4 blocks that switch its val start its down event.
                        self.assertEqual(values.added, {"down": (4, 0)})
                    radios += 1
                    effects += has_effect(page_object)
                    chosen += attributes["val"] == 1
        # 13 radios, of which 1 has an effect and 12 are chosen.
        self.assertEqual((radios, effects, chosen), (13, 1, 12))

    def test_with_an_effect(self):
        # The compile writes a radio unchosen, of a bco of 1234 and a pco of
        # 4321, with an effect of 3 and without one.
        for effect in (0, 3):
            decoded = _decoded(project_of(page(radio_component(
                bco=1234, pco=4321, val=0, effect=effect))))
            values = decoded_values(decoded.pages[0].objects[1], decoded.pages[0], decoded)
            with self.subTest(effect=effect):
                self.assertEqual({name: values.attributes[name] for name in ("bco", "pco", "val")},
                                 {"bco": 1234, "pco": 4321, "val": 0})
                self.assertEqual(values.attributes["effect"] != 0, effect != 0)
                self.assertEqual(values.added, {"down": (4, 0)})

    def test_a_down_event_without_its_switch(self):
        decoded = _decoded(project_of(page(radio_component())))
        radio = decoded.pages[0].objects[1]
        down = radio.events["down"]
        radio.events["down"] = type(down)(down.place, down.blocks[1:])
        self.assertRaises(DecodeError, decoded_values, radio, decoded.pages[0], decoded)

    def test_entries_of_no_variant(self):
        decoded = _decoded(project_of(page(radio_component())))
        radio = decoded.pages[0].objects[1]
        radio.entries = radio.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, radio, decoded.pages[0], decoded)


if __name__ == "__main__":
    unittest.main()
