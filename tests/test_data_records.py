"""Data records: their data files (testing/data_files.py), their methods in
the test machine (testing/editor_machine.py), and their drawing
(drawing/data_record_drawing.py), against the files the Editor's simulator
wrote and the pictures it showed (fixtures/data-record/, whose readings.toml
says what each holds), in the font NotoSans20."""
import functools
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.drawing.data_record_drawing import UNOPENED, record_at, table_layout
from nxwright.drawing.page_drawing import draw_page, inside_box
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.pictures import read_picture
from nxwright.project.screen_colours import rgb565_to_hex
from nxwright.project.truetype import noto_sans
from nxwright.project.zi_font import decode_font
from nxwright.source.page_source import Component
from nxwright.testing.data_files import DataFile
from nxwright.testing.editor_machine import EditorMachine, RefusedCode
from nxwright.testing.sd_cards import FolderCards
from tests.test_page_drawing import differing_pixels
from tests.test_scrolling_texts import ProbeFont, probe_components

FOLDER = Path(__file__).resolve().parent / "fixtures" / "data-record"
READINGS = tomllib.loads((FOLDER / "readings.toml").read_text(encoding="utf-8"))
FILES = ["cleared.data", "three.data", "ring.data", "fields.data", "small.data", "most1256.data"]
# The records looks.page.toml's data records held.
EIGHT = ["r%d^%d^n%d" % (number, number, number) for number in range(8)]


class NotoSans24(ProbeFont):
    """The resources of the probe of data records naming one file: its
    folder's one font, NotoSans24, which nxwright draws from Noto Sans as it
    draws a new folder's."""

    def font(self, font_id):
        return _noto_sans_24()


@functools.cache
def _noto_sans_24():
    return decode_font(draw_font_block("NotoSans24", noto_sans(), 24, "iso-8859-1", 0))


def records_of(file: str) -> list:
    """The records of one of the Editor's data files, as texts, the oldest first."""
    return [record.decode("latin-1")
            for record in DataFile.read((FOLDER / file).read_bytes()).records()]


def replayed(lenth: int, dez: int, maxval: int, calls: list) -> bytes:
    """A new data file's bytes after `calls`, (method, arguments) in turn."""
    data_file = DataFile.new(lenth, dez, maxval)
    for method, *arguments in calls:
        getattr(data_file, method)(*arguments)
    return data_file.to_bytes()


class DataFileTest(unittest.TestCase):

    def test_the_editors_files_read_and_write_back_byte_for_byte(self):
        for file in FILES:
            with self.subTest(file=file):
                data = (FOLDER / file).read_bytes()
                self.assertEqual(DataFile.read(data).to_bytes(), data)

    def test_the_editors_calls_replayed_write_its_files(self):
        cases = {
            "three.data": replayed(63, 3, 1000, [("insert", b"a^1^x"), ("insert", b"b^2^y"),
                                                 ("insert", b"c^3^z")]),
            # Deleting moves the records down, leaving the last slot as it was;
            # clearing leaves every slot as it was.
            "cleared.data": replayed(63, 3, 1000, [
                ("insert", b"one^1^first"), ("insert", b"two^2^second"),
                ("insert", b"one^1^first"), ("update", b"upd^9^changed", 0),
                ("delete", 0, 1), ("clear",)]),
            # Past `maxval`, a new record takes the oldest one's slot.
            "ring.data": replayed(63, 3, 3, [("insert", text) for text in
                                             (b"a^1^x", b"b^2^y", b"c^3^z", b"d^4^w", b"e^5^v")]),
            "fields.data": replayed(63, 2, 1000, [("insert", b"a^b^c"), ("insert", b"one^two")]),
            "small.data": replayed(31, 2, 10, []),
            "most1256.data": replayed(63, 3, 1256, []),
        }
        for file, data in cases.items():
            with self.subTest(file=file):
                self.assertEqual(data, (FOLDER / file).read_bytes())

    def test_the_records_the_oldest_first(self):
        self.assertEqual(records_of("ring.data"), ["c^3^z", "d^4^w", "e^5^v"])

    def test_what_changes_nothing(self):
        data_file = DataFile.new(7, 3, 1000)
        # A record longer than `lenth` bytes is refused, not cut.
        self.assertEqual((data_file.insert(b"ab^cd^ef"), data_file.insert(b"a^b^c")),
                         (False, True))
        self.assertFalse(data_file.delete(1, 1))
        self.assertFalse(data_file.update(b"x", 1))
        self.assertEqual(data_file.records(), [b"a^b^c"])

    def test_a_delete_past_the_last_record_deletes_none(self):
        # As the Nextion Editor's simulator ran it, on five records:
        # delete(1,5) and delete(3,3) deleted none, and delete(1,4), which
        # ends at the last, deleted four. A count of 0 deleted none. A count
        # below 0 added that many records at `number` there instead, which is
        # not followed: it changes nothing here.
        data_file = DataFile.new(7, 3, 1000)
        for text in (b"a^1^1", b"b^2^2", b"c^3^3", b"d^4^4", b"e^5^5"):
            data_file.insert(text)
        for number, count in ((1, 5), (3, 3), (0, 0), (0, -1)):
            with self.subTest(number=number, count=count):
                self.assertFalse(data_file.delete(number, count))
                self.assertEqual(len(data_file.records()), 5)
        self.assertTrue(data_file.delete(1, 4))
        self.assertEqual(data_file.records(), [b"a^1^1"])

    def test_a_header_that_does_not_check_is_refused(self):
        damaged = bytearray((FOLDER / "three.data").read_bytes())
        damaged[8] = 2          # the count, its check word not following
        with self.assertRaises(NxwrightError):
            DataFile.read(bytes(damaged))


