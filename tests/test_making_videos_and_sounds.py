"""Making videos and sounds: a video's file and frames, a sound in the form
the Editor's Audio panel writes, `nxwright video` and `nxwright sound`, and
the checks' warning of a sound not in that form.

Beside test_media.py's fixtures, tests/fixtures/media/sources/ holds WAV files
nxwright's own scripts made for a probe, which the Editor's Audio panel added
to a project: short22k.wav (16-bit mono, 22,050 samples a second),
short11k-stereo8.wav (8-bit stereo, 11,025), odd8.wav (8-bit mono, 1,101
samples, not a whole number of 4 bytes), and list.wav (16-bit mono, with a LIST
chunk before its samples). The Editor's files of them are beep.wav, chirp.wav,
odd8.wav, and list.wav, in tests/fixtures/media/.
"""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
import tomllib
import unittest
from unittest import mock

from PIL import Image

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project import ffmpeg
from nxwright.project.media_files import (animation_frames, screen_crc, sound_file,
                                          sound_file_problem, sound_length, turned_video,
                                          video_file, video_frame, video_frames, video_rotation)
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.stamp import CRC_START, word_crc
from nxwright.source.folder_check import check_folder
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import folder_byte_reader, folder_reader, new_source_folder
from nxwright.source.resource_adding import add_animation, add_sound, add_video
from tests.pictures import read_jpeg, rgba_image
from tests.test_making_media import gradient, mean_difference
from tests.test_media import FIXTURES, SETTINGS, folder_files

SOURCES = FIXTURES / "sources"
# Each source WAV, by its name, and the Editor's file of it.
EDITORS_FILES = {"short22k": "beep.wav", "short11k-stereo8": "chirp.wav", "odd8": "odd8.wav",
                 "list": "list.wav"}


def wav(channels: int, width: int, rate: int, samples: bytes, form: int = 1,
        extension: bytes = b"") -> bytes:
    """A WAV file of `samples`, its format chunk of 16 bytes, then `extension`."""
    body = (b"WAVE" + b"fmt " + struct.pack("<IHHIIHH", 16 + len(extension), form, channels,
                                            rate, rate * channels * width, channels * width,
                                            width * 8)
            + extension + b"data" + struct.pack("<I", len(samples)) + samples)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def video_pictures(video: bytes) -> list:
    """Returns each frame's JPEG picture of a video file."""
    count, = struct.unpack_from("<I", video, 12)
    pictures = []
    for number in range(count):
        place, = struct.unpack_from("<I", video, 76 + 40 * number + 8)
        size, = struct.unpack_from("<I", video, 76 + 40 * number + 16)
        pictures.append(video[76 + place:76 + place + size])
    return pictures


