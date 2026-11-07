"""The audio (tft/component_types/audio.py), a type P and E have and T and
K have not: its memory, entries, and path's room on P, by its from, its
page's load section, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, an audio's memory starts with its record's
first 28 bytes, which the frame writes, so its tests compare the values its
type writes after them (tests/tft/p_components.py). The probes of an audio's
whole user code, and its record's place and its playend event's, are
compared in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft import component_types
from nxwright.tft.component_types import ObjectPlace
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import audio_probes, p_probes
from tools.tft.probing.text_probes import text_component
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, project_of

_ENTRY = struct.Struct("<IiiiII")
# From a file, of a path of its own.
_FROM_A_FILE = {"path": "sd0/a.wav", "path_m": 20, "from": 1}
# Places for an audio of no probe, from the probes' tables: from the
# project, that of the audio at its defaults; from a file, that of the
# first of the probe of two.
_PLACE = place(p_probe("p-audio-at-its-defaults"), "page0-1")
_PLACE_FROM_A_FILE = place(p_probe("p-audio-two-beside-a-text"), "page0-1")


def _audio(**attributes):
    """Returns the page object of an audio of `attributes` on P."""
    return page(audio_probes.audio_component(**attributes), series="P").objects[1]


def _context(**attributes) -> dict:
    """Returns the context of a line in page0's Touch Release event, on a P
    page of a text and an audio of `attributes`."""
    project = project_of(page(text_component(), audio_probes.audio_component(**attributes),
                              series="P", code="on page0.up:\n  sys0=1\n"),
                         series="P", fonts=0)
    return next(need.context for need in project_needs(project)
                if need.kind == "code" and need.subject == "event")


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """An audio's memory, entries, and load section, against the pieces of the
    probes of one audio at its defaults and of two beside a text.

    Its memory, at places counted from its start, after its record's first 28
    bytes: zeros to 56, its vid, en, loop, fps, and dis, zeros, its buffer's
    size, 64000, and where its buffer lies.

    In its page's load section, an audio adds `init` with its ID."""

    TYPE = "audio"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-audio-")]
    COUNT = 3


class MemoryTest(unittest.TestCase):

    def test_from_a_file(self):
        # Its path_m and where its path lies, in a room of path_m + 1 bytes,
        # rounded up to 4; its vid 0.
        audio_object = _audio(**_FROM_A_FILE)
        module = component_types.object_module(audio_object)
        memory = p_memory(audio_object, _PLACE_FROM_A_FILE)
        self.assertEqual(memory[56:58], b"\x00\x00")
        path_m, path_place = struct.unpack_from("<HI", memory, 82)
        self.assertEqual((path_m, path_place), (20, _PLACE_FROM_A_FILE.text_places["path"]))
        self.assertEqual(component_types.p_text(module, audio_object, "path", "path_m"),
                         b"sd0/a.wav".ljust(24, b"\x00"))


class EntriesTest(unittest.TestCase):

    def test_by_its_from(self):
        # From the project, vid's entry is its 9th, of owner top 1; from a
        # file, the path's takes its place, of owner top 0x80 and a code of
        # its room, and the later entries are one on: en's is its 11th.
        def entries(object_place: ObjectPlace, **attributes):
            data = p_entries(_audio(**attributes), object_place)
            return [_ENTRY.unpack_from(data, entry * _ENTRY.size)
                    for entry in range(len(data) // _ENTRY.size)]
        from_the_project = entries(_PLACE)
        from_a_file = entries(_PLACE_FROM_A_FILE, **_FROM_A_FILE)
        self.assertEqual((len(from_the_project), len(from_a_file)), (20, 21))
        self.assertEqual(from_the_project[8][4] >> 24, 0x01)
        self.assertEqual(from_a_file[8][4] >> 24, 0x80)
        self.assertEqual(from_a_file[8][5], 21 << 8 | 0x3F)
        self.assertEqual(from_the_project[9][1] - from_the_project[9][0], 58)
        self.assertEqual(from_a_file[10][1] - from_a_file[10][0], 58)


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "audio", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "audio", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_times_at_their_entries_limits(self):
        rules = matched_rules()
        for name in ("tim", "stim", "qty"):
            for value in (-2 ** 31, 2 ** 31 - 1):
                with self.subTest(name, value=value):
                    need = Need("attribute", "audio." + name,
                                value.to_bytes(4, "little", signed=True), series="P")
                    self.assertEqual(unmatched([need], rules), [])

    def test_its_vid(self):
        # Any value from 0 to 65535: written as it is from the project, and
        # not written from a file.
        rules = matched_rules()

        def need(value: int, source: bytes) -> Need:
            return Need("attribute", "audio.vid", value.to_bytes(4, "little"),
                        context={"from": source}, series="P")
        for value in (0, 4, 0xFFFF):
            for source in (b"\x00", b"\x01"):
                with self.subTest(value=value, source=source):
                    self.assertEqual(unmatched([need(value, source)], rules), [])
        refused = need(0x10000, b"\x00")
        self.assertEqual(unmatched([refused], rules), [refused])

    def test_its_path(self):
        # Any characters, within its path_m, from a file and from the project
        # alike: from the project it is written nowhere.
        rules = matched_rules()

        def need(value: bytes, **context) -> Need:
            return Need("attribute", "audio.path", value, series="P",
                        context={"path_m": (20).to_bytes(2, "little"), **context})
        for source in (b"\x00", b"\x01"):
            with self.subTest(source):
                for value in (b"sd0/a.wav", b"sd0/a b.wav"):
                    self.assertEqual(unmatched([need(value, **{"from": source})], rules), [])
                for value in (b"a" * 21,):
                    refused = need(value, **{"from": source})
                    self.assertEqual(unmatched([refused], rules), [refused])

    def test_its_code(self):
        # From the project, its path is not in code; from a file, it is, set
        # from a text or from a txt (p_probes' paths-set-from-txts).
        rules = matched_rules()
        internal, external = _context(), _context(**_FROM_A_FILE)
        for line, context, covered in (
                ("sys0=wav0.en", internal, True), ('wav0.path="sd0/b.wav"', internal, False),
                ('wav0.path="sd0/b.wav"', external, True), ("t0.txt=wav0.path", external, True),
                ("wav0.path=t0.txt", external, True), ("wav0.path=t0.txt", internal, False)):
            with self.subTest(line, covered=covered):
                need = Need("code", "event", line, context=context, series="P")
                self.assertEqual(unmatched([need], rules), [] if covered else [need])


if __name__ == "__main__":
    unittest.main()
