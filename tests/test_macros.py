"""A project's macros: the Editor's block of them, comcode.sn, read and
written; a source folder's macros.nx; what the build refuses of them, as the
Editor refused it; and their running in tests, the simulator, and the
debugger, as the Editor's simulator ran them."""
import unittest

from nxwright import NxwrightError
from nxwright.language.resource_names import ResourceNames
from nxwright.project.dumper import ProjectDumper
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION
from nxwright.source.folder_check import check_folder
from nxwright.source.formatting import format_folder
from nxwright.source.macros_source import (block_from_macros, keep_comfortable_macros,
                                           macros_from_block, macros_to_source)
from nxwright.source.source_folder import (export_dump, folder_reader, import_dump,
                                           switch_to_nxlang)
from nxwright.testing import SourceFolderRunner
from nxwright.testing.recording import Recorder, recording
from nxwright.testing.simulation import Simulation
from tests.test_build_checks import add_component
from tests.test_nxlang import MACRO_CALLER
from tests.test_project_writer import edit_text
from tests.test_simulation import SimulationTestCase, placed
from tests.test_source_folder import SourceFolderTestCase

# As the Editor saved them: each macro's name, its number of lines, then its
# lines, each ending in CR LF, in UTF-8 whatever the project's encoding.
BLOCK = ('newcall\r\n2\r\nprinth 4D\r\nprints "café",0\r\nnewcall1\r\n0\r\n'
         'my name\r\n1\r\nsys0=7\r\n').encode("utf-8")
MACROS = [("newcall", ["printh 4D", 'prints "café",0']), ("newcall1", []),
          ("my name", ["sys0=7"])]
SOURCE = ('macro newcall:\n  printh 4D\n  prints "café",0\n\nmacro newcall1:\n\n'
          "macro my name:\n  sys0=7\n")


def _macro_chain(count: int) -> str:
    """Returns macros.nx's text of the macros m1 to m<count>, each calling the next."""
    return "\n".join("macro m%d:\n  %s\n" % (n, "call m%d" % (n + 1) if n < count else "printh 4D")
                     for n in range(1, count + 1))


class BlockTest(unittest.TestCase):

    def test_read_and_written_back(self):
        self.assertEqual(macros_from_block(BLOCK), (MACROS, []))
        self.assertEqual(block_from_macros(MACROS), BLOCK)

    def test_what_is_refused(self):
        # The Editor's tab refused a hyphen ("Illegal character in Name-"), a
        # digit first ("First character of a Name can not be number"), and a
        # name another macro has ("duplicate name").
        for block, message in ((b"newcall\r\n2\r\nsys0=1\r\n", "is cut short"),
                               (b"newcall\r\nx\r\n", "count of lines"),
                               (b"my-name\r\n0\r\n", "my-name: a macro's name"),
                               (b"9lives\r\n0\r\n", "9lives: a macro's name"),
                               (b"twin\r\n0\r\ntwin\r\n0\r\n", "twin twice"),
                               # A digit beyond ASCII, which int() does not take.
                               ("m\r\n²\r\n".encode("utf-8"), "count of lines"),
                               (b"\xff\r\n0\r\n", "UTF-8")):
            with self.subTest(block=block):
                with self.assertRaisesRegex(NxwrightError, message):
                    macros_from_block(block)


    def test_a_blank_line_is_dropped_with_a_warning(self):
        # The tab drops a blank line, so only a block written by hand holds
        # one. A macro with one compiled and ran in the Nextion Editor.
        self.assertEqual(macros_from_block(b"gap\r\n3\r\nprinth 4D\r\n  \r\n\r\n"),
                         ([("gap", ["printh 4D"])],
                          ["macro gap: 2 blank lines dropped; the Nextion Editor compiles them "
                           "to nothing"]))


class SourceTest(unittest.TestCase):

    def test_the_source_text(self):
        self.assertEqual(macros_to_source(MACROS), SOURCE)

    def test_a_comment_above_a_heading_is_kept_in_the_macro(self):
        # As an event's: the build puts it first in the macro's code, marked,
        # and the extract moves it back above the heading.
        self.assertEqual(macros_to_source([("noted", ["// ### Says M", "printh 4D"])]),
                         "// Says M\nmacro noted:\n  printh 4D\n")

    def test_comfortable_text_kept_where_it_builds_alike(self):
        old = "macro newcall:\n  printh 4D\n  prints \"café\", 0\n\nmacro my name:\n  sys0 = 8\n"
        kept = keep_comfortable_macros(SOURCE, old, ResourceNames([], []))
        self.assertEqual(kept, 'macro newcall:\n  printh 4D\n  prints "café", 0\n\n'
                               "macro newcall1:\n\nmacro my name:\n  sys0=7\n")


