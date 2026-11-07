"""The slider component (tft/component_types/slider.py): its drawing, its
background fill, and the block it adds to its page's load section, its
memory, its entries, what its list matched, which of its attributes code
may use, and its memory, entries, and load block on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/slider_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P. What the frame writes across
objects, such as a slider's record and the head of its memory on P, is
left to the frame's tests, and compared until then by the sample of whole
files (tests/tft/test_whole_files.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import slider
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, slider_probes
from tools.tft.probing.slider_probes import slider_component
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from nxwright.tft.tft_file import encode_blocks
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, LoadSectionPieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, project_of


def bounds(minval: int, maxval: int) -> dict:
    """The context of a slider's val's need, of a slider of `minval` and
    `maxval`."""
    return {"minval": minval.to_bytes(2, "little"), "maxval": maxval.to_bytes(2, "little")}


def _probe(name: str):
    return next(probe for probe in slider_probes.PROBES + p_probes.PROBES
                if probe.name == name)


class PiecesTest(TypePieces, CodePieces, LoadSectionPieces, unittest.TestCase):
    """Each slider of each probe that keeps its whole user code, at its type's
    functions, and each probe of code, at the statement encoder, against the
    probe's pieces (tests/tft/t_components.py): two on a page; one among the
    types matched; one on a second page; two of other colours and sizes; two
    upright; two with pictures or crops behind their tracks; and two with a
    picture as their cursor.

    A slider has no drawing of its own, its drawing a 0 word alone: the
    screen draws it from the block it adds to its page's load section, 09 16
    04 and its ID as text. Its memory gives its mode, sta, psta, wid, hig,
    dis, bco, pco, val, maxval, minval, ch, then its bco1; with pictures or
    crops behind its track, their IDs where its bco and bco1 lie, and zeros
    for its dis and ch; with a picture as its cursor, its ID where its pco
    lies. Its entries give each value's place, from its base, such as its
    val's at base + 10; the top bytes of five owner fields, wid 1, hig 2,
    maxval 3, minval 4, and val 5; and a picture's highest, the project's
    last."""

    TYPE = "slider"
    PROBES = slider_probes.PROBES
    COUNT = 12
    CODE_COUNT = 2

    def test_its_background_fill(self):
        # What lies behind it, the fill of its area, then a 0 word.
        self.assert_each(lambda h, project, its_place: encode_blocks(
            slider.variant(h).background_fill(h, project, its_place) + [b""]), "background-fill")


class PPiecesTest(PTypePieces, CodePieces, LoadSectionPieces, unittest.TestCase):
    """Each slider of each of its probes on P that keeps its whole user code,
    at its type's functions on P, and each probe of code, against the probe's
    pieces (tests/tft/p_components.py): its values, after its record's head and
    its effect's values, its mode, sta, psta, wid, hig, and dis, its bco and
    pco, its val, maxval, minval, and ch, five zeros, its bco1, then four
    zeros; its entries, a drawn component's, its effect's, then its own,
    each a place from its base; and its load section's block, `init` and its
    ID, in place of T's command."""

    TYPE = "slider"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-slider-")]
    COUNT = 13
    CODE_COUNT = 2


