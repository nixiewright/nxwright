"""Screen copies: decoding against known pictures, and encoding round trips."""
from pathlib import Path
import struct
import unittest

from nxwright import NxwrightError
from nxwright.project.pictures import read_picture
from nxwright.project.screen_copy import (FORMAT_COMPRESSED, FORMAT_RAW, FORMAT_RAW_WITH_HEADER,
                                          OPAQUE, ROTATIONS, ScreenPixels, UndecodedScreenCopyError,
                                          decode_screen_copy, encode_screen_copy,
                                          matches_within_editor_rounding, screen_copy_format,
                                          stored_pixels)
from tests.pictures import rgba_image

# The samples in compressed/ and raw/ come from a project turned by 180 degrees,
# so the tests read them at that rotation.
PICTURES = Path(__file__).resolve().parent / "fixtures" / "pictures"


def fixture_pairs(folder: str) -> list:
    """Returns (name, PNG bytes, screen copy bytes) for each sample picture."""
    return [(png.stem, png.read_bytes(), png.with_suffix(".i").read_bytes())
            for png in sorted((PICTURES / folder).glob("*.png"))]


class DecodeTest(unittest.TestCase):

    def test_compressed_samples_decode_to_their_png(self):
        pairs = fixture_pairs("compressed")
        self.assertEqual(len(pairs), 22)
        for name, png, block in pairs:
            with self.subTest(name=name):
                self.assertEqual(screen_copy_format(block), FORMAT_COMPRESSED)
                image = read_picture(png)
                expected = stored_pixels(image, FORMAT_COMPRESSED)
                decoded = decode_screen_copy(block, 180)
                # The Editor's colours for partly transparent pixels can be one step off.
                if all(alpha in (0, 255) for *_, alpha in image.get_flattened_data()):
                    self.assertEqual(decoded, expected)
                else:
                    self.assertTrue(matches_within_editor_rounding(decoded, image, FORMAT_COMPRESSED))

    def test_raw_samples_decode_to_their_png(self):
        pairs = fixture_pairs("raw")
        self.assertEqual(len(pairs), 23)
        for name, png, block in pairs:
            with self.subTest(name=name):
                self.assertEqual(screen_copy_format(block), FORMAT_RAW)
                self.assertEqual(decode_screen_copy(block, 180),
                                 stored_pixels(read_picture(png), FORMAT_RAW))

    def test_dot_positions_show_the_pixel_order(self):
        # The sample's single white pixel must land where its name says.
        for name, position in (("11-dot-top-left-8x8", (0, 0)), ("12-dot-top-right-8x8", (7, 0)),
                               ("13-dot-bottom-left-8x8", (0, 7)), ("14-dot-3-5-8x8", (3, 5))):
            with self.subTest(name=name):
                pixels = decode_screen_copy((PICTURES / "compressed" / (name + ".i")).read_bytes(), 180)
                whites = [index for index, colour in enumerate(pixels.colours) if colour == 0xFFFF]
                self.assertEqual(whites, [position[1] * 8 + position[0]])

    def test_malformed_screen_copies_are_refused(self):
        block = (PICTURES / "compressed" / "15-vertical-stripes-8x8.i").read_bytes()
        too_long_literal = bytearray(block)
        struct.pack_into("<I", too_long_literal, 44, (1 << 20) << 4 | 15)
        cases = {
            "not a screen copy": b"\x0a\x64\x01\x01" + bytes(40),
            "unknown format": block[:3] + b"\x07" + block[4:],
            "size field wrong": block[:-2],
            "block past the last pixel": bytes(too_long_literal),
            "second header wrong": block[:24] + b"\x02" + block[25:],
            "block of kind 0": block[:44] + bytes(4) + block[48:],
        }
        for case, data in cases.items():
            with self.subTest(case=case):
                with self.assertRaises(NxwrightError):
                    decode_screen_copy(data, 180)


class EncodeTest(unittest.TestCase):

    def assert_round_trip(self, pixels: ScreenPixels):
        block = encode_screen_copy(pixels, FORMAT_COMPRESSED, 180)
        self.assertEqual(decode_screen_copy(block, 180), pixels)
        return block

    def test_samples_round_trip(self):
        for name, png, _ in fixture_pairs("compressed"):
            with self.subTest(name=name):
                self.assert_round_trip(stored_pixels(read_picture(png), FORMAT_COMPRESSED))

    def test_solid_picture_matches_the_editors_bytes(self):
        _, png, block = fixture_pairs("compressed")[0]
        self.assertEqual(encode_screen_copy(stored_pixels(read_picture(png), FORMAT_COMPRESSED),
                                            FORMAT_COMPRESSED, 180), block)

    def test_long_runs_literals_and_long_alpha_runs(self):
        width, height = 50, 40
        colours = [0x1234] * 700 + [index * 7 & 0xFFFF for index in range(300)] + [0xF800] * 1000
        alphas = [0] * 600 + [index % 128 for index in range(200)] + [OPAQUE] * 1200
        block = self.assert_round_trip(ScreenPixels(width, height, colours, alphas))
        # Uncompressed, the colours alone take 4000 bytes. The 700 and 1000
        # pixel stretches must shrink to a few blocks.
        self.assertLess(len(block), 1000)

    def test_opaque_picture_has_no_alpha_section(self):
        block = encode_screen_copy(ScreenPixels(2, 1, [1, 2], [OPAQUE, OPAQUE]), FORMAT_COMPRESSED, 180)
        self.assertEqual(struct.unpack_from("<I", block, 20)[0], 0)

    def test_one_pixel_picture_is_refused(self):
        with self.assertRaises(NxwrightError):
            encode_screen_copy(ScreenPixels(1, 1, [0], [OPAQUE]), FORMAT_COMPRESSED, 180)


