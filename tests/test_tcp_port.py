"""A simulation's serial line over TCP (debug_adapter/tcp_port.py): the
port against a socket the test listens on, the link with that port, and
the MCU port's kinds through the debug adapter's launch and requests."""
import socket
import unittest

from nxwright import NxwrightError
from nxwright.debug_adapter.serial_port import TCP, SerialLink
from nxwright.debug_adapter.tcp_port import TcpPort, tcp_address
from tests.test_live_debugging import _PATIENCE, LiveTestCase
from tests.test_serial_port import ScreenPortTestCase, wait_until

END = b"\xff\xff\xff"


class Program:
    """The program at the other end: it listens on this computer, on a port
    the system picks, and `accept` returns its side of a connection."""

    def __init__(self, test: unittest.TestCase):
        self._test = test
        self._listening = socket.create_server(("127.0.0.1", 0))
        self._listening.settimeout(_PATIENCE)
        test.addCleanup(self._listening.close)
        self.address = "127.0.0.1:%d" % self._listening.getsockname()[1]

    def accept(self) -> socket.socket:
        connection, _ = self._listening.accept()
        connection.settimeout(_PATIENCE)
        self._test.addCleanup(connection.close)
        return connection

    def stop_listening(self):
        self._listening.close()


def received(connection: socket.socket, count: int) -> bytes:
    """Returns the next `count` bytes that `connection` receives."""
    data = b""
    while len(data) < count:
        data += connection.recv(count - len(data))
    return data


class TcpAddressTest(unittest.TestCase):

    def test_a_host_and_a_port_number(self):
        self.assertEqual(tcp_address("127.0.0.1:7000"), ("127.0.0.1", 7000))
        self.assertEqual(tcp_address("bench.local:65535"), ("bench.local", 65535))

    def test_an_ipv6_host_in_brackets(self):
        self.assertEqual(tcp_address("[::1]:7000"), ("::1", 7000))

    def test_what_is_not_an_address(self):
        for text in ("COM4", "127.0.0.1", ":7000", "127.0.0.1:", "127.0.0.1:0",
                     "127.0.0.1:65536", "127.0.0.1:port", "127.0.0.1:-1", 7000, None):
            with self.subTest(text=text):
                with self.assertRaises(NxwrightError) as raised:
                    tcp_address(text)
                self.assertIn("is not an address", str(raised.exception))


class TcpPortTest(unittest.TestCase):
    """The port against a socket the test listens on."""

    def setUp(self):
        self.program = Program(self)
        self.port = TcpPort(self.program.address)
        self.addCleanup(self.port.close)
        self.other_end = self.program.accept()

    def read(self, count: int) -> bytes:
        """Returns the next `count` bytes the port reads."""
        data = []
        wait_until(lambda: data.append(self.port.read()) or len(b"".join(data)) >= count)
        return b"".join(data)

    def test_bytes_pass_both_ways(self):
        self.assertEqual(self.port.write(b"\x88" + END), 4)
        self.assertEqual(received(self.other_end, 4), b"\x88" + END)
        self.other_end.sendall(b"get n0.val" + END + b"page 1" + END)
        self.assertEqual(self.read(17), b"get n0.val" + END + b"page 1" + END)

    def test_a_read_with_nothing_waiting_returns_nothing_after_its_wait(self):
        self.assertEqual(self.port.read(), b"")

    def test_a_change_of_rate_does_nothing(self):
        self.port.set_rate(115200)
        self.assertEqual(self.port.write(b"ok"), 2)
        self.assertEqual(received(self.other_end, 2), b"ok")

    def test_the_program_closing_its_end_fails_the_next_read(self):
        self.other_end.close()

        def read_fails():
            try:
                self.port.read()
            except OSError as error:
                self.assertIn("closed the connection", str(error))
                return True
            return False
        wait_until(read_fails)

    def test_a_write_the_program_does_not_read_ends(self):
        # The program reads nothing, so the system's buffers fill. A write
        # then gives up on what they do not take, and does not wait for the
        # program.
        data = bytes(1024 * 1024)
        taken = [self.port.write(data)]
        while taken[-1] == len(data) and len(taken) < 256:
            taken.append(self.port.write(data))
        self.assertLess(taken[-1], len(data))


