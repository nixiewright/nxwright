"""The MCU port that listens for a project's MCU emulator
(debug_adapter/emulator_port.py): the port on its own, a SerialLink that
uses it, the port through the debug adapter, and the port joined to a real
screen. The tests connect to the port with the library that an emulator uses
(nxwright/mcu.py). The last tests cover what the language server returns
about a project's MCU emulator."""
import os
import socket
import threading
import time
import unittest
from unittest import mock

from nxwright import mcu
from nxwright.debug_adapter.adapter import _emulator_wait, _seconds
from nxwright.debug_adapter.emulator_port import EmulatorPort
from nxwright.debug_adapter.serial_port import EMULATOR, SerialLink
from nxwright.language_server.file_texts import uri_of
from nxwright.language_server.server import _OWN
from nxwright.source.emulator_adding import add_emulator
from tests.language_server_connection import initialized
from tests.test_folder_check import FolderTestCase
from tests.test_live_debugging import _PATIENCE, LiveTestCase
from tests.test_serial_port import ScreenPortTestCase, wait_until

END = b"\xff\xff\xff"


def emulator_at(address: str) -> mcu.Line:
    """Returns the line of an emulator that connects to `address`, the way a
    program does when NXWRIGHT_MCU gives it that address."""
    with mock.patch.dict(os.environ, {mcu.ADDRESS_VARIABLE: address}):
        line = mcu.open()
    line.timeout = _PATIENCE
    return line


class Reading:
    """Reads a port on a thread of its own, the way a SerialLink reads it,
    and keeps what arrives in `received`."""

    def __init__(self, port):
        self._port = port
        self._stopping = threading.Event()
        self.received = []
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self):
        while not self._stopping.is_set():
            data = self._port.read()
            if data:
                self.received.append(data)

    def stop(self):
        self._stopping.set()
        self._thread.join(_PATIENCE)


class EmulatorPortTest(unittest.TestCase):

    def setUp(self):
        self.changes = []
        self.port = EmulatorPort(self.changes.append)
        self.addCleanup(self.port.close)
        self.reading = Reading(self.port)
        self.addCleanup(self.reading.stop)

    def emulator(self) -> mcu.Line:
        line = emulator_at(self.port.address)
        self.addCleanup(line.close)
        return line

    def test_it_listens_on_this_computer_alone(self):
        self.assertTrue(self.port.address.startswith("127.0.0.1:"))

    def test_bytes_pass_both_ways_once_an_emulator_connects(self):
        line = self.emulator()
        wait_until(lambda: self.changes == [True])
        line.write(b"page 1" + END)
        wait_until(lambda: b"".join(self.reading.received) == b"page 1" + END)
        self.assertEqual(self.port.write(b"\x88" + END), 4)
        self.assertEqual(line.read(4), b"\x88" + END)

    def test_what_is_written_while_no_emulator_is_connected_is_dropped(self):
        self.assertEqual(self.port.write(b"\x88" + END), 4)
        line = self.emulator()
        wait_until(lambda: self.changes == [True])
        self.port.write(b"\x66\x01" + END)
        self.assertEqual(line.read(5), b"\x66\x01" + END)

    def test_an_emulator_that_leaves_can_be_followed_by_another(self):
        first = self.emulator()
        wait_until(lambda: self.changes == [True])
        first.close()
        wait_until(lambda: self.changes == [True, False])
        self.assertEqual(self.port.write(b"dropped"), 7)
        second = self.emulator()
        wait_until(lambda: self.changes == [True, False, True])
        second.write(b"count=3" + END)
        wait_until(lambda: b"".join(self.reading.received) == b"count=3" + END)

    def test_a_second_program_is_turned_away(self):
        first = self.emulator()
        wait_until(lambda: self.changes == [True])
        second = self.emulator()
        with self.assertRaises(mcu.LineClosed):
            second.read(1)
        # The first emulator stays connected.
        self.assertEqual(self.changes, [True])
        self.port.write(b"\x88" + END)
        self.assertEqual(first.read(4), b"\x88" + END)

    def test_a_change_of_rate_does_nothing(self):
        line = self.emulator()
        wait_until(lambda: self.changes == [True])
        self.port.set_rate(115200)
        self.port.write(b"ok")
        self.assertEqual(line.read(2), b"ok")

    def test_closing_it_ends_the_emulators_line_and_stops_listening(self):
        line = self.emulator()
        wait_until(lambda: self.changes == [True])
        self.reading.stop()
        self.port.close()
        with self.assertRaises(mcu.LineClosed):
            line.read(1)
        host, _, number = self.port.address.rpartition(":")
        with self.assertRaises(OSError):
            socket.create_connection((host, int(number)), timeout=1)


