"""The F series' header 2 (tft_file.encode_f_header_2), on words the
Nextion Editor wrote for the three F models."""
import random
import unittest

from nxwright.tft.tft_file import HEADER_2_WORDS, decode_f_header_2, encode_f_header_2

# Each model's device ID, as header 1 stores it at 0x2E.
NX3224F024 = bytes.fromhex("bcc1495b")
NX3224F028 = bytes.fromhex("208e9cba")
NX4832F035 = bytes.fromhex("0376e41c")

# Words the Nextion Editor wrote: (device ID, word, plain value, stored value).
# NX3224F028's ID is the one with bit 31 set.
SEEN = (
    (NX3224F024, 0, 0xFE, 0xD31B9C8B),
    (NX3224F024, 13, 0x42, 0x9F31DEEC),
    (NX3224F028, 2, 0x3, 0xB9E3B4F2),
    (NX3224F028, 15, 0x16, 0xFAFCEE86),
    (NX4832F035, 7, 0x60446, 0x39E40756),
    (NX4832F035, 48, 0xFFFFFFFF, 0x537C1EC2),
)


class EncodeTest(unittest.TestCase):

    def test_words_the_nextion_editor_wrote(self):
        for device_id, word, plain, stored in SEEN:
            with self.subTest(device_id=device_id.hex(), word=word):
                words = [0] * word + [plain]
                self.assertEqual(encode_f_header_2(device_id, words)[word], stored)

    def test_a_word_does_not_depend_on_the_others(self):
        device_id, word, plain, stored = SEEN[1]
        draw = random.Random(13)
        words = [draw.getrandbits(32) for _ in range(word)] + [plain]
        self.assertEqual(encode_f_header_2(device_id, words)[word], stored)

    def test_bit_31_of_the_device_id_reaches_word_0_s_bit_31_alone(self):
        # a is doubled before key 1, so its bit 31 leaves after word 0's first key.
        cleared = bytes(NX3224F028[:3]) + bytes([NX3224F028[3] & 0x7F])
        words = list(range(HEADER_2_WORDS))
        with_bit, without = encode_f_header_2(NX3224F028, words), encode_f_header_2(cleared, words)
        self.assertEqual(with_bit[0] ^ without[0], 0x80000000)
        self.assertEqual(with_bit[1:], without[1:])

    def test_refuses_a_device_id_not_of_4_bytes(self):
        with self.assertRaises(ValueError):
            encode_f_header_2(b"\x01\x02\x03", [0])

    def test_refuses_more_words_than_header_2_has(self):
        with self.assertRaises(ValueError):
            encode_f_header_2(NX3224F024, [0] * (HEADER_2_WORDS + 1))


class DecodeTest(unittest.TestCase):

    def test_words_the_nextion_editor_wrote(self):
        for device_id, word, plain, stored in SEEN:
            with self.subTest(device_id=device_id.hex(), word=word):
                self.assertEqual(decode_f_header_2(device_id, [0] * word + [stored])[word], plain)

    def test_undoes_encode(self):
        draw = random.Random(49)
        for device_id in (NX3224F024, NX3224F028, NX4832F035, bytes(draw.getrandbits(8) for _ in range(4))):
            words = [draw.getrandbits(32) for _ in range(HEADER_2_WORDS)]
            with self.subTest(device_id=device_id.hex()):
                self.assertEqual(decode_f_header_2(device_id, encode_f_header_2(device_id, words)),
                                 words)


if __name__ == "__main__":
    unittest.main()
