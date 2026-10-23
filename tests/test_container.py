"""The block directory of a project file, on small project files built by hand."""
import struct
import unittest

from nxwright import NxwrightError
from nxwright.project.container import (DIRECTORY_COPY_OFFSET, DirectoryEntry, HmiContainer,
                                        directory_checksum, encode_directory, name_field,
                                        numbered_block)


EDITOR_DATA_START = 0x700000


def build_project(blocks: list, editor_layout: bool = False) -> bytes:
    """Returns a project file holding `blocks`, given as (name, bytes, flags) in
    order. Flags 1 marks a stale block.

    By default the blocks follow the directory and its checksum directly. With
    `editor_layout`, the file is laid out like the Editor's: the directory
    copied at DIRECTORY_COPY_OFFSET and the blocks from EDITOR_DATA_START.
    """
    data_start = EDITOR_DATA_START if editor_layout else 4 + 28 * len(blocks) + 4
    entries = []
    payload = b""
    for name, data, flags in blocks:
        entries.append(DirectoryEntry(name_field(name), data_start + len(payload), len(data), flags))
        payload += data
    directory = encode_directory(entries)
    out = bytearray(data_start)
    out[:len(directory)] = directory
    if editor_layout:
        out[DIRECTORY_COPY_OFFSET:DIRECTORY_COPY_OFFSET + len(directory)] = directory
    return bytes(out) + payload


def manifest(*block_names: str) -> bytes:
    """Returns a manifest listing `block_names`, such as "0.pa", in order. It is
    not stamped."""
    header = bytearray(96)
    struct.pack_into("<I", header, 4, 96)
    struct.pack_into("<II", header, 24, 96, len(block_names))
    table = b"".join(name.rsplit(".", 1)[1].encode("ascii").ljust(8, b"\0")
                     + name.encode("ascii").ljust(8, b"\0") for name in block_names)
    return bytes(header) + table


class HmiContainerTest(unittest.TestCase):

    def test_skips_stale_copies(self):
        container = HmiContainer(build_project([("0.pa", b"old", 1), ("0.pa", b"new", 0)]))
        self.assertEqual(container.blocks, {"0.pa": b"new"})
        self.assertEqual(container.stale_count, 1)

    def test_rejects_two_live_copies(self):
        with self.assertRaises(NxwrightError):
            HmiContainer(build_project([("0.pa", b"a", 0), ("0.pa", b"b", 0)]))

    def test_rejects_block_outside_file(self):
        data = bytearray(build_project([("0.pa", b"abc", 0)]))
        # The size field of the first entry: the block now runs past the end of the file.
        struct.pack_into("<I", data, 4 + 20, 1000)
        with self.assertRaises(NxwrightError):
            HmiContainer(bytes(data))

    def test_blocks_with_extension_orders_by_number(self):
        container = HmiContainer(build_project(
            [("10.pa", b"x", 0), ("2.pa", b"y", 0), ("2.zi", b"z", 0)]))
        self.assertEqual(list(container.blocks_with_extension("pa")), [2, 10])


class DirectoryChecksumTest(unittest.TestCase):

    def test_detects_a_changed_entry(self):
        data = bytearray(build_project([("0.pa", b"abc", 0)]))
        # Renames 0.pa to 1.pa without updating the checksum.
        data[4] = ord("1")
        self.assertFalse(HmiContainer(bytes(data)).directory_checksum_is_valid())

    def test_encoded_directory_carries_its_checksum(self):
        entries = [DirectoryEntry(name_field("0.pa"), 100, 3, 0),
                   DirectoryEntry(name_field("1.zi"), 103, 9, 1)]
        directory = encode_directory(entries)
        self.assertEqual(struct.unpack_from("<I", directory, len(directory) - 4)[0],
                         directory_checksum(directory[:-4]))


class NumberedBlockTest(unittest.TestCase):

    def test_accepts_ascii_number(self):
        self.assertEqual(numbered_block("12.pa", "pa"), 12)

    def test_rejects_other_extension(self):
        self.assertIsNone(numbered_block("12.pa", "i"))

    def test_rejects_non_ascii_digit(self):
        # "\xb2" (superscript two) counts as a digit for str.isdigit().
        self.assertIsNone(numbered_block("\xb2.pa", "pa"))


if __name__ == "__main__":
    unittest.main()
