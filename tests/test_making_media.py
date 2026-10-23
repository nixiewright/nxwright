"""Making animations: the JPEG writer, an animation's two files, and
`nxwright animation`.

Beside test_media.py's and test_playback.py's fixtures, tests/fixtures/media/
holds a probe's files: odd.gmov, GmovMaker's file of three frames 33 by 17,
red, green, and blue, each with a white last column and a black last row, as
nxwright writes it; and odd.screen.gmov, the form the Editor made of it when
its Gmov panel added it, which shows how it pads a frame. Likewise alpha.gmov
and alpha.screen.gmov, of a frame 16 by 16, white wholly transparent at the
top and (200, 100, 50) half transparent at the bottom, which show what the
Editor makes of transparency.
"""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.media_files import animation_files, animation_frames, gmovmaker_frames
from nxwright.project.pictures import write_png
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import new_source_folder
from nxwright.source.resource_adding import add_animation
from tests.pictures import read_jpeg, rgba_image
from tests.test_media import FIXTURES, SETTINGS, folder_files

def segments(jpeg: bytes) -> dict:
    """Returns {marker: [body]} of a JPEG picture's segments up to its scan."""
    found, at = {}, 2
    while jpeg[at + 1] != 0xDA:
        length, = struct.unpack_from(">H", jpeg, at + 2)
        found.setdefault(jpeg[at + 1], []).append(jpeg[at + 4:at + 2 + length])
        at += 2 + length
    return found


def gmovmaker_contents(data: bytes, png_form: bool = True) -> tuple:
    """Returns GmovMaker's file in a form that two files compare alike in
    when they differ only in how their frames' PNG pictures are compressed.
    Different zlib builds compress the same rows to different bytes, each
    valid, and so does .NET. Those bytes, and every length they set, are left
    out: each frame's entry's place and size, which reading its frame checks,
    the PNG's length before each picture, and its IDAT chunks' data. The
    header's two lengths, of the file after the header with and without its
    closing chunk, are checked against the file's own. Each frame's
    pixels and duration stand for them, and its PNG's other chunks for its
    form, such as its colour type. With `png_form` false, those chunks are
    left out too, for pictures another program wrote, as GmovMaker's .NET
    writes chunks nxwright does not."""
    header, count = struct.unpack_from("<II", data, 8)
    head = bytearray(data[:header])
    after_header = len(data) - header
    lengths = (struct.unpack_from("<I", head, 24)[0] == after_header,
               struct.unpack_from("<I", head, 40)[0] == after_header - 4096)
    head[24:28] = head[40:44] = bytes(4)
    entries, around = [], []
    for number in range(count):
        entry = bytearray(data[header + 40 * number:header + 40 * (number + 1)])
        _, _, place, _, _, size = struct.unpack_from("<IIIHHI", entry)
        entry[8:12] = entry[16:20] = bytes(4)
        entries.append(bytes(entry))
        frame = data[header + place:header + place + size]
        # .NET's serialized byte array: its length, then its element type.
        start = frame.index(b"\x89PNG")
        around.append((frame[:start - 5], frame[start - 1:start], frame[-1:],
                       png_chunks(frame[start:-1]) if png_form else None))
    frames = [(image.width, image.height, image.get_flattened_data(), duration)
              for image, duration in gmovmaker_frames(data)]
    return bytes(head), lengths, entries, around, data[-4096:], frames


def png_chunks(png: bytes) -> list:
    """Returns the chunks of a PNG picture as (kind, data), an IDAT chunk's
    data left out, as compressed rows are."""
    chunks, place = [], 8
    while place < len(png):
        size, kind = struct.unpack_from(">I4s", png, place)
        chunks.append((kind, None if kind == b"IDAT" else png[place + 8:place + 8 + size]))
        place += 12 + size
    return chunks


def gradient(width: int, height: int):
    """An RGBA picture of smooth colours, which JPEG keeps well, as gentle
    at any size: steep colours lose more to colour at half the width and
    height."""
    return rgba_image(width, height, [(x * 4 % 256, y * 5 % 256, 128, 255)
                                     for y in range(height) for x in range(width)])


def mean_difference(first: bytes, second: bytes) -> float:
    return sum(abs(a - b) for a, b in zip(first, second)) / len(first)


