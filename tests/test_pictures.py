"""Pictures read and written through Pillow: the kinds of picture file
nxwright reads, a picture's size, and the PNG files it writes."""
import io
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from PIL import Image

from nxwright import NxwrightError
from nxwright.project.pictures import (exif_orientation, picture_problem, picture_size,
                                       read_picture, still_picture_size, write_png)


def png_bytes(width: int, height: int, colour_type: int, rows: list, extra=(), depth=8,
              interlace=0) -> bytes:
    """Builds a PNG of `rows`, each stored unfiltered. An interlaced PNG's
    rows are those of its passes, in order."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    header = struct.pack(">IIBBBBB", width, height, depth, colour_type, 0, 0, interlace)
    data = zlib.compress(b"".join(b"\0" + bytes(row) for row in rows))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + b"".join(chunk(kind, body) for kind, body in extra)
            + chunk(b"IDAT", data) + chunk(b"IEND", b""))


def saved(picture: Image.Image, kind: str, **options) -> bytes:
    out = io.BytesIO()
    picture.save(out, kind, **options)
    return out.getvalue()


class ReadPictureTest(unittest.TestCase):

    def assert_pixels(self, image: Image.Image, width: int, height: int, pixels: list):
        """Compares pixels alone: an image read also carries its file's facts."""
        self.assertEqual((image.mode, image.size), ("RGBA", (width, height)))
        self.assertEqual(image.get_flattened_data(), tuple(pixels))

    def test_each_colour_type_is_read_as_rgba(self):
        cases = {
            "grey": (0, [[10, 20]], [(10, 10, 10, 255), (20, 20, 20, 255)], ()),
            "grey with alpha": (4, [[10, 5, 20, 6]], [(10, 10, 10, 5), (20, 20, 20, 6)], ()),
            "rgb": (2, [[1, 2, 3, 4, 5, 6]], [(1, 2, 3, 255), (4, 5, 6, 255)], ()),
            "rgb with a colour key": (2, [[1, 2, 3, 4, 5, 6]], [(1, 2, 3, 0), (4, 5, 6, 255)],
                                      ((b"tRNS", bytes([0, 1, 0, 2, 0, 3])),)),
            "palette with alpha": (3, [[1, 0]], [(4, 5, 6, 255), (1, 2, 3, 9)],
                                   ((b"PLTE", bytes([1, 2, 3, 4, 5, 6])), (b"tRNS", bytes([9])))),
        }
        for case, (colour_type, rows, pixels, extra) in cases.items():
            with self.subTest(case=case):
                self.assert_pixels(read_picture(png_bytes(2, 1, colour_type, rows, extra)),
                                   2, 1, pixels)

    def test_16_bit_channels_keep_their_high_byte(self):
        grey = png_bytes(3, 1, 0, [[0x00, 0x00, 0x12, 0x80, 0xFF, 0xFF]], depth=16)
        self.assert_pixels(read_picture(grey), 3, 1,
                           [(0, 0, 0, 255), (18, 18, 18, 255), (255, 255, 255, 255)])
        rgb = png_bytes(1, 1, 2, [[0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]], depth=16)
        self.assert_pixels(read_picture(rgb), 1, 1, [(0x12, 0x56, 0x9A, 255)])

    def test_a_16_bit_grey_pictures_colour_key_is_matched_on_16_bits(self):
        # The Editor's screen copy of such a picture, keyed on 0x1234, made
        # that grey transparent, and 0x1299, of the same high byte, opaque.
        grey = png_bytes(3, 1, 0, [[0x12, 0x34, 0x12, 0x99, 0xAB, 0xAB]],
                         ((b"tRNS", bytes([0x12, 0x34])),), depth=16)
        self.assert_pixels(read_picture(grey), 3, 1,
                           [(18, 18, 18, 0), (18, 18, 18, 255), (171, 171, 171, 255)])

    def test_a_16_bit_colour_picture_with_a_colour_key_is_refused(self):
        # The Editor matched the key on 16 bits a channel too; Pillow gives
        # the channels at 8, which would take a colour of the key's high
        # bytes, as the second pixel's, for the key.
        rgb = png_bytes(2, 1, 2, [[0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC,
                                   0x12, 0x99, 0x56, 0x99, 0x9A, 0x99]],
                        ((b"tRNS", bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])),), depth=16)
        with self.assertRaisesRegex(NxwrightError, "^a PNG of 16 bits a channel, with a colour key"):
            read_picture(rgb)
        # Interlaced too: a 1 by 1 picture's one pass.
        interlaced = png_bytes(1, 1, 2, [[0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]],
                               ((b"tRNS", bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])),),
                               depth=16, interlace=1)
        with self.assertRaisesRegex(NxwrightError, "^a PNG of 16 bits a channel, with a colour key"):
            read_picture(interlaced)

    def test_an_interlaced_png_is_read(self):
        # A 2 by 2 picture's passes: the top-left pixel, then the top-right,
        # then the bottom row.
        png = png_bytes(2, 2, 2, [[1, 2, 3], [4, 5, 6], [7, 8, 9, 10, 11, 12]], interlace=1)
        self.assert_pixels(read_picture(png), 2, 2,
                           [(1, 2, 3, 255), (4, 5, 6, 255), (7, 8, 9, 255), (10, 11, 12, 255)])

    def test_a_gif_is_read_by_its_first_frame(self):
        red, blue = Image.new("RGB", (2, 1), (255, 0, 0)), Image.new("RGB", (2, 1), (0, 0, 255))
        gif = saved(red, "GIF", save_all=True, append_images=[blue])
        self.assert_pixels(read_picture(gif), 2, 1, [(255, 0, 0, 255)] * 2)

    def test_a_jpeg_is_read(self):
        jpeg = saved(Image.new("RGB", (16, 8), (200, 100, 50)), "JPEG", quality=95)
        image = read_picture(jpeg)
        self.assertEqual((image.mode, image.size), ("RGBA", (16, 8)))
        red, green, blue, alpha = image.getpixel((3, 3))
        self.assertLessEqual(max(abs(red - 200), abs(green - 100), abs(blue - 50)), 2)
        self.assertEqual(alpha, 255)

    def test_what_is_not_a_picture_is_refused(self):
        # Cut past its end and its compressed data's checksum, into its pixels.
        cut_short = png_bytes(16, 16, 2, [range(48)] * 16)[:-30]
        # Pillow refuses a picture of this many pixels as it opens it.
        too_many_pixels = png_bytes(20000, 20000, 0, [])
        for case, data in {"empty": b"", "not a picture": b"GIF89a", "cut short": cut_short,
                           "too many pixels": too_many_pixels}.items():
            with self.subTest(case=case):
                with self.assertRaisesRegex(NxwrightError, "not a picture nxwright reads"):
                    read_picture(data)

    def test_what_opening_a_picture_finds(self):
        # What a picture's file shows as it is opened, without its pixels:
        # the same words read_picture gives, a file of no kind Pillow knows
        # in nxwright's own, not Pillow's, which name a memory buffer.
        unknown = "not a picture nxwright reads: no kind of picture Pillow knows"
        keyed = png_bytes(1, 1, 2, [[0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]],
                          ((b"tRNS", bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])),), depth=16)
        for data, words in ((b"GIF89a", unknown), (b"", unknown),
                            (png_bytes(20000, 20000, 0, []), "not a picture nxwright reads"),
                            (keyed, "a PNG of 16 bits a channel, with a colour key")):
            with self.subTest(words=words, data=data[:6]):
                self.assertTrue(picture_problem(data).startswith(words))
                with self.assertRaises(NxwrightError) as raised:
                    read_picture(data)
                self.assertEqual(str(raised.exception), picture_problem(data))
        # A picture whose pixels alone are damaged opens, so opening finds nothing.
        cut_short = png_bytes(16, 16, 2, [range(48)] * 16)[:-30]
        self.assertIsNone(picture_problem(cut_short))
        self.assertIsNone(picture_problem(png_bytes(2, 1, 0, [[10, 20]])))


