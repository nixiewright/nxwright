"""A simulation's serial line on a serial port (debug_adapter/serial_port.py):
the link with a stand-in port, through the debug adapter's requests; the
port on pyserial's loop://, which sends back what is written to it; and on a
real pair of ports when the environment names one."""
import os
import queue
import time
import unittest
from unittest import mock

import serial

from nxwright.debug_adapter import adapter as adapter_module
from nxwright.debug_adapter.serial_port import SerialLink, SerialPort, port_names
from tests.test_live_debugging import _PATIENCE, LiveTestCase

# Names a pair of ports joined to each other, such as com0com's
# "CNCA0,CNCB0", for the test on real ports.
_PAIR = os.environ.get("NXWRIGHT_SERIAL_PAIR")


class StandInPort:
    """A port whose arriving bytes the test puts in `arriving`, an OSError
    there failing the read; what the link writes is kept in `written`."""

    def __init__(self, name: str, rate: int):
        self.name, self.rate = name, rate
        self.arriving = queue.Queue()
        self.written = []
        self.taken = None            # how many bytes a write takes; all when None
        self.closed = False

    def read(self) -> bytes:
        try:
            chunk = self.arriving.get(timeout=0.01)
        except queue.Empty:
            return b""
        if isinstance(chunk, OSError):
            raise chunk
        return chunk

    def write(self, data: bytes) -> int:
        self.written.append(data)
        return len(data) if self.taken is None else self.taken

    def close(self):
        self.closed = True


class StandInPorts:
    """Opens StandInPorts, keeping them in `opened`, or refuses with `refusal`."""

    def __init__(self):
        self.opened = []
        self.refusal = None

    def __call__(self, name: str, rate: int) -> StandInPort:
        if self.refusal is not None:
            raise OSError(13, self.refusal)
        port = StandInPort(name, rate)
        self.opened.append(port)
        return port


def wait_until(condition):
    deadline = time.monotonic() + _PATIENCE
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("waited in vain")
        time.sleep(0.01)


class PiecesTaken:
    """Stands in for the simulation the link's work runs on."""

    def __init__(self):
        self.taken = []

    def serial_received(self, data: bytes):
        self.taken.append(data)


class SerialLinkTest(unittest.TestCase):

    def setUp(self):
        self.works = []
        self.news = []
        self.ports = StandInPorts()
        self.link = SerialLink(self.works.append, lambda kind, body: self.news.append((kind, body)),
                               self.ports)
        self.addCleanup(self.link.disconnect)

    def pieces(self, count: int) -> list:
        wait_until(lambda: len(self.works) >= count)
        simulation = PiecesTaken()
        for work in self.works:
            work(simulation)
        return simulation.taken

    def test_bytes_go_to_the_simulation_as_they_arrive(self):
        self.link.connect("COM4", 115200)
        port = self.ports.opened[0]
        self.assertEqual((port.name, port.rate), ("COM4", 115200))
        # The simulation's serial line cuts them (test_serial_line.py).
        chunks = [b"a=1\xff\xff\xffb=2\xff\xff\xffc=", b"3\xff", b"\xff\xff"]
        for chunk in chunks:
            port.arriving.put(chunk)
        self.assertEqual(self.pieces(3), chunks)

    def test_what_the_screen_sends(self):
        self.assertIsNone(self.link.send(b"none connected"))
        self.link.connect("COM4")
        port = self.ports.opened[0]
        self.assertEqual(port.rate, 9600)
        self.assertIsNone(self.link.send(b"ok"))
        port.taken = 1
        self.assertEqual(self.link.send(b"ok"),
                         "COM4 did not send 6b: the port did not take it in time")
        self.assertEqual(port.written, [b"ok", b"ok"])

    def test_changing_the_port_and_disconnecting(self):
        self.link.connect("COM4", 115200)
        self.link.connect("COM5", 9600)
        first, second = self.ports.opened
        self.assertTrue(first.closed)
        self.assertEqual(self.link.state(), {"name": "COM5", "baud": 9600, "connected": True,
                                             "problem": None})
        self.link.disconnect()
        self.assertTrue(second.closed)
        self.assertFalse(self.link.state()["connected"])
        self.assertEqual([body for kind, body in self.news if kind == "log"], [
            "connected to COM4 at 115200 bits per second",
            "connected to COM5 at 9600 bits per second", "COM5 disconnected"])

    def test_a_port_that_cannot_open(self):
        self.ports.refusal = "Access is denied."
        self.link.connect("COM4", 115200)
        self.assertEqual(self.link.state(), {"name": "COM4", "baud": 115200, "connected": False,
                                             "problem": "Access is denied."})
        self.assertIn(("log", "COM4 could not open: Access is denied."), self.news)
        self.assertIn(("state", self.link.state()), self.news)

    def test_a_port_lost_while_open(self):
        self.link.connect("COM4", 115200)
        port = self.ports.opened[0]
        port.arriving.put(OSError(22, "The device does not recognize the command."))
        wait_until(lambda: port.closed)
        state = self.link.state()
        self.assertFalse(state["connected"])
        self.assertEqual(state["problem"], "lost: The device does not recognize the command.")
        self.assertIsNone(self.link.send(b"ok"))


