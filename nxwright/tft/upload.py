"""Uploading a TFT file to a screen over its serial line, with Nextion's
upload protocol, as Nextion documents it in three versions, v1.0, v1.1,
and v1.2 (ResearchNotes/tft/uploading.md gives the pages, and where they
differ):

  1. find_screen sends `connect` at the screen's rate. The screen answers
     `comok`, then seven fields: its address after a hyphen in the second,
     its model in the third, such as NX4832T035_011R, and in the seventh a
     hyphen when it takes the upload at every rate of RATES.
  2. upload keeps the screen awake, as a sleeping screen ignores the upload
     command, then sends `whmi-wri <file size>,<upload rate>,0`. The screen
     answers 05 at the upload rate. The pages have the screen change rate
     with that command, but a real screen did not answer one that gave
     another rate than its own. So upload first moves the screen to the
     upload rate with `baud=`, and finds it there (_move_to).
  3. It sends the file in packets of 4096 bytes, the last one shorter, and
     waits for 05 after each.
  4. The screen restarts with the new file, and sends 88 FF FF FF once it
     is ready. upload does not wait for it: the last packet's 05 shows that
     the screen has the file, and the screen sends 88 FF FF FF as it starts,
     at its start-up rate, before the new project may set another, so it
     was not seen at the upload rate on a real screen.

The fast upload sends `whmi-wris` in place of `whmi-wri`. The screen may
then answer a packet with 08 and a place in the file, four bytes, read the
low one first, as ESPHome reads them: the upload goes on from that place,
and the screen keeps the part it skips, such as the firmware when only the
project changed. A place of 0 means the next packet.

The port is pyserial's Serial, or anything with its write, read, flush,
reset_input_buffer, in_waiting, timeout, and baudrate, such as the tests'
stand-in screen. Nothing here opens a port.

Once the screen has taken the upload command, it waits for the whole file,
and no source gives a way to resume or stop it: a screen that stops
answering then needs to be powered off and on, and the file uploaded again.
"""
from dataclasses import dataclass
import re
import time

from nxwright import NxwrightError

# The rates a screen's serial line takes, as the v1.2 page lists them.
RATES = (2400, 4800, 9600, 19200, 31250, 38400, 57600, 115200, 230400, 250000, 256000,
         512000, 921600)
# The order find_screen tries them in: the rate at power-on, and the
# commonest other, first.
RATES_TRIED = (9600, 115200) + tuple(rate for rate in RATES if rate not in (9600, 115200))
# The highest rate a screen takes when its comok answer has no hyphen in
# its seventh field. The v1.2 page gives the hyphen as the mark of a screen
# that takes every rate; the rates of the v1.1 page's table end here.
HIGHEST_RATE_ON_OLDER_SCREENS = 115200
# The end of every instruction.
END = b"\xff\xff\xff"
# The bytes that end a reparse mode, in which the screen hands what it
# receives to the project's code rather than taking it as instructions.
END_REPARSE = b"DRAKJHSUYDGBNCJHGJKSHBDN" + END
# The address every screen takes, whatever its own.
BROADCAST = b"\xff\xff"
# A packet, after which the screen answers 05.
PACKET_SIZE = 4096
# Each packet is written in pieces of this size, the port's output emptied
# after each, as the v1.2 page does in its example. Emptying the output
# waits for the adapter, so a larger piece may be faster: the size is to be
# chosen on a real screen.
PIECE_SIZE = 32
# How long to wait for each answer of the screen, in seconds: 5, as
# ESPHome waits, as its notes give that 500 ms was too short for some
# screens.
ANSWER_WAIT = 5.0
# The screen's answers.
_COMOK = re.compile(rb"comok ([^\xff]*)" + END)
_TAKEN = b"\x05"
# In a fast upload, the start of a place to go on from (the module's
# docstring).
_SKIP = b"\x08"
# How long one read waits at most, in seconds, so that a wait keeps to its
# own limit.
_POLL = 0.05
# How long to wait, in seconds, once a port's output is empty, before
# changing its rate. A WCH CH344 adapter still held bytes when its driver
# gave its output as empty: `baud=` written 2 ms before the rate changed was
# lost, and the same instruction went through with 0.3 s between.
_SETTLE = 0.3
# How many of the bytes that came in place of an answer an error gives.
_MOST_SHOWN = 16


class UploadError(NxwrightError):
    """An upload the screen stopped answering."""


@dataclass
class Screen:
    """A screen that answered `connect`: its model, as it gives it, such as
    NX4832T035_011R; the rate it answered at; its address, or None; and
    whether it takes the upload at every rate of RATES."""
    model: str
    rate: int
    address: int
    takes_every_rate: bool


