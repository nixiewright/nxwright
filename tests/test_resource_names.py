"""Picture and font names: the rules, lookups, and names from font headers."""
import unittest

from nxwright import NxwrightError
from nxwright.language.resource_names import (FONT, PICTURE, ResourceNames, check_names,
                                              font_header_name)


def named_font(name: bytes) -> bytes:
    """A font block whose header holds `name`, where the font generator puts it."""
    header = bytearray(0x2c)
    header[0x20] = len(name)
    return bytes(header) + name + b"iso-8859-1 "


class NameRuleTest(unittest.TestCase):

    def test_valid_names(self):
        check_names(["mono-dark/toast", "mono-dark/dialog", "Impact16", "picture-0001"], "pictures")

    def test_refusals(self):
        cases = {
            "not a valid name": [["a b"], ["../a"], ["a/"], ["a/con"], ["NUL"], ["com1/x"], [""]],
            "are the same name": [["toast", "Toast"], ["a/b", "A/B"]],
            "folder of another name": [["a", "a/b"], ["A", "a/b/c"], ["a/b", "a/b/c"]],
        }
        for message, name_lists in cases.items():
            for names in name_lists:
                with self.subTest(names=names):
                    with self.assertRaisesRegex(NxwrightError, message):
                        check_names(names, "pictures")


class LookupTest(unittest.TestCase):

    def test_both_ways(self):
        names = ResourceNames(["a", "b"], ["Impact16"])
        self.assertEqual((names.id_of(PICTURE, "b"), names.id_of(FONT, "Impact16")), (1, 0))
        self.assertEqual((names.name_of(PICTURE, 0), names.name_of(PICTURE, 2),
                          names.name_of(PICTURE, 65535)), ("a", None, None))
        with self.assertRaisesRegex(NxwrightError, "no font is named a"):
            names.id_of(FONT, "a")


class FontHeaderNameTest(unittest.TestCase):

    def test_names(self):
        self.assertEqual(font_header_name(named_font(b"Impact16")), "Impact16")
        self.assertEqual(font_header_name(named_font(b"24ascii")), "24ascii")

    def test_no_usable_name(self):
        for font in (bytes(0x2c), named_font(b"two words"), named_font(b"a/b"), b"short",
                     bytes(0x20) + b"\x40" + bytes(11)):
            with self.subTest(font=font[:48]):
                self.assertIsNone(font_header_name(font))


if __name__ == "__main__":
    unittest.main()
