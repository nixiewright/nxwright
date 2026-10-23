"""The source folder: import from a dump, export back, and build."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from nxwright.cli import main
from nxwright.project.dumper import ProjectDumper
from nxwright.project.project_writer import ProjectWriter
from nxwright.source.project_files import build, extract
from nxwright import NxwrightError
from nxwright.project.container import HmiContainer
from nxwright.project.page_block import Attribute, Event, Marker
from nxwright.source.page_source import PageSource, page_from_source, page_to_source
from nxwright.project.page_text import page_from_text, page_to_text
from nxwright.language.resource_names import ResourceNames
from nxwright.source.source_folder import (add_page, app_name, export_dump, import_dump,
                                           read_app, switch_to_nxlang)
from tests.test_project_writer import edit_text, sample_png, write_small_project
from tests.test_resource_names import named_font

NO_NAMES = ResourceNames([], [])
# No component defaults: every object's attributes are written in full.
NO_DEFAULTS = {}


def assert_same_dump_files(test: unittest.TestCase, original: Path, rebuilt: Path):
    """Checks that the files the project writer reads are the same in both dumps."""
    for pattern in ("pages/*.txt", "images/*.png", "fonts/*.zi", "program.s"):
        names = sorted(path.relative_to(original) for path in original.glob(pattern))
        test.assertEqual(names, sorted(path.relative_to(rebuilt) for path in rebuilt.glob(pattern)))
        for name in names:
            with test.subTest(file=str(name)):
                test.assertEqual((original / name).read_bytes(), (rebuilt / name).read_bytes())


class SourceFolderTestCase(unittest.TestCase):
    """The small test project (see write_small_project), its dump, and the source
    folder imported from that dump, all in a temporary folder."""

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

    def assert_export_refused(self, message: str):
        with self.assertRaisesRegex(NxwrightError, message):
            export_dump(self.source, self.folder / "again")
        self.assertFalse((self.folder / "again").exists())


class RoundTripTest(SourceFolderTestCase):

    def test_small_project(self):
        export_dump(self.source, self.folder / "again")
        assert_same_dump_files(self, self.dump, self.folder / "again")

    def test_import_refuses_a_gap_in_the_page_ids(self):
        pages = self.dump / "pages"
        (pages / "01-second.txt").rename(pages / "02-second.txt")
        with self.assertRaisesRegex(NxwrightError,
                                    "page IDs must run from 0 without gaps: it has no page 1$"):
            import_dump(self.dump, self.folder / "other")

    def test_layout(self):
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app, {"format": 1, "language": "nextion", "screen": "NX1060P101",
                               "rotation": 0, "encoding": "iso-8859-1",
                               "pages": ["first", "second"],
                               "pictures": ["picture-0000", "picture-0001"],
                               "fonts": ["font-00", "font-01"]})
        for relative in ("program.nx", "defaults.toml", "pages/first.page.toml", "pages/first.nx",
                         "pictures/picture-0001.png", "fonts/font-01.zi"):
            self.assertTrue((self.source / relative).is_file(), relative)

    def test_refuses_dump_missing_a_folder(self):
        (self.dump / "fonts").rename(self.folder / "fonts-elsewhere")
        with self.assertRaisesRegex(NxwrightError, "no fonts folder"):
            import_dump(self.dump, self.folder / "other")

    def test_a_blank_line_in_program_is_dropped_with_a_warning(self):
        # As in an event: the Nextion Editor compiled such lines to nothing.
        (self.dump / "program.s").write_bytes(b"sys0=1\r\n\r\n  \r\nsys1=2\r\n")
        self.assertEqual(import_dump(self.dump, self.folder / "other"),
                         ["program.s: 2 blank lines dropped; the Nextion Editor compiles them to "
                          "nothing"])
        self.assertEqual((self.folder / "other" / "program.nx").read_text(encoding="utf-8"),
                         "sys0=1\nsys1=2\n")

    def test_an_empty_program_drops_nothing(self):
        (self.dump / "program.s").write_bytes(b"")
        self.assertEqual(import_dump(self.dump, self.folder / "other"), [])
        self.assertEqual((self.folder / "other" / "program.nx").read_text(encoding="utf-8"), "")

    def test_extract_prints_what_it_dropped(self):
        (self.dump / "program.s").write_bytes(b"sys0=1\r\n\r\nsys1=2\r\n")
        project = self.folder / "spaced.HMI"
        ProjectWriter(self.project, self.dump, project).write()
        errors = io.StringIO()
        with redirect_stdout(io.StringIO()), redirect_stderr(errors):
            self.assertEqual(main(["extract", str(project), str(self.folder / "other")]), 0)
        self.assertEqual(errors.getvalue(),
                         "nxwright extract: warning: program.s: 1 blank line dropped; the Nextion "
                         "Editor compiles it to nothing\n")
        self.assertEqual((self.folder / "other" / "program.nx").read_text(encoding="utf-8"),
                         "sys0=1\nsys1=2\n")

    def test_refuses_non_empty_folder_that_is_not_a_source_folder(self):
        other = self.folder / "other"
        other.mkdir()
        (other / "notes.txt").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(NxwrightError, "neither empty nor a source folder"):
            import_dump(self.dump, other)
        self.assertEqual([path.name for path in other.iterdir()], ["notes.txt"])


class ImportUpdateTest(SourceFolderTestCase):
    """Importing into an existing source folder, as after an edit in the Editor."""

    # Comfortable code, with spaces, a blank line, and "{" on the line of its
    # "if". The build turns it into Editor code. Import keeps it as written while
    # the Editor leaves the event unchanged.
    COMFORTABLE = "on first.down:\n  if (sys0 == 1) {\n\n    sys0 = 2\n  }\n"
    # A program with spaces, which the Editor's code would not have, kept as
    # written while the Editor leaves it unchanged. It declares sys0, as the
    # Editor requires.
    PROGRAM = "int sys0=0\nsys0 = 1"

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", 'events = []', 'events = ["down"]')
        (self.source / "pages" / "first.nx").write_text(self.COMFORTABLE, encoding="utf-8",
                                                         newline="\n")
        (self.source / "program.nx").write_text(self.PROGRAM, encoding="utf-8", newline="\n")
        # The project as the Editor would save it: built from the comfortable source.
        built = self.folder / "built.HMI"
        build(self.source, built)
        self.dump = self.folder / "built-dump"
        ProjectDumper(built, self.dump).dump()

    def test_keeps_code_the_editor_did_not_change(self):
        import_dump(self.dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         self.COMFORTABLE)
        self.assertEqual((self.source / "program.nx").read_text(encoding="utf-8"), self.PROGRAM)

    def test_extract_from_the_project_file(self):
        extract(self.folder / "built.HMI", self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         self.COMFORTABLE)
        with self.assertRaisesRegex(NxwrightError, "neither empty nor a source folder"):
            other = self.folder / "other"
            other.mkdir()
            (other / "notes.txt").write_text("keep", encoding="utf-8")
            extract(self.folder / "built.HMI", other)

    def test_replaces_code_the_editor_changed(self):
        edit_text(self.dump / "pages" / "00-first.txt", "sys0=2", "sys0=3")
        (self.dump / "program.s").write_bytes(b"int sys0=0\r\nsys0=5")
        import_dump(self.dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         "on first.down:\n  if(sys0==1)\n  {\n    sys0=3\n  }\n")
        self.assertEqual((self.source / "program.nx").read_text(encoding="utf-8"),
                         "int sys0=0\nsys0=5")

    def test_deletes_only_files_the_old_app_file_lists(self):
        (self.dump / "pages" / "01-second.txt").unlink()
        (self.dump / "images" / "0001.png").unlink()
        (self.dump / "fonts" / "01.zi").unlink()
        (self.source / "notes.txt").write_text("keep", encoding="utf-8")
        (self.source / "pages" / "draft.nx").write_text("keep", encoding="utf-8")
        import_dump(self.dump, self.source)
        pages = sorted(path.name for path in (self.source / "pages").iterdir())
        self.assertEqual(pages, ["draft.nx", "first.nx", "first.page.toml"])
        self.assertEqual(sorted(path.name for path in (self.source / "pictures").iterdir()),
                         ["picture-0000.png"])
        self.assertEqual(sorted(path.name for path in (self.source / "fonts").iterdir()),
                         ["font-00.zi"])
        self.assertTrue((self.source / "notes.txt").is_file())

    def test_stops_on_code_it_cannot_preprocess(self):
        broken = 'on first.down:\n  x = "open\n'
        (self.source / "pages" / "first.nx").write_text(broken, encoding="utf-8", newline="\n")
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(NxwrightError, "first.nx line 2: a string is not closed"):
            import_dump(self.dump, self.source)
        self.assertEqual({path: path.read_bytes() for path in self.source.rglob("*")
                          if path.is_file()}, before)

    def test_build_names_the_line_of_code_it_cannot_preprocess(self):
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  x = 1 {\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_export_refused("first.nx line 2:")

    def test_build_names_the_file_of_an_event_given_twice(self):
        (self.source / "pages" / "first.nx").write_text(
            "on first.down:\n  sys0=1\n\non first.down:\n  sys0=2\n", encoding="utf-8", newline="\n")
        self.assert_export_refused("pages/first.nx line 4: first.down appears twice")


class TrailingSpacesTest(SourceFolderTestCase):
    """Spaces and tabs ending a code line, which the Nextion Editor's compile
    drops: the build writes none, and extracting drops them."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')

    def write_code(self, events: str, program: str):
        (self.source / "pages" / "first.nx").write_text(events, encoding="utf-8", newline="\n")
        (self.source / "program.nx").write_text(program, encoding="utf-8", newline="\n")

    def source_texts(self) -> tuple:
        return tuple((self.source / path).read_text(encoding="utf-8")
                     for path in ("pages/first.nx", "program.nx"))

    @staticmethod
    def event_lines(dump: Path) -> list:
        page = page_from_text((dump / "pages" / "00-first.txt").read_text(encoding="utf-8"))
        return next(item.lines for item in page.objects[0].items
                    if isinstance(item, Event) and item.name == "down")

    def project_dump(self, name: str) -> Path:
        """Builds the source folder into a project file, and returns its dump,
        as extracting reads one."""
        project, dump = self.folder / (name + ".HMI"), self.folder / name
        build(self.source, project)
        ProjectDumper(project, dump).dump()
        return dump

    def spaced_dump(self, name: str) -> Path:
        """Returns a dump of the source folder's project as the Nextion Editor
        could save it: each line of its events and program.s ending in a space
        and a tab."""
        dump = self.project_dump(name)
        path = dump / "pages" / "00-first.txt"
        page = page_from_text(path.read_text(encoding="utf-8"))
        items = page.objects[0].items
        for place, item in enumerate(items):
            if isinstance(item, Event):
                items[place] = Event(item.name, [line + b" \t" for line in item.lines])
        path.write_text(page_to_text(page), encoding="utf-8", newline="\n")
        program = (dump / "program.s").read_bytes()
        (dump / "program.s").write_bytes(b"".join(line + b" \t\r\n"
                                                  for line in program.split(b"\r\n")[:-1]))
        return dump

    def test_the_build_writes_none(self):
        self.write_code("// Sets it \non first.down:\n  if (sys0 == 1) {\t\n    sys0=2 // two \n"
                        "  }  \n  printh 01 02 \n", "int sys0=0 \nsys0=1\t\n")
        export_dump(self.source, self.folder / "built")
        self.assertEqual(self.event_lines(self.folder / "built"),
                         [b"// ### Sets it", b"if(sys0==1)", b"{", b"  sys0=2 // two", b"}",
                          b"printh 01 02"])
        self.assertEqual((self.folder / "built" / "program.s").read_bytes(),
                         b"int sys0=0\r\nsys0=1\r\n")

    def test_extracting_drops_them(self):
        self.write_code("on first.down:\n  sys0=2\n  // two\n", "int sys0=0\nsys0=1\n")
        export_dump(self.source, self.folder / "plain")
        import_dump(self.spaced_dump("spaced"), self.folder / "extracted")
        extracted = self.folder / "extracted"
        self.assertEqual((extracted / "pages" / "first.nx").read_text(encoding="utf-8"),
                         "on first.down:\n  sys0=2\n  // two\n")
        self.assertEqual((extracted / "program.nx").read_text(encoding="utf-8"),
                         "int sys0=0\nsys0=1\n")
        # Built again, it gives the project back, without them.
        export_dump(extracted, self.folder / "again")
        assert_same_dump_files(self, self.folder / "plain", self.folder / "again")

    def test_extracting_keeps_a_folders_code_where_only_they_differ(self):
        # A folder written without them, the project saved with them.
        self.write_code("on first.down:\n  sys0 = 2\n", "int sys0=0\nsys0 = 1\n")
        before = self.source_texts()
        import_dump(self.spaced_dump("spaced"), self.source)
        self.assertEqual(self.source_texts(), before)
        # A folder written with them, the project built without them.
        self.write_code("on first.down:\n  sys0 = 2 \n", "int sys0=0\t\nsys0 = 1 \n")
        before = self.source_texts()
        import_dump(self.project_dump("built"), self.source)
        self.assertEqual(self.source_texts(), before)

    def test_switching_to_nxlang(self):
        self.write_code("// Sets it \non first.down:\n  sys0=2 \n", "int sys0=0 \nsys0=1\n")
        switch_to_nxlang(self.source)
        export_dump(self.source, self.folder / "built")
        self.assertEqual(self.event_lines(self.folder / "built"), [b"// ### Sets it", b"sys0=2"])


