"""The formatter, its check that the Editor code does not change, nxwright
format, rename, and the Editor code of a .nx file with the lines it comes from."""
import contextlib
import io
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.language_server.file_texts import FileTexts
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION
from nxwright.source.folder_index import FolderIndex
from nxwright.source.formatter import format_code, format_macros
from nxwright.language_server.rename import rename
from nxwright.source.formatting import format_folder
from nxwright.source.source_folder import folder_reader, read_folder_source
from tests.test_folder_check import FolderTestCase


def event(*lines: str) -> str:
    """Returns a .nx file with one event whose code is `lines`, as written."""
    return "on page0.load:\n" + "".join("  %s\n" % line for line in lines)


class FormatterTest(unittest.TestCase):

    def assertFormats(self, text: str, expected: str, nxlang: bool = True, program: bool = False):
        formatted = format_code(text, nxlang, program)
        self.assertEqual(formatted, expected)
        self.assertEqual(format_code(formatted, nxlang, program), formatted)

    def test_a_comment_above_no_heading_stays_where_it_is(self):
        # Before the first event, between two, and after the last; in nxlang,
        # one before the first heading is the file's preamble.
        middle = ("on page0.load:\n  vis t0,1\n\n// --- Releases ---\n\n// More.\n\n"
                  "on page0.up:\n  vis t0,0\n\n// The end.\n")
        self.assertFormats("// The page's events.\n\n" + middle,
                           "// The page's events.\n\n" + middle, nxlang=False)
        self.assertFormats(middle, middle)

    def test_blocks_and_braces(self):
        self.assertFormats(event("if(a==1)", "{", "sys0=1", "}", "else", "{", "sys0=2", "}"),
                           event("if (a == 1) {", "  sys0 = 1", "} else {", "  sys0 = 2", "}"))

    def test_else_if_and_loops(self):
        self.assertFormats(
            event("while(i<3) {", "for(j=0;j<2;j++){", "i++", "}", "}else if(b){", "}"),
            event("while (i < 3) {", "  for (j = 0; j < 2; j++) {", "    i++", "  }",
                  "} else if (b) {", "}"))

    def test_a_switch(self):
        self.assertFormats(
            event("switch (mode) {", "case 1:", "sys0 = 1", "break",
                  "// The rest.", "default:", "sys0 = 2", "}"),
            event("switch (mode) {", "  case 1:", "    sys0 = 1", "    break",
                  "  // The rest.", "  default:", "    sys0 = 2", "}"))

    def test_spaces(self):
        self.assertFormats(
            event("x.val=-a.val*(b+c)", "flag=!ready", "t0.txt=f( 1,2 )+b[3].txt",
                  "var total=-1", "return total-  2"),
            event("x.val = -a.val * (b + c)", "flag = !ready", "t0.txt = f(1, 2) + b[3].txt",
                  "var total = -1", "return total - 2"))

    def test_a_conditional_and_the_lines_ending_with_a_colon(self):
        # ? and : spaced as other operators; a label, case, and default kept.
        self.assertFormats(event("x=a?1:b?2:3", "up:", "switch (x) {", "case 1:", "goto up",
                                 "default:", "}"),
                           event("x = a ? 1 : b ? 2 : 3", "up:", "switch (x) {", "  case 1:",
                                 "    goto up", "  default:", "}"))

    def test_the_form_of_an_own_attribute(self):
        # Spaced as a name; in a quoted text, left as written.
        self.assertFormats(event("'&val&'+=10", "t0.txt=\"'&val&'\"+'&txt&'", "x='&val&'-1"),
                           event("'&val&' += 10", "t0.txt = \"'&val&'\" + '&txt&'",
                                 "x = '&val&' - 1"))

    def test_left_as_written(self):
        lines = ['printh 00  00 ff', 'covx a, b,0,0', 'vis t0,1', 't0.txt="a  b"',
                 'sys0=1    // note  here', 't0.txt = "not closed']
        self.assertFormats(event(*lines),
                           event('printh 00  00 ff', 'covx a, b,0,0', 'vis t0,1', 't0.txt = "a  b"',
                                 'sys0 = 1    // note  here', 't0.txt = "not closed'))

    def test_blank_lines_and_trailing_spaces(self):
        text = ('include  "lib/a.nx"\nconst  LIMIT=4\n\n\n// The load.\non page0.load:\n\n'
                '  sys0=1   \n\n\n  sys1=2\n\n\non page0.up:\n  sys0=3\n\n')
        self.assertFormats(text, 'include "lib/a.nx"\nconst LIMIT = 4\n\n// The load.\n'
                                 'on page0.load:\n  sys0 = 1\n\n  sys1 = 2\n\non page0.up:\n'
                                 '  sys0 = 3\n')

    def test_a_function_heading(self):
        self.assertFormats("function  join( a:text,b : text )->text:\n  return a+b\n",
                           "function join(a: text, b: text) -> text:\n  return a + b\n")

    def test_program_nx(self):
        self.assertFormats("// Settings.\nint a=0, b=1\nbaud=9600\n\n\npage 0\n",
                           "// Settings.\nint a=0, b=1\nbaud = 9600\n\npage 0\n", program=True)

    def test_the_editors_own_language(self):
        self.assertFormats(event("if(sys0==1)", "{", "sys1=sys0+1", "}"),
                           event("if (sys0 == 1) {", "  sys1 = sys0 + 1", "}"), nxlang=False)

    def test_macros(self):
        # macros.nx: Editor code under macro headings, whatever the folder's
        # language; a comment above a heading stays with it.
        text = ("// Marks.\nmacro my name:\n\n  if(sys0==1)\n  {\n  sys1=2\n  }   \n\n\n"
                "macro other:\n  printh 4D\n")
        formatted = format_macros(text)
        self.assertEqual(formatted, "// Marks.\nmacro my name:\n  if (sys0 == 1) {\n    sys1 = 2\n"
                                    "  }\n\nmacro other:\n  printh 4D\n")
        self.assertEqual(format_macros(formatted), formatted)

    def test_labels_goto_and_return(self):
        self.assertFormats(event("up:  // again", "sys0+=1", "if(sys0<3)", "{", "end:", "goto up",
                                 "}", "return"),
                           event("up:  // again", "sys0 += 1", "if (sys0 < 3) {", "  end:",
                                 "  goto up", "}", "return"), nxlang=False)


