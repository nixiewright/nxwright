"""The screen's serial line, as a simulation receives it.

Bytes arrive in pieces, such as what one read of a serial port gives. An
instruction may span pieces, and a piece may hold several. The line cuts
the bytes into instructions at each FF FF FF, as the screen cuts them. It
keeps the bytes of an instruction not yet ended until its FF FF FF arrives.

A transfer takes the bytes that arrive as data, not as instructions. There
are two kinds: `addt` and `wept` take a given number of bytes, their
transparent data (Transfer), and `twfile` takes its file in packets
(file_packets.PacketTransfer). The bytes after a transfer are instructions
again.

In protocol reparse mode, which `recmod` turns on, every byte goes into the
buffer that code reads (serial_buffer.py), until the text that ends the
mode, END_OF_REPARSE. The line keeps back the bytes that may be the start
of that text, until it knows.

In address mode, which `addr` turns on, an instruction runs only when its
first two bytes are the screen's address, low byte first, or BROADCAST.
The line drops any other. A transfer's data and the buffer's bytes carry no
address.
"""
from dataclasses import dataclass, field
from typing import Callable

from nxwright.testing.simulation_log import END

# The most bytes kept waiting for the FF FF FF that ends an instruction,
# against a program at the other end that never sends one.
MOST_WAITING = 65536
# The screen's serial buffer, in bytes, as the vendor gives it. The
# instructions `com_stop` holds, and the buffer of protocol reparse mode,
# wait there (Simulation._waiting_size).
SERIAL_BUFFER_SIZE = 1024

# The text that ends protocol reparse mode, none of which goes into the
# buffer, as the vendor gives it. Without its FF FF FF, it is bytes like any.
END_OF_REPARSE = b"DRAKJHSUYDGBNCJHGJKSHBDN" + END

# The addresses `addr` takes, besides 0, which turns address mode off.
ADDRESSES = range(256, 2816)
# The address of every screen in address mode.
BROADCAST = b"\xff\xff"

# What the line gives, each with its value (SerialLine.receive).
INSTRUCTION = "instruction"
NOT_ADDRESSED = "not addressed"
TRANSFER_STEP = "transfer step"
TRANSFER_END = "transfer end"
BUFFER = "buffer"
REPARSE_END = "reparse end"
DROPPED = "dropped"


@dataclass
class Transfer:
    """A transfer under way that takes a given number of bytes: the bytes
    it still has to take (`left`), the bytes it took (`data`), and
    `done(data)`, which runs once they are all in."""
    left: int
    done: Callable[[bytes], None]
    data: bytearray = field(default_factory=bytearray)

    def take(self, waiting: bytes) -> tuple:
        """Takes its data from the start of `waiting`. Returns (the bytes
        after its data, an empty list, whether it has all its bytes). The
        empty list is where file_packets.PacketTransfer.take returns its
        steps, so that the serial line can call either kind of transfer the
        same way."""
        taken = waiting[:self.left]
        self.data += taken
        self.left -= len(taken)
        return waiting[len(taken):], [], not self.left