class EmulatorLinkTest(unittest.TestCase):
    """A SerialLink whose port listens for the MCU emulator."""

    def setUp(self):
        self.received = []
        self.news = []
        self.link = SerialLink(self.received.append,
                               lambda kind, body: self.news.append((kind, body)), "MCU port")
        self.addCleanup(self.link.disconnect)
        self.link.connect(kind=EMULATOR)
        self.address = self.link.state()["name"]

    def logged(self) -> list:
        return [body for kind, body in self.news if kind == "log"]

    def test_it_is_connected_from_the_moment_it_listens(self):
        self.assertEqual(self.link.state(), {"kind": "emulator", "name": self.address,
                                             "baud": None, "connected": True, "problem": None,
                                             "attached": False})
        self.assertEqual(self.logged(),
                         ["MCU port %s listening for the MCU emulator" % self.address])

    def test_an_emulator_coming_and_going_is_logged_and_shows_in_the_state(self):
        line = emulator_at(self.address)
        wait_until(lambda: self.link.state()["attached"])
        line.write(b"page 1" + END)
        wait_until(lambda: b"".join(self.received) == b"page 1" + END)
        self.assertIsNone(self.link.send(b"\x88" + END))
        self.assertEqual(line.read(4), b"\x88" + END)
        line.close()
        wait_until(lambda: not self.link.state()["attached"])
        # The link stays connected, and what the screen sends is dropped.
        self.assertTrue(self.link.state()["connected"])
        self.assertIsNone(self.link.send(b"\x88" + END))
        self.assertEqual(self.logged()[1:],
                         ["MCU port %s: the MCU emulator connected" % self.address,
                          "MCU port %s: the MCU emulator disconnected" % self.address])
        states = [body for kind, body in self.news if kind == "state"]
        self.assertEqual([state["attached"] for state in states], [False, True, False])

    def test_a_change_of_rate_does_nothing_and_logs_nothing(self):
        self.assertIsNone(self.link.set_rate(115200))
        self.assertEqual(len(self.logged()), 1)

    def test_no_emulator_is_connected_once_the_port_no_longer_listens(self):
        line = emulator_at(self.address)
        self.addCleanup(line.close)
        wait_until(lambda: self.link.state()["attached"])
        self.link.disconnect()
        state = self.link.state()
        self.assertEqual((state["connected"], state["attached"]), (False, False))

    def test_another_port_takes_its_place(self):
        self.link.disconnect()
        self.assertFalse(self.link.state()["connected"])
        self.assertEqual(self.logged()[-1], "MCU port %s disconnected" % self.address)
        host, _, number = self.address.rpartition(":")
        with self.assertRaises(OSError):
            socket.create_connection((host, int(number)), timeout=1)


class EmulatorPortSessionTest(LiveTestCase):
    """The emulator's port through the debug adapter."""

    def state(self) -> dict:
        return self.request("nxwright/serialPorts")["body"]["state"]

    def test_a_launch_with_the_emulators_port(self):
        self.launch(serialPort="emulator", emulatorWait=0)
        self.wait_for("nxwright/drawing")
        state = self.state()
        self.assertEqual((state["kind"], state["connected"], state["attached"], state["baud"]),
                         ("emulator", True, False, None))
        line = emulator_at(state["name"])
        self.addCleanup(line.close)
        wait_until(lambda: self.state()["attached"])
        # An instruction that arrives runs, and what the app sends goes out.
        line.write(b"count=3" + END)
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 3)
        self.request("nxwright/press", x=10, y=10)
        self.assertEqual(line.read(7), b"pressed")
        self.assertIn(True, [body.get("attached")
                             for body in self.events("nxwright/serialState")])

    def test_the_app_keeps_running_while_the_emulator_is_started_again(self):
        self.launch(serialPort="emulator", emulatorWait=0)
        self.wait_for("nxwright/drawing")
        address = self.state()["name"]
        first = emulator_at(address)
        wait_until(lambda: self.state()["attached"])
        first.close()
        wait_until(lambda: not self.state()["attached"])
        self.request("nxwright/press", x=10, y=10)
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 11)
        second = emulator_at(address)
        self.addCleanup(second.close)
        wait_until(lambda: self.state()["attached"])
        second.write(b"get count" + END)
        self.assertEqual(second.read(8), b"\x71\x0b\x00\x00\x00" + END)
        self.assertEqual(self.events("terminated"), [])

    def test_the_side_bar_chooses_the_emulators_port(self):
        self.launch()
        self.wait_for("nxwright/drawing")
        answer = self.request("nxwright/serialPort", emulator=True)["body"]["state"]
        self.assertEqual((answer["kind"], answer["connected"], answer["attached"]),
                         ("emulator", True, False))
        self.request("nxwright/serialPort", name="")
        self.assertFalse(self.state()["connected"])

    def test_an_agents_action_needs_the_users_go_while_the_port_listens(self):
        self.launch(serialPort="emulator", emulatorWait=0)
        self.wait_for("nxwright/drawing")
        refused = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True,
                                                   agent=True))
        self.assertFalse(refused["success"])
        self.assertIn("the MCU port listens for the project's MCU emulator",
                      refused["message"])
        allowed = self.reply_to(self.request_later("nxwright/press", x=10, y=10, handled=True,
                                                   agent=True, allowed=True))
        self.assertTrue(allowed["success"])


