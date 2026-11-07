"""The sliding text (tft/component_types/sliding_text.py), a type P and E
have and T and K have not: its memory and its two texts' rooms on P, its
path's room at a path_m of 0, its entries and their owner fields, its page's
load section, the blocks of its attributes in code, and what its rules
cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a sliding text's memory starts with its
record's head, which the frame writes, so its tests compare the values its
type writes after the head (tests/tft/p_components.py). The probes of a
sliding text's whole user code are compared in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import p_probes, sliding_text_probes
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, probe_project, project_of

_PAGE_ENTRIES = 33
# A place for a sliding text of no probe: that of the sliding text at its
# defaults, from its probe's table.
_PLACE = place(p_probe("p-sliding-text-at-its-defaults"), "page0-1")


def _sliding_text(**attributes):
    """Returns the page object of a sliding text of `attributes` on P."""
    return page(sliding_text_probes.sliding_text_component(**attributes),
                series="P").objects[1]


def _project(**attributes):
    """Returns a Project of the facts of a page on P of one sliding text of
    `attributes`, for the encoder."""
    return project_of(page(sliding_text_probes.sliding_text_component(**attributes),
                           series="P"), series="P")


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """A sliding text's memory, entries, and load section, against the pieces
    of the probes of one sliding text at its defaults, of two beside a text,
    and of one at the lowest and one at the highest maxval_y and val_y.

    Its memory, at places counted from its start: from 70 its txt_maxl and the
    place of its txt, from 82 its path_m and the place of its path, and its
    maxval_y and val_y, 4 bytes each. Its entries: seven give a top byte of
    their own in their owner field, and its texts' give where they lie.

    In its page's load section, a sliding text adds `init` with its ID."""

    TYPE = "sliding-text"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-sliding-text-")]
    COUNT = 22


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its txt's room, its ten lines in 260 bytes, then its path's, 260
        # bytes of zeros: at a path_m of 0, its txt_maxl gives its room.
        text_object = _sliding_text()
        module = component_types.object_module(text_object)
        lines = b"000\r\n111\r\n222\r\n333\r\n444\r\n666\r\n777\r\n777\r\n888\r\n999"
        self.assertEqual(component_types.p_text(module, text_object, "txt", "txt_maxl"),
                         lines.ljust(260, b"\x00"))
        self.assertEqual(component_types.p_text(module, text_object, "path", "path_m"),
                         bytes(260))

    def test_its_path_s_room(self):
        # Its path_m + 1 bytes, rounded up to 4; its txt_maxl + 1 at a
        # path_m of 0. Its txt's room is its txt_maxl + 1 bytes, rounded up
        # to 4.
        for attributes, room in (({"path_m": 20}, 24), ({"path_m": 1, "txt_maxl": 50}, 4),
                                 ({"txt": "ab", "txt_maxl": 10}, 12)):
            with self.subTest(attributes):
                text_object = _sliding_text(**attributes)
                module = component_types.object_module(text_object)
                txt_maxl = attributes.get("txt_maxl", 256)
                self.assertEqual(len(component_types.p_text(module, text_object, "txt",
                                                            "txt_maxl")),
                                 -(-(txt_maxl + 1) // 4) * 4)
                self.assertEqual(len(component_types.p_text(module, text_object, "path",
                                                            "path_m")), room)


class EntryTest(unittest.TestCase):

    def test_in_code(self):
        # Its val_y is the 38th of its own entries, after the page's 33.
        self.assertEqual(encode_line("sys0=slt0.val_y", CodePlace(0, "page0", "up"),
                                     CompileContext(_project())),
                         b"\x05\x00\x00\x00\x00=\x01" + (_PAGE_ENTRIES + 37).to_bytes(4, "little"))

    def test_its_path_in_code(self):
        # Code names its path as its own entry 34, whose data is empty.
        self.assertEqual(p_entries(_sliding_text(), _PLACE)[24 * 34:][:24], bytes(24))
        self.assertEqual(encode_line('slt0.path="a"', CodePlace(0, "page0", "up"),
                                     CompileContext(_project())),
                         b"\x01" + (_PAGE_ENTRIES + 34).to_bytes(4, "little") + b'="a"')

    def test_its_path_in_code_with_an_effect(self):
        # An effect moves its entries from 19 two on, its path's too.
        self.assertEqual(encode_line('slt0.path="a"', CodePlace(0, "page0", "up"),
                                     CompileContext(_project(effect=2))),
                         b"\x01" + (_PAGE_ENTRIES + 36).to_bytes(4, "little") + b'="a"')

    def test_its_path_in_code_with_a_border_or_nothing_behind(self):
        # A border of one colour moves its entries from its font's two on,
        # its path's too. With nothing behind it, its style's and its bco's
        # entries are not there, and its path's moves two down.
        for attributes, entry in (({"style": 1}, 36), ({"sta": 3}, 32)):
            with self.subTest(**attributes):
                self.assertEqual(encode_line('slt0.path="a"', CodePlace(0, "page0", "up"),
                                             CompileContext(_project(**attributes))),
                                 b"\x01" + (_PAGE_ENTRIES + entry).to_bytes(4, "little")
                                 + b'="a"')


class LeftshowAndKeyTest(unittest.TestCase):
    """Its leftshow and its key, which have no entry."""

    def test_its_leftshow_lies_in_its_memory(self):
        # At 67, before its left, and nowhere else; a key of 5 nowhere.
        plain, shown = (p_memory(_sliding_text(**attributes), _PLACE)
                        for attributes in ({}, {"leftshow": 1, "key": 5}))
        self.assertEqual([at for at, (a, b) in enumerate(zip(plain, shown)) if a != b], [67])
        self.assertEqual(shown[67], 1)

    def test_any_key(self):
        # Any key, on P and E, 1 to 4, which bind a keyboard, among them.
        rules = matched_rules()
        for series in ("P", "E"):
            for key in (0, 1, 2, 4, 5, 255):
                with self.subTest(series=series, key=key):
                    need = Need("attribute", "sliding-text.key", bytes([key]), series=series)
                    self.assertEqual(unmatched([need], rules), [])

    def test_the_keypad_s_key_opens_its_page(self):
        # As a text's key does: its keyboard's three lines, after its own
        # Touch Release code. A key of no keyboard adds none.
        self.assertEqual(component_types.key_lines(_sliding_text(key=2, vscope=1), 1),
                         ["keybdB.loadpageid.val=dp", "keybdB.loadcmpid.val=1", "page keybdB"])
        self.assertEqual(component_types.key_lines(_sliding_text(key=5), 1), [])

    def test_the_frame_writes_the_keypad_s_page(self):
        # The probe's pages made in memory: `page keybdB`, 09 0c 04 and the
        # page's name, ends the sliding text's Touch Release code beside the
        # keypad; a key of no keyboard writes none.
        for name, pages in (("p-sliding-text-on-the-keypad", [b"\x09\x0c\x04keybdB"]),
                            ("p-sliding-text-of-leftshow-and-key", [])):
            code = frame.user_code(probe_project(p_probe(name)))
            with self.subTest(name):
                self.assertEqual([block for block in code.blocks
                                  if block[:1] == b"\x09" and block.endswith(b"keybdB")], pages)


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "sliding-text", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "sliding-text", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_txt(self):
        # Lines of any characters between "\r\n", or none, no
        # longer than its txt_maxl.
        rules = matched_rules()

        def need(txt: bytes, txt_maxl: int) -> Need:
            return Need("attribute", "sliding-text.txt", txt, series="P",
                        context={"txt_maxl": txt_maxl.to_bytes(2, "little")})
        for txt, txt_maxl in ((b"Ab\r\n9z\r\nc", 9), (b"a", 1), (b"a b", 255), (b"a\nb", 255),
                              (b"", 0)):
            with self.subTest(txt):
                self.assertEqual(unmatched([need(txt, txt_maxl)], rules), [])
        for txt, txt_maxl in ((b"Ab\r\n9z\r\nc", 8),):
            with self.subTest(txt):
                self.assertEqual(unmatched([need(txt, txt_maxl)], rules), [need(txt, txt_maxl)])

    def test_its_path(self):
        # Lines of any characters between "\r\n", no longer than its
        # path_m, or than its txt_maxl at a path_m of 0.
        rules = matched_rules()

        def need(path: bytes, path_m: int, txt_maxl: int = 256) -> Need:
            return Need("attribute", "sliding-text.path", path, series="P",
                        context={"path_m": path_m.to_bytes(2, "little"),
                                 "txt_maxl": txt_maxl.to_bytes(2, "little")})
        for path, path_m, txt_maxl in ((b"Ab\r\n9z\r\nc", 9, 1), (b"cdefghij", 0, 8),
                                       (b"a b", 255, 256), (b"a\nb", 255, 256)):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m, txt_maxl)], rules), [])
        for path, path_m, txt_maxl in ((b"Ab\r\n9z\r\nc", 8, 256), (b"cdefghij", 0, 7)):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m, txt_maxl)], rules),
                                 [need(path, path_m, txt_maxl)])

    def test_its_values(self):
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "sliding-text." + name, value.to_bytes(4, "little"),
                        series="P")
        for name, value in (("path_m", 0), ("path_m", 65534), ("txt_maxl", 0), ("txt_maxl", 1024),
                            ("txt_maxl", 0xFFFE), ("txt_maxl", 0xFFFF), ("left", 2), ("left", 3),
                            ("ch", 32), ("ch", 33)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])
        for name, value in (("path_m", 65535),):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [need(name, value)])


if __name__ == "__main__":
    unittest.main()