class SerialLine:
    """What the serial line has received and not yet used."""

    def __init__(self):
        self._waiting = b""         # bytes not yet taken
        self._transfer = None       # the Transfer under way, if any
        self._reparse = False       # whether protocol reparse mode is on
        self._address = 0           # the screen's address in address mode, or 0
        self._receiving = False     # whether receive is giving a piece's items

    def empty(self):
        """Drops what the line holds: the bytes waiting, a transfer under
        way, and protocol reparse mode, as a screen that starts again has an
        empty buffer and `recmod` 0."""
        self._waiting = b""
        self.drop_transfer()
        self._reparse = False
        self._address = 0

    def start_reparse(self):
        """Turns protocol reparse mode on. The bytes of an instruction not yet
        ended are dropped, as in the Nextion Editor's simulator: they reach
        neither the buffer nor a later instruction. While receive is giving a
        piece's items, the bytes waiting are the rest of that piece, and go
        into the buffer."""
        if not self._receiving:
            self._waiting = b""
        self._reparse = True

    def end_reparse(self):
        """Turns protocol reparse mode off, as code setting `recmod` to 0
        does. The bytes kept back as the start of END_OF_REPARSE were the
        buffer's, which the end of the mode empties: they are dropped."""
        if not self._receiving:
            self._waiting = b""
        self._reparse = False

    def set_address(self, address: int):
        """Turns address mode on with the screen's `address`, one of
        ADDRESSES, or off with 0."""
        self._address = address

    def in_reparse(self) -> bool:
        """Returns whether protocol reparse mode is on."""
        return self._reparse

    def drop_transfer(self):
        """Drops the transfer under way, if any, so that the bytes that
        arrive next are instructions. A transfer of packets may have kept
        back the beginning of a packet until the next piece arrives. Those
        bytes are dropped with the transfer. While receive is giving a
        piece's items, the bytes waiting are the rest of that piece, and
        they stay."""
        if self._transfer is not None and not self._receiving:
            self._waiting = b""
        self._transfer = None

    def start_transfer(self, transfer):
        """Gives the next bytes to `transfer`, a Transfer or a
        file_packets.PacketTransfer, in place of a transfer under way.
        `transfer.left` is above 0."""
        self._transfer = transfer

    def transfer(self):
        """Returns the transfer under way, or None."""
        return self._transfer

    def receive(self, data: bytes):
        """Takes `data`, a piece that arrived, and yields what it gives, one
        at a time, as (kind, value):
          - (INSTRUCTION, its bytes without the FF FF FF that ended them,
            nor the address that came before them in address mode);
          - (NOT_ADDRESSED, the bytes of an instruction dropped in address
            mode, which lack the screen's address and BROADCAST);
          - (TRANSFER_STEP, a file_packets.TransferStep), for each packet of
            a `twfile` and for the bytes dropped around the packets;
          - (TRANSFER_END, the transfer), once a transfer has its bytes;
          - (BUFFER, bytes for the buffer of protocol reparse mode);
          - (REPARSE_END, None), once END_OF_REPARSE arrived, which turns the
            mode off;
          - (DROPPED, a count of bytes) that waited past MOST_WAITING with no
            FF FF FF after them.
        The caller acts on each before asking for the next: an instruction
        may start a transfer, or turn protocol reparse mode on, for the
        bytes after it."""
        self._waiting += data
        self._receiving = True
        try:
            yield from self._items()
        finally:
            self._receiving = False

    def _items(self):
        """Gives the items of the bytes waiting, as receive says."""
        while self._waiting:
            transfer = self._transfer
            if transfer is not None:
                self._waiting, steps, complete = transfer.take(self._waiting)
                for step in steps:
                    yield TRANSFER_STEP, step
                if not complete:
                    return
                self._transfer = None
                yield TRANSFER_END, transfer
            elif self._reparse:
                end = self._waiting.find(END_OF_REPARSE)
                if end < 0:
                    # Keep back what may start the text ending the mode.
                    kept = _start_of_end(self._waiting)
                    taken = self._waiting[:len(self._waiting) - kept]
                    self._waiting = self._waiting[len(taken):]
                    if taken:
                        yield BUFFER, taken
                    return
                taken = self._waiting[:end]
                self._waiting = self._waiting[end + len(END_OF_REPARSE):]
                self._reparse = False
                if taken:
                    yield BUFFER, taken
                yield REPARSE_END, None
            else:
                instruction, end, rest = self._waiting.partition(END)
                if not end:
                    break
                self._waiting = rest
                if not self._address:
                    yield INSTRUCTION, instruction
                elif instruction[:2] in (self._address.to_bytes(2, "little"), BROADCAST):
                    yield INSTRUCTION, instruction[2:]
                else:
                    yield NOT_ADDRESSED, instruction
        if len(self._waiting) > MOST_WAITING:
            dropped, self._waiting = len(self._waiting), b""
            yield DROPPED, dropped


def _start_of_end(data: bytes) -> int:
    """The length of the longest end of `data` that starts END_OF_REPARSE."""
    for length in range(min(len(data), len(END_OF_REPARSE) - 1), 0, -1):
        if END_OF_REPARSE.startswith(data[-length:]):
            return length
    return 0
