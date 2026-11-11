"""The demo's MCU emulator (mcu/main.py), and what the app does with the
outdoor temperature it sends."""
import contextlib
import importlib.util
import io
import re
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from nxwright.testing import run_with_emulator

from screen import APP
from test_library import MODE_COOL, MODE_OFF, RUN_IDLE, number_of

EMULATOR = Path(__file__).resolve().parent.parent / "mcu" / "main.py"
# The value of `outdoor` until an MCU sends one (pages/lib/constants.nx).
OUTDOOR_UNKNOWN = 100000
# How long the test waits for the emulator, in seconds.
PATIENCE = 10


def connected_to(port: int) -> socket.socket:
    """Returns a connection to the emulator that listens on `port` of this
    computer, trying again for up to PATIENCE seconds while the connection is
    refused. The emulator prints that it is waiting for the simulator just
    before it starts to listen, so the first attempt can come too early."""
    deadline = time.monotonic() + PATIENCE
    while True:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=PATIENCE)
        except ConnectionRefusedError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def emulator():
    """Returns the emulator's module, loaded from its file."""
    spec = importlib.util.spec_from_file_location("thermostat_mcu", EMULATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OutdoorTemperatureTest(unittest.TestCase):
    """Each test takes the room through 12 minutes with nothing running, from
    21.0 degrees. In that time, the room moves a twentieth of the way towards
    the outdoor temperature."""

    def room_after(self, mode: int, outdoor: int) -> int:
        return number_of("r.val = roomAfter(2100, %d, %d, 12)" % (mode, RUN_IDLE), "lib/room.nx",
                         {"outdoor": outdoor})

    def test_the_room_leaks_towards_the_temperature_the_mcu_sent(self):
        self.assertEqual(self.room_after(MODE_OFF, 1500), 2100 - 30)
        self.assertEqual(self.room_after(MODE_OFF, 2500), 2100 + 20)

    def test_the_temperature_sent_counts_whatever_the_mode(self):
        # Cooling would have a hot day outdoors if the MCU had not sent a
        # temperature.
        self.assertEqual(self.room_after(MODE_COOL, 1500), 2100 - 30)

    def test_without_an_mcu_the_outdoors_suits_the_mode(self):
        self.assertEqual(self.room_after(MODE_OFF, OUTDOOR_UNKNOWN), 2100 - 65)
        self.assertEqual(self.room_after(MODE_COOL, OUTDOOR_UNKNOWN), 2100 + 45)


class EmulatorTest(unittest.TestCase):

    def test_the_day_is_warmest_in_the_afternoon_and_coldest_before_dawn(self):
        outdoor_at = emulator().outdoor_at
        self.assertEqual(outdoor_at(15), 1500)
        self.assertEqual(outdoor_at(3), 500)
        self.assertEqual((outdoor_at(9), outdoor_at(21)), (1000, 1000))
        self.assertEqual(outdoor_at(0), outdoor_at(24))

    def test_it_sends_the_outdoor_temperature_and_ends_with_the_simulation(self):
        with socket.create_server(("127.0.0.1", 0)) as listening:
            port = listening.getsockname()[1]
        program = subprocess.Popen([sys.executable, str(EMULATOR), str(port)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(program.kill)
        self.assertEqual(program.stdout.readline(),
                         "Waiting for the simulator on 127.0.0.1:%d\n" % port)
        with connected_to(port) as simulator:
            sent = b""
            while not sent.endswith(b"\xff\xff\xff"):
                sent += simulator.recv(64)
        self.assertTrue(re.fullmatch(rb"outdoor=\d+\xff\xff\xff", sent), sent)
        value = int(sent[len(b"outdoor="):-3])
        self.assertTrue(500 <= value <= 1500, value)
        # The simulator has closed the connection, so the emulator ends at
        # its next reading.
        _, errors = program.communicate(timeout=PATIENCE)
        self.assertEqual((program.returncode, errors), (0, ""))


class EmulatorWithTheAppTest(unittest.TestCase):

    def test_the_app_takes_each_reading_the_emulator_sends(self):
        # The emulator sends a reading when it starts, then one every 5
        # seconds, so three in 12 seconds. It also prints each reading, and
        # the test keeps that output out of the test results.
        with contextlib.redirect_stdout(io.StringIO()):
            run = run_with_emulator(APP, emulator().main, 12)
        readings = re.findall(rb"outdoor=(\d+)\xff\xff\xff", run.received)
        self.assertEqual(len(readings), 3)
        self.assertEqual(run.received,
                         b"".join(b"outdoor=%s\xff\xff\xff" % reading for reading in readings))
        # The readings follow the time of day, so the test does not check
        # their values. It checks only that the app has the last one.
        self.assertEqual(run.value("outdoor"), int(readings[-1]))
        self.assertEqual(run.page, "home")


if __name__ == "__main__":
    unittest.main()