class SoundFileTest(unittest.TestCase):

    def test_the_editors_files_are_made_byte_for_byte(self):
        # Samples kept, other chunks dropped, the samples padded to whole
        # words, and the check value and name in hmic.
        for name, editors in EDITORS_FILES.items():
            with self.subTest(name):
                self.assertEqual(sound_file((SOURCES / (name + ".wav")).read_bytes(), name),
                                 (FIXTURES / editors).read_bytes())

    def test_the_check_value_leaves_out_the_samples_last_8_bytes(self):
        # It runs from the data chunk's header for as many bytes as the
        # samples hold: odd8's last samples, padded, are not in it.
        made = sound_file((SOURCES / "odd8.wav").read_bytes(), "odd8")
        at = made.index(b"data")
        self.assertEqual(screen_crc(made[at:len(made) - 8]), struct.unpack_from("<I", made, 52)[0])
        changed = made[:-1] + b"\x7f"
        self.assertIsNone(sound_file_problem(changed))

    def test_the_check_value_is_the_stamps_crc_of_words(self):
        data = bytes((value * 37 + 11) % 256 for value in range(1000))
        words = struct.unpack("<250I", data)
        self.assertEqual(screen_crc(data), word_crc(CRC_START, words))
        self.assertEqual(screen_crc(data[:999]), word_crc(CRC_START, words[:-1] + (
            words[-1] & 0x00FFFFFF,)))

    def test_a_file_not_in_the_editors_form(self):
        for name in EDITORS_FILES.values():
            self.assertIsNone(sound_file_problem((FIXTURES / name).read_bytes()))
        self.assertEqual(sound_file_problem((SOURCES / "short22k.wav").read_bytes()),
                         "it has no hmic chunk")
        zeroed = bytearray((FIXTURES / "beep.wav").read_bytes())
        zeroed[52:56] = bytes(4)
        self.assertEqual(sound_file_problem(bytes(zeroed)),
                         "its hmic chunk's check value does not match its samples")
        # A file that is not a WAV file at all is the simulator's to refuse.
        self.assertIsNone(sound_file_problem(b"ID3 an mp3"))

    def test_the_simulator_reads_its_length(self):
        made = sound_file(wav(1, 2, 8000, bytes(800)), "tick")
        self.assertEqual(sound_length(made), 50)

    def test_the_simulator_times_every_sound_the_audio_panel_keeps(self):
        # 400 frames at 8,000 a second, whatever their samples. The
        # extensible format names its samples in its own subformat, which
        # the Audio panel cuts off with the format chunk past 16 bytes.
        float_subformat = struct.pack("<HHI", 22, 32, 0) + struct.pack("<H", 3) + bytes(14)
        for name, sound in (
                ("24-bit", wav(1, 3, 8000, bytes(3 * 400))),
                ("float", wav(1, 4, 8000, bytes(4 * 400), form=3)),
                ("extensible, float", wav(2, 4, 8000, bytes(8 * 400), form=0xFFFE,
                                          extension=float_subformat)),
                ("extensible, cut", wav(2, 3, 8000, bytes(6 * 400), form=0xFFFE))):
            with self.subTest(name):
                self.assertEqual(sound_length(sound), 50)

    def test_the_simulator_refuses_a_sound_it_cannot_time(self):
        adpcm_subformat = struct.pack("<HHI", 22, 4, 0) + struct.pack("<H", 2) + bytes(14)
        for sound, reason in (
                (wav(1, 1, 8000, bytes(400), form=2), "neither PCM nor float"),
                (wav(1, 1, 8000, bytes(400), form=0xFFFE, extension=adpcm_subformat),
                 "neither PCM nor float"),
                (wav(1, 2, 0, bytes(800)), "its rate is 0"),
                (wav(0, 2, 8000, bytes(800)), "its frames are 0 bytes"),
                (b"RIFF....WAVE", "lacks a format or a data chunk")):
            with self.subTest(reason):
                with self.assertRaisesRegex(NxwrightError, reason):
                    sound_length(sound)

    def test_what_it_cannot_take_is_refused(self):
        for data, reason in ((b"RIFF....WAVE", "lacks a format or a data chunk"),
                             (b"ID3 an mp3", "not a WAV file"),
                             (wav(1, 3, 8000, bytes(30)), "8 or 16 bits"),
                             (wav(1, 4, 8000, bytes(40), form=3), "PCM samples"),
                             (wav(3, 2, 8000, bytes(60)), "mono or stereo"),
                             (wav(1, 2, 8000, bytes(40))[:-10], "data chunk is cut short")):
            with self.subTest(reason):
                with self.assertRaisesRegex(NxwrightError, reason):
                    sound_file(data, "x")
        with self.assertRaisesRegex(NxwrightError, "a sound's name is at most 484 bytes"):
            sound_file(wav(1, 2, 8000, bytes(40)), "x" * 485)
        self.assertTrue(sound_file(wav(1, 2, 8000, bytes(40)), "x" * 484))


