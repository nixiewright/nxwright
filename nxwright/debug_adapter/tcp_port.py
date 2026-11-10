"""A TCP connection in place of a serial port, for a simulation's serial line.

The program at the other end of the screen's serial line, called the MCU,
can listen at an address: a host and a port number, such as 127.0.0.1:7000,
on this computer or on another. A TcpPort connects to that address. A
SerialLink (serial_port.py) then reads and writes it with the same four
methods as a serial port: `read`, `write`, `set_rate`, and `close`. So a
program on this computer can be the MCU without a serial port, and without
the virtual pair of ports that com0com creates.

A SocketPort has those four methods for a connection that is already open,
whichever side opened it. The port that listens for a project's MCU
emulator uses one for the emulator that connects (emulator_port.py).

A TCP connection has no rate. Its bytes arrive whatever rate the screen is
set to, so `set_rate` does nothing.
"""
import select
import socket

from nxwright import NxwrightError

# How long each attempt to connect may take, in seconds. A host name can
# stand for several addresses, such as localhost for ::1 and 127.0.0.1, and
# each is tried in turn.
_CONNECT_WAIT = 3.0
# How long a read waits for a first byte, in seconds.
_READ_WAIT = 0.01
# How long a write waits for the connection to take more bytes, in seconds.
# A write that waits longer ends, so that a program that stopped reading
# cannot stop the simulation.
_WRITE_WAIT = 0.02
# The most bytes one read takes.
_MOST_READ = 65536


def tcp_address(text) -> tuple:
    """Returns the (host, port number) of an address written as host:port,
    such as "127.0.0.1:7000" or "[::1]:7000". Raises NxwrightError if `text`
    is not written that way, or if its port number is not from 1 to 65535."""
    host, colon, number = text.rpartition(":") if isinstance(text, str) else ("", "", "")
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not colon or not host or not number.isascii() or not number.isdigit() \
            or not 1 <= int(number) <= 65535:
        raise NxwrightError("%r is not an address. Please provide a host and a port number, "
                            "such as 127.0.0.1:7000" % (text,))
    return host, int(number)


class SocketPort:
    """An open TCP connection, `connection`, to a program at its other end,
    with the methods that SerialLink calls on a port. `read` returns what
    arrived, waiting a little for a first byte, and `write` returns how many
    bytes the connection took. Both raise OSError if the connection fails,
    and a read also raises it once the program has closed its end. A read
    and a write may come from two threads."""

    def __init__(self, connection: socket.socket):
        self._socket = connection
        # Each instruction goes out when it is written. By default, the system
        # would keep a short one back to send it with the next.
        self._socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # Reads and writes wait in `select`, each for its own time. A time
        # limit set on the socket would apply to both.
        self._socket.setblocking(False)

    def read(self) -> bytes:
        readable, _, _ = select.select([self._socket], [], [], _READ_WAIT)
        if not readable:
            return b""
        try:
            data = self._socket.recv(_MOST_READ)
        except BlockingIOError:
            return b""
        if not data:
            raise OSError("the program at the other end closed the connection")
        return data

    def write(self, data: bytes) -> int:
        """Writes `data`, and returns how many of its bytes were written. If
        the connection takes no more bytes for _WRITE_WAIT seconds, the write
        ends there."""
        written = 0
        while written < len(data):
            _, writable, _ = select.select([], [self._socket], [], _WRITE_WAIT)
            if not writable:
                break
            try:
                written += self._socket.send(data[written:])
            except BlockingIOError:
                break
        return written

    def set_rate(self, rate: int):
        """Does nothing: a TCP connection has no rate."""

    def close(self):
        self._socket.close()


class TcpPort(SocketPort):
    """A TCP connection to the program listening at `address`, written as
    host:port. Raises OSError if `address` is not written that way, or if the
    connection cannot open."""

    def __init__(self, address: str):
        try:
            host, number = tcp_address(address)
        except NxwrightError as error:
            raise OSError(str(error)) from None
        try:
            connection = socket.create_connection((host, number), timeout=_CONNECT_WAIT)
        except UnicodeError:
            # A host name with an empty part, such as bench..lan, or with a
            # part longer than 63 characters makes Python raise UnicodeError
            # before it looks the name up. UnicodeError is not an OSError.
            raise OSError("%r is not a valid host name." % host) from None
        super().__init__(connection)
