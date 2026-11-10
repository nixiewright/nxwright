"""The screen's serial line for an MCU emulator (nxwright/mcu.py), against a
socket that stands in for the simulation."""
import os
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import nxwright
from nxwright import mcu

END = b"\xff\xff\xff"
# How long a test waits for something that should happen at once, in seconds.
_PATIENCE = 10


def free_port() -> int:
    """Returns the number of a port of this computer that nothing listens on."""
    with socket.create_server(("127.0.0.1", 0)) as listening:
        return listening.getsockname()[1]


class LineTestCase(unittest.TestCase):
    """A Line, with the simulation's end of its connection in `simulation`."""

    def setUp(self):
        listening = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(listening.close)
        address = "127.0.0.1:%d" % listening.getsockname()[1]
        with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: address}):
            self.line = mcu.open()
        self.addCleanup(self.line.close)
        self.simulation, _ = listening.accept()
        self.simulation.settimeout(_PATIENCE)
        self.addCleanup(self.simulation.close)

    def sent_to_simulation(self, count: int) -> bytes:
        data = b""
        while len(data) < count:
            data += self.simulation.recv(count - len(data))
        return data


class OpenTest(unittest.TestCase):

    def test_it_connects_to_the_address_the_variable_gives(self):
        with socket.create_server(("127.0.0.1", 0)) as listening:
            address = "127.0.0.1:%d" % listening.getsockname()[1]
            with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: address}):
                with mcu.open() as line:
                    simulation, _ = listening.accept()
                    with simulation:
                        simulation.sendall(b"\x88" + END)
                        self.assertEqual(line.read_until(END), b"\x88" + END)

    def test_the_variable_comes_before_a_port_to_listen_on(self):
        with socket.create_server(("127.0.0.1", 0)) as listening:
            address = "127.0.0.1:%d" % listening.getsockname()[1]
            with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: address}):
                with mcu.open(listen=free_port()):
                    listening.accept()[0].close()

    def test_given_a_port_it_waits_for_the_simulator_to_connect(self):
        port = free_port()
        opened = []
        with mock.patch.dict(os.environ):
            os.environ.pop(mcu.ADDRESS_VARIABLE, None)
            waiting = threading.Thread(target=lambda: opened.append(mcu.open(listen=port)))
            waiting.start()
            simulation = None
            deadline = time.monotonic() + _PATIENCE
            while simulation is None and time.monotonic() < deadline:
                try:
                    simulation = socket.create_connection(("127.0.0.1", port), timeout=1)
                except OSError:
                    time.sleep(0.01)
            waiting.join(_PATIENCE)
        self.assertIsNotNone(simulation)
        self.addCleanup(simulation.close)
        line = opened[0]
        self.addCleanup(line.close)
        self.assertEqual(line.write(b"page 1" + END), 9)
        simulation.settimeout(_PATIENCE)
        self.assertEqual(simulation.recv(9), b"page 1" + END)
        # The port no longer listens, because a line has only one simulation
        # at its other end.
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)

    def test_with_neither_it_says_what_to_give(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(mcu.ADDRESS_VARIABLE, None)
            with self.assertRaises(OSError) as raised:
                mcu.open()
        self.assertIn("NXWRIGHT_MCU gives no address", str(raised.exception))
        self.assertIn("open(listen=7000)", str(raised.exception))

    def test_an_address_nothing_listens_at(self):
        address = "127.0.0.1:%d" % free_port()
        with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: address}):
            with self.assertRaises(OSError) as raised:
                mcu.open()
        self.assertIn("could not connect to the simulation at %s" % address,
                      str(raised.exception))

    def test_an_address_that_is_not_one(self):
        with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: "COM4"}):
            with self.assertRaises(OSError) as raised:
                mcu.open()
        self.assertIn("could not connect to the simulation at COM4", str(raised.exception))


class ReadTest(LineTestCase):

    def test_a_read_waits_for_all_the_bytes_asked_for(self):
        self.simulation.sendall(b"\x65\x00")
        threading.Timer(0.05, self.simulation.sendall, [b"\x02\x01" + END]).start()
        self.assertEqual(self.line.read(7), b"\x65\x00\x02\x01" + END)

    def test_a_read_takes_no_more_than_asked_for(self):
        self.simulation.sendall(b"abcdef")
        self.assertEqual(self.line.read(2), b"ab")
        self.assertEqual(self.line.read(), b"c")
        self.assertEqual(self.line.read(3), b"def")

    def test_a_read_returns_what_came_once_its_timeout_has_passed(self):
        self.line.timeout = 0.05
        self.simulation.sendall(b"ab")
        started = time.monotonic()
        self.assertEqual(self.line.read(5), b"ab")
        self.assertGreaterEqual(time.monotonic() - started, 0.04)
        self.assertEqual(self.line.read(5), b"")

    def test_a_timeout_of_zero_does_not_wait(self):
        self.line.timeout = 0
        started = time.monotonic()
        self.assertEqual(self.line.read(5), b"")
        self.assertLess(time.monotonic() - started, 1)

    def test_read_until_stops_after_what_it_looks_for(self):
        self.simulation.sendall(b"\x88" + END + b"\x65\x00\x02\x01" + END + b"\x01")
        self.assertEqual(self.line.read_until(END), b"\x88" + END)
        self.assertEqual(self.line.read_until(END), b"\x65\x00\x02\x01" + END)
        self.line.timeout = 0.05
        self.assertEqual(self.line.read_until(END), b"\x01")

    def test_read_until_looks_for_a_line_feed_by_default(self):
        self.simulation.sendall(b"first\nsecond\n")
        self.assertEqual(self.line.read_until(), b"first\n")

    def test_read_until_returns_no_more_than_its_size(self):
        self.simulation.sendall(b"abcdef" + END)
        self.assertEqual(self.line.read_until(END, 4), b"abcd")
        self.assertEqual(self.line.read_until(END, 4), b"ef\xff\xff")
        # The FF that is left is not a whole END, so read_until waits for more.
        self.line.timeout = 0.05
        self.assertEqual(self.line.read_until(END, 4), b"\xff")

    def test_in_waiting_counts_the_bytes_a_read_would_return_at_once(self):
        self.assertEqual(self.line.in_waiting, 0)
        self.simulation.sendall(b"abc")
        deadline = time.monotonic() + _PATIENCE
        while self.line.in_waiting < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.line.in_waiting, 3)
        self.assertEqual(self.line.read(1), b"a")
        self.assertEqual(self.line.in_waiting, 2)


