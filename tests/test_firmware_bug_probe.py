"""Tests the list of the firmware's bugs that nxwright's simulator matches
(tools/screen/matched_firmware_bugs.py), and the probe that checks them on a
real screen (tools/screen/firmware_bug_probe.py). nxwright's simulator stands
in for the screen."""
import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from nxwright.source.device_change import change_device
from tests.test_screen_probe import PROJECT, SimulatorExchange
from tools.screen.firmware_bug_probe import (bugs_in, bugs_no_longer_shown, main, report,
                                             summary)
from tools.screen.matched_firmware_bugs import BUGS
from tools.screen.ram_probe import ENCODING, END, Answer, run_checks

_NXWRIGHT = Path(__file__).resolve().parent.parent


def answers_of_the_simulator(bugs: list, encoding: str) -> list:
    """Runs the checks of `bugs` on a simulation of the probe's project,
    built in `encoding`, and returns their answers."""
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary) / "project"
        shutil.copytree(PROJECT, folder)
        if encoding != ENCODING:
            change_device(folder, encoding=encoding)
        return run_checks([check for bug in bugs for check in bug.checks],
                          SimulatorExchange(folder), lambda question: True, encoding)


class ScreenOnAPort(SimulatorExchange):
    """Stands in for the probe's serial exchange: a simulation of the
    probe's project that answers `connect` the way a screen does, or a port
    with no screen on it, which answers nothing."""

    def __init__(self, answering: bool = True):
        super().__init__(PROJECT)
        self._answering = answering
        self.closed = False

    def __call__(self, data: bytes) -> bytes:
        if not self._answering:
            return b""
        if data == b"connect" + END:
            return b"comok 2,1793-0,NX8048P070_011C" + END
        return super().__call__(data)

    def close(self):
        self.closed = True


class MatchedFirmwareBugsTest(unittest.TestCase):

    def test_each_bug_is_described(self):
        for bug in BUGS:
            with self.subTest(bug.what[:40]):
                self.assertTrue(bug.what.strip())
                self.assertTrue(bug.matched_in)
                self.assertTrue(bug.checks)

    def test_the_code_that_matches_each_bug_exists(self):
        # A bug's entry gives the code to change once the firmware fixes
        # the bug, so it must keep pointing at that code.
        for bug in BUGS:
            for path, name in bug.matched_in:
                with self.subTest(path, name=name):
                    self.assertIn("def %s(" % name,
                                  (_NXWRIGHT / path).read_text(encoding="utf-8"))

    def test_nxwrights_simulator_has_each_bug(self):
        for encoding in sorted({bug.encoding for bug in BUGS}):
            with self.subTest(encoding):
                bugs = bugs_in(encoding)
                answers = answers_of_the_simulator(bugs, encoding)
                self.assertEqual([answer.check.rule for answer in answers if answer.differs], [])
                self.assertEqual(bugs_no_longer_shown(bugs, answers), [])


class FirmwareBugProbeTest(unittest.TestCase):

    def answers(self, bugs: list, differing: tuple = ()) -> list:
        """Returns an answer for each check of `bugs`: what the check
        expects, or nothing for a check whose rule is in `differing`."""
        return [Answer(check, b"" if check.rule in differing else check.expected)
                for bug in bugs for check in bug.checks]

    def test_the_checks_of_an_encoding(self):
        self.assertEqual(bugs_in(ENCODING) + bugs_in("shift-jis"), BUGS)
        self.assertTrue(bugs_in("shift-jis"))
        self.assertEqual({bug.encoding for bug in bugs_in("shift-jis")}, {"shift-jis"})

    def test_a_screen_that_shows_each_bug(self):
        bugs = bugs_in(ENCODING)
        answers = self.answers(bugs)
        self.assertEqual(bugs_no_longer_shown(bugs, answers), [])
        self.assertEqual(summary(bugs, answers),
                         "The screen shows each of the %d bugs checked." % len(bugs))
        text = report(bugs, answers, "comok 2,1793-0,NX8048P070_011C", ENCODING)
        self.assertIn("`comok 2,1793-0,NX8048P070_011C`", text)
        self.assertIn("built in iso-8859-1.", text)
        self.assertIn("| Check | Sent | A screen with the bug | The screen | Differs |", text)
        self.assertNotIn("code that matches the bug", text)

    def test_a_screen_that_no_longer_shows_a_bug(self):
        bugs = bugs_in("shift-jis")
        counting = bugs[0]
        # A bug counts as no longer shown as soon as one of its checks differs.
        answers = self.answers(bugs, differing=(counting.checks[1].rule,))
        self.assertEqual(bugs_no_longer_shown(bugs, answers), [counting])
        self.assertEqual(summary(bugs, answers),
                         "The screen no longer shows 1 of the %d bugs checked." % len(bugs))
        text = report(bugs, answers, "comok 2,1793-0,NX8048P070_011C", "shift-jis")
        self.assertIn("built in shift-jis.", text)
        self.assertIn("| nothing | **yes** |", text)
        self.assertIn("The bugs that the screen no longer shows:\n\n"
                      "- %s\n  - nxwright's code that matches the bug: "
                      "`counted_characters` in `nxwright/project/zi_font.py`.\n"
                      % counting.what, text)
        self.assertNotIn(bugs[1].what, text)

    def run_main(self, screen: ScreenOnAPort, report_file: Path) -> tuple:
        """Runs the probe's command with `screen` on its port, and returns
        its exit code and what it printed."""
        printed = io.StringIO()
        on_the_port = mock.patch("tools.screen.ram_probe.SerialExchange",
                                 lambda port, baud, quiet: screen)
        with on_the_port, contextlib.redirect_stdout(printed), \
                contextlib.redirect_stderr(printed):
            code = main(["COM9", "--report", str(report_file)])
        return code, printed.getvalue()

    def test_the_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_file = Path(temporary) / "report.md"
            screen = ScreenOnAPort()
            code, printed = self.run_main(screen, report_file)
            shown = len(bugs_in(ENCODING))
            self.assertEqual(code, 0)
            self.assertEqual(printed, "The screen shows each of the %d bugs checked. The report "
                                      "is in %s.\n" % (shown, report_file))
            text = report_file.read_text(encoding="utf-8")
            self.assertIn("`comok 2,1793-0,NX8048P070_011C`", text)
            self.assertTrue(text.endswith("The screen shows each of the %d bugs checked.\n"
                                          % shown))
            self.assertTrue(screen.closed)

    def test_the_command_with_no_screen_on_the_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            report_file = Path(temporary) / "report.md"
            screen = ScreenOnAPort(answering=False)
            code, printed = self.run_main(screen, report_file)
            self.assertEqual(code, 1)
            self.assertEqual(printed,
                             "firmware_bug_probe: no screen answered on COM9 at 9600 baud\n")
            self.assertFalse(report_file.exists())
            self.assertTrue(screen.closed)


if __name__ == "__main__":
    unittest.main()