class VideoFileTest(unittest.TestCase):

    def test_videoboxs_files_are_made_byte_for_byte_from_their_frames(self):
        for name in ("clip.video", "colours.video"):
            with self.subTest(name):
                video = (FIXTURES / name).read_bytes()
                width, height = struct.unpack_from("<HH", video, 16)
                self.assertEqual(video_file(width, height, video[6], video_pictures(video)), video)

    def test_a_frame_is_padded_with_white_to_whole_blocks(self):
        picture = video_frame(gradient(33, 17))
        width, height, rgb = read_jpeg(picture)
        self.assertEqual((width, height), (48, 32))
        # The blocks the padding does not reach keep the picture within
        # JPEG's loss. The last column and row share their colour with the
        # white beside them, as VideoBox's do.
        def blocks(pixels: bytes, width: int) -> bytes:
            return b"".join(pixels[row * width * 3:(row * width + 32) * 3] for row in range(16))
        original = gradient(33, 17).convert("RGB").tobytes()
        self.assertLess(mean_difference(blocks(rgb, 48), blocks(original, 33)), 3)
        padding = rgb[(20 * 48 + 40) * 3:(20 * 48 + 40) * 3 + 3]
        self.assertTrue(all(value > 245 for value in padding), padding)

    def test_its_frames_read_back_at_its_rate(self):
        pictures = [video_frame(rgba_image(16, 16, [colour] * 256))
                    for colour in ((255, 0, 0, 255), (0, 0, 255, 255), (0, 255, 0, 255))]
        frames = video_frames(video_file(16, 16, 10, pictures))
        self.assertEqual((frames.width, frames.height, frames.starts, frames.length),
                         (16, 16, (0, 100, 200), 300))
        self.assertEqual(frames.pictures, tuple(pictures))

    def test_a_video_turned_to_another_rotation(self):
        # Each frame is coded again for the new rotation, upright as before:
        # turned back, it keeps its picture within two codings' loss. The
        # header keeps the video's own size and rate.
        frames = [gradient(40, 24), rgba_image(40, 24, [(0, 0, 255, 255)] * (40 * 24))]
        video = video_file(40, 24, 10, [video_frame(frame) for frame in frames])
        upright_turns = {90: Image.Transpose.ROTATE_90, 180: Image.Transpose.ROTATE_180,
                         270: Image.Transpose.ROTATE_270}
        for rotation, turn in upright_turns.items():
            with self.subTest(rotation=rotation):
                turned = turned_video(video, rotation)
                self.assertEqual((video_rotation(turned), turned[6]), (rotation, 10))
                read = video_frames(turned)
                self.assertEqual((read.width, read.height, len(read.pictures)), (40, 24, 2))
                for frame, picture in zip(frames, read.pictures):
                    with Image.open(io.BytesIO(picture)) as stored:
                        upright = stored.convert("RGB").transpose(turn).crop((0, 0, 40, 24))
                    self.assertLess(mean_difference(upright.tobytes(),
                                                    frame.convert("RGB").tobytes()), 4)
                self.assertEqual(turned_video(turned, rotation), turned)

    def test_what_it_cannot_write_is_refused(self):
        picture = video_frame(rgba_image(16, 16, [(0, 0, 0, 255)] * 256))
        for arguments, reason in (((16, 16, 12, []), "needs a frame"),
                                  ((16, 16, 0, [picture]), "from 1 to 255 frames a second"),
                                  ((16, 16, 256, [picture]), "from 1 to 255 frames a second"),
                                  ((65536, 16, 12, [picture]), "at most 65,535 pixels")):
            with self.subTest(reason):
                with self.assertRaisesRegex(NxwrightError, reason):
                    video_file(*arguments)


