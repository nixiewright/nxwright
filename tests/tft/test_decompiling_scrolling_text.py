"""The scrolling text's decoder
(tft/decompiling/component_types/scrolling_text.py): each scrolling text
of each probe of T, K, and F that keeps its whole user code, decoded from
that user code (decoded_file.decoded_user_code), against the probe's own
scrolling text, and the code the Nextion Editor writes for it in its page's
load section. A scrolling text's effect is kept only as whether it has one,
and its style behind a picture or a crop only when it is 1.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import key_probes
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the decoder gives that its record keeps as the Nextion
# Editor's defaults when the scrolling text has none: its aph and its
# sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# Every attribute the file keeps of a scrolling text behind a colour, its
# sta 1, of no border of style 1, but its effect and its key.
_GIVEN = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "sta", "style", "font", "bco", "pco",
          "xcen", "ycen", "dir", "dis", "tim", "en", "txt_maxl", "txt", "isbr", "spax", "spay",
          "vvs0", "vvs1", "vvs2", "vvs3")
# The blocks the Nextion Editor writes for a scrolling text in its page's
# load section.
_LOAD_BLOCKS = 66


def _expected(page_object, name: str):
    """Returns the probe's value of the scrolling text `page_object`'s
    attribute `name`: its bytes for its txt, and a number for any other."""
    value = page_object.attribute(name)
    if value is None:
        return _RECORD_DEFAULTS[name]
    return value if name == "txt" else number_from_bytes(value)


def _decoded(project):
    """Returns the decoded file of the user code the compile writes for
    `project`, on T."""
    return decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")


class ScrollingTextTest(unittest.TestCase):

    def test_each_scrolling_text(self):
        texts = effects = colours = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name != "scrolling-text":
                        continue
                    values = decoded_values(each, decoded_page, decoded)
                    attributes = dict(values.attributes)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether it has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        if attributes["sta"] == 1 and attributes["style"] != 1:
                            self.assertEqual(sorted(attributes), sorted(_GIVEN))
                        self.assertEqual(attributes, {name: _expected(page_object, name)
                                                      for name in attributes})
                        self.assertEqual(values.added["load"], (_LOAD_BLOCKS, 0))
                    texts += 1
                    effects += has_effect(page_object)
                    colours += attributes["sta"] == 1
        # 35 scrolling texts, of which 1 has an effect and 33 a colour behind.
        self.assertEqual((texts, effects, colours), (35, 1, 33))

    def test_each_style_behind_each_background(self):
        # The compile writes these, of a borderc of 1234 and a borderw of 3,
        # behind a crop, a colour, and a picture, with an effect of 3 behind
        # a colour. A style of 1 keeps its border behind any of them, and
        # any other style leaves no trace but behind a colour.
        cases = [(0, 1, 0, {"style": 1, "borderc": 1234, "borderw": 3, "picc": 0}),
                 (2, 2, 0, {"pic": 0}),
                 (1, 1, 3, {"style": 1, "borderc": 1234, "borderw": 3, "bco": 65535}),
                 (1, 3, 0, {"style": 3, "bco": 65535})]
        for sta, style, effect, given in cases:
            behind = {0: {"picc": "p0"}, 2: {"pic": "p0"}}.get(sta)
            decoded = _decoded(project_of(page(scrolling_text_component(
                sta=sta, style=style, borderc=1234, borderw=3, effect=effect, pictures=behind),
                pictures=("p0",)), pictures=1))
            values = decoded_values(decoded.pages[0].objects[1], decoded.pages[0], decoded)
            with self.subTest(sta=sta, style=style, effect=effect):
                self.assertEqual({name: values.attributes[name] for name in
                                  ("style", "borderc", "borderw", "picc", "bco", "pic")
                                  if name in values.attributes}, given)
                self.assertEqual(values.attributes["effect"] != 0, effect != 0)
                self.assertEqual(values.added, {"load": (_LOAD_BLOCKS, 0)})

    def test_a_key(self):
        # The scrolling text with key 2 beside the keypad, as the compile
        # writes it: its code in the load section and its key's lines both.
        probe = next(probe for probe in key_probes.PROBES
                     if probe.name == "key-callers-on-two-pages")
        decoded = _decoded(probe_facts(probe))
        values = decoded_values(decoded.pages[0].objects[1], decoded.pages[0], decoded)
        self.assertEqual(values.attributes["key"], 2)
        self.assertEqual(values.added, {"load": (_LOAD_BLOCKS, 0), "up": (0, 3)})

    def test_a_load_section_without_its_code(self):
        decoded = _decoded(project_of(page(scrolling_text_component())))
        decoded_page = decoded.pages[0]
        section = decoded_page.load_section
        decoded_page.load_section = CodeRun(section.place, section.blocks[1:])
        self.assertRaises(DecodeError, decoded_values, decoded_page.objects[1], decoded_page,
                          decoded)

    def test_entries_of_no_variant(self):
        decoded = _decoded(project_of(page(scrolling_text_component())))
        text = decoded.pages[0].objects[1]
        text.entries = text.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, text, decoded.pages[0], decoded)


if __name__ == "__main__":
    unittest.main()
