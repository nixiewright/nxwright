"""The pictures, the fonts, and on P the animations, videos, and sounds of
a TFT file's resources section, turned back into their project blocks
(tft/decompiling/resources.py): the blocks the compile's packaging lays
out in the section's parts (packaging.py), read back, as nxwright keeps
them.

Each test gives packaging's own layout of the parts its input, and compares
what the decoder gives with packaging's input: pictures, animations,
videos, and sounds nxwright writes, and the base folder's fonts, as the TFT
file keeps them, which a project may keep them as too.
"""
from dataclasses import replace
import io
import unittest
import wave

from nxwright.project.media_files import animation_files, sound_file, video_file, video_frame
from nxwright.project.screen_copy import FORMAT_COMPRESSED, encode_screen_copy, stored_pixels
from nxwright.project.zi_font import decode_font, turned_font
from PIL import Image

from nxwright.tft import packaging
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.resources import (media_blocks, picture_blocks, sound_blocks,
                                         stored_font_blocks)
from tests.tft.unit_inputs import font_in_other_bytes, page, project_of, with_font_blocks


def _pictures() -> list:
    """Returns the blocks of three pictures nxwright writes, 8 by 4 pixels,
    of three colours, as a project keeps them."""
    return [encode_screen_copy(stored_pixels(Image.new("RGBA", (8, 4), colour),
                                             FORMAT_COMPRESSED), FORMAT_COMPRESSED, 0)
            for colour in ((255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 128))]


def _picture_part(blocks: list) -> bytes:
    """Returns the section's part of the pictures `blocks`, as packaging lays
    it out."""
    return packaging._headers_first(blocks, packaging.PICTURE_HEADER,
                                    packaging.PICTURE_PLACE_FIELD, packaging.PICTURE_ID_FIELD)


class PicturesTest(unittest.TestCase):

    def test_three_pictures(self):
        blocks = _pictures()
        self.assertEqual(picture_blocks(_picture_part(blocks), 3), blocks)

    def test_one_picture_is_its_block(self):
        # One block alone is the same in the part and in the project.
        block = _pictures()[0]
        self.assertEqual(_picture_part([block]), block)
        self.assertEqual(picture_blocks(block, 1), [block])

    def test_no_picture(self):
        self.assertEqual(picture_blocks(b"", 0), [])

    def test_a_part_out_of_order(self):
        # The second picture's header places its rest before the first's,
        # or past the part's end.
        part = bytearray(_picture_part(_pictures()))
        for place in (0, len(part) + 1):
            with self.subTest(place):
                broken = bytearray(part)
                broken[packaging.PICTURE_HEADER + packaging.PICTURE_PLACE_FIELD:
                       packaging.PICTURE_HEADER + packaging.PICTURE_PLACE_FIELD + 4] = (
                    place.to_bytes(4, "little"))
                self.assertRaises(DecodeError, picture_blocks, bytes(broken), 3)

    def test_a_part_cut_short(self):
        # The part ends inside the headers of its three pictures.
        part = _picture_part(_pictures())
        self.assertRaises(DecodeError, picture_blocks, part[:packaging.PICTURE_HEADER * 2], 3)


class FontsTest(unittest.TestCase):

    def project(self, series: str, rotation: int):
        """Returns a Project of facts of `series` at `rotation`, with the
        base folder's fonts turned to that rotation, as a project keeps
        them."""
        project = with_font_blocks(project_of(series=series, rotation=rotation), series)
        names = [name for kind, name in project.resources if kind == "font"]
        return replace(project, blocks={**project.blocks, **{
            name: turned_font(project.blocks[name], rotation) for name in names}}), names

    def test_each_series_and_rotation(self):
        # The decoder gives each font as the TFT file keeps it, and turns
        # none: at 0 degrees on F, and at the project's rotation on T and K.
        # A project may keep a font so, and the compile writes it as it is.
        compared = 0
        for series in ("T", "K", "F"):
            for rotation in (0, 90, 180, 270):
                project, names = self.project(series, rotation)
                fonts = packaging._fonts(project)
                part = packaging._headers_first(fonts, packaging.FONT_HEADER,
                                                packaging.FONT_PLACE_FIELD)
                with self.subTest(series=series, rotation=rotation):
                    given = stored_font_blocks(part, len(names))
                    self.assertEqual(given, fonts)
                    again = replace(project, blocks={**project.blocks, **dict(zip(names, given))})
                    self.assertEqual(packaging._fonts(again), fonts)
                compared += 1
        self.assertEqual(compared, 12)

    def test_a_font_part_out_of_order(self):
        # Two fonts, the second's header placing its rest before the first's.
        project, names = self.project("T", 0)
        fonts = [project.blocks[names[0]]] * 2
        part = bytearray(packaging._headers_first(fonts, packaging.FONT_HEADER,
                                                  packaging.FONT_PLACE_FIELD))
        at = packaging.FONT_HEADER + packaging.FONT_PLACE_FIELD
        part[at:at + 4] = bytes(4)
        self.assertRaises(DecodeError, stored_font_blocks, bytes(part), 2)

    def test_a_font_already_at_0_degrees_on_f(self):
        # On F at 90 degrees, a font the project keeps at 0 degrees is
        # written as it is, though nxwright would code its glyph otherwise.
        project, names = self.project("F", 90)
        ours, other = font_in_other_bytes(project.settings.encoding)
        self.assertEqual(turned_font(other, 0), ours)
        self.assertEqual(decode_font(other).rotation, 0)
        project = replace(project, blocks={**project.blocks, names[0]: other})
        self.assertEqual(packaging._fonts(project), [other])

    def test_a_font_at_the_project_s_rotation_is_turned_on_f_alone(self):
        # The part holds F's fonts at 0 degrees, unlike the project's. On the
        # other series, the TFT file keeps a font at the project's rotation.
        project, names = self.project("F", 90)
        self.assertNotEqual(packaging._fonts(project), [project.blocks[name] for name in names])