class MachineTest(unittest.TestCase):
    """The methods code calls, as calls.page.toml's buttons called them."""

    def setUp(self):
        d0 = next(component for component in probe_components(FOLDER / "calls.page.toml")
                  if component.name == "d0")
        self.values = {"d0." + key: value for key, value in d0.values.items()}
        # A page file stores `val` -1 as its 32 bits; a simulation starts it at -1.
        self.values["d0.val"] = -1

    def run_lines(self, machine: EditorMachine, lines: list):
        machine.run(lines)
        return machine.values["d0.qty"], machine.values["d0.val"], machine.values["d0.txt"]

    def test_as_the_editors_simulator_ran_them(self):
        machine = EditorMachine(self.values)
        # The buttons' code, and code choosing the record the tap chose.
        steps = [['d0.insert("one^1^first")'], ['d0.insert("two^2^second")'],
                 ['d0.insert("one^1^first")'], ["d0.val=1"], ["d0.val=1"],
                 ['d0.up("upd^9^changed",0)'], ["d0.delete(0,1)"], ["d0.clear()"]]
        for lines, reading in zip(steps, READINGS["calls"]):
            with self.subTest(lines=lines):
                self.assertEqual(self.run_lines(machine, lines),
                                 (reading["qty"], reading["val"], reading["txt"]))
        self.assertEqual(machine.values["file contents"][self.values["d0.path"]],
                         (FOLDER / "cleared.data").read_bytes())
        self.assertEqual([command for command, _ in machine.values["file commands"]],
                         ["insert", "insert", "insert", "up", "delete", "clear"])

    def test_a_number_past_the_last_changes_nothing(self):
        reading = READINGS["ring"]
        self.values["d0.maxval"] = 3
        machine = EditorMachine(self.values)
        lines = ['d0.insert("%s^%d^%s")' % record for record in
                 (("a", 1, "x"), ("b", 2, "y"), ("c", 3, "z"), ("d", 4, "w"), ("e", 5, "v"))]
        self.assertEqual(self.run_lines(machine, lines + ["d0.val=1"]),
                         (reading["qty"], reading["val"], reading["txt"]))
        self.assertEqual(self.run_lines(machine, ["d0.val=9", "d0.delete(5,1)",
                                                  'd0.up("zz^9^q",9)']),
                         (reading["qty"], reading["val"], reading["txt"]))
        self.assertEqual([command for command, _ in machine.values["file errors"]],
                         ["delete", "up"])

    def test_a_missing_file_with_mode_0_is_not_made(self):
        self.values["d0.mode"] = 0
        machine = EditorMachine(self.values)
        self.assertEqual(self.run_lines(machine, ['d0.insert("a")']), (0, -1, ""))
        self.assertEqual(machine.values["file errors"], [("insert", self.values["d0.path"])])
        self.assertNotIn(self.values["d0.path"], machine.values.get("file contents", {}))

    def test_on_a_card_given_a_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            machine = EditorMachine(self.values, cards=FolderCards({"sd0/": folder}))
            machine.run(['d0.insert("a^1^x")', 'd0.insert("b^2^y")', 'd0.insert("c^3^z")'])
            written = Path(folder) / self.values["d0.path"][len("sd0/"):]
            self.assertEqual(written.read_bytes(), (FOLDER / "three.data").read_bytes())

    def on_a_held_card(self, refusing: str, lines: list):
        """Runs `lines` on a card's folder holding three.data, its cards'
        `refusing` raising OSError, as a file another program holds would.
        Returns the machine and the file's bytes afterwards."""
        with tempfile.TemporaryDirectory() as folder:
            written = Path(folder) / self.values["d0.path"][len("sd0/"):]
            written.write_bytes((FOLDER / "three.data").read_bytes())
            machine = EditorMachine(self.values, cards=FolderCards({"sd0/": folder}))
            with mock.patch.object(FolderCards, refusing, side_effect=OSError("held")):
                machine.run(lines)
            return machine, written.read_bytes()

    def test_a_file_the_folder_will_not_give_is_not_made_anew(self):
        machine, data = self.on_a_held_card("read", ['d0.insert("d^4^w")'])
        self.assertEqual(data, (FOLDER / "three.data").read_bytes())
        path = self.values["d0.path"]
        self.assertEqual(machine.values["file errors"], [("read", path), ("insert", path)])

    def test_a_file_the_folder_will_not_take_changes_nothing(self):
        machine, data = self.on_a_held_card("write", ['d0.insert("d^4^w")'])
        self.assertEqual(data, (FOLDER / "three.data").read_bytes())
        self.assertEqual(machine.values["d0.qty"], self.values["d0.qty"])
        self.assertEqual(machine.values["file errors"], [("insert", self.values["d0.path"])])
        self.assertNotIn("file commands", machine.values)

    def test_the_calls_the_editor_refuses(self):
        # As it compiles: a missing or extra argument, a text where a
        # number goes, quoted or a text attribute, and texts joined.
        values = dict(self.values, **{"t0.txt": "a^1^x", "t1.txt": "b", "n0.val": 0})
        for line in ("d0.delete(0)", "d0.up(0)", 'd0.up(0,"text")', "d0.insert()",
                     "d0.clear(1)", 'd0.delete("a",1)', "d0.up(t0.txt,t1.txt)",
                     'd0.insert(t0.txt+"^"+t1.txt)'):
            with self.subTest(line=line), self.assertRaises(RefusedCode):
                EditorMachine(dict(values)).run([line])

    def test_a_number_where_a_text_goes_adds_nothing(self):
        # The Editor compiles it; the screen adds no record, and says nothing.
        machine = EditorMachine(dict(self.values, **{"n0.val": 0}))
        self.assertEqual(self.run_lines(machine, ["d0.insert(n0.val)", "d0.insert(5)"]),
                         (0, -1, ""))
        self.assertEqual([command for command, _ in machine.values["file errors"]],
                         ["insert", "insert"])

    def test_at_init_1_no_file_until_code_sets_its_path(self):
        # As the Nextion Editor's simulator ran it: each method counts as
        # done, and changes nothing. Once code sets `path`, even to the same
        # file, the record works as at 0.
        self.values["d0.init"] = 1
        path = self.values["d0.path"]
        machine = EditorMachine(self.values)
        self.assertEqual(self.run_lines(machine, ['d0.insert("a^1^x")', 'd0.up("b^2^y",0)',
                                                  "d0.delete(0,1)", "d0.clear()"]),
                         (0, -1, ""))
        self.assertNotIn(path, machine.values.get("file contents", {}))
        self.assertNotIn("file errors", machine.values)
        self.assertNotIn("file commands", machine.values)
        self.assertEqual(self.run_lines(machine, ['d0.path="%s"' % path, 'd0.insert("a^1^x")']),
                         (1, -1, ""))

    def test_a_text_from_a_variable(self):
        machine = EditorMachine(dict(self.values, **{"t0.txt": "a^1^x"}))
        self.assertEqual(self.run_lines(machine, ["d0.insert(t0.txt)", "d0.val=0"]),
                         (1, 0, "a^1^x"))

    def test_the_scroll_follows_the_records(self):
        # Eight records in each of looks.page.toml's data records.
        for record in probe_components(FOLDER / "looks.page.toml"):
            if record.type != "data-record":
                continue
            name = record.name
            machine = EditorMachine(dict({"%s.%s" % (name, key): value
                                          for key, value in record.values.items()},
                                         **{name + ".val": -1}))
            machine.run(['%s.insert("%s")' % (name, text) for text in EIGHT])
            for attribute, readings in READINGS["looks"].items():
                if name in readings:
                    with self.subTest(record=name, attribute=attribute):
                        self.assertEqual(machine.values["%s.%s" % (name, attribute)],
                                         readings[name])