class FolderTest(SourceFolderTestCase):
    """The small test project, its first page given a text t0 of local scope
    and a text t1 of global scope, and macros."""

    def setUp(self):
        super().setUp()
        pages = self.source / "pages"
        add_component(pages / "first.page.toml", "t0")
        add_component(pages / "first.page.toml", "t1")
        edit_text(pages / "first.page.toml", 'name = "t1"\n', 'name = "t1"\nvscope = 1\n')
        edit_text(pages / "first.page.toml", "events = []", 'events = ["down"]')

    def write_macros(self, text: str):
        (self.source / "macros.nx").write_text(text, encoding="utf-8", newline="\n")

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def test_built_and_extracted_back(self):
        self.write_macros(SOURCE)
        self.write_code("call newcall")
        export_dump(self.source, self.folder / "again")
        self.assertEqual((self.folder / "again" / "macros.s").read_bytes(), BLOCK)
        # And back: a dump holding the Editor's block, extracted into a fresh
        # folder. (The dump's writing into a project is test_project_writer's.)
        import_dump(self.dump_with_macros(BLOCK), self.folder / "fresh")
        self.assertEqual((self.folder / "fresh" / "macros.nx").read_text(encoding="utf-8"),
                         SOURCE)

    def test_a_project_without_macros(self):
        # Its folder has no macros.nx, and an update removes one the folder had.
        export_dump(self.source, self.folder / "again")
        self.assertFalse((self.folder / "again" / "macros.s").exists())
        self.write_macros(SOURCE)
        import_dump(self.dump_with_macros(None), self.source)
        self.assertFalse((self.source / "macros.nx").exists())

    def test_a_macros_file_without_macros(self):
        # The Editor removes the block once every macro is deleted.
        self.write_macros("")
        export_dump(self.source, self.folder / "again")
        self.assertFalse((self.folder / "again" / "macros.s").exists())

    def test_an_extract_names_a_block_it_refuses(self):
        with self.assertRaisesRegex(NxwrightError, r"macros\.s: my-name: a macro's name"):
            import_dump(self.dump_with_macros(b"my-name\r\n0\r\n"), self.folder / "fresh")

    def dump_with_macros(self, block):
        """Returns a dump of the small project with `block` as its macros.s,
        or with none."""
        dump = self.folder / ("dump-%d" % len(list(self.folder.iterdir())))
        ProjectDumper(self.project, dump).dump()
        if block is not None:
            (dump / "macros.s").write_bytes(block)
        return dump

    def test_spaces_ending_a_line_are_dropped(self):
        # The Nextion Editor's compile drops them: the build writes none,
        # in a macro's comment or its code, and extracting drops them.
        self.write_macros("// Says hi \nmacro my name:\n  sys0=7 \t\n")
        export_dump(self.source, self.folder / "again")
        self.assertEqual((self.folder / "again" / "macros.s").read_bytes(),
                         b"my name\r\n2\r\n// ### Says hi\r\nsys0=7\r\n")
        import_dump(self.dump_with_macros(b"my name\r\n1\r\nsys0=7 \t\r\n"), self.folder / "fresh")
        self.assertEqual((self.folder / "fresh" / "macros.nx").read_text(encoding="utf-8"),
                         "macro my name:\n  sys0=7\n")

    def test_a_comment_above_no_heading_is_kept_in_the_folder_only(self):
        # Where the project changed the code of the macro after it, too.
        text = ("macro a:\n  sys0 = 1\n\n// --- More ---\n\nmacro b:\n  sys0 = 2\n\n"
                "// The end.\n")
        self.write_macros(text)
        export_dump(self.source, self.folder / "built")
        macros = (self.folder / "built" / "macros.s").read_bytes()
        self.assertNotIn(b"More", macros)
        self.assertNotIn(b"The end", macros)
        import_dump(self.dump_with_macros(b"a\r\n1\r\nsys0=1\r\nb\r\n1\r\nsys0=3\r\n"),
                    self.source)
        self.assertEqual((self.source / "macros.nx").read_text(encoding="utf-8"),
                         text.replace("sys0 = 2", "sys0=3"))

    def test_an_update_keeps_comfortable_text(self):
        self.write_macros("macro my name:\n  sys0 = 7\n")
        import_dump(self.dump_with_macros(b"my name\r\n1\r\nsys0=7\r\n"), self.source)
        self.assertEqual((self.source / "macros.nx").read_text(encoding="utf-8"),
                         "macro my name:\n  sys0 = 7\n")

    def add_to_program(self, line: str):
        """Adds `line` at the end of program.nx."""
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        program.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf-8", newline="\n")

    def assert_build_refused(self, message: str):
        with self.assertRaisesRegex(NxwrightError, message):
            export_dump(self.source, self.folder / ("refused%d" % len(list(self.folder.iterdir()))))

    def test_what_the_build_refuses(self):
        # What the Editor refused as it compiled, and what pages' code is
        # refused, in macros too.
        cases = [
            ("macro m:\n  printh 4D\n", ("call nosuch",),
             r"first\.nx line 2: call nosuch: the folder has no macro nosuch"),
            ("macro m:\n  printh 4D\n", ("call M",), r"has no macro M"),
            ("macro m:\n  printh 4D\n\nmacro m:\n  printh 4E\n", (),
             r"macros\.nx line 4: macro m appears twice"),
            ("macro my-name:\n  printh 4D\n", (), r"macros\.nx line 1: my-name: a macro's name"),
            ("macro m:\n  t1.txt=\"g\"\n", (),
             r"macros\.nx line 2: t1: a macro names a component with its page"),
            ("macro m:\n  first.t0.txt=\"g\"\n", (),
             r"macros\.nx line 2: first\.t0: a macro cannot reach a component of local scope"),
            ("macro m:\n  call nosuch\n", (), r"macros\.nx line 2: call nosuch"),
            # A command naming a component, by name with its page's or not:
            # the Editor refused `vis t0,0` and `click page0.b0,1`, b0 global,
            # saying "Invalid Component ID".
            ("macro m:\n  vis t0,0\n", (),
             r"macros\.nx line 2: vis t0: in a macro, a command takes a component's number"),
            ("macro m:\n  click first.t1,1\n", (), r"macros\.nx line 2: click first\.t1: in a "),
            ("macro m:\n  goto later\n", (), r"macros\.nx line 2: goto later: the "
                                             r"Nextion Editor finds"),
            ("macro m:\n  first.t1.w=10\n", (), r"macros\.nx line 2: .*code cannot change"),
            # The escapes and a variable's attributes, as in a page's code.
            ('macro m:\n  first.t1.txt="a\\qb"\n', (),
             r"macros\.nx line 2: .*Improper use of escape characters"),
            ("macro m:\n  sys0=first.vg.val\n", (), r"macros\.nx line 2: .*Invalid Variables"),
            # A name alone that names nothing, as in a page's code: the
            # Editor refused `sys0=abc` in a macro, and took `sys0=RED+dim`.
            ("macro m:\n  sys0=abc\n", (),
             r"macros\.nx line 2: sys0=abc: the Nextion Editor knows no abc"),
            ("macro m\n  printh 4D\n", (), r"macros\.nx line 1: expected a 'macro <name>:'"),
        ]
        # vg: a variable of a text, of global scope, which a macro reaches.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "vg"\ntype = "variable"\nvscope = 1\nsta = 1\n')
        for number, (macros, code, message) in enumerate(cases):
            with self.subTest(macros=macros, code=code):
                self.write_macros(macros)
                self.write_code(*code)
                self.assert_build_refused(message)

    def test_what_the_build_takes(self):
        # A component of global scope with its page's name; a command giving
        # a component's number, or a variable or value holding one, as the
        # Editor compiled `vis sys0,0` and `vis page0.n0.val,0`; another
        # macro; a label and its goto, and a return; program.nx's variables.
        self.write_macros('macro m:\n  first.t1.txt="g"\n  click 2,1\n  vis sys0,0\n'
                          "  tsw first.t1.x,1\n  call other\n"
                          "  goto later\n  later:\n  sys0=RED+dim\n  return\n\n"
                          "macro other:\n  printh 4D\n")
        self.write_code("call m")
        export_dump(self.source, self.folder / "again")

    def test_a_component_of_global_scope_by_its_type_default(self):
        # A page file leaves out what equals its type's default, so with the
        # folder's texts global by default, t2 is global without saying so.
        edit_text(self.source / "defaults.toml", "[text.attributes]\nvscope = 0\n",
                  "[text.attributes]\nvscope = 1\n")
        add_component(self.source / "pages" / "first.page.toml", "t2")
        self.write_macros('macro m:\n  first.t2.txt="g"\n')
        export_dump(self.source, self.folder / "again")

    def test_program_variables_undeclared_in_a_macro(self):
        edit_text(self.source / "program.nx", EDITOR_PROGRAM_DECLARATION + "\n", "")
        self.write_macros("macro m:\n  sys1=2\n")
        self.assert_build_refused(r"macros\.nx line 2: .*sys1")

    def test_nxlang_code_calls_a_macro(self):
        # A page's code calls any macro whose clicks the build can follow;
        # program.nx calls one that clicks nothing. A click of an ID the page
        # lacks runs nothing. A chain of 7 calls and clicks is the most.
        switch_to_nxlang(self.source)
        self.write_macros("macro m:\n  printh 4D\n  call far\n\nmacro far:\n  click 99,1\n\n"
                          "macro quiet:\n  printh 4E\n\n" + _macro_chain(7))
        self.write_code("call m", "call m1")
        self.add_to_program("call quiet")
        export_dump(self.source, self.folder / "built")
        self.assertIn("call quiet", (self.folder / "built" / "program.s").read_text("utf-8"))

    def test_what_nxlang_refuses_of_a_macro_it_calls(self):
        # Where nxlang code calls it, directly or through another macro.
        switch_to_nxlang(self.source)
        cases = [
            # A click whose event the build cannot tell.
            ("macro m:\n  click sys0,1\n", ("call m",),
             r"macros\.nx line 2: click sys0,1: .*a component's ID and 0 or 1"),
            ("macro m:\n  call other\n\nmacro other:\n  click 1,sys0\n", ("call m",),
             r"macros\.nx line 5: click 1,sys0: "),
            # Coming back to a macro already running.
            ("macro m:\n  call other\n\nmacro other:\n  call m\n", ("call m",),
             r"macro m -> macro other -> macro m"),
            # 8 calls and clicks from first.down.
            (_macro_chain(8), ("call m1",), r"first\.down -> macro m1 -> .* nest 8 deep"),
        ]
        for macros, code, message in cases:
            with self.subTest(macros=macros):
                self.write_macros(macros)
                self.write_code(*code)
                self.assert_build_refused(message)

    def test_program_nx_calls_no_macro_that_clicks(self):
        # program.nx has no page whose events the build could follow.
        switch_to_nxlang(self.source)
        self.write_macros("macro m:\n  call tap\n\nmacro tap:\n  click 1,1\n")
        self.add_to_program("call m")
        self.assert_build_refused(r"macros\.nx line 5: click 1,1: .*program\.nx")

    def test_formatting_lays_the_macros_out_as_editor_code(self):
        # As a code editor asks the formatter for macros.nx alone. The file is
        # Editor code in either language, so a folder in nxlang lays it out
        # alike, never as nxlang.
        self.write_macros("macro m:\n  if(sys0==1)\n  {\n    sys1=2\n  }\n")
        formatted = {"macros.nx": "macro m:\n  if (sys0 == 1) {\n    sys1 = 2\n  }\n"}
        self.assertEqual(format_folder(folder_reader(self.source), only=["macros.nx"]), formatted)
        switch_to_nxlang(self.source)
        self.assertEqual(format_folder(folder_reader(self.source), only=["macros.nx"]), formatted)

    def test_a_macros_file_that_does_not_read_leaves_calls_unchecked(self):
        # As in the build, whose build of the macros then says what is wrong,
        # once: a test's compile of a page does not stop on it.
        self.write_macros("macro m\n  printh 4D\n")
        self.write_code("call m")
        SourceFolderRunner(self.source).compile("first")

    def test_the_checks_report_it_at_its_line(self):
        self.write_macros("macro m:\n  printh 4D\n  call nosuch\n")
        found = check_folder(folder_reader(self.source), lambda path: (self.source / path).is_file())
        self.assertEqual([(finding.file, finding.line) for finding in found.errors()],
                         [("macros.nx", 3)])


