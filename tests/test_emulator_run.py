"""An app run with its MCU emulator on the simulation's clock
(nxwright/testing/emulator_run.py). The app sends "ready" when it starts,
and the timer "tick" of its first page, page0, then sends "t" every second.
Each test's emulator is a function written in the test."""
import sys
import time
import unittest

from nxwright import NxwrightError, mcu
from nxwright.source.emulator_adding import add_emulator
from nxwright.testing import run_with_emulator
from nxwright.testing.emulator_run import _MOST_CALLS_WITHOUT_WAITING
from tests.test_simulation import SimulationTestCase, table

END = b"\xff\xff\xff"


class EmulatorRunTestCase(SimulationTestCase):

    def setUp(self):
        super().setUp()
        self.program('int count=0\nprints "ready",0\n\npage page0\n')
        self.page("page0", [table("tick", "timer", tim=1000, en=1)],
                  'on tick.timer:\n  prints "t",0\n')
        self.page("second", [])

    def run_with(self, main, seconds: float = 10):
        return run_with_emulator(self.root, main, seconds)


class LineTest(EmulatorRunTestCase):
    """The line that mcu.open gives the emulator."""

    def test_what_the_app_sends_when_it_starts_waits_for_the_first_read(self):
        read = []

        def main():
            with mcu.open() as line:
                read.append(line.read(5))

        self.run_with(main)
        self.assertEqual(read, [b"ready"])

    def test_the_screen_runs_what_the_emulator_writes(self):
        written = []

        def main():
            line = mcu.open(listen=7000)
            written.append(line.write(b"count=3" + END))
            written.append(line.write(b"page second" + END))

        run = self.run_with(main)
        self.assertEqual(written, [10, 14])
        self.assertEqual((run.value("count"), run.page), (3, "second"))
        self.assertEqual(run.received, b"count=3" + END + b"page second" + END)

    def test_a_read_waits_on_the_simulations_clock_and_takes_no_real_time(self):
        read = []

        def main():
            line = mcu.open()
            line.read(5)
            read.append(line.read(3))
            read.append(line.in_waiting)

        started = time.monotonic()
        self.run_with(main, 3600)
        self.assertEqual(read, [b"ttt", 0])
        self.assertLess(time.monotonic() - started, 60)

    def test_a_read_returns_what_has_come_once_its_timeout_has_passed(self):
        read = []

        def main():
            line = mcu.open()
            line.read(5)
            line.timeout = 2.5
            read.append(line.read(5))
            # The read ended 2.5 seconds in: the next tick is half a second on.
            line.timeout = 0.4
            read.append(line.read(1))
            line.timeout = 0.2
            read.append(line.read(1))
            line.timeout = 0
            read.append(line.read(1))

        self.run_with(main)
        self.assertEqual(read, [b"tt", b"", b"t", b""])

    def test_read_until_stops_at_what_is_expected(self):
        read = []

        def main():
            line = mcu.open()
            read.append(line.read_until(b"y"))
            read.append(line.read_until(b"t", 1))
            read.append(line.read_until(b"x", 2))

        self.run_with(main)
        self.assertEqual(read, [b"ready", b"t", b"tt"])

    def test_a_sleep_lets_the_simulations_time_pass(self):
        waiting = []

        def main():
            line = mcu.open()
            line.read(5)
            line.sleep(3.2)
            waiting.append(line.in_waiting)
            line.sleep(0.9)
            waiting.append(line.in_waiting)

        self.run_with(main)
        self.assertEqual(waiting, [3, 4])

    def test_a_negative_sleep_raises_ValueError_the_same_as_time_sleep(self):
        def main():
            mcu.open().sleep(-1)

        with self.assertRaisesRegex(ValueError, "sleep length must be non-negative"):
            self.run_with(main)


