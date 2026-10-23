"""The data file a data record keeps its records in, on an SD card, as the
Editor's simulator writes it (tests/fixtures/data-record/).

A data file is a header of 512 bytes, the same header again, then `maxval`
slots of `lenth` + 1 bytes each, from byte 1024, and 1024 bytes more past
the last whole 512 bytes the slots reach. A record is its text, in the
project's encoding, with `^` between its fields, ended by zero bytes. The
header's 32-bit words, little-endian:
  +0   a check word: the screen's CRC unit fed the header's bytes 4 to 27,
       a byte at a time (project/stamp.py, word_crc)
  +4   0x0053BD5C
  +8   how many records the file holds
  +12  a slot's size, `lenth` + 1
  +16  the slot of the oldest record
  +20  `dez`, the fields a record has
  +24  `maxval`, the most records the file keeps
The Editor's simulator refused a file whose check word did not match, as
it started, "File Header Data Error".

The slots are a ring: records are numbered from the oldest, 0, which may
be in any slot, the next record in the next slot round. Once the file holds
`maxval` records, a new one takes the oldest one's slot. A record longer
than a slot less its last byte is refused. Deleting moves the records after
those deleted down, leaving the slots past the last as they were; clearing
leaves every slot as it was, the count 0. All of this was seen in the
files the Editor's simulator wrote, byte for byte.
"""
import struct

from nxwright import NxwrightError
from nxwright.project.stamp import CRC_START, word_crc

MAGIC = 0x0053BD5C
HEADER_SIZE = 512
FIRST_SLOT = 2 * HEADER_SIZE
# The bytes the check word covers: the header's from the magic to `maxval`.
_CHECKED = slice(4, 28)
_HEADER = struct.Struct("<7I")


class DataFile:
    """A data file's records and slots, as the module's docstring says."""

    def __init__(self, size: int, fields: int, most: int, slots: list = None,
                 count: int = 0, oldest: int = 0):
        self.size, self.fields, self.most = size, fields, most
        self.slots = slots if slots is not None else [bytes(size)] * most
        self.count, self.oldest = count, oldest

    @classmethod
    def new(cls, lenth: int, dez: int, maxval: int) -> "DataFile":
        """An empty data file for a data record's `lenth`, `dez`, and
        `maxval`. Raises NxwrightError for a size or count it cannot have."""
        if lenth < 1 or maxval < 1:
            raise NxwrightError("a data file needs lenth and maxval of 1 at least, not %d and %d"
                                % (lenth, maxval))
        return cls(lenth + 1, dez, maxval)

    @classmethod
    def read(cls, data: bytes) -> "DataFile":
        """Reads a data file. Raises NxwrightError for one whose header does
        not check, or whose records do not fit it."""
        if len(data) < FIRST_SLOT:
            raise NxwrightError("a data file is %d bytes at least, not %d"
                                % (FIRST_SLOT, len(data)))
        check, magic, count, size, oldest, fields, most = _HEADER.unpack_from(data, 0)
        if magic != MAGIC or check != _check_word(data):
            raise NxwrightError("the data file's header does not check")
        if size < 2 or most < 1 or count > most or oldest >= most \
                or len(data) < FIRST_SLOT + most * size:
            raise NxwrightError("the data file's header does not fit its file")
        slots = [bytes(data[FIRST_SLOT + slot * size:FIRST_SLOT + (slot + 1) * size])
                 for slot in range(most)]
        return cls(size, fields, most, slots, count, oldest)

    def to_bytes(self) -> bytes:
        """The data file's bytes."""
        header = bytearray(HEADER_SIZE)
        _HEADER.pack_into(header, 0, 0, MAGIC, self.count, self.size, self.oldest, self.fields,
                          self.most)
        struct.pack_into("<I", header, 0, _check_word(header))
        sectors = -(-self.most * self.size // HEADER_SIZE) + 2
        body = bytearray(sectors * HEADER_SIZE)
        for slot, record in enumerate(self.slots):
            body[slot * self.size:(slot + 1) * self.size] = record
        return bytes(header) * 2 + bytes(body)

    def records(self) -> list:
        """The records' bytes, the oldest first, each up to its first zero byte."""
        return [self.slots[self._slot(number)].split(b"\0", 1)[0] for number in range(self.count)]

    def insert(self, record: bytes) -> bool:
        """Adds `record` after the newest, in place of the oldest when the
        file is full. Returns False, changing nothing, when it does not fit
        a slot."""
        if len(record) >= self.size:
            return False
        if self.count < self.most:
            self.slots[self._slot(self.count)] = self._padded(record)
            self.count += 1
        else:
            self.slots[self.oldest] = self._padded(record)
            self.oldest = (self.oldest + 1) % self.most
        return True

    def delete(self, number: int, count: int) -> bool:
        """Deletes `count` records from record `number`. Returns False,
        changing nothing, when `number` is past the last record, when fewer
        than `count` records follow it, or when `count` is not 1 at least,
        as the Editor's simulator did. It added records there for a `count`
        below 0, which is not followed."""
        if not 0 <= number < self.count or not 0 < count <= self.count - number:
            return False
        for moved in range(number, self.count - count):
            self.slots[self._slot(moved)] = self.slots[self._slot(moved + count)]
        self.count -= count
        return True

    def update(self, record: bytes, number: int) -> bool:
        """Puts `record` in place of record `number`. Returns False, changing
        nothing, when there is no such record or it does not fit a slot."""
        if not 0 <= number < self.count or len(record) >= self.size:
            return False
        self.slots[self._slot(number)] = self._padded(record)
        return True

    def clear(self):
        """Holds no records any more, the slots as they were."""
        self.count, self.oldest = 0, 0

    def _slot(self, number: int) -> int:
        return (self.oldest + number) % self.most

    def _padded(self, record: bytes) -> bytes:
        return record + bytes(self.size - len(record))


def _check_word(header) -> int:
    """The check word of a header: its bytes 4 to 27, each fed to the
    screen's CRC unit as a word of its own."""
    return word_crc(CRC_START, bytes(header[_CHECKED]))


def data_file_for(attributes: dict, found):
    """The data file of a data record with the attributes `attributes`
    (`lenth`, `dez`, `maxval`, `mode`), from its file's bytes `found`, or
    None when it has none. A missing file is an empty one when `mode` is 1;
    None otherwise, and for a damaged file."""
    try:
        if found is not None:
            return DataFile.read(found)
        if attributes.get("mode", 1) != 1:
            return None
        return DataFile.new(attributes.get("lenth", 63), attributes.get("dez", 3),
                            attributes.get("maxval", 1000))
    except NxwrightError:
        return None