class BuildTest(SourceFolderTestCase):

    def test_builds_an_edit(self):
        edit_text(self.source / "pages" / "second.page.toml", 'txt = "bye"', 'txt = "goodbye"')
        output = self.folder / "out.HMI"
        build(self.source, output)
        self.assertIn(b"goodbye", HmiContainer.from_file(output).blocks["1.pa"])

    def test_unchanged_source_builds_the_same_content(self):
        output = self.folder / "out.HMI"
        build(self.source, output)
        ProjectDumper(output, self.folder / "out-dump").dump()
        assert_same_dump_files(self, self.dump, self.folder / "out-dump")

    def built_page_headers(self) -> list:
        """Builds the source folder; returns the header_40 line of each page."""
        output = self.folder / "out.HMI"
        build(self.source, output)
        ProjectDumper(output, self.folder / "out-dump").dump()
        return [line for path in sorted((self.folder / "out-dump" / "pages").glob("*.txt"))
                for line in path.read_text(encoding="utf-8").split("\n")
                if line.startswith("header_40")]

    def test_pages_take_the_encoding_as_the_editor_writes_them(self):
        edit_text(self.source / "app.toml", 'encoding = "iso-8859-1"', 'encoding = "utf-8"')
        self.assertEqual(self.built_page_headers(),
                         ["header_40 = 01440218000000000000000000000000"] * 2)

    def test_a_page_in_the_older_header_form_takes_the_newer_one(self):
        # The Editor writes 01 44 02 and the encoding over the older form
        # 01 43 01 00 whenever it writes a page.
        edit_text(self.dump / "pages" / "01-second.txt", "header_40 = 01440203",
                  "header_40 = 01430100")
        source = self.folder / "older"
        import_dump(self.dump, source)
        self.source = source
        self.assertEqual(self.built_page_headers(),
                         ["header_40 = 01440203000000000000000000000000"] * 2)

    def folder_files(self) -> list:
        return sorted(path.name for path in self.folder.iterdir())

    def test_replaces_an_existing_project_file(self):
        output = self.folder / "out.HMI"
        build(self.source, output)
        files = self.folder_files()
        edit_text(self.source / "pages" / "second.page.toml", 'txt = "bye"', 'txt = "goodbye"')
        build(self.source, output)
        self.assertIn(b"goodbye", HmiContainer.from_file(output).blocks["1.pa"])
        self.assertEqual(self.folder_files(), files)

    def test_a_failed_build_keeps_the_existing_project_file(self):
        output = self.folder / "out.HMI"
        build(self.source, output)
        before, files = output.read_bytes(), self.folder_files()
        # The writer refuses a 1-by-1 picture on a screen that compresses its pictures.
        (self.source / "pictures" / "picture-0000.png").write_bytes(sample_png("raw/19-red-1x1"))
        with self.assertRaisesRegex(NxwrightError, "picture-0000|images/0000.png"):
            build(self.source, output)
        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(self.folder_files(), files)

    def test_refuses_to_replace_a_file_that_is_not_a_project_file(self):
        output = self.folder / "notes.txt"
        output.write_bytes(b"keep")
        with self.assertRaisesRegex(NxwrightError, "not a project file"):
            build(self.source, output)
        self.assertEqual(output.read_bytes(), b"keep")

    def test_a_project_file_the_nextion_editor_holds(self):
        # The Nextion Editor 3.1.73 kept a project it had open from being
        # read or written ("Permission denied"). Stand-ins refuse the
        # build's read of the project file, then its replace, as the
        # Editor would; the file is left as it was.
        output = self.folder / "built.HMI"
        build(self.source, output)
        before = output.read_bytes()
        advice = (r"built\.HMI: Permission denied; if the Nextion Editor has the project open, "
                  r"it keeps the file from being read or written: close it there, then try "
                  r"again")
        for target, refused in (
                ("nxwright.project.container.HmiContainer.from_file",
                 PermissionError(13, "Permission denied", str(output))),
                ("os.replace",
                 PermissionError(13, "Permission denied", "built.HMI.0.partial", None,
                                 str(output)))):
            with self.subTest(target=target):
                with mock.patch(target, side_effect=refused):
                    with self.assertRaisesRegex(NxwrightError, advice):
                        build(self.source, output)
                self.assertEqual(output.read_bytes(), before)
        # Another file's refusal keeps its own words.
        other = PermissionError(13, "Permission denied", str(self.folder / "other.HMI"))
        with mock.patch("nxwright.project.container.HmiContainer.from_file", side_effect=other):
            with self.assertRaises(PermissionError):
                build(self.source, output)

    def test_a_project_file_the_nextion_editor_holds_is_not_extracted(self):
        refused = PermissionError(13, "Permission denied", str(self.project))
        with mock.patch("nxwright.project.container.HmiContainer.from_file", side_effect=refused):
            with self.assertRaisesRegex(NxwrightError, r"Permission denied; if the Nextion "
                                                       r"Editor has the project open"):
                extract(self.project, self.folder / "extracted")

    def test_refuses_a_folder_as_the_output(self):
        with self.assertRaisesRegex(NxwrightError, "not a project file"):
            build(self.source, self.source)


