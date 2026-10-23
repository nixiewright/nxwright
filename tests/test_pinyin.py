"""The screen's pinyin table (testing/pinyin_table.py), and the two pinyin
commands the machine runs from it, pa_q and pa_txt (editor_machine.py), as
the Nextion Editor's simulator ran them.
The tables are the tests' own: the vendor's is never copied."""
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.project.stamp import CRC_START, word_crc
from nxwright.source.source_folder import new_source_folder
from nxwright.testing import EditorMachine, SourceFolderRunner, pinyin_table
from nxwright.testing.pinyin_table import PinyinTable, installed_pinyin_table, read_pinyin_table
from nxwright.testing.simulation import Simulation
from tests.test_live_debugging import LiveTestCase


def pairs(first: int, second: int, count: int) -> bytes:
    """`count` gb2312 characters, from the pair `first` `second` on."""
    return b"".join(bytes([first, second + index]) for index in range(count))


# Syllables and their candidates, as many as the screen's table holds for
# "mei", "m", and "lv". By key, they go ku, cou, tiao, mei, mian, m, lv.
SYLLABLES = {"ku": pairs(0xbf, 0xdd, 3), "cou": pairs(0xb4, 0xd5, 4),
             "tiao": pairs(0xcc, 0xf4, 8), "mei": pairs(0xc3, 0xa1, 26),
             "mian": pairs(0xc3, 0xe6, 15), "m": pairs(0xdf, 0xbc, 1),
             "lv": pairs(0xc2, 0xc0, 21)}
MEI, TIAO, MIAN = SYLLABLES["mei"], SYLLABLES["tiao"], SYLLABLES["mian"]


def table_bytes(syllables: dict, gap: int = 2) -> bytes:
    """A pinyin table of `syllables`, {syllable: its candidates}, laid out as
    the screen's: a row for each syllable, by increasing key, then `gap`
    bytes, then the candidates in the rows' order."""
    rows = sorted(syllables.items(), key=lambda item: word_crc(CRC_START, item[0].encode()))
    place = 8 * len(rows) + gap
    head, body = b"", b""
    for index, (syllable, candidates) in enumerate(rows):
        key = word_crc(CRC_START, syllable.encode())
        first = len(rows) if index == 0 else len(rows[index - 1][1])
        head += struct.pack("<HHHH", first, key & 0xffff, key >> 16, place + len(body))
        body += candidates
    return head + bytes(gap) + body


def tft_bytes(table: bytes, section: int = 0x10000) -> bytes:
    """A TFT file holding `table` as the first of its firmware parts, where
    the screen's pinyin table lies, the rest of it zeros."""
    data = bytearray(section + 0x90 + len(table) + 64)
    struct.pack_into("<I", data, 0x34, section)
    struct.pack_into("<III", data, section, 0x90, len(table), 0)
    data[section + 0x90:section + 0x90 + len(table)] = table
    return bytes(data)


TABLE = PinyinTable(table_bytes(SYLLABLES), "the test's table")


