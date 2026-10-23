"""The project writer: applying an edited dump the way the Editor saves."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nxwright.project.dumper import ProjectDumper
from nxwright import NxwrightError
from nxwright.project.container import (DIRECTORY_COPY_OFFSET, ENTRY_SIZE, HmiContainer,
                                        encode_directory)
from nxwright.project.device_settings import DeviceSettings, manifest_header
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION
from nxwright.project.pictures import read_picture
from nxwright.project import project_writer
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.resources import (ImageSource, encode_image_source, encode_manifest,
                                        parse_image_source, parse_manifest)
from nxwright.project.screen_copy import (FORMAT_COMPRESSED, decode_screen_copy,
                                          matches_within_editor_rounding, screen_copy_format,
                                          stored_pixels)
from nxwright.project.screen_models import model_named
from nxwright.project.stamp import block_stamp, manifest_stamp, with_manifest_stamp, with_stamp
from tests.test_container import build_project
from tests.test_dumper import font_block
from tests.test_page_block import attribute, object_body, page_block, record

PICTURES = Path(__file__).resolve().parent / "fixtures" / "pictures"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Two sample pictures that do not look the same turned by 180 degrees, so that
# the writer can tell the project's screen rotation from them.
SMALL_PROJECT_PICTURES = ("compressed/14-dot-3-5-8x8", "compressed/18-unique-9x7")


def sample_png(name: str) -> bytes:
    """Returns the PNG of the sample picture `name`, such as "raw/19-red-1x1"."""
    return (PICTURES / (name + ".png")).read_bytes()


def picture_blocks(number: int, name: str) -> list:
    """The ".is" and ".i" blocks of the sample picture `name` as block `number`."""
    image = read_picture(sample_png(name))
    source = encode_image_source(ImageSource(image.width, image.height, sample_png(name), ".png"))
    return [("%d.is" % number, source, 0),
            ("%d.i" % number, (PICTURES / (name + ".i")).read_bytes(), 0)]


def small_page(name: str, text: bytes) -> bytes:
    """Returns a stamped page block whose only object is the page, shaped like the
    Editor's, with `text` as its txt. Its header is an ordinary page's in a
    project in iso-8859-1, as the Editor writes it."""
    return with_stamp(page_block(name, object_body(
        record(b"att-5"), attribute("type", bytes([121])), attribute("id", b"\0"),
        attribute("objname", name.encode("ascii")), attribute("vscope", b"\0"),
        attribute("txt", text)), header_16=bytes.fromhex("00000000004f2100"),
        header_40=bytes.fromhex("01440203") + bytes(12)))


def stamped_manifest(*block_names: str, header: bytes = None) -> bytes:
    """A manifest listing `block_names`, with the device settings of an
    NX1060P101 project the Editor saved, or of `header`, and stamped as it
    would be."""
    reference = header or (Path(__file__).resolve().parent / "fixtures" / "manifests"
                           / "NX1060P101.main").read_bytes()
    resources = [(name.rsplit(".", 1)[1], name) for name in block_names]
    return with_manifest_stamp(encode_manifest(reference, resources), reference)


def write_small_project(folder: Path, stale_entries: int = 0,
                        pictures: tuple = SMALL_PROJECT_PICTURES, header: bytes = None) -> Path:
    """Writes project.HMI into `folder`, laid out like the Editor's, and returns
    its path. It holds pages "first" (txt "hello") and "second" (txt "bye"), the
    sample `pictures`, and fonts of heights 16 and 24. Its program declares
    sys0 to sys2, as the Editor's new project does. `stale_entries` adds
    empty stale entries before the blocks, to fill the directory. `header`,
    a manifest's header, gives other device settings (stamped_manifest)."""
    picture_names = ["%d.i" % number for number in range(len(pictures))]
    blocks = [("", b"", 1)] * stale_entries + [
        ("main.HMI", stamped_manifest("0.pa", "1.pa", *picture_names, "0.zi", "1.zi",
                                      header=header), 0),
        ("Program.s", EDITOR_PROGRAM_DECLARATION.encode() + b"\r\npage 0", 0),
        ("0.pa", small_page("first", b"hello"), 0),
        ("1.pa", small_page("second", b"bye"), 0),
    ]
    for number, name in enumerate(pictures):
        blocks += picture_blocks(number, name)
    blocks += [("0.zi", font_block(16), 0), ("1.zi", font_block(24), 0)]
    path = folder / "project.HMI"
    path.write_bytes(build_project(blocks, editor_layout=True))
    return path


