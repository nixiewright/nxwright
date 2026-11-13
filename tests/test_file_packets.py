"""The packets that carry a twfile's file (testing/file_packets.py): how a
packet is laid out, and what a transfer answers to each packet. The bytes
and the answers are the ones a real NX8048P070 took and gave."""
import unittest

from nxwright.testing.file_packets import (CRC16, CRC32, PACKET_START, REJECTED, TAKEN,
                                           PacketTransfer, check_of, packet, packets)

HELLO = bytes.fromhex("3A A1 BB 44 7F FF FE 00 00 00 05 00") + b"HELLO"


class PacketTest(unittest.TestCase):

    def test_a_packet_is_a_header_then_its_data(self):
        self.assertEqual(packet(0, b"HELLO"), HELLO)
        self.assertEqual(packet(1, b"WORLD"),
                         bytes.fromhex("3A A1 BB 44 7F FF FE 00 01 00 05 00") + b"WORLD")
        self.assertTrue(HELLO.startswith(PACKET_START))

    def test_the_check_follows_the_data_and_counts_in_the_size(self):
        self.assertEqual(packet(0, b"HELLO", CRC16),
                         bytes.fromhex("3A A1 BB 44 7F FF FE 01 00 00 07 00") + b"HELLO"
                         + bytes.fromhex("65 E1"))
        self.assertEqual(packet(0, b"HELLO", CRC32),
                         bytes.fromhex("3A A1 BB 44 7F FF FE 0A 00 00 09 00") + b"HELLO"
                         + bytes.fromhex("13 59 64 C7"))

    def test_another_check_is_zero_bytes(self):
        # Two bytes of 0 for a number below 10, and four for a number above 10.
        # rdfile adds the same bytes.
        self.assertEqual((check_of(0, b"HELLO"), check_of(2, b"HELLO"), check_of(11, b"HELLO")),
                         (b"", bytes(2), bytes(4)))
        self.assertEqual(packet(0, b"HELLO", 2)[7:], b"\x02\x00\x00\x07\x00HELLO\x00\x00")

    def test_a_file_is_cut_into_packets_of_at_most_4096_bytes(self):
        data = bytes(range(256)) * 70      # 17920 bytes
        cut = packets(data)
        self.assertEqual([len(one) - 12 for one in cut], [4096] * 4 + [1536])
        self.assertEqual([one[8:10] for one in cut],
                         [number.to_bytes(2, "little") for number in range(5)])
        self.assertEqual(b"".join(one[12:] for one in cut), data)
        # The check's bytes count in the 4096.
        self.assertEqual([len(one) - 12 for one in packets(data, CRC16)], [4096] * 4 + [1546])
        self.assertEqual(len(packets(b"")), 0)