class JpegTest(unittest.TestCase):

    def test_its_pictures_are_of_the_editors_kind(self):
        # Baseline, colour at half the width and height, the same tables.
        editor = animation_frames((FIXTURES / "colours.screen.gmov").read_bytes()).pictures[0]
        ours = animation_frames(animation_files([(gradient(80, 64), 50)])[1]).pictures[0]
        for marker in (0xDB, 0xC0, 0xC4):
            with self.subTest(marker=hex(marker)):
                self.assertEqual(segments(ours)[marker], segments(editor)[marker])

    def test_a_frame_reads_back_within_jpegs_loss(self):
        picture = gradient(64, 48)
        frame = animation_frames(animation_files([(picture, 50)])[1]).pictures[0]
        width, height, rgb = read_jpeg(frame)
        self.assertEqual((width, height), (64, 48))
        self.assertLess(mean_difference(rgb, picture.convert("RGB").tobytes()), 2)


class AnimationFilesTest(unittest.TestCase):
    """An animation's two files, against GmovMaker's and the Editor's."""

    def test_gmovmakers_file_is_as_the_editor_took_it(self):
        # The Editor added it, and kept it as it was (odd.gmov).
        odd = (FIXTURES / "odd.gmov").read_bytes()
        self.assertEqual(gmovmaker_contents(animation_files(gmovmaker_frames(odd))[0]),
                         gmovmaker_contents(odd))

    def test_gmovmakers_own_file_reads_back_the_same(self):
        # GmovMaker's .NET writes its PNGs otherwise than nxwright, so only
        # their pixels compare; the rest of the file is the same.
        blink = (FIXTURES / "blink.gmov").read_bytes()
        self.assertEqual(gmovmaker_contents(animation_files(gmovmaker_frames(blink))[0], False),
                         gmovmaker_contents(blink, False))

    def test_the_screens_form_is_as_the_editor_makes_it(self):
        editor = (FIXTURES / "odd.screen.gmov").read_bytes()
        ours = animation_files(gmovmaker_frames((FIXTURES / "odd.gmov").read_bytes()))[1]
        # Header and closing chunk, but for the sizes.
        self.assertEqual((ours[:24], ours[28:40], ours[44:76], ours[-4096:]),
                         (editor[:24], editor[28:40], editor[44:76], editor[-4096:]))
        theirs, mine = animation_frames(editor), animation_frames(ours)
        self.assertEqual((mine.width, mine.height, mine.starts, mine.length),
                         (theirs.width, theirs.height, theirs.starts, theirs.length))
        for number, (picture, editors) in enumerate(zip(mine.pictures, theirs.pictures)):
            with self.subTest(frame=number):
                # Padded with black to 48 by 32, as the Editor's.
                width, height, rgb = read_jpeg(picture)
                self.assertEqual((width, height), read_jpeg(editors)[:2])
                self.assertLess(mean_difference(rgb, read_jpeg(editors)[2]), 3)

    def test_each_screen_frame_starts_with_its_jpegs_size(self):
        ours = animation_files(gmovmaker_frames((FIXTURES / "odd.gmov").read_bytes()))[1]
        editor = (FIXTURES / "odd.screen.gmov").read_bytes()
        for data in (ours, editor):
            self.assertEqual(data[196:216], struct.pack("<III8x", 0, 48, 32))

    def test_transparency_goes_as_the_editor_drops_it(self):
        # alpha.gmov's frame: white wholly transparent at the top, and
        # (200, 100, 50) half transparent at the bottom. The Editor's form of
        # it (alpha.screen.gmov) showed the top black and the bottom its own
        # colour, not darkened.
        frames = gmovmaker_frames((FIXTURES / "alpha.gmov").read_bytes())
        ours = animation_frames(animation_files(frames)[1]).pictures[0]
        editors = animation_frames((FIXTURES / "alpha.screen.gmov").read_bytes()).pictures[0]
        _, _, rgb = read_jpeg(ours)
        # The decoder smooths colour across rows, so the black row next to
        # the coloured half takes some of it, in the Editor's frame too.
        self.assertLess(max(rgb[:3 * 7 * 16]), 8)
        self.assertLess(mean_difference(rgb[3 * 8 * 16:], bytes((200, 100, 50) * 128)), 4)
        self.assertLess(mean_difference(rgb, read_jpeg(editors)[2]), 3)

    def test_frames_it_cannot_write_are_refused(self):
        small, large = gradient(16, 16), gradient(32, 16)
        for frames, message in (([], "needs a frame"),
                                ([(small, 50), (large, 50)], "must all be 16 by 16"),
                                ([(small, 0)], "lasts 1 ms at least"),
                                ([(gradient(0, 16), 50)],
                                 "at least 1 and at most 65,535 pixels wide and high"),
                                ([(small, 2 ** 31), (small, 2 ** 31)],
                                 "lasts 4,294,967,295 ms at most")):
            with self.subTest(message=message):
                with self.assertRaisesRegex(NxwrightError, message):
                    animation_files(frames)