class PageHeaderTest(SourceFolderTestCase):
    """The page header: a system page's mark, a page's lock and its password,
    and the forms extracting accepts."""

    def set_dump_header(self, line: str, old: str, new: str):
        edit_text(self.dump / "pages" / "01-second.txt", "%s = %s" % (line, old),
                  "%s = %s" % (line, new))

    def test_ordinary_pages_write_no_header(self):
        text = (self.source / "pages" / "second.page.toml").read_text(encoding="utf-8")
        for key in ("header_16", "header_40", "system_page", "locked", "lock_password"):
            self.assertNotIn(key, text)

    def test_system_pages_round_trip(self):
        for name, mark in (("keyboard", "01"), ("keypad", "02"), ("speed-dial", "03"),
                           ("chinese-input", "04")):
            with self.subTest(system_page=name):
                self.set_dump_header("header_16", "00000000004f2100", "00000000004f21" + mark)
                source = self.folder / name
                import_dump(self.dump, source)
                self.assertIn('type = "page"\nsystem_page = "%s"\n' % name,
                              (source / "pages" / "second.page.toml").read_text(encoding="utf-8"))
                again = self.folder / (name + "-again")
                export_dump(source, again)
                self.assertIn("header_16 = 00000000004f21" + mark,
                              (again / "pages" / "01-second.txt").read_text(encoding="utf-8"))
                self.set_dump_header("header_16", "00000000004f21" + mark, "00000000004f2100")

    def test_a_locked_page_round_trips(self):
        # Locked in the Editor: the Editor's stock keyboard as it adds it,
        # locked without a password, and a page locked with "abcde".
        for header, lines in (("00000000014f2101", 'system_page = "keyboard"\nlocked = true\n'),
                              ("52c80ffa014f2100",
                               'locked = true\nlock_password_hash = "52c80ffa"\n')):
            with self.subTest(header=header):
                self.set_dump_header("header_16", "00000000004f2100", header)
                source = self.folder / header
                import_dump(self.dump, source)
                self.assertIn('type = "page"\n' + lines,
                              (source / "pages" / "second.page.toml").read_text(encoding="utf-8"))
                again = self.folder / (header + "-again")
                export_dump(source, again)
                self.assertIn("header_16 = " + header,
                              (again / "pages" / "01-second.txt").read_text(encoding="utf-8"))
                self.set_dump_header("header_16", header, "00000000004f2100")

    def test_extract_refuses_a_header_it_does_not_know(self):
        for line, old, new in (("header_16", "00000000004f2100", "00000000004f2105"),
                               ("header_16", "00000000004f2100", "00000000024f2100"),
                               ("header_16", "00000000004f2100", "00000000004f2200"),
                               ("header_40", "01440203000000000000000000000000",
                                "01440203000000000000000000000001"),
                               ("header_40", "01440203", "01450203")):
            with self.subTest(line=line, value=new):
                self.set_dump_header(line, old, new)
                with self.assertRaisesRegex(NxwrightError, "page second: its header .* is not one"):
                    import_dump(self.dump, self.folder / "refused")
                self.assertFalse((self.folder / "refused").exists())
                self.set_dump_header(line, new, old)

    def test_build_refuses_page_files_holding_what_they_no_longer_keep(self):
        page = self.source / "pages" / "second.page.toml"
        cases = {"header_16 , which page files no longer keep":
                 ('type = "page"\n', 'type = "page"\nheader_16 = "00000000004f2100"\n'),
                 "system_page must be": ('type = "page"\n', 'type = "page"\nsystem_page = "pad"\n'),
                 "locked must be true or false":
                 ('type = "page"\n', 'type = "page"\nlocked = 1\n'),
                 "lock_password_hash must be 8 lower-case hexadecimal digits":
                 ('type = "page"\n', 'type = "page"\nlock_password_hash = "ABCDEF01"\n'),
                 "only the \\[page\\] table can give locked":
                 ('type = "page"\n', 'type = "page"\n\n[[component]]\nname = "k"\n'
                  'type = "variable"\nlocked = true\n'),
                 "only the \\[page\\] table can give system_page":
                 ('type = "page"\n', 'type = "page"\n\n[[component]]\nname = "k"\n'
                  'type = "variable"\nsystem_page = "keypad"\n')}
        original = page.read_text(encoding="utf-8")
        for message, (old, new) in cases.items():
            with self.subTest(message=message):
                page.write_text(original.replace(old, new, 1), encoding="utf-8", newline="\n")
                self.assert_export_refused(message.replace(" ,", ","))
        page.write_text(original, encoding="utf-8", newline="\n")


