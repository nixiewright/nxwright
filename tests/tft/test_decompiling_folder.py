"""The source folder's files of a decoded file (tft/decompiling/folder.py):
its app.toml, program.nx, macros.nx, fonts, and pictures, around the pages'
files, which tests/tft/test_decompiling_page_files.py tests.

The probes' tests have the compile write a probe's user code in memory, and
compare the folder's files with the probe's own facts, and the whole
file's test has the compile write a whole file in memory. A picture's test
makes its screen copy in memory, as the build makes it from a picture file,
and makes it again from the picture file the folder writer gives. The
round trip's tests write and build whole folders.
"""
from dataclasses import replace
import random
import re
import tempfile
from pathlib import Path
import tomllib
import unittest

from PIL import Image
from nxwright import NxwrightError
from nxwright.project.component_defaults import DEFAULTS_FILE
from nxwright.project.media_files import animation_files, gmovmaker_frames
from nxwright.project.picture_cache import make_screen_copy
from nxwright.project.pictures import write_png
from nxwright.project.screen_copy import (FORMAT_COMPRESSED, FORMAT_RAW, FORMAT_RAW_WITH_HEADER,
                                          ROTATIONS, ScreenPixels, encode_screen_copy)
from nxwright.project.zi_font import HEADER_SIZE
from nxwright.source.device_keys import device_keys
from nxwright.source.macros_source import macros_to_source

from nxwright.tft import frame
from nxwright.tft.commands.compile import compile_project
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.folder import (decompiled_folder, folder_files, gmovmaker_file,
                                     picture_file)
from nxwright.tft.firmware import Firmware
from nxwright.tft.packaging import firmware_names
from tools.tft.probing import macro_probes, statement_probes
from tests.tft.test_decompiling_resources import p_project_with_media
from tests.tft.unit_inputs import probe_change, probe_facts, with_font_blocks

# The probes of macros whose lines are written as the decoder writes them.
_MACROS_AS_DECODED = ("macros-called", "macros-sorted-by-crc")


def _in_memory(probe) -> tuple:
    """Returns (the Project of facts of `probe`, with its fonts' blocks, the
    decoded file of the user code the compile writes for it, and its fonts'
    blocks)."""
    project = with_font_blocks(probe_facts(probe), probe.base)
    settings = project.settings
    decoded = decoded_user_code(frame.user_code(project), probe.base, settings.model.name,
                                settings.rotation, settings.encoding)
    fonts = [project.blocks[name] for kind, name in project.resources if kind == "font"]
    return project, decoded, fonts


