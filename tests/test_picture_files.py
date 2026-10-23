"""Picture files in projects. The Editor keeps a picture's file as it is
given, a PNG, a JPEG, a BMP, or a GIF, whatever its suffix says of it, and
its record names the suffix the file had, lower-cased; the picture's screen
copy is made from the file's pixels.

Two probes (Editor 3.1.73) added pictures through the Editor's Picture panel
to new projects:
  - tests/fixtures/pictures/jpeg/: three JPEG pictures of 160 by 96 added
    to an NX8048K050 project, whose screen copies are raw, and to an
    NX8048P050, whose screen copies are compressed. baseline.jpg is a
    baseline JPEG, and progressive.jpg a progressive one; oriented.jpg
    holds baseline.jpg's pixels with an EXIF orientation of 6, which the
    Editor did not apply. For each, <name>.is is the Editor's record of it,
    the same in both projects, and <name>.raw.i and <name>.compressed.i its
    screen copies.
  - tests/fixtures/pictures/tags/: Logo.PNG, photo.jpeg (baseline.jpg's
    bytes), plain.bmp, and still.gif, added to an NX8048K050 project, as
    <name>-<suffix>.is, the Editor's records of them, and the BMP's and the
    GIF's screen copies, <name>-<suffix>.raw.i.
"""
import base64
from pathlib import Path
import struct
import tempfile
import unittest

from PIL import Image

from nxwright import NxwrightError
from nxwright.source.definitions import definitions
from nxwright.language_server.file_texts import FileTexts
from nxwright.source.folder_index import FolderIndex, file_start
from nxwright.testing.preview import Previews
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.picture_cache import make_screen_copy
from nxwright.project.pictures import read_picture, write_png
from nxwright.project.resources import ImageSource, encode_image_source, parse_image_source
from nxwright.project.screen_copy import FORMAT_COMPRESSED, FORMAT_RAW, decode_screen_copy
from nxwright.project.screen_models import model_named
from nxwright.source.folder_check import check_folder
from nxwright.source.lint import ERROR, Finding
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import (folder_byte_reader, folder_reader, new_source_folder,
                                           picture_file)
from tests.test_folder_check import edited_app, edited_page_file
from tests.test_pictures import png_bytes
from tests.test_project_writer import WriterTestCase

PICTURES = Path(__file__).resolve().parent / "fixtures" / "pictures"
JPEGS = ("baseline", "progressive", "oriented")
# The tags probe's records, by their fixtures' names, with the suffix each
# file was added with, as the record names it.
TAGGED = {"Logo-PNG": ".png", "photo-jpeg": ".jpeg", "plain-bmp": ".bmp",
          "still-gif": ".gif"}
# An Enhanced screen, whose screen copies are raw.
RAW_SCREEN = DeviceSettings(model_named("NX8048K050"), 0, "iso-8859-1")


def jpeg(name: str) -> bytes:
    return (PICTURES / "jpeg" / name).read_bytes()


def tagged(name: str) -> bytes:
    return (PICTURES / "tags" / name).read_bytes()


class RecordTest(unittest.TestCase):

    def test_the_editors_records_are_read_and_written_again(self):
        for name in JPEGS:
            with self.subTest(name):
                record = jpeg(name + ".is")
                source = parse_image_source(record)
                self.assertEqual((source.width, source.height, source.suffix, source.data),
                                 (160, 96, ".jpg", jpeg(name + ".jpg")))
                self.assertEqual(encode_image_source(source), record)
        for name, suffix in TAGGED.items():
            with self.subTest(name):
                record = tagged(name + ".is")
                source = parse_image_source(record)
                # The header ends with the suffix: photo.jpeg's takes a byte more.
                header_size, = struct.unpack_from("<I", record, 8)
                self.assertEqual((source.suffix, header_size), (suffix, 23 + len(suffix)))
                self.assertEqual(encode_image_source(source), record)

    def test_the_file_is_kept_whatever_its_suffix_says(self):
        # As the Editor keeps a JPEG file added as photo.jpeg: its bytes are
        # baseline.jpg's.
        self.assertEqual(parse_image_source(tagged("photo-jpeg.is")).data, jpeg("baseline.jpg"))
        source = ImageSource(160, 96, jpeg("baseline.jpg"), ".png")
        self.assertEqual(parse_image_source(encode_image_source(source)), source)

    def test_a_suffix_nxwright_does_not_keep_is_refused(self):
        record = encode_image_source(ImageSource(160, 96, jpeg("baseline.jpg"), ".tif"))
        with self.assertRaisesRegex(NxwrightError, "image record of a .tif file; nxwright keeps "
                                                   ".png, .jpg, .jpeg, .bmp, .gif files"):
            parse_image_source(record)