class TcpPortOpeningTest(unittest.TestCase):

    def test_no_program_listening(self):
        program = Program(self)
        program.stop_listening()
        with self.assertRaises(OSError):
            TcpPort(program.address)

    def test_an_address_that_is_not_one(self):
        with self.assertRaises(OSError) as raised:
            TcpPort("COM4")
        self.assertIn("is not an address", str(raised.exception))

    def test_a_host_that_is_not_a_host_name(self):
        # Python does not even look these up: a name with an empty part, and
        # one with a part longer than 63 characters.
        for host in ("bench..lan", "a" * 64):
            with self.subTest(host=host):
                with self.assertRaises(OSError) as raised:
                    TcpPort("%s:7000" % host)
                self.assertEqual(str(raised.exception), "%r is not a valid host name." % host)


class TcpLinkTest(unittest.TestCase):
    """A SerialLink whose port is a TCP connection."""

    def setUp(self):
        self.program = Program(self)
        self.received = []
        self.news = []
        self.link = SerialLink(self.received.append,
                               lambda kind, body: self.news.append((kind, body)), "MCU port")
        self.addCleanup(self.link.disconnect)

    def logged(self) -> list:
        return [body for kind, body in self.news if kind == "log"]

    def test_connecting_has_no_rate(self):
        self.link.connect(self.program.address, kind=TCP)
        self.program.accept()
        self.assertEqual(self.link.state(), {"kind": "tcp", "name": self.program.address,
                                             "baud": None, "connected": True, "problem": None})
        self.assertEqual(self.logged(), ["MCU port %s connected" % self.program.address])

    def test_bytes_pass_both_ways(self):
        self.link.connect(self.program.address, kind=TCP)
        other_end = self.program.accept()
        other_end.sendall(b"page 1" + END)
        wait_until(lambda: b"".join(self.received) == b"page 1" + END)
        self.assertIsNone(self.link.send(b"\x88" + END))
        self.assertEqual(received(other_end, 4), b"\x88" + END)

    def test_a_change_of_rate_does_nothing_and_logs_nothing(self):
        self.link.connect(self.program.address, kind=TCP)
        self.program.accept()
        self.assertIsNone(self.link.set_rate(115200))
        self.assertIsNone(self.link.state()["baud"])
        self.assertEqual(len(self.logged()), 1)

    def test_the_program_closing_its_end_loses_the_port(self):
        self.link.connect(self.program.address, kind=TCP)
        self.program.accept().close()
        wait_until(lambda: not self.link.state()["connected"])
        self.assertEqual(self.link.state()["problem"],
                         "lost: the program at the other end closed the connection")
        self.assertEqual(self.logged()[-1], "MCU port %s lost: the program at the other end "
                                            "closed the connection" % self.program.address)

    def test_no_program_listening(self):
        self.program.stop_listening()
        self.link.connect(self.program.address, kind=TCP)
        state = self.link.state()
        self.assertEqual((state["kind"], state["name"], state["baud"], state["connected"]),
                         ("tcp", self.program.address, None, False))
        self.assertTrue(state["problem"])
        self.assertTrue(self.logged()[0].startswith(
            "MCU port %s could not open: " % self.program.address))


