"""Extracted code naming assets (source/asset_names_in_code.py)."""
import unittest

from nxwright.language.resource_names import ResourceNames
from nxwright.project.container import HmiContainer
from nxwright.source.asset_names_in_code import with_asset_names
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import switch_to_nxlang
from tests.test_build_checks import add_component
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase

NAMES = ResourceNames(pictures=["picture-0000", "logo", "icons/back"], fonts=["font-00", "Sans16"],
                      animations=["animation-00"], videos=["video-00"], sounds=["sound-00"])


class WithAssetNamesTest(unittest.TestCase):

    def assert_named(self, line: str, named: str):
        self.assertEqual(with_asset_names(line, NAMES), named)

    def assert_unchanged(self, line: str):
        self.assertEqual(with_asset_names(line, NAMES), line)

    def test_attributes_that_hold_a_picture(self):
        for attribute in ("pic", "pic1", "pic2", "picc", "picc1", "picc2", "bpic", "ppic"):
            with self.subTest(attribute=attribute):
                self.assert_named("  b0.%s=1" % attribute, "  b0.%s=@pic(logo)" % attribute)

    def test_the_font_attribute(self):
        self.assert_named("  t0.font=1", "  t0.font=@font(Sans16)")

    def test_a_component_of_another_page_or_in_an_array(self):
        self.assert_named("page1.b0.pic2=2", "page1.b0.pic2=@pic(icons/back)")
        self.assert_named("b[3].pic=0", "b[3].pic=@pic(picture-0000)")
        self.assert_named("b[sys0].pic=0", "b[sys0].pic=@pic(picture-0000)")

    def test_the_drawing_commands(self):
        self.assert_named("  pic 0,0,1", "  pic 0,0,@pic(logo)")
        self.assert_named("picq 0,0,10,10,1", "picq 0,0,10,10,@pic(logo)")
        self.assert_named("xpic 0,0,10,10,5,5,1", "xpic 0,0,10,10,5,5,@pic(logo)")
        self.assert_named('xstr 0,0,100,30,1,RED,WHITE,0,0,1,"a,b"',
                          'xstr 0,0,100,30,@font(Sans16),RED,WHITE,0,0,1,"a,b"')

    def test_a_comment_after_the_code_stays(self):
        self.assert_named("  b0.pic=1   // the logo", "  b0.pic=@pic(logo)   // the logo")

    def test_numbers_that_may_mean_something_else_stay(self):
        for line in ("sys0=1", "b0.val=1", "b0.pic=sys0", "b0.pic=sys0+1", "b0.pic=1+1",
                     "b0.pic==1", "if(b0.pic==1)", "pic 0,0,sys0", "fill 0,0,1,1,1",
                     "pic 0,1", "xstr 0,0,100,30,sys0,RED,WHITE,0,0,1,\"a\""):
            with self.subTest(line=line):
                self.assert_unchanged(line)

    def test_other_forms_of_a_number_stay(self):
        for line in ("b0.pic=0x01", "b0.pic=01", "b0.pic=-1", "pic 0,0,0x01", "pic 0,0,01"):
            with self.subTest(line=line):
                self.assert_unchanged(line)

    def test_a_number_with_no_asset_stays(self):
        self.assert_unchanged("b0.pic=3")
        self.assert_unchanged("t0.font=2")
        self.assert_unchanged("pic 0,0,3")

    def test_vid_stays(self):
        self.assert_unchanged("v0.vid=0")

    def test_strings_and_comments_stay(self):
        self.assert_unchanged('t0.txt="b0.pic=1"')
        self.assert_unchanged("// b0.pic=1")
        self.assert_unchanged("  sys0=2 // b0.pic=1")

    def test_headings_stay(self):
        self.assert_unchanged("on b0.down:")
        self.assert_unchanged("macro pic:")

    def test_a_line_that_cannot_be_read_stays(self):
        self.assert_unchanged('b0.pic=1 "open')

    def test_every_line_of_a_file(self):
        self.assertEqual(with_asset_names("on b0.down:\n  sys0=1\n  b0.pic=1\n", NAMES),
                         "on b0.down:\n  sys0=1\n  b0.pic=@pic(logo)\n")


class ExtractTest(SourceFolderTestCase):
    """A project with numbers for its assets, extracted into a new folder."""

    EVENTS = 'on first.down:\n  t0.font=1\n  pic 0,0,1\n  xstr 0,0,9,9,1,0,0,0,0,1,"a"\n  sys0=1\n'
    NAMED = ('on first.down:\n  t0.font=@font(font-01)\n  pic 0,0,@pic(picture-0001)\n'
             '  xstr 0,0,9,9,@font(font-01),0,0,0,0,1,"a"\n  sys0=1\n')

    def setUp(self):
        super().setUp()
        add_component(self.source / "pages" / "first.page.toml", "t0")
        edit_text(self.source / "pages" / "first.page.toml", 'events = []', 'events = ["down"]')
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        (self.source / "program.nx").write_text("int sys0=0\npic 0,0,1\npage 0\n",
                                                encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro setit:\n  pic 0,0,1\n", encoding="utf-8",
                                               newline="\n")
        self.built = self.folder / "built.HMI"
        build(self.source, self.built)
        self.extracted = self.folder / "extracted"
        extract(self.built, self.extracted)

    def text(self, file: str) -> str:
        return (self.extracted / file).read_text(encoding="utf-8")

    def test_events(self):
        self.assertEqual(self.text("pages/first.nx"), self.NAMED)

    def test_the_program(self):
        self.assertIn("pic 0,0,@pic(picture-0001)\n", self.text("program.nx"))

    def test_macros(self):
        self.assertEqual(self.text("macros.nx"), "macro setit:\n  pic 0,0,@pic(picture-0001)\n")

    def test_it_builds_the_same_project(self):
        again = self.folder / "again.HMI"
        build(self.extracted, again)
        self.assertEqual(again.read_bytes(), self.built.read_bytes())

    def test_it_still_builds_the_same_project_after_switching_to_nxlang(self):
        switch_to_nxlang(self.extracted)
        again = self.folder / "again.HMI"
        build(self.extracted, again)
        self.assertEqual(HmiContainer.from_file(again).blocks["0.pa"][4:],
                         HmiContainer.from_file(self.built).blocks["0.pa"][4:])


if __name__ == "__main__":
    unittest.main()