class PictureSizeTest(unittest.TestCase):

    def test_a_pictures_size_or_its_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            picture = Path(folder) / "wide.png"
            picture.write_bytes(write_png(5, 2, bytes(40)))
            self.assertEqual(picture_size(picture), (5, 2))
            text = Path(folder) / "notes.png"
            text.write_text("not a picture")
            with self.assertRaisesRegex(NxwrightError, "notes.png: not a picture nxwright reads"):
                picture_size(text)
            with self.assertRaisesRegex(NxwrightError, "absent.png: not a picture nxwright reads"):
                picture_size(Path(folder) / "absent.png")


class StillPictureSizeTest(unittest.TestCase):

    def test_a_still_picture_or_none(self):
        with tempfile.TemporaryDirectory() as folder:
            still, animated = Path(folder) / "still.png", Path(folder) / "spin.gif"
            still.write_bytes(write_png(5, 2, bytes(40)))
            first, second = Image.new("RGB", (4, 3), (255, 0, 0)), Image.new("RGB", (4, 3))
            first.save(animated, save_all=True, append_images=[second])
            # An MPEG-1 video stream's header, which Pillow knows but cannot decode.
            stream = Path(folder) / "clip.m1v"
            stream.write_bytes(b"\x00\x00\x01\xb3\x14\x00\xf0\x13" + bytes(64))
            # An MPO photo, two views of one moment, as a phone's 3D photo:
            # one still picture, Pillow reading its first view.
            photo = Path(folder) / "photo.jpg"
            first.save(photo, "MPO", save_all=True, append_images=[second])
            self.assertEqual([still_picture_size(path)
                              for path in (still, animated, stream, photo)],
                             [(5, 2), None, None, (4, 3)])
            # Its first view, red, not its second, black, within JPEG's loss.
            red, green, _, _ = read_picture(photo.read_bytes()).getpixel((0, 0))
            self.assertGreater(red, 240)
            self.assertLess(green, 16)


