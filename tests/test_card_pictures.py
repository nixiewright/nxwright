"""The picture files an external picture shows from an SD card, as PictureBox
writes them (.xi), and `nxwright sd-picture`.

tests/fixtures/media/xi/ holds a probe's files: PictureBox V1.1's files of
three pictures nxwright made, named <picture>-<quality>-<rotation>.xi.
smooth.png is 80 by 60 of smooth colours, with a white last column and a black
last row; odd.png is 33 by 17, red, its top 4 rows wholly transparent and its
bottom 4 half transparent; dots.png is 16 by 2, its first row transparent at
every other pixel, its second row's right half at alpha 64.
"""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.media_files import (CARD_PICTURE_QUALITIES, card_picture_file,
                                          read_card_picture)
from nxwright.project.pictures import read_picture
from nxwright.project.screen_copy import decode_alphas, encode_alphas
from nxwright.source.resource_adding import write_card_pictures
from tests.pictures import read_jpeg
from tests.test_making_media import mean_difference

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "media" / "xi"


def picture(name: str):
    return read_picture((FIXTURES / (name + ".png")).read_bytes())


def quantisation(jpeg: bytes) -> bytes:
    """A JPEG picture's quantisation tables, as its segments hold them."""
    return jpeg[jpeg.index(b"\xff\xdb"):jpeg.index(b"\xff\xc0")]


class CardPictureFileTest(unittest.TestCase):

    def test_pictureboxs_files_are_made_again(self):
        # The header but for its sizes, the alpha section, and the JPEG's
        # tables byte for byte; the JPEG's pixels within its loss.
        for theirs in sorted(FIXTURES.glob("*.xi")):
            name, quality, rotation = theirs.stem.split("-")
            with self.subTest(theirs.name):
                data = theirs.read_bytes()
                ours = card_picture_file(picture(name), int(quality), int(rotation))
                self.assertEqual(ours[:24], data[:24])
                expected, made = read_card_picture(data), read_card_picture(ours)
                self.assertEqual(made.alphas, expected.alphas)
                self.assertEqual(quantisation(made.jpeg), quantisation(expected.jpeg))
                their_pixels, our_pixels = read_jpeg(expected.jpeg), read_jpeg(made.jpeg)
                self.assertEqual(our_pixels[:2], their_pixels[:2])
                self.assertLess(mean_difference(our_pixels[2], their_pixels[2]), 2)

    def test_qualities_by_pictureboxs_names(self):
        self.assertEqual(CARD_PICTURE_QUALITIES, {"highest": 100, "very-high": 96, "high": 80,
                                                  "middle": 70, "low": 50, "very-low": 30})

    def test_a_file_read(self):
        odd = read_card_picture((FIXTURES / "odd-96-90.xi").read_bytes())
        self.assertEqual((odd.width, odd.height, odd.rotation), (33, 17, 90))
        self.assertEqual(read_jpeg(odd.jpeg)[:2], (32, 48))
        # Turned clockwise: the top rows, wholly transparent, are at the right.
        self.assertEqual(odd.alphas[:32], (0,) * 15 + (63,) * 4 + (127,) * 9 + (0,) * 4)
        self.assertIsNone(read_card_picture((FIXTURES / "smooth-96-0.xi").read_bytes()).alphas)

    def test_what_it_cannot_take_is_refused(self):
        smooth = picture("smooth")
        with self.assertRaisesRegex(NxwrightError, "a rotation is one of 0, 90, 180, 270"):
            card_picture_file(smooth, 96, 45)
        with self.assertRaisesRegex(NxwrightError, "quality is from 1 to 100"):
            card_picture_file(smooth, 0, 0)
        good = (FIXTURES / "odd-96-0.xi").read_bytes()
        marker_past = good[:8] + bytes([0x0E]) + good[9:]
        no_jpeg = good[:32] + b"\0\0" + good[34:]
        # A header of 49 by 17 implies a JPEG of 64 by 32, where it is 48 by 32.
        other_size = good[:20] + struct.pack("<H", 49) + good[22:]
        # Its last run, of 225 pixels, made one short.
        short_alpha = good[:-1] + bytes([good[-1] - 1])
        for data, reason in ((b"\x89PNG", "not a picture file of PictureBox's"),
                             (good[:200], "cut short"), (marker_past, "rotation marker 0xe"),
                             (no_jpeg, "holds no JPEG picture"),
                             (other_size, "JPEG picture is not the 64 by 32 its header gives"),
                             (short_alpha, "the .xi file's alpha section does not cover")):
            with self.subTest(reason):
                with self.assertRaisesRegex(NxwrightError, reason):
                    read_card_picture(data)