def _media_part(blocks: list) -> bytes:
    """Returns the section's part of the animations or the videos `blocks`,
    as packaging lays it out."""
    return packaging._headers_first(blocks, packaging.MEDIA_HEADER, packaging.MEDIA_PLACE_FIELD)


def _sound(samples: int, name: str) -> bytes:
    """Returns a sound's block, as nxwright keeps it, of `samples` samples
    of silence, mono, at 22050 a second of 16 bits, named `name`."""
    out = io.BytesIO()
    with wave.open(out, "wb") as written:
        written.setnchannels(1)
        written.setsampwidth(2)
        written.setframerate(22050)
        written.writeframes(bytes(2 * samples))
    return sound_file(out.getvalue(), name)


def p_project_with_media():
    """Returns (a Project of facts on P of a blank page, with the base
    folder's fonts, an animation, a video, and two sounds, then those blocks, {kind: [block]}
    in ID order, the animation's GmovMaker file apart)."""
    gmovmaker, screen = animation_files([(Image.new("RGBA", (16, 8), (255, 0, 0, 255)), 100),
                                         (Image.new("RGBA", (16, 8), (0, 0, 255, 255)), 50)])
    video = video_file(16, 8, 10, [video_frame(Image.new("RGBA", (16, 8), (0, 255, 0, 255)))])
    sounds = [_sound(100, "beep"), _sound(31, "")]
    project = with_font_blocks(project_of(page(series="P"), series="P"), "P")
    blocks = {"0.gmov": screen, "0.gmovs": gmovmaker, "0.v": video, "0.wav": sounds[0],
              "1.wav": sounds[1]}
    project = replace(project, resources=project.resources + [
        ("animation", "0.gmov"), ("video", "0.v"), ("sound", "0.wav"), ("sound", "1.wav")],
        blocks={**project.blocks, **blocks})
    return project, {"animation": [screen], "gmovmaker": [gmovmaker], "video": [video],
                     "sound": sounds}


class MediaTest(unittest.TestCase):

    def test_animations_and_videos(self):
        # Two animations' screen forms, and two videos, of a frame or two
        # of a colour each.
        animations = [animation_files([(Image.new("RGBA", (16, 8), colour), 100)] * frames)[1]
                      for colour, frames in (((255, 0, 0, 255), 1), ((0, 0, 255, 255), 2))]
        videos = [video_file(16, 8, rate, [video_frame(Image.new("RGBA", (16, 8), colour))] * 2)
                  for colour, rate in (((0, 255, 0, 255), 10), ((255, 255, 0, 255), 25))]
        for blocks in (animations, videos):
            with self.subTest(blocks[0][:4]):
                self.assertEqual(media_blocks(_media_part(blocks), 2), blocks)
        self.assertEqual(media_blocks(b"", 0), [])

    def test_sounds(self):
        # Each sound's header gives where its file lies in the part, and its
        # length.
        blocks = [_sound(100, "beep"), _sound(31, "")]
        self.assertEqual(sound_blocks(packaging._sounds(blocks), 2), blocks)
        self.assertEqual(sound_blocks(b"", 0), [])

    def test_a_sounds_part_out_of_order(self):
        # A header placing its sound past the part's end, or before the
        # headers, or a part cut short inside them, is refused.
        part = packaging._sounds([_sound(100, "beep"), _sound(31, "")])
        size = packaging.SOUND_HEADER.size
        for header in (packaging.SOUND_HEADER.pack(len(part), 4),
                       packaging.SOUND_HEADER.pack(0, 4)):
            with self.subTest(header):
                self.assertRaises(DecodeError, sound_blocks, header + part[size:], 2)
        self.assertRaises(DecodeError, sound_blocks, part[:size], 2)


if __name__ == "__main__":
    unittest.main()
