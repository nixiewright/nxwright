"""What the screen keeps of a number code stores in an attribute, as the
Nextion Editor's simulator kept it: refused outside the attribute's
range, answering 0x1C and keeping its value, or, for a few attributes,
cut to their bytes (project/attribute_descriptions.toml, `code_range`
and `code_wraps`; testing/editor_machine.py, _store).

fixtures/stored-numbers/ holds what that probe read back, on an
NX8048P050, from one component of each type, c0 to c27, at its defaults
(components.json gives their types). Event code stored numbers in each
number attribute code can change, read each back, and wrote what it read
to a file on the SD card, each as "c3.dis 300=25 ":
  - round1-<n>.txt: -1, 300, and 200 in an attribute of 1 byte; -1,
    70000, and 40000 in one of 2 bytes; -1 in one of 4;
  - ladder-<n>.txt: a ladder of values in each that refused all three;
  - edges-<n>.txt: the tops of the others, and each edge the ladder left
    open walked across, as "c9.left walk1001..9999=1024 ": the last value
    read back unchanged, -99999 for none.
"""
import json
from pathlib import Path
import re
import unittest

from nxwright.project.attribute_descriptions import COMMON, WRAPS, _tables, describe, type_has
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_text import expected_width
from nxwright.testing.simulation import Simulation
from nxwright.testing.source_runner import SourceFolderRunner
from tests.test_simulation import SimulationTestCase, placed, table

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "stored-numbers"
# The probe's attributes that take no code_range, though the screen did not
# keep every number in them: what each holds is checked otherwise. Of them,
# one that wraps, as a sliding text's `font`, names nothing the screen checks.
CHECKED_OTHERWISE = {
    # The number of a picture, a font, or a media file the project has.
    "font": "a resource", "pic": "a resource", "picc": "a resource", "pic1": "a resource",
    "vid": "a resource",
}
# Of one type: a range that follows another of its values, as the test
# machine works it out; and an edge the probe left unpinned.
CHECKED_OTHERWISE_BY_TYPE = {
    ("combo-box", "val"): "follows its items", ("select", "val"): "follows its lines",
    ("gauge", "up"): "unpinned", ("gauge", "down"): "unpinned",
    ("scrolling-text", "tim"): "unpinned",
}
_READ = re.compile(r"(c\d+)\.(\w+) (-?\d+|walk-?\d+\.\.-?\d+)=(-?\d+)")


def probe_reads() -> list:
    """[(type, attribute, what was stored, what was read)] of every file,
    the stored a number, or "walk<from>..<to>"."""
    types = json.loads((FIXTURES / "components.json").read_text(encoding="utf-8"))
    reads = []
    for path in sorted(FIXTURES.glob("*.txt")):
        text = path.read_bytes().split(b"\0", 1)[0].decode("latin-1")
        for component, attribute, stored, read in _READ.findall(text):
            reads.append((types[component], attribute, stored, int(read)))
    return reads


def cut(value: int, wraps: str) -> int:
    bits, signed = WRAPS[wraps]
    value %= 2 ** bits
    return value - 2 ** bits if signed and value >= 2 ** (bits - 1) else value


def expected_walk(start: int, stop: int, low: int, high: int) -> int:
    """The last value a walk from `start` to `stop`, both included, reads
    back unchanged, given the range from `low` to `high`; -99999 for none."""
    if start <= stop:
        first, last = max(start, low), min(stop, high)
        return last if first <= last else -99999
    first, last = min(start, high), max(stop, low)
    return last if first >= last else -99999