class FolderFilesTest(unittest.TestCase):

    def test_each_probe_of_statements(self):
        # app.toml lists the probe's pages and fonts, with its device
        # settings; defaults.toml and each font are nxwright's own bytes;
        # and program.nx declares the probe's int variables, with their
        # values, then gives the decoded code of program.s.
        for probe in statement_probes.PROBES:
            with self.subTest(probe.name):
                project, decoded, fonts = _in_memory(probe)
                files = folder_files(decoded, {"font": fonts})
                app = tomllib.loads(files["app.toml"].decode("utf-8"))
                self.assertEqual(app, {"format": 1, "language": "nextion",
                                       "pages": [page.name for page in project.pages],
                                       "pictures": [], "fonts": ["NotoSans24"],
                                       **device_keys(project.settings)})
                self.assertEqual(files["defaults.toml"], DEFAULTS_FILE.read_bytes())
                self.assertEqual(files["fonts/NotoSans24.zi"], fonts[0])
                self.assertEqual(sorted(path for path in files if path.startswith("pages/")),
                                 sorted("pages/%s%s" % (page.name, suffix)
                                        for page in project.pages
                                        for suffix in (".page.toml", ".nx")))
                lines = files["program.nx"].decode("utf-8").split("\n")
                self.assertEqual(lines[-1], "")
                ints = frame.read_int_declaration(lines[0])
                self.assertEqual([value for _, value in ints],
                                 [value for _, value in frame.int_variables(project)])
                self.assertEqual(ints, [(each.name.text, each.value) for each in decoded.ints])
                self.assertNotIn("macros.nx", files)

    def test_the_device_settings(self):
        # app.toml keeps the one-time update and the memory file's storage
        # size the file gives, and leaves them out at their defaults.
        _, decoded, fonts = _in_memory(statement_probes.PROBES[0])
        changed = replace(decoded, one_time_update=True, memory_file_storage_size=4096)
        keys = {"one_time_update": True, "memory_file_storage_size": 4096}
        for each, kept in ((decoded, False), (changed, True)):
            with self.subTest(kept=kept):
                app = tomllib.loads(folder_files(each, {"font": fonts})["app.toml"].decode())
                for key, value in keys.items():
                    if kept:
                        self.assertEqual(app[key], value)
                    else:
                        self.assertNotIn(key, app)

    def test_a_program_of_no_lines(self):
        # A file whose program.s has no lines, no int variables and no code,
        # gets a program.nx of a comment alone. The build writes an empty
        # program.nx as a new project's program.s, with its own lines.
        _, decoded, fonts = _in_memory(statement_probes.PROBES[0])
        empty = replace(decoded, ints=[], program=CodeRun(decoded.program.place, []))
        lines = folder_files(empty, {"font": fonts})["program.nx"].decode("utf-8").split("\n")
        self.assertEqual((len(lines), lines[0][:2], lines[1]), (2, "//", ""))

    def test_each_probe_of_macros(self):
        # macros.nx gives the probe's macros, in its order, each named
        # macro0, macro1, and so on, as no guess matches a macro's name, and
        # a call names the macro so named. A probe without macros gets no
        # macros.nx. The lines are compared with the probe's own where it
        # writes them as the decoder does: with no label, no int variable
        # but sys0 to sys2, and only decimal numbers.
        compared = 0
        for probe in macro_probes.PROBES:
            with self.subTest(probe.name):
                _, decoded, fonts = _in_memory(probe)
                macros = probe_change(probe).macros
                files = folder_files(decoded, {"font": fonts})
                if not macros:
                    self.assertNotIn("macros.nx", files)
                    continue
                text = files["macros.nx"].decode("utf-8")
                self.assertEqual(re.findall(r"^macro (.*):$", text, re.M),
                                 ["macro%d" % number for number in range(len(macros))])
                if probe.name not in _MACROS_AS_DECODED:
                    continue
                readable = {name: "macro%d" % number for number, (name, _) in enumerate(macros)}

                def renamed(line: str) -> str:
                    return re.sub(r"(?<=call )(.+)$", lambda found: readable[found.group(1)],
                                  line)
                self.assertEqual(text, macros_to_source(
                    [(readable[name], [renamed(line) for line in lines])
                     for name, lines in macros]))
                compared += 1
        self.assertEqual(compared, len(_MACROS_AS_DECODED))

    def test_font_names(self):
        # A font is named after the name in its header, as nxwright's
        # extract names a new one. A font whose header holds a name taken
        # before it, or no name nxwright takes, is named after its ID.
        probe = statement_probes.PROBES[0]
        _, decoded, [font] = _in_memory(probe)
        nameless = bytearray(font)
        nameless[HEADER_SIZE] = 0x80
        files = folder_files(decoded, {"font": [font, font, bytes(nameless)]})
        self.assertEqual(tomllib.loads(files["app.toml"].decode("utf-8"))["fonts"],
                         ["NotoSans24", "font-01", "font-02"])
        self.assertEqual(files["fonts/font-02.zi"], bytes(nameless))


class MediaFilesTest(unittest.TestCase):

    def test_an_animation_a_video_and_two_sounds(self):
        # Each is named as nxwright's extract names a new one, from its ID,
        # and app.toml lists it. A video and a sound are their blocks, and
        # an animation is its screen form beside GmovMaker's file of the
        # frames it shows, at their sizes and durations.
        _, media = p_project_with_media()
        _, decoded, fonts = _in_memory(statement_probes.PROBES[0])
        files = folder_files(decoded, {"font": fonts, "animation": media["animation"],
                                       "video": media["video"], "sound": media["sound"]})
        app = tomllib.loads(files["app.toml"].decode("utf-8"))
        self.assertEqual((app["animations"], app["videos"], app["sounds"]),
                         (["animation-00"], ["video-00"], ["sound-00", "sound-01"]))
        self.assertEqual(files["animations/animation-00.screen.gmov"], media["animation"][0])
        self.assertEqual(files["videos/video-00.video"], media["video"][0])
        self.assertEqual([files["sounds/sound-00.wav"], files["sounds/sound-01.wav"]],
                         media["sound"])
        frames = gmovmaker_frames(files["animations/animation-00.gmov"])
        self.assertEqual([(image.size, duration) for image, duration in frames],
                         [((16, 8), 100), ((16, 8), 50)])
        # Its frames come back from JPEG pictures, so their colours are close
        # to the frames' own, red then blue.
        for (image, _), colour in zip(frames, ((255, 0, 0), (0, 0, 255))):
            self.assertTrue(all(abs(got - wanted) < 16 for got, wanted in
                                zip(image.getpixel((8, 4)), colour + (255,))))

    def test_an_animation_at_each_rotation(self):
        # The screen form keeps its frames turned for the screen. GmovMaker's
        # file keeps them upright, so each comes back at its own size.
        _, decoded, fonts = _in_memory(statement_probes.PROBES[0])
        picture = Image.new("RGBA", (16, 8), (255, 0, 0, 255))
        picture.paste((0, 0, 255, 255), (0, 0, 4, 4))
        for rotation in ROTATIONS:
            with self.subTest(rotation=rotation):
                screen = animation_files([(picture, 100)], rotation)[1]
                files = folder_files(replace(decoded, rotation=rotation),
                                     {"font": fonts, "animation": [screen]})
                [(image, _)] = gmovmaker_frames(files["animations/animation-00.gmov"])
                self.assertEqual(image.size, (16, 8))
                # The blue corner is still at the top left.
                self.assertLess(image.getpixel((1, 1))[0], 64)
                self.assertGreater(image.getpixel((12, 6))[0], 192)

    def test_a_frame_that_is_no_picture(self):
        # A screen form whose frame's JPEG picture is cut short is refused.
        screen = animation_files([(Image.new("RGBA", (16, 8), (255, 0, 0, 255)), 100)])[1]
        start = screen.index(bytes.fromhex("ffd8"))
        cut = screen[:start + 4] + bytes(len(screen) - start - 4)
        self.assertRaises(DecodeError, gmovmaker_file, cut)

    def test_a_frame_of_no_time(self):
        # A screen form whose frame lasts 0 ms is refused: GmovMaker's file
        # keeps no such frame.
        screen = bytearray(animation_files([(Image.new("RGBA", (16, 8), (255, 0, 0, 255)),
                                              100)])[1])
        # The first frame's entry follows the 76-byte header, and gives its
        # duration at its 24th byte.
        screen[76 + 24:76 + 28] = bytes(4)
        self.assertRaises(DecodeError, gmovmaker_file, bytes(screen))