class MediaCommandTestCase(unittest.TestCase):
    """A new source folder, with three PNG pictures of 16 by 16: red, blue, and green."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        new_source_folder(self.source, SETTINGS, "nextion")
        self.pictures = []
        for number, colour in enumerate(((255, 0, 0), (0, 0, 255), (0, 255, 0))):
            path = self.folder / ("frame%d.png" % number)
            path.write_bytes(write_png(16, 16, bytes(colour + (255,)) * 256))
            self.pictures.append(path)

    def tearDown(self):
        self._folder.cleanup()

    def app(self) -> str:
        return (self.source / "app.toml").read_text(encoding="utf-8")

    def rotate(self):
        text = self.app()
        self.assertIn("rotation = 0\n", text)
        (self.source / "app.toml").write_text(text.replace("rotation = 0\n", "rotation = 90\n"),
                                              encoding="utf-8")


class SoundCommandTest(MediaCommandTestCase):
    """`nxwright sound`."""

    def test_a_wav_file_is_added_in_the_editors_form(self):
        self.assertEqual(add_sound(self.source, SOURCES / "short22k.wav"), "short22k")
        self.assertEqual(tomllib.loads(self.app())["sounds"], ["short22k"])
        self.assertEqual((self.source / "sounds" / "short22k.wav").read_bytes(),
                         (FIXTURES / "beep.wav").read_bytes())

    def test_the_editor_names_it_after_its_file(self):
        # A name in a subfolder is the file's name, which hmic keeps.
        add_sound(self.source, SOURCES / "odd8.wav", "alarms/odd8")
        self.assertEqual((self.source / "sounds" / "alarms" / "odd8.wav").read_bytes(),
                         (FIXTURES / "odd8.wav").read_bytes())

    def test_a_name_the_folder_has_is_refused_before_writing(self):
        add_sound(self.source, SOURCES / "odd8.wav", "beep")
        before = self.app()
        with self.assertRaisesRegex(NxwrightError, "has a sound named beep"):
            add_sound(self.source, SOURCES / "list.wav", "Beep")
        self.assertEqual(self.app(), before)

    def test_converting_goes_through_ffmpeg(self):
        converted = wav(1, 2, 8000, bytes(range(200)))

        def ffmpeg_writes(command, **_):
            Path(command[-1]).write_bytes(converted)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch("nxwright.project.ffmpeg.shutil.which", return_value="ffmpeg"), \
                mock.patch("nxwright.project.ffmpeg.subprocess.run",
                           side_effect=ffmpeg_writes) as run:
            add_sound(self.source, SOURCES / "short11k-stereo8.wav", "low", rate=8000, mono=True)
        command = run.call_args.args[0]
        self.assertEqual((command[command.index("-ar") + 1], command[command.index("-ac") + 1],
                          command[command.index("-acodec") + 1]), ("8000", "1", "pcm_s16le"))
        self.assertEqual((self.source / "sounds" / "low.wav").read_bytes(),
                         sound_file(converted, "low"))

    def test_another_kind_of_file_goes_through_ffmpeg(self):
        mp3 = self.folder / "tune.mp3"
        mp3.write_bytes(b"ID3 an mp3")
        with mock.patch("nxwright.project.ffmpeg.shutil.which", return_value=None):
            with self.assertRaisesRegex(NxwrightError, "tune.mp3: not a WAV file: nxwright "
                                                       "converts others through ffmpeg, which "
                                                       "is not on the PATH"):
                add_sound(self.source, mp3)
            with self.assertRaisesRegex(NxwrightError, "converting short22k.wav needs ffmpeg"):
                add_sound(self.source, SOURCES / "short22k.wav", mono=True)
        self.assertFalse((self.source / "sounds").exists())

    def test_a_rate_the_editor_was_not_seen_to_take_is_refused(self):
        for rate in (7999, 48001):
            with self.assertRaisesRegex(NxwrightError, "from 8,000 to 48,000"):
                add_sound(self.source, SOURCES / "short22k.wav", rate=rate)

    def test_the_command_takes_its_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["sound", str(self.source), str(SOURCES / "list.wav"),
                                   "--name", "chime"]), 0)
        self.assertIn("Added the sound chime", output.getvalue())
        self.assertEqual(tomllib.loads(self.app())["sounds"], ["chime"])

    def test_a_folder_with_a_made_sound_builds_and_extracts_back(self):
        add_sound(self.source, SOURCES / "odd8.wav")
        before = folder_files(self.source)
        build(self.source, self.folder / "made.HMI")
        extract(self.folder / "made.HMI", self.source)
        self.assertEqual(folder_files(self.source), before)


class VideoCommandTest(MediaCommandTestCase):
    """`nxwright video`."""

    def test_pictures_make_a_video(self):
        self.assertEqual(add_video(self.source, self.pictures), "frame0")
        self.assertEqual(tomllib.loads(self.app())["videos"], ["frame0"])
        frames = video_frames((self.source / "videos" / "frame0.video").read_bytes())
        self.assertEqual((frames.width, frames.height, frames.length), (16, 16, 250))
        _, _, rgb = read_jpeg(frames.pictures[1])
        self.assertLess(mean_difference(rgb[:3], bytes((0, 0, 255))), 8)

    def test_pictures_of_two_sizes_are_refused(self):
        self.pictures[2].write_bytes(write_png(8, 16, bytes(4 * 128)))
        with self.assertRaisesRegex(NxwrightError, "frame2.png is 8 by 16, where a video's "
                                                   "frames must all be 16 by 16"):
            add_video(self.source, self.pictures)
        self.assertFalse((self.source / "videos").exists())

    def test_pictures_are_taken_as_they_are(self):
        with self.assertRaisesRegex(NxwrightError, "a size, a start, and a length cut a video"):
            add_video(self.source, self.pictures, size=(8, 8))
        movies = [self.folder / "a.mp4", self.folder / "b.mp4"]
        for movie in movies:
            movie.write_bytes(b"not read here")
        with self.assertRaisesRegex(NxwrightError, "a.mp4 is not a still picture; a video is "
                                                   "made of one video file, or of still pictures"):
            add_video(self.source, movies)

    def test_still_pictures_of_other_kinds_make_a_video(self):
        frames = []
        for picture, kind in zip(self.pictures, ("jpg", "bmp", "gif")):
            frame = picture.with_suffix("." + kind)
            read_picture(picture.read_bytes()).convert("RGB").save(frame)
            frames.append(frame)
        add_video(self.source, frames, name="kinds")
        made = video_frames((self.source / "videos" / "kinds.video").read_bytes())
        self.assertEqual((made.width, made.height, len(made.pictures)), (16, 16, 3))
        _, _, rgb = read_jpeg(made.pictures[1])
        self.assertLess(mean_difference(rgb[:3], bytes((0, 0, 255))), 8)

    def test_mpo_photos_make_a_video(self):
        # Each photo holds two views of one moment; the first is the frame.
        photos = []
        for picture in self.pictures:
            photo = picture.with_suffix(".mpo.jpg")
            first = read_picture(picture.read_bytes()).convert("RGB")
            first.save(photo, "MPO", save_all=True, append_images=[Image.new("RGB", (16, 16))])
            photos.append(photo)
        add_video(self.source, photos, name="photos")
        made = video_frames((self.source / "videos" / "photos.video").read_bytes())
        self.assertEqual((made.width, made.height, len(made.pictures)), (16, 16, 3))
        _, _, rgb = read_jpeg(made.pictures[1])
        self.assertLess(mean_difference(rgb[:3], bytes((0, 0, 255))), 8)

    def test_an_animated_gif_is_a_video_file(self):
        gif = self.folder / "clip.gif"
        first, *others = [read_picture(picture.read_bytes()).convert("RGB")
                          for picture in self.pictures]
        first.save(gif, save_all=True, append_images=others)
        with mock.patch("nxwright.project.ffmpeg.shutil.which", return_value=None):
            with self.assertRaisesRegex(NxwrightError, "cuts a video file into frames through "
                                                       "ffmpeg"):
                add_video(self.source, [gif])
        with self.assertRaisesRegex(NxwrightError, "clip.gif is not a still picture"):
            add_video(self.source, [self.pictures[0], gif])

    def test_a_video_file_is_cut_by_ffmpeg(self):
        movie = self.folder / "movie.mp4"
        movie.write_bytes(b"not read here")
        cut = [picture.read_bytes() for picture in self.pictures[:2]]

        def ffmpeg_cuts(command, **_):
            pattern = command[-1]
            for number, picture in enumerate(cut, start=1):
                Path(pattern.replace("%05d", "%05d" % number)).write_bytes(picture)
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with mock.patch("nxwright.project.ffmpeg.shutil.which", return_value="ffmpeg"), \
                mock.patch("nxwright.project.ffmpeg.subprocess.run",
                           side_effect=ffmpeg_cuts) as run:
            add_video(self.source, [movie], 8, (16, 16), 1.5, 2)
        command = run.call_args.args[0]
        self.assertEqual([command[command.index(option) + 1]
                          for option in ("-i", "-ss", "-t", "-r", "-vf")],
                         [str(movie), "1.500", "2.000", "8", "scale=16:16"])
        frames = video_frames((self.source / "videos" / "movie.video").read_bytes())
        self.assertEqual((len(frames.pictures), frames.length), (2, 250))

    def test_a_video_file_needs_ffmpeg(self):
        movie = self.folder / "movie.mp4"
        movie.write_bytes(b"not read here")
        with mock.patch("nxwright.project.ffmpeg.shutil.which", return_value=None):
            with self.assertRaisesRegex(NxwrightError, "movie.mp4 is no still picture nxwright "
                                                       "reads: nxwright cuts a video file into "
                                                       "frames through ffmpeg, which is not on "
                                                       "the PATH"):
                add_video(self.source, [movie])
        with self.assertRaisesRegex(NxwrightError, "absent.mp4 cannot be read"):
            add_video(self.source, [self.folder / "absent.mp4"])

    def test_the_command_takes_its_options(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["video", str(self.source), *map(str, self.pictures),
                                   "--rate", "20", "--name", "flash"]), 0)
        self.assertIn("Added the video flash", output.getvalue())
        frames = video_frames((self.source / "videos" / "flash.video").read_bytes())
        self.assertEqual(frames.starts, (0, 50, 100))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["video", str(self.source), str(self.pictures[0]), "--size", "320x240"])

    def test_a_folder_with_a_made_video_builds_and_extracts_back(self):
        add_video(self.source, self.pictures)
        before = folder_files(self.source)
        build(self.source, self.folder / "made.HMI")
        extract(self.folder / "made.HMI", self.source)
        self.assertEqual(folder_files(self.source), before)

    def test_a_rotated_folder_gets_files_turned_for_its_screen(self):
        # A picture 24 by 8 is padded to 32 by 16, then turned to 16 by 32.
        self.rotate()
        wide = self.folder / "wide.png"
        image = gradient(24, 8)
        wide.write_bytes(write_png(24, 8, image.tobytes()))
        add_animation(self.source, [wide], 50)
        add_video(self.source, [wide])
        animation = animation_frames((self.source / "animations" / "wide.screen.gmov")
                                     .read_bytes())
        video = video_frames((self.source / "videos" / "wide.video").read_bytes())
        self.assertEqual((animation.rotation, video.rotation), (90, 90))
        self.assertEqual(video.pictures[0], video_frame(read_picture(wide.read_bytes()), 90))
        self.assertEqual(read_jpeg(animation.pictures[0])[:2], (16, 32))


class SoundWarningTest(MediaCommandTestCase):
    """The checks' warning of a sound not in the Editor's form."""

    def check(self, read_bytes=True):
        return check_folder(folder_reader(self.source), lambda path: (self.source / path).is_file(),
                            read_bytes=folder_byte_reader(self.source)
                            if read_bytes else None).findings()

    def test_a_sound_without_hmic_is_warned_of_on_its_line(self):
        add_sound(self.source, SOURCES / "short22k.wav", "plain")
        add_sound(self.source, SOURCES / "odd8.wav")
        (self.source / "sounds" / "plain.wav").write_bytes((SOURCES / "short22k.wav").read_bytes())
        findings = self.check()
        self.assertEqual([(found.file, found.severity, found.rule) for found in findings],
                         [("app.toml", "warning", "sound-file-form")])
        line = self.app().split("\n")[findings[0].line - 1]
        self.assertIn('"plain"', line)
        self.assertIn("sounds/plain.wav: it has no hmic chunk", findings[0].message)
        self.assertIn("`nxwright sound` makes the file", findings[0].message)
        # Only a check given the files' bytes reads them.
        self.assertEqual(self.check(read_bytes=False), [])

    def test_a_missing_sound_is_the_checks_error_alone(self):
        add_sound(self.source, SOURCES / "odd8.wav")
        (self.source / "sounds" / "odd8.wav").unlink()
        self.assertEqual([(found.severity, found.message) for found in self.check()],
                         [("error", "sounds/odd8.wav is missing")])

    def test_nxwright_check_shows_it(self):
        add_sound(self.source, SOURCES / "odd8.wav")
        (self.source / "sounds" / "odd8.wav").write_bytes((SOURCES / "odd8.wav").read_bytes())
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["check", str(self.source)]), 0)
        self.assertIn("warning: sounds/odd8.wav: it has no hmic chunk", output.getvalue())


class FfmpegCommandTest(unittest.TestCase):

    def test_its_own_words_say_why_a_video_failed(self):
        done = mock.Mock(returncode=1, stdout=b"", stderr=b"moov atom not found\n")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("nxwright.project.ffmpeg.subprocess.run", return_value=done):
            with self.assertRaisesRegex(NxwrightError, "could not read a.mp4: moov atom"):
                ffmpeg.video_as_pngs("ffmpeg", Path("a.mp4"), Path(folder), 12)

    def test_a_video_it_cut_nothing_from_is_refused(self):
        done = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("nxwright.project.ffmpeg.subprocess.run", return_value=done):
            with self.assertRaisesRegex(NxwrightError, "cut no picture from a.mp4"):
                ffmpeg.video_as_pngs("ffmpeg", Path("a.mp4"), Path(folder), 12)

    def test_it_never_waits_for_a_key(self):
        done = mock.Mock(returncode=0, stdout=b"", stderr=b"")
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch("nxwright.project.ffmpeg.subprocess.run", return_value=done) as run:
            with self.assertRaises(NxwrightError):
                ffmpeg.video_as_pngs("ffmpeg", Path("a.mp4"), Path(folder), 12)
        self.assertIs(run.call_args.kwargs["stdin"], ffmpeg.subprocess.DEVNULL)


if __name__ == "__main__":
    unittest.main()