class ScreenCopyTest(unittest.TestCase):

    def test_the_editors_pixel_for_pixel(self):
        for name in JPEGS:
            with self.subTest(name):
                data = jpeg(name + ".jpg")
                # Raw, the Editor's own bytes.
                self.assertEqual(make_screen_copy(data, FORMAT_RAW, 0).block,
                                 jpeg(name + ".raw.i"))
                # Compressed, the Editor's pixels, coded in nxwright's own
                # runs, as for a PNG.
                made = make_screen_copy(data, FORMAT_COMPRESSED, 0).block
                self.assertEqual(decode_screen_copy(made, 0),
                                 decode_screen_copy(jpeg(name + ".compressed.i"), 0))
        for name in ("plain-bmp", "still-gif"):
            with self.subTest(name):
                data = parse_image_source(tagged(name + ".is")).data
                self.assertEqual(make_screen_copy(data, FORMAT_RAW, 0).block,
                                 tagged(name + ".raw.i"))


class DumpTest(WriterTestCase):
    """A JPEG picture added to a dump, and written into its project by
    `nxwright write` (project_writer.py)."""

    def test_its_record_is_the_editors_and_dumps_back(self):
        (self.dump / "images" / "0002.jpg").write_bytes(jpeg("baseline.jpg"))
        self.assertEqual(self.write(), ["Added picture 2 as block 2.i",
                                        "Rewrote the manifest (7 resources)"])
        self.assertEqual(self.written().blocks["2.is"], jpeg("baseline.is"))
        ProjectDumper(self.output, self.folder / "again").dump()
        self.assertEqual((self.folder / "again" / "images" / "0002.jpg").read_bytes(),
                         jpeg("baseline.jpg"))

    def test_a_picture_whose_suffix_changed_is_written_again(self):
        # Its bytes alone are the same: the record names its suffix.
        images = self.dump / "images"
        (images / "0001.png").rename(images / "0001.bmp")
        self.assertIn("Added picture 1 as block 2.i", self.write())
        self.assertEqual(parse_image_source(self.written().blocks["2.is"]).suffix, ".bmp")

    def test_an_id_with_two_files_is_refused(self):
        (self.dump / "images" / "0001.jpg").write_bytes(jpeg("baseline.jpg"))
        with self.assertRaisesRegex(NxwrightError, "images/0001.png and images/0001.jpg are "
                                                   "there; a picture has one file"):
            self.write()
        self.assertFalse(self.output.exists())