class FolderFormatTest(FolderTestCase):

    def setUp(self):
        super().setUp()
        # Already in the formatter's layout, as the Editor's declaration is.
        self.write("program.nx", EDITOR_PROGRAM_DECLARATION + "\npage 0\n")

    def test_formats_and_checks(self):
        self.write("pages/page0.nx", event("if(sys0==1)", "{", "title.txt=\"a\"", "}"))
        self.assertEqual(format_folder(folder_reader(self.root)), {
            "pages/page0.nx": event("if (sys0 == 1) {", '  title.txt = "a"', "}")})

    def test_some_files(self):
        self.write("pages/page0.nx", event("sys0=1"))
        self.write("pages/second.nx", "on second.load:\n  sys0=2\n")
        self.assertEqual(list(format_folder(folder_reader(self.root), only=["pages/second.nx"])),
                         ["pages/second.nx"])

    def test_a_folder_that_does_not_build(self):
        self.write("pages/page0.nx", event("bogus.txt=1"))
        with self.assertRaisesRegex(NxwrightError, "the folder does not build"):
            format_folder(folder_reader(self.root))

    def test_a_file_program_nx_includes_through_another(self):
        # The build reads lib/b.nx through lib/a.nx, so it is formatted too.
        self.write("program.nx", 'include "lib/a.nx"\npage 0\n')
        self.write("lib/a.nx", 'include "b.nx"\nconst A=1\n')
        self.write("lib/b.nx", "const B=2\n")
        self.assertEqual(format_folder(folder_reader(self.root)),
                         {"lib/a.nx": 'include "b.nx"\nconst A = 1\n', "lib/b.nx": "const B = 2\n"})

    def test_a_change_of_the_editor_code_is_refused(self):
        self.write("pages/page0.nx", event("printh 00 00"))
        # As if the formatter joined a command's arguments, which would change its bytes.
        with mock.patch("nxwright.source.formatting.format_code",
                        lambda text, nxlang, program: text.replace("00 00", "0000")), \
                self.assertRaisesRegex(NxwrightError,
                                       "would change the code in strict Nextion syntax that "
                                       "page0 builds to"):
            format_folder(folder_reader(self.root))

    def test_macros_nx(self):
        # As Editor code, in this folder in nxlang too, and asked for alone,
        # as a code editor asks.
        self.write("macros.nx", "macro m:\n  if(sys0==1)\n  {\n  sys1=2\n  }\n")
        formatted = {"macros.nx": "macro m:\n  if (sys0 == 1) {\n    sys1 = 2\n  }\n"}
        self.assertEqual(format_folder(folder_reader(self.root)), formatted)
        self.assertEqual(format_folder(folder_reader(self.root), only=["macros.nx"]), formatted)
        self.assertEqual(self.run_format("--check")[1], "macros.nx\n")

    def test_a_change_of_a_macros_editor_code_is_refused(self):
        self.write("macros.nx", "macro m:\n  printh 00 00\n")
        with mock.patch("nxwright.source.formatting.format_macros",
                        lambda text: text.replace("00 00", "0000")), \
                self.assertRaisesRegex(NxwrightError,
                                       "would change the code in strict Nextion syntax that "
                                       "macro m builds to"):
            format_folder(folder_reader(self.root))

    def run_format(self, *options: str) -> tuple:
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = main(["format", str(self.root), *options])
        return code, output.getvalue(), errors.getvalue()

    def test_the_command(self):
        self.write("pages/page0.nx", event("sys0=1"))
        self.assertEqual(self.run_format("--check"),
                         (1, "pages/page0.nx\n", "nxwright format: 1 files would change\n"))
        self.assertEqual(self.text("pages/page0.nx"), event("sys0=1"))
        self.assertEqual(self.run_format(), (0, "Formatted pages/page0.nx\n", ""))
        self.assertEqual(self.text("pages/page0.nx"), event("sys0 = 1"))
        self.assertEqual(self.run_format("--check"), (0, "no file would change\n", ""))