class GmovMakerFileTest(unittest.TestCase):
    """A file GmovMaker wrote, read for its frames: blink.gmov, its own, whose
    PNG pictures .NET wrote, which the Editor's Gmov panel took."""

    def setUp(self):
        self.blink = (FIXTURES / "blink.gmov").read_bytes()

    def test_its_frames_and_durations(self):
        self.assertEqual([(image.size, duration)
                          for image, duration in gmovmaker_frames(self.blink)],
                         [((80, 60), 50)] * 3)

    def test_what_it_refuses(self):
        header = struct.unpack_from("<I", self.blink, 8)[0]
        start = header + struct.unpack_from("<I", self.blink, header + 8)[0]
        no_picture = self.blink[:start] + bytes(200) + self.blink[start + 200:]
        cases = [((FIXTURES / "blink.screen.gmov").read_bytes(), "the form the screen shows"),
                 (b"VIDE" + self.blink[4:], "not a file of GmovMaker's"),
                 (self.blink[:4] + b"\x0b" + self.blink[5:], "rotation marker"),
                 (no_picture, "frame 0 holds no PNG picture"),
                 (self.blink[:start + 10], "frame 0 lies outside the file")]
        for data, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(NxwrightError, message):
                    gmovmaker_frames(data)

    def test_a_frames_picture_ends_where_its_png_does(self):
        # Without .NET's end byte, the frame reads alike; with its PNG cut
        # short, it holds no whole PNG picture.
        header = struct.unpack_from("<I", self.blink, 8)[0]
        size = struct.unpack_from("<I", self.blink, header + 16)[0]
        frames = []
        for shorter_by in (1, 20):
            data = bytearray(self.blink)
            struct.pack_into("<I", data, header + 16, size - shorter_by)
            frames.append(bytes(data))
        self.assertEqual([image.tobytes() for image, _ in gmovmaker_frames(frames[0])],
                         [image.tobytes() for image, _ in gmovmaker_frames(self.blink)])
        with self.assertRaisesRegex(NxwrightError, "frame 0 holds no PNG picture"):
            gmovmaker_frames(frames[1])

    def test_the_screens_form_made_of_it_is_the_editors(self):
        editor = (FIXTURES / "blink.screen.gmov").read_bytes()
        ours = animation_files(gmovmaker_frames(self.blink))[1]
        self.assertEqual((ours[:24], ours[28:40], ours[44:76], ours[-4096:]),
                         (editor[:24], editor[28:40], editor[44:76], editor[-4096:]))
        theirs, mine = animation_frames(editor), animation_frames(ours)
        self.assertEqual((mine.width, mine.height, mine.starts, mine.length),
                         (theirs.width, theirs.height, theirs.starts, theirs.length))
        for number, (picture, editors) in enumerate(zip(mine.pictures, theirs.pictures)):
            with self.subTest(frame=number):
                width, height, rgb = read_jpeg(picture)
                self.assertEqual((width, height), read_jpeg(editors)[:2])
                self.assertLess(mean_difference(rgb, read_jpeg(editors)[2]), 3)