class SourceFolderTestCase(unittest.TestCase):
    """A new source folder for an NX8048K050, whose app.toml lists the
    picture "photo", and whose page shows it."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "source"
        new_source_folder(self.source, RAW_SCREEN, "nextion")
        (self.source / "pictures").mkdir()
        self.edit_app(lambda app: app.update(pictures=["photo"]))
        page = self.source / "pages" / "page0.page.toml"
        page.write_text(edited_page_file(page.read_text(encoding="utf-8"),
                                         lambda tables: tables[0].update(sta=2, pic="photo")),
                        encoding="utf-8", newline="\n")

    def tearDown(self):
        self._folder.cleanup()

    def edit_app(self, edit):
        app = self.source / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"), edit), encoding="utf-8",
                       newline="\n")

    def picture(self, suffix: str, content: bytes):
        (self.source / "pictures" / ("photo" + suffix)).write_bytes(content)

    def built(self, name: str = "built.HMI") -> HmiContainer:
        build(self.source, self.folder / name)
        return HmiContainer.from_file(self.folder / name)

    def findings(self) -> list:
        return check_folder(folder_reader(self.source),
                            lambda path: (self.source / path).is_file(), None,
                            folder_byte_reader(self.source)).folder_findings

    def photo_line(self) -> int:
        """The line of app.toml that lists the picture."""
        lines = (self.source / "app.toml").read_text(encoding="utf-8").split("\n")
        return lines.index('    "photo",') + 1


class SourceFolderTest(SourceFolderTestCase):

    def test_a_picture_builds_as_the_editor_keeps_it(self):
        for suffix, record, copy in ((".jpg", jpeg("baseline.is"), jpeg("baseline.raw.i")),
                                     (".jpeg", tagged("photo-jpeg.is"), jpeg("baseline.raw.i")),
                                     (".bmp", tagged("plain-bmp.is"), tagged("plain-bmp.raw.i"))):
            with self.subTest(suffix):
                for old in (self.source / "pictures").iterdir():
                    old.unlink()
                self.picture(suffix, parse_image_source(record).data)
                project = self.built()
                self.assertEqual(project.blocks_with_extension("is"), {0: record})
                self.assertEqual(project.blocks_with_extension("i"), {0: copy})

    def test_a_jpeg_under_a_pngs_name_is_kept_so(self):
        self.picture(".png", jpeg("baseline.jpg"))
        self.assertEqual(self.built().blocks["0.is"],
                         encode_image_source(ImageSource(160, 96, jpeg("baseline.jpg"), ".png")))

    def test_it_extracts_with_its_suffix_and_builds_back(self):
        self.picture(".jpeg", jpeg("progressive.jpg"))
        built = self.built().blocks
        again = self.folder / "again"
        extract(self.folder / "built.HMI", again)
        (picture,) = (again / "pictures").iterdir()
        self.assertEqual((picture.suffix, picture.read_bytes()),
                         (".jpeg", jpeg("progressive.jpg")))
        build(again, self.folder / "again.HMI")
        self.assertEqual(HmiContainer.from_file(self.folder / "again.HMI").blocks, built)

    def test_a_picture_whose_suffix_changed_loses_its_old_file(self):
        self.picture(".png", write_png(160, 96, bytes(160 * 96 * 4)))
        self.built("png.HMI")
        jpeg_folder = self.folder / "jpeg"
        extract(self.folder / "png.HMI", jpeg_folder)
        (picture,) = (jpeg_folder / "pictures").iterdir()
        picture.unlink()
        (jpeg_folder / "pictures" / (picture.stem + ".jpg")).write_bytes(jpeg("baseline.jpg"))
        build(jpeg_folder, self.folder / "jpeg.HMI")
        # Extracted over the folder of the PNG, the JPEG keeps its name.
        extract(self.folder / "jpeg.HMI", self.source)
        self.assertEqual(sorted(path.name for path in (self.source / "pictures").iterdir()),
                         ["photo.jpg"])

    def test_a_picture_of_two_files_is_refused(self):
        self.picture(".png", write_png(160, 96, bytes(160 * 96 * 4)))
        self.picture(".jpg", jpeg("baseline.jpg"))
        two = "pictures/photo.png and pictures/photo.jpg are there; a picture has one file"
        with self.assertRaisesRegex(NxwrightError, two):
            self.built()
        self.assertIn(Finding("app.toml", self.photo_line(), ERROR, two), self.findings())

    def test_a_picture_with_no_file_is_named_by_each_suffix(self):
        missing = "pictures/photo.png, .jpg, .jpeg, .bmp, or .gif is missing"
        with self.assertRaisesRegex(NxwrightError, missing):
            self.built()
        self.assertIn(Finding("app.toml", self.photo_line(), ERROR, missing), self.findings())


class UnreadablePictureTest(SourceFolderTestCase):
    """A picture file nxwright cannot read, named by the folder's own file, in
    the checks and in the build, in nxwright's own words."""

    def test_what_opening_it_finds(self):
        keyed = png_bytes(1, 1, 2, [[0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC]],
                          ((b"tRNS", bytes([0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC])),), depth=16)
        for content, words in ((b"not a png", "not a picture nxwright reads: no kind of "
                                              "picture Pillow knows"),
                               (keyed, "a PNG of 16 bits a channel, with a colour key")):
            with self.subTest(words):
                self.picture(".png", content)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line, finding.severity),
                                 ("app.toml", self.photo_line(), ERROR))
                self.assertTrue(finding.message.startswith("pictures/photo.png: " + words))
                with self.assertRaises(NxwrightError) as raised:
                    self.built()
                self.assertEqual(str(raised.exception), finding.message)
        # The checks a page alone gets read no picture.
        self.assertEqual(check_folder(folder_reader(self.source),
                                      lambda path: (self.source / path).is_file(),
                                      ["page0"]).folder_findings, [])

    def test_damaged_pixels(self):
        # A picture whose pixels alone are damaged opens, so the checks pass
        # it; the build finds it as it decodes it, naming the folder's file.
        self.picture(".png", png_bytes(16, 16, 2, [range(48)] * 16)[:-30])
        self.assertEqual(self.findings(), [])
        with self.assertRaisesRegex(NxwrightError, r"^pictures/photo\.png: not a picture "
                                                   r"nxwright reads"):
            self.built()