class PinyinTableTest(unittest.TestCase):

    def candidates(self, table: PinyinTable, syllable: bytes):
        place = table.place(syllable)
        return None if place is None else table.data[place[0]:place[1]]

    def test_a_syllables_candidates(self):
        for syllable, candidates in SYLLABLES.items():
            with self.subTest(syllable):
                self.assertEqual(self.candidates(TABLE, syllable.encode()), candidates)
        # The syllable is matched exactly.
        for syllable in (b"MEI", b"me", b"meii", b"", b"ni hao"):
            with self.subTest(syllable):
                self.assertIsNone(TABLE.place(syllable))

    def test_read_from_input_bin_or_a_tft_file(self):
        table = table_bytes(SYLLABLES)
        with tempfile.TemporaryDirectory() as folder:
            for name, data in (("input.bin", table), ("app.TFT", tft_bytes(table)),
                               ("p.tft", tft_bytes(table, 0x20000))):
                with self.subTest(name):
                    path = Path(folder) / name
                    path.write_bytes(data)
                    read = read_pinyin_table(path)
                    self.assertEqual(read.data, table)
                    self.assertEqual(self.candidates(read, b"mei"), MEI)

    def test_a_file_that_is_no_table_is_refused(self):
        table = table_bytes(SYLLABLES)
        unsorted = bytearray(table)
        unsorted[0:8], unsorted[8:16] = table[8:16], table[0:8]
        backwards = bytearray(table)
        struct.pack_into("<H", backwards, 8 + 6, 4)
        cases = {"short": (table[:6], "too short to be a pinyin table"),
                 "empty": (bytes(8) + table[8:], "it holds no rows"),
                 "rows": (table[:40], "its 7 rows run past its end"),
                 "keys": (bytes(unsorted), "its rows are not in the order of their keys"),
                 "places": (bytes(backwards), "row 1's candidates start before row 0's"),
                 "tft": (tft_bytes(table)[:0x10000], "holds no pinyin table where a TFT file "
                                                     "holds one")}
        with tempfile.TemporaryDirectory() as folder:
            for case, (data, message) in cases.items():
                with self.subTest(case):
                    path = Path(folder) / ("app.tft" if case == "tft" else "input.bin")
                    path.write_bytes(data)
                    with self.assertRaisesRegex(NxwrightError, message):
                        read_pinyin_table(path)
            with self.assertRaisesRegex(NxwrightError, "missing.bin"):
                read_pinyin_table(Path(folder) / "missing.bin")

    def test_the_installed_nextion_editors_table(self):
        with tempfile.TemporaryDirectory() as folder:
            with mock.patch.object(pinyin_table, "_installed_editor_folder",
                                   return_value=Path(folder)):
                self.assertIsNone(installed_pinyin_table())
                (Path(folder) / "input.bin").write_bytes(table_bytes(SYLLABLES))
                self.assertEqual(installed_pinyin_table(), Path(folder) / "input.bin")
            with mock.patch.object(pinyin_table, "_installed_editor_folder", return_value=None):
                self.assertIsNone(installed_pinyin_table())


def run(lines: list, encoding: str = "gb2312", table=TABLE, limit: int = 60) -> dict:
    """Runs `lines` on a machine of three texts, va0 and va1 of `limit`
    bytes and va3 of 3, and a number, va2."""
    values = {"va0.txt": "", "va1.txt": "", "va3.txt": "", "va2.val": 0,
              "text limits": {"va0.txt": limit, "va1.txt": limit, "va3.txt": 3}}
    return EditorMachine(values, encoding=encoding, pinyin_table=table).run(lines)


def stored(values: dict, name: str, encoding: str = "gb2312") -> bytes:
    """The bytes a text holds, as the screen stores it."""
    return values[name].encode(encoding, "surrogateescape")


