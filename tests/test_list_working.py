"""List components worked out in tests as in the simulator
(testing/list_working.py): the values that follow from a value code sets
on a file browser, a select, a sliding text, a combo box, or a data
record, in a test's run of a page's events (source_runner.py), and in a
machine given no folder resources, which works none of them."""
from pathlib import Path

from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.testing.editor_machine import EditorMachine
from nxwright.testing.simulation import Simulation
from nxwright.testing.source_runner import SourceFolderRunner
from tests.test_simulation import SimulationTestCase, table

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# Twelve lines, in the Editor's code: "\r" breaks a line.
TWELVE_LINES = "\\r".join("line%d" % number for number in range(12))


class PageEventTestCase(SimulationTestCase):
    """A test of page0's Touch Press event, which `code` gives."""
    language = "nextion"

    def run_test(self, components: list, code: str, values: dict = None) -> dict:
        self.page("page0", components, "on page0.down:\n" + "".join(
            "  %s\n" % line for line in code.strip("\n").split("\n")))
        return SourceFolderRunner(self.root).run("page0", [("page0", "down")], values)


class StoredTest(PageEventTestCase):
    """What follows from a value code sets."""

    def test_a_file_browser(self):
        # Its folder listed, folders first; `val` picks an entry; `up()`
        # goes to the folder above and lists it.
        files = {"sd0/a.txt": b"a", "sd0/b.txt": b"b", "sd0/sub/c.txt": b"c"}
        browser = table("fb0", "file-browser", x=0, y=0, w=200, h=200, dir="sd0/sub/")
        values = self.run_test([browser], 'fb0.dir="sd0/"\nfb0.val=1',
                               {"file contents": files})
        self.assertEqual((values["fb0.qty"], values["fb0.txt"]), (3, "a.txt"))
        values = self.run_test([browser], "fb0.up()", {"file contents": files})
        self.assertEqual((values["fb0.dir"], values["fb0.qty"], values["fb0.val"]),
                         ("sd0/", 3, -1))

    def test_code_reads_what_the_working_set_but_not_what_is_beneath(self):
        # The page file's values serve the working alone: code reading one
        # the test did not give stops the run, as any field not given does,
        # while a value the working set joins the test's own.
        files = {"sd0/a.txt": b"a"}
        browser = table("fb0", "file-browser", x=0, y=0, w=200, h=200, dir="sd0/")
        values = self.run_test([browser], 'fb0.dir="sd0/"\nsys0=fb0.qty',
                               {"file contents": files, "sys0": 0})
        self.assertEqual(values["sys0"], 1)
        with self.assertRaises(KeyError):
            self.run_test([browser], "sys0=fb0.h", {"sys0": 0})

    def test_a_check_that_turns_on_a_type(self):
        # The type comes from the page file, as in the simulator, though the
        # test gives none: a file stream's position below 0 is refused.
        stream = table("fs0", "file-stream")
        values = self.run_test([stream], "fs0.val=-1", {"fs0.val": 0})
        self.assertEqual(values["fs0.val"], 0)

    def test_up_on_another_type(self):
        # Only a file browser goes up and lists. A text's up(), which the
        # build refuses in page code, is refused typed too, before it runs:
        # it works nothing.
        self.page("page0", [table("t0", "text", x=0, y=0, w=100, h=30, txt="a")])
        simulation = Simulation(self.root)
        simulation.serial_input("t0.up()")
        self.assertNotIn("t0.qty", simulation.values())

    def test_a_select(self):
        select = table("sel0", "select", x=0, y=0, w=200, h=100, path="one\\r\\ntwo")
        self.assertEqual(self.run_test([select], "sel0.val=1")["sel0.txt"], "two")

    def test_a_sliding_text(self):
        # Its `maxval_y` worked out from its new lines, in the folder's font,
        # and its `val_y` stopped where code may scroll it, as the simulator
        # stops them.
        sliding = table("s0", "sliding-text", x=0, y=0, w=200, h=120, txt="a", txt_maxl=200)
        code = 's0.txt="%s"\ns0.val_y=500' % TWELVE_LINES
        values = self.run_test([sliding], code)
        simulation = Simulation(self.root)
        simulation.serial_input("click page0,1")
        expected = simulation.values()
        self.assertEqual((values["s0.maxval_y"], values["s0.val_y"]),
                         (expected["s0.maxval_y"], expected["s0.val_y"]))
        self.assertGreater(values["s0.maxval_y"], 0)
        self.assertLess(values["s0.val_y"], 500)

    def test_a_combo_box(self):
        # A `val` past its last item is taken back to the last within them.
        combo = table("cb0", "combo-box", x=0, y=0, w=200, h=40, path="a\\r\\nb")
        values = self.run_test([combo], "cb0.val=1\ncb0.val=9")
        self.assertEqual((values["cb0.val"], values["cb0.txt"]), (1, "b"))

    def test_a_data_records_scroll(self):
        # A new `hig` works out `maxval_y` again: seven rows and the titles',
        # past 148 inside a 3D edge. `val_y` settles 32 pixels past it once
        # the event ends, and `val_x` at `maxval_x`.
        record = table("d0", "data-record", x=0, y=0, w=380, h=150, path="sd0/d.data",
                       dir="A^B", dez=2)
        inserts = "\n".join('d0.insert("r%d^%d")' % (number, number) for number in range(7))
        values = self.run_test([record], inserts + "\nd0.val_y=500\nd0.val_x=500\nd0.hig=40")
        self.assertEqual((values["d0.val_y"], values["d0.val_x"], values["d0.maxval_y"]),
                         (8 * 40 + 1 - 148 + 32, 0, 8 * 40 + 1 - 148))

    def test_a_data_record_shut_out_of_its_file(self):
        # d1 finds the file d0 holds: no records, as the page's table shows;
        # still none once d0 lets it go, until d1's own method opens it.
        records = [table(name, "data-record", x=0, y=200 * place, w=380, h=150,
                         path="sd0/d.data", dir="A^B", dez=2)
                   for place, name in enumerate(("d0", "d1"))]
        values = self.run_test(records, 'd0.insert("a^1")\nd1.hig=40')
        self.assertEqual(values["d1.qty"], 0)
        values = self.run_test(records, 'd0.insert("a^1")\nd1.hig=40\nd0.path="sd0/e.data"\n'
                                        "d1.hig=32")
        self.assertEqual(values["d1.qty"], 0)
        values = self.run_test(records, 'd0.insert("a^1")\nd1.hig=40\nd0.path="sd0/e.data"\n'
                                        'd1.insert("b^2")\nd1.hig=32')
        self.assertEqual(values["d1.qty"], 2)


