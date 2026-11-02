"""Components of names that are not plain, such as `b)0` or `b 0`, which
the Nextion Editor allows (ResearchNotes/object-names.md), or which a
project file may hold. Extract keeps them, and the build writes them back.
In a .nx file, the heading of such a component's event quotes its name:
`on "b 0".up:`. A name with a double quote or a control character cannot
be written in a heading, so it is refused."""
import json
from pathlib import Path
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.language_server.symbols import file_symbols
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_block import parse_page
from nxwright.project.page_text import escape_string
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.resources import parse_manifest
from nxwright.project.screen_models import model_named
from nxwright.source.definitions import definitions
from nxwright.source.folder_index import FolderIndex
from nxwright.source.nx_files import event_heading, read_event_heading
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import new_source_folder

SETTINGS = DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1")
# The names the buttons b0 to b6 take: the Editor allows the first three,
# and a project file may hold the others. The last stays plain.
NAMES = ["b)0", "b 0", "b0 ", "b.0", "b[0]", "b\\0", "b6"]


def page_block(project: Path) -> bytes:
    """Returns the block of the project's page 0."""
    blocks = HmiContainer.from_file(project).blocks
    return blocks[parse_manifest(blocks["main.HMI"]).block_names("pa")[0]]


def object_names(project: Path) -> list:
    """Returns the objname of each object of the project's page 0."""
    return [page_object.attribute("objname") for page_object in
            parse_page(page_block(project)).objects]


def write_buttons(folder: Path, names: list, headings: list = None):
    """Adds a button of each name of `names` to the folder's page0, each
    with Touch Release code, under the heading `headings` gives, by default
    the one event_heading writes."""
    page = folder / "pages" / "page0.page.toml"
    # A JSON string is a TOML string too, escapes and all.
    tables = "".join('\n[[component]]\nname = %s\ntype = "button"\nx = 10\ny = %d\n'
                     'w = 100\nh = 30\n' % (json.dumps(name), 10 + 40 * at)
                     for at, name in enumerate(names))
    page.write_text(page.read_text(encoding="utf-8") + tables, encoding="utf-8", newline="\n")
    code = "".join("\n%s\n  sys0=%d\n" % ((headings or [])[at] if headings
                                          else event_heading(name, "up"), at)
                   for at, name in enumerate(names))
    nx = folder / "pages" / "page0.nx"
    nx.write_text(nx.read_text(encoding="utf-8") + code, encoding="utf-8", newline="\n")