class PinyinCommandTest(unittest.TestCase):

    def test_pa_q_counts_a_syllables_candidates(self):
        for pinyin, count in (('"mei"', 26), ('"m"', 1), ('"lv"', 21), ('"MEI"', 0),
                              ('"xyz"', 0), ('""', 0), ('"ni hao"', 0)):
            with self.subTest(pinyin):
                self.assertEqual(run(["pa_q %s,va2.val" % pinyin])["va2.val"], count)
        # The pinyin may be a text's txt.
        self.assertEqual(run(['va0.txt="mei"', "pa_q va0.txt,va2.val"])["va2.val"], 26)

    def test_pa_txt_gives_candidates_from_a_start(self):
        for start, count, expected in ((0, 5, MEI[:10]), (2, 3, MEI[4:10]), (24, 2, MEI[48:]),
                                       (25, 1, MEI[50:])):
            with self.subTest(start=start, count=count):
                values = run(['pa_txt "mei",va1.txt,%d,%d' % (start, count)])
                self.assertEqual(stored(values, "va1.txt"), expected)
        # Its numbers may be arithmetic, as other commands' may.
        values = run(["va2.val=2", 'pa_txt "mei",va1.txt,va2.val+1,va2.val'])
        self.assertEqual(stored(values, "va1.txt"), MEI[6:10])

    def test_pa_txt_empties_the_text_past_the_last_candidate(self):
        for line in ('pa_txt "mei",va1.txt,24,5', 'pa_txt "mei",va1.txt,26,1',
                     'pa_txt "mei",va1.txt,0,0', 'pa_txt "xyz",va1.txt,0,1'):
            with self.subTest(line):
                self.assertEqual(run(['va1.txt="ab"', line])["va1.txt"], "")

    def test_a_start_below_0_reads_before_the_syllables_candidates(self):
        # "tiao" comes before "mei" in the table: its last candidate shows.
        values = run(['pa_txt "mei",va1.txt,-1,2'])
        self.assertEqual(stored(values, "va1.txt"), TIAO[-2:] + MEI[:2])

    def test_a_count_below_0_copies_on_to_the_texts_limit(self):
        # Past "mei"'s candidates, into "mian"'s, which come next.
        values = run(['pa_txt "mei",va1.txt,1,-1'])
        self.assertEqual(stored(values, "va1.txt"), MEI[2:] + MIAN[:10])

    def test_a_start_and_a_count_summing_below_0_empty_the_text(self):
        # As the screen did: "lang" from 1 for -2, and "ku" from -2 for 1,
        # gave nothing, where from 1 for -1, and from -1 for 1, read.
        for line in ('pa_txt "mei",va1.txt,1,-2', 'pa_txt "mei",va1.txt,0,-1',
                     'pa_txt "mei",va1.txt,-2,1'):
            with self.subTest(line):
                self.assertEqual(run(['va1.txt="ab"', line])["va1.txt"], "")

    def test_a_read_starting_before_the_tables_first_byte_is_empty(self):
        # "ku"'s candidates come first. Starting 2 bytes before the table's
        # first byte, the screen read nothing, though start and count sum to 0.
        before = -(TABLE.place(b"ku")[0] // 2) - 1
        values = run(['va1.txt="ab"', 'pa_txt "ku",va1.txt,%d,%d' % (before, -before)])
        self.assertEqual(values["va1.txt"], "")

    def test_the_text_is_cut_to_its_limit_within_a_character(self):
        values = run(['pa_txt "mei",va3.txt,0,5'])
        self.assertEqual(stored(values, "va3.txt"), MEI[:3])

    def test_the_candidates_are_gb2312_bytes_in_any_encoding(self):
        values = run(['pa_txt "mei",va1.txt,0,2'], encoding="utf-8")
        self.assertEqual(stored(values, "va1.txt", "utf-8"), MEI[:4])

    def test_without_a_table_the_commands_are_recorded(self):
        values = run(["pa_q \"mei\",va2.val", 'pa_txt "mei",va1.txt,0,2'], table=None)
        self.assertEqual(values["other commands"],
                         [("pa_q", '"mei"', "va2.val"), ("pa_txt", '"mei"', "va1.txt", "0", "2")])
        self.assertEqual((values["va2.val"], values["va1.txt"]), (0, ""))

    def test_a_path_is_read_as_a_table(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.bin"
            path.write_bytes(table_bytes(SYLLABLES))
            self.assertEqual(run(['pa_q "lv",va2.val'], table=path)["va2.val"], 21)


class PinyinInAFolderTest(unittest.TestCase):
    """A source folder's code, run by its tests and by the simulator."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name) / "app"
        new_source_folder(self.root, DeviceSettings(model_named("NX4832T035"), 0, "gb2312"),
                          "nextion")
        (self.root / "program.nx").write_text(
            'int sys0=0,sys1=0,sys2=0\npa_q "mei",sys0\npa_q "lv",sys1\npage 0\n',
            encoding="utf-8", newline="\n")
        (self.root / "pages" / "page0.nx").write_text(
            'on page0.down:\n  pa_q "lv",sys2\n', encoding="utf-8", newline="\n")
        self.table = Path(self._folder.name) / "input.bin"
        self.table.write_bytes(table_bytes(SYLLABLES))

    def tearDown(self):
        self._folder.cleanup()

    def test_a_test_runs_them_with_the_table_it_gives(self):
        runner = SourceFolderRunner(self.root, pinyin_table=self.table)
        self.assertEqual(runner.run("page0", [("page0", "down")])["sys2"], 21)
        values = SourceFolderRunner(self.root).run("page0", [("page0", "down")])
        self.assertEqual((values["sys2"], values["other commands"]),
                         (0, [("pa_q", '"lv"', "sys2")]))

    def test_the_simulator_runs_them_with_a_table(self):
        simulation = Simulation(self.root, pinyin_table=self.table)
        self.assertEqual((simulation.globals["sys0"], simulation.globals["sys1"]), (26, 21))
        self.assertFalse(any("pinyin" in line for _, line in simulation.log))

    def test_without_a_table_the_simulator_says_so_once(self):
        simulation = Simulation(self.root)
        self.assertEqual((simulation.globals["sys0"], simulation.globals["sys1"]), (0, 0))
        notes = [line for _, line in simulation.log if "pinyin table" in line]
        self.assertEqual(notes, ["pa_q: no pinyin table was found, so Chinese input shows no "
                                 "candidates. To give one, set the launch configuration's "
                                 "pinyinTable, or the setting nxwright.simulator.pinyinTable, to "
                                 "the Nextion Editor's input.bin or to a TFT file."])

    def test_a_file_that_is_no_table_stops_the_simulation(self):
        self.table.write_bytes(b"no table")
        with self.assertRaisesRegex(NxwrightError, "is no pinyin table"):
            Simulation(self.root, pinyin_table=self.table)


class PinyinLaunchTest(LiveTestCase):
    """The pinyin table of a simulation VS Code launches (debug_adapter)."""

    def setUp(self):
        super().setUp()
        self.table = self.root.parent / "input.bin"
        self.table.write_bytes(table_bytes(SYLLABLES))
        # No test finds the Nextion Editor this computer may have.
        installed = mock.patch("nxwright.debug_adapter.adapter.installed_pinyin_table",
                               return_value=None)
        self.installed = installed.start()
        self.addCleanup(installed.stop)

    def count_after_pa_q(self) -> str:
        """What `get count` sends once `pa_q "mei",count` ran, typed."""
        self.wait_for("nxwright/drawing")
        self.request("nxwright/serial", text='pa_q "mei",count')
        self.request("nxwright/serial", text="get count")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            lines = [line for body in self.events("output") if body["category"] == "stdout"
                     for line in body["output"].splitlines() if " sends 71 " in line]
            if lines:
                return lines[-1].split(" sends ", 1)[1]
            time.sleep(0.01)
        self.fail("get count sent nothing")

    def test_the_table_the_launch_names(self):
        self.launch(pinyinTable=str(self.table))
        self.assertEqual(self.count_after_pa_q(), "71 1a 00 00 00 ff ff ff (get)")

    def test_the_installed_nextion_editors_table(self):
        self.installed.return_value = self.table
        self.launch()
        self.assertEqual(self.count_after_pa_q(), "71 1a 00 00 00 ff ff ff (get)")

    def test_a_named_file_that_is_no_table_stops_the_launch(self):
        self.table.write_bytes(b"no table")
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), pinyinTable=str(self.table))
        self.assertFalse(reply["success"])
        self.assertIn("is no pinyin table", reply["message"])

    def test_an_installed_table_not_read_is_said(self):
        self.table.write_bytes(b"no table")
        self.installed.return_value = self.table
        self.launch()
        self.assertEqual(self.count_after_pa_q(), "71 00 00 00 00 ff ff ff (get)")
        console = "".join(body["output"] for body in self.events("output")
                          if body["category"] == "console")
        self.assertIn("The Nextion Editor's pinyin table was not read: ", console)
