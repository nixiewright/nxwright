"""The form '&name&', naming an attribute of the object whose event holds the
line, as the Editor 3.1.73 compiled and ran it: the build checks a line using
it as the Editor reads it, tests and the simulator run it so, and code that
belongs to no event refuses it."""
import unittest

from nxwright import NxwrightError
from nxwright.language.code_preprocessor import Owner, preprocess, with_own_attributes
from nxwright.language.nxlang import (ProgramNames, compile_page, compile_program,
                                      read_program_names)
from nxwright.project.dumper import ProjectDumper
from nxwright.source.page_source import compile_nxlang_page
from nxwright.source.project_files import build
from nxwright.source.source_folder import (export_dump, folder_reader, import_dump,
                                           read_folder_source, switch_to_nxlang)
from nxwright.testing import EditorMachine, SourceFolderRunner
from nxwright.testing.simulation import Simulation
from tests.test_build_checks import add_component
from tests.test_nxlang import COMPONENTS, NO_NAMES
from tests.test_project_writer import edit_text
from tests.test_simulation import SimulationTestCase, placed
from tests.test_source_folder import SourceFolderTestCase

# The lines the probe ran in n0's Touch Press event, as the build keeps them.
PROBED = ["sys1='&id&'", "'&val&'+=10", "covx '&val&',t1.txt,0,0", "t2.txt=\"'&val&'\"",
          "t3.txt=\"a'&id&'b\""]
NO_OWNER = (r"the form '&name&' stands for an attribute of the object whose event holds the "
            r"line, and this line has no such object \(\"Invalid Variables\"\)")


class ReplacementTest(unittest.TestCase):

    def test_a_line_as_the_editor_reads_it(self):
        # A quoted text's form too, as the Editor showed `n0.val` for
        # "'&val&'". A lone '&, and a name that is no word, stay as written.
        owner = Owner("n0", 3)
        for line, read in (("sys1='&id&'", "sys1=3"), ("'&val&'+=10", "n0.val+=10"),
                           ("covx '&val&',t1.txt,0,0", "covx n0.val,t1.txt,0,0"),
                           ("t2.txt=\"'&val&'\"", 't2.txt="n0.val"'),
                           ("t3.txt=\"a'&id&'b\"", 't3.txt="a3b"'),
                           ("sys0='&vall&'", "sys0=n0.vall"),
                           ("t1.txt=\"it'&s\"", "t1.txt=\"it'&s\""), ("sys0='&&'", "sys0='&&'")):
            with self.subTest(line=line):
                self.assertEqual(with_own_attributes(line, owner), read)