class EmulatorWaitTest(LiveTestCase):
    """A simulation launched with the emulator's port: the app's start waits
    for an emulator to connect. The app prints "ready" when it starts."""

    def setUp(self):
        super().setUp()
        self.program('int count=0, ticks=0\nprints "ready",0\n\npage page0\n')

    def console(self) -> str:
        """Returns what the adapter wrote to the Debug Console about the
        session, without the simulation's log."""
        return "".join(body["output"] for body in self.events("output")
                       if body.get("category") == "console")

    def listening(self) -> str:
        """Returns the address the emulator's port listens at."""
        return self.wait_for("nxwright/serialState")["name"]

    def assertNotStarted(self):
        self.assertIsNone(self.adapter._live.simulation)
        self.assertEqual(self.events("nxwright/starting"), [])

    def test_the_app_starts_once_the_emulator_connects(self):
        self.launch(serialPort="emulator", emulatorWait=_PATIENCE)
        address = self.listening()
        self.assertIn("Waiting up to %d seconds for the MCU emulator to connect before the app "
                      "starts.\n" % _PATIENCE, self.console())
        self.assertEqual((_seconds(1), _seconds(2.5)), ("1 second", "2.5 seconds"))
        self.assertNotStarted()
        line = emulator_at(address)
        self.addCleanup(line.close)
        # The emulator receives what the app sends when it starts.
        self.assertEqual(line.read(5), b"ready")
        self.wait_for("nxwright/drawing")
        self.assertNotIn("No MCU emulator connected", self.console())

    def test_the_app_starts_without_an_emulator_once_the_wait_is_over(self):
        self.launch(serialPort="emulator", emulatorWait=0.2)
        self.wait_for("nxwright/drawing")
        self.assertIn("No MCU emulator connected within 0.2 seconds, so the app starts without "
                      "one.\n", self.console())
        # An emulator can still connect afterwards.
        line = emulator_at(self.listening())
        self.addCleanup(line.close)
        line.write(b"count=3" + END)
        wait_until(lambda: self.adapter._live.simulation.globals["count"] == 3)

    def test_a_wait_of_zero_starts_the_app_at_once(self):
        self.launch(serialPort="emulator", emulatorWait=0)
        self.wait_for("nxwright/drawing")
        self.assertNotIn("Waiting", self.console())
        self.assertNotIn("No MCU emulator connected", self.console())

    def test_the_projects_wait_is_used_when_the_launch_gives_none(self):
        self.write("app.toml", self.text("app.toml")
                   + '\n[mcu]\nemulator = "../mcu/main.py"\nwait = 0.2\n')
        self.launch(serialPort="emulator")
        self.wait_for("nxwright/drawing")
        self.assertIn("No MCU emulator connected within 0.2 seconds", self.console())

    def test_the_launchs_wait_replaces_the_projects(self):
        self.write("app.toml", self.text("app.toml")
                   + '\n[mcu]\nemulator = "../mcu/main.py"\nwait = %d\n' % _PATIENCE)
        self.assertEqual(_emulator_wait(None, self.root), _PATIENCE)
        self.assertEqual(_emulator_wait(0.5, self.root), 0.5)

    def test_a_project_without_an_emulator_waits_ten_seconds(self):
        self.assertEqual(_emulator_wait(None, self.root), 10)

    def test_a_wait_that_is_not_a_number_of_seconds_stops_the_launch(self):
        self.request("initialize")
        for wait in ("soon", -1, True):
            with self.subTest(wait=wait):
                reply = self.request("launch", sourceFolder=str(self.root),
                                     serialPort="emulator", emulatorWait=wait)
                self.assertFalse(reply["success"])
                self.assertEqual(reply["message"],
                                 "emulatorWait must be a number of seconds, 0 or more, such as 10")

    def test_a_launch_with_another_port_does_not_wait(self):
        self.launch(emulatorWait=_PATIENCE)
        self.wait_for("nxwright/drawing")
        self.assertNotIn("Waiting", self.console())

    def test_starting_again_does_not_wait(self):
        self.launch(serialPort="emulator", emulatorWait=0.2)
        self.wait_for("nxwright/drawing")
        self.request("nxwright/startAgain")
        self.wait_for("nxwright/drawing", 2)
        self.assertEqual(self.console().count("No MCU emulator connected"), 1)

    def test_a_port_that_stops_listening_ends_the_wait(self):
        self.launch(serialPort="emulator", emulatorWait=_PATIENCE)
        self.listening()
        self.assertNotStarted()
        self.request("nxwright/serialPort", name="")
        self.wait_for("nxwright/drawing")
        self.assertNotIn("No MCU emulator connected", self.console())

    def test_an_action_asked_meanwhile_is_done_once_the_app_has_started(self):
        self.launch(serialPort="emulator", emulatorWait=_PATIENCE)
        address = self.listening()
        press = self.request_later("nxwright/press", x=10, y=10, handled=True)
        self.assertEqual(self.replies_to(press), [])
        line = emulator_at(address)
        self.addCleanup(line.close)
        self.assertTrue(self.reply_to(press)["success"])
        self.assertEqual(self.adapter._live.simulation.globals["count"], 11)

    def test_ending_the_session_ends_the_wait(self):
        self.launch(serialPort="emulator", emulatorWait=_PATIENCE)
        self.listening()
        self.request("disconnect")
        self.adapter._live._thread.join(_PATIENCE)
        self.assertFalse(self.adapter._live._thread.is_alive())
        self.assertNotStarted()


