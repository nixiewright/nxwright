"""QR codes: the codes the Editor's simulator drew, fixtures/qr-codes.json,
made module for module; the split of a text into segments; and the most a
code holds."""
from pathlib import Path
import json
import unittest

from nxwright import NxwrightError
from nxwright.project.qr_code import ALPHANUMERIC, BYTE, NUMERIC, qr_modules, segments

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "qr-codes.json"


class EditorCodesTest(unittest.TestCase):

    def test_every_code_as_the_editor_drew_it(self):
        """A text the Editor splits otherwise, marked with its
        `editor_segments`, makes another code: if it ever makes the
        Editor's, the mark is out of date."""
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for code in data["codes"]:
            with self.subTest(txt=code["txt"]):
                made = ["".join("#" if module else "." for module in row)
                        for row in qr_modules(code["txt"].encode(data["encoding"]))]
                if "editor_segments" in code:
                    self.assertNotEqual(made, code["modules"])
                else:
                    self.assertEqual(made, code["modules"])


class SegmentsTest(unittest.TestCase):

    def test_the_fewest_bits(self):
        # 228 bits, where the Editor's split takes 229.
        self.assertEqual(segments(b"Price: 1234567 EUR, ref 00042", 2), [
            (BYTE, b"Price"), (ALPHANUMERIC, b": 1234567 EUR"), (BYTE, b", ref "),
            (NUMERIC, b"00042")])

    def test_digits_split_out_of_byte_text(self):
        self.assertEqual(segments(b"abc1234567890xyz", 1),
                         [(BYTE, b"abc"), (NUMERIC, b"1234567890"), (BYTE, b"xyz")])

    def test_a_tie_splits(self):
        # 60 bits either way: "abc123" in one byte segment, or as two.
        self.assertEqual(segments(b"abc123", 1), [(BYTE, b"abc"), (NUMERIC, b"123")])

    def test_short_digit_runs_stay_byte(self):
        self.assertEqual(segments(b"ab12cd345ef6789gh", 1), [(BYTE, b"ab12cd345ef6789gh")])

    def test_capitals_split_out_of_byte_text(self):
        self.assertEqual(segments(b"abcDEFGHIJKLMNOPQRSTUVWXYZxyz", 2), [
            (BYTE, b"abc"), (ALPHANUMERIC, b"DEFGHIJKLMNOPQRSTUVWXYZ"), (BYTE, b"xyz")])

    def test_empty(self):
        self.assertEqual(segments(b"", 1), [])


class SizeTest(unittest.TestCase):

    def test_version_40_holds_2953_bytes(self):
        self.assertEqual(len(qr_modules(b"a" * 2953)), 177)

    def test_more_is_refused(self):
        with self.assertRaises(NxwrightError):
            qr_modules(b"a" * 2954)


if __name__ == "__main__":
    unittest.main()
