"""A simulation's serial line on a serial port of the computer, and a real
screen on another.

In its "User MCU input" mode, the Nextion Editor's simulator connects the
screen's serial line to a serial port, so that a program at the other end,
called the MCU, talks to the app. With a virtual pair of ports, such as one
com0com creates, that program can run on the same computer. A SerialLink
does the same for a running simulation (live.py):
  - the bytes that arrive go into the simulation's queue as they arrive,
    and the simulation cuts them into instructions the same way a screen
    does (Simulation.serial_received);
  - the bytes the screen sends go to the port, in order (Simulation's
    `sending`).

A SerialLink can also connect the simulation's serial line to a program
that listens at an address, over TCP (tcp_port.py), or listen for the
project's MCU emulator to connect (emulator_port.py). Neither connection has
a rate.

A second SerialLink connects a real screen beside the simulation, on a port
of its own called the screen port. Instructions typed in the Simulator section can go to the
screen, and LoggedPieces cuts what the screen sends into replies for the
log. screen_rate finds the screen's rate by sending it `connect` at each
rate.

Ports open through pyserial, on any system it supports. They use the
settings of a screen's serial line, which are always 8 data bits, no parity,
and 1 stop bit, with no flow control.
"""
import re
import threading
import time

import serial
from serial.tools import list_ports

from nxwright.debug_adapter.emulator_port import EmulatorPort
from nxwright.debug_adapter.tcp_port import TcpPort
from nxwright.testing.simulation_log import END, hex_bytes
from nxwright.tft.upload import RATES_TRIED, find_screen

# The kinds of port a SerialLink connects. SERIAL is a serial port of the
# computer, given by its name and a rate. TCP is a connection to a program
# that listens at an address. EMULATOR is a port that listens for the
# project's MCU emulator. TCP and EMULATOR have no rate.
SERIAL = "serial"
TCP = "tcp"
EMULATOR = "emulator"

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
# How long, in seconds, the log waits for more bytes from the screen before it
# shows bytes that no FF FF FF has ended. Data in protocol reparse mode, and a
# transfer's data, have no FF FF FF.
_QUIET = 0.1
# The replies of a fixed length, by their first byte, with how many bytes
# follow that byte before the FF FF FF, as the vendor's instruction set
# documents them. They are a touch (0x65), the page's ID (0x66), a touch's
# place (0x67, and 0x68 while asleep), and a number (0x71). Their bytes may be
# FF, as in the reply to `get` of -1, so such a reply cannot be cut at the
# first FF FF FF.
REPLY_LENGTHS = {0x65: 3, 0x66: 1, 0x67: 5, 0x68: 5, 0x71: 4}


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
        try:
            # pyserial opens a port with DTR and RTS held on.
            self._port = serial.serial_for_url(
                name, baudrate=rate, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, xonxoff=False, rtscts=False, dsrdtr=False,
                timeout=_READ_WAIT / 1000, write_timeout=_write_wait(rate))
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

    def set_rate(self, rate: int):
        """Changes the port's rate once everything already written has gone
        out, so that those bytes still go at the old rate. Raises OSError if
        the port refuses the rate."""
        try:
            self._port.flush()
            self._port.baudrate = rate
            self._port.write_timeout = _write_wait(rate)
        except (serial.SerialException, ValueError) as error:
            raise OSError(str(error)) from None

    def close(self):
        self._port.close()


def _write_wait(rate: int) -> float:
    """Returns how long a write waits for the port to take each piece, in
    seconds. That is _WRITE_WAIT, plus the time the piece's bytes take to go
    out at `rate`, at 10 bits a byte."""
    return _WRITE_WAIT / 1000 + _PIECE * 10 / rate


def _opening_words(error: Exception) -> str:
    """Returns why pyserial could not open a port, without its own "could not
    open port 'COM4': " at the start, which the log's line says already. A
    URL pyserial does not know raises a ValueError, which has no strerror."""
    words = _words(error) if isinstance(error, OSError) else str(error).strip()
    return re.sub(r"^could not open port .*?: ", "", words)