class SharedFileTest(unittest.TestCase):
    """Two data records naming one file: the first to open it holds it, until
    code changes its `path`."""

    def setUp(self):
        d0 = next(component for component in probe_components(FOLDER / "calls.page.toml")
                  if component.name == "d0")
        self.values = {}
        for name in ("d0", "d1"):
            self.values.update({"%s.%s" % (name, key): value for key, value in d0.values.items()})
            self.values[name + ".val"] = -1
        self.path = self.values["d0.path"]

    def records(self, machine: EditorMachine, path: str = None) -> list:
        data = machine.values["file contents"][path or self.path]
        return [record.decode("latin-1") for record in DataFile.read(data).records()]

    def test_a_method_of_a_record_another_holds_the_file_of(self):
        # It changes nothing, and counts as done.
        machine = EditorMachine(self.values)
        machine.run(['d0.insert("a^1^x")', 'd1.insert("b^2^y")'])
        self.assertEqual((machine.values["d0.qty"], machine.values["d1.qty"]), (1, 0))
        self.assertEqual(self.records(machine), ["a^1^x"])
        self.assertNotIn("file errors", machine.values)

    def test_a_new_path_lets_the_file_go(self):
        # d1's insert then opens it, d0's record in it.
        machine = EditorMachine(self.values)
        machine.run(['d0.insert("a^1^x")', 'd0.path="sd0/other.data"', 'd1.insert("c^3^z")'])
        self.assertEqual((machine.values["d1.qty"], self.records(machine)),
                         (2, ["a^1^x", "c^3^z"]))

    def test_the_holder_given_its_own_file_again(self):
        # It lets the file go, finds it free, and holds it again.
        machine = EditorMachine(self.values)
        machine.run(['d0.insert("a^1^x")', 'd0.path="%s"' % self.path, 'd1.insert("b^2^y")'])
        self.assertEqual((machine.values["d0.qty"], machine.values["d1.qty"]), (1, 0))

    def test_a_path_naming_a_file_another_holds(self):
        # 0x06, and nothing opened.
        self.values["d1.path"] = "sd0/own.data"
        screen = mock.Mock(asleep=False)
        machine = EditorMachine(self.values, screen=screen)
        machine.run(['d0.insert("a^1^x")', 'd1.insert("b^2^y")', 'd1.path="%s"' % self.path])
        # Run as event code, as a test's lines are.
        self.assertEqual(screen.refused.call_args_list, [mock.call(0x06, False)])
        values = machine.values
        self.assertEqual((values["d1.qty"], values["d1.val"], values["d1.txt"],
                          values["d1.maxval_y"], values["file errors"]),
                         (0, -1, "", 0, [("open", self.path)]))
        self.assertEqual(self.records(machine, "sd0/own.data"), ["b^2^y"])

    def test_an_empty_path_is_held_by_none(self):
        # Assumed: records whose path code has yet to set shut no one out.
        self.values["d0.path"] = self.values["d1.path"] = ""
        machine = EditorMachine(self.values)
        machine.run(['d0.insert("a^1^x")', 'd1.insert("b^2^y")'])
        self.assertEqual((machine.values["d1.qty"], machine.values.get("data files held", {})),
                         (2, {}))

    def test_two_spellings_of_one_file_on_a_card_given_a_folder(self):
        # The card's name in capitals is the same card, and so the same file.
        self.values["d1.path"] = "SD0/" + self.path[len("sd0/"):]
        with tempfile.TemporaryDirectory() as folder:
            machine = EditorMachine(self.values, cards=FolderCards({"sd0/": folder}))
            machine.run(['d0.insert("a^1^x")', 'd1.insert("b^2^y")'])
        self.assertEqual((machine.values["d0.qty"], machine.values["d1.qty"]), (1, 0))


