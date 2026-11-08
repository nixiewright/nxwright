"""Writing a new resource into an existing resource's place, its slot, by the
functions that add each kind (source/resource_adding.py): the new files are
written, app.toml names the new resource where the old one was, so that its
ID stays, and the old resource's other files are deleted."""
import io
from pathlib import Path
from unittest import mock

from PIL import Image

from nxwright import NxwrightError
from nxwright.project.pictures import write_png
from nxwright.project.truetype import NOTO_SANS
from nxwright.source.resource_adding import (Slot, add_animation, add_font, add_font_file,
                                             add_pictures, add_sound, add_video)
from nxwright.source.source_folder import resource_file_paths
from tests.test_making_videos_and_sounds import SOURCES
from tests.test_remove_resource import RemoveResourceTestCase


class SlotTest(RemoveResourceTestCase):

    def picture(self, name: str, colour: tuple, suffix: str = ".png") -> Path:
        """Writes an 8-by-8 picture of `colour` outside the source folder."""
        path = self.folder / (name + suffix)
        if suffix == ".png":
            path.write_bytes(write_png(8, 8, bytes(colour + (255,)) * 64))
        else:
            image = io.BytesIO()
            Image.new("RGB", (8, 8), colour).save(image, format="BMP")
            path.write_bytes(image.getvalue())
        return path

    def test_each_kind_keeps_its_place_and_name(self):
        green = self.picture("green", (0, 255, 0))
        before = self.files()
        add_pictures(self.source, [green], replacing=Slot("a"))
        add_font(self.source, NOTO_SANS, 20, "NotoSans24", replacing=Slot("NotoSans24"))
        add_animation(self.source, [green], 200, "blink", replacing=Slot("blink"))
        add_video(self.source, [green], name="clip", replacing=Slot("clip"))
        add_sound(self.source, SOURCES / "short22k.wav", "beep", replacing=Slot("beep"))
        app = self.app()
        self.assertEqual((app["pictures"], app["fonts"], app["animations"], app["videos"],
                          app["sounds"]),
                         (["a", "b"], ["NotoSans24", "NotoSans16"], ["blink"], ["clip"],
                          ["beep"]))
        after = self.files()
        for path in ("pictures/a.png", "fonts/NotoSans24.zi", "animations/blink.gmov",
                     "animations/blink.screen.gmov", "videos/clip.video"):
            with self.subTest(path=path):
                self.assertNotEqual(after[path], before[path])
        self.assertEqual(after["pictures/a.png"], green.read_bytes())

    def test_a_new_name_takes_the_old_ones_place(self):
        add_pictures(self.source, [self.picture("green", (0, 255, 0))], replacing=Slot("a"),
                     name="green")
        self.assertEqual(self.app()["pictures"], ["green", "b"])
        self.assertTrue((self.source / "pictures" / "green.png").is_file())
        self.assertFalse((self.source / "pictures" / "a.png").exists())
        add_sound(self.source, SOURCES / "short22k.wav", "chime", replacing=Slot("beep"))
        self.assertEqual(self.app()["sounds"], ["chime"])
        self.assertFalse((self.source / "sounds" / "beep.wav").exists())

    def test_a_name_differing_in_letter_case_alone(self):
        # On a file system that ignores letter case, A.png is a.png: the file
        # just written is not the old one to delete.
        add_pictures(self.source, [self.picture("green", (0, 255, 0))], replacing=Slot("a"),
                     name="A")
        self.assertEqual(self.app()["pictures"], ["A", "b"])
        self.assertTrue((self.source / "pictures" / "A.png").is_file())

    def test_a_picture_of_another_kind_deletes_the_old_file(self):
        add_pictures(self.source, [self.picture("green", (0, 255, 0), ".bmp")], replacing=Slot("a"))
        self.assertTrue((self.source / "pictures" / "a.bmp").is_file())
        self.assertFalse((self.source / "pictures" / "a.png").exists())
        self.assertEqual(self.app()["pictures"], ["a", "b"])

    def test_a_ready_made_font(self):
        block = (self.source / "fonts" / "NotoSans16.zi").read_bytes()
        (self.folder / "small.zi").write_bytes(block)
        add_font_file(self.source, self.folder / "small.zi", replacing=Slot("NotoSans24"))
        self.assertEqual(self.app()["fonts"], ["NotoSans24", "NotoSans16"])
        self.assertEqual((self.source / "fonts" / "NotoSans24.zi").read_bytes(), block)

    def test_refusals_write_nothing(self):
        green = self.picture("green", (0, 255, 0))
        (self.source / "pictures" / "stray.png").write_bytes(green.read_bytes())
        before = self.files()
        for replace, message in (
                (lambda: add_pictures(self.source, [green], replacing=Slot("c")),
                 "no picture named c"),
                (lambda: add_pictures(self.source, [green], replacing=Slot("a"), name="b"),
                 "has a picture named b"),
                (lambda: add_pictures(self.source, [green], replacing=Slot("a"), name="stray"),
                 "already there"),
                (lambda: add_pictures(self.source, [green, green], replacing=Slot("a")),
                 "one picture"),
                (lambda: add_pictures(self.source, [green], name="green"),
                 "only with replacing"),
                (lambda: add_sound(self.source, SOURCES / "short22k.wav", "x",
                                   replacing=Slot("nothing")), "no sound named nothing")):
            with self.subTest(message=message), self.assertRaisesRegex(NxwrightError, message):
                replace()
            self.assertEqual(self.files(), before)

    def test_a_failed_write_puts_the_files_back(self):
        # The animation's second file fails to write: its first is put back.
        green = self.picture("green", (0, 255, 0))
        before = self.files()
        real = Path.write_bytes

        def failing(path, data):
            if path.name == "blink.screen.gmov":
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(Path, "write_bytes", failing):
            with self.assertRaises(OSError):
                add_animation(self.source, [green], 200, "blink", replacing=Slot("blink"))
        self.assertEqual(self.files(), before)

    def test_the_files_of_a_resource(self):
        self.assertEqual(resource_file_paths(self.source, "pictures", "a"), ["pictures/a.png"])
        self.assertEqual(resource_file_paths(self.source, "animations", "blink"),
                         ["animations/blink.gmov", "animations/blink.screen.gmov"])
        (self.source / "pictures" / "a.source.png").write_bytes(b"x")
        self.assertEqual(resource_file_paths(self.source, "pictures", "a"),
                         ["pictures/a.png", "pictures/a.source.png"])


if __name__ == "__main__":
    import unittest
    unittest.main()
