"""The progress bar component (tft/component_types/progress_bar.py): its
memory, its drawing, its entries and slots, what its list matched, the
blocks the encoder gives its attributes in code, and its memory and entries
on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/progress_bar_probes.py), made
by nxwright's page reader, and, for a function that reads a project, a
Project of the facts it reads (tests/tft/unit_inputs.py). A probe of code
compares the encoder's blocks with its fixture, which the probe runner wrote
once the probe matched the Nextion Editor's file. The probes of a progress
bar's whole user code are compared at its type's functions, and one of
them is compared whole, as the type's sample, in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.component_types import progress_bar
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import p_probes, progress_bar_probes
from tools.tft.probing.progress_bar_probes import OF_PICTURES, PICTURES, progress_bar_component
from tools.tft.probing.statement_probes import event_blocks, touch_release_code
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, piece, piece_names, project_of

# The pictures of the probes drawn in pictures, by name, in ID order.
_PICTURE_NAMES = tuple(name for name, _, _ in PICTURES)


def value(number: int, size: int = 2) -> bytes:
    return number.to_bytes(size, "little", signed=True)


def _probe(name: str):
    return next(probe for probe in progress_bar_probes.PROBES if probe.name == name)


class MemoryTest(unittest.TestCase):
    """A progress bar's starting memory: sta 0, dez 0, its val, dis 25, bco
    48631, and pco 1024. It reads no project."""

    def test_its_val(self):
        for val in (0, 50, 73, 100):
            bar = page(progress_bar_component(val=val)).objects[1]
            with self.subTest(val=val):
                self.assertEqual(progress_bar.variant(bar).memory(bar, None),
                                 bytes([0, 0, val, 25]) + struct.pack("<HH", 48631, 1024))


class LooksTest(TypePieces, unittest.TestCase):
    """Each progress bar of each probe that keeps its whole user code, as
    the Nextion Editor wrote it, against the probe's pieces: its memory, its
    drawing, and its entries, at its type's functions (tests/tft/t_components.py).
    Among them, two bars of other colours and corners, filled upward, and
    drawn in pictures."""

    TYPE = "progress-bar"
    PROBES = progress_bar_probes.PROBES
    COUNT = 10

    def test_its_entries_and_slots_in_pictures(self):
        # 32 entries: its bpic and ppic 22 and 23, in its bco's and pco's
        # places, and no dis; slots 31 and 32, and no slots 4, 16, and 55.
        page_object = page(*OF_PICTURES, pictures=_PICTURE_NAMES).objects[1]
        pictures = progress_bar.variant(page_object)
        self.assertEqual(pictures.ENTRIES, 32)
        self.assertEqual([pictures.attribute_place(name) for name in ("val", "bpic", "ppic")],
                         [21, 22, 23])
        for name in ("dis", "bco", "pco"):
            with self.subTest(name), self.assertRaises(KeyError):
                pictures.attribute_place(name)
        self.assertEqual(pictures.record_slots(), {
            1: 3, 2: 19, 20: 21, 30: 20, 31: 22, 32: 23, 42: 9, 43: 10, 44: 13, 45: 14, 46: 11,
            47: 12, 49: 1, 62: 0})


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each progress bar of each of its probes on P that keeps its whole user code, at
    its type's functions on P, against the probe's pieces
    (tests/tft/p_components.py)."""

    TYPE = "progress-bar"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-progress-bar-")]
    COUNT = 10
    CODE_COUNT = 2