# A project's macros, as the Editor stores them in comcode.sn (format.md).
MACROS = b"newcall\r\n2\r\nprinth 4D\r\nprinth 4E\r\n"


def edit_text(path: Path, old: str, new: str):
    """Replaces `old` with `new` in the text file `path`. Fails the test when
    `old` is not there, so an edit cannot silently do nothing."""
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError("%r not in %s" % (old, path))
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


class WriterTestCase(unittest.TestCase):
    """A small project and its dump in a temporary folder."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.project = write_small_project(self.folder)
        self.dump = self.folder / "dump"
        ProjectDumper(self.project, self.dump).dump()
        self.output = self.folder / "out.HMI"

    def tearDown(self):
        self._folder.cleanup()

    def write(self) -> list:
        return ProjectWriter(self.project, self.dump, self.output).write()

    def written(self) -> HmiContainer:
        """Returns the output, after checking what every written file must hold."""
        after = HmiContainer.from_file(self.output)
        self.assertTrue(after.directory_checksum_is_valid())
        length = 4 + after.entry_count * ENTRY_SIZE + 4
        self.assertEqual(after.data[DIRECTORY_COPY_OFFSET:DIRECTORY_COPY_OFFSET + length],
                         after.data[:length])
        offsets = [entry.offset for entry in after.entries]
        self.assertEqual(offsets, sorted(offsets))
        self.assertEqual(after.entries[-1].offset + after.entries[-1].size, after.file_size)
        manifest_block = after.blocks["main.HMI"]
        reference = HmiContainer.from_file(self.project).blocks["main.HMI"]
        self.assertEqual(manifest_stamp(manifest_block, reference),
                         int.from_bytes(manifest_block[:4], "little"))
        for name, block in after.blocks.items():
            if name.endswith(".pa"):
                self.assertEqual(block_stamp(block), int.from_bytes(block[:4], "little"), name)
        return after

    def resources(self, container: HmiContainer) -> list:
        return parse_manifest(container.blocks["main.HMI"]).resources

    def assert_stale_and_unnamed(self, container: HmiContainer, original_index: int, name: str):
        """Checks that the entry at `original_index` is now stale and no longer
        named `name`. The Editor finds blocks by name, so a stale entry that kept
        its name would be loaded instead of the live one."""
        entry = container.entries[original_index]
        self.assertTrue(entry.stale)
        self.assertEqual(entry.name_field, b"\0" + name.encode().ljust(16, b"\0")[1:])
        self.assertNotIn(name, container.blocks)


class PageChangesTest(WriterTestCase):

    def test_replaces_changed_page_like_the_editor(self):
        edit_text(self.dump / "pages" / "01-second.txt", 'txt = "bye"', 'txt = "goodbye"')
        self.assertEqual(self.write(), ["Replaced page 1 (second, block 1.pa)"])
        before = HmiContainer.from_file(self.project)
        after = self.written()
        self.assertEqual(len(after.entries), len(before.entries) + 1)
        old_index = [entry.name for entry in before.entries].index("1.pa")
        self.assertTrue(after.entries[old_index].stale)
        self.assertEqual(after.entries[old_index].name_field, b"\0.pa" + bytes(12))
        last = after.entries[-1]
        self.assertEqual((last.name, last.offset), ("1.pa", before.file_size))
        self.assertIn(b"goodbye", after.blocks["1.pa"])
        self.assertEqual(after.blocks["0.pa"], before.blocks["0.pa"])
        # Same pages, same order: the manifest is not rewritten.
        self.assertEqual(after.blocks["main.HMI"], before.blocks["main.HMI"])

    def test_adds_a_page(self):
        text = (self.dump / "pages" / "01-second.txt").read_text(encoding="utf-8")
        (self.dump / "pages" / "02-third.txt").write_text(
            text.replace("page second", "page third"), encoding="utf-8", newline="\n")
        self.assertIn("Added page 2 (third) as block 2.pa", self.write())
        after = self.written()
        self.assertEqual([name for kind, name in self.resources(after) if kind == "pa"],
                         ["0.pa", "1.pa", "2.pa"])
        # The new entry goes right after the last page entry.
        self.assertEqual(self.resources(after)[2], ("pa", "2.pa"))

    def test_removes_a_page(self):
        (self.dump / "pages" / "01-second.txt").unlink()
        self.assertIn("Removed page second (block 1.pa)", self.write())
        before = HmiContainer.from_file(self.project)
        after = self.written()
        self.assertEqual(self.resources(after), [("pa", "0.pa"), ("i", "0.i"), ("i", "1.i"),
                                                 ("zi", "0.zi"), ("zi", "1.zi")])
        self.assert_stale_and_unnamed(after, [e.name for e in before.entries].index("1.pa"), "1.pa")

    def test_reorders_pages(self):
        pages = self.dump / "pages"
        (pages / "00-first.txt").rename(pages / "tmp.txt")
        (pages / "01-second.txt").rename(pages / "00-second.txt")
        (pages / "tmp.txt").rename(pages / "01-first.txt")
        self.assertEqual(self.write(), ["Rewrote the manifest (6 resources)"])
        before = HmiContainer.from_file(self.project)
        after = self.written()
        self.assertEqual(self.resources(after)[:2], [("pa", "1.pa"), ("pa", "0.pa")])
        self.assertEqual(after.blocks["0.pa"], before.blocks["0.pa"])

    def test_refuses_two_pages_with_one_name(self):
        text = (self.dump / "pages" / "01-second.txt").read_text(encoding="utf-8")
        (self.dump / "pages" / "02-again.txt").write_text(text, encoding="utf-8", newline="\n")
        self.assert_refused("two page files")

    def test_refuses_gap_in_page_ids(self):
        pages = self.dump / "pages"
        (pages / "01-second.txt").rename(pages / "02-second.txt")
        self.assert_refused("page IDs must run from 0 without gaps: it has no page 1$")

    def assert_refused(self, message: str):
        with self.assertRaisesRegex(NxwrightError, message):
            self.write()
        self.assertFalse(self.output.exists())


class FontAndProgramChangesTest(WriterTestCase):

    def test_adds_a_font(self):
        (self.dump / "fonts" / "02.zi").write_bytes(font_block(40))
        self.assertIn("Added font 2 as block 2.zi", self.write())
        after = self.written()
        self.assertEqual([name for kind, name in self.resources(after) if kind == "zi"],
                         ["0.zi", "1.zi", "2.zi"])
        self.assertEqual(after.blocks["2.zi"], font_block(40))

    def test_removes_a_font(self):
        # Removing font 0 leaves font 24 (block 1.zi) as the only font, ID 0.
        (self.dump / "fonts" / "00.zi").unlink()
        (self.dump / "fonts" / "01.zi").rename(self.dump / "fonts" / "00.zi")
        self.assertIn("Removed font block 0.zi", self.write())
        before = HmiContainer.from_file(self.project)
        after = self.written()
        self.assertEqual([name for kind, name in self.resources(after) if kind == "zi"], ["1.zi"])
        self.assert_stale_and_unnamed(after, [e.name for e in before.entries].index("0.zi"), "0.zi")

    def test_reorders_fonts(self):
        fonts = self.dump / "fonts"
        first, second = (fonts / "00.zi").read_bytes(), (fonts / "01.zi").read_bytes()
        (fonts / "00.zi").write_bytes(second)
        (fonts / "01.zi").write_bytes(first)
        self.assertEqual(self.write(), ["Rewrote the manifest (6 resources)"])
        after = self.written()
        self.assertEqual([name for kind, name in self.resources(after) if kind == "zi"],
                         ["1.zi", "0.zi"])

    def test_refuses_gap_in_font_ids(self):
        (self.dump / "fonts" / "00.zi").unlink()
        with self.assertRaisesRegex(NxwrightError,
                                    "font IDs must run from 0 without gaps: it has no font 0$"):
            self.write()

    def test_replaces_program(self):
        (self.dump / "program.s").write_bytes(b"page 1")
        self.assertEqual(self.write(), ["Replaced program.s"])
        self.assertEqual(self.written().blocks["Program.s"], b"page 1")

    def test_adds_replaces_and_removes_the_macros(self):
        # The macros' block, comcode.sn, is written as the dump's macros.s
        # holds it, and a dump without one has none.
        (self.dump / "macros.s").write_bytes(MACROS)
        self.assertEqual(self.write(), ["Added the macros"])
        self.assertEqual(self.written().blocks["comcode.sn"], MACROS)
        # Dumped again, the same macros change nothing.
        self.project, self.dump = self.output, self.folder / "dump2"
        ProjectDumper(self.project, self.dump).dump()
        self.output = self.folder / "out2.HMI"
        self.assertEqual(self.write(), [])
        self.assertFalse(self.output.exists())
        (self.dump / "macros.s").write_bytes(MACROS + b"newcall1\r\n0\r\n")
        self.output = self.folder / "out3.HMI"
        self.assertEqual(self.write(), ["Replaced the macros"])
        self.assertEqual(self.written().blocks["comcode.sn"], MACROS + b"newcall1\r\n0\r\n")
        (self.dump / "macros.s").unlink()
        self.output = self.folder / "out4.HMI"
        self.assertEqual(self.write(), ["Removed the macros"])
        before = HmiContainer.from_file(self.project)
        self.assert_stale_and_unnamed(self.written(),
                                      [entry.name for entry in before.entries].index("comcode.sn"),
                                      "comcode.sn")


class PictureChangesTest(WriterTestCase):

    def picture_names(self, container: HmiContainer) -> list:
        return [name for kind, name in self.resources(container) if kind == "i"]

    def assert_picture(self, container: HmiContainer, block_name: str, png: bytes):
        """The picture's PNG block holds `png`, and its screen copy decodes to it."""
        source = parse_image_source(container.blocks[block_name + "s"])
        image = read_picture(png)
        self.assertEqual((source.width, source.height, source.data), (image.width, image.height, png))
        self.assertEqual(decode_screen_copy(container.blocks[block_name], 180),
                         stored_pixels(image, FORMAT_COMPRESSED))

    def test_adds_a_picture(self):
        png = sample_png("compressed/23-alpha-ramp-unique-16x4")
        (self.dump / "images" / "0002.png").write_bytes(png)
        self.assertEqual(self.write(), ["Added picture 2 as block 2.i",
                                        "Rewrote the manifest (7 resources)"])
        after = self.written()
        self.assertEqual(self.picture_names(after), ["0.i", "1.i", "2.i"])
        self.assert_picture(after, "2.i", png)
        # A new dump shows the picture, with the generated screen copy.
        ProjectDumper(self.output, self.folder / "again").dump()
        self.assertEqual((self.folder / "again" / "images" / "0002.png").read_bytes(), png)

    def test_replaces_a_picture(self):
        png = sample_png("compressed/12-dot-top-right-8x8")
        (self.dump / "images" / "0000.png").write_bytes(png)
        changes = self.write()
        self.assertIn("Added picture 0 as block 2.i", changes)
        self.assertIn("Removed picture block 0.i", changes)
        before = HmiContainer.from_file(self.project)
        after = self.written()
        self.assertEqual(self.picture_names(after), ["2.i", "1.i"])
        self.assert_picture(after, "2.i", png)
        names = [entry.name for entry in before.entries]
        self.assert_stale_and_unnamed(after, names.index("0.i"), "0.i")
        self.assert_stale_and_unnamed(after, names.index("0.is"), "0.is")

    def test_removes_a_picture(self):
        images = self.dump / "images"
        (images / "0000.png").unlink()
        (images / "0001.png").rename(images / "0000.png")
        self.assertIn("Removed picture block 0.i", self.write())
        after = self.written()
        self.assertEqual(self.picture_names(after), ["1.i"])
        self.assertNotIn("0.is", after.blocks)

    def test_reorders_pictures(self):
        images = self.dump / "images"
        first, second = (images / "0000.png").read_bytes(), (images / "0001.png").read_bytes()
        (images / "0000.png").write_bytes(second)
        (images / "0001.png").write_bytes(first)
        self.assertEqual(self.write(), ["Rewrote the manifest (6 resources)"])
        self.assertEqual(self.picture_names(self.written()), ["1.i", "0.i"])

    def test_screen_copy_files_are_not_read(self):
        (self.dump / "images" / "0000.i").write_bytes(b"edited by hand")
        self.assertEqual(self.write(), [])

    def test_refuses_gap_in_picture_ids(self):
        images = self.dump / "images"
        (images / "0001.png").rename(images / "0002.png")
        self.assert_refused("picture IDs must run from 0 without gaps: it has no picture 1$")

    def test_refuses_unreadable_png(self):
        (self.dump / "images" / "0002.png").write_bytes(PNG_SIGNATURE + b"damaged")
        self.assert_refused("images/0002.png")

    def test_refuses_one_pixel_picture(self):
        (self.dump / "images" / "0002.png").write_bytes(sample_png("raw/19-red-1x1"))
        self.assert_refused("1-by-1")

    def assert_refused(self, message: str):
        with self.assertRaisesRegex(NxwrightError, message):
            self.write()
        self.assertFalse(self.output.exists())