class OwnAttributeTest(SourceFolderTestCase):
    """Page first of the small test project, with its down event, and n0, a
    number with its own down event, then the texts t1, t2, and t3. n0 is
    the page's first component: its ID is 1."""

    def setUp(self):
        super().setUp()
        page = self.source / "pages" / "first.page.toml"
        edit_text(page, "events = []", 'events = ["down"]')
        with open(page, "a", encoding="utf-8", newline="\n") as file:
            file.write('\n[[component]]\nname = "n0"\ntype = "number"\nevents = ["down"]\n'
                       'x = 0\ny = 40\nw = 100\nh = 30\n')
        for name in ("t1", "t2", "t3"):
            add_component(page, name, limit=20)

    def write_events(self, text: str):
        (self.source / "pages" / "first.nx").write_text(text, encoding="utf-8", newline="\n")

    def write_probed(self):
        self.write_events("on first.down:\n  '&bco&'=2016\n\non n0.down:\n"
                          + "".join("  %s\n" % line for line in PROBED))

    def test_the_probed_lines_build_as_written(self):
        self.write_probed()
        export_dump(self.source, self.folder / "built")
        page = (self.folder / "built" / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("".join("    | %s\n" % line for line in PROBED), page)
        self.assertIn("    | '&bco&'=2016\n", page)

    def test_they_run_as_the_editors_simulator_ran_them(self):
        self.write_probed()
        runner = SourceFolderRunner(self.source)
        values = runner.run("first", [("n0", "down")], {"n0.val": 5})
        self.assertEqual((values["sys1"], values["n0.val"], values["t1.txt"], values["t2.txt"],
                          values["t3.txt"]), (1, 15, "15", "n0.val", "a1b"))
        self.assertEqual(runner.run("first", [("first", "down")])["first.bco"], 2016)

    def test_a_refusal_names_the_line_as_written_and_as_read(self):
        # Refused as n0.val="a" is.
        self.write_events("on n0.down:\n  '&val&'=\"a\"\n")
        self.assert_export_refused(r"first\.nx line 2: '&val&'=\"a\", as the Nextion Editor reads "
                                   r"it: n0\.val=\"a\": the Nextion Editor refuses to compile a "
                                   r"text given to a number \(\"Assignment operation failed\"\)")
        with self.assertRaisesRegex(NxwrightError, r"as the Nextion Editor reads it: "
                                                   r"n0\.val=\"a\""):
            SourceFolderRunner(self.source).run("first", [("n0", "down")])

    def test_a_form_with_spaces_is_read_as_the_editor_drops_them(self):
        # In an event, checked as n0.val; in program.nx, refused as '&id&' is.
        self.write_events("on n0.down:\n  '& val &'=\"a\"\n")
        self.assert_export_refused(r"first\.nx line 2: '& val &'=\"a\", as the Nextion Editor "
                                   r"reads it: n0\.val=\"a\"")
        self.write_events("")
        program = self.source / "program.nx"
        start = program.read_text(encoding="utf-8")
        program.write_text(start + "\nsys2='& id &'\n", encoding="utf-8", newline="\n")
        self.assert_export_refused(r"program\.nx line 3: sys2='&id&': " + NO_OWNER)
        program.write_text(start, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  '& val &'=1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_export_refused(r"macros\.nx line 2: '&val&'=1: " + NO_OWNER)

    def test_code_of_no_event_refuses_it(self):
        # Outside a quoted text, as the Editor refused it in program.s and in a
        # macro. In a quoted text there it stays as written, as the Editor's
        # simulator sent it (SimulatedTest).
        program = self.source / "program.nx"
        start = program.read_text(encoding="utf-8")
        program.write_text(start + "\nsys2='&id&'\n", encoding="utf-8", newline="\n")
        self.assert_export_refused(r"program\.nx line 3: sys2='&id&': " + NO_OWNER)
        program.write_text(start + "\nprints \"'&id&'\",0\n", encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "quoted")
        program.write_text(start, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  '&val&'=1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_export_refused(r"macros\.nx line 2: '&val&'=1: " + NO_OWNER)
        (self.source / "macros.nx").write_text("macro probe:\n  prints \"'&id&'\",0\n",
                                               encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "quoted in a macro")
        # A text given to events_from_text belongs to no page.
        with self.assertRaisesRegex(NxwrightError, "line 2: '&val&'=1: " + NO_OWNER):
            SourceFolderRunner(self.source).events_from_text("on n0.down:\n  '&val&'=1\n")

    def test_the_editor_code_view_and_an_extract_keep_it(self):
        comfortable = "on n0.down:\n  '&val&' += 10\n  sys1 = '&id&'\n"
        self.write_events(comfortable)
        [(title, lines)] = read_folder_source(folder_reader(self.source)).editor_code(
            "first", "pages/first.nx")
        self.assertEqual((title, [code for _, code in lines]),
                         ("on n0.down", ["'&val&'+=10", "sys1='&id&'"]))
        # The project as the Editor would save it, imported again: the
        # event's source is kept, as the Editor left it unchanged.
        built = self.folder / "built.HMI"
        build(self.source, built)
        ProjectDumper(built, self.folder / "built-dump").dump()
        import_dump(self.folder / "built-dump", self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         comfortable)

    def test_switching_to_nxlang_keeps_it(self):
        # A line nxlang reads as the Editor does is kept; one it would read
        # otherwise gets the parentheses that keep the Editor's meaning,
        # left to right, the form as written.
        self.write_events("on n0.down:\n  '&val&'+=10\n  sys0='&val&'+2*3\n"
                          "  '&val&'=sys0+sys1*sys2\n")
        switch_to_nxlang(self.source)
        self.assertIn('language = "nxlang"', (self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual((self.source / "pages" / "first.nx").read_text(
            encoding="utf-8").splitlines(),
                         ["on n0.down:", "  '&val&'+=10", "  sys0=('&val&'+2)*3",
                          "  '&val&'=(sys0+sys1)*sys2"])
        # It builds, the form replaced, and runs as the Editor's code did.
        export_dump(self.source, self.folder / "built")
        page = (self.folder / "built" / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("    | n0.val+=10\n", page)
        values = SourceFolderRunner(self.source).run("first", [("n0", "down")],
                                                     {"n0.val": 5, "sys1": 1, "sys2": 2})
        self.assertEqual((values["sys0"], values["n0.val"]), (51, 104))

    def test_in_nxlang_it_is_checked_as_the_name_it_stands_for(self):
        # The build checks the code nxlang writes, the form replaced, so
        # '&foo&' is refused as n0.foo is, word for word.
        switch_to_nxlang(self.source)
        refusals = []
        for line in ("n0.foo = 1", "'&foo&' = 1"):
            self.write_events("on n0.down:\n  %s\n" % line)
            with self.assertRaises(NxwrightError) as refused:
                export_dump(self.source, self.folder / "again")
            refusals.append(str(refused.exception))
        self.assertEqual(refusals[1], refusals[0])

    def test_switching_refuses_a_compound_assignment_it_cannot_rewrite(self):
        # Rewriting it needs the kind of n0's val, which the rewrite does not
        # know; nxlang would read it as n0.val-(sys0+sys1).
        self.write_events("on n0.down:\n  '&val&'-=sys0+sys1\n")
        with self.assertRaisesRegex(NxwrightError, r"would not build to the same code"):
            switch_to_nxlang(self.source)
        self.assertNotIn("nxlang", (self.source / "app.toml").read_text(encoding="utf-8"))

    def test_extracting_into_nxlang_takes_it(self):
        self.write_events("on n0.down:\n  n0.val+=10\n")
        switch_to_nxlang(self.source)
        built = self.folder / "built.HMI"
        build(self.source, built)
        ProjectDumper(built, self.folder / "built-dump").dump()
        # The Nextion Editor adds a line using the form to n0's event.
        page = self.folder / "built-dump" / "pages" / "00-first.txt"
        edit_text(page, "    | n0.val+=10\n", "    | n0.val+=10\n    | '&val&'+=1\n")
        import_dump(self.folder / "built-dump", self.source)
        self.assertIn("'&val&'+=1", (self.source / "pages" / "first.nx").read_text(
            encoding="utf-8"))
        values = SourceFolderRunner(self.source).run("first", [("n0", "down")], {"n0.val": 5})
        self.assertEqual(values["n0.val"], 16)

    def test_run_code_refuses_it(self):
        # Its code runs in no object's event.
        switch_to_nxlang(self.source)
        with self.assertRaisesRegex(NxwrightError, IN_NO_EVENT):
            SourceFolderRunner(self.source).run_code("sys0 = '&id&'")


class TypedTest(unittest.TestCase):

    def test_a_typed_form_answers_an_invalid_variable(self):
        # Typed, nothing replaces the form: it is a name the screen does not
        # know, as the Editor's simulator answered 0x1A to '&val&'=7. In a
        # quoted text it is text.
        machine = EditorMachine({"n0.val": 0, "t0.txt": ""})
        with self.assertRaises(KeyError):
            machine.run_instruction("'&val&'=7")
        machine.run_instruction("t0.txt=\"'&val&'\"")
        self.assertEqual((machine.values["n0.val"], machine.values["t0.txt"]), (0, "'&val&'"))


class SimulatedTest(SimulationTestCase):
    """page0 holding n0, a number with a down event, and t0, a text."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [placed("n0", "number", 0, 0, events=["down"]),
                            placed("t0", "text", 0, 60, txt_maxl=20)],
                  "on n0.down:\n  '&val&'+=10\n  t0.txt=\"'&id&'\"\n")

    def test_a_press_runs_its_own_attributes(self):
        simulation = Simulation(self.root)
        simulation.press("n0")
        simulation.release()
        values = simulation.values()
        self.assertEqual((values["n0.val"], values["t0.txt"]), (10, "1"))

    def test_a_typed_form_answers_an_invalid_variable(self):
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        sent.clear()
        simulation.serial_input("'&val&'=7")
        self.assertEqual([data.hex(" ") for data in sent], ["1a ff ff ff"])
        self.assertEqual(simulation.values()["n0.val"], 0)

    def test_a_macros_quoted_form_is_sent_as_written(self):
        # As the Editor's simulator sent it from a macro that an event called:
        # the text as written, naming no object's attribute.
        self.write("macros.nx", "macro m1:\n  print \"a'&name&'b\"\n")
        self.page("page0", [placed("n0", "number", 0, 0, events=["down"])],
                  "on n0.down:\n  call m1\n")
        sent = []
        simulation = Simulation(self.root, sending=sent.append)
        sent.clear()
        simulation.press("n0")
        simulation.release()
        self.assertEqual([data.hex(" ") for data in sent], ["61 27 26 6e 61 6d 65 26 27 62"])


def compile_event(code: str, owner=Owner("a", 1), key=("a", "down"), functions=None,
                  preamble: str = "") -> list:
    """Returns the Editor code `code` compiles to, as the event `key` of the
    page p of tests/test_nxlang.py, whose owner is `owner`, or which has
    none when it is None; the page's functions are `functions`, {name:
    (file, heading line, heading, body lines)}."""
    compiled = compile_page("p", COMPONENTS, ProgramNames(), [("p.nx", numbered(preamble))],
                            {key: ("p.nx", numbered(code))}, functions,
                            owners={key: owner} if owner else {})
    return preprocess(compiled.events[key], NO_NAMES)


def numbered(text: str) -> list:
    """`text`'s lines as (line number, line) pairs from 1, as the compiler takes them."""
    return list(enumerate(text.split("\n"), start=1)) if text else []


IN_A_FUNCTION = r"nxlang refuses the form '&name&' in a function"
IN_A_CONSTANT = r"nxlang refuses the form '&name&' in a constant"
IN_NO_EVENT = r"nxlang refuses the form '&name&' here: no object's event holds this line"


class NxlangTest(unittest.TestCase):
    """nxlang's events read the form as the Editor does; the rest refuses it."""

    def test_an_event_reads_it_as_the_editor_does(self):
        # In a quoted text too, as the Editor replaces it there. a is the
        # page's first component: its ID is 1.
        for code, read in (("'&val&' += 10", "a.val += 10"), ("x.val = '&id&'", "x.val = 1"),
                           ("t0.txt = \"'&val&'\"", "t0.txt = \"a.val\""),
                           ("t0.txt = \"'&val&'\" + t1.txt", "t0.txt = \"a.val\" + t1.txt")):
            with self.subTest(code=code):
                self.assertEqual(compile_event(code), compile_event(read))
        # The page's own event: the page is the object 0.
        self.assertEqual(compile_event("'&bco&' = 2016", Owner("p", 0), ("p", "down")),
                         compile_event("p.bco = 2016", Owner("p", 0), ("p", "down")))

    def test_a_refusal_gives_the_line_as_written(self):
        # Refused as a.val = "a" is, the line as written first.
        with self.assertRaises(NxwrightError) as refused:
            compile_event('a.val = "a"')
        with self.assertRaises(NxwrightError) as written:
            compile_event("'&val&' = \"a\"")
        self.assertEqual(str(written.exception),
                         "p.nx line 1: '&val&' = \"a\", as the Nextion Editor reads it: %s"
                         % refused.exception.reason)
        # A refusal's quick fix stays: here, declaring sys0 in program.nx.
        with self.assertRaises(NxwrightError) as refused:
            compile_event("sys0 = a.val")
        with self.assertRaises(NxwrightError) as written:
            compile_event("sys0 = '&val&'")
        self.assertIsNotNone(refused.exception.fix)
        self.assertEqual(written.exception.fix, refused.exception.fix)

    def test_a_switch_reads_its_case_labels_ahead_replaced(self):
        code = "switch (x.val) {\n  case %s:\n    x.val = 5\n}"
        self.assertEqual(compile_event(code % "'&id&'"), compile_event(code % "1"))

    def test_a_function_refuses_it(self):
        # A function's body runs from a hotspot nxlang adds, whose
        # attributes the form would name.
        functions = {"f": ("p.nx", 1, "function f():", [(2, "  '&val&' = 1")])}
        with self.assertRaisesRegex(NxwrightError, r"p\.nx line 2: " + IN_A_FUNCTION):
            compile_event("f()", functions=functions)

    def test_a_constant_refuses_it(self):
        # Its text reaches every line naming it, a function's too.
        with self.assertRaisesRegex(NxwrightError, r"p\.nx line 1: " + IN_A_CONSTANT):
            compile_event("t0.txt = greeting", preamble="const greeting = \"'&val&'\"")

    def test_code_of_no_object_refuses_it(self):
        # An event without an owner, and program.nx.
        for code in ("'&val&' = 1", "t0.txt = \"'&val&'\""):
            with self.subTest(code=code):
                with self.assertRaisesRegex(NxwrightError, r"p\.nx line 1: " + IN_NO_EVENT):
                    compile_event(code, owner=None)
        lines = [(1, "int counter=0"), (2, "counter = '&id&'")]
        with self.assertRaisesRegex(NxwrightError, r"line 2: " + IN_NO_EVENT):
            compile_program(lines, read_program_names(lines))

    def test_an_included_event_takes_each_pages_object(self):
        read = {"pages/lib/shared.nx": "on n0.down:\n  n0.val = '&id&'\n"}.get
        program = ProgramNames()
        for components, written in ((["home", "n0", "t0"], "n0.val=1"),
                                    (["other", "t0", "n0"], "n0.val=2")):
            with self.subTest(page=components[0]):
                compiled = compile_nxlang_page('include "lib/shared.nx"\n', components[0],
                                               components, program, read=read)
                self.assertEqual(preprocess(compiled.events[("n0", "down")], NO_NAMES),
                                 [written])


if __name__ == "__main__":
    unittest.main()
