"""A simulation's serial line on a serial port of the computer.

The Editor's simulator connects the screen's serial line to a serial port
in its "User MCU input" mode, so that a program at the other end talks to
the app; with a virtual pair of ports, such as com0com makes, that program
runs on the same computer. A SerialLink does the same for a running
simulation (live.py):
  - the bytes that arrive go to the simulation as they arrive, in its
    queue, and it cuts them into instructions as the screen does
    (Simulation.serial_received);
  - the bytes the screen sends go to the port, in order (Simulation's
    `sending`).

The port is pyserial's, on any system pyserial supports: 8 data bits, no
parity, 1 stop bit, as the screen's line always is, and no flow control.
"""
import re
import threading

import serial
from serial.tools import list_ports

from nxwright.testing.simulation_log import hex_bytes

# The rates the screen's `baud` takes, as the vendor lists them.
RATES = [2400, 4800, 9600, 19200, 31250, 38400, 57600, 115200, 230400, 250000, 256000,
         512000, 921600]
# The screen's rate at power-on, a port's when none is given.
DEFAULT_RATE = 9600
# How long a read waits for a first byte, in milliseconds.
_READ_WAIT = 10
# How long a write waits for the port to take each of its pieces: this, in
# milliseconds, and the time the piece's bytes take at the port's rate. A
# piece not taken by then ends the write, so that a port nobody reads, which
# com0com holds writes to, cannot hold the simulation.
_WRITE_WAIT = 20
# The bytes of each piece of a write. pyserial's time limit is one figure,
# whatever a write's length, so a write goes in pieces of the same length.
_PIECE = 64


def port_names() -> list:
    """Returns the names of the computer's serial ports, as its system names
    them, such as COM4 on Windows or /dev/ttyUSB0 on Linux, sorted."""
    return sorted((port.device for port in list_ports.comports()), key=_port_order)


def _port_order(name: str):
    """COM2 before COM10."""
    stem, number = re.match(r"(.*?)(\d*)$", name).groups()
    return (stem, int(number) if number else -1)


class SerialPort:
    """An open serial port, through pyserial: `read` returns what arrived,
    waiting a little for a first byte, `write` returns how many bytes the
    port took, and `close` closes it. Raises OSError when the port cannot
    open or fails. Reads and writes may come from two threads: pyserial has
    each in progress on its own, so a write does not wait for a read.

    `name` is the port's name, as its system names it, or a URL that
    pyserial opens, such as loop://, a port that sends back what is
    written to it."""

    def __init__(self, name: str, rate: int):
        if rate <= 0:
            raise OSError("%d is no rate" % rate)
        # A byte is 10 bits on the line.
        piece_time = _PIECE * 10 / rate
        try:
            # pyserial opens a port with DTR and RTS held on.
            self._port = serial.serial_for_url(
                name, baudrate=rate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False,
                timeout=_READ_WAIT / 1000, write_timeout=_WRITE_WAIT / 1000 + piece_time)
        except (serial.SerialException, ValueError) as error:
            raise OSError(_opening_words(error)) from None
        try:
            # What waited in the port from before is not the app's.
            self._port.reset_input_buffer()
            self._port.reset_output_buffer()
        except serial.SerialException:
            self._port.close()
            raise

    def read(self) -> bytes:
        # pyserial's read waits for every byte asked for: those waiting are
        # asked for, or else one, which it waits up to _READ_WAIT for.
        return self._port.read(self._port.in_waiting or 1)

    def write(self, data: bytes) -> int:
        """Writes `data` in pieces of _PIECE bytes. The first piece the port
        does not take in time ends the write: returns the bytes written
        before it."""
        written = 0
        for start in range(0, len(data), _PIECE):
            try:
                written += self._port.write(data[start:start + _PIECE])
            except serial.SerialTimeoutException:
                break
        return written

    def close(self):
        self._port.close()


def _opening_words(error: Exception) -> str:
    """Returns why pyserial could not open a port, without its own "could not
    open port 'COM4': " at the start, which the log's line says already. A
    URL pyserial does not know raises a ValueError, which has no strerror."""
    words = _words(error) if isinstance(error, OSError) else str(error).strip()
    return re.sub(r"^could not open port .*?: ", "", words)