class EndOfRunTest(EmulatorRunTestCase):
    """What happens once the run's time is over."""

    def test_the_line_closes_and_the_emulator_ends(self):
        read = []

        def main():
            line = mcu.open()
            while True:
                read.append(line.read_until(b"t"))

        run = self.run_with(main, 3.5)
        # The emulator did not catch LineClosed, and run_with_emulator does
        # not raise it to the test.
        self.assertEqual(read, [b"readyt", b"t", b"t"])
        self.assertEqual(run.sent, b"readyttt")

    def test_a_read_returns_the_bytes_left_before_it_raises(self):
        seen = []

        def main():
            line = mcu.open()
            line.sleep(1.5)
            try:
                line.sleep(10)
            except mcu.LineClosed:
                seen.append("sleep")
            seen.append(line.read(100))
            for use in (lambda: line.read(1), lambda: line.write(b"count=1" + END)):
                try:
                    use()
                except mcu.LineClosed:
                    seen.append("closed")

        run = self.run_with(main, 3)
        self.assertEqual(seen, ["sleep", b"readyttt", "closed", "closed"])
        self.assertEqual((run.value("count"), run.received), (0, b""))

    def test_the_app_runs_on_once_the_emulator_has_returned(self):
        run = self.run_with(lambda: None, 4)
        self.assertEqual(run.sent, b"readytttt")

    def test_the_run_still_ends_on_time_after_the_app_starts_again(self):
        # When the app starts again, the simulation's clock starts again
        # from 0. The run must still end 5 seconds after it began.
        def main():
            line = mcu.open()
            line.sleep(2)
            line.write(b"rest" + END)
            line.sleep(60)

        run = self.run_with(main, 5)
        self.assertEqual(run.sent, b"readytt" + b"readyttt")

    def test_an_emulator_that_closes_its_line_leaves_the_app_running(self):
        def main():
            with mcu.open() as line:
                line.read(6)

        self.assertEqual(self.run_with(main, 3).sent, b"readyttt")


class EmulatorFunctionTest(EmulatorRunTestCase):
    """How run_with_emulator runs the emulator's function: what the function
    finds around it, where its errors go, and how a function that never waits
    is stopped."""

    def test_the_emulator_has_no_command_line_arguments_and_mcu_open_is_put_back(self):
        opened, arguments = mcu.open, list(sys.argv)
        seen = []
        self.run_with(lambda: seen.append((list(sys.argv), mcu.open is opened)))
        self.assertEqual(seen, [(arguments[:1], False)])
        self.assertEqual((sys.argv, mcu.open is opened), (arguments, True))

    def test_the_first_program_runs_as_it_is(self):
        # The program that new-emulator writes reads its port number from the
        # command line, and its `main` does not catch LineClosed.
        namespace = {"__name__": "first_emulator"}
        exec(compile(add_emulator(self.root).read_text(encoding="utf-8"), "main.py", "exec"),
             namespace)
        self.assertEqual(self.run_with(namespace["main"], 3).sent, b"readyttt")

    def test_an_error_other_than_LineClosed_reaches_the_test(self):
        def main():
            raise ValueError("no sensor")

        opened = mcu.open
        with self.assertRaisesRegex(ValueError, "no sensor"):
            self.run_with(main)
        self.assertIs(mcu.open, opened)

    def test_an_emulator_that_never_waits_is_stopped(self):
        polls = []

        def main():
            line = mcu.open()
            while not line.in_waiting == 100:
                polls.append(None)

        with self.assertRaises(NxwrightError) as raised:
            self.run_with(main)
        self.assertEqual(len(polls), _MOST_CALLS_WITHOUT_WAITING)
        self.assertEqual(str(raised.exception),
                         "the emulator used the line 100000 times in a row without waiting, so "
                         "the simulation's time cannot pass. Please make the emulator wait "
                         "with line.sleep, or in a read")

    def test_a_loop_that_waits_now_and_then_is_not_stopped(self):
        polls = []

        def main():
            line = mcu.open()
            while True:
                for _ in range(30_000):
                    polls.append(line.in_waiting)
                line.sleep(0.5)

        # In all, the emulator uses the line more times than it may in a row.
        self.run_with(main, 2.5)
        self.assertEqual(len(polls), 150_000)

    def test_a_wait_too_short_to_let_time_pass_counts_as_no_wait(self):
        def main():
            line = mcu.open()
            while True:
                line.sleep(0.0004)

        with self.assertRaises(NxwrightError):
            self.run_with(main)


class ResultTest(EmulatorRunTestCase):

    def test_asking_for_a_value_the_app_does_not_have_raises_an_error(self):
        run = self.run_with(lambda: None, 1)
        self.assertEqual(run.value("tick.tim"), 1000)
        with self.assertRaises(NxwrightError) as raised:
            run.value("nowhere.val")
        self.assertEqual(str(raised.exception),
                         "the app has no value named nowhere.val on the page page0")

    def test_an_app_that_does_not_build_stops_the_test(self):
        self.write("pages/page0.nx", "on tick.timer:\n  nowhere.val = 1\n")
        with self.assertRaises(NxwrightError):
            self.run_with(lambda: None, 1)


if __name__ == "__main__":
    unittest.main()
