"""The MCU port of a project's MCU emulator, for a simulation's serial line.

An MCU emulator is a Python program that emulates the microcontroller at the
other end of the screen's serial line (nxwright/mcu.py). An EmulatorPort
listens for it on this computer, on a port number the system picks, for as
long as the port is the simulation's MCU port. Whatever program connects is
the emulator. When that program leaves, the port keeps listening, and the
next program to connect takes its place. So the emulator can be started
again while the app keeps running.

A SerialLink (serial_port.py) reads and writes an EmulatorPort with the same
four methods as a serial port: `read`, `write`, `set_rate`, and `close`.
Programs can come and go behind these methods. While no program is
connected, a read returns nothing and a write drops its bytes, the same as
on a serial line with nothing at its other end.
"""
import select
import socket
import threading

from nxwright.debug_adapter.tcp_port import SocketPort

# How long a read waits for a program to connect, in seconds, while no
# emulator is connected.
_READ_WAIT = 0.01


class EmulatorPort:
    """A port that listens for a project's MCU emulator on this computer's
    own address, which no other computer can reach. `address` is where it
    listens, written as host:port, such as 127.0.0.1:53124.

    The port calls `changed(True)` when an emulator connects, and
    `changed(False)` when the emulator leaves, on the thread that reads the
    port. One emulator is connected at a time: another program that connects
    meanwhile is turned away. Raises OSError if the port cannot listen."""

    def __init__(self, changed):
        self._changed = changed
        self._listening = socket.create_server(("127.0.0.1", 0))
        self._listening.setblocking(False)
        self.address = "127.0.0.1:%d" % self._listening.getsockname()[1]
        # Held while `_emulator` is replaced, and while a write uses it, so
        # that a write never uses a connection that is closing.
        self._lock = threading.Lock()
        self._emulator = None        # the SocketPort of the emulator connected, if any

    def read(self) -> bytes:
        """Returns what the emulator sent, waiting a little for a first byte.
        Returns nothing while no emulator is connected. A read is also where
        the port notices that a program connected, or that the emulator
        left."""
        self._accept()
        emulator = self._emulator
        if emulator is None:
            return b""
        try:
            return emulator.read()
        except OSError:
            self._leave()
            return b""

    def write(self, data: bytes) -> int:
        """Writes `data` to the emulator, and returns how many of its bytes
        were written. While no emulator is connected, the bytes are dropped,
        and count as written."""
        with self._lock:
            if self._emulator is None:
                return len(data)
            try:
                return self._emulator.write(data)
            except OSError:
                # The emulator left. The next read notices it.
                return len(data)

    def set_rate(self, rate: int):
        """Does nothing: the connection to the emulator has no rate."""

    def close(self):
        with self._lock:
            if self._emulator is not None:
                self._emulator.close()
                self._emulator = None
        self._listening.close()

    def _accept(self):
        """Accepts a program that is waiting to connect, if there is one. The
        program becomes the emulator, unless an emulator is already
        connected, in which case the new program is turned away. While no
        emulator is connected, waits a little for a program to connect."""
        wait = _READ_WAIT if self._emulator is None else 0
        readable, _, _ = select.select([self._listening], [], [], wait)
        if not readable:
            return
        try:
            connection, _ = self._listening.accept()
        except OSError:
            return
        if self._emulator is not None:
            connection.close()
            return
        with self._lock:
            self._emulator = SocketPort(connection)
        self._changed(True)

    def _leave(self):
        """Closes the connection of the emulator that left."""
        with self._lock:
            self._emulator.close()
            self._emulator = None
        self._changed(False)