class TableTest(unittest.TestCase):

    def test_the_descriptions_follow_the_probe(self):
        reads = probe_reads()
        self.assertGreater(len(reads), 2000)
        for type_name, attribute, stored, read in reads:
            described = describe(type_name, attribute)
            if ((attribute in CHECKED_OTHERWISE and described.code_wraps is None)
                    or (type_name, attribute) in CHECKED_OTHERWISE_BY_TYPE):
                continue
            with self.subTest(type=type_name, attribute=attribute, stored=stored):
                if attribute == "move":
                    # x read after a move of no time to there, which no range refuses.
                    self.assertEqual(read, int(stored))
                elif stored.startswith("walk"):
                    start, stop = map(int, stored[4:].split(".."))
                    self.assertEqual(read, expected_walk(start, stop, *described.code_range))
                elif described.code_wraps is not None:
                    self.assertEqual(read, cut(int(stored), described.code_wraps))
                elif described.code_range is not None:
                    low, high = described.code_range
                    if low <= int(stored) <= high:
                        self.assertEqual(read, int(stored))
                    else:
                        self.assertNotEqual(read, int(stored))
                else:
                    self.assertEqual(read, int(stored))

    def test_each_entry_names_an_attribute_and_fits_it(self):
        for type_name, entries in _tables().items():
            for attribute, entry in entries.items():
                if "code_range" not in entry and "code_wraps" not in entry:
                    continue
                with self.subTest(type=type_name, attribute=attribute):
                    self.assertFalse("code_range" in entry and "code_wraps" in entry)
                    if "description" not in entry:
                        # It takes the common entry's words, which must be there.
                        self.assertIn(attribute, _tables()[COMMON])
                    types = list(TYPES_BY_NAME) if type_name == COMMON else [type_name]
                    having = [kind for kind in types if type_has(kind, attribute)]
                    self.assertTrue(having)
                    if "code_range" in entry:
                        low, high = entry["code_range"]
                        self.assertLessEqual(low, high)
                    else:
                        bits = WRAPS[entry["code_wraps"]][0]
                        for kind in having:
                            self.assertLessEqual(
                                bits, 8 * expected_width(TYPES_BY_NAME[kind], attribute))

    def test_an_entry_of_only_its_range_takes_the_common_words(self):
        # A sliding text's xcen wraps, where other types' refuse past 2;
        # its description is the common one.
        own, common = describe("sliding-text", "xcen"), describe("text", "xcen")
        self.assertEqual((own.description, own.code_wraps, own.code_range),
                         (common.description, "u8", None))
        self.assertEqual(common.code_range, (0, 2))


class StoredNumberTest(SimulationTestCase):
    """Stores the probe tried, typed with bkcmd 3, answered as the Nextion
    Editor's simulator answered them: 0x1C, the value kept, for one
    refused; 0x01 for one taken or cut."""

    def setUp(self):
        super().setUp()
        self.program("bkcmd=3\npage page0\n")
        self.page("page0", [placed("t0", "text", 0, 0, txt="x", txt_maxl=20),
                            placed("n0", "number", 0, 60),
                            placed("h0", "slider", 0, 120),
                            placed("g0", "scrolling-text", 0, 180),
                            placed("s0", "sliding-text", 0, 240),
                            placed("fb0", "file-browser", 200, 0),
                            placed("gm0", "gmov", 200, 300),
                            placed("b0", "button", 400, 0)],
                  "on b0.down:\n  t0.aph=200\n  n0.val=5\n")

    def answer(self, text: str) -> tuple:
        """Types `text` into a new simulation; returns what it sent, in
        hexadecimal, and its values."""
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        sent.clear()
        simulation.serial_input(text)
        return [data.hex(" ") for data in sent], simulation.values()

    def test_a_number_outside_the_range_is_refused(self):
        for text, name, kept in (("t0.aph=200", "t0.aph", 127), ("t0.xcen=5", "t0.xcen", 1),
                                 ("t0.x=7000", "t0.x", 0), ("t0.pco=65536", "t0.pco", 0)):
            with self.subTest(text):
                sent, values = self.answer(text)
                self.assertEqual((sent, values[name]), (["1c ff ff ff"], kept))

    def test_a_number_inside_the_range_is_taken(self):
        for text, name, value in (("t0.aph=127", "t0.aph", 127), ("t0.x=-6000", "t0.x", -6000),
                                  ("t0.pco=65535", "t0.pco", 65535)):
            with self.subTest(text):
                sent, values = self.answer(text)
                self.assertEqual((sent, values[name]), (["01 ff ff ff"], value))

    def test_a_number_that_wraps_is_cut(self):
        for text, name, value in (("h0.val=-1", "h0.val", 65535),
                                  ("g0.vvs0=40000", "g0.vvs0", -25536),
                                  ("s0.xcen=300", "s0.xcen", 44),
                                  ("fb0.pic2=70000", "fb0.pic2", 112)):
            with self.subTest(text):
                sent, values = self.answer(text)
                self.assertEqual((sent, values[name]), (["01 ff ff ff"], value))

    def test_four_bytes_keep_any_number(self):
        sent, values = self.answer("n0.val=-1")
        self.assertEqual((sent, values["n0.val"]), (["01 ff ff ff"], -1))

    def test_a_move_of_no_time_is_taken_past_the_range(self):
        # As the Nextion Editor's simulator placed a text at x 7000.
        sent, values = self.answer("move t0,0,0,7000,0,0,0")
        self.assertEqual(values["t0.x"], 7000)

    def test_a_vid_the_project_lacks_is_refused(self):
        sent, values = self.answer("gm0.vid=3")
        self.assertEqual(sent, ["1c ff ff ff"])

    def test_a_test_records_the_refusal(self):
        # The store changes nothing, and the event goes on.
        values = SourceFolderRunner(self.root).run("page0", [("b0", "down")])
        self.assertEqual(("t0.aph" in values, values["n0.val"]), (False, 5))
        self.assertIn((0x1C, "t0.aph=200"), values["refusals"])


if __name__ == "__main__":
    unittest.main()