class VariantTest(unittest.TestCase):
    """A slider's entries and slots by what lies behind its track and by its
    cursor, on page objects of the probes' components, and its load block
    on K and F."""

    @classmethod
    def setUpClass(cls):
        cls.crops = page_of(_probe("slider-of-pictures-and-crops")).objects[1:3]
        cls.cursors = page_of(_probe("slider-of-a-picture-cursor")).objects[1:3]

    def test_its_entries_and_slots(self):
        # With pictures or crops behind its track, 38 entries: theirs 24 and
        # 25, then its pco, val, maxval, and minval, each one down from a
        # colour's, and none of its bco, bco1, or ch. Its record gives a pic
        # and a pic1 in slots 6 and 40, a picc and a picc1 in slots 5 and 36,
        # and no slots 3, 4, and 38.
        pictures, crops = slider.variant(self.crops[0]), slider.variant(self.crops[1])
        self.assertEqual((pictures.ENTRIES, crops.ENTRIES), (38, 38))
        self.assertEqual([pictures.attribute_place(name)
                          for name in ("pic", "pic1", "pco", "val", "maxval", "minval")],
                         [24, 25, 26, 27, 28, 29])
        for name in ("bco", "bco1", "ch", "picc"):
            with self.subTest(name), self.assertRaises(KeyError):
                pictures.attribute_place(name)
        common = {1: 3, 2: 20, 14: 19, 15: 21, 16: 26, 18: 22, 19: 23, 20: 27, 21: 28, 22: 29,
                  42: 9, 43: 10, 44: 13, 45: 14, 46: 11, 47: 12, 49: 1, 62: 0}
        self.assertEqual(pictures.record_slots(), {**common, 6: 24, 40: 25})
        self.assertEqual(crops.record_slots(), {**common, 5: 24, 36: 25})

    def test_a_picture_cursor_s_entry_and_slot(self):
        # Its pic2 where its pco lies, by the pco's entry and slot 17.
        cursor = slider.variant(self.cursors[0])
        self.assertEqual((cursor.attribute_place("pic2"), cursor.record_slots()[17]), (27, 27))
        self.assertNotIn(16, cursor.record_slots())

    def test_its_load_block_on_k_and_f(self):
        # K numbers the command 0x18 in table 4, and F 0x1d, where T has
        # 0x16. Its ID is written as on T. The block reads the series and
        # the slider's ID alone, so its place is a T probe's h0's.
        h0_place = place(_probe("slider-two"), "page0-1")
        for series, command in (("K", 0x18), ("F", 0x1D)):
            with self.subTest(series):
                h0 = page(slider_component(), series=series).objects[1]
                self.assertEqual(slider.variant(h0).load_start(h0, project_of(series=series),
                                                               h0_place, {}),
                                 [bytes([0x09, command, 0x04]) + b"1"])