class AnimationCommandTest(unittest.TestCase):
    """`nxwright animation`, adding an animation to a source folder."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        new_source_folder(self.source, SETTINGS, "nextion")
        self.pictures = []
        for number, colour in enumerate(((255, 0, 0), (0, 0, 255))):
            path = self.folder / ("frame%d.png" % number)
            path.write_bytes(write_png(8, 8, bytes(colour + (255,)) * 64))
            self.pictures.append(path)

    def tearDown(self):
        self._folder.cleanup()

    def test_its_files_are_written_and_listed(self):
        self.assertEqual(add_animation(self.source, self.pictures, 100), "frame0")
        app = (self.source / "app.toml").read_text(encoding="utf-8")
        self.assertEqual(tomllib.loads(app)["animations"], ["frame0"])
        frames = animation_frames(
            (self.source / "animations" / "frame0.screen.gmov").read_bytes())
        self.assertEqual((frames.starts, frames.length), ((0, 100), 200))
        self.assertEqual([image.getpixel((0, 0)) for image, _ in gmovmaker_frames(
            (self.source / "animations" / "frame0.gmov").read_bytes())],
            [(255, 0, 0, 255), (0, 0, 255, 255)])

    def test_a_name_the_folder_has_is_refused_before_writing(self):
        add_animation(self.source, self.pictures, 100, "blink")
        before = (self.source / "app.toml").read_text(encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "has an animation named blink"):
            add_animation(self.source, self.pictures, 100, "Blink")
        self.assertEqual((self.source / "app.toml").read_text(encoding="utf-8"), before)

    def test_another_kind_of_picture_is_read_too(self):
        # A GIF of two frames: its first, red, is taken.
        gif = self.folder / "spin.gif"
        red, blue = (rgba_image(8, 8, [colour + (255,)] * 64)
                     for colour in ((255, 0, 0), (0, 0, 255)))
        red.save(gif, save_all=True, append_images=[blue])
        add_animation(self.source, [gif], 100)
        self.assertEqual([image.getpixel((0, 0)) for image, _ in gmovmaker_frames(
            (self.source / "animations" / "spin.gmov").read_bytes())], [(255, 0, 0, 255)])

    def test_a_picture_that_does_not_read_is_refused_before_writing(self):
        damaged = self.folder / "damaged.gif"
        damaged.write_bytes(b"GIF89a")
        with self.assertRaisesRegex(NxwrightError, "damaged.gif: not a picture nxwright reads"):
            add_animation(self.source, [damaged], 100)
        self.assertFalse((self.source / "animations").exists())

    def test_the_command_takes_its_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["animation", str(self.source), *map(str, self.pictures),
                                   "--duration", "70", "--name", "pulse"]), 0)
        self.assertIn("Added the animation pulse", output.getvalue())
        frames = animation_frames(
            (self.source / "animations" / "pulse.screen.gmov").read_bytes())
        self.assertEqual(frames.starts, (0, 70))

    def test_a_gmovmaker_file_is_kept_and_its_screens_form_made(self):
        blink = FIXTURES / "blink.gmov"
        self.assertEqual(add_animation(self.source, [blink]), "blink")
        self.assertEqual((self.source / "animations" / "blink.gmov").read_bytes(),
                         blink.read_bytes())
        frames = animation_frames(
            (self.source / "animations" / "blink.screen.gmov").read_bytes())
        self.assertEqual((frames.width, frames.height, frames.starts), (80, 60, (0, 50, 100)))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["animation", str(self.source), str(blink), "--name", "wink"]),
                             0)
        self.assertEqual((self.source / "animations" / "wink.gmov").read_bytes(),
                         blink.read_bytes())

    def test_a_gmovmaker_file_for_a_turned_folder(self):
        turned = self.folder / "turned"
        new_source_folder(turned, DeviceSettings(SETTINGS.model, 90, SETTINGS.encoding),
                          "nextion")
        blink = (FIXTURES / "blink.gmov").read_bytes()
        add_animation(turned, [FIXTURES / "blink.gmov"])
        self.assertEqual((turned / "animations" / "blink.screen.gmov").read_bytes(),
                         animation_files(gmovmaker_frames(blink), 90)[1])

    def test_what_is_refused_with_a_gmovmaker_file(self):
        blink = str(FIXTURES / "blink.gmov")
        cases = [([blink, "--duration", "70"], "its frames have their own durations"),
                 ([blink, str(self.pictures[0])], "a GmovMaker file is given alone"),
                 ([blink, blink], "a GmovMaker file is given alone"),
                 ([str(FIXTURES / "blink.screen.gmov")],
                  "blink.screen.gmov: the form the screen shows")]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    self.assertEqual(main(["animation", str(self.source), *arguments]), 1)
                self.assertIn(message, errors.getvalue())
        self.assertFalse((self.source / "animations").exists())

    def test_a_folder_with_a_made_animation_builds_and_extracts_back(self):
        add_animation(self.source, self.pictures, 100)
        before = folder_files(self.source)
        build(self.source, self.folder / "made.HMI")
        extract(self.folder / "made.HMI", self.source)
        self.assertEqual(folder_files(self.source), before)


if __name__ == "__main__":
    unittest.main()
