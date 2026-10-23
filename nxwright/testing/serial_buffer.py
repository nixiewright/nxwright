"""The buffer of protocol reparse mode, as code reads and changes it.

While `recmod` is not 0, the bytes that arrive on the serial line go into
the buffer (serial_line.py), and code reads them: `usize` gives the count of
bytes, and `u[index]` one byte. `ucopy <attribute>,<from>,<count>,<to>`
copies some of them into a number or a text, and `udelete <count>` removes
the first ones. A test gives the buffer as the record "serial buffer".

The functions here work as the Nextion Editor's simulator did, but for
the bytes past the buffer's end. The simulator read leftover bytes there,
which depended on what it had received before. nxwright reads 0.
"""
import re

# `u[index]`, once the machine has computed the index.
BUFFER_BYTE = re.compile(r"u\[(-?\d+)\]")
# A number's bytes, which `ucopy` fills from its lowest.
_NUMBER_SIZE = 4


def buffer_read(buffer: bytes, name: str) -> int:
    """Returns what code reads of `name`: `usize`, the count of bytes in
    `buffer`, or `u[index]`, its byte at `index`."""
    if name == "usize":
        return len(buffer)
    return _byte_at(buffer, int(BUFFER_BYTE.fullmatch(name)[1]))


def copied_into_number(value: int, buffer: bytes, start: int, count: int, to: int) -> int:
    """Returns the number `value` after `ucopy`: `count` bytes of `buffer`,
    from its byte `start`, put in the number's bytes from its byte `to`,
    the lowest first. A count below 0 fills the number to its last byte.
    Bytes that fall outside the number's 4 are dropped."""
    if count < 0:
        count = _NUMBER_SIZE - to
    data = bytearray((value % 2 ** 32).to_bytes(_NUMBER_SIZE, "little"))
    for offset in range(max(0, -to), min(count, _NUMBER_SIZE - to)):
        data[to + offset] = _byte_at(buffer, start + offset)
    return int.from_bytes(data, "little", signed=True)


def copied_into_text(text: bytes, buffer: bytes, start: int, count: int, to: int) -> bytes:
    """Returns the bytes of a text after `ucopy`: its bytes before `to`,
    then `count` bytes of `buffer` from its byte `start`. The text ends at
    the first zero byte among them, which a byte past the buffer's end is.
    A count below 0 copies the rest of the buffer. A `to` past the text's
    end, or below 0, leaves the text as it is."""
    if not 0 <= to <= len(text):
        return text
    if count < 0:
        count = len(buffer) - start
    if start < 0 or count <= 0:
        # A byte before the buffer's start is 0, which ends the copy at once.
        copied = b""
    else:
        copied = buffer[start:start + count].split(b"\0", 1)[0]
    return text[:to] + copied


def deleted(buffer: bytes, count: int) -> bytes:
    """Returns `buffer` after `udelete count`: without its first `count`
    bytes. A count below 0, or past the buffer's end, empties it."""
    return b"" if count < 0 else buffer[count:]


def _byte_at(buffer: bytes, index: int) -> int:
    """The byte of `buffer` at `index`, 0 outside it."""
    return buffer[index] if 0 <= index < len(buffer) else 0