def is_compressed_format_3(block: bytes) -> bool:
    """True for a format 3 screen copy in its compressed variant, which is not decoded."""
    return screen_copy_format(block) == FORMAT_RAW_WITH_HEADER and block[24] == 1


class ModelFixtureTest(unittest.TestCase):
    """The Editor's screen copies for one screen model of each format, at each rotation."""

    FORMATS = {"raw": FORMAT_RAW, "raw-with-header": FORMAT_RAW_WITH_HEADER,
               "compressed": FORMAT_COMPRESSED}

    def folders(self):
        for folder in sorted((PICTURES / "models").iterdir()):
            label, rotation = folder.name.rsplit("-", 1)
            yield folder, self.FORMATS[label], int(rotation)

    def test_every_picture_decodes_in_its_format_and_rotation(self):
        for folder, kind, rotation in self.folders():
            for png in sorted(folder.glob("*.png")):
                with self.subTest(folder=folder.name, picture=png.stem):
                    block = png.with_suffix(".i").read_bytes()
                    image = read_picture(png.read_bytes())
                    # A compressed project stores a 1-by-1 picture raw.
                    one_pixel = image.width * image.height == 1
                    expected_kind = FORMAT_RAW if one_pixel and kind == FORMAT_COMPRESSED else kind
                    self.assertEqual(screen_copy_format(block), expected_kind)
                    if is_compressed_format_3(block):
                        with self.assertRaises(UndecodedScreenCopyError):
                            decode_screen_copy(block, rotation)
                        continue
                    self.assertTrue(matches_within_editor_rounding(
                        decode_screen_copy(block, rotation), image, expected_kind))

    def test_only_its_own_rotation_fits_a_picture_with_distinct_pixels(self):
        for folder, kind, rotation in self.folders():
            with self.subTest(folder=folder.name):
                block = (folder / "18-unique-9x7.i").read_bytes()
                image = read_picture((folder / "18-unique-9x7.png").read_bytes())
                fitting = []
                for candidate in ROTATIONS:
                    try:
                        if matches_within_editor_rounding(decode_screen_copy(block, candidate),
                                                          image, kind):
                            fitting.append(candidate)
                    except NxwrightError:
                        pass
                # Format 3 stores every rotation in the 0-degree order.
                expected = list(ROTATIONS) if kind == FORMAT_RAW_WITH_HEADER else [rotation]
                self.assertEqual(fitting, expected)

    def test_encoding_gives_back_the_editors_layout(self):
        for folder, kind, rotation in self.folders():
            for block_path in sorted(folder.glob("*.i")):
                block = block_path.read_bytes()
                if screen_copy_format(block) != kind or is_compressed_format_3(block):
                    continue
                with self.subTest(folder=folder.name, picture=block_path.stem):
                    pixels = decode_screen_copy(block, rotation)
                    encoded = encode_screen_copy(pixels, kind, rotation)
                    self.assertEqual(decode_screen_copy(encoded, rotation), pixels)
                    if kind == FORMAT_COMPRESSED:
                        # The header and second header, sides swapped at 90 and 270 degrees.
                        self.assertEqual(encoded[:16] + encoded[24:44], block[:16] + block[24:44])
                    else:
                        self.assertEqual(encoded, block)


class EditorRoundingTest(unittest.TestCase):

    def test_tolerance(self):
        # One opaque pixel and one partly transparent pixel, in each format.
        # Only the partly transparent one may be off, and by one step at most.
        # 0x0020 is one step of green in an RGB565 colour.
        image = rgba_image(2, 1, [(8, 8, 8, 255), (200, 100, 50, 120)])
        for kind in (FORMAT_COMPRESSED, FORMAT_RAW):
            with self.subTest(kind=kind):
                base = stored_pixels(image, kind)
                one_step = ScreenPixels(2, 1, [base.colours[0], base.colours[1] + 0x0020], base.alphas)
                two_steps = ScreenPixels(2, 1, [base.colours[0], base.colours[1] + 0x0040], base.alphas)
                opaque_off = ScreenPixels(2, 1, [base.colours[0] + 0x0020, base.colours[1]], base.alphas)
                self.assertTrue(matches_within_editor_rounding(base, image, kind))
                self.assertTrue(matches_within_editor_rounding(one_step, image, kind))
                self.assertFalse(matches_within_editor_rounding(two_steps, image, kind))
                self.assertFalse(matches_within_editor_rounding(opaque_off, image, kind))


if __name__ == "__main__":
    unittest.main()