class ProjectNameTest(SourceFolderTestCase):
    """A project's own name, in app.toml."""

    def test_the_name_is_kept_second(self):
        # A name to show, of any one line; written back second, after format.
        app = self.source / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace(
            "format = 1\n", 'format = 1\nname = "Thermostat: v2"\n', 1), encoding="utf-8")
        add_page(self.source)
        self.assertEqual(app.read_text(encoding="utf-8").splitlines()[:2],
                         ["format = 1", 'name = "Thermostat: v2"'])
        self.assertEqual(app_name(read_app(self.source), self.source), "Thermostat: v2")

    def test_the_folders_name_without_one(self):
        self.assertEqual(app_name(read_app(self.source), self.source), "source")

    def test_extracting(self):
        # Into a new folder: the project file's name; into a folder: its own.
        fresh = self.folder / "fresh"
        built = self.folder / "Living room.HMI"
        build(self.source, built)
        extract(built, fresh)
        self.assertEqual(read_app(fresh)["name"], "Living room")
        app = self.source / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace(
            "format = 1\n", 'format = 1\nname = "Kept"\n', 1), encoding="utf-8")
        extract(built, self.source)
        self.assertEqual(read_app(self.source)["name"], "Kept")


class SourceRefusalTest(SourceFolderTestCase):

    def test_app_file(self):
        app = self.source / "app.toml"
        # A trailing space tells apart two cases expecting the same message.
        cases = {
            "format must be": ("format = 1", 'format = "2"'),
            "needs a newer nxwright": ("format = 1", "format = 3"),
            "format must be ": ("format = 1", "format = true"),
            "language must be": ('language = "nextion"\n', ""),
            "not a valid name": ('"font-00"', '"../font-00"'),
            "unknown key": ("format = 1", "format = 1\ncolour = 1"),
            "are the same name": ('"font-01"', '"font-00"'),
            "same name": ('"font-01"', '"FONT-00"'),
            "folder of another name": ('"picture-0001"', '"picture-0000/x"'),
            "not a valid name ": ('"font-01"', '"con"'),
            "name must be": ("format = 1", 'format = 1\nname = ""'),
            "name must be ": ("format = 1", 'format = 1\nname = " Clock"'),
            "name must be  ": ("format = 1", 'format = 1\nname = "a\\nb"'),
            "name must be   ": ("format = 1", "format = 1\nname = 3"),
        }
        original = app.read_text(encoding="utf-8")
        for message, (old, new) in cases.items():
            with self.subTest(message=message):
                app.write_text(original.replace(old, new, 1), encoding="utf-8", newline="\n")
                self.assert_export_refused(message.strip())
        app.write_text(original, encoding="utf-8", newline="\n")

    def test_page_file(self):
        page = self.source / "pages" / "first.page.toml"
        cases = {
            "unknown attribute": ('txt = "hello"', 'txt = "hello"\nnotanattribute = 1'),
            "colour": ('vscope = 0', 'vscope = 0\nbco = "white"'),
            "does not fit": ('vscope = 0', 'vscope = 300'),
            "names the page": ('name = "first"', 'name = "other"'),
            "holds only": ("[page]", "[extra]\na = 1\n\n[page]"),
            "unknown type": ('type = "page"', 'type = "dial"'),
            "endx and endy need h": ('vscope = 0', 'vscope = 0\nendx = 5'),
            "unknown type \\[1\\]": ('type = "page"', 'type = [1]'),
            "defaults must be true or false": ("defaults = false", "defaults = 0"),
            "component t0 needs its place on the screen; x, y, w, h missing":
                ('txt = "hello"', 'txt = "hello"\n\n[[component]]\nname = "t0"\ntype = "text"'),
        }
        original = page.read_text(encoding="utf-8")
        for message, (old, new) in cases.items():
            with self.subTest(message=message):
                page.write_text(original.replace(old, new, 1), encoding="utf-8", newline="\n")
                self.assert_export_refused(message)
        page.write_text(original, encoding="utf-8", newline="\n")

    def test_two_objects_with_one_name(self):
        page = self.source / "pages" / "first.page.toml"
        page.write_text(page.read_text(encoding="utf-8")
                        + '\n[[component]]\nname = "first"\ntype = "variable"\n',
                        encoding="utf-8", newline="\n")
        self.assert_export_refused("two objects are named first")

    def test_events_file(self):
        events = self.source / "pages" / "first.nx"
        cases = {
            "not an event listed": "on first.slide:\n  sys0=1\n",
            "appears twice": "on first.load:\n  sys0=1\non first.load:\n  sys1=1\n",
            "indented by two spaces": "on first.load:\nsys0=1\n",
        }
        for message, text in cases.items():
            with self.subTest(message=message):
                events.write_text(text, encoding="utf-8", newline="\n")
                self.assert_export_refused(message)

    def test_missing_file(self):
        (self.source / "pictures" / "picture-0001.png").unlink()
        self.assert_export_refused("missing")


