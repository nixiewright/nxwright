"""The packets that carry a file to the screen for `twfile`.

After `twfile <path>,<size>`, the program at the other end of the serial
line sends the file in packets, and the screen answers each one. The
layout and the answers here are what a real NX8048P070 took and gave.

A packet is a header of 12 bytes, then a body. The body is the packet's
data, then a check of that data, such as a CRC. The header is:

- PACKET_START, 7 bytes that are the same in every packet;
- 1 byte that selects the check, with the numbers that the last argument
  of `rdfile` takes (check_of);
- the packet's number, in 2 bytes, low byte first. The first packet of a
  file is number 0;
- the size of the body, in 2 bytes, low byte first. It is at most
  MOST_IN_A_PACKET.

The screen answers each packet with one byte: TAKEN, or REJECTED for a
packet the program may send again. The packet that completes the file gets
FD FF FF FF in place of TAKEN. The screen drops the bytes that are not in
a packet.
"""
from dataclasses import dataclass
from typing import Callable

from nxwright.project.stamp import CRC_START, word_crc
from nxwright.testing.modbus_crc import crc_after, crc_start

PACKET_START = bytes.fromhex("3A A1 BB 44 7F FF FE")
HEADER_SIZE = len(PACKET_START) + 5
# The most bytes a packet's body has, its check included.
MOST_IN_A_PACKET = 4096

# The numbers that select a check, in a packet and in `rdfile`.
NO_CHECK = 0
CRC16 = 1
CRC32 = 10

# What the screen answers to a packet.
TAKEN = b"\x05"
REJECTED = b"\x04"


def check_of(kind: int, data: bytes) -> bytes:
    """Returns the check of `data` that the number `kind` selects, low byte
    first. 0 selects none, 1 the Modbus CRC16 (modbus_crc.py), and 10 the
    screen's CRC32, which takes each byte as a 32-bit word of its own
    (stamp.word_crc). Any other number selects bytes of value 0 in place
    of a check: 2 of them for a number from 0 to 9, and 4 otherwise.
    In the Nextion Editor's simulator, `rdfile` sent these bytes for 2, 3,
    11, and -1. A real screen took packets with them for 2 and 11."""
    if kind == NO_CHECK:
        return b""
    if kind == CRC16:
        return crc_after(crc_start(0xFFFF), data).to_bytes(2, "little")
    if kind == CRC32:
        return word_crc(CRC_START, data).to_bytes(4, "little")
    return bytes(2 if 0 <= kind < 10 else 4)


def packet(number: int, data: bytes, check: int = NO_CHECK) -> bytes:
    """Returns the packet numbered `number` that carries `data`, with the
    check that `check` selects. The packet is built whatever the size of
    `data`, so that a test can build one that the screen drops, such as a
    packet that is too large."""
    body = data + check_of(check, data)
    return (PACKET_START + bytes([check]) + number.to_bytes(2, "little")
            + len(body).to_bytes(2, "little") + body)


def packets(data: bytes, check: int = NO_CHECK) -> tuple:
    """Returns the packets that carry the file `data`, in order, each with
    the check that `check` selects and as much data as a packet takes."""
    most = MOST_IN_A_PACKET - len(check_of(check, b""))
    return tuple(packet(number, data[start:start + most], check)
                 for number, start in enumerate(range(0, len(data), most)))


@dataclass(frozen=True)
class TransferStep:
    """One thing a transfer of packets did with the bytes it took: `note`
    describes it for the simulator's log, and `answer` is what the screen
    sends for it, which may be nothing."""
    note: str
    answer: bytes = b""


@dataclass(frozen=True)
class _Header:
    """The header of a packet whose body is arriving."""
    check: int
    number: int
    size: int