class ShowingTest(SourceFolderTestCase):
    """The preview and the language server find a JPEG picture's file, as
    the simulator does, through source_folder.picture_file."""

    def setUp(self):
        super().setUp()
        self.picture(".jpg", jpeg("baseline.jpg"))
        self.jpeg = self.source / "pictures" / "photo.jpg"

    def test_the_preview_loads_its_file_and_finds_its_size(self):
        drawing = Previews().drawing(self.source, "pages/page0.page.toml",
                                     folder_reader(self.source))
        self.assertEqual(drawing["pictureFiles"]["photo"]["path"], str(self.jpeg))
        # The page paints its picture only once it finds the picture's size,
        # and outlines it otherwise.
        self.assertEqual([shape["kind"] for shape in drawing["shapes"]], ["picture"])

    def test_an_oriented_jpeg_goes_as_its_pixels_unturned(self):
        # The Editor does not turn a JPEG by its EXIF orientation, where the
        # webview's browser would: the preview hands over the pixels as read.
        self.jpeg.write_bytes(jpeg("oriented.jpg"))
        drawing = Previews().drawing(self.source, "pages/page0.page.toml",
                                     folder_reader(self.source))
        file = drawing["pictureFiles"]["photo"]
        self.assertNotIn("path", file)
        prefix = "data:image/png;base64,"
        self.assertTrue(file["data"].startswith(prefix))
        shown = read_picture(base64.b64decode(file["data"][len(prefix):]))
        self.assertEqual((shown.size, shown.tobytes()),
                         ((160, 96), read_picture(jpeg("oriented.jpg")).tobytes()))

    def test_an_orientation_past_8_asks_for_nothing(self):
        exif = Image.Exif()
        exif[0x0112] = 9
        Image.new("RGB", (160, 96)).save(self.jpeg, "JPEG", exif=exif)
        drawing = Previews().drawing(self.source, "pages/page0.page.toml",
                                     folder_reader(self.source))
        self.assertEqual(drawing["pictureFiles"]["photo"]["path"], str(self.jpeg))

    def test_its_file_is_found(self):
        def exists(path: str) -> bool:
            return (self.source / path).is_file()
        self.assertEqual(picture_file("photo", exists), "pictures/photo.jpg")
        # A picture whose file is missing is named by its PNG file.
        self.assertEqual(picture_file("gone", exists), "pictures/gone.png")

    def test_a_definition_goes_to_its_file(self):
        index = FolderIndex(self.source, FileTexts().read)
        line = (self.source / "pages" / "page0.page.toml").read_text(
            encoding="utf-8").split("\n").index('pic = "photo"')
        self.assertEqual(definitions(index, "pages/page0.page.toml", line, len('pic = "p')),
                         [file_start("pictures/photo.jpg")])


if __name__ == "__main__":
    unittest.main()