class ExifOrientationTest(unittest.TestCase):
    """The EXIF orientation of a picture file, read from the block Pillow
    finds as it opens it."""

    def orientation_of(self, data: bytes) -> int:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "picture"
            path.write_bytes(data)
            return exif_orientation(path)

    def with_orientation(self, kind: str, orientation: int) -> bytes:
        exif = Image.Exif()
        exif[0x0112] = orientation
        return saved(Image.new("RGB", (4, 2)), kind, exif=exif)

    def test_a_jpegs_and_a_pngs(self):
        for orientation in (1, 6, 9):
            with self.subTest(orientation=orientation):
                self.assertEqual(self.orientation_of(self.with_orientation("JPEG", orientation)),
                                 orientation)
        # Pillow writes a PNG's eXIf chunk before its pixels, where it is read.
        self.assertEqual(self.orientation_of(self.with_orientation("PNG", 6)), 6)

    def test_none_counts_as_1(self):
        plain = saved(Image.new("RGB", (4, 2)), "JPEG")
        # A JPEG whose EXIF block is damaged: its APP1 segment holds no TIFF data.
        body = b"Exif\x00\x00garbage"
        damaged = plain[:2] + b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body + plain[2:]
        for case, data in {"no EXIF": plain, "a damaged EXIF block": damaged,
                           "not a picture": b"text"}.items():
            with self.subTest(case=case):
                self.assertEqual(self.orientation_of(data), 1)


class WritePngTest(unittest.TestCase):

    def test_written_pixels_read_back(self):
        rgba = bytes(range(7 * 3 * 4))
        image = read_picture(write_png(7, 3, rgba))
        self.assertEqual((image.size, image.tobytes()), ((7, 3), rgba))

    def test_any_other_number_of_pixels_is_refused(self):
        for size in (15, 17):
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    write_png(2, 2, bytes(size))


if __name__ == "__main__":
    unittest.main()