class MostFilesHeldTest(unittest.TestCase):
    """Data records each naming a file of its own: at most 8 files are held at
    once. A record finding 8 held by others is shut out, as if its file were
    held (test_simulation.py for their pages opening)."""

    def setUp(self):
        d0 = next(component for component in probe_components(FOLDER / "calls.page.toml")
                  if component.name == "d0")
        self.values = {}
        for place in range(10):
            name = "d%d" % place
            self.values.update({"%s.%s" % (name, key): value for key, value in d0.values.items()})
            self.values.update({name + ".val": -1, name + ".path": "sd0/%s.data" % name})

    def eight_held(self, screen=None) -> EditorMachine:
        """A machine whose d0 to d7 hold their files, a record in each."""
        machine = EditorMachine(self.values, screen=screen)
        machine.run(['d%d.insert("a^1^x")' % place for place in range(8)])
        return machine

    def test_a_method_of_a_record_past_the_eighth_file(self):
        # It changes nothing, and counts as done.
        machine = self.eight_held()
        machine.run(['d8.insert("b^2^y")'])
        self.assertEqual(machine.values["d8.qty"], 0)
        self.assertNotIn("sd0/d8.data", machine.values["file contents"])
        self.assertNotIn("file errors", machine.values)

    def test_a_place_a_new_path_frees(self):
        # d8's next method opens its file, and d9 then finds 8 held.
        machine = self.eight_held()
        machine.run(['d8.insert("b^2^y")', 'd0.path=""', 'd8.insert("c^3^z")',
                     'd9.insert("d^4^w")'])
        self.assertEqual((machine.values["d8.qty"], machine.values["d9.qty"]), (1, 0))

    def test_a_holder_given_a_new_path(self):
        # It lets its file go first, so it opens the new one.
        machine = self.eight_held()
        machine.run(['d0.path="sd0/new.data"', 'd0.insert("b^2^y")'])
        self.assertEqual(machine.values["d0.qty"], 1)

    def test_a_path_set_past_the_eighth_file(self):
        # 0x06, and nothing opened; none for an empty path, which opens nothing.
        screen = mock.Mock(asleep=False)
        machine = self.eight_held(screen)
        machine.run(['d8.path="sd0/new.data"', 'd9.path=""'])
        self.assertEqual(screen.refused.call_args_list, [mock.call(0x06, False)])
        self.assertEqual(machine.values["file errors"], [("open", "sd0/new.data")])