class MatchedTest(unittest.TestCase):
    """The needs progress_bar.MATCHED covers (matching.py)."""

    def need(self, attribute: str, raw: bytes, **context) -> Need:
        attributes = {"x": value(10), "y": value(10), "w": value(128), "h": value(30)}
        attributes.update({name: value(number) for name, number in context.items()})
        return Need("attribute", "progress-bar." + attribute, raw, context=attributes)

    def test_what_it_covers(self):
        covered = [Need("type", "progress-bar"),
                   Need("attribute", "progress-bar.objname", b"j0"),
                   self.need("x", value(192), x=192, y=450),
                   self.need("w", value(2), x=0, y=0, w=2, h=2),
                   self.need("val", bytes([0])), self.need("val", bytes([100])),
                   self.need("bco", value(0)), self.need("pco", value(0xFFFF, 4)[:2]),
                   self.need("dis", bytes([0])), self.need("dis", bytes([100])),
                   self.need("dez", bytes([1])), self.need("sta", bytes([1])),
                   self.need("bpic", value(1)), self.need("ppic", value(0xFFFF, 4)[:2])]
        self.assertEqual(unmatched(covered, progress_bar.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A dez and a sta past 1 are left out. A val and a dis past 100 are
        # taken.
        left = [self.need("dez", bytes([2])), self.need("sta", bytes([2]))]
        self.assertEqual(unmatched(left, progress_bar.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may use a progress bar's val, and any other attribute it writes.
    The encoder reads the page's components and program.s's variables."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page(progress_bar_component()))

    def test_its_val(self):
        # j0 is page0's first component: its first entry is 33, so its val's
        # is 54.
        self.assertEqual(encode_line("j0.val=5", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x01\x36\x00\x00\x00=5")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its pco, entry 24 within the type,
        # after j0's first entry, 33; but not one it does not write.
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("j0.pco=1", place, CompileContext(self.project)),
                         b"\x01" + (33 + 24).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "j0's txt is not encoded"):
            encode_line("j0.txt=1", place, CompileContext(self.project))


class CodeFixtureTest(unittest.TestCase):
    """The blocks the encoder gives page0's Touch Release event, in strict
    Nextion syntax, as the probes of code keep them as their one piece,
    "event"."""

    def assert_event(self, project, probe_name: str):
        probe = _probe(probe_name)
        self.assertEqual(event_blocks(project),
                         {name: piece(probe, name) for name in piece_names(probe)})

    def test_its_val(self):
        # Its val set, stepped, read, compared in if, while, and for, and as
        # the serial commands' operand.
        made = page(*progress_bar_probes.VAL_IN_CODE_COMPONENTS, strict=True,
                    code=touch_release_code(progress_bar_probes.VAL_IN_CODE))
        self.assert_event(project_of(made, strict=True), "progress-bar-val-in-code")

    def test_its_pictures(self):
        # Its pictures read and set, and its val and dis, whose entries are
        # one down drawn in pictures.
        made = page(*progress_bar_probes.PICTURES_IN_CODE_COMPONENTS, strict=True,
                    pictures=_PICTURE_NAMES,
                    code=touch_release_code(progress_bar_probes.PICTURES_IN_CODE))
        self.assert_event(project_of(made, strict=True, pictures=len(_PICTURE_NAMES)),
                          "progress-bar-pictures-in-code")


class PTest(unittest.TestCase):
    """On P, a progress bar's entries by its sta, and what the check matches
    there; its memory's values are PPiecesTest's (p_probes.py)."""

    def test_its_entries_by_its_sta(self):
        # As on T: in pictures, its dis has no entry, so its bpic and ppic
        # take entries 22 and 23. A picture's highest is set from the
        # project (P_LAST_RESOURCE).
        entries = {sta: {entry: (name, at) for entry, (name, at, *_) in
                         progress_bar._of(sta).P_ENTRIES.items() if entry >= 19}
                   for sta in (0, 1)}
        self.assertEqual(entries[0], {19: ("sta", 56), 20: ("dez", 57), 21: ("val", 58),
                                      22: ("dis", 59), 23: ("bco", 60), 24: ("pco", 62)})
        self.assertEqual(entries[1], {19: ("sta", 56), 20: ("dez", 57), 21: ("val", 58),
                                      22: ("bpic", 60), 23: ("ppic", 62)})
        self.assertEqual(progress_bar._of(1).P_LAST_RESOURCE,
                         {"bpic": "picture", "ppic": "picture"})

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "progress-bar", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