def pause(rate: int) -> float:
    """Returns how long to wait for an answer at `rate`, in seconds:
    (1000000 / rate) + 30 ms, as the v1.1 and v1.2 pages give it."""
    return (1_000_000 / rate + 30) / 1000


def find_screen(port, rates, pause_of=pause):
    """Returns the Screen that answers `connect` on `port` at the first of
    `rates` it answers at, or None. At each rate, it sends the bytes that
    end a reparse mode, then `connect`, then `connect` to the broadcast
    address, waiting `pause_of(rate)` seconds after each. It looks for the
    answer among whatever arrives, as the screen's running app may send
    bytes of its own first."""
    for rate in rates:
        port.baudrate = rate
        port.reset_input_buffer()
        received = b""
        for message in (END_REPARSE, b"connect" + END, BROADCAST + b"connect" + END):
            port.write(message)
            received += _read_for(port, pause_of(rate))
            found = _COMOK.search(received)
            if found:
                return _screen_of(found[1].decode("latin-1"), rate)
    return None


def _screen_of(answer: str, rate: int) -> Screen:
    """Returns the Screen of a comok answer's fields, `answer`, given at
    `rate`. The second field gives the address after a hyphen, by the v1.1
    page, such as 2556 in 38024-2556."""
    fields = answer.split(",")
    fields += [""] * (7 - len(fields))
    _, hyphen, address = fields[1].partition("-")
    # A screen's address takes two bytes, from 256 to 2815 by the v1.2 page.
    address = int(address) if hyphen and address.isdigit() else 0
    address = address if 0 < address <= 0xFFFF else None
    return Screen(fields[2], rate, address, "-" in fields[6])


def upload(port, screen: Screen, data: bytes, upload_rate: int, progress=None,
           answer_wait: float = None, fast: bool = False, on_skip=None, pause_of=pause,
           settle: float = None):
    """Uploads `data`, a TFT file, to `screen` on `port`, at `upload_rate`,
    with `whmi-wri`, or, when `fast`, with `whmi-wris`, after which the
    screen may skip what it has (the module's docstring). Calls
    `progress(place, size)` after each packet, when given, with the place
    in the file the upload has reached, and `on_skip(bytes skipped)` when
    the screen skips some. Returns once the screen has answered the last
    packet: it then restarts with the file.

    The upload waits at several points, and three arguments set how long.
    `pause_of(rate)` gives the pause at `rate`, in seconds, and is `pause`
    by default. The upload pauses once after the instructions it sends
    first and, if it moves the screen to `upload_rate`, after each message
    it sends to find the screen there (find_screen). `settle` is how long it
    waits, once the port's output is empty, before it changes the port's
    rate, and is _SETTLE by default. `answer_wait` is how long it waits for
    each of the screen's answers, and is ANSWER_WAIT by default.

    Raises UploadError when the screen does not answer the upload command,
    or a packet, in time, or gives a place before what was sent or past the
    file."""
    answer_wait = ANSWER_WAIT if answer_wait is None else answer_wait
    settle = _SETTLE if settle is None else settle
    for instruction in ("sleep=0", "thsp=0"):
        port.write(_instruction(screen, instruction))
    # Bytes the app sent before must not be taken for the screen's answer.
    port.flush()
    time.sleep(pause_of(screen.rate))
    if upload_rate != screen.rate:
        _move_to(port, screen, upload_rate, answer_wait, pause_of, settle)
    port.reset_input_buffer()
    command = "whmi-wris" if fast else "whmi-wri"
    port.write(_instruction(screen, "%s %d,%d,0" % (command, len(data), upload_rate)))
    answers = _Answers(port)
    if not answers.wait_for(_TAKEN, answer_wait):
        # A screen of an older firmware may not take the fast upload.
        again = ("power it off and on, then try again, or with --full, which sends the whole "
                 "file" if fast else "power it off and on before you try again")
        raise UploadError("the screen did not answer the upload command%s; %s"
                          % (answers.instead(), again))
    place = 0
    while place < len(data):
        packet = data[place:place + PACKET_SIZE]
        for at in range(0, len(packet), PIECE_SIZE):
            port.write(packet[at:at + PIECE_SIZE])
            port.flush()
        sent = place + len(packet)
        answer = answers.first_of((_TAKEN, _SKIP) if fast else (_TAKEN,), answer_wait)
        if answer is None:
            raise UploadError("the screen did not answer after %d of %d bytes%s; it now needs "
                              "to be powered off and on, and the file uploaded again"
                              % (sent, len(data), answers.instead()))
        place = sent
        if answer == _SKIP:
            given = answers.take(4, answer_wait)
            skip_to = int.from_bytes(given, "little")
            if len(given) < 4 or (skip_to and not sent <= skip_to <= len(data)):
                raise UploadError("the screen gave a place in the file nxwright cannot go on from, "
                                  "after %d of %d bytes; it sent %s; it now needs to be powered "
                                  "off and on, and the file uploaded again"
                                  % (sent, len(data), (_SKIP + given).hex(" ")))
            if skip_to:
                if on_skip is not None and skip_to > sent:
                    on_skip(skip_to - sent)
                place = skip_to
        if progress is not None:
            progress(place, len(data))


