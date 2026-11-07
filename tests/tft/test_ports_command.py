"""The ports command (tft/commands/ports.py): the serial ports it lists, with
pyserial's list in place of the computer's, so that no port is opened."""
from contextlib import redirect_stdout
import io
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from nxwright.cli import main

PORTS = [SimpleNamespace(device="COM5", description="USB-SERIAL CH340 (COM5)"),
         SimpleNamespace(device="COM3", description="n/a")]


def run(*arguments: str, ports: list = PORTS) -> tuple:
    """Runs nxwright ports with `arguments`, pyserial listing `ports`, and
    returns its exit code and what it printed."""
    printed = io.StringIO()
    with mock.patch("serial.tools.list_ports.comports", lambda: list(ports)), \
            redirect_stdout(printed):
        code = main(["ports", *arguments])
    return code, printed.getvalue()


class PortsCommandTest(unittest.TestCase):

    def test_each_port_with_its_description(self):
        # Sorted by name; a port pyserial describes as n/a has no description.
        self.assertEqual(run(), (0, "COM3\nCOM5  USB-SERIAL CH340 (COM5)\n"))

    def test_json(self):
        code, printed = run("--json")
        self.assertEqual(code, 0)
        self.assertEqual([json.loads(line) for line in printed.splitlines()],
                         [{"port": "COM3", "description": ""},
                          {"port": "COM5", "description": "USB-SERIAL CH340 (COM5)"}])

    def test_no_port(self):
        self.assertEqual(run(ports=[]), (0, "No serial port was found.\n"))
        self.assertEqual(run("--json", ports=[]), (0, ""))


if __name__ == "__main__":
    unittest.main()
