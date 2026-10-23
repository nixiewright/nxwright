"""The buffer of protocol reparse mode (testing/serial_buffer.py), as the
Nextion Editor's simulator read and changed it, but for the bytes past
its end, which nxwright reads as 0."""
import unittest

from nxwright.testing.serial_buffer import (buffer_read, copied_into_number, copied_into_text,
                                            deleted)

BUFFER = b"ABCDEFGH"


class SerialBufferTest(unittest.TestCase):

    def test_reads(self):
        self.assertEqual([buffer_read(BUFFER, name) for name in ("usize", "u[0]", "u[7]")],
                         [8, 65, 72])
        # The Nextion Editor's simulator read leftover bytes past the end.
        self.assertEqual([buffer_read(BUFFER, name) for name in ("u[8]", "u[-1]")], [0, 0])

    def test_copying_into_a_number(self):
        # The first byte lowest, from the number's byte `to`.
        self.assertEqual(copied_into_number(0, b" 1", 0, 2, 0), 0x3120)
        self.assertEqual(copied_into_number(0, BUFFER, 0, 4, 0), 0x44434241)
        self.assertEqual(copied_into_number(-1, BUFFER, 0, 2, 2), 0x4241FFFF)
        self.assertEqual(copied_into_number(0, b"\xff\xff\xff\xff", 0, 4, 0), -1)
        # A count below 0 fills the number to its last byte.
        self.assertEqual(copied_into_number(0, BUFFER, 0, -1, 0), 0x44434241)
        self.assertEqual(copied_into_number(0, BUFFER, 0, -1, 2), 0x42410000)
        # Past the buffer's end, 0; past the number's last byte, dropped.
        self.assertEqual(copied_into_number(0, BUFFER, 6, 4, 0), 0x4847)
        self.assertEqual(copied_into_number(7, BUFFER, 0, 2, 4), 7)

    def test_copying_into_a_text(self):
        self.assertEqual(copied_into_text(b"newtxt", BUFFER, 1, 3, 0), b"BCD")
        # The text keeps its bytes before `to`, and ends after the copy.
        self.assertEqual(copied_into_text(b"newtxt", BUFFER, 0, 2, 2), b"neAB")
        # A count below 0 copies the rest of the buffer.
        self.assertEqual(copied_into_text(b"", BUFFER, 5, -1, 0), b"FGH")
        # A zero byte, as one past the end, ends the text.
        self.assertEqual(copied_into_text(b"x", b"AB\0CD", 0, 5, 0), b"AB")
        self.assertEqual(copied_into_text(b"x", BUFFER, 10, 2, 0), b"")
        # A `to` past the text's end leaves it as it is.
        self.assertEqual(copied_into_text(b"ne", BUFFER, 0, 2, 4), b"ne")

    def test_deleting(self):
        self.assertEqual(deleted(BUFFER, 3), b"DEFGH")
        # Past the end, or a count below 0, empties the buffer.
        self.assertEqual((deleted(BUFFER, 20), deleted(BUFFER, -1)), (b"", b""))


if __name__ == "__main__":
    unittest.main()
