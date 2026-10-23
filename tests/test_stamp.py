"""Block stamps: the CRC against a plain reference, and stamps of real files."""
from pathlib import Path
import os
import unittest

from nxwright.project.stamp import block_stamp, manifest_stamp, with_manifest_stamp, with_stamp

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# The header bytes the page stamp covers again after the rest of the block.
PAGE_TAIL = (4, 5, 6, 7, 12, 13, 14, 15, 20, 21)


def reference_crc(words, register: int = 0xFFFFFFFF) -> int:
    """Returns the CRC of `words` computed one bit at a time, top bit first, to
    check stamp.py's table-driven version against. Each value is fed as a 32-bit
    word."""
    for word in words:
        register ^= word
        for _ in range(32):
            register = ((register << 1) ^ 0x04C11DB7 if register & 0x80000000
                        else register << 1) & 0xFFFFFFFF
    return register


class PageStampTest(unittest.TestCase):

    def test_matches_reference(self):
        for length in (24, 56, 301):
            block = os.urandom(length)
            expected = reference_crc(list(block[4:]) + [block[i] for i in PAGE_TAIL])
            self.assertEqual(block_stamp(block), expected, length)

    def test_with_stamp_sets_the_first_four_bytes(self):
        block = with_stamp(os.urandom(100))
        self.assertEqual(int.from_bytes(block[:4], "little"), block_stamp(block))


class ManifestStampTest(unittest.TestCase):
    """A manifest's stamp is computed with the project's own manifest, which the
    Editor stamped, as reference: the stamp also covers values the Editor keeps
    for the screen model outside the manifest."""

    def test_matches_reference(self):
        reference = with_manifest_stamp(os.urandom(96), os.urandom(96))
        block = os.urandom(96)
        stored = int.from_bytes(reference[:4], "little")
        expected = (reference_crc(list(block[4:]) + list(block[4:8]) + [0] * 6)
                    ^ reference_crc(list(reference[4:]) + list(reference[4:8]) + [0] * 6) ^ stored)
        self.assertEqual(manifest_stamp(block, reference), expected)

    def test_another_screen_models_manifests(self):
        # Two manifests of the NX1060P101 screen model, at rotations 0 and 90:
        # the model's own fixture, and another.
        first, second = (FIXTURES / "manifests" / name for name in ("NX1060P101.main",
                                                                   "NX1060P101-90.main"))
        first, second = first.read_bytes(), second.read_bytes()
        self.assertEqual(manifest_stamp(second, first), int.from_bytes(second[:4], "little"))
        self.assertEqual(manifest_stamp(first, second), int.from_bytes(first[:4], "little"))

    def test_with_manifest_stamp_sets_the_first_four_bytes(self):
        reference = os.urandom(96)
        block = with_manifest_stamp(os.urandom(112), reference)
        self.assertEqual(int.from_bytes(block[:4], "little"), manifest_stamp(block, reference))


if __name__ == "__main__":
    unittest.main()
