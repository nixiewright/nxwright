"""The external picture (tft/component_types/external_picture.py), a type
P and E have and T and K have not: its memory and its path's room on P, its
entries, the blocks of its attributes in code, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, an external picture's memory starts with its
record's head, which the frame writes, so its tests compare the values its
type writes after the head (tests/tft/p_components.py). The probes of an
external picture's whole user code are compared in
tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import external_picture_probes, p_probes
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_memory, p_probe
from tests.tft.unit_inputs import page, place, project_of

# A place for an external picture of no probe: that of the external
# picture at its defaults, from its probe's table.
_PLACE = place(p_probe("p-external-picture-at-its-defaults"), "page0-1")


def _external_picture(**attributes):
    """Returns the page object of an external picture of `attributes` on
    P."""
    return page(external_picture_probes.external_picture(**attributes),
                series="P").objects[1]


class PieceTest(PTypePieces, unittest.TestCase):
    """An external picture's memory and entries, against the pieces of the
    probes of one at its defaults and of two beside a switch.

    Its memory, at places counted from its start: from 52 its effect, first,
    and time, zeros, two more zeros, its path_m, 255 at its defaults, and the
    place of its path."""

    TYPE = "external-picture"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-external-picture-")]
    COUNT = 3


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its path's room, 256 bytes of zeros.
        picture_object = _external_picture()
        module = component_types.object_module(picture_object)
        self.assertEqual(component_types.p_text(module, picture_object, "path", "path_m"),
                         bytes(256))

    def test_its_path_s_room(self):
        # Its path, then zeros, path_m + 1 bytes, rounded up to 24; its
        # memory gives its path_m at 58.
        picture_object = _external_picture(path="sd0/a.jpg", path_m=20)
        module = component_types.object_module(picture_object)
        self.assertEqual(p_memory(picture_object, _PLACE)[58:60], b"\x14\x00")
        self.assertEqual(component_types.p_text(module, picture_object, "path", "path_m"),
                         b"sd0/a.jpg".ljust(24, b"\x00"))


class CodeTest(unittest.TestCase):

    def test_its_entries(self):
        # Its w's entry is the 12th of its own, and its path's the 20th,
        # after the page's 33.
        project = project_of(page(external_picture_probes.external_picture(), series="P"),
                             series="P")
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=xp0.w", place, CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (33 + 11).to_bytes(4, "little"))
        self.assertEqual(encode_line('xp0.path="a.jpg"', place, CompileContext(project)),
                         b"\x01" + (33 + 19).to_bytes(4, "little") + b'="a.jpg"')


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "external-picture", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "external-picture", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_path(self):
        # A path of any characters, no longer than its path_m.
        rules = matched_rules()

        def need(path: bytes, path_m: int) -> Need:
            return Need("attribute", "external-picture.path", path, series="P",
                        context={"path_m": path_m.to_bytes(2, "little")})
        for path, path_m in ((b"sd0/Pic_1.jpg", 13), (b"", 1), (b"sd0/a-b.jpg", 255),
                             (b"a b.jpg", 255)):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [])
        for path, path_m in ((b"sd0/Pic_1.jpg", 12),):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [need(path, path_m)])

    def test_its_path_m(self):
        rules = matched_rules()

        def need(value: int) -> Need:
            return Need("attribute", "external-picture.path_m", value.to_bytes(2, "little"),
                        series="P")
        for value in (0, 65534):
            with self.subTest(value):
                self.assertEqual(unmatched([need(value)], rules), [])
        for value in (65535,):
            with self.subTest(value):
                self.assertEqual(unmatched([need(value)], rules), [need(value)])


if __name__ == "__main__":
    unittest.main()