class TableScrollTest(unittest.TestCase):
    """How far a table scrolls, as the Editor's simulator gave it for a data
    record as looks.page.toml's da, holding eight records."""

    def setUp(self):
        self.page, self.da = probe_components(FOLDER / "looks.page.toml")[:2]

    def test_the_last_columns_line_counts_across(self):
        # Columns 600 wide inside 378 scrolled 223, and 225 with `gdh` 3;
        # db's 222 has `gdh` 0 (readings.toml).
        for gdh, most in ((1, 223), (3, 225), (0, 222)):
            values = dict(self.da.values, format="200^200^200", gdh=gdh)
            with self.subTest(gdh=gdh):
                self.assertEqual(table_layout(values, 8, inside_box(values)).most_x, most)

    def test_code_may_scroll_the_records_32_pixels_further(self):
        # The Editor's simulator drew da's records scrolled to 173, 32 past
        # its `maxval_y` of 141: the line under the last record 32 pixels up.
        grid = rgb565_to_hex(self.da.values.get("gdc", 50712))

        def last_line(scrolled: int) -> int:
            da = Component(self.da.name, self.da.type, dict(self.da.values, val_y=scrolled))
            shapes = draw_page([self.page, da], ProbeFont(), listings={"da": EIGHT})["shapes"]
            return max(shape["y"] for shape in shapes if shape["component"] == "da"
                       and shape.get("colour") == grid and shape["w"] > 1)
        self.assertEqual(last_line(141 + 32), last_line(141) - 32)


class RecordAtTest(unittest.TestCase):
    """Which record a touch lands on, as the touch probe's taps chose them
    (readings.toml, [[touches]])."""

    def test_the_rows_under_the_probes_taps(self):
        tables = {component.name: component.values
                  for component in probe_components(FOLDER / "touches.page.toml")
                  if component.type == "data-record"}
        cases = [("da", 3, 0, 25, None), ("da", 3, 0, 58, 2), ("da", 3, 0, 90, 1),
                 ("da", 3, 0, 122, 0), ("da", 3, 0, 170, None),
                 ("db", 8, 40, 58, 1), ("db", 8, 0, 58, 0),
                 ("dc", 3, 0, 25, 2), ("dc", 3, 0, 58, 1), ("dc", 0, 0, 25, None)]
        for name, records, scrolled, y, expected in cases:
            values = dict(tables[name], val_y=scrolled)
            with self.subTest(table=name, y=y, scrolled=scrolled):
                self.assertEqual(record_at(values, records, inside_box(values), y), expected)


