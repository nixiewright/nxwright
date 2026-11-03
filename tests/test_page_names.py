"""Pages of names that are not plain, such as `p 0` or `a:b`, which the
Nextion Editor allows (ResearchNotes/object-names.md), or which a project
file may have. Extract keeps them, and the build writes them back. A page's
file names write its name with `%` and the characters Windows refuses in a
file name percent-encoded: the page `a:b` has `pages/a%3Ab.page.toml`."""
from pathlib import Path
import tomllib
import unittest

from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_file_names import page_file_stem, page_of_file_stem
from nxwright.project.page_text import escape_string
from nxwright.project.project_writer import ProjectWriter
from nxwright.project.container import HmiContainer
from nxwright.project.page_block import parse_page
from nxwright.project.resources import parse_manifest
from nxwright.source.definitions import definitions
from nxwright.source.folder_index import FolderIndex, page_of
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import add_page, switch_to_nxlang
from nxwright.testing.preview import page_of_file
from tests.test_object_names import ObjectNamesTestCase, write_buttons

# The names pages 1 to 4 take; page0 keeps its plain name.
NAMES = ["p 0", "a:b", "x|y", "p100%"]
# Their files' names, without `.page.toml` or `.nx`.
STEMS = ["p 0", "a%3Ab", "x%7Cy", "p100%25"]


def page_names(project: Path) -> list:
    """Returns the names of the project's pages, in ID order."""
    blocks = HmiContainer.from_file(project).blocks
    return [parse_page(blocks[name]).objects[0].attribute("objname")
            for name in parse_manifest(blocks["main.HMI"]).block_names("pa")]


class PageNamesTestCase(ObjectNamesTestCase):

    def renamed_project(self) -> Path:
        """Returns a project whose pages 1 to 4 are named NAMES, page1 with a
        button b0 with Touch Release code, as the Nextion Editor, or another
        tool, could have saved it: built with plain names, then renamed in
        its dump and written."""
        source = self.new_folder("plain")
        for _ in NAMES:
            add_page(source)
        page1 = source / "pages" / "page1.page.toml"
        page1.write_text(page1.read_text(encoding="utf-8")
                         + '\n[[component]]\nname = "b0"\ntype = "button"\nx = 10\ny = 10\n'
                         'w = 100\nh = 30\n', encoding="utf-8", newline="\n")
        (source / "pages" / "page1.nx").write_text("on b0.up:\n  sys0=1\n", encoding="utf-8",
                                                   newline="\n")
        built = self.folder / "plain.HMI"
        build(source, built)
        dump = self.folder / "dump"
        ProjectDumper(built, dump).dump()
        for at, name in enumerate(NAMES, start=1):
            [page] = (dump / "pages").glob("%02d-*.txt" % at)
            text = page.read_text(encoding="utf-8")
            label = (escape_string(name.encode("latin-1"))[1:-1]
                     if " " not in name else None)
            # The page's header names it too, on the dump's first line.
            text = text.replace("page page%d\n" % at, "page %s\n" % name, 1)
            text = text.replace("object 0 page%d\n" % at,
                                "object 0%s\n" % (" " + label if label else ""))
            text = text.replace('objname = "page%d"' % at,
                                "objname = " + escape_string(name.encode("latin-1")))
            page.write_text(text, encoding="utf-8", newline="\n")
        renamed = self.folder / "renamed.HMI"
        ProjectWriter(built, dump, renamed).write()
        self.assertEqual(page_names(renamed)[1:], [name.encode("latin-1") for name in NAMES])
        return renamed