class AlphaSectionTest(unittest.TestCase):
    """A screen copy's alpha section, which PictureBox's files share."""

    def test_decoded_as_encoded(self):
        alphas = [127] * 300 + [0, 127, 0] + [63] * 2
        self.assertEqual(decode_alphas(encode_alphas(alphas), len(alphas)), alphas)

    def test_one_that_does_not_cover_the_picture_is_refused(self):
        section = encode_alphas([127] * 10)
        for count in (9, 11):
            with self.assertRaisesRegex(NxwrightError, "does not cover the picture exactly"):
                decode_alphas(section, count)


class SdPictureCommandTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.output = self.folder / "card"

    def tearDown(self):
        self._folder.cleanup()

    def test_each_picture_is_written(self):
        paths = write_card_pictures([FIXTURES / "odd.png", FIXTURES / "smooth.png"], self.output,
                                    "high", 180)
        self.assertEqual([path.name for path in paths], ["odd.xi", "smooth.xi"])
        self.assertEqual(paths[1].read_bytes(),
                         card_picture_file(picture("smooth"), 80, 180))

    def test_what_would_go_wrong_is_refused_before_writing(self):
        self.output.mkdir()
        (self.output / "smooth.xi").write_bytes(b"theirs")
        with self.assertRaisesRegex(NxwrightError, "smooth.xi is already there"):
            write_card_pictures([FIXTURES / "odd.png", FIXTURES / "smooth.png"], self.output)
        self.assertEqual(sorted(path.name for path in self.output.iterdir()), ["smooth.xi"])
        other = self.folder / "ODD.png"
        other.write_bytes((FIXTURES / "odd.png").read_bytes())
        with self.assertRaisesRegex(NxwrightError, "odd.png and ODD.png would both be written"):
            write_card_pictures([FIXTURES / "odd.png", other], self.folder / "new")
        with self.assertRaisesRegex(NxwrightError, "a quality is one of highest, very-high"):
            write_card_pictures([FIXTURES / "odd.png"], self.folder / "new", "best")
        self.assertFalse((self.folder / "new").exists())

    def test_another_kind_of_picture_is_read_too(self):
        damaged = self.folder / "damaged.bmp"
        damaged.write_bytes(b"BM")
        with self.assertRaisesRegex(NxwrightError, "damaged.bmp: not a picture nxwright reads"):
            write_card_pictures([damaged], self.output)
        bmp = self.folder / "logo.bmp"
        picture("dots").convert("RGB").save(bmp)
        write_card_pictures([bmp], self.output)
        self.assertEqual(read_card_picture((self.output / "logo.xi").read_bytes()).width, 16)

    def test_the_command_takes_its_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["sd-picture", str(FIXTURES / "odd.png"), "--output",
                                   str(self.output), "--quality", "low", "--rotation", "270"]), 0)
        self.assertIn("odd.xi", output.getvalue())
        made = (self.output / "odd.xi").read_bytes()
        self.assertEqual(struct.unpack_from("<B", made, 8)[0], 0x0D)
        self.assertEqual(made, card_picture_file(picture("odd"), 50, 270))


if __name__ == "__main__":
    unittest.main()
