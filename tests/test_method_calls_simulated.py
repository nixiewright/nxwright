"""A method call as a value, and a method alone on a line, in the simulator.

A call used as a value, as in `sys0=fs0.close()`, runs the method, and
gives 1 when it succeeds and 0 when it fails. A method written alone on a
line without its parentheses, as in `fs0.close`, does nothing.

The values of a file stream are the ones an NX8048P070 gave when each
instruction was typed on its serial line. Those of a data record and of a
file browser come from the simulator of the Nextion Editor 1.68.2
(ResearchNotes/tft/method-calls-in-code.md).
"""
from pathlib import Path
import tempfile

from nxwright.testing.simulation import Simulation
from tests.test_simulation import DataFileHoldingTestCase, placed, table

_PROGRAM = "int sys0=0,sys1=0,sys2=0\npage 0\n"


class MethodCallsTestCase(DataFileHoldingTestCase):
    """A simulation of a page with a text t0, a button b0, a file stream
    fs0, a data record d0, and a file browser fb0. The SD card is a folder
    with a file of 10 bytes, a.txt, and a folder, sub."""

    def setUp(self):
        super().setUp()
        self.card = tempfile.TemporaryDirectory()
        self.addCleanup(self.card.cleanup)
        (Path(self.card.name) / "a.txt").write_bytes(b"0123456789")
        (Path(self.card.name) / "sub").mkdir()
        self.write("program.nx", _PROGRAM)

    def started(self, code: str = "") -> tuple:
        self.page("page0", [
            placed("t0", "text", 0, 0, txt="Hi"), placed("b0", "button", 0, 60),
            table("fs0", "file-stream"),
            table("d0", "data-record", x=300, y=10, w=250, h=140, path="sd0/d.data", dir="a^b",
                  lenth=16, maxval=10, mode=1),
            table("fb0", "file-browser", x=300, y=200, w=250, h=140)], code)
        sent = []
        return Simulation(self.root, sending=sent.append,
                          cards={"sd0/": Path(self.card.name)}), sent

    def value_of(self, simulation: Simulation, call: str) -> int:
        """Returns the value of `sys0` after `sys0=<call>` is typed. `sys0`
        is set to 7 first, to tell a call that gave 0 from a line that did
        not run."""
        simulation.serial_input("sys0=7")
        simulation.serial_input("sys0=%s" % call)
        return simulation.values()["sys0"]


class FileStreamTest(MethodCallsTestCase):

    def test_an_open_gives_1_and_opens_the_file(self):
        simulation, sent = self.started()
        self.assertEqual(self.value_of(simulation, 'fs0.open("sd0/a.txt")'), 1)
        self.assertEqual((simulation.values()["fs0.en"], sent), (1, []))

    def test_an_open_of_a_missing_file_gives_0_and_sends_nothing(self):
        simulation, sent = self.started()
        self.assertEqual(self.value_of(simulation, 'fs0.open("sd0/missing.txt")'), 0)
        self.assertEqual((simulation.values()["fs0.en"], sent), (0, []))

    def test_a_close_gives_1_with_or_without_an_open_file(self):
        simulation, sent = self.started()
        self.assertEqual(self.value_of(simulation, "fs0.close()"), 1)
        simulation.serial_input('fs0.open("sd0/a.txt")')
        self.assertEqual(self.value_of(simulation, "fs0.close()"), 1)
        self.assertEqual((simulation.values()["fs0.en"], sent), (0, []))

    def test_a_read_and_a_write_give_1_on_an_open_file(self):
        simulation, _ = self.started()
        simulation.serial_input('fs0.open("sd0/a.txt")')
        self.assertEqual(self.value_of(simulation, "fs0.write(t0.txt,0,2)"), 1)
        self.assertEqual(simulation.values()["fs0.val"], 2)
        self.assertEqual(self.value_of(simulation, "fs0.read(t0.txt,0,2)"), 1)

    def test_a_read_and_a_write_give_0_when_they_fail(self):
        simulation, sent = self.started()
        # No file is open.
        self.assertEqual(self.value_of(simulation, "fs0.read(t0.txt,0,2)"), 0)
        self.assertEqual(self.value_of(simulation, "fs0.write(t0.txt,0,2)"), 0)
        # Past the end of the file, which has 10 bytes.
        simulation.serial_input('fs0.open("sd0/a.txt")')
        self.assertEqual(self.value_of(simulation, "fs0.read(t0.txt,0,50)"), 0)
        self.assertEqual(sent, [])

    def test_a_find_gives_0_whatever_the_file(self):
        simulation, _ = self.started()
        self.assertEqual(self.value_of(simulation, 'fs0.find("sd0/a.txt")'), 0)
        self.assertEqual(self.value_of(simulation, 'fs0.find("sd0/missing.txt")'), 0)

    def test_the_value_joins_other_operands(self):
        simulation, _ = self.started()
        self.assertEqual(self.value_of(simulation, '2+fs0.open("sd0/a.txt")'), 3)
        simulation.serial_input("sys0=7")
        simulation.serial_input("sys0+=fs0.close()")
        self.assertEqual(simulation.values()["sys0"], 8)
        self.assertEqual(self.value_of(simulation, 'fs0.find("sd0/a.txt")+5'), 5)

    def test_a_call_in_a_condition(self):
        simulation, _ = self.started(
            'on b0.up:\n  if(fs0.open("sd0/a.txt")==1)\n  {\n    sys1=4\n  }\n')
        simulation.serial_input("click b0,0")
        self.assertEqual((simulation.values()["sys1"], simulation.values()["fs0.en"]), (4, 1))

    def test_a_call_in_an_event(self):
        simulation, sent = self.started(
            'on b0.up:\n  sys0=fs0.open("sd0/a.txt")\n  sys1=fs0.close()+fs0.find("sd0/a.txt")\n')
        simulation.serial_input("click b0,0")
        values = simulation.values()
        self.assertEqual((values["sys0"], values["sys1"], values["fs0.en"], sent), (1, 1, 0, []))

    def test_a_call_in_the_start_of_a_for_is_not_run(self):
        # The Nextion Editor writes the start without the call's parentheses
        # and arguments. In its simulator, the file stayed open, and sys0
        # took the value that `close` has as an attribute, 101.
        simulation, _ = self.started(
            'on b0.up:\n  for(sys0=fs0.close();sys0<0;sys0++)\n  {\n  }\n')
        simulation.serial_input('fs0.open("sd0/a.txt")')
        simulation.serial_input("click b0,0")
        self.assertEqual((simulation.values()["sys0"], simulation.values()["fs0.en"]), (101, 1))

    def test_a_call_in_the_start_of_a_for_may_have_a_parenthesis_in_its_text(self):
        (Path(self.card.name) / "a(1).txt").write_bytes(b"0123456789")
        simulation, _ = self.started(
            'on b0.up:\n  for(sys0=fs0.open("sd0/a(1).txt");sys0<0;sys0++)\n  {\n  }\n  sys1=3\n')
        simulation.serial_input("click b0,0")
        self.assertEqual((simulation.values()["sys1"], simulation.values()["fs0.en"]), (3, 0))

    def test_a_call_with_the_wrong_arguments_is_not_run(self):
        # An NX8048P070 answered each typed line this way: 0x1E for the wrong
        # number of arguments, 0x1A for a name that is not a method, and 0x00
        # for a call of such a name alone on its line.
        simulation, sent = self.started()
        simulation.serial_input('fs0.open("sd0/a.txt")')
        simulation.serial_input("sys0=7")
        for line, answer in (("sys0=fs0.close(1)", "1e"), ("fs0.close(1)", "1e"),
                             ("sys0=fs0.open()", "1e"), ("fs0.open()", "1e"),
                             ("sys0=fs0.read(t0.txt)", "1e"), ("sys0=fb0.up(1)", "1e"),
                             ("sys0=t0.txt()", "1a"), ("sys0=fs0.val()", "1a"),
                             ("t0.txt()", "00")):
            with self.subTest(line):
                sent.clear()
                simulation.serial_input(line)
                values = simulation.values()
                self.assertEqual((sent, values["sys0"], values["fs0.en"]),
                                 ([bytes.fromhex(answer + " ff ff ff")], 7, 1))


