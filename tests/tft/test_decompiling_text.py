"""The text's decoder (tft/decompiling/component_types/text.py): each text
of each probe of T, K, and F that keeps its whole user code, decoded from
that user code (decoded_file.decoded_user_code), against the probe's own
text.

Some of a text's attributes leave no trace in the file. A text's effect is
kept only as whether it has one, and its style behind a picture or a crop
only when it is 1. The test compares these as the file keeps them.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.text_probes import text_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the text's decoder gives that its record keeps as the
# Nextion Editor's defaults when the text has none: its aph and its
# sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# The attributes the file always keeps of a text, but its effect; what lies
# behind it, by its sta; and its border's, at a style of 1 alone. Its
# style is kept behind a colour, or at a style of 1 behind anything.
_ALWAYS = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "sta", "font", "isbr", "pco", "xcen",
           "ycen", "pw", "txt", "txt_maxl", "spax", "spay")
_BEHIND = {0: "picc", 1: "bco", 2: "pic"}
_BORDER = ("borderc", "borderw")


def _probes() -> list:
    """Returns every probe of T, K, and F whose fixtures keep its whole user
    code, in parts, and whose pages are made in memory, once each."""
    return [probe for probe in _probes_keeping_their_user_code() if made_in_memory(probe)]


def _expected(page_object, name: str):
    """Returns the probe's value of the text `page_object`'s attribute
    `name`: its bytes for its txt, and a number for any other."""
    value = page_object.attribute(name)
    if value is None:
        return _RECORD_DEFAULTS[name]
    return value if name == "txt" else number_from_bytes(value)


class TextTest(unittest.TestCase):

    def test_each_text(self):
        texts = effects = global_texts = 0
        for probe in _probes():
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(page.objects[1:], made.objects[1:]):
                    if each.type_name != "text":
                        continue
                    attributes = dict(decoded_values(each, page, decoded).attributes)
                    with self.subTest(probe.name, page=page.page_id, object_id=each.object_id):
                        # The file keeps only whether a text has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        # The probe's own style says which the file keeps. The
                        # probes keep stand-in code, so no key is read back.
                        style = number_from_bytes(page_object.attribute("style"))
                        given = set(_ALWAYS) | {_BEHIND[attributes["sta"]]}
                        if attributes["sta"] == 1 or style == 1:
                            given.add("style")
                        if style == 1:
                            given |= set(_BORDER)
                        self.assertEqual(set(attributes), given)
                        self.assertEqual(attributes, {name: _expected(page_object, name)
                                                      for name in attributes})
                    texts += 1
                    effects += has_effect(page_object)
                    global_texts += each.is_global
        # 122 texts, of which 1 has an effect and 3 are global.
        self.assertEqual((texts, effects, global_texts), (122, 1, 3))

    def test_each_style_behind_each_background(self):
        # No probe that keeps its user code has a style behind a picture or
        # a crop, so the compile writes these texts, of a borderc of 1234 and
        # a borderw of 3, behind a crop, a colour, and a picture. A style of
        # 1 keeps its border's entries behind any of them, and any other
        # style leaves no trace but behind a colour.
        cases = [(0, 1, {"style": 1, "borderc": 1234, "borderw": 3, "picc": 0}),
                 (2, 1, {"style": 1, "borderc": 1234, "borderw": 3, "pic": 0}),
                 (2, 2, {"pic": 0}),
                 (1, 1, {"style": 1, "borderc": 1234, "borderw": 3, "bco": 65535}),
                 (1, 3, {"style": 3, "bco": 65535})]
        for sta, style, given in cases:
            behind = {0: {"picc": "p0"}, 2: {"pic": "p0"}}.get(sta)
            project = project_of(page(text_component(sta=sta, style=style, borderc=1234,
                                                     borderw=3, pictures=behind),
                                      pictures=("p0",)), pictures=1)
            decoded = decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0,
                                        "iso-8859-1")
            attributes = decoded_values(decoded.pages[0].objects[1], decoded.pages[0],
                                        decoded).attributes
            with self.subTest(sta=sta, style=style):
                self.assertEqual({name: attributes[name] for name in
                                  ("style", "borderc", "borderw", "picc", "bco", "pic")
                                  if name in attributes}, given)
                self.assertEqual(attributes["sta"], sta)

    def test_entries_of_no_variant(self):
        probe = next(probe for probe in _probes() if probe.name == "text-two")
        decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
        page = decoded.pages[0]
        text = page.objects[1]
        text.entries = text.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, text, page, decoded)


if __name__ == "__main__":
    unittest.main()