class SerialLink:
    """Joins a port to what takes its bytes, through:
      - `received(data)`, called on the port's reading thread with each
        piece of bytes as it arrives;
      - `notify(kind, body)`, called from any thread: "state", with the
        port's state as `state` returns it, when it changes; and "log", with
        a line saying what became of the port.
    `label` names the port in those lines, such as "MCU port". `send` writes
    to the port. `open_port(name, rate)` opens a serial port,
    `open_tcp(address)` opens a connection over TCP, and
    `open_emulator(changed)` opens a port that listens for the MCU emulator.
    By default, they are SerialPort, TcpPort, and EmulatorPort."""

    def __init__(self, received, notify, label: str, open_port=SerialPort, open_tcp=TcpPort,
                 open_emulator=EmulatorPort):
        self._received = received
        self._notify = notify
        self._label = label
        self._open_port = open_port
        self._open_tcp = open_tcp
        self._open_emulator = open_emulator
        self._lock = threading.Lock()
        self._connection = None      # the port connected, if any
        self._kind = SERIAL
        self._name = None
        self._rate = DEFAULT_RATE    # None for a port without a rate
        self._problem = None         # why the port last chosen is not connected
        self._attached = False       # for an emulator's port: whether an emulator is connected

    def state(self) -> dict:
        """Returns the state of the port last chosen, with these keys:
          - `kind`: SERIAL, TCP, or EMULATOR;
          - `name`: the port's name, or the address of a TCP port or of an
            emulator's port;
          - `baud`: the port's rate, or None for a port without one;
          - `connected`: whether the port is connected. An emulator's port
            is connected from the moment it listens;
          - `problem`: why the port is not connected, or None;
          - `attached`, for an emulator's port only: whether an emulator is
            connected to it."""
        with self._lock:
            connected = self._connection is not None
            state = {"kind": self._kind, "name": self._name, "baud": self._rate,
                     "connected": connected, "problem": self._problem}
            if self._kind == EMULATOR:
                # No emulator is connected to a port that no longer listens.
                state["attached"] = connected and self._attached
            return state

    def connect(self, name: str = None, rate: int = None, kind: str = SERIAL):
        """Connects a port, in place of the one connected. `kind` sets what
        `name` and `rate` mean:
          - SERIAL: `name` is a serial port's name, and the port opens at
            `rate`;
          - TCP: `name` is the address of a listening program, and `rate` is
            not used;
          - EMULATOR: neither is used. The port listens for the MCU emulator,
            and its name is the address it listens at.
        If the port cannot open, no port is left connected, and the log and
        the port's state give the reason."""
        self.disconnect(quietly=True)
        rate = (rate or DEFAULT_RATE) if kind == SERIAL else None
        try:
            port = self._opened(name, rate, kind)
        except OSError as error:
            self._failed(name or "Emulator", rate, _words(error),
                         "could not open: %s" % _words(error), kind)
            return
        if kind == EMULATOR:
            name = port.address
        connection = _Connection(port)
        with self._lock:
            self._connection = connection
            self._kind, self._name, self._rate, self._problem = kind, name, rate, None
            self._attached = False
        connection.thread = threading.Thread(target=self._read, args=(connection,),
                                             name="serial port", daemon=True)
        connection.thread.start()
        if kind == EMULATOR:
            self._tell("%s %s listening for the MCU emulator" % (self._label, name))
        else:
            at_rate = "" if rate is None else " at %d bits per second" % rate
            self._tell("%s %s connected%s" % (self._label, name, at_rate))

    def _opened(self, name: str, rate: int, kind: str):
        """Opens the port of the kind `kind`, and returns it. Raises OSError
        if it cannot open."""
        if kind == TCP:
            return self._open_tcp(name)
        if kind == EMULATOR:
            return self._open_emulator(self._emulator_changed)
        return self._open_port(name, rate)

    def _emulator_changed(self, attached: bool):
        """Records and logs that an emulator connected to the emulator's
        port, or left it. Called on the port's reading thread."""
        with self._lock:
            self._attached = attached
            name = self._name
        self._tell("%s %s: the MCU emulator %s"
                   % (self._label, name, "connected" if attached else "disconnected"))

    def find_and_connect(self, name: str, find_rate):
        """Connects the port `name` at the rate that `find_rate(name)`
        returns. Any port already connected is closed first, because
        `find_rate`, such as screen_rate, opens the port itself. Finding the
        rate may take seconds. If the port cannot open, or `find_rate`
        returns None because it found no rate, no port is connected, and the
        log shows why."""
        self.disconnect(quietly=True)
        try:
            rate = find_rate(name)
        except OSError as error:
            self._failed(name, DEFAULT_RATE, _words(error), "could not open: %s" % _words(error))
            return
        if rate is None:
            self._failed(name, DEFAULT_RATE, "no screen answered at any rate",
                         "found no screen at any rate")
            return
        self.connect(name, rate)

    def _failed(self, name: str, rate: int, problem: str, words: str, kind: str = SERIAL):
        """Records that the port `name`, of the kind `kind`, is not connected
        because of `problem`, and logs `words` after the port's label and
        name."""
        with self._lock:
            self._kind, self._name, self._rate, self._problem = kind, name, rate, problem
        self._tell("%s %s %s" % (self._label, name, words))

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
            self._tell("%s %s disconnected" % (self._label, self._name))

    def send(self, data: bytes):
        """Writes `data` to the port connected, if any.
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
                return "%s %s did not send %s: %s" % (self._label, self._name,
                                                      hex_bytes(data), _words(error))
        if written < len(data):
            return "%s %s did not send %s: the port did not take it in time" % (
                self._label, self._name, hex_bytes(data[written:]))
        return None

    def send_whole(self, data: bytes, wait: float):
        """Writes all of `data` to the connected port, and gives the port up
        to `wait` seconds in all to take it. Returns a line for the log if
        the port is not connected or did not take all of `data`, or None if
        it did."""
        deadline = time.monotonic() + wait
        with self._lock:
            connection = self._connection
        if connection is None:
            return "%s did not send %s: it is not connected" % (self._label, hex_bytes(data))
        with connection.writing:
            written = 0
            while written < len(data):
                if connection.closing.is_set():
                    return "%s %s did not send %s: it closed" % (
                        self._label, self._name, hex_bytes(data[written:]))
                try:
                    taken = connection.port.write(data[written:])
                except OSError as error:
                    return "%s %s did not send %s: %s" % (
                        self._label, self._name, hex_bytes(data[written:]), _words(error))
                written += taken
                if written < len(data):
                    if time.monotonic() >= deadline:
                        return "%s %s did not send %s: the port did not take it in %g s" % (
                            self._label, self._name, hex_bytes(data[written:]), wait)
                    if not taken:
                        time.sleep(0.001)
        return None

    def set_rate(self, rate: int):
        """Changes the rate of the port connected, once what was written has
        gone out. Returns a line for the log when it could not, or None. A
        port without a rate, such as a TCP port, stays as it is, and nothing
        is logged."""
        with self._lock:
            connection = self._connection
            has_rate = self._rate is not None
        if connection is None:
            return "%s is not connected" % self._label
        if not has_rate:
            return None
        with connection.writing:
            try:
                connection.port.set_rate(rate)
            except OSError as error:
                return "%s %s could not change to %d bits per second: %s" % (
                    self._label, self._name, rate, _words(error))
        with self._lock:
            self._rate = rate
        self._tell("%s %s now at %d bits per second" % (self._label, self._name, rate))
        return None

    def _read(self, connection):
        """The reading thread: hands what arrives to `received`, until the
        port is disconnected or lost. It closes the port, once no write
        uses it."""
        try:
            while not connection.closing.is_set():
                try:
                    data = connection.port.read()
                except OSError as error:
                    self._lost(connection, error)
                    return
                if data:
                    self._received(data)
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
        self._tell("%s %s lost: %s" % (self._label, self._name, _words(error)))

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


class LoggedPieces:
    """Cuts the bytes a port receives into the pieces the log shows, and
    hands each, with its FF FF FF, to `show(piece)` in order. It hands on:
      - a piece whose first byte is in `lengths`, once all its bytes have
        arrived, even if some of them are FF;
      - any other piece once an FF FF FF ends it;
      - bytes that no FF FF FF ends, as they are, once `quiet` seconds pass
        without more bytes.
    To cut the screen's replies, pass REPLY_LENGTHS. To cut instructions,
    pass an empty dict. `add` takes each piece of bytes as it arrives, on the port's
    reading thread. The bytes still waiting are shown from a timer's
    thread."""

    def __init__(self, show, lengths: dict, quiet: float = _QUIET):
        self._show = show
        self._lengths = lengths
        self._quiet = quiet
        self._lock = threading.Lock()
        self._waiting = b""
        self._timer = None           # the timer that shows the bytes waiting, if any

    def add(self, data: bytes):
        with self._lock:
            self._stop_timer()
            self._waiting += data
            while True:
                end = piece_end(self._waiting, self._lengths)
                if end is None:
                    break
                piece, self._waiting = self._waiting[:end], self._waiting[end:]
                self._show(piece)
            if self._waiting:
                self._timer = threading.Timer(self._quiet, self._show_waiting)
                self._timer.daemon = True
                self._timer.start()

    def stop(self):
        """Drops the bytes still waiting, without showing them."""
        with self._lock:
            self._stop_timer()
            self._waiting = b""

    def _show_waiting(self):
        with self._lock:
            # If a piece arrived just as this timer fired, `add` has already
            # handled the waiting bytes, and has cleared or replaced this
            # timer.
            if self._timer is not threading.current_thread():
                return
            self._timer = None
            waiting, self._waiting = self._waiting, b""
            if waiting:
                self._show(waiting)

    def _stop_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


def piece_end(data: bytes, lengths: dict):
    """Returns where the first piece in `data` ends, just after its FF FF FF,
    or None if it has not ended yet. If the piece's first byte is in
    `lengths`, that many bytes follow it before its FF FF FF, whatever they
    are. Any other piece ends at its first FF FF FF (LoggedPieces)."""
    length = lengths.get(data[0]) if data else None
    if length is not None:
        end = 1 + length + len(END)
        return end if len(data) >= end else None
    end = data.find(END)
    return None if end < 0 else end + len(END)


def screen_rate(name: str):
    """Returns the rate at which a screen on the port `name` answers
    `connect`, or None if it answers at none of the rates tried. It tries
    the same rates as `nxwright upload`, with find_screen from
    tft/upload.py, and at each rate it sends the bytes that end protocol
    reparse mode, then `connect`. Finding the rate takes a few seconds.
    Raises OSError if the port cannot open or fails."""
    try:
        port = serial.serial_for_url(name, baudrate=DEFAULT_RATE, bytesize=serial.EIGHTBITS,
                                     parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                     timeout=0)
    except (serial.SerialException, ValueError) as error:
        raise OSError(_opening_words(error)) from None
    try:
        screen = find_screen(port, RATES_TRIED)
    finally:
        port.close()
    return None if screen is None else screen.rate
