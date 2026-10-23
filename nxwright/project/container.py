"""The block directory of a Nextion Editor project file (.HMI).

An .HMI file is a container of named blocks. The directory at offset 0 is a
u32 entry count followed by 28-byte entries: a NUL-padded 16-byte name, then
the block's absolute offset, size, and flags as u32. All numbers are
little-endian. Each save appends new copies of changed blocks and sets bit 0
of the old copies' flags ("stale"). Only the live (non-stale) blocks make up
the project.

The 4 bytes after the last entry are the directory checksum (see
directory_checksum). The Editor keeps the entries in offset order, with the
last entry ending at the end of the file, and finds free space by that order.
An exact copy of the directory and its checksum sits at DIRECTORY_COPY_OFFSET.
The Editor writes it, so nxwright does too.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import struct

from nxwright import NxwrightError
from nxwright.project.stamp import multiply, word_crc, x_power

ENTRY_SIZE = 28
DIRECTORY_COPY_OFFSET = 0x80000
STALE_FLAG = 0x1
_NAME_SIZE = 16
_NUMBERED_NAME = re.compile(r"([0-9]+)\.([A-Za-z]+)")
_DIRECTORY_CHECKSUM_XOR = 0xf5d03d45


@dataclass
class DirectoryEntry:
    """One directory entry, live or stale.

    `name_field` is the raw 16-byte name field. It is kept whole because stale
    entries can hold leftover bytes after the name's terminating zero, and a
    rewritten directory should not change entries it does not mean to change.
    """
    name_field: bytes
    offset: int
    size: int
    flags: int

    @property
    def name(self) -> str:
        """The block's name: the name field up to its first zero byte."""
        return self.name_field.split(b"\0")[0].decode("latin-1")

    @property
    def stale(self) -> bool:
        """True when bit 0 of the flags marks the entry as an old copy."""
        return bool(self.flags & STALE_FLAG)

    def encode(self) -> bytes:
        """Returns the entry's 28 bytes as the directory stores them."""
        return self.name_field + struct.pack("<III", self.offset, self.size, self.flags)

    def mark_stale(self):
        """Marks the entry stale: sets flags bit 0 and zeroes the first byte of
        the name. The Editor finds blocks by name, so an old copy that kept
        its name would be loaded instead of the new one."""
        self.flags |= STALE_FLAG
        self.name_field = b"\0" + self.name_field[1:]


def name_field(name: str) -> bytes:
    """Returns `name` as a NUL-padded 16-byte name field."""
    return name.encode("latin-1").ljust(_NAME_SIZE, b"\0")


def directory_checksum(directory: bytes) -> int:
    """Returns the checksum of `directory`: the entry count and the entries.

    A CRC with polynomial 0x04C11DB7, MSB first, starting at 0xFFFFFFFF, over
    the bytes as little-endian 32-bit words, then one zero word, then XOR
    0xf5d03d45. Worked out from project files the Editor saved; not documented
    by the vendor.
    """
    words = [int.from_bytes(directory[i:i + 4], "little") for i in range(0, len(directory), 4)]
    return multiply(word_crc(0xFFFFFFFF, words), x_power(32)) ^ _DIRECTORY_CHECKSUM_XOR


def encode_directory(entries: list) -> bytes:
    """Returns the directory bytes for `entries`, followed by their checksum."""
    directory = struct.pack("<I", len(entries)) + b"".join(entry.encode() for entry in entries)
    return directory + struct.pack("<I", directory_checksum(directory))


class HmiContainer:
    """The directory and live blocks of one .HMI file.

    `entries` lists every directory entry, live or stale, in stored order.
    `blocks` maps each live block's name to its bytes.
    """

    def __init__(self, data: bytes):
        """Parses the directory of `data`, the whole file's bytes.

        Raises NxwrightError when the directory runs past the end of the
        file, a block lies outside the file, or a name has two live copies.
        """
        self.data = data
        self.file_size = len(data)
        if len(data) < 4:
            raise NxwrightError("file is too short to hold a directory")
        self.entry_count = struct.unpack_from("<I", data, 0)[0]
        if 4 + self.entry_count * ENTRY_SIZE + 4 > len(data):
            raise NxwrightError("directory of %d entries runs past the end of the file"
                                % self.entry_count)
        self.entries = [self._read_entry(data, 4 + index * ENTRY_SIZE)
                        for index in range(self.entry_count)]
        self.stale_count = sum(entry.stale for entry in self.entries)
        self.blocks = {}
        for entry in self.entries:
            if entry.stale:
                continue
            if entry.offset + entry.size > len(data):
                raise NxwrightError("block %s lies outside the file" % entry.name)
            # Two live copies would leave no way to tell which one the Editor uses.
            if entry.name in self.blocks:
                raise NxwrightError("block %s has more than one live copy" % entry.name)
            self.blocks[entry.name] = data[entry.offset:entry.offset + entry.size]

    @classmethod
    def from_file(cls, path: Path) -> "HmiContainer":
        """Reads `path` without modifying it and parses its directory."""
        return cls(Path(path).read_bytes())

    @staticmethod
    def _read_entry(data: bytes, entry_offset: int) -> DirectoryEntry:
        # Stale entries are kept as they are, even when they no longer fit the file.
        offset, size, flags = struct.unpack_from("<III", data, entry_offset + _NAME_SIZE)
        return DirectoryEntry(data[entry_offset:entry_offset + _NAME_SIZE], offset, size, flags)

    def stored_directory_checksum(self) -> int:
        """Returns the checksum stored after the last directory entry."""
        return struct.unpack_from("<I", self.data, 4 + self.entry_count * ENTRY_SIZE)[0]

    def directory_checksum_is_valid(self) -> bool:
        """Returns whether the stored directory checksum matches the directory."""
        end = 4 + self.entry_count * ENTRY_SIZE
        return directory_checksum(self.data[:end]) == self.stored_directory_checksum()

    def blocks_with_extension(self, extension: str) -> dict:
        """Returns {number: bytes} for live blocks named "<number>.<extension>",
        ordered by number."""
        found = {}
        for name, block in self.blocks.items():
            number = numbered_block(name, extension)
            if number is not None:
                found[number] = block
        return dict(sorted(found.items()))


def numbered_block(name: str, extension: str):
    """Returns N when `name` is "N.<extension>" with N in ASCII digits, else None."""
    match = _NUMBERED_NAME.fullmatch(name)
    if match and match.group(2) == extension:
        return int(match.group(1))
    return None