class NamesTest(SourceFolderTestCase):
    """Pictures and fonts by name in the source folder."""

    def rename_picture(self, old: str, new: str):
        edit_text(self.source / "app.toml", '"%s"' % old, '"%s"' % new)
        target = self.source / "pictures" / (new + ".png")
        target.parent.mkdir(parents=True, exist_ok=True)
        (self.source / "pictures" / (old + ".png")).rename(target)

    def build_and_dump(self) -> Path:
        """Builds the source folder and dumps the result, as after a save in the Editor."""
        built = self.folder / "built.HMI"
        build(self.source, built)
        dump = self.folder / "built-dump"
        ProjectDumper(built, dump).dump()
        return dump

    def test_renamed_picture_builds_the_same_project(self):
        self.rename_picture("picture-0001", "mono-dark/toast")
        assert_same_dump_files(self, self.dump, self.build_and_dump())

    def test_import_keeps_names_also_when_pictures_move(self):
        self.rename_picture("picture-0000", "dot")
        self.rename_picture("picture-0001", "grid")
        dump = self.build_and_dump()
        first, second = (dump / "images" / "0000.png").read_bytes(), (dump / "images" / "0001.png").read_bytes()
        (dump / "images" / "0000.png").write_bytes(second)
        (dump / "images" / "0001.png").write_bytes(first)
        import_dump(dump, self.source)
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["pictures"], ["grid", "dot"])

    def test_new_names_from_font_headers_and_placeholders(self):
        self.rename_picture("picture-0000", "picture-0002")
        dump = self.build_and_dump()
        (dump / "images" / "0002.png").write_bytes((dump / "images" / "0001.png").read_bytes()
                                                   + b"\0")
        (dump / "fonts" / "02.zi").write_bytes(named_font(b"Impact16"))
        (dump / "fonts" / "03.zi").write_bytes(named_font(b"impact16"))
        import_dump(dump, self.source)
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        # Picture 0 already holds the placeholder name of the new picture 2, so it
        # gets a suffix. Font 3's header name differs from font 2's only in
        # letter case, so font 3 gets a placeholder.
        self.assertEqual(app["pictures"], ["picture-0002", "picture-0001", "picture-0002-2"])
        self.assertEqual(app["fonts"], ["font-00", "font-01", "Impact16", "font-03"])

    def test_new_file_differing_from_a_stale_one_only_in_case_is_kept(self):
        # Windows file names ignore case: deleting the stale "impact16.zi" must
        # not delete the new "Impact16.zi".
        edit_text(self.source / "app.toml", '"font-00"', '"impact16"')
        (self.source / "fonts" / "font-00.zi").rename(self.source / "fonts" / "impact16.zi")
        # Font 1 moves to ID 0, and a new font named Impact16 takes ID 1, so the
        # old "impact16" matches nothing and is not edited in place either.
        fonts = self.dump / "fonts"
        fonts.joinpath("00.zi").write_bytes(fonts.joinpath("01.zi").read_bytes())
        fonts.joinpath("01.zi").write_bytes(named_font(b"Impact16"))
        import_dump(self.dump, self.source)
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["fonts"], ["font-01", "Impact16"])
        self.assertEqual((self.source / "fonts" / "Impact16.zi").read_bytes(), named_font(b"Impact16"))

    def test_new_name_avoids_the_folder_of_a_kept_name(self):
        # picture-0002 would be the folder of the kept name picture-0002/dot.
        self.rename_picture("picture-0000", "picture-0002/dot")
        dump = self.build_and_dump()
        (dump / "images" / "0002.png").write_bytes((dump / "images" / "0001.png").read_bytes()
                                                   + b"\0")
        import_dump(dump, self.source)
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["pictures"], ["picture-0002/dot", "picture-0001", "picture-0002-2"])

    def test_picture_edited_in_place_keeps_its_name(self):
        self.rename_picture("picture-0001", "grid")
        dump = self.build_and_dump()
        (dump / "images" / "0001.png").write_bytes((dump / "images" / "0001.png").read_bytes() + b"\0")
        import_dump(dump, self.source)
        app = tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["pictures"], ["picture-0000", "grid"])

    def test_code_naming_a_removed_picture_counts_as_changed(self):
        edit_text(self.source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0 = @pic(picture-0001)\n",
                                                         encoding="utf-8", newline="\n")
        dump = self.build_and_dump()
        (dump / "images" / "0001.png").unlink()
        edit_text(dump / "pages" / "00-first.txt", "sys0=1", "sys0=0")
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         "on first.down:\n  sys0=0\n")

    def test_missing_old_picture_file_does_not_block_import(self):
        (self.source / "pictures" / "picture-0001.png").unlink()
        import_dump(self.dump, self.source)
        self.assertTrue((self.source / "pictures" / "picture-0001.png").is_file())