class RenameTest(FolderTestCase):

    def setUp(self):
        super().setUp()
        self.write("pages/lib/show.nx", "const LIMIT = 4\n\nfunction show(value: number):\n"
                                         "  var shown = value + LIMIT\n  sys0 = shown\n")
        self.write("pages/page0.nx", 'include "lib/show.nx"\n\non title.up:\n  show(1)\n'
                                     '  vis title,1\n  second.title.txt = "a"\n')
        self.write("pages/second.nx", 'include "lib/show.nx"\n\non second.load:\n  show(2)\n')

    def rename_at(self, path: str, needle: str, new_name: str, inside: str = None) -> dict:
        """Renames the name at the first `needle` of `path`, or at `inside` it,
        and returns {file: its new text}."""
        lines = self.text(path).split("\n")
        line = next(number for number, text in enumerate(lines) if needle in text)
        column = lines[line].index(needle) + (needle.index(inside) if inside else 0)
        index = FolderIndex(self.root, FileTexts().read)
        edits = rename(index, path, line, column, new_name, folder_reader(self.root),
                       lambda file: (self.root / file).is_file())
        texts = {}
        for file, file_edits in edits.items():
            file_lines = self.text(file).split("\n")
            for place, new_text in sorted(file_edits, key=lambda edit: (edit[0].line,
                                                                        edit[0].start),
                                          reverse=True):
                text = file_lines[place.line]
                file_lines[place.line] = text[:place.start] + new_text + text[place.end:]
            texts[file] = "\n".join(file_lines)
        return texts

    def test_a_component(self):
        texts = self.rename_at("pages/page0.nx", "vis title", "heading", "title")
        self.assertIn('name = "heading"', texts["pages/page0.page.toml"])
        self.assertEqual(texts["pages/page0.nx"].count("heading"), 2)
        self.assertIn("on heading.up:", texts["pages/page0.nx"])
        self.assertEqual(sorted(texts), ["pages/page0.nx", "pages/page0.page.toml"])

    def test_a_component_a_macro_names(self):
        # A macro reaches only a component of global scope, with its page's
        # name. The rename changes macros.nx too, and the folder builds.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml").replace(
            'name = "title"\n', 'name = "title"\nvscope = 1\n'))
        self.write("macros.nx", 'macro mark:\n  page0.title.txt="m"\n')
        # The rename refuses one after which the folder would not build.
        texts = self.rename_at("pages/page0.nx", "vis title", "heading", "title")
        self.assertEqual(texts["macros.nx"], 'macro mark:\n  page0.heading.txt="m"\n')

    def test_a_macro(self):
        # Its heading and each call of it, a name with spaces too; the new
        # name is a plain one, as Rename Symbol takes any.
        self.write("macros.nx", "macro mark it:\n  printh 4D\n\nmacro other:\n  call mark it\n")
        texts = self.rename_at("macros.nx", "call mark it", "marker", "mark it")
        self.assertEqual(texts, {"macros.nx": "macro marker:\n  printh 4D\n\nmacro other:\n"
                                              "  call marker\n"})
        with self.assertRaisesRegex(NxwrightError, "'two words' is not a name"):
            self.rename_at("macros.nx", "call mark it", "two words", "mark it")
        # A name another macro has: the folder would not build.
        with self.assertRaisesRegex(NxwrightError, "would not build after the rename"):
            self.rename_at("macros.nx", "call mark it", "other", "mark it")

    def test_a_name_a_shared_library_gives_every_page(self):
        # The library names each page's own title: renaming one page's would
        # leave the library naming a component the other page lacks.
        self.write("pages/lib/show.nx", self.text("pages/lib/show.nx").replace(
            "sys0 = shown", "title.txt = shown"))
        with self.assertRaisesRegex(NxwrightError, "would not build after the rename"):
            self.rename_at("pages/page0.nx", "vis title", "heading", "title")

    def test_another_pages_component(self):
        texts = self.rename_at("pages/page0.nx", "second.title", "label", "title")
        self.assertIn('name = "label"', texts["pages/second.page.toml"])
        self.assertIn("second.label.txt", texts["pages/page0.nx"])

    def test_a_function_constant_local_and_parameter(self):
        texts = self.rename_at("pages/page0.nx", "show(1)", "display")
        self.assertEqual(sorted(texts), ["pages/lib/show.nx", "pages/page0.nx", "pages/second.nx"])
        self.assertIn("function display(", texts["pages/lib/show.nx"])
        self.assertIn("const MOST = 4", self.rename_at("pages/lib/show.nx", "LIMIT", "MOST")[
            "pages/lib/show.nx"])
        self.assertIn("sys0 = total", self.rename_at("pages/lib/show.nx", "shown", "total")[
            "pages/lib/show.nx"])
        self.assertIn("var shown = amount + LIMIT",
                      self.rename_at("pages/lib/show.nx", "value", "amount")["pages/lib/show.nx"])

    def test_refusals(self):
        with self.assertRaisesRegex(NxwrightError, "renamed by hand"):
            self.rename_at("pages/page0.nx", "second.title", "other", "second")
        with self.assertRaisesRegex(NxwrightError, "is not a name"):
            self.rename_at("pages/page0.nx", "vis title", "two words", "title")
        with self.assertRaisesRegex(NxwrightError, "no name to rename"):
            self.rename_at("pages/page0.nx", "vis title", "x", "vis")
        # Another component of the page already has that name.
        add_line = '\n[[component]]\nname = "taken"\ntype = "text"\nx = 0\ny = 0\nw = 9\nh = 9\n'
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") + add_line)
        with self.assertRaisesRegex(NxwrightError, "would not build after the rename"):
            self.rename_at("pages/page0.nx", "vis title", "taken", "title")

    def test_a_folder_that_does_not_build(self):
        self.write("pages/second.nx", 'include "lib/show.nx"\n\non second.load:\n  bogus.txt = 1\n')
        texts = self.rename_at("pages/lib/show.nx", "LIMIT", "MOST")
        self.assertIn("const MOST", texts["pages/lib/show.nx"])