class EmulatorBridgeTest(ScreenPortTestCase):
    """The emulator's port joined to a real screen's port (bridge.py). The
    screen's port is a stand-in on COM7 at 9600."""

    def setUp(self):
        super().setUp()
        self.address = self.request("nxwright/serialPort",
                                    emulator=True)["body"]["state"]["name"]
        self.screen = self.connect_screen()

    def join(self):
        self.assertTrue(self.request("nxwright/bridge", on=True)["body"]["bridged"])
        wait_until(lambda: b"get bauds" + END in self.screen.written)
        self.screen.arriving.put(b"\x71" + (9600).to_bytes(4, "little") + END)
        wait_until(lambda: any(line.startswith("bridge: did not pass 71")
                               for line in self.log_lines("console")))

    def bridged(self) -> bool:
        return self.request("nxwright/serialPorts")["body"]["bridged"]

    def test_the_port_can_be_joined_before_an_emulator_connects(self):
        self.join()
        line = emulator_at(self.address)
        self.addCleanup(line.close)
        line.write(b"get n" + END)
        wait_until(lambda: b"get n" + END in b"".join(self.screen.written))
        self.screen.arriving.put(b"\x71\x05\x00\x00\x00" + END)
        self.assertEqual(line.read(8), b"\x71\x05\x00\x00\x00" + END)

    def test_an_emulator_leaving_does_not_end_the_join(self):
        self.join()
        first = emulator_at(self.address)
        wait_until(lambda: self.request("nxwright/serialPorts")["body"]["state"]["attached"])
        first.close()
        wait_until(
            lambda: not self.request("nxwright/serialPorts")["body"]["state"]["attached"])
        # What the screen sends meanwhile is dropped, and the join stays.
        self.screen.arriving.put(b"\x65\x00\x02\x01" + END)
        time.sleep(0.1)
        self.assertTrue(self.bridged())
        second = emulator_at(self.address)
        self.addCleanup(second.close)
        second.write(b"page 1" + END)
        wait_until(lambda: b"page 1" + END in b"".join(self.screen.written))
        self.assertTrue(self.bridged())

    def test_choosing_no_port_ends_the_join(self):
        self.join()
        self.request("nxwright/screenPort", name="")
        self.assertFalse(self.bridged())


class EmulatorOfProjectTest(FolderTestCase):
    """What the language server returns about a project's MCU emulator, and
    the server's request that adds one."""

    def request(self, method: str, **params) -> dict:
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": _OWN + method, "params": params})
        return connection.sent[-1]

    def test_a_project_without_an_emulator_names_none(self):
        self.assertNotIn("emulator", self.request("project", folder=str(self.root))["result"])

    def test_a_project_names_its_emulators_file(self):
        file = add_emulator(self.root)
        self.assertEqual(self.request("project", folder=str(self.root))["result"]["emulator"],
                         str(file))

    def test_the_request_adds_an_emulator_and_names_its_file(self):
        document = {"uri": uri_of(self.root / "app.toml")}
        added = self.request("addEmulator", textDocument=document)["result"]
        # The folder comes from the file's URI, whose drive letter may differ in case.
        self.assertTrue((self.root.parent / "mcu" / "main.py").samefile(added["file"]))
        again = self.request("addEmulator", textDocument=document)
        self.assertIn("app.toml already has an [mcu] table", again["error"]["message"])


if __name__ == "__main__":
    unittest.main()