class PacketTransfer:
    """The transfer of a `twfile`: the file's bytes taken so far (`data`),
    and `done(data)`, which the simulation runs once the file is complete
    (Simulation._end_transfer)."""

    def __init__(self, size: int, done: Callable[[bytes], None]):
        """`size` is the size of the file, above 0."""
        self.data = bytearray()
        self.done = done
        self._size = size
        self._next = 0              # the number of the packet that comes next
        self._header = None         # the _Header of the packet arriving, if any
        self._body = bytearray()    # that packet's body so far, unless it is too large
        self._body_left = 0         # the bytes of that body still to arrive
        self._unreported = 0        # bytes dropped since the last step that reported any
        self._reported = False      # whether a step reported dropped bytes since the last packet

    @property
    def left(self) -> int:
        """The bytes of the file still to arrive."""
        return self._size - len(self.data)

    def take(self, waiting: bytes) -> tuple:
        """Takes what it can use of `waiting`, the bytes that arrived and
        were not used yet. Returns (the bytes it leaves, the TransferSteps
        that happened in order, whether the file is now complete).

        Before the file is complete, the bytes it leaves are the beginning
        of a packet whose header has not fully arrived. The caller gives them
        again, in front of the bytes that arrive next. Once the file is
        complete, the bytes it leaves are the bytes after the last
        packet."""
        steps = []
        while self.left:
            if self._header is None:
                waiting = self._find_header(waiting, steps)
                if self._header is None:
                    break
            taken = waiting[:self._body_left]
            waiting = waiting[len(taken):]
            self._body_left -= len(taken)
            if self._header.size <= MOST_IN_A_PACKET:
                self._body += taken
            if self._body_left:
                break
            steps.append(self._end_of_packet())
        return waiting, steps, not self.left

    def _find_header(self, waiting: bytes, steps: list) -> bytes:
        """Looks for a packet's header in `waiting`, and sets it as the
        packet arriving when it is all there. Drops the bytes before it,
        and adds a step to `steps` when dropped bytes are to be reported.
        Returns the bytes left: those after the header, or the beginning
        of a header that has not fully arrived."""
        start = waiting.find(PACKET_START)
        if start < 0:
            # Keep the last bytes when they may be the first bytes of PACKET_START.
            start = len(waiting) - _beginning_of_start(waiting)
        self._unreported += start
        waiting = waiting[start:]
        # A run of dropped bytes is reported when it begins, so that the log
        # shows it even if no packet ever follows. The rest of the run is
        # reported when the next packet arrives, not piece by piece.
        if self._unreported and not self._reported:
            steps.append(TransferStep("dropped %s outside a packet, because a real screen "
                                      "takes the file only in packets"
                                      % _bytes_counted(self._unreported)))
            self._unreported, self._reported = 0, True
        if len(waiting) < HEADER_SIZE:
            return waiting
        if self._unreported:
            steps.append(TransferStep("dropped %s outside a packet"
                                      % _bytes_counted(self._unreported, "more ")))
        self._unreported, self._reported = 0, False
        check, number, size = (waiting[7], int.from_bytes(waiting[8:10], "little"),
                               int.from_bytes(waiting[10:12], "little"))
        self._header, self._body, self._body_left = _Header(check, number, size), bytearray(), size
        return waiting[HEADER_SIZE:]

    def _end_of_packet(self) -> TransferStep:
        """Ends the packet arriving, whose body is all there: adds its
        data to the file if the screen takes it. Returns the step that
        says what the screen did with it."""
        header, body = self._header, bytes(self._body)
        self._header = None
        about = "packet %d, %s: " % (header.number, _bytes_counted(header.size))
        if not header.size:
            return TransferStep(about + "dropped without an answer, because it is empty")
        if header.size > MOST_IN_A_PACKET:
            return TransferStep(about + "dropped without an answer, because a packet has at "
                                        "most %d bytes" % MOST_IN_A_PACKET)
        check_size = len(check_of(header.check, b""))
        if len(body) < check_size:
            return TransferStep(about + "rejected, because it is shorter than its check",
                                REJECTED)
        data = body[:len(body) - check_size]
        if body[len(data):] != check_of(header.check, data):
            return TransferStep(about + "rejected, because its check is wrong", REJECTED)
        if header.number == self._next:
            self.data += data[:self.left]
            self._next += 1
            # The simulation answers FD FF FF FF to the packet that completes
            # the file (Simulation._end_transfer).
            return TransferStep(about + "taken", TAKEN if self.left else b"")
        if header.number == self._next - 1:
            return TransferStep(about + "already taken, so its data is not added", TAKEN)
        return TransferStep(about + "rejected, because packet %d comes next" % self._next,
                            REJECTED)


def _beginning_of_start(data: bytes) -> int:
    """Returns how many bytes at the end of `data` are the first bytes of
    PACKET_START, or 0 if `data` does not end with the beginning of
    PACKET_START."""
    for length in range(min(len(data), len(PACKET_START) - 1), 0, -1):
        if PACKET_START.startswith(data[-length:]):
            return length
    return 0


def _bytes_counted(count: int, more: str = "") -> str:
    """Returns `count` bytes as a log line gives them: "1 byte", "5 bytes",
    or "5 more bytes" when `more` is "more "."""
    return "%d %s%s" % (count, more, "byte" if count == 1 else "bytes")