class EditorDataRecordTest(unittest.TestCase):
    """The drawing, against the Editor's pictures, pixel for pixel."""

    def assert_drawn_alike(self, page: str, picture: str, listings: dict, changes: dict = None,
                           resources=None):
        components = [component if component.name not in (changes or {}) else
                      Component(component.name, component.type,
                                dict(component.values, **changes[component.name]))
                      for component in probe_components(FOLDER / ("%s.page.toml" % page))]
        records = [component for component in components[1:] if component.type == "data-record"]
        drawn = paint_drawing(draw_page(components[:1] + records, resources or ProbeFont(),
                                        listings=listings))
        shot = read_picture((FOLDER / picture).read_bytes())
        for component in records:
            with self.subTest(picture=picture, component=component.name):
                differing = differing_pixels(drawn, shot, component.values, 2)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_records_that_could_not_open_their_file(self):
        # unopened.png: d0 opened the file, empty; d1 and d2, naming it too,
        # showed the message in white on black, in their font.
        self.assert_drawn_alike("unopened", "unopened.png",
                                {"d0": [], "d1": UNOPENED, "d2": UNOPENED},
                                resources=NotoSans24())

    def test_records_of_no_path(self):
        # file-lost.png: d0 and d1, each of `path` "", showed "File Lost:" in
        # white on black, in their font, the Editor's page view alike.
        for listings in ({"d0": [], "d1": []}, {}):
            self.assert_drawn_alike("file-lost", "file-lost.png", listings,
                                    resources=NotoSans24())

    def test_the_orders_and_the_chosen_record(self):
        three = records_of("three.data")
        self.assert_drawn_alike("orders", "orders.png", {"d0": three, "d1": three})
        self.assert_drawn_alike("orders", "orders-chosen.png", {"d0": three, "d1": three},
                                {"d0": {"val": READINGS["orders"]["chosen"]["d0"]}})

    def test_scrolled_wide_and_without_titles(self):
        listings = {"da": EIGHT, "db": EIGHT, "dc": EIGHT}
        self.assert_drawn_alike("looks", "looks.png", listings)
        down = {"da": {"val_y": 40}, "db": {"val_y": 40}}
        self.assert_drawn_alike("looks", "looks-scrolled.png", listings, down)
        self.assert_drawn_alike("looks", "looks-across.png", listings,
                                dict(down, db={"val_y": 40, "val_x": 100}))

    def test_a_ring_and_fewer_columns_than_fields(self):
        self.assert_drawn_alike("ring", "ring.png",
                                {"da": records_of("ring.data"), "db": [],
                                 "dc": records_of("fields.data")},
                                {"da": {"val": READINGS["ring"]["val"]}})

    def test_the_chosen_record_and_the_untitled_top_row(self):
        # touches.png: da's second row chosen, db as it opened, and dc's top
        # row, where titles would be, chosen.
        abc = ["a^1^x", "b^2^y", "c^3^z"]
        self.assert_drawn_alike("touches", "touches.png", {"da": abc, "db": EIGHT, "dc": abc},
                                {"da": {"val": 1}, "dc": {"val": 2}})

    def test_an_empty_record_keeps_its_row(self):
        # Without titles, an empty newest record takes the titles' row as any
        # other does, where a tap finds it (record_at).
        page, _, _, dc = probe_components(FOLDER / "touches.page.toml")[:4]

        def lines(listing):
            shapes = draw_page([page, dc], ProbeFont(), listings={"dc": listing})["shapes"]
            grid = rgb565_to_hex(dc.values.get("gdc", 50712))
            return sorted({(shape["y"], shape["h"]) for shape in shapes
                           if shape["component"] == "dc" and shape.get("colour") == grid})
        self.assertEqual(lines(["a^1^x", ""]), lines(["a^1^x", "z"]))

    def test_the_preview_draws_titles_and_lines(self):
        # Without records, as the preview has no card: the titles' row, and
        # the line under it.
        page, d0 = probe_components(FOLDER / "orders.page.toml")[:2]
        shapes = draw_page([page, d0], ProbeFont())["shapes"]
        grid = rgb565_to_hex(d0.values["gdc"])
        lines = [shape for shape in shapes if shape["component"] == "d0"
                 and shape["kind"] == "colour" and shape["colour"] == grid]
        top = d0.values["y"] + 1      # inside its 3D edge
        self.assertEqual(sorted({shape["y"] for shape in lines if shape["h"] == 1}),
                         [top, top + d0.values["hig"]])


if __name__ == "__main__":
    unittest.main()
