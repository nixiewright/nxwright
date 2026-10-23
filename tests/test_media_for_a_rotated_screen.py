"""Animations and videos for a screen turned 90, 180, or 270 degrees.

tests/fixtures/media/turned/ holds a probe's files. quarters.png is
72 by 40: red at its top left, green at its top right, blue at its bottom
left, and white at its bottom right. quarters2.png is cyan, magenta,
yellow, and black alike. quarters.gmov is GmovMaker's file of the two, each
lasting 500 ms, as nxwright writes it. quarters-<rotation>.screen.gmov is
the form the Editor's Gmov panel made of it in a project turned that many
degrees; the Editor kept quarters.gmov as it was. quarters-<rotation>.video
is VideoBox's video of quarters.png, made at that display direction: 3
frames at 12 a second, cut from a video of the picture.
"""
import contextlib
import io
from pathlib import Path
import shutil
import struct
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.media_files import (VIDEO_HEAD_SIZE, animation_files, animation_frames,
                                          video_file, video_frame, video_frames)
from nxwright.project.pictures import read_picture
from nxwright.source.folder_check import check_folder
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_byte_reader, folder_reader
from tests.pictures import read_jpeg
from tests.test_making_media import gmovmaker_contents, mean_difference
from tests.test_making_videos_and_sounds import MediaCommandTestCase
from tests.test_playback import PlayingFolderTestCase

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "media" / "turned"
TURNED = (90, 180, 270)
_HEADER, _ENTRY = 76, 40


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def quarters() -> list:
    """The frames of quarters.gmov, each lasting 500 ms."""
    return [(read_picture(fixture(name)), 500) for name in ("quarters.png", "quarters2.png")]


def fixed_fields(data: bytes) -> tuple:
    """An animation's or a video's header, entries, and closing chunk, but
    for the sizes and places, which follow the JPEG pictures' sizes."""
    count, = struct.unpack_from("<I", data, 12)
    entries = [data[at:at + 8] + data[at + 12:at + 16] + data[at + 20:at + _ENTRY]
               for at in range(_HEADER, _HEADER + _ENTRY * count, _ENTRY)]
    return data[:24], data[28:40], data[44:_HEADER], entries, data[-4096:]


def frame_headers(data: bytes) -> list:
    """The 20-byte header before each frame of an animation's screen form."""
    count, = struct.unpack_from("<I", data, 12)
    places = [struct.unpack_from("<I", data, _HEADER + _ENTRY * number + 8)[0]
              for number in range(count)]
    return [data[_HEADER + place:_HEADER + place + 20] for place in places]


class TurnedFilesTest(unittest.TestCase):
    """The files of an animation and a video for a turned screen."""

    def assert_pictures_alike(self, ours: tuple, theirs: tuple):
        # Within JPEG's loss: nxwright's coder is not the Editor's or VideoBox's.
        for mine, expected in zip(ours, theirs, strict=True):
            width, height, pixels = read_jpeg(mine)
            self.assertEqual((width, height), read_jpeg(expected)[:2])
            self.assertLess(mean_difference(pixels, read_jpeg(expected)[2]), 3)

    def test_gmovmakers_file_is_not_turned(self):
        # GmovMaker has no direction; the Editor kept its file as it was.
        for rotation in (0,) + TURNED:
            with self.subTest(rotation=rotation):
                self.assertEqual(gmovmaker_contents(animation_files(quarters(), rotation)[0]),
                                 gmovmaker_contents(fixture("quarters.gmov")))

    def test_the_editors_turned_forms_are_made_again(self):
        for rotation in TURNED:
            with self.subTest(rotation=rotation):
                editor = fixture("quarters-%d.screen.gmov" % rotation)
                ours = animation_files(quarters(), rotation)[1]
                self.assertEqual(fixed_fields(ours), fixed_fields(editor))
                # Each frame's header gives its turned JPEG picture's size.
                self.assertEqual(frame_headers(ours), frame_headers(editor))
                self.assert_pictures_alike(animation_frames(ours).pictures,
                                           animation_frames(editor).pictures)

    def test_videoboxs_videos_are_made_again_at_each_direction(self):
        image = quarters()[0][0]
        for rotation in (0,) + TURNED:
            with self.subTest(rotation=rotation):
                theirs = fixture("quarters-%d.video" % rotation)
                ours = video_file(72, 40, 12, [video_frame(image, rotation)] * 3, rotation)
                self.assertEqual(fixed_fields(ours), fixed_fields(theirs))
                self.assert_pictures_alike(video_frames(ours).pictures,
                                           video_frames(theirs).pictures)

    def test_a_turned_frame_is_padded_then_turned(self):
        # At 90 degrees, the black padding under an animation's frame comes
        # to its left, and the padding at its right to its bottom.
        picture = animation_frames(animation_files(quarters(), 90)[1]).pictures[0]
        width, height, pixels = read_jpeg(picture)
        self.assertEqual((width, height), (48, 80))

        def pixel(x, y):
            return pixels[(y * width + x) * 3:(y * width + x) * 3 + 3]
        self.assertLess(max(pixel(2, 30)), 20)          # padding
        self.assertLess(max(pixel(24, 77)), 20)         # padding
        self.assertGreater(pixel(44, 10)[0], 200)       # red, at the top right
        self.assertGreater(pixel(12, 10)[2], 200)       # blue, at its left

    def test_a_rotation_there_is_not_is_refused(self):
        image = quarters()[0][0]
        for make in (lambda: animation_files(quarters(), 45),
                     lambda: video_frame(image, 45),
                     lambda: video_file(72, 40, 12, [video_frame(image)], 45)):
            with self.assertRaisesRegex(NxwrightError, "a rotation is one of 0, 90, 180, 270"):
                make()