class PictureFileTest(unittest.TestCase):

    def test_each_format_and_rotation(self):
        # The screen copy the build makes of the picture file is the screen
        # copy the file was made from, for opaque, partly transparent, and
        # transparent pixels of any colour, in each format, at each rotation.
        chosen = random.Random(1)
        width, height = 23, 11
        rgba = bytes(chosen.choice((0, 1, 37, 128, 200, 254, 255)) if number % 4 == 3
                     else chosen.randrange(256) for number in range(width * height * 4))
        picture = write_png(width, height, rgba)
        for kind in (FORMAT_RAW, FORMAT_RAW_WITH_HEADER, FORMAT_COMPRESSED):
            for rotation in ROTATIONS:
                with self.subTest(kind=kind, rotation=rotation):
                    block = make_screen_copy(picture, kind, rotation).block
                    again = make_screen_copy(picture_file(block, rotation), kind, rotation)
                    self.assertEqual(again.block, block)

    def test_a_pixel_no_picture_gives(self):
        # A fully transparent pixel of the compressed format keeps a colour
        # of 0, or one of the few its rounding gives a pixel of almost no
        # alpha. Any other colour is refused.
        block = encode_screen_copy(ScreenPixels(2, 1, [0x0841, 0], [0, 0]), FORMAT_COMPRESSED, 0)
        self.assertRaises(DecodeError, picture_file, block, 0)


class DecompiledFolderTest(unittest.TestCase):

    def test_a_whole_file(self):
        # A probe's whole file, compiled in memory on zeros for the firmware,
        # is written into an empty folder as folder_files gives its files,
        # and its names no guess matched come back with what each names: its
        # fourth int variable, which the probe names a, as int3, and its four
        # macros.
        probe = macro_probes.PROBES[0]
        project, decoded, fonts = _in_memory(probe)
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        with tempfile.TemporaryDirectory() as scratch:
            names = decompiled_folder(compile_project(project, firmware), Path(scratch))
            written = {path.relative_to(scratch).as_posix(): path.read_bytes()
                       for path in Path(scratch).rglob("*") if path.is_file()}
        self.assertEqual(written, folder_files(decoded, {"font": fonts}))
        self.assertEqual([(owner, name.text, name.matched) for owner, name in names],
                         [(("int", "int3"), "int3", False)]
                         + [(("macro", "macro%d" % number), "macro%d" % number, False)
                            for number in range(4)])

    def test_a_folder_holding_files(self):
        # A folder that holds a file is refused before the TFT file is read,
        # and keeps its file.
        with tempfile.TemporaryDirectory() as scratch:
            (Path(scratch) / "kept.txt").write_text("kept", encoding="utf-8")
            self.assertRaises(NxwrightError, decompiled_folder, b"", Path(scratch))
            self.assertEqual(sorted(path.name for path in Path(scratch).iterdir()),
                             ["kept.txt"])

    def test_a_file_for_the_folder(self):
        # A file where the folder should be is refused, and kept.
        with tempfile.TemporaryDirectory() as scratch:
            kept = Path(scratch) / "kept.txt"
            kept.write_text("kept", encoding="utf-8")
            self.assertRaises(NxwrightError, decompiled_folder, b"", kept)
            self.assertEqual(kept.read_text(encoding="utf-8"), "kept")


if __name__ == "__main__":
    unittest.main()