class DataRecordAndFileBrowserTest(MethodCallsTestCase):

    def test_a_data_record_s_methods(self):
        simulation, _ = self.started()
        self.assertEqual(self.value_of(simulation, 'd0.insert("a^b")'), 1)
        self.assertEqual(simulation.values()["d0.qty"], 1)
        self.assertEqual(self.value_of(simulation, 'd0.up("c^d",0)'), 1)
        self.assertEqual(self.value_of(simulation, "d0.delete(5,1)"), 0)
        self.assertEqual(self.value_of(simulation, "d0.delete(0,1)"), 1)
        self.assertEqual(self.value_of(simulation, "d0.clear()"), 1)
        # The value joins other operands.
        self.assertEqual(self.value_of(simulation, '2+d0.insert("a^b")'), 3)

    def test_a_data_record_that_changes_nothing_gives_0(self):
        # d0 keeps the file that d1 shares with it, and d2 opens no file
        # because its `init` is 1.
        self.page("second", [
            table("d0", "data-record", x=0, y=10, w=250, h=140, path="sd0/s.data", dir="a^b",
                  lenth=16, maxval=10, mode=1),
            table("d1", "data-record", x=260, y=10, w=250, h=140, path="sd0/s.data", dir="a^b",
                  lenth=16, maxval=10, mode=1),
            table("d2", "data-record", x=520, y=10, w=250, h=140, path="sd0/i.data", dir="a^b",
                  lenth=16, maxval=10, mode=1, init=1)])
        simulation, _ = self.started()
        simulation.serial_input("page second")
        self.assertEqual(self.value_of(simulation, 'd1.insert("a^b")'), 0)
        self.assertEqual(self.value_of(simulation, 'd2.insert("a^b")'), 0)
        self.assertEqual(self.value_of(simulation, 'd0.insert("a^b")'), 1)

    def test_a_file_browser_s_up(self):
        # `up()` gives 0 in the card's own folder, and 1 from a folder below it.
        simulation, _ = self.started()
        self.assertEqual(self.value_of(simulation, "fb0.up()"), 0)
        simulation.serial_input('fb0.dir="sd0/sub/"')
        self.assertEqual(self.value_of(simulation, "fb0.up()"), 1)
        self.assertEqual(self.value_of(simulation, "fb0.up()+5"), 5)


class MethodAloneTest(MethodCallsTestCase):

    def test_it_does_nothing_and_sends_nothing(self):
        simulation, sent = self.started()
        simulation.serial_input('fs0.open("sd0/a.txt")')
        simulation.serial_input('d0.insert("a^b")')
        for line in ("fs0.close", "fs0.open", "fs0.find", "d0.clear", "fb0.up"):
            with self.subTest(line):
                simulation.serial_input(line)
                values = simulation.values()
                self.assertEqual((values["fs0.en"], values["d0.qty"], sent), (1, 1, []))

    def test_in_an_event(self):
        simulation, sent = self.started('on b0.up:\n  fs0.close\n  sys1=3\n')
        simulation.serial_input('fs0.open("sd0/a.txt")')
        simulation.serial_input("click b0,0")
        values = simulation.values()
        self.assertEqual((values["fs0.en"], values["sys1"], sent), (1, 3, []))