class OpenedTest(PageEventTestCase):
    """A test's page as it opened, before its events run: its list
    components worked out as the simulator's page opening works them, then
    the values the test gives written over them."""

    def test_a_file_browser_lists_its_folder(self):
        files = {"sd0/a.txt": b"a", "sd0/b.txt": b"b"}
        browser = table("fb0", "file-browser", x=0, y=0, w=200, h=200, dir="sd0/")
        values = self.run_test([browser], "sys0=fb0.qty\nfb0.val=1",
                               {"file contents": files, "sys0": 0})
        self.assertEqual((values["sys0"], values["fb0.txt"]), (2, "b.txt"))

    def test_a_sliding_texts_maxval_y(self):
        # In a page file, a line breaks at a carriage return and a line feed.
        lines = "\\r\\n".join("line%d" % number for number in range(12))
        sliding = table("s0", "sliding-text", x=0, y=0, w=200, h=120, txt=lines, txt_maxl=200)
        values = self.run_test([sliding], "sys0=s0.maxval_y", {"sys0": 0})
        self.assertEqual(values["sys0"], Simulation(self.root).values()["s0.maxval_y"])
        self.assertGreater(values["sys0"], 0)

    def test_a_data_record_reads_its_file(self):
        record = table("d0", "data-record", x=0, y=0, w=380, h=150, path="sd0/d.data",
                       dir="A^B^C")
        three = (FIXTURES / "data-record" / "three.data").read_bytes()
        values = self.run_test([record], "sys0=d0.qty",
                               {"file contents": {"sd0/d.data": three}, "sys0": 0})
        self.assertEqual(values["sys0"], 3)

    def test_a_value_the_test_gives_wins(self):
        # Even one the working would change: a `val_y` past where code may
        # scroll the text.
        sliding = table("s0", "sliding-text", x=0, y=0, w=200, h=120, txt="a", txt_maxl=200)
        values = self.run_test([sliding], "sys0=s0.val_y", {"s0.val_y": 500, "sys0": 0})
        self.assertEqual(values["sys0"], 500)


class NoResourcesTest(SimulationTestCase):
    """A machine made with values alone, as in Python, works no list
    component: what code sets stays as set."""

    def test_values_stay_as_set(self):
        machine = EditorMachine({"s0.type": TYPES_BY_NAME["sliding-text"], "s0.val_y": 0,
                                 "s0.maxval_y": 0, "fb0.type": TYPES_BY_NAME["file-browser"],
                                 "fb0.dir": "", "fb0.qty": 0})
        machine.run(["s0.val_y=500", 'fb0.dir="sd0/"'])
        self.assertEqual((machine.values["s0.val_y"], machine.values["fb0.qty"]), (500, 0))
