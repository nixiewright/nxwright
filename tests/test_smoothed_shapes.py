"""Smoothed shapes drawn through Pillow (smoothed_shapes.py): what each pixel
takes of a shape, and that drawing a picture band by band, over the part its
shapes reach, changes none of its pixels. How close the shapes come to the
Editor's is tested with the widgets that draw them (test_page_drawing.py)."""
import math
import unittest
from unittest import mock

from nxwright.drawing import smoothed_shapes
from nxwright.drawing.smoothed_shapes import SmoothedPicture, rounded_bar
from nxwright.project.pictures import read_picture

RED, BLUE, GREEN = (200, 0, 0), (0, 0, 200), (0, 150, 0)


def pixels(picture: SmoothedPicture) -> tuple:
    return read_picture(picture.png()).get_flattened_data()


def mixed_picture(width: int, height: int) -> SmoothedPicture:
    """A picture of each kind of shape, partly past its edges, a needle's
    polygon among them, whose points fall between sub-pixels."""
    picture = SmoothedPicture(width, height)
    picture.ellipse((-3.5, 2.5, 20.5, 31.5), RED)
    picture.rounded_rectangle((4.5, 0.5, 27.5, 13.5), 3.625, BLUE)
    angle = math.radians(33)
    centre, tip = (width / 2 + 0.5, height / 2 + 0.5), height / 2 - 1
    picture.polygon([(centre[0] - math.cos(angle) * tip, centre[1] - math.sin(angle) * tip),
                     (centre[0] + 1.3, centre[1] - 0.7), (centre[0] - 1.3, centre[1] + 0.7)],
                    GREEN)
    return picture


class SmoothedPictureTest(unittest.TestCase):

    def test_a_pixel_takes_the_share_of_it_a_shape_covers(self):
        # A quarter of the pixel: its top-left quarter.
        picture = SmoothedPicture(2, 1)
        picture.rounded_rectangle((0, 0, 0.5, 0.5), 0, RED)
        (*colour, alpha), clear = pixels(picture)
        self.assertLessEqual(abs(alpha - 64), 1)
        self.assertLessEqual(max(abs(a - b) for a, b in zip(colour, RED)), 2)
        self.assertEqual(clear[3], 0)

    def test_a_shape_covers_those_before_it(self):
        picture = SmoothedPicture(4, 4)
        picture.ellipse((0, 0, 4, 4), RED)
        picture.rounded_rectangle((1, 1, 3, 3), 0, BLUE)
        self.assertEqual(read_picture(picture.png()).getpixel((1, 1)), BLUE + (255,))

    def test_the_bands_and_the_part_drawn_change_no_pixel(self):
        width, height = 31, 40
        whole = pixels(mixed_picture(width, height))
        # A band of a single row at a time.
        with mock.patch.object(smoothed_shapes, "_MOST_BAND_SUB_PIXELS", 1):
            self.assertEqual(pixels(mixed_picture(width, height)), whole)
        # A dot at the far corner widens the part drawn to the whole picture.
        widened = mixed_picture(width, height)
        widened.ellipse((width - 1, height - 1, width, height), RED)
        self.assertEqual(pixels(widened)[:-1], whole[:-1])

    def test_a_shape_past_the_picture_draws_what_is_in_it(self):
        picture = SmoothedPicture(4, 4)
        picture.ellipse((-10, -10, -2, -2), RED)
        self.assertEqual(set(pixels(picture)), {(0, 0, 0, 0)})

    def test_a_box_shorter_than_two_roundings_is_its_ends_rounding_cut_by_the_box(self):
        # 4 pixels long, rounded by 4: the right half of a rounding 8 across,
        # its left edge the box's.
        picture = SmoothedPicture(8, 10)
        picture.rounded_rectangle((2, 0, 6, 10), 4, RED)
        alphas = read_picture(picture.png()).getchannel("A")
        self.assertEqual([alphas.getpixel((x, y)) for x in (0, 1, 6, 7) for y in range(10)],
                         [0] * 40)
        self.assertEqual([alphas.getpixel((2, y)) for y in range(1, 9)], [255] * 8)
        self.assertEqual([alphas.getpixel((x, y)) for x in range(8) for y in range(10)],
                         [alphas.getpixel((x, 9 - y)) for x in range(8) for y in range(10)])
        self.assertLess(alphas.getpixel((5, 0)), alphas.getpixel((5, 5)))


class RoundedBarTest(unittest.TestCase):

    def test_a_bar_running_up_is_the_bar_across_turned(self):
        across = read_picture(rounded_bar(30, 12, 3.625, 11, False, BLUE, RED))
        up = read_picture(rounded_bar(12, 30, 3.625, 11, True, BLUE, RED))
        self.assertEqual(up.size, (12, 30))
        self.assertEqual([up.getpixel((y, 29 - x)) for x in range(30) for y in range(12)],
                         [across.getpixel((x, y)) for x in range(30) for y in range(12)])


if __name__ == "__main__":
    unittest.main()
