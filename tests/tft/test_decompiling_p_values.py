"""The reader of the values of an object on P that its named entries give
(tft/decompiling/objects.p_values), on every object of every probe of P
that keeps its whole user code, against the probe's own values; then
on each component of the types it reads whole, rebuilt from those values
alone and compiled again (unit_inputs.rebuilt_user_code).
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import P_VALUES_SKIPPED, candidate_object, p_values
from tests.tft.t_components import made_in_memory
from tests.tft.test_decoded_file import _probes_keeping_their_user_code
from tests.tft.unit_inputs import probe_facts, rebuilt_user_code, user_code_of

# A page's place and size, which the frame writes as the screen's, whatever
# the page's own.
_SCREENS = ("x", "y", "w", "h")
# The types of T on P whose every value the file keeps lies in a named
# entry, the record's head, or the head their memory starts with. A gauge
# and a waveform keep values that no entry gives, which their decoders read.
_READ_WHOLE = ("text", "number", "xfloat", "button", "dual-state-button", "checkbox", "radio",
               "picture", "crop", "hotspot", "progress-bar", "slider", "qr-code",
               "scrolling-text", "timer", "variable", "touch-capture")


def _probes() -> list:
    """Returns every probe of P whose fixtures keep its whole user code, in
    parts, and whose pages are made in memory, once each."""
    return [probe for probe in _probes_keeping_their_user_code(series=("P",))
            if made_in_memory(probe)]


def _expected(page_object, name: str, value):
    """Returns the probe's value of `page_object`'s attribute `name`, as
    p_values gives it, whose value read is `value`: bytes for a text, and a
    number for any other. An attribute the page object lacks is at its
    type's default."""
    given = page_object.attribute(name)
    if given is None:
        given = candidate_object(page_object.attribute("type")[0], {}).attribute(name)
    return given if isinstance(value, bytes) else number_from_bytes(given)


class ValuesTest(unittest.TestCase):

    def test_each_value_of_each_object(self):
        objects = values = 0
        for probe in _probes():
            project = probe_facts(probe)
            decoded = decoded_user_code(user_code_of(probe), probe.base,
                                        project.settings.model.name, project.settings.rotation,
                                        project.settings.encoding)
            for decoded_page, made in zip(decoded.pages, project.pages):
                for each, own in zip(decoded_page.objects, made.objects):
                    read = p_values(each, decoded_page, decoded)
                    with self.subTest(probe.name, page=decoded_page.page_id,
                                      object_id=each.object_id):
                        self.assertFalse(set(read) & set(P_VALUES_SKIPPED))
                        for name, value in read.items():
                            if each.object_id == 0 and name in _SCREENS:
                                continue
                            self.assertEqual(value, _expected(own, name, value), name)
                            values += 1
                    objects += 1
        # 1032 objects, of 19705 values.
        self.assertEqual((objects, values), (1032, 19705))

    def test_each_component_rebuilt_from_its_values(self):
        # Each component of the types the reader reads whole, at its type's
        # defaults but the values read, compiles into the same user code.
        def values_of(decoded_object, decoded_page, decoded_file):
            if decoded_object.type_name not in _READ_WHOLE:
                return None
            return p_values(decoded_object, decoded_page, decoded_file)
        rebuilt = 0
        for probe in _probes():
            with self.subTest(probe.name):
                code, again, count = rebuilt_user_code(probe_facts(probe), values_of)
                self.assertEqual(again, code)
                rebuilt += count
        # 546 components.
        self.assertEqual(rebuilt, 546)


if __name__ == "__main__":
    unittest.main()