class ObjectNamesTestCase(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def new_folder(self, name: str) -> Path:
        folder = self.folder / name
        new_source_folder(folder, SETTINGS, "nextion")
        return folder

    def renamed_project(self) -> Path:
        """Returns a project whose buttons b0 to b6 are named NAMES, as the
        Nextion Editor, or another tool, could have saved it: built with
        plain names, then renamed in its dump and written."""
        source = self.new_folder("plain")
        write_buttons(source, ["b%d" % at for at in range(len(NAMES))])
        built = self.folder / "plain.HMI"
        build(source, built)
        dump = self.folder / "dump"
        ProjectDumper(built, dump).dump()
        page = next((dump / "pages").glob("*.txt"))
        text = page.read_text(encoding="utf-8")
        for at, name in enumerate(NAMES):
            # The label shows the name as the dump escapes it, when it can.
            label = (escape_string(name.encode("latin-1"))[1:-1]
                     if name.isprintable() and " " not in name else None)
            text = text.replace("object %d b%d\n" % (at + 1, at),
                                "object %d%s\n" % (at + 1, " " + label if label else ""))
            text = text.replace('objname = "b%d"' % at,
                                "objname = " + escape_string(name.encode("latin-1")))
        page.write_text(text, encoding="utf-8", newline="\n")
        renamed = self.folder / "renamed.HMI"
        ProjectWriter(built, dump, renamed).write()
        self.assertEqual(object_names(renamed)[1:],
                         [name.encode("latin-1") for name in NAMES])
        return renamed


class ExtractTest(ObjectNamesTestCase):

    def test_extract_keeps_each_name_and_the_build_gives_the_page_back(self):
        renamed = self.renamed_project()
        source = self.folder / "extracted"
        extract(renamed, source)
        build(source, self.folder / "again.HMI")
        self.assertEqual(page_block(self.folder / "again.HMI"), page_block(renamed))

    def test_a_heading_quotes_a_name_that_is_not_plain(self):
        source = self.folder / "extracted"
        extract(self.renamed_project(), source)
        lines = (source / "pages" / "page0.nx").read_text(encoding="utf-8").split("\n")
        for name in NAMES[:-1]:
            self.assertIn('on "%s".up:' % name, lines)
        self.assertIn("on b6.up:", lines)

    def test_a_dump_and_nxwright_write_keep_the_names(self):
        renamed = self.renamed_project()
        dump = self.folder / "dump-again"
        ProjectDumper(renamed, dump).dump()
        self.assertEqual(ProjectWriter(renamed, dump, self.folder / "out.HMI").write(), [])

    def test_go_to_definition_and_the_outline_find_such_an_event(self):
        source = self.folder / "extracted"
        extract(self.renamed_project(), source)
        index = FolderIndex(source, lambda path: (source / path).read_text(encoding="utf-8"))
        lines = (source / "pages" / "page0.nx").read_text(encoding="utf-8").split("\n")
        line = lines.index('on "b 0".up:')
        [place] = definitions(index, "pages/page0.nx", line, len('on "b'))
        self.assertEqual(place.path, "pages/page0.page.toml")
        names = [symbol.name for symbol in file_symbols(index, "pages/page0.nx")]
        self.assertIn('on "b 0".up', names)
        self.assertIn("on b6.up", names)


class HeadingTest(unittest.TestCase):

    def test_a_name_that_is_not_plain_is_quoted(self):
        self.assertEqual(event_heading("b 0", "up"), 'on "b 0".up:')
        self.assertEqual(event_heading("b6", "up"), "on b6.up:")

    def test_a_heading_reads_back_whole(self):
        for name in NAMES:
            with self.subTest(name=name):
                heading = read_event_heading(event_heading(name, "down"))
                self.assertEqual((heading.name, heading.event), (name, "down"))

    def test_a_quoted_plain_name_reads_as_the_plain_one(self):
        heading = read_event_heading('on "b6".up:')
        self.assertEqual((heading.name, heading.event), ("b6", "up"))

    def test_a_backslash_stands_for_itself(self):
        self.assertEqual(read_event_heading('on "b\\0".up:').name, "b\\0")


class PageFileTest(ObjectNamesTestCase):

    def test_a_page_file_may_name_such_a_component(self):
        source = self.new_folder("named")
        write_buttons(source, ["b 0", "b)0"])
        build(source, self.folder / "named.HMI")
        self.assertEqual(object_names(self.folder / "named.HMI")[1:], [b"b 0", b"b)0"])

    def test_a_quoted_plain_name_builds_as_the_plain_one(self):
        quoted, plain = self.new_folder("quoted"), self.new_folder("plain-heading")
        write_buttons(quoted, ["b0"], ['on "b0".up:'])
        write_buttons(plain, ["b0"], ["on b0.up:"])
        build(quoted, self.folder / "quoted.HMI")
        build(plain, self.folder / "plain-heading.HMI")
        self.assertEqual(page_block(self.folder / "quoted.HMI"),
                         page_block(self.folder / "plain-heading.HMI"))

    def test_an_empty_name_or_one_latin_1_lacks_is_refused(self):
        # The Editor refuses an empty name; a name is stored in Latin-1.
        for name, words in (("", "name '' is empty"),
                            ("b中0", "name 'b中0' has a character Latin-1 lacks")):
            with self.subTest(name=name):
                source = self.new_folder("odd-%d" % len(list(self.folder.iterdir())))
                write_buttons(source, [name], ["on b0.up:"])
                with self.assertRaisesRegex(NxwrightError, words):
                    build(source, self.folder / "odd.HMI")

    def test_a_name_with_a_quote_or_a_line_break_is_refused(self):
        for name in ('b"0', "b\n0"):
            with self.subTest(name=name):
                source = self.new_folder("refused-%d" % len(list(self.folder.iterdir())))
                write_buttons(source, [name], ["on b0.up:"])
                with self.assertRaisesRegex(NxwrightError, "name %s" % repr(name)
                                            .replace("\\", "\\\\").replace("(", "\\(")):
                    build(source, self.folder / "refused.HMI")


if __name__ == "__main__":
    unittest.main()