class TurnedFilesReadTest(unittest.TestCase):
    """Reading the files of an animation and a video for a turned screen."""

    def test_the_rotation_a_file_was_made_for_is_read(self):
        for rotation in TURNED:
            with self.subTest(rotation=rotation):
                form = animation_frames(fixture("quarters-%d.screen.gmov" % rotation))
                video = video_frames(fixture("quarters-%d.video" % rotation))
                self.assertEqual((form.rotation, video.rotation), (rotation, rotation))
                # The sizes stay the frames' own, unturned.
                self.assertEqual((form.width, form.height, video.width, video.height),
                                 (72, 40, 72, 40))
        self.assertEqual(video_frames(fixture("quarters-0.video")).rotation, 0)

    def test_a_marker_there_is_not_is_refused(self):
        for read, name in ((animation_frames, "quarters-90.screen.gmov"),
                           (video_frames, "quarters-90.video")):
            data = bytearray(fixture(name))
            data[4] = 0x0E
            with self.subTest(name=name), self.assertRaisesRegex(
                    NxwrightError, "rotation marker 0xe is not one known"):
                read(bytes(data))


class TurnedFramesDrawnTest(PlayingFolderTestCase):
    """A turned file's frame, as the preview and the simulator draw it."""

    def test_a_frame_carries_its_files_own_rotation(self):
        # The webview turns the picture back by it; an upright one has none.
        self.assertEqual([shape.get("rotation") for shape in self.drawn().values()],
                         [None, None])
        shutil.copyfile(FIXTURES / "quarters-90.screen.gmov",
                        self.source / "animations" / "colours.screen.gmov")
        shutil.copyfile(FIXTURES / "quarters-270.video", self.source / "videos" / "colours.video")
        shapes = self.drawn()
        self.assertEqual((shapes["gm0"]["rotation"], shapes["video0"]["rotation"]), (90, 270))
        # Its rectangle is the frame's own size, unturned, at the component's corner.
        self.assertEqual([(shape["x"], shape["y"], shape["w"], shape["h"])
                          for shape in shapes.values()], [(20, 20, 72, 40), (200, 20, 72, 40)])


class MediaForAnotherRotationTest(MediaCommandTestCase):
    """A video or an animation made for another rotation than the folder's,
    turned 90 degrees. The Editor refuses to compile such a video, and makes
    such an animation's form again as it compiles."""

    def setUp(self):
        super().setUp()
        self.rotate()

    def put(self, kind: str, files: dict):
        """Puts `files` {name: bytes} in the folder's `kind` folder, and
        lists the one name they share in app.toml."""
        (self.source / kind).mkdir()
        for file, data in files.items():
            (self.source / kind / file).write_bytes(data)
        name = next(iter(files)).split(".")[0]
        with open(self.source / "app.toml", "a", encoding="utf-8") as app:
            app.write('%s = ["%s"]\n' % (kind, name))

    def put_video(self, made_for: int):
        self.put("videos", {"quarters.video": fixture("quarters-%d.video" % made_for)})

    def check(self, read_bytes=None) -> list:
        return check_folder(folder_reader(self.source), lambda path: (self.source / path).is_file(),
                            read_bytes=read_bytes or folder_byte_reader(self.source)).findings()

    def test_the_build_refuses_such_a_video(self):
        self.put_video(0)
        with self.assertRaisesRegex(NxwrightError, "videos/quarters.video was made for a screen "
                                                   "turned 0 degrees, where the folder's is turned "
                                                   "90; the Nextion Editor refuses to compile it"):
            build(self.source, self.folder / "made.HMI")
        self.assertFalse((self.folder / "made.HMI").exists())

    def test_a_video_made_for_the_folders_rotation_is_taken(self):
        self.put_video(90)
        build(self.source, self.folder / "made.HMI")
        self.assertEqual(self.check(), [])

    def test_the_checks_show_it_as_an_error_on_its_line(self):
        self.put_video(0)
        findings = self.check()
        self.assertEqual([(found.file, found.severity, found.rule) for found in findings],
                         [("app.toml", "error", "video-rotation")])
        self.assertIn('"quarters"', self.app().split("\n")[findings[0].line - 1])
        self.assertIn("make it again for the folder's rotation, with `nxwright video` or "
                      "VideoBox's display direction", findings[0].message)

    def test_the_checks_read_a_videos_first_bytes_only(self):
        # Videos can be large, and the live checks run often.
        self.put_video(0)
        asked, read = {}, folder_byte_reader(self.source)

        def recording(path: str, size: int = None) -> bytes:
            asked[path] = size
            return read(path, size)
        self.check(recording)
        self.assertEqual(asked["videos/quarters.video"], VIDEO_HEAD_SIZE)

    def test_nxwright_check_shows_it(self):
        self.put_video(0)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["check", str(self.source)]), 1)
        self.assertIn("error: videos/quarters.video was made for a screen turned 0 degrees",
                      output.getvalue())

    def test_an_animation_made_for_another_rotation_is_taken(self):
        gmovmaker, screen = animation_files(quarters(), 0)
        self.put("animations", {"quarters.gmov": gmovmaker, "quarters.screen.gmov": screen})
        build(self.source, self.folder / "made.HMI")
        self.assertEqual(self.check(), [])

    def test_a_file_that_is_not_a_video_is_left_to_the_other_checks(self):
        self.put("videos", {"quarters.video": b"not a video"})
        build(self.source, self.folder / "made.HMI")
        self.assertEqual(self.check(), [])


if __name__ == "__main__":
    unittest.main()
