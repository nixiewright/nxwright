"""The dual-state button's decoder
(tft/decompiling/component_types/dual_state_button.py): each dual-state
button of each probe of T, K, and F that keeps its whole user code, decoded
from that user code (decoded_file.decoded_user_code), against the probe's
own dual-state button.

A dual-state button is written as the button of its sta and style is, but
for its val and its events. Its effect is kept only as whether it has one,
and its style behind a picture or a crop only when it is 1. The test
compares these as the file keeps them.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import button
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the decoder gives that its record keeps as the Nextion
# Editor's defaults when the dual-state button has none: its aph and its
# sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# The blocks the Nextion Editor adds at the start of its down event: a
# checkbox's switch of its val, four blocks, then its ref of itself. Its up
# event has none.
_ADDED = {"down": (5, 0)}


def _expected(page_object, name: str):
    """Returns the probe's value of the dual-state button `page_object`'s
    attribute `name`: a text's bytes for its txt, its val 0 by default, else
    a number."""
    value = page_object.attribute(name)
    if name == "txt":
        return value or b""
    if name == "val" and value is None:
        return 0
    return _RECORD_DEFAULTS[name] if value is None else number_from_bytes(value)


def _decoded_button(project):
    """Returns (the decoded dual-state button, its decoded page, the decoded
    file) of the first component of `project`'s first page, a dual-state
    button, from the user code the frame writes for `project`."""
    decoded = decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")
    return decoded.pages[0].objects[1], decoded.pages[0], decoded


class DualStateButtonTest(unittest.TestCase):

    def test_each_dual_state_button(self):
        buttons = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for page_decoded, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(page_decoded.objects[1:], made.objects[1:]):
                    if each.type_name != "dual-state-button":
                        continue
                    values = decoded_values(each, page_decoded, decoded)
                    attributes = dict(values.attributes)
                    sta, style = (number_from_bytes(page_object.attribute(name))
                                  for name in ("sta", "style"))
                    with self.subTest(probe.name, page=page_decoded.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether a button has an effect,
                        # and its style behind a colour, or a style of 1.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        if sta == button.COLOUR or style == button.BORDERED:
                            self.assertEqual(attributes.pop("style"), style)
                        self.assertNotIn("style", attributes)
                        self.assertEqual(attributes, {name: _expected(page_object, name)
                                                      for name in attributes})
                        self.assertEqual(values.added, _ADDED)
                    buttons += 1
        self.assertGreaterEqual(buttons, 10)

    def test_each_style_behind_each_background(self):
        # The compile writes these dual-state buttons, of a borderc of 1234 and a
        # borderw of 3, behind a crop, a colour, and a picture. A style of 1
        # keeps its border behind any of them, and any other style leaves no
        # trace but behind a colour.
        cases = [(0, 1, {"style": 1, "borderc": 1234, "borderw": 3, "picc": 0, "picc2": 0}),
                 (2, 1, {"style": 1, "borderc": 1234, "borderw": 3, "pic": 0, "pic2": 0}),
                 (2, 2, {"pic": 0, "pic2": 0}),
                 (1, 1, {"style": 1, "borderc": 1234, "borderw": 3, "bco": 50712, "bco2": 50712}),
                 (1, 3, {"style": 3, "bco": 50712, "bco2": 50712})]
        for sta, style, given in cases:
            behind = {0: {"picc": "p0", "picc2": "p0"}, 2: {"pic": "p0", "pic2": "p0"}}.get(sta)
            project = project_of(page(dual_state_button_component(sta=sta, style=style, borderc=1234,
                                                       borderw=3, bco=50712, bco2=50712,
                                                       pictures=behind),
                                      pictures=("p0",)), pictures=1)
            attributes = decoded_values(*_decoded_button(project)).attributes
            with self.subTest(sta=sta, style=style):
                self.assertEqual({name: attributes[name] for name in
                                  ("style", "borderc", "borderw", "picc", "picc2", "bco", "bco2",
                                   "pic", "pic2") if name in attributes}, given)
                self.assertEqual(attributes["sta"], sta)

    def test_entries_of_no_variant(self):
        dual, decoded_page, decoded = _decoded_button(
            project_of(page(dual_state_button_component())))
        dual.entries = dual.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, dual, decoded_page, decoded)

    def test_a_down_event_without_the_code_the_editor_adds(self):
        # Its down event starts with the switch of its val, then its ref of
        # itself.
        dual, decoded_page, decoded = _decoded_button(
            project_of(page(dual_state_button_component())))
        dual.events["down"].blocks = dual.events["down"].blocks[1:]
        self.assertRaises(DecodeError, decoded_values, dual, decoded_page, decoded)


if __name__ == "__main__":
    unittest.main()