class WriteTest(LineTestCase):

    def test_a_write_sends_its_bytes_as_they_are(self):
        data = b't0.txt="caf\xe9"' + END
        self.assertEqual(self.line.write(data), len(data))
        self.assertEqual(self.sent_to_simulation(len(data)), data)


class ClosingTest(LineTestCase):

    def test_what_came_before_the_simulation_closed_is_still_read(self):
        self.simulation.sendall(b"ab")
        self.simulation.close()
        self.assertEqual(self.line.read(5), b"ab")
        with self.assertRaises(mcu.LineClosed):
            self.line.read(5)
        with self.assertRaises(mcu.LineClosed):
            self.line.read_until(END)

    def test_a_write_fails_once_the_simulation_closed(self):
        self.simulation.close()
        with self.assertRaises(mcu.LineClosed):
            # The system may accept the first writes before it notices that
            # the simulation closed.
            for _ in range(100):
                self.line.write(b"page 1" + END)
                time.sleep(0.01)

    def test_in_waiting_is_zero_once_the_simulation_closed(self):
        self.simulation.close()
        self.assertEqual(self.line.in_waiting, 0)

    def test_a_with_block_closes_the_line(self):
        with self.line:
            pass
        self.simulation.settimeout(_PATIENCE)
        self.assertEqual(self.simulation.recv(1), b"")


class SleepTest(LineTestCase):

    def test_sleep_waits(self):
        started = time.monotonic()
        self.line.sleep(0.05)
        self.assertGreaterEqual(time.monotonic() - started, 0.04)


class ImportTest(unittest.TestCase):

    def test_the_module_loads_only_the_standard_library(self):
        # An emulator's own Python environment may lack what the rest of
        # nxwright needs. So importing nxwright.mcu may load only modules of
        # Python's standard library, the nxwright package, and nxwright.mcu
        # itself. What Python loads when it starts does not count.
        def loaded(statement: str) -> set:
            listing = statement + "; import sys; print('\\n'.join(sorted(sys.modules)))"
            output = subprocess.run([sys.executable, "-c", listing], capture_output=True,
                                    text=True, check=True,
                                    cwd=Path(nxwright.__file__).parent.parent).stdout
            return set(output.split())
        added = loaded("import nxwright.mcu") - loaded("pass")
        others = sorted(name for name in added - {"nxwright", "nxwright.mcu"}
                        if name.partition(".")[0] not in sys.stdlib_module_names)
        self.assertEqual(others, [])


class InterruptTest(unittest.TestCase):
    """Ctrl+C stops a program that waits on the line. On Windows, Ctrl+C does
    not interrupt a wait in the operating system, and Python acts on Ctrl+C
    only once the wait returns, so a single wait with no end would never be
    stopped."""

    def interrupted(self, waiting: str) -> subprocess.CompletedProcess:
        """Runs a program whose main thread is interrupted, as by Ctrl+C,
        while it runs the statements `waiting`."""
        program = ("import _thread, socket, threading\n"
                   "from nxwright import mcu\n"
                   "threading.Timer(0.5, _thread.interrupt_main).start()\n" + waiting)
        return subprocess.run([sys.executable, "-c", program], capture_output=True, text=True,
                              timeout=_PATIENCE, cwd=Path(nxwright.__file__).parent.parent,
                              env={**os.environ, mcu.ADDRESS_VARIABLE: ""})

    def test_while_it_waits_for_the_simulator_to_connect(self):
        done = self.interrupted("mcu.open(listen=%d)\n" % free_port())
        self.assertIn("KeyboardInterrupt", done.stderr)

    def test_while_a_read_waits_without_a_timeout(self):
        done = self.interrupted(
            "listening = socket.create_server(('127.0.0.1', %d))\n"
            "simulation = socket.create_connection(listening.getsockname())\n"
            "mcu.Line(listening.accept()[0]).read(1)\n" % free_port())
        self.assertIn("KeyboardInterrupt", done.stderr)


if __name__ == "__main__":
    unittest.main()