class ScreenModelTest(unittest.TestCase):
    """New pictures in projects of every screen copy format and rotation."""

    FORMATS = {"raw": 0, "raw-with-header": 3, "compressed": 4}

    def add_picture(self, folder: Path, pictures: tuple, png: bytes,
                    header: bytes = None) -> HmiContainer:
        project = write_small_project(folder, pictures=pictures, header=header)
        dump = folder / "dump"
        ProjectDumper(project, dump).dump()
        (dump / "images" / ("%04d.png" % len(pictures))).write_bytes(png)
        ProjectWriter(project, dump, folder / "out.HMI").write()
        return HmiContainer.from_file(folder / "out.HMI")

    def test_adds_a_picture_in_each_format_and_rotation(self):
        png = sample_png("compressed/17-unique-16x16")
        for models in sorted((PICTURES / "models").iterdir()):
            label, rotation = models.name.rsplit("-", 1)
            kind = self.FORMATS[label]
            with self.subTest(models=models.name), tempfile.TemporaryDirectory() as name:
                pictures = ("models/%s/18-unique-9x7" % models.name,
                            "models/%s/14-dot-3-5-8x8" % models.name)
                block = self.add_picture(Path(name), pictures, png).blocks["2.i"]
                self.assertEqual(screen_copy_format(block), kind)
                self.assertTrue(matches_within_editor_rounding(
                    decode_screen_copy(block, int(rotation)), read_picture(png), kind))

    def test_raw_one_pixel_picture_does_not_count_as_a_format(self):
        with tempfile.TemporaryDirectory() as name:
            pictures = ("models/compressed-90/19-red-1x1", "models/compressed-90/18-unique-9x7")
            block = self.add_picture(Path(name), pictures,
                                     sample_png("compressed/17-unique-16x16")).blocks["2.i"]
            self.assertEqual(screen_copy_format(block), 4)

    def test_a_first_picture_takes_the_projects_model_and_rotation(self):
        # With no pictures to confirm the format and pixel order, the
        # project's screen model and rotation give them, as a build takes them.
        png = sample_png("compressed/17-unique-16x16")
        for model in ("NX4832T035", "NX4832F035", "NX1060P101"):
            for rotation in (0, 90, 180, 270):
                settings = DeviceSettings(model_named(model), rotation, "iso-8859-1")
                with self.subTest(model=model, rotation=rotation), \
                        tempfile.TemporaryDirectory() as name:
                    block = self.add_picture(Path(name), (), png,
                                             manifest_header(settings)).blocks["0.i"]
                    kind = settings.model.picture_format
                    self.assertEqual(screen_copy_format(block), kind)
                    self.assertTrue(matches_within_editor_rounding(
                        decode_screen_copy(block, rotation), read_picture(png), kind))

    def test_one_pixel_raw_pictures_alone_confirm_nothing(self):
        # So the project's model and rotation give the format, as with none.
        png = sample_png("compressed/17-unique-16x16")
        with tempfile.TemporaryDirectory() as name:
            settings = DeviceSettings(model_named("NX1060P101"), 90, "iso-8859-1")
            block = self.add_picture(Path(name), ("models/compressed-90/19-red-1x1",), png,
                                     manifest_header(settings)).blocks["1.i"]
            self.assertEqual(screen_copy_format(block), FORMAT_COMPRESSED)
            self.assertTrue(matches_within_editor_rounding(
                decode_screen_copy(block, 90), read_picture(png), FORMAT_COMPRESSED))

    def test_format_3_project_with_only_compressed_pictures_is_refused(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaisesRegex(NxwrightError, "all compressed"):
                self.add_picture(Path(name), ("models/raw-with-header-0/21-red-40x30",),
                                 sample_png("compressed/17-unique-16x16"))


class UnsupportedPictureProjectTest(unittest.TestCase):
    """Projects whose pictures do not confirm the format and pixel order the
    writer generates: new pictures are refused, other edits still work."""

    def assert_new_picture_refused(self, pictures: tuple, message: str, header: bytes = None):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            project = write_small_project(folder, pictures=pictures, header=header)
            dump = folder / "dump"
            ProjectDumper(project, dump).dump()
            (dump / "images" / ("%04d.png" % len(pictures))).write_bytes(
                sample_png("compressed/17-unique-16x16"))
            with self.assertRaisesRegex(NxwrightError, message):
                ProjectWriter(project, dump, folder / "out.HMI").write()
            self.assertFalse((folder / "out.HMI").exists())
            # Removing the new picture again leaves an edit the writer accepts.
            (dump / "images" / ("%04d.png" % len(pictures))).unlink()
            edit_text(dump / "pages" / "00-first.txt", 'txt = "hello"', 'txt = "hi"')
            self.assertEqual(ProjectWriter(project, dump, folder / "out.HMI").write(),
                             ["Replaced page 0 (first, block 0.pa)"])

    def test_no_pictures_and_a_screen_model_nxwright_does_not_know(self):
        # Neither a picture nor the model gives the format.
        header = bytearray(manifest_header(DeviceSettings(model_named("NX1060P101"), 0,
                                                          "iso-8859-1")))
        header[16:20] = bytes.fromhex("00112233")
        self.assert_new_picture_refused(
            (), "the project's screen model, device ID 00112233, is not one nxwright knows",
            bytes(header))

    def test_mixed_formats(self):
        self.assert_new_picture_refused(("raw/14-dot-3-5-8x8", "compressed/18-unique-9x7"),
                                        "share one screen copy format")

    def test_only_pictures_that_look_the_same_turned(self):
        self.assert_new_picture_refused(("compressed/01-red-8x8", "compressed/04-white-8x8"),
                                        "looks the same in more than one screen rotation")

    def test_screen_copy_in_another_order(self):
        # A PNG whose screen copy holds its dot elsewhere stands for another rotation.
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            project = write_small_project(folder, pictures=("compressed/11-dot-top-left-8x8",))
            data = project.read_bytes()
            copy = (PICTURES / "compressed" / "11-dot-top-left-8x8.i").read_bytes()
            other = (PICTURES / "compressed" / "14-dot-3-5-8x8.i").read_bytes()
            self.assertEqual(len(copy), len(other))
            project.write_bytes(data.replace(copy, other))
            dump = folder / "dump"
            ProjectDumper(project, dump).dump()
            (dump / "images" / "0001.png").write_bytes(sample_png("compressed/17-unique-16x16"))
            with self.assertRaisesRegex(NxwrightError, "does not match its picture"):
                ProjectWriter(project, dump, folder / "out.HMI").write()


class RefusalTest(WriterTestCase):

    def assert_refused(self, message: str = ""):
        with self.assertRaisesRegex(NxwrightError, message):
            self.write()
        self.assertFalse(self.output.exists())

    def test_unchanged_dump_writes_nothing(self):
        self.assertEqual(self.write(), [])
        self.assertFalse(self.output.exists())

    def test_refuses_old_dump_format(self):
        summary = self.dump / "project.txt"
        summary.write_text(summary.read_text().split("\n", 1)[1])
        self.assert_refused("current format")

    def test_refuses_an_existing_file_that_is_no_project_file(self):
        # As a mistyped output, such as a file of the dump.
        edit_text(self.dump / "pages" / "01-second.txt", 'txt = "bye"', 'txt = "goodbye"')
        self.output.write_bytes(b"keep")
        with self.assertRaisesRegex(NxwrightError, "not a project file"):
            self.write()
        self.assertEqual(self.output.read_bytes(), b"keep")

    def test_refuses_directory_out_of_offset_order(self):
        container = HmiContainer.from_file(self.project)
        entries = list(container.entries)
        entries[0], entries[1] = entries[1], entries[0]
        data = bytearray(container.data)
        data[:len(encode_directory(entries))] = encode_directory(entries)
        self.project.write_bytes(bytes(data))
        self.assert_refused("offset order")

    def test_refuses_last_entry_not_at_end_of_file(self):
        self.project.write_bytes(self.project.read_bytes() + b"extra")
        self.assert_refused("end of the file")


class ReplacingTest(WriterTestCase):
    """An existing project file at the output is replaced, but only once the
    new one is written in full and has passed its check. It is written
    beside the output first, as <name>.<random>.partial."""

    def setUp(self):
        super().setUp()
        edit_text(self.dump / "pages" / "01-second.txt", 'txt = "bye"', 'txt = "goodbye"')
        self.before = self.project.read_bytes()

    def assert_nothing_partial_left(self):
        self.assertEqual(list(self.folder.glob("*.partial")), [])

    def test_replaces_an_existing_project_file(self):
        self.output.write_bytes(self.before)
        self.assertTrue(self.write())
        self.written()
        self.assertNotEqual(self.output.read_bytes(), self.before)
        self.assert_nothing_partial_left()

    def test_writes_over_its_own_project(self):
        # The project is read in full before the new file replaces it.
        changes = ProjectWriter(self.project, self.dump, self.project).write()
        self.assertTrue(changes)
        self.assertTrue(HmiContainer.from_file(self.project).directory_checksum_is_valid())
        self.assertNotEqual(self.project.read_bytes(), self.before)
        self.assert_nothing_partial_left()

    def test_a_write_that_fails_its_check_leaves_the_existing_file(self):
        self.output.write_bytes(self.before)
        with mock.patch.object(project_writer, "_check_written",
                               side_effect=NxwrightError("the written file is wrong")), \
                self.assertRaisesRegex(NxwrightError, "the written file is wrong"):
            self.write()
        self.assertEqual(self.output.read_bytes(), self.before)
        self.assert_nothing_partial_left()

    def test_a_write_that_fails_midway_leaves_the_existing_file(self):
        self.output.write_bytes(self.before)
        with mock.patch.object(Path, "write_bytes", side_effect=OSError("the disk is full")), \
                self.assertRaisesRegex(NxwrightError, "the disk is full"):
            self.write()
        self.assertEqual(self.output.read_bytes(), self.before)
        self.assert_nothing_partial_left()


class DamagedProjectTest(unittest.TestCase):

    def test_refuses_manifest_missing_a_page(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            blocks = [("main.HMI", stamped_manifest("0.pa"), 0), ("Program.s", b"", 0),
                      ("0.pa", small_page("first", b"a"), 0),
                      ("1.pa", small_page("second", b"b"), 0)]
            project = folder / "project.HMI"
            project.write_bytes(build_project(blocks, editor_layout=True))
            with self.assertRaisesRegex(NxwrightError, "manifest"):
                ProjectWriter(project, folder / "dump", folder / "out.HMI").write()


class FullDirectoryTest(unittest.TestCase):

    def test_refuses_directory_that_would_not_fit(self):
        # 18,724 entries are the most that fit below the directory's copy, and
        # the small project has 10 blocks. Replacing a page adds one entry more.
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            project = write_small_project(folder, stale_entries=18724 - 10)
            dump = folder / "dump"
            ProjectDumper(project, dump).dump()
            edit_text(dump / "pages" / "00-first.txt", 'txt = "hello"', 'txt = "hi"')
            with self.assertRaisesRegex(NxwrightError, "no longer fit"):
                ProjectWriter(project, dump, folder / "out.HMI").write()
            self.assertFalse((folder / "out.HMI").exists())


if __name__ == "__main__":
    unittest.main()
