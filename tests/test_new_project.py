"""Writing a project file from a dump, with no existing project."""
from pathlib import Path
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.project.container import DIRECTORY_COPY_OFFSET, HmiContainer
from nxwright.project.device_settings import DeviceSettings, read_device_settings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.new_project import BLOCKS_START, write_new_project
from nxwright.project.pictures import read_picture
from nxwright.project.resources import parse_image_source, parse_manifest
from nxwright.project.screen_copy import (FORMAT_RAW_WITH_HEADER, decode_screen_copy,
                                          matches_within_editor_rounding, screen_copy_format)
from nxwright.project.screen_models import model_named
from nxwright.project.stamp import stamp_number
from tests.test_project_writer import MACROS, edit_text, write_small_project


def _dump_files(dump: Path) -> dict:
    """The parts of a dump that a project written anew keeps: everything but
    project.txt, which shows block names and the header, and the screen copies
    with their index, which shows their checksums: they are generated again."""
    return {path.relative_to(dump): path.read_bytes() for path in dump.rglob("*")
            if path.is_file() and path.name != "project.txt" and path.suffix != ".i"
            and path.relative_to(dump).as_posix() != "images/index.txt"}


class NewProjectTest(unittest.TestCase):
    """The small test project, dumped, then written anew for a screen model."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.dump = self.folder / "dump"
        ProjectDumper(write_small_project(self.folder), self.dump).dump()

    def tearDown(self):
        self._folder.cleanup()

    def write(self, settings: DeviceSettings, name: str = "new.HMI") -> Path:
        output = self.folder / name
        write_new_project(self.dump, settings, output)
        return output

    def test_holds_what_the_dump_holds(self):
        settings = DeviceSettings(model_named("NX8048P050"), 90, "utf-8", one_time_update=True)
        # Each page's header repeats the encoding: utf-8 is 24 (0x18).
        for path in (self.dump / "pages").glob("*.txt"):
            edit_text(path, "header_40 = 01440203", "header_40 = 01440218")
        output = self.write(settings)
        ProjectDumper(output, self.folder / "again").dump()
        self.assertEqual(_dump_files(self.folder / "again"), _dump_files(self.dump))
        manifest = HmiContainer.from_file(output).blocks["main.HMI"]
        self.assertEqual(read_device_settings(manifest), settings)
        self.assertEqual(stamp_number(manifest), settings.model.stamp_number)

    def test_keeps_the_macros(self):
        (self.dump / "macros.s").write_bytes(MACROS)
        output = self.write(DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1"))
        self.assertEqual(HmiContainer.from_file(output).blocks["comcode.sn"], MACROS)
        ProjectDumper(output, self.folder / "again").dump()
        self.assertEqual((self.folder / "again" / "macros.s").read_bytes(), MACROS)

    def test_is_laid_out_as_the_editor_lays_out_a_new_project(self):
        data = self.write(DeviceSettings(model_named("NX3224T024"), 0, "iso-8859-1")).read_bytes()
        container = HmiContainer(data)
        self.assertTrue(container.directory_checksum_is_valid())
        directory_size = 4 + 28 * container.entry_count + 4
        self.assertEqual(data[DIRECTORY_COPY_OFFSET:DIRECTORY_COPY_OFFSET + directory_size],
                         data[:directory_size])
        self.assertEqual(data[0x380000:0x380004], b"\xff" * 4)
        self.assertEqual(data[0x6ffff8:BLOCKS_START], b"ver21234")
        self.assertEqual(container.entries[0].offset, BLOCKS_START)
        self.assertEqual([entry.name for entry in container.entries][0], "Program.s")
        self.assertEqual(container.entries[-1].name, "main.HMI")
        # The Editor's order in the manifest: pictures, fonts, then pages.
        kinds = [kind for kind, _ in parse_manifest(container.blocks["main.HMI"]).resources]
        self.assertEqual(kinds, sorted(kinds, key=["i", "zi", "pa"].index))

    def test_screen_copies_follow_the_series_and_rotation(self):
        for model, rotation in (("NX4832T035", 270), ("NX3224F024", 90), ("NX8048P050", 180),
                                ("NX4848E021", 0)):
            with self.subTest(model=model, rotation=rotation):
                settings = DeviceSettings(model_named(model), rotation, "iso-8859-1")
                container = HmiContainer.from_file(self.write(settings, model + ".HMI"))
                kind = settings.model.picture_format
                for name in parse_manifest(container.blocks["main.HMI"]).block_names("i"):
                    block = container.blocks[name]
                    self.assertEqual(screen_copy_format(block), kind)
                    order = 0 if kind == FORMAT_RAW_WITH_HEADER else rotation
                    png = parse_image_source(container.blocks[name + "s"]).data
                    self.assertTrue(matches_within_editor_rounding(
                        decode_screen_copy(block, order), read_picture(png), kind))

    def test_the_same_dump_gives_the_same_file(self):
        settings = DeviceSettings(model_named("NX8048K050"), 0, "iso-8859-1")
        self.assertEqual(self.write(settings, "one.HMI").read_bytes(),
                         self.write(settings, "two.HMI").read_bytes())

    def test_an_existing_output_is_refused(self):
        output = self.folder / "taken.HMI"
        output.write_bytes(b"keep")
        with self.assertRaisesRegex(NxwrightError, "already exists"):
            write_new_project(self.dump, DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1"),
                              output)
        self.assertEqual(output.read_bytes(), b"keep")

    def test_pages_must_be_numbered_without_gaps(self):
        next(iter((self.dump / "pages").glob("00-*.txt"))).unlink()
        with self.assertRaisesRegex(NxwrightError, "page IDs must run from 0 without gaps: it "
                                                   "has no page 0$"):
            self.write(DeviceSettings(model_named("NX8048P050"), 0, "iso-8859-1"))


if __name__ == "__main__":
    unittest.main()
