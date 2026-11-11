"""File commands on a path that is neither on an SD card nor in `ram/`,
such as `x.bin`. Each expected answer is the one the Nextion Editor's
simulator gave for an NX8048P050."""
from pathlib import Path
import tempfile
import unittest

from nxwright.testing.editor_machine import NOT_ON_A_CARD, EditorMachine
from nxwright.testing.simulation import Simulation
from tests.test_simulation import SimulationTestCase, placed, table

REFUSED = b"\x06\xff\xff\xff"

# The five commands the screen ignores on a path such as `x.bin`, and the
# entry each one adds to "file errors".
LINES = ['newfile "y.bin",8', 'delfile "x.bin"', 'refile "x.bin","z.bin"', 'newdir "d/"',
         'deldir "d/"']
ERRORS = [("newfile", "y.bin"), ("delfile", "x.bin"), ("refile", "x.bin"), ("newdir", "d/"),
          ("deldir", "d/")]


def run(lines: list, files: dict = None, space: int = 0) -> dict:
    """Runs `lines` on a test machine that starts with `files`, {path:
    bytes}, and returns the machine's values."""
    values = {"file contents": dict(files)} if files else {}
    return EditorMachine(values, memory_file_storage_size=space).run(lines)


class TestMachineTest(unittest.TestCase):

    def test_the_five_commands_are_ignored_and_change_nothing(self):
        files = {"x.bin": b"kept"}
        values = run(LINES, files)
        self.assertEqual(values["file contents"], files)
        self.assertEqual(values["file errors"], ERRORS)
        self.assertEqual(values.get("file commands", []), [])

    def test_ram_in_upper_case_is_on_no_card(self):
        values = run(['newfile "RAM/a.bin",8'], space=4096)
        self.assertEqual(values.get("file contents", {}), {})
        self.assertEqual(values["file errors"], [("newfile", "RAM/a.bin")])

    def test_a_file_a_test_gives_is_still_found_and_read(self):
        values = EditorMachine({"file contents": {"x.bin": b"hello"}, "existing": ["e.bin"],
                                "t0.txt": ""}).run(
            ['findfile "x.bin",sys0', 'findfile "e.bin",sys1', 'fs0.open("x.bin")',
             "fs0.read(t0.txt,0,5)"])
        self.assertEqual((values["sys0"], values["sys1"], values["t0.txt"]), (1, 1, "hello"))
        self.assertNotIn("file errors", values)

    def test_redir_is_still_recorded(self):
        values = run(['redir "a/","b/"'])
        self.assertEqual(values["file commands"], [("redir", "a/", "b/")])
        self.assertNotIn("file errors", values)

    def test_commands_still_work_on_a_card_given_no_folder(self):
        # The card's name may be in upper or lower case, and `sd0` alone is
        # the card.
        for card in ("sd0/", "sd1/", "SD0/"):
            with self.subTest(card=card):
                lines = ['newfile "%sa.bin",3' % card, 'newfile "%sb.bin",2' % card,
                         'delfile "%sb.bin"' % card, 'refile "%sa.bin","%sc.bin"' % (card, card),
                         'newdir "%sd/"' % card, 'deldir "%sd/"' % card, 'deldir "%s"' % card[:-1]]
                values = run(lines)
                self.assertEqual(values["file contents"], {card + "a.bin": bytes(3)})
                self.assertEqual([entry[0] for entry in values["file commands"]],
                                 ["newfile", "newfile", "delfile", "refile", "newdir", "deldir",
                                  "deldir"])
                self.assertNotIn("file errors", values)


class SimulationTest(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.addCleanup(self._card.cleanup)
        self.card = Path(self._card.name).resolve()
        self.program("page page0\n")
        self.page("page0", [placed("go", "button", 0, 0), table("found", "variable")], "")
        self.sent = []

    def simulation(self, **options) -> Simulation:
        simulation = Simulation(self.root, sending=self.sent.append, **options)
        self.sent.clear()
        return simulation

    def typed(self, simulation: Simulation, *lines: str):
        for line in lines:
            simulation.serial_received(line.encode() + b"\xff\xff\xff")

    def file_lines(self, simulation: Simulation) -> list:
        """The log's lines about file commands."""
        return [line for _, line in simulation.log if line.startswith(("SD card:", "ram/:"))]

    def test_each_of_the_five_commands_answers_06(self):
        simulation = self.simulation()
        self.typed(simulation, *LINES)
        self.assertEqual(self.sent, [REFUSED] * 5)
        values = simulation.values()
        self.assertEqual(values.get("file contents", {}), {})
        self.assertEqual(values["file errors"], ERRORS)
        self.assertEqual(values.get("file commands", []), [])

    def test_the_log_says_why(self):
        simulation = self.simulation()
        self.typed(simulation, *LINES, 'twfile "r.txt",5')
        self.assertEqual(self.file_lines(simulation), [
            "SD card: %s of %s refused: %s" % (command, path, NOT_ON_A_CARD)
            for command, path in ERRORS + [("twfile", "r.txt")]])
        self.assertEqual(NOT_ON_A_CARD, "the path does not start with sd0/, sd1/, or ram/")

    def test_newfile_checks_its_size_first(self):
        simulation = self.simulation()
        self.typed(simulation, 'newfile "y.bin","abc"')
        self.assertEqual(self.sent, [b"\x1b\xff\xff\xff"])
        self.assertEqual(self.file_lines(simulation), ["SD card: newfile of y.bin refused"])

    def test_beside_a_card_given_a_folder(self):
        # Nothing is created in the card's folder, and paths on the card still work.
        simulation = self.simulation(cards={"sd0/": self.card})
        self.typed(simulation, 'newfile "y.bin",8', 'newdir "d/"', 'newfile "sd0/a.bin",2',
                   'newfile "sd1/b.bin",2')
        self.assertEqual(self.sent, [REFUSED] * 2)
        self.assertEqual([path.name for path in self.card.iterdir()], ["a.bin"])
        self.assertEqual(simulation.values()["file contents"], {"sd1/b.bin": bytes(2)})
        self.assertEqual(self.file_lines(simulation)[2:], [
            "SD card: newfile sd0/a.bin 2", "SD card: newfile sd1/b.bin 2"])


if __name__ == "__main__":
    unittest.main()
