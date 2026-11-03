"""A picture's source: the file a picture had before it was resized in the
Nextion Editor's picture viewer, which the Editor keeps in a block N.ib,
beside the picture's file (N.is) and its screen copy (N.i), in the layout
of an N.is block (ResearchNotes/format.md, Pictures). Extract writes it
beside the picture's file, as pictures/<name>.source<suffix>, and the build
writes it back."""
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.project.container import HmiContainer
from nxwright.project.dumper import ProjectDumper
from nxwright.project.pictures import write_png
from nxwright.project.resources import ImageSource, encode_image_source, parse_manifest
from nxwright.source.lint import ERROR, Finding
from nxwright.source.project_files import build, extract
from nxwright.source.resource_adding import add_pictures
from nxwright.source.resource_removal import remove_resource_files
from nxwright.source.unknown_content import UnknownContentError
from tests.test_container import build_project
from tests.test_extract_unknown import PatchedDemoTestCase
from tests.test_picture_files import SourceFolderTestCase
from tests.test_project_writer import WriterTestCase

# A picture's source, as the Editor keeps it: a PNG of 40 by 20, larger than
# the picture it was resized to, and its block.
SOURCE = write_png(40, 20, bytes(range(256)) * 12 + bytes(128))
SOURCE_BLOCK = encode_image_source(ImageSource(40, 20, SOURCE, ".png"))
# Another source, of the same size.
OTHER_SOURCE = write_png(40, 20, bytes(40 * 20 * 4))


def first_picture_block(project: Path) -> str:
    """Returns the name of the screen copy's block of the project's
    picture 0, such as "0.i"."""
    blocks = HmiContainer.from_file(project).blocks
    return parse_manifest(blocks["main.HMI"]).block_names("i")[0]


class ExtractTest(PatchedDemoTestCase):
    """Extract keeps a picture's source, and the build writes it back."""

    def setUp(self):
        self.source_block = first_picture_block(self.demo) + "b"
        self.resized = self.patched("resized.HMI", blocks={self.source_block: SOURCE_BLOCK})

    def test_extract_writes_it_beside_its_picture_and_asks_nothing(self):
        messages = extract(self.resized, self.target("resized"))
        pictures = self.target("resized") / "pictures"
        self.assertEqual((pictures / "picture-0000.source.png").read_bytes(), SOURCE)
        self.assertTrue((pictures / "picture-0000.png").is_file())
        self.assertFalse(any(self.source_block in message for message in messages))

    def test_extract_then_build_gives_back_its_block(self):
        extract(self.resized, self.target("again"))
        build(self.target("again"), self.folder / "again.HMI")
        self.assertEqual(HmiContainer.from_file(self.folder / "again.HMI").blocks
                         [self.source_block], SOURCE_BLOCK)

    def test_an_update_deletes_a_source_the_project_no_longer_has(self):
        extract(self.resized, self.target("updated"))
        extract(self.demo, self.target("updated"))
        pictures = self.target("updated") / "pictures"
        self.assertFalse((pictures / "picture-0000.source.png").exists())
        self.assertTrue((pictures / "picture-0000.png").is_file())

    def test_a_source_without_its_picture_may_be_lost(self):
        project = self.patched("alone.HMI", blocks={"99.ib": SOURCE_BLOCK})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("alone"))
        self.assertIn("a picture's source the build leaves out (block 99.ib)",
                      str(raised.exception))
        extract(project, self.target("alone"), continue_with_unknown=True)
        self.assertEqual(sorted((self.target("alone") / "pictures").glob("*.source.*")), [])

    def test_a_source_nxwright_cannot_read_may_be_lost(self):
        project = self.patched("unread.HMI", blocks={self.source_block: b"?"})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("unread"))
        self.assertIn("a picture's source the build leaves out (block %s)" % self.source_block,
                      str(raised.exception))

    def test_a_source_whose_header_differs_gets_the_builds(self):
        header = bytearray(SOURCE_BLOCK)
        header[4] = 1
        project = self.patched("header.HMI", blocks={self.source_block: bytes(header)})
        with self.assertRaises(UnknownContentError) as raised:
            extract(project, self.target("header"))
        self.assertIn("a picture's header that differs from the build's (block %s)"
                      % self.source_block, str(raised.exception))
        extract(project, self.target("header"), continue_with_unknown=True)
        build(self.target("header"), self.folder / "header-again.HMI")
        self.assertEqual(HmiContainer.from_file(self.folder / "header-again.HMI").blocks
                         [self.source_block], SOURCE_BLOCK)