class SerialPortSessionTest(LiveTestCase):
    """The serial port through the debug adapter, with stand-in ports."""

    def setUp(self):
        super().setUp()
        self.ports = StandInPorts()
        patcher = mock.patch.object(adapter_module, "SerialLink",
                                    lambda act, notify: SerialLink(act, notify, self.ports))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_launch_naming_a_port(self):
        self.launch(serialPort={"name": "COM4", "baud": 115200})
        self.wait_for("nxwright/drawing")
        port = self.ports.opened[0]
        self.assertEqual((port.name, port.rate), ("COM4", 115200))
        # An instruction that arrives runs; what the app sends goes out.
        port.arriving.put(b"count=3\xff\xff\xff")
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 3)
        self.request("nxwright/press", x=10, y=10)
        wait_until(lambda: b"pressed" in port.written)
        self.assertIn("receives count=3", self.wait_for_log())

    def test_bytes_arriving_while_paused_wait_outside_the_serial_buffer(self):
        # More than the screen's 1024 bytes arrive while the debugger has
        # paused the simulation. They wait in its queue, and each runs once
        # it resumes: a pause does not change what the app does.
        self.launch(serialPort={"name": "COM4"})
        self.wait_for("nxwright/drawing")
        port = self.ports.opened[0]
        self.request("pause")
        self.wait_for("stopped")
        for _ in range(100):
            port.arriving.put(b"count=count+1\xff\xff\xff")
        wait_until(port.arriving.empty)
        self.request("continue")
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 100)
        self.assertNotIn(b"\x24\xff\xff\xff", port.written)

    def test_the_side_bar_changes_the_port(self):
        self.launch()
        # The side bar hears the port's state at launch, connected or not.
        self.assertFalse(self.wait_for("nxwright/serialState")["connected"])
        self.wait_for("nxwright/drawing")
        offered = self.request("nxwright/serialPorts")["body"]
        self.assertEqual(set(offered), {"ports", "rates", "state"})
        self.assertIn(115200, offered["rates"])
        self.assertEqual(offered["ports"], port_names())
        self.assertFalse(offered["state"]["connected"])
        answer = self.request("nxwright/serialPort", name="COM4", baud=57600)["body"]
        self.assertEqual(answer["state"], {"name": "COM4", "baud": 57600, "connected": True,
                                           "problem": None})
        self.assertTrue(self.wait_for("nxwright/serialState", 2)["connected"])
        self.request("nxwright/serialPort", name="")
        self.assertTrue(self.ports.opened[0].closed)
        self.assertFalse(self.wait_for("nxwright/serialState", 3)["connected"])

    def test_a_port_that_cannot_open_leaves_the_simulation_running(self):
        self.ports.refusal = "Access is denied."
        self.launch(serialPort={"name": "COM4"})
        self.wait_for("nxwright/drawing")
        connection = [body["output"] for body in self.events("output")
                      if body["category"] == "console"]
        self.assertTrue(connection[0].endswith("COM4 could not open: Access is denied.\n"))
        self.assertEqual(self.events("terminated"), [])

    def test_a_port_named_wrongly_is_refused(self):
        self.request("initialize")
        reply = self.request("launch", sourceFolder=str(self.root), serialPort="COM4")
        self.assertFalse(reply["success"])

    def test_an_agents_action_needs_the_users_go_while_a_port_is_connected(self):
        # What the app sends would reach the device on the port: the user
        # says whether an agent may act, and the extension marks its
        # requests `allowed` once the user agreed.
        self.launch(serialPort={"name": "COM4", "baud": 115200})
        self.wait_for("nxwright/drawing")
        port = self.ports.opened[0]
        self.sequence += 1
        self.adapter.handle({"type": "request", "seq": self.sequence, "command": "nxwright/press",
                             "arguments": {"x": 10, "y": 10, "handled": True, "agent": True}})
        refused = self.sequence
        wait_until(lambda: any(message.get("request_seq") == refused for message in self.sent))
        reply = next(message for message in self.sent if message.get("request_seq") == refused)
        self.assertFalse(reply["success"])
        self.assertIn("COM4", reply["message"])
        self.assertEqual(self.adapter._live.simulation.globals["count"], 0)
        self.sequence += 1
        self.adapter.handle({"type": "request", "seq": self.sequence, "command": "nxwright/press",
                             "arguments": {"x": 10, "y": 10, "handled": True, "agent": True,
                                           "allowed": True}})
        allowed = self.sequence
        wait_until(lambda: any(message.get("request_seq") == allowed for message in self.sent))
        self.assertEqual(self.adapter._live.simulation.globals["count"], 11)
        wait_until(lambda: b"pressed" in b"".join(port.written))

    def test_disconnecting_the_session_closes_the_port(self):
        self.launch(serialPort={"name": "COM4", "baud": 115200})
        self.wait_for("nxwright/drawing")
        self.request("disconnect")
        self.assertTrue(self.ports.opened[0].closed)


