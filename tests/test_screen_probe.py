"""The probe of `ram/` files for a real screen (tools/screen/ram_probe.py),
run against nxwright's simulator in place of a screen."""
from pathlib import Path
import shutil
import tempfile
import unittest

from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tools.screen.ram_probe import (CHECKS, END, NO_SPACE_CHECKS, SPACE, Check, number, report,
                                    run_checks)

PROJECT = Path(__file__).resolve().parent.parent / "tools" / "screen" / "project"


class SimulatorExchange:
    """Sends bytes to a simulation of the probe's project, and returns what
    the simulation sends back, the way a serial port would."""

    def __init__(self, folder: Path):
        self._sent = []
        self._simulation = Simulation(folder, sending=self._sent.append)
        self._sent.clear()

    def __call__(self, data: bytes) -> bytes:
        self._simulation.serial_received(data)
        answer = b"".join(self._sent)
        self._sent.clear()
        return answer


class ProbeTest(unittest.TestCase):

    def differing(self, checks, folder: Path) -> list:
        """Runs `checks` on a simulation of the project in `folder`, and
        returns the rules whose answers differ from the Nextion Editor's
        simulator's."""
        answers = run_checks(checks, SimulatorExchange(folder), lambda question: True)
        self.assertEqual(len(answers), len(checks))
        return [answer.check.rule for answer in answers if answer.differs]

    def test_the_project_sets_the_space_the_checks_assume(self):
        self.assertIn("memory_file_storage_size = %d" % SPACE,
                      (PROJECT / "app.toml").read_text(encoding="utf-8"))

    def test_nxwrights_simulator_gives_the_answers_of_the_nextion_editors_simulator(self):
        self.assertEqual(self.differing(CHECKS, PROJECT), [])

    def test_the_checks_with_no_space_set_aside(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "project"
            shutil.copytree(PROJECT, folder)
            app = folder / "app.toml"
            app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                      lambda data: data.update(memory_file_storage_size=0)),
                           encoding="utf-8")
            self.assertEqual(self.differing(NO_SPACE_CHECKS, folder), [])

    def test_the_data_of_a_twfile_reaches_the_file(self):
        check = next(check for check in CHECKS if check.rule.startswith("twfile writes"))
        answer, = run_checks([check], SimulatorExchange(PROJECT), lambda question: True)
        self.assertEqual(answer.sent, b"\xfe" + END + b"\xfd" + END + b"\x05\x00\x00\x00HELLO")

    def test_the_report(self):
        checks = [Check("A rule", ('newfile "RAM/a.bin",8',), number(0)),
                  Check("A question", ("get sys0",), number(0), question="Is it there?",
                        then=("sys0=1",)),
                  Check("Not run by the simulator", ("get sys0",))]
        answers = run_checks(checks, SimulatorExchange(PROJECT), lambda question: False)
        text = report(answers, "comok 1,30601-0,NX8048P050_011R")
        self.assertIn("`comok 1,30601-0,NX8048P050_011R`", text)
        self.assertIn("| A rule | `newfile \"RAM/a.bin\",8` | `71 00 00 00 00 FF FF FF` "
                      "| `06 FF FF FF` | **yes** |", text)
        self.assertIn("| A question | `get sys0`<br>`sys0=1` | `71 00 00 00 00 FF FF FF` "
                      "| `71 00 00 00 00 FF FF FF`<br>Is it there? No. | **yes** |", text)
        self.assertIn("| Not run by the simulator | `get sys0` | not run "
                      "| `71 01 00 00 00 FF FF FF` | no |", text)
        self.assertIn("The screen differs from the Nextion Editor's simulator on 2 of 3 checks.",
                      text)


if __name__ == "__main__":
    unittest.main()
