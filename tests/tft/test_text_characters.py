"""Texts' characters past ASCII letters and digits (tft/statements.py,
tft/control_statements.py, and component_types.text_fits): the blocks the
probes of text_character_probes.py kept once they matched the Nextion
Editor's file, how the encoder writes a text in the project's encoding, and
what the rules take on each series.

Each test gives the function it checks its own input: a probe's page made
in memory from what the probe adds, in a Project of the facts it reads,
and each component's place, read from the probe's table
(tests/tft/unit_inputs.py).
"""
from dataclasses import replace
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame
from tools.tft.probing import p_probes, text_character_probes
from nxwright.tft.component_types import object_module, text_fits
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing.component_probes import user_code_kept
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tests.tft.p_components import TXTS_PAST_ASCII, PTypePieces
from tests.tft.t_components import LoadSectionPieces, t_drawing, t_entries, t_memory
from tests.tft.unit_inputs import piece, piece_names, place, probe_facts, probe_project, project_of


class TxtPiecesTest(unittest.TestCase):
    """Each component of each probe of txts that keeps its whole user code,
    whatever its type, at its type's functions: its memory, which holds its
    txt for a text or a button, its drawing, and its entries; and, for a
    type that keeps its txt after its page's components' memory, as a QR
    code or a scrolling text does, its txt among its page's texts."""

    PROBES = [probe for probe in text_character_probes.PROBES if probe.kept is user_code_kept]

    def test_its_probes(self):
        self.assertEqual(len(self.PROBES), 3)

    def test_each_component(self):
        compared = 0
        for probe in self.PROBES:
            project = probe_facts(probe)
            for object_id, page_object in enumerate(project.pages[0].objects[1:], 1):
                its_place = place(probe, "page0-%d" % object_id)
                for kind, function in (("memory", t_memory), ("drawing", t_drawing),
                                       ("entries", t_entries)):
                    with self.subTest(probe.name, object_id=object_id, kind=kind):
                        self.assertEqual(function(page_object, project, its_place),
                                         piece(probe, "page0-%d-%s" % (object_id, kind)))
                compared += 1
        self.assertEqual(compared, 12)

    def test_each_txt_after_the_memory(self):
        # Each txt, as its type keeps it, is among its page's texts. Where
        # each lies among them is the frame's, which the sample compares
        # until the tests of the frame take it.
        compared = 0
        for probe in self.PROBES:
            project = probe_facts(probe)
            texts = piece(probe, "page0-texts")
            for object_id, page_object in enumerate(project.pages[0].objects[1:], 1):
                if place(probe, "page0-%d" % object_id).text_place is None:
                    continue
                with self.subTest(probe.name, object_id=object_id):
                    self.assertIn(object_module(page_object).page_text(page_object, project),
                                  texts)
                compared += 1
        self.assertEqual(compared, 4)


class TxtOnPTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """Each component of each P probe of txts past ASCII letters and digits,
    whatever its type, at its type's functions on P, against the probe's
    pieces: its values after its record's head, its entries, its blocks in
    its page's load section, and its texts' rooms among its page's texts.
    The probes are T's probes of txts above, those of the encodings' txts
    in gb2312, utf-8, shift-jis, and koi8-r (encoding_probes.py), and P's
    of a select, a combo box, and a switch, in iso-8859-1, gb2312, and
    utf-8 (p_probes.py)."""

    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith(TXTS_PAST_ASCII)]
    # 12 components in T's three probes, 6 in each of the four encodings',
    # and 3 in each of P's three.
    COUNT = 45

    def test_each_text_among_its_page_s_texts(self):
        # Each text's room, as its type gives it, where its place gives it
        # among its page's texts. The piece starts with the 4 zeros the
        # frame writes before them (frame._BEFORE_TEXTS), then the first
        # text.
        compared = 0
        for probe in self.PROBES:
            components = [(page_object, its_place) for each, page_object, its_place, _
                          in self.components if each is probe]
            first = min(text_place for _, its_place in components
                        for text_place in (its_place.text_places or {}).values())
            texts = piece(probe, "page0-texts")
            for page_object, its_place in components:
                module = object_module(page_object)
                for attribute, maxl, _ in component_types.p_texts(module).values():
                    room = component_types.p_text(module, page_object, attribute, maxl)
                    start = len(frame._BEFORE_TEXTS) + its_place.text_places[attribute] - first
                    with self.subTest(probe.name, object_id=its_place.object_id,
                                      text=attribute):
                        self.assertEqual(texts[start:start + len(room)], room)
                    compared += 1
        # A txt of each component, and a path of each select and combo box.
        self.assertEqual(compared, 51)


class CodeFixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe of texts in code, on its page made
    in memory, against the probe's pieces."""

    def test_each_probe(self):
        probes = [probe for probe in text_character_probes.PROBES
                  if probe.fixtures and probe.kept is not user_code_kept]
        self.assertEqual(len(probes), 2)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class EncodeTest(unittest.TestCase):
    """A text is written in the project's encoding, iso-8859-1: each
    character from U+00A0 to U+00FF as its own byte, as the Nextion Editor
    wrote them."""

    def test_texts_in_code(self):
        project = project_of()
        self.assertEqual(encode_line('prints "é ü",0', CodePlace(), CompileContext(project)),
                         b'\x09\x0f\x08"\xe9 \xfc",0')
        self.assertEqual(encode_line('sys0=sys1', CodePlace(), CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=\x05\x04\x00\x00\x00")

    def test_control_characters(self):
        # A control character is written as its byte, as any other is.
        project = project_of()
        for line in ('prints "a\tb",0', 'prints "\u0085",0',
                     'xstr 0,0,9,9,0,RED,WHITE,0,0,1,"\u009f"'):
            with self.subTest(line):
                self.assertTrue(encodable(line))
        self.assertEqual(encode_line('prints "a\tb",0', CodePlace(), CompileContext(project)),
                         b'\x09\x0f\x08"a\tb",0')

    def test_a_character_the_encoding_lacks_is_refused(self):
        # nxwright cannot write a character past U+00FF in iso-8859-1, so the
        # rule of a line past ASCII refuses it (frame.py).
        left = [Need("text in code", "iso-8859-1", 'prints "Ā",0')]
        self.assertEqual(unmatched(left, frame.MATCHED), left)


class TxtTest(unittest.TestCase):
    """A component's txt, on each series, is written as its bytes, so it may
    be of any characters, up to its txt_maxl in bytes."""

    @staticmethod
    def need(value: bytes, series: str = "T", txt_maxl: int = 100) -> Need:
        return Need("attribute", "text.txt", value, context={"txt_maxl": bytes([txt_maxl])},
                    series=series)

    def test_on_each_series(self):
        for series in ("T", "K", "P", "E", "F"):
            for value in (text_character_probes.PRINTABLE_ASCII.encode("ascii"),
                          text_character_probes.LATIN_1.encode("iso-8859-1"),
                          b"a\tb", b"a\x85b", b"two\r\nlines", b""):
                with self.subTest(series=series, value=value[:10]):
                    self.assertTrue(text_fits(self.need(value, series)))
        # A need of no series is taken for T's.
        self.assertTrue(text_fits(replace(self.need(b"a b"), series=None)))

    def test_past_its_txt_maxl(self):
        # Its room holds no more bytes than its txt_maxl.
        self.assertTrue(text_fits(self.need(b"abc", txt_maxl=3)))
        self.assertFalse(text_fits(self.need(b"abcd", txt_maxl=3)))


class TextsInRoomsTest(unittest.TestCase):
    """The texts of P's own types, and the paths of the external picture, the
    gmov, the video, and the audio, are written as their bytes in their
    rooms, so each may be of any characters, empty among them, up to its
    room in bytes."""

    # Each text, by its type, and the attribute that gives its room.
    TEXTS = [("data-record.%s" % text, room) for text, room in (
                 ("path", "path_m"), ("format", "format_m"), ("dir", "dir_m"),
                 ("filter", "filter_m"), ("txt", "txt_m"))] \
        + [("file-browser.%s" % text, room) for text, room in (
               ("dir", "dir_m"), ("filter", "filter_m"), ("txt", "txt_m"), ("vvs2", "vvs2_m"))] \
        + [("select.path", "path_m"), ("combo-box.path", "path_m"),
           ("sliding-text.txt", "txt_maxl"), ("sliding-text.path", "path_m"),
           ("external-picture.path", "path_m"), ("gmov.path", "path_m"),
           ("video.path", "path_m"), ("audio.path", "path_m")]
    VALUE = "a b/é\t^*|.\r\nz".encode("iso-8859-1")

    def need(self, subject: str, room: str, value: bytes, size: int) -> Need:
        context = {room: bytes([size]), "txt_maxl": bytes([size])}
        return Need("attribute", subject, value, context=context, series="P",
                    encoding="iso-8859-1")

    def test_any_characters_in_its_room(self):
        rules = matched_rules()
        for subject, room in self.TEXTS:
            for value in (self.VALUE, b""):
                with self.subTest(subject, value=value):
                    need = self.need(subject, room, value, len(self.VALUE))
                    self.assertEqual(unmatched([need], rules), [])
            with self.subTest(subject, past_its_room=True):
                need = self.need(subject, room, self.VALUE, len(self.VALUE) - 1)
                self.assertEqual(unmatched([need], rules), [need])


if __name__ == "__main__":
    unittest.main()