class RefusingPort:
    """A stand-in for pyserial's port that takes the first `taken` writes,
    then refuses the next as not taken in time; what it was given is kept."""

    def __init__(self, taken: int):
        self.taken = taken
        self.given = []

    def write(self, data: bytes) -> int:
        self.given.append(data)
        if len(self.given) > self.taken:
            raise serial.SerialTimeoutException("Write timeout")
        return len(data)

    def reset_input_buffer(self):
        pass

    def reset_output_buffer(self):
        pass

    def close(self):
        pass


class SerialPortTest(unittest.TestCase):
    """The port through pyserial, on its loop://: what is written comes back."""

    def setUp(self):
        self.port = SerialPort("loop://", 115200)
        self.addCleanup(self.port.close)

    def test_one_read_takes_all_that_waits(self):
        self.assertEqual(self.port.write(b"get t0.txt\xff\xff\xff"), 13)
        self.assertEqual(self.port.read(), b"get t0.txt\xff\xff\xff")

    def test_a_read_with_nothing_waiting_returns_nothing_after_its_wait(self):
        self.assertEqual(self.port.read(), b"")

    def test_a_long_write_goes_in_pieces(self):
        data = bytes(range(200))
        self.assertEqual(self.port.write(data), 200)
        self.assertEqual(self.port.read(), data)

    def test_a_piece_not_taken_in_time_ends_the_write(self):
        refusing = RefusingPort(taken=1)
        with mock.patch.object(serial, "serial_for_url", return_value=refusing):
            port = SerialPort("COM4", 9600)
        data = bytes(range(150))
        self.assertEqual(port.write(data), 64)
        self.assertEqual(refusing.given, [data[:64], data[64:128]])

    def test_a_port_that_cannot_open_says_why(self):
        refusal = serial.SerialException(
            "could not open port 'COM4': PermissionError(13, 'Access is denied.', None, 5)")
        with mock.patch.object(serial, "serial_for_url", side_effect=refusal):
            with self.assertRaises(OSError) as raised:
                SerialPort("COM4", 9600)
        self.assertEqual(str(raised.exception),
                         "PermissionError(13, 'Access is denied.', None, 5)")

    def test_a_url_pyserial_does_not_know_says_why(self):
        with self.assertRaises(OSError):
            SerialPort("nosuch://port", 9600)


@unittest.skipUnless(_PAIR, "NXWRIGHT_SERIAL_PAIR names no pair of ports")
class RealPortsTest(LiveTestCase):
    """The app on one port of a pair, the test at the other end."""

    def test_an_instruction_runs_and_its_reply_comes_back(self):
        theirs, ours = _PAIR.split(",")
        self.launch(serialPort={"name": ours, "baud": 115200})
        self.wait_for("nxwright/drawing")
        other_end = SerialPort(theirs, 115200)
        self.addCleanup(other_end.close)
        other_end.write(b"count=3\xff\xff\xffget count\xff\xff\xff")
        received = b""
        deadline = time.monotonic() + _PATIENCE
        while len(received) < 8 and time.monotonic() < deadline:
            received += other_end.read()
        self.assertEqual(received, b"\x71\x03\x00\x00\x00\xff\xff\xff")


if __name__ == "__main__":
    unittest.main()