class RunTest(SimulationTestCase):
    """Macros run by tests, the simulator, and the debugger, as a probe ran
    them in the Editor's simulator: page0's button b0
    calls `mark`, which adds to page0's text `log`, of global scope."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("b0", "button", 0, 0),
                            placed("log", "text", 0, 100, txt="", txt_maxl=50, vscope=1)],
                  "on b0.down:\n  call mark\n")
        self.write("macros.nx", '// Marks the log.\nmacro mark:\n  page0.log.txt+="m"\n')

    def test_a_test_runs_it(self):
        values = SourceFolderRunner(self.root).run("page0", [("b0", "down")], {"log.txt": ""})
        self.assertEqual(values["log.txt"], "m")

    def test_the_simulator_runs_it_from_a_press_and_the_serial_line(self):
        simulation = Simulation(self.root)
        simulation.press("b0")
        simulation.release()
        simulation.serial_input("call mark")
        # One the project lacks is ignored.
        simulation.serial_input("call nosuch")
        self.assertEqual(simulation.values()["log.txt"], "mm")
        self.assertEqual(simulation.log[-1][1], "receives call nosuch")

    def test_its_click_gives_a_components_number(self):
        # A macro names a component by its number alone: b0 is 1.
        self.write("macros.nx", 'macro mark:\n  page0.log.txt+="m"\n\nmacro tap:\n  click 1,1\n')
        simulation = Simulation(self.root)
        simulation.serial_input("call tap")
        self.assertEqual(simulation.values()["log.txt"], "m")

    def test_a_test_reaches_a_component_by_its_number(self):
        self.write("pages/page0.nx", "on b0.down:\n  call mark\n\non b0.up:\n  click 1,1\n")
        values = SourceFolderRunner(self.root).run("page0", [("b0", "up")], {"log.txt": ""})
        self.assertEqual(values["log.txt"], "m")

    def test_an_id_no_component_has(self):
        # The Editor's simulator answered 02, an invalid component ID: to the
        # instruction itself, and from an event, which went on.
        self.write("macros.nx", 'macro mark:\n  page0.log.txt+="m"\n\n'
                                'macro hide:\n  vis 99,0\n  page0.log.txt+="h"\n')
        simulation = Simulation(self.root)
        simulation.serial_input("vis 99,0")
        simulation.serial_input("call hide")
        self.assertEqual([line for _, line in simulation.log][-5:],
                         ["receives vis 99,0", "sends 02 ff ff ff", "receives call hide",
                          "vis 99: no component has that ID", "sends 02 ff ff ff"])
        self.assertEqual(simulation.values()["log.txt"], "h")

    def test_the_debugger_records_its_lines_in_macros_nx(self):
        with recording(Recorder()) as recorder:
            SourceFolderRunner(self.root).run("page0", [("b0", "down")], {"log.txt": ""})
        self.assertEqual([(step.place.file, step.place.line, step.place.owner, len(step.frames))
                          for step in recorder.steps],
                         [("pages/page0.nx", 2, "b0.down", 1), ("macros.nx", 3, "macro mark", 2)])


class NxlangRunTest(SimulationTestCase):
    """A macro that nxlang code calls, as a test runs it."""
    language = "nxlang"

    def test_an_event_a_macro_runs_keeps_its_callers_temporaries(self):
        self.program("page page0\n")
        self.page("page0", [placed("b0", "button", 0, 0), placed("b1", "button", 0, 60),
                            placed("x", "number", 0, 120), placed("a", "number", 0, 180),
                            placed("b", "number", 0, 240), placed("c", "number", 0, 300)],
                  MACRO_CALLER)
        # b1 is object 2, after the page and b0.
        self.write("macros.nx", "macro tap:\n  click 2,1\n")
        values = SourceFolderRunner(self.root).run(
            "page0", [("b0", "down")], {"a.val": 3, "b.val": 4, "c.val": 0, "x.val": 0})
        self.assertEqual((values["x.val"], values["c.val"]), (6, -9))


if __name__ == "__main__":
    unittest.main()