class SerialLink:
    """Joins a serial port to a running simulation, through:
      - `act(work)`, which has the simulation's thread do `work(simulation)`
        in its queue (LiveSimulation.act);
      - `notify(kind, body)`, called from any thread: "state", with the
        port's state as `state` returns it, when it changes; and "log", with
        a line saying what became of the port.
    `send` is the simulation's `sending`. `open_port(name, rate)` opens a
    port, a SerialPort unless given."""

    def __init__(self, act, notify, open_port=SerialPort):
        self._act = act
        self._notify = notify
        self._open_port = open_port
        self._lock = threading.Lock()
        self._connection = None      # the port connected, if any
        self._name = None
        self._rate = DEFAULT_RATE
        self._problem = None         # why the port last chosen is not connected

    def state(self) -> dict:
        with self._lock:
            return {"name": self._name, "baud": self._rate,
                    "connected": self._connection is not None, "problem": self._problem}

    def connect(self, name: str, rate: int = None):
        """Connects the port `name` at `rate`, in place of the one connected.
        A port that cannot open leaves none connected, and says why."""
        self.disconnect(quietly=True)
        rate = rate or DEFAULT_RATE
        try:
            port = self._open_port(name, rate)
        except OSError as error:
            with self._lock:
                self._name, self._rate, self._problem = name, rate, _words(error)
            self._tell("%s could not open: %s" % (name, _words(error)))
            return
        connection = _Connection(port)
        with self._lock:
            self._connection = connection
            self._name, self._rate, self._problem = name, rate, None
        connection.thread = threading.Thread(target=self._read, args=(connection,),
                                             name="serial port", daemon=True)
        connection.thread.start()
        self._tell("connected to %s at %d bits per second" % (name, rate))

    def disconnect(self, quietly: bool = False):
        """Disconnects the port connected, if any, once its last read ends."""
        with self._lock:
            connection, self._connection = self._connection, None
        if connection is None:
            return
        connection.closing.set()
        if connection.thread is not threading.current_thread():
            connection.thread.join()
        if not quietly:
            self._tell("%s disconnected" % self._name)

    def send(self, data: bytes):
        """Writes what the screen sends to the port connected, if any.
        Returns a line for the log when not all of it was sent, or None."""
        with self._lock:
            connection = self._connection
        if connection is None:
            return None
        with connection.writing:
            if connection.closing.is_set():
                return None
            try:
                written = connection.port.write(data)
            except OSError as error:
                return "%s did not send %s: %s" % (self._name, hex_bytes(data), _words(error))
        if written < len(data):
            return "%s did not send %s: the port did not take it in time" % (
                self._name, hex_bytes(data[written:]))
        return None

    def _read(self, connection):
        """The reading thread: hands what arrives to the simulation, until
        the port is disconnected or lost. It closes the port, once no write
        uses it."""
        try:
            while not connection.closing.is_set():
                try:
                    data = connection.port.read()
                except OSError as error:
                    self._lost(connection, error)
                    return
                if data:
                    self._act(lambda simulation, data=data: simulation.serial_received(data))
        finally:
            with connection.writing:
                connection.closing.set()
                connection.port.close()

    def _lost(self, connection, error: OSError):
        with self._lock:
            if self._connection is not connection:
                return          # disconnected meanwhile
            self._connection = None
            self._problem = "lost: %s" % _words(error)
        self._tell("%s lost: %s" % (self._name, _words(error)))

    def _tell(self, line: str):
        self._notify("log", line)
        self._notify("state", self.state())


class _Connection:
    """A port connected, with its reading thread."""

    def __init__(self, port):
        self.port = port
        self.thread = None
        self.closing = threading.Event()
        # Held while writing, and while closing, so that no write meets a
        # closed port.
        self.writing = threading.Lock()


def _words(error: OSError) -> str:
    """An OSError in its system's words, without its number."""
    return (error.strerror or str(error)).strip()