class SourceFileTest(SourceFolderTestCase):
    """A source folder's source files, in the build and in its checks."""

    def setUp(self):
        super().setUp()
        self.picture(".png", write_png(20, 10, bytes(20 * 10 * 4)))

    def source_file(self, suffix: str, content: bytes):
        (self.source / "pictures" / ("photo.source" + suffix)).write_bytes(content)

    def test_the_build_writes_it_as_the_pictures_source_block(self):
        self.assertNotIn("0.ib", self.built().blocks)
        self.source_file(".png", SOURCE)
        self.assertEqual(self.built().blocks["0.ib"], SOURCE_BLOCK)

    def test_two_source_files_of_one_picture_are_refused(self):
        self.source_file(".png", SOURCE)
        self.source_file(".jpg", SOURCE)
        two = ("pictures/photo.source.png and pictures/photo.source.jpg exist; a picture can "
               "have only one source file")
        with self.assertRaisesRegex(NxwrightError, two):
            self.built()
        self.assertIn(Finding("app.toml", self.photo_line(), ERROR, two), self.findings())

    def test_a_source_file_nxwright_cannot_read_is_refused(self):
        self.source_file(".png", b"not a png")
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line, finding.severity),
                         ("app.toml", self.photo_line(), ERROR))
        self.assertTrue(finding.message.startswith("pictures/photo.source.png: not a picture "
                                                   "nxwright reads"))
        with self.assertRaises(NxwrightError) as raised:
            self.built()
        self.assertEqual(str(raised.exception), finding.message)

    def test_removing_the_picture_deletes_its_source_file(self):
        self.source_file(".png", SOURCE)
        removed, left = remove_resource_files(self.source, "pictures", "photo")
        self.assertEqual((sorted(removed), left),
                         (["pictures/photo.png", "pictures/photo.source.png"], []))

    def test_a_new_picture_whose_source_file_is_there_is_refused(self):
        (self.source / "pictures" / "icon.source.png").write_bytes(SOURCE)
        added = self.folder / "icon.png"
        added.write_bytes(write_png(4, 4, bytes(4 * 4 * 4)))
        with self.assertRaisesRegex(NxwrightError, "icon.source.png is already there, though "
                                                   "app.toml does not list it"):
            add_pictures(self.source, [added])


class WriteTest(WriterTestCase):
    """`nxwright write` writes a dump's source files into a project
    (project_writer.py), and keeps its N.ib blocks in step with them."""

    def setUp(self):
        super().setUp()
        self.picture_block = parse_manifest(HmiContainer.from_file(self.project)
                                            .blocks["main.HMI"]).block_names("i")[-1]
        self.last = len(list((self.dump / "images").glob("*.i"))) - 1

    def source_path(self) -> Path:
        return self.dump / "images" / ("%04d.source.png" % self.last)

    def resized(self) -> HmiContainer:
        """Writes the project with a source for its last picture, then makes
        that the project, and dumps it again."""
        self.source_path().write_bytes(SOURCE)
        self.write()
        written = self.written()
        self.project, self.output = self.output, self.folder / "again.HMI"
        self.dump = self.folder / "dump-again"
        ProjectDumper(self.project, self.dump).dump()
        return written

    def test_a_dumps_source_is_written_as_its_pictures_source_block(self):
        self.assertEqual(self.resized().blocks[self.picture_block + "b"], SOURCE_BLOCK)

    def test_an_unchanged_source_changes_nothing(self):
        self.resized()
        self.assertEqual(self.write(), [])

    def test_a_changed_source_replaces_its_block(self):
        self.resized()
        self.source_path().write_bytes(OTHER_SOURCE)
        self.write()
        self.assertEqual(self.written().blocks[self.picture_block + "b"],
                         encode_image_source(ImageSource(40, 20, OTHER_SOURCE, ".png")))

    def test_a_source_gone_from_the_dump_removes_its_block(self):
        self.resized()
        self.source_path().unlink()
        self.write()
        self.assertNotIn(self.picture_block + "b", self.written().blocks)

    def test_a_removed_picture_takes_its_source_with_it(self):
        self.resized()
        self.source_path().unlink()
        for path in (self.dump / "images").glob("%04d.*" % self.last):
            path.unlink()
        self.write()
        blocks = self.written().blocks
        for extension in ("", "s", "b"):
            self.assertNotIn(self.picture_block + extension, blocks)

    def test_a_new_picture_does_not_take_the_number_of_an_orphan_source(self):
        # A source block whose picture the manifest does not list, which the
        # dump leaves out, keeps its number: a new picture takes the next one.
        blocks = HmiContainer.from_file(self.project).blocks
        orphan = "%d.ib" % (max(int(name.split(".")[0]) for name in blocks
                                if name.endswith((".i", ".is"))) + 1)
        self.project = self.folder / "orphan.HMI"
        self.project.write_bytes(build_project(
            [(name, data, 0) for name, data in {**blocks, orphan: SOURCE_BLOCK}.items()],
            editor_layout=True))
        self.dump = self.folder / "dump-orphan"
        ProjectDumper(self.project, self.dump, leave_out_unknown_blocks=True).dump()
        (self.dump / "images" / ("%04d.png" % (self.last + 1))).write_bytes(OTHER_SOURCE)
        changes = self.write()
        self.assertFalse([change for change in changes if "the source of" in change], changes)
        self.assertEqual(self.written().blocks[orphan], SOURCE_BLOCK)

    def test_a_dump_in_format_3_is_refused(self):
        summary = self.dump / "project.txt"
        lines = summary.read_text(encoding="utf-8").split("\n")
        summary.write_text("\n".join(["dump format        3"] + lines[1:]), encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "is not a dump in the current format"):
            self.write()


if __name__ == "__main__":
    unittest.main()
