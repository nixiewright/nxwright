"""A stand-in for a screen on a serial port, for the tests of uploading
(tft/upload.py). It takes the place of pyserial's Serial: the code under
test writes to it, reads from it, and sets its rate, and it answers as a
screen does by Nextion's upload protocol. No port is opened.

It keeps every byte it is sent, with the rate it was sent at, so that a
test can check them in order."""
import re

END = b"\xff\xff\xff"


class StandInScreen:
    """A screen of the model `model`, as its `comok` answer gives it, at the
    rate `rate`, with the address `address` (0 for none). `every_rate` gives
    the hyphen in the seventh field of its `comok` answer. It stops
    answering after `answered_packets` packets, when given. It ignores the upload
    command when not `takes_upload`, as a sleeping screen does. `app_bytes` are
    bytes its running app has sent before anything is written, such as a
    touch event.

    It takes `whmi-wris`, the fast upload, too. Then, with `skip_to`, it
    answers packet `skip_packet`, the first by default, with 08 and the
    place `skip_to`, four bytes, the low one first, or with the bytes
    `skip_answer` when given, and takes the rest of the file from that
    place."""

    def __init__(self, model: str = "NX4832T035_011R", rate: int = 9600, address: int = 0,
                 every_rate: bool = True, answered_packets: int = None,
                 app_bytes: bytes = b"", takes_upload: bool = True,
                 skip_to: int = None, skip_answer: bytes = None, skip_packet: int = 1,
                 deaf_after_move: int = 0):
        self.model, self.rate, self.address = model, rate, address
        self.every_rate, self.answered_packets = every_rate, answered_packets
        self.takes_upload = takes_upload
        self.skip_to, self.skip_answer, self.skip_packet = skip_to, skip_answer, skip_packet
        # How many instructions it ignores after `baud=`, as a real screen
        # takes a moment to move to the new rate, and how many are left.
        self.deaf_after_move, self._deaf = deaf_after_move, 0
        # Whether the upload command was whmi-wris.
        self.fast = None
        self.baudrate, self.timeout = 9600, None
        # [(rate, bytes)] of each write, in order.
        self.writes = []
        self.flushes, self.closed = 0, False
        self._waiting = bytearray(app_bytes)
        self._command = b""
        self._upload_size = None
        self._uploaded = bytearray()
        self._packets = 0
        # The place in the file the next byte received goes to, and where
        # the packet it belongs to started.
        self._place = self._packet_start = 0

    @property
    def in_waiting(self) -> int:
        return len(self._waiting)

    def read(self, size: int = 1) -> bytes:
        got = bytes(self._waiting[:size])
        del self._waiting[:size]
        return got

    def reset_input_buffer(self):
        self._waiting.clear()

    def flush(self):
        self.flushes += 1

    def close(self):
        self.closed = True

    def write(self, data: bytes) -> int:
        self.writes.append((self.baudrate, bytes(data)))
        # Bytes at a rate other than the screen's are noise to it.
        if self.baudrate != self.rate:
            return len(data)
        if self._upload_size is not None:
            self._take_upload(data)
        else:
            self._command += data
            while END in self._command:
                instruction, self._command = self._command.split(END, 1)
                self._take(instruction)
        return len(data)

    def app_sends(self, data: bytes):
        """Puts `data` in the port's input, as bytes the running app sent."""
        self._waiting += data

    def sent(self) -> bytes:
        """Returns every byte written, in order."""
        return b"".join(data for _, data in self.writes)

    def _take(self, instruction: bytes):
        """Answers one instruction, without its FF FF FF."""
        if self._deaf:
            self._deaf -= 1
            return
        if instruction.startswith(b"\xff\xff"):
            instruction = instruction[2:]
        elif self.address:
            if not instruction.startswith(self.address.to_bytes(2, "little")):
                return
            instruction = instruction[2:]
        if instruction == b"connect":
            seventh = "16777216-0" if self.every_rate else "16777216"
            fields = ["1", "38024-%d" % self.address, self.model, "99", "61488",
                      "D264B8204F0E1828", seventh]
            self._waiting += b"comok " + ",".join(fields).encode("ascii") + END
            return
        moved = re.fullmatch(rb"baud=(\d+)", instruction)
        if moved:
            self.rate = int(moved[1])
            self._deaf = self.deaf_after_move
            return
        found = re.fullmatch(rb"whmi-wri(s?) (\d+),(\d+),(.)", instruction)
        # The user's NX8048P070 did not answer an upload command that gave
        # another rate than its own, so neither does the stand-in.
        if found and self.takes_upload and int(found[3]) == self.rate:
            self.fast = found[1] == b"s"
            self._upload_size = int(found[2])
            self._waiting += b"\x05"

    def _take_upload(self, data: bytes):
        self._uploaded += data
        self._place += len(data)
        while True:
            packet_end = min(self._packet_start + 4096, self._upload_size)
            if self._place < packet_end:
                return
            self._packets += 1
            if self.answered_packets is not None and self._packets > self.answered_packets:
                return
            if (self.fast and self._packets == self.skip_packet
                    and (self.skip_to or self.skip_answer)):
                if self.skip_answer:
                    # As for a place of 0: the next packet follows.
                    self._waiting += self.skip_answer
                    self._packet_start = packet_end
                    continue
                self._waiting += b"\x08" + self.skip_to.to_bytes(4, "little")
                self._place = self._packet_start = self.skip_to
                continue
            if self._place == self._upload_size:
                self._waiting += b"\x05"
                return
            self._waiting += b"\x05"
            self._packet_start = packet_end

    @property
    def uploaded(self) -> bytes:
        """The bytes of the file the screen received."""
        return bytes(self._uploaded)