class EditorCodeTest(FolderTestCase):

    def editor_code(self, page: str, path: str) -> list:
        return read_folder_source(folder_reader(self.root)).editor_code(page, path)

    def test_a_page_file_an_included_file_and_a_function(self):
        self.write("pages/lib/show.nx", "function show(value: number):\n  sys0 = value * 2 + 1\n")
        self.write("pages/page0.nx", 'include "lib/show.nx"\n\n// Loads.\non page0.load:\n'
                                     "  sys1 = 3\n  show(4)\n")
        [(title, code)] = self.editor_code("page0", "pages/page0.nx")
        self.assertEqual(title, "on page0.load")
        self.assertEqual([number for number, _ in code if number], [3, 5, 6, 6, 6])
        self.assertEqual(code[0], (3, "// ### Loads."))
        [(title, code)] = self.editor_code("page0", "pages/lib/show.nx")
        self.assertEqual(title, "function show")
        self.assertEqual({number for number, _ in code}, {2})

    def test_the_editors_own_language(self):
        self.write("app.toml", self.text("app.toml").replace('"nxlang"', '"nextion"'))
        self.write("pages/page0.nx", "on page0.load:\n  if (sys0 == 1) {\n    sys1 = 2\n  }\n")
        [(title, code)] = self.editor_code("page0", "pages/page0.nx")
        self.assertEqual(code, [(2, "if(sys0==1)"), (2, "{"), (3, "  sys1=2"), (4, "}")])


if __name__ == "__main__":
    unittest.main()