class ExtractTest(PageNamesTestCase):

    def test_extract_keeps_each_name_and_the_build_gives_the_project_back(self):
        renamed = self.renamed_project()
        source = self.folder / "extracted"
        extract(renamed, source)
        build(source, self.folder / "again.HMI")
        self.assertEqual(page_names(self.folder / "again.HMI"), page_names(renamed))
        # Page by page, in ID order: the writer numbered its blocks otherwise.
        pages = []
        for project in (renamed, self.folder / "again.HMI"):
            blocks = HmiContainer.from_file(project).blocks
            pages.append([blocks[name] for name in
                          parse_manifest(blocks["main.HMI"]).block_names("pa")])
        self.assertEqual(pages[1], pages[0])

    def test_the_pages_files_encode_their_names(self):
        source = self.folder / "extracted"
        extract(self.renamed_project(), source)
        files = sorted(path.name for path in (source / "pages").iterdir())
        self.assertEqual(files, sorted(["page0.page.toml", "page0.nx"]
                                       + ["%s%s" % (stem, suffix) for stem in STEMS
                                          for suffix in (".page.toml", ".nx")]))
        app = tomllib.loads((source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["pages"], ["page0"] + NAMES)

    def test_a_dump_and_nxwright_write_keep_the_names(self):
        renamed = self.renamed_project()
        dump = self.folder / "dump-again"
        ProjectDumper(renamed, dump).dump()
        self.assertEqual(sorted(path.name for path in (dump / "pages").iterdir()),
                         ["00-page0.txt"] + ["%02d-%s.txt" % (at, stem)
                                             for at, stem in enumerate(STEMS, start=1)])
        self.assertEqual(ProjectWriter(renamed, dump, self.folder / "out.HMI").write(), [])

    def test_the_switch_to_nxlang_reads_such_a_page_s_files(self):
        source = self.folder / "extracted"
        extract(self.renamed_project(), source)
        switch_to_nxlang(source)
        build(source, self.folder / "switched.HMI")
        self.assertEqual(page_names(self.folder / "switched.HMI")[1:],
                         [name.encode("latin-1") for name in NAMES])

    def test_go_to_definition_works_in_the_files_of_such_a_page(self):
        source = self.folder / "extracted"
        extract(self.renamed_project(), source)
        index = FolderIndex(source, lambda path: (source / path).read_text(encoding="utf-8"))
        [place] = definitions(index, "pages/p 0.nx", 0, len("on b"))
        self.assertEqual(place.path, "pages/p 0.page.toml")


class FileNameTest(unittest.TestCase):

    def test_a_name_and_its_files(self):
        for name, stem in zip(NAMES + ["page0", "a\\b/c*d?e<f>g\"h"],
                              STEMS + ["page0", "a%5Cb%2Fc%2Ad%3Fe%3Cf%3Eg%22h"]):
            with self.subTest(name=name):
                self.assertEqual(page_file_stem(name), stem)
                self.assertEqual(page_of_file_stem(stem), name)

    def test_the_page_of_each_of_its_files(self):
        for name, stem in zip(NAMES, STEMS):
            with self.subTest(name=name):
                self.assertEqual(page_of("pages/%s.page.toml" % stem), name)
                self.assertEqual(page_of_file("pages/%s.page.toml" % stem), name)
                self.assertEqual(page_of_file("pages/%s.nx" % stem), name)


class PageFileTest(ObjectNamesTestCase):

    def test_app_toml_may_list_such_a_page(self):
        source = self.new_folder("listed")
        write_buttons(source, ["b0"])
        app = source / "app.toml"
        app.write_text(app.read_text(encoding="utf-8").replace('"page0"', '"a:b"'),
                       encoding="utf-8", newline="\n")
        pages = source / "pages"
        for suffix in (".page.toml", ".nx"):
            (pages / ("page0" + suffix)).rename(pages / ("a%3Ab" + suffix))
        toml = pages / "a%3Ab.page.toml"
        toml.write_text(toml.read_text(encoding="utf-8").replace('name = "page0"', 'name = "a:b"'),
                        encoding="utf-8", newline="\n")
        build(source, self.folder / "listed.HMI")
        self.assertEqual(page_names(self.folder / "listed.HMI"), [b"a:b"])


if __name__ == "__main__":
    unittest.main()