class PacketTransferTest(unittest.TestCase):
    """What a transfer gives for the bytes it takes: the bytes it leaves,
    a step for each packet and for the bytes it drops, and whether the file
    is complete."""

    def taken(self, transfer: PacketTransfer, data: bytes):
        """Gives `data` to `transfer`, and returns the bytes it left, the
        answers of its steps, and whether the file is complete."""
        rest, steps, complete = transfer.take(data)
        return rest, [step.answer for step in steps], complete

    def test_packets_fill_the_file(self):
        transfer = PacketTransfer(10, print)
        self.assertEqual(transfer.left, 10)
        self.assertEqual(self.taken(transfer, packet(0, b"HELLO")), (b"", [TAKEN], False))
        self.assertEqual(transfer.left, 5)
        # The last packet's step has no answer, because the simulation answers
        # FD FF FF FF when the transfer ends.
        self.assertEqual(self.taken(transfer, packet(1, b"WORLD") + b"get 1"),
                         (b"get 1", [b""], True))
        self.assertEqual(bytes(transfer.data), b"HELLOWORLD")

    def test_a_packet_in_pieces(self):
        transfer = PacketTransfer(5, print)
        # The first piece ends inside the packet's start, the second inside
        # the header, and the third inside the data.
        # The transfer leaves the bytes it cannot use yet. The serial line
        # gives them again in front of the next piece, and so does this test.
        left = b""
        for piece in (HELLO[:3], HELLO[3:9], HELLO[9:14]):
            left, answers, complete = self.taken(transfer, left + piece)
            self.assertEqual((answers, complete), ([], False))
        self.assertEqual(self.taken(transfer, left + HELLO[14:]), (b"", [b""], True))
        self.assertEqual(bytes(transfer.data), b"HELLO")

    def test_what_is_rejected_can_be_sent_again(self):
        wrong_check = packet(0, b"HELLO", CRC16)[:-1] + b"\x00"
        shorter_than_its_check = PACKET_START + bytes.fromhex("01 00 00 01 00") + b"H"
        for rejected in (wrong_check, shorter_than_its_check, packet(1, b"HELLO"),
                         packet(0, b"HELLO", 2)[:-2].replace(b"\x07\x00H", b"\x05\x00H")):
            with self.subTest(rejected=rejected):
                transfer = PacketTransfer(5, print)
                self.assertEqual(self.taken(transfer, rejected), (b"", [REJECTED], False))
                self.assertEqual(self.taken(transfer, HELLO), (b"", [b""], True))
                self.assertEqual(bytes(transfer.data), b"HELLO")

    def test_each_check(self):
        for check in (CRC16, CRC32, 2, 11):
            with self.subTest(check=check):
                transfer = PacketTransfer(5, print)
                self.assertEqual(self.taken(transfer, packet(0, b"HELLO", check)),
                                 (b"", [b""], True))
                self.assertEqual(bytes(transfer.data), b"HELLO")

    def test_a_repeat_of_the_last_packet_is_answered_and_not_added(self):
        transfer = PacketTransfer(15, print)
        answers = [self.taken(transfer, one)[1] for one in (
            packet(0, b"HELLO"), packet(0, b"HOWDY"), packet(1, b"WORLD"),
            # Packet 0 is no longer the last one taken.
            packet(0, b"HOWDY"), packet(2, b"AGAIN"))]
        self.assertEqual(answers, [[TAKEN], [TAKEN], [TAKEN], [REJECTED], [b""]])
        self.assertEqual(bytes(transfer.data), b"HELLOWORLDAGAIN")

    def test_a_packet_of_no_bytes_or_of_too_many_gets_no_answer(self):
        transfer = PacketTransfer(5, print)
        self.assertEqual(self.taken(transfer, packet(0, b"")), (b"", [b""], False))
        # The empty packet did not count: packet 0 still comes next.
        self.assertEqual(self.taken(transfer, packet(1, b"HELLO")), (b"", [REJECTED], False))
        # A good packet inside the body of a packet that is too large counts as
        # part of that body.
        for body in (HELLO + bytes(5000 - len(HELLO)), bytes(4096) + HELLO + bytes(887)):
            self.assertEqual(self.taken(transfer, packet(0, body)), (b"", [b""], False))
        self.assertEqual(transfer.left, 5)
        # A good packet in the body of a rejected packet is part of that body too.
        self.assertEqual(self.taken(transfer, packet(1, HELLO)), (b"", [REJECTED], False))
        self.assertEqual(self.taken(transfer, HELLO), (b"", [b""], True))

    def test_bytes_outside_a_packet_are_dropped(self):
        transfer = PacketTransfer(10, print)
        rest, steps, complete = transfer.take(b"xyz" + HELLO)
        self.assertEqual((rest, [step.answer for step in steps], complete),
                         (b"", [b"", TAKEN], False))
        self.assertIn("3 bytes", steps[0].note)
        # Raw bytes are dropped, except the last ones when they may be the
        # beginning of a packet.
        self.assertEqual(self.taken(transfer, b"get 1\xff\xff\xff" + HELLO[:4]),
                         (HELLO[:4], [b""], False))
        self.assertEqual(self.taken(transfer, HELLO[:4] + b"WORLD"), (b"", [], False))
        # The first step reports the bytes dropped since the last report.
        self.assertEqual(self.taken(transfer, packet(1, b"WORLD")), (b"", [b"", b""], True))
        self.assertEqual(bytes(transfer.data), b"HELLOWORLD")

    def test_dropped_bytes_are_reported_once_until_the_next_packet(self):
        transfer = PacketTransfer(5, print)
        notes = [[step.note for step in transfer.take(piece)[1]]
                 for piece in (b"hel", b"lo", b"!!" + HELLO)]
        self.assertEqual([len(given) for given in notes], [1, 0, 2])
        self.assertIn("3 bytes", notes[0][0])
        self.assertIn("4 more bytes", notes[2][0])

    def test_bytes_past_the_files_size_are_dropped(self):
        transfer = PacketTransfer(5, print)
        self.assertEqual(self.taken(transfer, packet(0, b"HELLOWORLD") + b"get 1"),
                         (b"get 1", [b""], True))
        self.assertEqual(bytes(transfer.data), b"HELLO")
