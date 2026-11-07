"""The video (tft/component_types/video.py), a type P and E have and T and
K have not: its memory and its buffer on P, its entries and its path's
room by its from, its page's load section, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a video's memory starts with its record's
head, which the frame writes, so its tests compare the values its type
writes after the head (tests/tft/p_components.py). The probes of a video's
whole user code are compared in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft import component_types
from nxwright.tft.component_types import video
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import p_probes, video_probes
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe, p_values
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, piece, place, project_of

_PROBE_AT_ITS_DEFAULTS = "p-video-at-its-defaults"
# A place for a video from a file of no probe: that of the second of the
# probe of two, from its probe's table. Where its path and its buffer lie is
# the frame's, compared on a whole build in tests/tft/test_whole_files.py.
_FROM_A_FILE = place(p_probe("p-video-two-beside-a-text"), "page0-3")


def _video(**attributes):
    """Returns the page object of a video of `attributes` on P."""
    return page(video_probes.video_component(**attributes), series="P").objects[1]


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """A video's memory, entries, and load section, against the pieces of the
    probes of one video at its defaults and of two beside a text.

    Its memory, at places counted from its start: from the project, no path_m
    and no path's place at 82 and 84, though its path_m is 255; its buffer's
    size, 64000, at 88, and its place at 92. Its entries: from the project,
    its vid's is 20, with 1 in its owner field's top byte, and its en's 21;
    from a file, its path's takes vid's.

    In its page's load section, a video adds `init` with its ID."""

    TYPE = "video"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-video-")]
    COUNT = 3


class FromTheProjectTest(unittest.TestCase):

    def test_no_room_and_its_buffer(self):
        # It keeps no room for a path; its buffer is 64000 bytes.
        video_object = _video()
        module = component_types.object_module(video_object)
        self.assertEqual(component_types.p_texts(module), {})
        self.assertEqual(module.buffer_size(video_object, project_of(series="P")), 64000)
        self.assertRaises(KeyError, video._of(False).attribute_place, "path")

    def test_path_and_molloc_change_nothing(self):
        # Its values with a path, a path_m, a molloc, and a molloc_s are
        # those of the probe at its defaults.
        probe = p_probe(_PROBE_AT_ITS_DEFAULTS)
        self.assertEqual(
            p_values(_video(path="sd0/a.video", path_m=20, molloc=30000, molloc_s=20000),
                     place(probe, "page0-1")),
            piece(probe, "page0-1-memory"))


class FromAFileTest(unittest.TestCase):

    def test_memory(self):
        # Its vid 0 at 56; its from, 1, at 80, its path_m, 255, at 82, and
        # its buffer's size, 64000, at 88; its path's room, 256 bytes of
        # zeros.
        video_object = _video(**{"from": 1})
        module = component_types.object_module(video_object)
        memory = p_memory(video_object, _FROM_A_FILE)
        self.assertEqual(memory[56:58], bytes(2))
        self.assertEqual(memory[80:84].hex(" "), "01 00 ff 00")
        self.assertEqual(memory[88:92].hex(" "), "00 fa 00 00")
        self.assertEqual(component_types.p_text(module, video_object, "path", "path_m"),
                         bytes(256))

    def test_entries(self):
        # Its path's entry takes vid's, 20, with 0x80 in its owner field's
        # top byte; 21 is empty; its en's is 22. Each owner field starts
        # with the page's ID and the object's, which its place gives.
        entries = p_entries(_video(**{"from": 1}), _FROM_A_FILE)
        self.assertEqual(entries[24 * 20:][18:24].hex(" "), "00 80 3f 00 01 00")
        self.assertEqual(entries[24 * 21:][:24], bytes(24))
        self.assertEqual(entries[24 * 22:][18:24].hex(" "), "00 02 31 01 00 00")
        self.assertRaises(KeyError, video._of(True).attribute_place, "vid")


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "video", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "video", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_path(self):
        # Any characters, no longer than its path_m, from a file and from the
        # project alike.
        rules = matched_rules()

        def need(path: bytes, path_m: int, source: int) -> Need:
            return Need("attribute", "video.path", path, series="P",
                        context={"path_m": path_m.to_bytes(2, "little"),
                                 "from": source.to_bytes(1, "little")})
        for source in (0, 1):
            with self.subTest(source):
                for path, path_m in ((b"sd0/Vid_1.video", 15), (b"a b", 255)):
                    self.assertEqual(unmatched([need(path, path_m, source)], rules), [])
                for path, path_m in ((b"sd0/Vid_1.video", 14),):
                    self.assertEqual(unmatched([need(path, path_m, source)], rules),
                                     [need(path, path_m, source)])

    def test_its_times_at_their_entries_limits(self):
        rules = matched_rules()
        for name in ("tim", "stim", "qty"):
            for value in (-2 ** 31, 2 ** 31 - 1):
                with self.subTest(name, value=value):
                    need = Need("attribute", "video." + name,
                                value.to_bytes(4, "little", signed=True), series="P")
                    self.assertEqual(unmatched([need], rules), [])

    def test_its_values(self):
        # Its vid, any value from the project, written as it is.
        rules = matched_rules()

        def need(name: str, value: int, **context) -> Need:
            return Need("attribute", "video." + name, value.to_bytes(4, "little"),
                        context=context, series="P")
        for name, value in (("from", 1), ("en", 2), ("en", 3), ("fps", 50), ("fps", 51),
                            ("dis", 9), ("dis", 10), ("dis", 1000),
                            ("tim", 0x7FFFFFFF), ("vid", 0), ("vid", 0xFFFF)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])
        for name, value in (("from", 2), ("vid", 0x10000)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [need(name, value)])
        # From a file, any vid too, which it does not write.
        self.assertEqual(unmatched([need("vid", 3, **{"from": b"\x01"})], rules), [])


if __name__ == "__main__":
    unittest.main()
