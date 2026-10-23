"""Component defaults, the attributes and events a newly added component of each
type has: page files leave them out, the build fills them back in, and defaults
are read from a sample project and written to TOML."""
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.source.project_files import build
from nxwright.project.dumper import ProjectDumper
from nxwright import NxwrightError
from nxwright.project.component_defaults import (DEFAULTS_FILE, TypeDefaults, defaults_from_pages,
                                                 defaults_from_toml, defaults_to_toml)
from nxwright.project.page_block import Attribute, Event, Marker
from nxwright.source.page_source import PageSource, page_from_source, page_to_source
from nxwright.project.page_text import page_from_text
from nxwright.language.resource_names import ResourceNames
from nxwright.source.source_folder import export_dump, import_dump
from tests.test_project_writer import edit_text, small_page, write_small_project
from tests.test_source_folder import _dump_text

NAMES = ResourceNames([], [])
# Defaults for type 121, the page, that match page() as it is by default, so
# that its page file leaves them all out. Type, id, and objname are never defaults.
PAGE_DEFAULTS = {121: TypeDefaults([("vscope", b"\0"), ("txt", b"hello")], ["down", "up"])}


def page(events=("down", "up"), vscope=b"\0", text=b"hello"):
    """Returns the small test page with the given events, and `vscope` and `text`
    as its vscope and txt."""
    block = page_from_text(_dump_text(small_page("first", text)))
    items = block.objects[0].items
    items[4] = Attribute("vscope", vscope)
    items += [Event(name, []) for name in events]
    return block


class LeaveOutTest(unittest.TestCase):

    def round_trip(self, block) -> str:
        source = page_to_source(block, NAMES, PAGE_DEFAULTS)
        self.assertEqual(page_from_source(source, "first", NAMES, PAGE_DEFAULTS), block)
        return source.toml

    def test_defaults_are_left_out(self):
        toml = self.round_trip(page())
        self.assertNotIn("vscope", toml)
        self.assertNotIn("txt", toml)
        self.assertNotIn("events", toml)

    def test_non_default_values_and_events_are_written(self):
        toml = self.round_trip(page(events=("down",), vscope=b"\1"))
        self.assertIn("vscope = 1", toml)
        self.assertEqual(tomllib.loads(toml)["page"]["events"], ["down"])
        self.assertNotIn("txt", toml)

    def test_type_without_defaults_is_written_in_full(self):
        source = page_to_source(page(), NAMES, {})
        self.assertIn("defaults = false", source.toml)
        self.assertIn("vscope = 0", source.toml)
        self.assertEqual(page_from_source(source, "first", NAMES, {}), page())

    def test_different_attribute_lists_are_written_in_full(self):
        # One page has an attribute the defaults lack; the other has vscope and
        # txt swapped. Neither matches the defaults' list of attributes.
        extra = page()
        extra.objects[0].items.insert(6, Attribute("pco", b"\0\0"))
        extra.objects[0].items[0] = Marker(b"att-6")
        swapped = page()
        items = swapped.objects[0].items
        items[4], items[5] = items[5], items[4]
        for block in (extra, swapped):
            with self.subTest(attributes=[item.name for item in block.objects[0].items
                                          if isinstance(item, Attribute)]):
                self.assertIn("defaults = false", self.round_trip(block))

    def test_build_refusals(self):
        toml = page_to_source(page(), NAMES, PAGE_DEFAULTS).toml
        cases = {
            "type page has no attribute pco": (toml + "pco = 0\n", PAGE_DEFAULTS),
            "has no defaults": (toml, {}),
        }
        for message, (text, defaults) in cases.items():
            with self.subTest(message=message):
                with self.assertRaisesRegex(NxwrightError, message):
                    page_from_source(PageSource(text, ""), "first", NAMES, defaults)


class DefaultsFileTest(unittest.TestCase):

    def test_attributes_that_are_not_a_table_are_refused(self):
        with self.assertRaisesRegex(NxwrightError, "test: \\[text\\] attributes must be a table"):
            defaults_from_toml("[text]\nevents = []\nattributes = 1\n", "test")

    def test_a_text_past_u00ff_is_refused(self):
        # The file gives each byte of a text as a character from U+0000 to
        # U+00FF, so another character is no byte; so in the text form of a
        # scrolling text's dir.
        for text, where in (('[text]\nevents = []\n\n[text.attributes]\ntxt = "\\u20ac"\n',
                             r"\[text\.attributes\] txt holds U\+20AC"),
                            ('[scrolling-text]\nevents = []\n\n[scrolling-text.attributes]\n'
                             'dir = "\\u0100"\n',
                             r"\[scrolling-text\.attributes\] dir holds U\+0100")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(NxwrightError, "test: " + where):
                    defaults_from_toml(text, "test")

    def test_toml_round_trip(self):
        defaults = {116: TypeDefaults([("vscope", b"\0"), ("pco", b"\x1f\x00"), ("txt", b"newtxt")],
                                      ["down", "up"])}
        text = defaults_to_toml(defaults, "a header\nsecond line")
        self.assertTrue(text.startswith("# a header\n# second line\n"))
        self.assertEqual(defaults_from_toml(text, "test"), defaults)

    def test_four_byte_values_are_written_signed(self):
        # A file browser's val, 0xFFFFFFFF, as the Editor's panel shows it.
        defaults = {65: TypeDefaults([("val", b"\xff\xff\xff\xff")], [])}
        text = defaults_to_toml(defaults, "a header")
        self.assertIn("val = -1\n", text)
        self.assertEqual(defaults_from_toml(text, "test"), defaults)
        self.assertEqual(defaults_from_toml(text.replace("val = -1", "val = 4294967295"), "test"),
                         defaults)

    def test_disagreeing_components_of_one_type_are_refused(self):
        first, second = page(), page(vscope=b"\1")
        with self.assertRaisesRegex(NxwrightError, "two components of type page that differ"):
            defaults_from_pages([first, second])

class SourceFolderDefaultsTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.project = write_small_project(self.folder)
        self.dump = self.folder / "dump"
        ProjectDumper(self.project, self.dump).dump()
        self.source = self.folder / "source"
        import_dump(self.dump, self.source)

    def tearDown(self):
        self._folder.cleanup()

    def test_build_reads_the_folders_own_copy(self):
        self.assertEqual((self.source / "defaults.toml").read_bytes(), DEFAULTS_FILE.read_bytes())
        # A copy fitted to the small test page, which leaves vscope out: the
        # build must fill it in from this copy, not from the tool's defaults.
        (self.source / "defaults.toml").write_text(
            '[page]\nevents = []\n\n[page.attributes]\nvscope = 1\ntxt = "hello"\n',
            encoding="utf-8", newline="\n")
        page_file = self.source / "pages" / "first.page.toml"
        edit_text(page_file, "defaults = false\n", "")
        edit_text(page_file, "vscope = 0\n", "")
        output = self.folder / "out.HMI"
        build(self.source, output)
        ProjectDumper(output, self.folder / "out-dump").dump()
        self.assertIn("vscope = 1", (self.folder / "out-dump" / "pages" / "00-first.txt")
                      .read_text(encoding="utf-8"))

    def test_folder_without_defaults_is_refused(self):
        (self.source / "defaults.toml").unlink()
        with self.assertRaisesRegex(NxwrightError, "defaults.toml is missing"):
            export_dump(self.source, self.folder / "again")


if __name__ == "__main__":
    unittest.main()
