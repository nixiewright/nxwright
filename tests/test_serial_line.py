"""The screen's serial line (testing/serial_line.py): its bytes cut into
instructions at each FF FF FF, whatever pieces they arrive in, a transfer's
bytes taken as data, and protocol reparse mode's bytes put in the buffer."""
import unittest

from nxwright.testing.serial_line import (BUFFER, DROPPED, END_OF_REPARSE, INSTRUCTION,
                                          MOST_WAITING, NOT_ADDRESSED, REPARSE_END,
                                          TRANSFER_END, SerialLine, Transfer)


def instructions(given) -> list:
    return [value for kind, value in given if kind == INSTRUCTION]


class SerialLineTest(unittest.TestCase):

    def test_instructions_cut_at_ff_ff_ff(self):
        line = SerialLine()
        # Two in one piece, then one across three.
        self.assertEqual(instructions(line.receive(b"a=1\xff\xff\xffb=2\xff\xff\xffc=")),
                         [b"a=1", b"b=2"])
        self.assertEqual(instructions(line.receive(b"3\xff")), [])
        self.assertEqual(instructions(line.receive(b"\xff\xff")), [b"c=3"])

    def test_an_empty_instruction(self):
        self.assertEqual(list(SerialLine().receive(b"\xff\xff\xff")), [(INSTRUCTION, b"")])

    def test_bytes_never_ended_are_dropped(self):
        line = SerialLine()
        self.assertEqual(list(line.receive(b"x" * MOST_WAITING)), [])
        self.assertEqual(list(line.receive(b"xxxx")), [(DROPPED, MOST_WAITING + 4)])
        # What arrives next starts afresh.
        self.assertEqual(list(line.receive(b"a=1\xff\xff\xff")), [(INSTRUCTION, b"a=1")])

    def test_a_transfer_takes_its_count_of_bytes_then_instructions_again(self):
        line = SerialLine()
        given = []
        # The instruction starting the transfer comes first, as the
        # simulation runs each before asking for the next.
        for kind, value in line.receive(b"addt 1,0,4\xff\xff\xff\x01\xff"):
            given.append((kind, value))
            if kind == INSTRUCTION:
                line.start_transfer(Transfer(4, print))
        self.assertEqual(given, [(INSTRUCTION, b"addt 1,0,4")])
        self.assertEqual(line.transfer().data, b"\x01\xff")
        given = list(line.receive(b"\xff\xffget 1\xff\xff\xff"))
        self.assertEqual([kind for kind, _ in given], [TRANSFER_END, INSTRUCTION])
        self.assertEqual((given[0][1].data, given[1][1]), (b"\x01\xff\xff\xff", b"get 1"))
        self.assertIsNone(line.transfer())

    def test_emptying_drops_the_bytes_waiting_and_the_transfer(self):
        line = SerialLine()
        list(line.receive(b"n="))
        line.empty()
        self.assertEqual(instructions(line.receive(b"5\xff\xff\xff")), [b"5"])
        line.start_transfer(Transfer(3, print))
        list(line.receive(b"\x01"))
        line.empty()
        self.assertIsNone(line.transfer())
        self.assertEqual(instructions(line.receive(b"get 1\xff\xff\xff")), [b"get 1"])

    def test_reparse_mode_puts_every_byte_in_the_buffer_until_its_end(self):
        line = SerialLine()
        given = []
        for kind, value in line.receive(b"recmod=1\xff\xff\xffget 1\xff\xff\xffDRAKJ"):
            given.append((kind, value))
            if kind == INSTRUCTION:
                line.start_reparse()
        # The rest of the piece goes into the buffer, but for what may start
        # the text ending the mode.
        self.assertEqual(given, [(INSTRUCTION, b"recmod=1"), (BUFFER, b"get 1\xff\xff\xff")])
        # Without its FF FF FF, the text is bytes like any.
        self.assertEqual(list(line.receive(b"HSUYDGBNCJHGJKSHBDN!")),
                         [(BUFFER, b"DRAKJHSUYDGBNCJHGJKSHBDN!")])
        self.assertEqual(list(line.receive(b"ab" + END_OF_REPARSE[:10])), [(BUFFER, b"ab")])
        self.assertEqual(list(line.receive(END_OF_REPARSE[10:] + b"get 2\xff\xff\xff")),
                         [(REPARSE_END, None), (INSTRUCTION, b"get 2")])
        self.assertFalse(line.in_reparse())

    def test_reparse_mode_turned_on_between_pieces_drops_an_instruction_not_ended(self):
        # As code setting recmod did in the Nextion Editor's simulator.
        line = SerialLine()
        list(line.receive(b"ab"))
        line.start_reparse()
        self.assertEqual(list(line.receive(b"cd\xff\xff\xff")), [(BUFFER, b"cd\xff\xff\xff")])
        # Turned off by code, the line drops what it kept back, which the
        # end of the mode empties with the buffer.
        list(line.receive(b"DRA"))
        line.end_reparse()
        self.assertFalse(line.in_reparse())
        self.assertEqual(list(line.receive(b"get 1\xff\xff\xff")), [(INSTRUCTION, b"get 1")])

    def test_address_mode_takes_only_the_screens_address_and_every_screens(self):
        line = SerialLine()
        line.set_address(258)
        given = list(line.receive(b"\x02\x01get 1\xff\xff\xff\xff\xffget 2\xff\xff\xff"
                                  b"\x01\x02get 3\xff\xff\xffg\xff\xff\xff"))
        self.assertEqual(given, [(INSTRUCTION, b"get 1"), (INSTRUCTION, b"get 2"),
                                 (NOT_ADDRESSED, b"\x01\x02get 3"), (NOT_ADDRESSED, b"g")])
        line.set_address(0)
        self.assertEqual(list(line.receive(b"get 4\xff\xff\xff")), [(INSTRUCTION, b"get 4")])

    def test_emptying_while_receiving_drops_the_rest_of_the_piece(self):
        line = SerialLine()
        given = []
        for kind, value in line.receive(b"rest\xff\xff\xffn=7\xff\xff\xff"):
            given.append(value)
            line.empty()
        self.assertEqual(given, [b"rest"])


if __name__ == "__main__":
    unittest.main()
