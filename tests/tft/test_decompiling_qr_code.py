"""The QR code's decoder (tft/decompiling/component_types/qr_code.py):
each QR code of each probe of T, K, and F that keeps its whole user code,
decoded from that user code (decoded_file.decoded_user_code), against the
probe's own QR code. A QR code's effect is kept only as whether it has
one, and its pic only with a logo, at a sta of 1.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import has_effect
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing.qr_code_probes import qr_code_component
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import page, probe_facts, project_of, user_code_of

# The attributes the QR code's decoder gives that its record keeps as the
# Nextion Editor's defaults when the QR code has none: its aph and
# its sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}
# Every attribute the file keeps of a QR code without a logo, but its
# effect. One with a logo keeps its pic too.
_GIVEN = ("vscope", "x", "y", "w", "h", "aph", "sendkey", "sta", "dis", "bco", "pco",
          "txt_maxl", "txt")


def _expected(page_object, name: str):
    """Returns the probe's value of the QR code `page_object`'s attribute
    `name`: its bytes for its txt, and a number for any other."""
    value = page_object.attribute(name)
    if value is None:
        return _RECORD_DEFAULTS[name]
    return value if name == "txt" else number_from_bytes(value)


def _decoded(project):
    """Returns the decoded file of the user code the compile writes for
    `project`, on T."""
    return decoded_user_code(frame.user_code(project), "T", "NX4832T035", 0, "iso-8859-1")


class QrCodeTest(unittest.TestCase):

    def test_each_qr_code(self):
        codes = effects = logos = global_codes = 0
        for probe in _probes_keeping_their_user_code():
            if not made_in_memory(probe):
                continue
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base, "NX4832T035", 0,
                                        "iso-8859-1")
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, page_object in zip(decoded_page.objects[1:], made.objects[1:]):
                    if each.type_name != "qr-code":
                        continue
                    values = decoded_values(each, decoded_page, decoded)
                    attributes = dict(values.attributes)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        # The file keeps only whether it has an effect.
                        self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                        logo = ("pic",) if attributes["sta"] == 1 else ()
                        self.assertEqual(sorted(attributes), sorted(_GIVEN + logo))
                        self.assertEqual(attributes, {name: _expected(page_object, name)
                                                      for name in attributes})
                        self.assertEqual(values.added, {})
                    codes += 1
                    effects += has_effect(page_object)
                    logos += attributes["sta"] == 1
                    global_codes += each.is_global
        # 25 QR codes, of which 1 has an effect, 2 a logo, and 2 are global.
        self.assertEqual((codes, effects, logos, global_codes), (25, 1, 2, 2))

    def test_a_logo_with_an_effect(self):
        # The compile writes a QR code with a logo, its pic 1, holding "abc",
        # with an effect of 3 and without one.
        for effect in (0, 3):
            decoded = _decoded(project_of(page(qr_code_component(
                txt="abc", sta=1, effect=effect, pic="p1"),
                pictures=("p0", "p1")), pictures=2))
            values = decoded_values(decoded.pages[0].objects[1], decoded.pages[0], decoded)
            with self.subTest(effect=effect):
                self.assertEqual({name: values.attributes[name] for name in ("sta", "pic", "txt")},
                                 {"sta": 1, "pic": 1, "txt": b"abc"})
                self.assertEqual(values.attributes["effect"] != 0, effect != 0)

    def test_entries_of_no_variant(self):
        decoded = _decoded(project_of(page(qr_code_component())))
        code = decoded.pages[0].objects[1]
        code.entries = code.entries[:-1]
        self.assertRaises(DecodeError, decoded_values, code, decoded.pages[0], decoded)


if __name__ == "__main__":
    unittest.main()