class PageSourceTest(unittest.TestCase):

    def test_picture_and_font_attributes(self):
        page = self.page()
        items = page.objects[0].items
        items.insert(len(items), Attribute("pic", (0).to_bytes(2, "little")))
        items.insert(len(items), Attribute("picc", (65535).to_bytes(2, "little")))
        items.insert(len(items), Attribute("pic2", (5).to_bytes(2, "little")))
        items.insert(len(items), Attribute("font", b"\x00"))
        items[0] = Marker(b"att-%d" % sum(isinstance(item, Attribute) for item in items))
        names = ResourceNames(["dot"], ["Impact16"])
        source = page_to_source(page, names, NO_DEFAULTS)
        for line in ('pic = "dot"', "picc = 65535", "pic2 = 5", 'font = "Impact16"'):
            self.assertIn(line, source.toml)
        self.assertEqual(page_from_source(source, "first", names, NO_DEFAULTS), page)
        with self.assertRaisesRegex(NxwrightError, "pic: no picture is named grid"):
            page_from_source(PageSource(source.toml.replace('"dot"', '"grid"'), ""), "first", names,
                             NO_DEFAULTS)

    def page(self, events_text="", extra_attribute=None):
        from tests.test_project_writer import small_page
        page = page_from_text(_dump_text(small_page("first", b"hello")))
        if extra_attribute:
            page.objects[0].items.insert(2, extra_attribute)
        return page

    def test_events_with_and_without_code(self):
        page = self.page()
        page.objects[0].items.append(Event("down", [b"  x=1", b"// c\xe9"]))
        page.objects[0].items.append(Event("up", []))
        source = page_to_source(page, NO_NAMES, NO_DEFAULTS)
        self.assertEqual(source.events, "on first.down:\n    x=1\n  // cé\n")
        self.assertEqual(tomllib.loads(source.toml)["page"]["events"], ["down", "up"])
        self.assertEqual(page_from_source(source, "first", NO_NAMES, NO_DEFAULTS), page)

    def test_a_blank_line_is_dropped_with_a_warning(self):
        # A line of only spaces or tabs, which the Nextion Editor compiled to
        # nothing. The import drops the spaces ending each line first, so it
        # meets one as an empty line. An event of blank lines alone keeps no
        # code, and so no heading.
        page = self.page()
        page.objects[0].items.append(Event("down", [b"x=1", b"  ", b"", b"y=2"]))
        page.objects[0].items.append(Event("up", [b" \t"]))
        source = page_to_source(page, NO_NAMES, NO_DEFAULTS)
        self.assertEqual(source.events, "on first.down:\n  x=1\n  y=2\n")
        self.assertEqual(tomllib.loads(source.toml)["page"]["events"], ["down", "up"])
        self.assertEqual(source.warnings, (
            "page first, event first.down: 2 blank lines dropped; the Nextion Editor compiles "
            "them to nothing",
            "page first, event first.up: 1 blank line dropped; the Nextion Editor compiles it to "
            "nothing"))

    def test_refuses_what_the_source_cannot_hold(self):
        cases = {
            "control character": lambda page: page.objects[0].items.append(Event("down", [b"a\x01"])),
            "class marker": lambda page: page.objects[0].items.insert(1, Marker(b"att-1")),
            "header size": lambda page: setattr(page, "header_size", 60),
            "appears twice": lambda page: page.objects[0].items.extend([Event("down", []),
                                                                         Event("down", [])]),
            "lowercase letters": lambda page: page.objects[0].items.append(Event("Down", [])),
            "named after the page": lambda page: setattr(page, "name", "other"),
        }
        for message, change in cases.items():
            with self.subTest(message=message):
                page = self.page()
                change(page)
                with self.assertRaisesRegex(NxwrightError, message):
                    page_to_source(page, NO_NAMES, NO_DEFAULTS)

    def test_four_byte_values_are_written_signed(self):
        # As the Editor's panel shows them: -42 for 0xFFFFFFD6.
        page = self.page()
        items = page.objects[0].items
        items.append(Attribute("val", (2 ** 32 - 42).to_bytes(4, "little")))
        items[0] = Marker(b"att-%d" % sum(isinstance(item, Attribute) for item in items))
        source = page_to_source(page, NO_NAMES, NO_DEFAULTS)
        self.assertIn("val = -42", source.toml)
        self.assertEqual(page_from_source(source, "first", NO_NAMES, NO_DEFAULTS), page)
        unsigned = PageSource(source.toml.replace("val = -42", "val = 4294967254"), "")
        self.assertEqual(page_from_source(unsigned, "first", NO_NAMES, NO_DEFAULTS), page)
        for value in (-2 ** 31 - 1, 2 ** 32):
            with self.subTest(value=value):
                too_large = PageSource(source.toml.replace("val = -42", "val = %d" % value), "")
                with self.assertRaisesRegex(NxwrightError, "val does not fit in 4 bytes"):
                    page_from_source(too_large, "first", NO_NAMES, NO_DEFAULTS)

    def test_derived_value_that_differs_is_kept(self):
        page = self.page()
        items = page.objects[0].items
        index = next(i for i, item in enumerate(items) if isinstance(item, Attribute) and item.name == "id")
        items[index] = Attribute("id", b"\x07")
        source = page_to_source(page, NO_NAMES, NO_DEFAULTS)
        self.assertIn("id = 7", source.toml)
        self.assertEqual(page_from_source(source, "first", NO_NAMES, NO_DEFAULTS), page)


def _dump_text(block: bytes) -> str:
    """Returns the page block `block` as the text of its page file in a dump."""
    from nxwright.project.page_block import parse_page
    from nxwright.project.page_text import page_to_text
    return page_to_text(parse_page(block))


if __name__ == "__main__":
    unittest.main()