class MatchedTest(unittest.TestCase):
    """The needs slider.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "slider"), Need("attribute", "slider.objname", b"h0"),
                   Need("attribute", "slider.val", (0).to_bytes(2, "little"),
                        context=bounds(0, 100)),
                   Need("attribute", "slider.val", (100).to_bytes(2, "little"),
                        context=bounds(0, 100)),
                   Need("attribute", "slider.val", (60000).to_bytes(2, "little"),
                        context=bounds(5, 60000)),
                   Need("attribute", "slider.maxval", (200).to_bytes(2, "little")),
                   Need("attribute", "slider.mode", b"\x01"),
                   Need("attribute", "slider.wid", b"\x00"),
                   Need("attribute", "slider.dis", b"\x00"),
                   Need("attribute", "slider.bco1", (2016).to_bytes(2, "little"))]
        self.assertEqual(unmatched(covered, slider.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A sta past 2 is left out. So is a psta of 2, a square cursor, which
        # nxwright's build refuses on T, K, and F, and a psta past 2 on P.
        left = [Need("attribute", "slider.sta", b"\x03"),
                Need("attribute", "slider.psta", b"\x02"),
                Need("attribute", "slider.psta", b"\x03", series="P")]
        self.assertEqual(unmatched(left, slider.MATCHED), left)

    def test_a_square_cursor_on_p_and_e(self):
        # A psta of 2, a square cursor of its pco's colour
        # (slider-of-a-square-cursor).
        taken = [Need("attribute", "slider.psta", b"\x02", series=series) for series in "PE"]
        self.assertEqual(unmatched(taken, slider.MATCHED), [])

    def test_bounds_inside_its_entries_whatever_its_val(self):
        # A val past its maxval, or below its minval; a minval above its val,
        # a maxval below it, and a minval above its maxval. The Nextion Editor
        # writes each as it is (slider-val-outside-its-bounds).
        taken = [Need("attribute", "slider.val", (101).to_bytes(2, "little"),
                      context=bounds(0, 100)),
                 Need("attribute", "slider.val", (5).to_bytes(2, "little"),
                      context=bounds(10, 200)),
                 Need("attribute", "slider.minval", (60).to_bytes(2, "little"),
                      context={"val": (50).to_bytes(2, "little")}),
                 Need("attribute", "slider.maxval", (40).to_bytes(2, "little"),
                      context={"val": (50).to_bytes(2, "little")}),
                 Need("attribute", "slider.minval", (300).to_bytes(2, "little"),
                      context={"maxval": (200).to_bytes(2, "little"),
                               "val": (250).to_bytes(2, "little")})]
        self.assertEqual(unmatched(taken, slider.MATCHED), [])
        # Bounds outside 0 to 65535, whatever its val.
        left = [Need("attribute", "slider.maxval", (70000).to_bytes(4, "little"),
                     context={"val": (50).to_bytes(2, "little")}),
                Need("attribute", "slider.minval", (-5).to_bytes(4, "little", signed=True),
                     context={"val": (50).to_bytes(2, "little")})]
        self.assertEqual(unmatched(left, slider.MATCHED), left)

    def test_the_needs_of_a_minval_above_its_val(self):
        # The needs the check reads from a page of a slider whose minval, 60,
        # lies above its val, 50, are each taken.
        project = project_of(page(slider_component(minval=60)), fonts=0)
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = project_of(page(slider_component(), series="K"), series="K", fonts=0)
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a slider's val, and any other attribute it writes. The
    encoder reads the page's components and program.s's variables."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page_of(_probe("slider-one")))

    def test_its_val(self):
        # h0's first entry is 33, and its val's entry 28 within the type.
        self.assertEqual(encode_line("h0.val=5", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x01" + struct.pack("<I", 61) + b"=5")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its maxval, entry 29 within the type,
        # after h0's first entry, 33; but not one it does not write.
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("h0.maxval=1", place, CompileContext(self.project)),
                         b"\x01" + (33 + 29).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "h0's txt is not encoded"):
            encode_line("h0.txt=1", place, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        # The needs of slider-val-in-code's page, its val in code.
        made = page_of(_probe("slider-val-in-code"), strict=True)
        self.assertEqual(unmatched(project_needs(project_of(made, strict=True, fonts=0)),
                                   matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, a slider's dis has an entry with a colour behind its track, and
    its ch is 100 at most (p_probes.py). Its values, its entries, and its
    load block are compared with the pieces of each probe of a slider on P,
    in PPiecesTest."""

    def test_its_entries_by_what_lies_behind_its_track(self):
        # As on T, but with a colour behind its track, its dis takes entry
        # 24, which T leaves empty. With a picture or a crop there, its dis
        # and ch have none.
        def names(sta: int) -> dict:
            return {entry: name for entry, (name, *_) in slider._of(sta, 0).P_ENTRIES.items()
                    if entry >= 19}
        self.assertEqual(names(1), {19: "mode", 20: "sta", 21: "psta", 22: "wid", 23: "hig",
                                    24: "dis", 25: "bco", 26: "bco1", 27: "pco", 28: "val",
                                    29: "maxval", 30: "minval", 31: "ch"})
        self.assertEqual(names(2), {19: "mode", 20: "sta", 21: "psta", 22: "wid", 23: "hig",
                                    24: "pic", 25: "pic1", 26: "pco", 27: "val", 28: "maxval",
                                    29: "minval"})

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "slider", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])

    def test_its_ch_is_written_as_it_is_on_p_and_e(self):
        # A ch past 100 is written as it is on every series, as long as it
        # fits in its byte.
        for series in ("T", "K", "P", "E"):
            with self.subTest(series):
                taken = [Need("attribute", "slider.ch", bytes([ch]), series=series)
                         for ch in (100, 101, 255)]
                self.assertEqual(unmatched(taken, slider.MATCHED), [])


if __name__ == "__main__":
    unittest.main()