def _move_to(port, screen: Screen, rate: int, wait: float, pause_of, settle: float):
    """Moves `screen` and `port` to `rate` before the upload command is sent,
    because a real screen did not answer when the upload command itself
    changed the rate (ResearchNotes/tft/uploading.md). It sends `baud=<rate>`
    at the screen's current rate, waits until that instruction has left the
    port, and moves the port to `rate`. Then it sends `connect` at the new
    rate until the screen answers, for up to `wait` seconds, because a real
    screen took a moment to move. `pause_of` and `settle` are the waits
    passed to upload().

    Raises UploadError when the screen does not answer in time. The screen
    may then stay at `rate` until it restarts, and does not take an upload
    yet."""
    port.write(_instruction(screen, "baud=%d" % rate))
    _drained(port, screen.rate, settle)
    port.baudrate = rate
    deadline = time.monotonic() + wait
    while find_screen(port, [rate], pause_of) is None:
        if time.monotonic() >= deadline:
            raise UploadError("the screen did not answer at %d bauds once moved to that rate; "
                              "try a lower --upload-baud, after powering the screen off and on"
                              % rate)


def _instruction(screen: Screen, text: str) -> bytes:
    """Returns the bytes of the instruction `text` to `screen`: its address
    first, two bytes, the low one first, when it has one."""
    address = b"" if screen.address is None else screen.address.to_bytes(2, "little")
    return address + text.encode("ascii") + END


class _Answers:
    """The screen's answers on `port` during an upload. What arrives after
    an answer is kept for the next wait, such as the place that follows an
    08."""

    def __init__(self, port):
        self._port, self._pending, self._unanswered = port, b"", b""

    def wait_for(self, answer: bytes, seconds: float) -> bool:
        """Whether `answer` arrives within `seconds` (first_of)."""
        return self.first_of((answer,), seconds) is not None

    def first_of(self, answers: tuple, seconds: float):
        """Returns the first of `answers` to arrive within `seconds`, or
        None. What came before it is dropped, and what came after it kept.
        When none arrives, what came instead is kept for `instead`."""
        def found(got: bytes) -> bool:
            return any(answer in got for answer in answers)
        if not found(self._pending):
            self._pending += _read_for(self._port, seconds,
                                       lambda got: found(self._pending + got))
        places = [(self._pending.find(answer), answer) for answer in answers
                  if answer in self._pending]
        if not places:
            self._pending, self._unanswered = b"", self._pending
            return None
        at, answer = min(places)
        self._pending = self._pending[at + len(answer):]
        return answer

    def take(self, count: int, seconds: float) -> bytes:
        """Returns the next `count` bytes to arrive within `seconds`, or
        fewer when they do not."""
        if len(self._pending) < count:
            self._pending += _read_for(self._port, seconds,
                                       lambda got: len(self._pending + got) >= count)
        taken, self._pending = self._pending[:count], self._pending[count:]
        return taken

    def instead(self) -> str:
        """Returns the words that give what arrived in place of the last
        answer waited for, in hexadecimal, as "; it sent 1a ff ff ff
        instead", or nothing when nothing arrived. A screen that sends an
        error code, or bytes at another rate, is then told from a silent
        one."""
        if not self._unanswered:
            return ""
        shown = self._unanswered[:_MOST_SHOWN]
        return "; it sent %s%s instead" % (shown.hex(" "), " ..." if shown != self._unanswered
                                           else "")


def _drained(port, rate: int, settle: float):
    """Returns once the bytes written to `port` have left it. It waits until
    the port's output is empty (pyserial's `out_waiting` is 0), then
    `settle` seconds more, or two bytes' time at `rate` if that is longer.
    If the output is still not empty after ANSWER_WAIT seconds, it stops
    waiting for it."""
    port.flush()
    deadline = time.monotonic() + ANSWER_WAIT
    while getattr(port, "out_waiting", 0) and time.monotonic() < deadline:
        time.sleep(0.001)
    time.sleep(max(settle, 20 / rate))


def _read_for(port, seconds: float, enough=None) -> bytes:
    """Returns what arrives on `port` within `seconds`, or sooner, once
    `enough(what arrived)` is true. Reads at least once."""
    deadline = time.monotonic() + seconds
    got = b""
    while True:
        remaining = deadline - time.monotonic()
        port.timeout = max(0.0, min(remaining, _POLL))
        got += port.read(max(1, port.in_waiting))
        if (enough is not None and enough(got)) or remaining <= 0:
            return got
