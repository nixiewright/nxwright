"""The screen's serial line, for a Python program that emulates the MCU.

On real hardware, a microcontroller (the MCU) sits at the other end of a
Nextion screen's serial line. An MCU emulator is a Python program that takes
the microcontroller's place while the app runs in nxwright's simulator, so
that the app can be tried without the hardware. This module gives that
program the line:

    from nxwright import mcu

    with mcu.open() as line:
        line.write(b'page 1\\xff\\xff\\xff')
        reply = line.read_until(b"\\xff\\xff\\xff")

The line carries bytes as they are. It has the members of pyserial's Serial
that an emulator needs, with the same meaning: `read`, `read_until`,
`write`, `in_waiting`, `timeout`, and `close`. Code written for a serial
port therefore works on the line unchanged.

`open` finds the simulation in one of two ways:
  - If the environment variable NXWRIGHT_MCU gives an address, such as
    127.0.0.1:53124, `open` connects to that address. Whatever starts the
    program sets the variable, to tell it where the simulation is.
  - Otherwise, if a port number to listen on is given, as in
    `open(listen=7000)`, `open` waits for the simulator to connect to that
    port of this computer. In the simulator, connect the MCU port over TCP
    to 127.0.0.1:7000.

To wait, use the line's `sleep` or a read's `timeout`, and do not use
time.sleep. A later version of nxwright may run the app on a simulated
clock, and time.sleep would not follow that clock.

This module uses only Python's standard library, so that an emulator's own
Python environment needs nothing but nxwright.
"""
import os
import select
import socket
import time

# The environment variable that gives the address of the simulation to
# connect to, written as host:port.
ADDRESS_VARIABLE = "NXWRIGHT_MCU"
# How long connecting to the simulation may take, in seconds.
_CONNECT_WAIT = 10.0
# The most bytes taken from the connection at once.
_MOST_READ = 65536
# The longest single wait in the operating system, in seconds. On Windows,
# Ctrl+C does not interrupt such a wait, and Python acts on Ctrl+C only once
# the wait returns. A wait with no end is therefore made of short ones.
_WAIT_STEP = 0.2


class LineClosed(OSError):
    """Raised by a read or a write of a Line once the simulation has closed
    its end, which happens when the simulation stops. An emulator can catch
    it to end."""


class Line:
    """The screen's serial line, over the connection `connection` to the
    simulation. `timeout` is how long a read waits, in seconds: None, the
    default, waits until the bytes have come, and 0 does not wait. A Line is
    also a context manager: a `with` block closes the Line when the block
    ends."""

    def __init__(self, connection: socket.socket):
        self._socket = connection
        # Each write goes out at once. By default, the system would keep a
        # short one back to send it with the next.
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._waiting = bytearray()  # the bytes received and not read yet
        self._over = False           # whether the simulation closed its end
        self.timeout = None

    def read(self, size: int = 1) -> bytes:
        """Returns the next `size` bytes the screen sent. If they have not
        all come once `timeout` has passed, returns those that have, which
        may be none. Raises LineClosed if the simulation closed its end and
        no byte is left to read."""
        deadline = self._deadline()
        while len(self._waiting) < size and self._more(deadline):
            pass
        return self._taken(size)

    def read_until(self, expected: bytes = b"\n", size: int = None) -> bytes:
        """Returns the bytes the screen sent, up to and including the first
        `expected`, such as the FF FF FF that ends each of the screen's
        messages. If `size` is given, returns at most that many bytes. If
        `expected` has not come once `timeout` has passed, returns the bytes
        that have. Raises LineClosed if the simulation closed its end and no
        byte is left to read."""
        deadline = self._deadline()
        while True:
            end = self._waiting.find(expected)
            if end >= 0:
                count = end + len(expected)
                return self._taken(count if size is None else min(count, size))
            if size is not None and len(self._waiting) >= size:
                return self._taken(size)
            if not self._more(deadline):
                return self._taken(len(self._waiting) if size is None else size)

    def write(self, data: bytes) -> int:
        """Sends `data` to the screen, and returns how many bytes that is.
        Raises LineClosed if the simulation closed its end."""
        try:
            self._socket.sendall(data)
        except ConnectionError:
            self._over = True
            raise LineClosed("the simulation closed the line") from None
        return len(data)

    @property
    def in_waiting(self) -> int:
        """How many bytes a read would return without waiting."""
        self._more(time.monotonic())
        return len(self._waiting)

    def sleep(self, seconds: float):
        """Waits for `seconds` seconds. An emulator calls this in place of
        time.sleep, so that a later version of nxwright can make the wait
        follow a simulated clock."""
        time.sleep(seconds)

    def close(self):
        """Closes the line."""
        self._socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.close()

    def _deadline(self):
        """Returns the time at which a read that starts now stops waiting, on
        time.monotonic's clock, or None if the read waits without end."""
        return None if self.timeout is None else time.monotonic() + self.timeout

    def _more(self, deadline) -> bool:
        """Waits until `deadline` for more bytes from the screen, or without
        end if `deadline` is None, and adds them to those waiting. Returns
        whether any came, which is always False once the simulation has
        closed its end."""
        if self._over:
            return False
        while True:
            left = _WAIT_STEP if deadline is None else max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select([self._socket], [], [], min(left, _WAIT_STEP))
            if readable:
                break
            if deadline is not None and time.monotonic() >= deadline:
                return False
        try:
            data = self._socket.recv(_MOST_READ)
        except ConnectionError:
            data = b""
        if not data:
            self._over = True
            return False
        self._waiting += data
        return True

    def _taken(self, count: int) -> bytes:
        """Removes the first `count` bytes from those waiting, or all of them
        if there are fewer, and returns them. Raises LineClosed if none wait
        and none will come."""
        if not self._waiting and self._over:
            raise LineClosed("the simulation closed the line")
        taken = bytes(self._waiting[:count])
        del self._waiting[:count]
        return taken


def open(listen: int = None) -> Line:
    """Returns the screen's serial line, as a Line.

    If the environment variable NXWRIGHT_MCU gives an address, connects to
    the simulation at that address. Otherwise, if `listen` is a port number,
    waits for the simulator to connect to that port of this computer.

    Raises OSError if it cannot connect or listen, or if it is given neither
    an address nor a port to listen on."""
    address = os.environ.get(ADDRESS_VARIABLE)
    if address:
        host, _, number = address.rpartition(":")
        try:
            connection = socket.create_connection((host, int(number)), timeout=_CONNECT_WAIT)
        except (OSError, ValueError) as error:
            raise OSError("could not connect to the simulation at %s, the address that %s "
                          "gives: %s" % (address, ADDRESS_VARIABLE, error)) from None
        # The time limit was for connecting. A Line does its own waiting.
        connection.settimeout(None)
        return Line(connection)
    if listen is not None:
        # Listens on this computer's own address only, so that no other
        # computer can connect.
        with socket.create_server(("127.0.0.1", listen)) as listening:
            listening.settimeout(_WAIT_STEP)
            while True:
                try:
                    connection, _ = listening.accept()
                    break
                except TimeoutError:
                    continue
        connection.settimeout(None)
        return Line(connection)
    raise OSError("no port number to listen on, and the environment variable %s gives no "
                  "address of a simulation. Please provide a port number, as in "
                  "open(listen=7000), then connect the simulator's MCU port to it over TCP"
                  % ADDRESS_VARIABLE)