class McuPortKindsTest(LiveTestCase):
    """The kinds of MCU port through the debug adapter: a program over TCP,
    and none."""

    def setUp(self):
        super().setUp()
        self.program = Program(self)

    def test_a_launch_naming_an_address(self):
        self.launch(serialPort={"tcp": self.program.address})
        other_end = self.program.accept()
        self.wait_for("nxwright/drawing")
        state = self.wait_for("nxwright/serialState")
        self.assertEqual((state["kind"], state["name"], state["baud"], state["connected"]),
                         ("tcp", self.program.address, None, True))
        # An instruction that arrives runs, and what the app sends goes out.
        other_end.sendall(b"count=3" + END)
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 3)
        self.request("nxwright/press", x=10, y=10)
        self.assertEqual(received(other_end, 7), b"pressed")

    def test_a_launch_with_no_port(self):
        for port in ("none", None):
            with self.subTest(port=port):
                reply = self.request("launch", sourceFolder=str(self.root), serialPort=port)
                self.assertTrue(reply["success"])
                self.assertFalse(self.events("nxwright/serialState")[-1]["connected"])

    def test_the_side_bar_connects_an_address(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        answer = self.request("nxwright/serialPort", tcp=self.program.address)["body"]
        self.program.accept()
        self.assertEqual(answer["state"], {"kind": "tcp", "name": self.program.address,
                                           "baud": None, "connected": True, "problem": None})
        self.request("nxwright/serialPort", name="")
        self.assertFalse(self.events("nxwright/serialState")[-1]["connected"])

    def test_an_address_that_is_not_one_leaves_the_simulation_running(self):
        self.launch(serialPort={"tcp": "COM4"})
        self.wait_for("nxwright/drawing")
        state = self.wait_for("nxwright/serialState")
        self.assertEqual((state["kind"], state["name"], state["connected"]),
                         ("tcp", "COM4", False))
        self.assertIn("is not an address", state["problem"])
        console = [body["output"] for body in self.events("output")
                   if body["category"] == "console"]
        self.assertIn("MCU port COM4 could not open: 'COM4' is not an address", console[0])
        self.assertEqual(self.events("terminated"), [])

    def test_a_port_given_wrongly_is_refused(self):
        self.request("initialize")
        for port in ({"tcp": 7000}, {"tcp": self.program.address, "name": "COM4"}, "serial"):
            with self.subTest(port=port):
                reply = self.request("launch", sourceFolder=str(self.root), serialPort=port)
                self.assertFalse(reply["success"])

    def test_an_agents_action_needs_the_users_go_while_a_program_is_connected(self):
        self.launch(serialPort={"tcp": self.program.address})
        self.program.accept()
        self.wait_for("nxwright/drawing")
        refused = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True,
                                                   agent=True))
        self.assertFalse(refused["success"])
        self.assertIn("the program at %s" % self.program.address, refused["message"])
        self.assertEqual(self.adapter._live.simulation.globals["count"], 0)


class TcpBridgeTest(ScreenPortTestCase):
    """The MCU port over TCP joined to a real screen's port (bridge.py). The
    screen's port is a stand-in on COM7 at 9600."""

    def setUp(self):
        super().setUp()
        self.program = Program(self)
        self.request("nxwright/serialPort", tcp=self.program.address)
        self.mcu = self.program.accept()
        self.screen = self.connect_screen()
        self.assertTrue(self.request("nxwright/bridge", on=True)["body"]["bridged"])
        wait_until(lambda: b"get bauds" + END in self.screen.written)
        self.screen.arriving.put(b"\x71" + (9600).to_bytes(4, "little") + END)
        wait_until(lambda: any(line.startswith("bridge: did not pass 71")
                               for line in self.log_lines("console")))

    def test_a_change_of_rate_changes_the_screen_port_alone(self):
        self.mcu.sendall(b"baud=115200" + END)
        wait_until(lambda: self.screen.rates[-1] == 115200)
        # The bridge still runs, and bytes pass both ways at the new rate.
        self.assertTrue(self.request("nxwright/serialPorts")["body"]["bridged"])
        self.assertIsNone(self.request("nxwright/serialPorts")["body"]["state"]["baud"])
        self.mcu.sendall(b"get n" + END)
        wait_until(lambda: b"get n" + END in b"".join(self.screen.written))
        self.assertFalse(any(line.startswith("MCU port") and "bits per second" in line
                             for line in self.log_lines("console")))


if __name__ == "__main__":
    unittest.main()
