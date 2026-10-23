"""Tests of nxlang, the nxwright language: compiling it, running what it compiles to, and
building and importing source folders that use it."""
from pathlib import Path
import random
import re
import unittest

from nxwright.source.project_files import build
from nxwright.project.dumper import ProjectDumper
from nxwright import NxwrightError
from nxwright.language.code_preprocessor import preprocess
from nxwright.source.nx_files import read_page_files
from nxwright.source.page_source import compile_nxlang_page
from nxwright.source.editor_code_merge import nxlang_import_changes
from nxwright.language.resource_names import ResourceNames
from nxwright.language.editor_code import (editor_equivalent, global_declarations,
                                           keep_editor_meaning, without_global_declarations,
                                           write_expression)
from nxwright.language.nxlang import (Binary, Literal, Macro, ProgramNames, compile_page,
                                      compile_program, read_program_names)
from nxwright.source import source_folder
from nxwright.source.folder_check import check_folder
from nxwright.source.source_folder import export_dump, folder_reader, import_dump, switch_to_nxlang
from nxwright.testing import EditorMachine
from nxwright.testing.editor_machine import c_operation, int32
from tests.test_folder_check import edited_page_file
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase, assert_same_dump_files

NO_NAMES = ResourceNames([], [])
COMPONENTS = ["p", "a", "b", "c", "d", "x", "r", "t0", "t1"]
KEY = ("p", "down")


def compile_lines(code: str, program: ProgramNames = None, preamble: str = "",
                  components=COMPONENTS, object_types: dict = None) -> list:
    """Returns the lines of Editor code that `code` compiles to, as the event p.down
    of a page p with the components COMPONENTS, the types of the pages' objects
    being `object_types`, {page: {name: type}}, as compile_page takes them."""
    compiled = compile_page("p", components, program or ProgramNames(),
                            [("p.nx", _numbered(preamble) if preamble else [])],
                            {KEY: ("p.nx", _numbered(code))}, object_types=object_types)
    return preprocess(compiled.events[KEY], NO_NAMES)


def _numbered(text: str) -> list:
    """Returns `text` as (line number, line) pairs from 1, as the compiler takes it."""
    return list(enumerate(text.rstrip("\n").split("\n"), start=1))


VALUES = {"a.val": 7, "b.val": -3, "c.val": 5, "d.val": 2, "x.val": 0, "r.val": 0,
          "t0.txt": "", "t1.txt": "ab"}


def run(code: str, values: dict = None, **options) -> dict:
    """Compiles `code` as compile_lines does, runs it from VALUES updated with
    `values`, and returns the values after it."""
    lines = compile_lines(code, **options)
    start = dict(VALUES, **(values or {}))
    # Generated variables start at 0 or "", as the Editor creates them.
    for line in lines:
        for name in re.findall(r"_[vtspr][0-9]+\.(?:val|txt)", line):
            start.setdefault(name, "" if name.endswith(".txt") else 0)
    return EditorMachine(start).run(lines)


# Compiling is the slow part of the tests that run a page, and many tests run the
# same page. So each compiled page is kept for the rest of the run, keyed by
# everything its compilation reads: its text, its included files, and `program`.
# Callers must not change the events they get.
_COMPILED_PAGES = {}


def run_page(text: str, values: dict = None, event: tuple = KEY, files: dict = None,
             program: ProgramNames = None) -> EditorMachine:
    """Compiles `text`, a page's .nx file, with the files it includes, `files` as
    {path: text}, and the names `program` declares. Runs `event` from VALUES updated
    with `values`, and returns the machine."""
    program = program or ProgramNames()
    key = (text, tuple(sorted((files or {}).items())), repr(program))
    events = _COMPILED_PAGES.get(key)
    if events is None:
        compiled = compile_nxlang_page(text, "p", COMPONENTS, program, read=reader(files))
        events = {key: preprocess(lines, NO_NAMES) for key, lines in compiled.events.items()}
        _COMPILED_PAGES[key] = events
    start = dict(VALUES, **(values or {}))
    for lines in events.values():
        for line in lines:
            for name in re.findall(r"_[vtspr][0-9]+\.(?:val|txt)", line):
                start.setdefault(name, "" if name.endswith(".txt") else 0)
    machine = EditorMachine(start, events)
    machine.run(events[event])
    return machine


def reader(files: dict):
    """Returns a read(path) function for the compiler that gives the text of each of
    `files` {path: text}, and refuses any other path as missing."""
    def read(path: str) -> str:
        if path not in (files or {}):
            raise NxwrightError("%s is missing" % path)
        return files[path]
    return read


def call_function(files: dict, include: str, code: str, values: dict = None,
                  program: ProgramNames = None) -> dict:
    """Runs `code` in an event of a page including `include`, one of `files`
    {path: text}; returns the values after it. For testing library functions."""
    page = 'include "%s"\n\non p.down:\n%s\n' % (include, block(code))
    return run_page(page, values, files=files, program=program).values


# Random expressions, as trees of tuples. Their values are computed in Python, with
# the screen's arithmetic, to check what the compiled code computes.

_OPERATORS = ["+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>"]


def random_expression(generator: random.Random, depth: int):
    """Returns a random expression at most `depth` deep: ("name", "a.val"),
    ("number", -3), ("minus", expression), or ("binary", operator, left, right)."""
    if depth == 0 or generator.random() < 0.25:
        if generator.random() < 0.6:
            return ("name", generator.choice(["a.val", "b.val", "c.val", "d.val"]))
        return ("number", generator.randint(-9, 9))
    if generator.random() < 0.1:
        return ("minus", random_expression(generator, depth - 1))
    operator = generator.choice(_OPERATORS)
    # C gives no defined result for a shift by a negative or large count.
    right = (("number", generator.randint(0, 4)) if operator in ("<<", ">>")
             else random_expression(generator, depth - 1))
    return ("binary", operator, random_expression(generator, depth - 1), right)


def evaluate(expression, values: dict) -> int:
    """Returns the value of a random expression, with `values` for its names."""
    if expression[0] == "name":
        return values[expression[1]]
    if expression[0] == "number":
        return expression[1]
    if expression[0] == "minus":
        return int32(-evaluate(expression[1], values))
    return c_operation(expression[1], evaluate(expression[2], values), evaluate(expression[3], values))


def source_text(expression, generator: random.Random) -> str:
    """Returns the expression as nxlang text, fully parenthesised, with random spacing."""
    space = generator.choice(["", " "])
    if expression[0] == "name":
        return expression[1]
    if expression[0] == "number":
        # A negative number in parentheses: "a--1" would read as a decrement.
        return str(expression[1]) if expression[1] >= 0 else "(%d)" % expression[1]
    if expression[0] == "minus":
        return "-(" + source_text(expression[1], generator) + ")"
    right = source_text(expression[3], generator)
    # A space before a right side such as "-(a.val)": "b.val--(a.val)" would read
    # as a decrement too.
    return "(%s%s%s%s%s)" % (source_text(expression[2], generator), space, expression[1],
                             " " if right.startswith("-") else space, right)


def to_tree(expression):
    """Returns the expression as the compiler's own tree, for write_expression to
    print with the fewest parentheses."""
    if expression[0] == "name":
        from nxwright.language.nxlang import Reference
        name, attribute = expression[1].split(".")
        return Reference(((name, None), (attribute, None)), "number")
    if expression[0] == "number":
        return Literal(str(expression[1]), "number")
    if expression[0] == "minus":
        return Binary("-", Literal("0", "number"), to_tree(expression[1]))
    return Binary(expression[1], to_tree(expression[2]), to_tree(expression[3]))


class ExpressionTest(unittest.TestCase):

    def test_hex_constants(self):
        # nxlang reads numbers as C does, in 32 bits. A hex constant the Editor
        # reads, its digits in pairs, with no sign, within 32 bits, is kept as
        # written; another is written so that the Editor reads it.
        for code, line, value in (
                ("x.val = 0x1f + 1", "x.val=0x1f+1", 32),
                ("x.val = 0xFFFFFFFF", "x.val=0xFFFFFFFF", -1),
                ("x.val = 0x1", "x.val=0x01", 1),
                ("x.val = 0x123", "x.val=0x0123", 291),
                ("x.val = -0x10", "x.val=-16", -16),
                ("x.val = -0xFFFFFFFF", "x.val=1", 1),
                ("x.val = 2 - 0x10", "x.val=2-0x10", -14),
                ("x.val = 2 * -0x10", "x.val=2*-16", -32),
                # Past 32 bits, its low 32 bits, as C keeps them.
                ("x.val = 0x0100000005", "x.val=0x00000005", 5),
                ("x.val = 0x1FFFFFFFF", "x.val=0xFFFFFFFF", -1)):
            with self.subTest(code=code):
                self.assertEqual(compile_lines(code), [line])
                self.assertEqual(run(code)["x.val"], value)
        # Constants alike, and a command's arguments: a minus right after an
        # operand subtracts, and any other is a sign.
        self.assertEqual(compile_lines("x.val = ODD\nr.val = LOW",
                                       preamble="const ODD = 0x1\nconst LOW = -0x10\n"),
                         ["x.val=0x01", "r.val=-16"])
        self.assertEqual(compile_lines('fill 0,0,10,10,0xF800\nfill 0,0,10,10,0xF\n'
                                       'substr t0.txt,t1.txt,a.val-0x1,-0x1\nprints "0x1",0'),
                         ["fill 0,0,10,10,0xF800", "fill 0,0,10,10,0x0F",
                          "substr t0.txt,t1.txt,a.val-0x01,-1", 'prints "0x1",0'])

    def test_hex_in_an_ints_starting_value(self):
        # The Editor refuses hex there (the vendor's rule 1.8): it is written
        # in decimal, as its 32 bits.
        self.assertEqual(compile_program(_numbered("int mask=0x8005, low=-0x10, odd=0x1, "
                                                   "big=0xFFFFFFFF, n=7"), ProgramNames()),
                         [(1, "int mask=32773, low=-16, odd=1, big=-1, n=7")])

    def test_random_expressions_compute_as_written(self):
        generator = random.Random(1)
        checked = 0
        for _ in range(400):
            expression = random_expression(generator, 4)
            try:
                expected = evaluate(expression, VALUES)
            except ZeroDivisionError:
                continue
            # Once fully parenthesised, once with the fewest parentheses.
            for text in (source_text(expression, generator), write_expression(to_tree(expression))):
                with self.subTest(code=text):
                    self.assertEqual(run("x.val = " + text)["x.val"], expected)
            checked += 1
        self.assertGreater(checked, 300)

    def test_precedence(self):
        self.assertEqual(run("x.val = a.val + b.val * c.val")["x.val"], 7 + -3 * 5)
        self.assertEqual(run("x.val = (a.val + b.val) * c.val")["x.val"], (7 - 3) * 5)
        self.assertEqual(run("x.val = a.val - b.val - c.val")["x.val"], 7 + 3 - 5)
        self.assertEqual(run("x.val = a.val - (b.val - c.val)")["x.val"], 7 - (-3 - 5))
        self.assertEqual(run("x.val = 1 << 2 + 1")["x.val"], 8)
        self.assertEqual(run("x.val = a.val & 3 | 8")["x.val"], 7 & 3 | 8)
        # C's order: comparisons bind tighter than bitwise operators.
        self.assertEqual(run("if ((a.val & 1) == 1) {\n  r.val = 1\n}")["r.val"], 1)
        with self.assertRaisesRegex(NxwrightError, "a comparison can only be a condition"):
            compile_lines("if (a.val & 1 == 1) {\n  r.val = 1\n}")
    def test_no_temporary_when_left_to_right_is_right(self):
        self.assertEqual(compile_lines("x.val = a.val * b.val + c.val"), ["x.val=a.val*b.val+c.val"])
        # Addition does not depend on order, so the product can go first.
        self.assertEqual(compile_lines("x.val = a.val + b.val * c.val"), ["x.val=b.val*c.val+a.val"])

    def test_temporary_when_needed(self):
        self.assertEqual(compile_lines("x.val = a.val - b.val * c.val"),
                         ["__g0_0=b.val*c.val", "x.val=a.val-__g0_0"])

    def test_minus_before_a_name(self):
        self.assertEqual(compile_lines("x.val = -a.val"), ["x.val=0-a.val"])
        self.assertEqual(run("x.val = -a.val * 2")["x.val"], -14)
        self.assertEqual(run("x.val = b.val - -1")["x.val"], -2)

    def test_compound_assignment_means_the_whole_right_side(self):
        self.assertEqual(run("x.val = 10\nx.val -= a.val + b.val")["x.val"], 10 - (7 - 3))
        self.assertEqual(run("x.val = 2\nx.val *= a.val + 1")["x.val"], 16)
        self.assertEqual(compile_lines("x.val += a.val - b.val"), ["x.val+=a.val-b.val"])
        self.assertEqual(compile_lines("x.val *= a.val * b.val"), ["x.val*=a.val*b.val"])
        self.assertEqual(compile_lines("x.val -= a.val + b.val / (c.val - d.val)"),
                         ["__g0_0=c.val-d.val", "__g0_1=b.val/__g0_0+a.val", "x.val-=__g0_1"])

    def test_text_naming_its_target(self):
        # On the screen, a text join such as `t = "a" + t` comes out wrong when it names
        # its target anywhere but first. The compiler then joins into a temporary.
        self.assertEqual(run('t1.txt = "-" + t1.txt')["t1.txt"], "-ab")
        self.assertEqual(run('t1.txt = "<" + t1.txt + ">"')["t1.txt"], "<ab>")
        self.assertEqual(run('t1.txt = t1.txt + "-" + t1.txt')["t1.txt"], "ab-ab")
        self.assertEqual(run('t1.txt += "x" + t1.txt')["t1.txt"], "abxab")
        self.assertEqual(run('t1.txt = t1.txt + "x"')["t1.txt"], "abx")
        self.assertEqual(compile_lines('t1.txt = t1.txt + "x"'), ['t1.txt=t1.txt+"x"'])

    def test_the_interpreter_copies_the_screen(self):
        # What the Editor's simulator gave. Each join names its target somewhere
        # other than first, so it comes out wrong; the interpreter must match.
        cases = [('r0.txt="005"', 'r0.txt="0:["+r0.txt+"]"', "0050:[]"),
                 ('t1.txt="ab"', 't1.txt=t1.txt+"-"+t1.txt', "ab-ab-"),
                 ('t1.txt="ab"', 't1.txt+="x"+t1.txt', "abxabx"),
                 ('t1.txt="ab"', 't1.txt="<"+t1.txt+">"', "ab<>")]
        for first, second, expected in cases:
            with self.subTest(code=second):
                values = EditorMachine(dict(VALUES, **{"r0.txt": ""})).run([first, second])
                self.assertEqual(values[second.split("=")[0].rstrip("+")], expected)

    def test_text(self):
        self.assertEqual(run('t0.txt = "n=" + a.val + "!"')["t0.txt"], "n=7!")
        self.assertEqual(run('t0.txt = 1 + 2 + "a"')["t0.txt"], "3a")
        self.assertEqual(run('t0.txt = "a" + 1 + 2')["t0.txt"], "a12")
        self.assertEqual(run('t0.txt = t1.txt + ("c" + t1.txt)')["t0.txt"], "abcab")
        self.assertEqual(run("t0.txt = a.val * 2")["t0.txt"], "14")
        self.assertEqual(run("t1.txt += a.val")["t1.txt"], "ab7")
        # On text, -= removes that many characters from the end.
        self.assertEqual(run("t1.txt -= 1")["t1.txt"], "a")

    def test_index(self):
        values = {"b[1].val": 0, "b[3].val": 9}
        self.assertEqual(run("b[a.val - 6].val = 4", values)["b[1].val"], 4)
        self.assertEqual(compile_lines("x.val = b[d.val + 1].val"), ["x.val=b[d.val+1].val"])
        self.assertEqual(run("if (b[d.val + 1].val == 9) {\n  x.val = 1\n}", values)["x.val"], 1)


class ConditionTest(unittest.TestCase):

    def test_random_conditions(self):
        generator = random.Random(2)
        comparisons = ["==", "!=", "<", ">", "<=", ">="]

        def condition(depth):
            choice = generator.random()
            if depth == 0 or choice < 0.3:
                left, right = random_expression(generator, 1), random_expression(generator, 1)
                operator = generator.choice(comparisons)
                return (("compare", operator, left, right),
                        "%s %s %s" % (source_text(left, generator), operator,
                                      source_text(right, generator)))
            if choice < 0.4:
                inner, text = condition(depth - 1)
                return ("not", inner), "!(" + text + ")"
            operator = generator.choice(["&&", "||"])
            (left, left_text), (right, right_text) = condition(depth - 1), condition(depth - 1)
            return (operator, left, right), "(%s %s %s)" % (left_text, operator, right_text)

        def truth(tree):
            if tree[0] == "compare":
                left, right = evaluate(tree[2], VALUES), evaluate(tree[3], VALUES)
                return {"==": left == right, "!=": left != right, "<": left < right,
                        ">": left > right, "<=": left <= right, ">=": left >= right}[tree[1]]
            if tree[0] == "not":
                return not truth(tree[1])
            # Both sides, as the compiled code computes every part first.
            left, right = truth(tree[1]), truth(tree[2])
            return (left and right) if tree[0] == "&&" else (left or right)

        for _ in range(300):
            tree, text = condition(3)
            try:
                expected = truth(tree)
            except ZeroDivisionError:
                continue
            code = "if (%s) {\n  r.val = 1\n} else {\n  r.val = 2\n}" % text
            with self.subTest(code=text):
                self.assertEqual(run(code)["r.val"], 1 if expected else 2)

    def test_mixed_logic_and_not(self):
        code = "if (a.val == 7 || b.val == 0 && c.val == 0) {\n  r.val = 1\n}"
        self.assertEqual(run(code)["r.val"], 1)
        self.assertEqual(compile_lines("if (!(a.val == 1)) {\n  r.val = 1\n}"),
                         ["if(a.val!=1)", "{", "  r.val=1", "}"])
        self.assertEqual(run("if (a.val) {\n  r.val = 1\n}")["r.val"], 1)

    def test_else_if_with_temporaries(self):
        code = ("if (a.val + 1 == 0) {\n  r.val = 1\n} else if (a.val * 2 == 14) {\n  r.val = 2\n"
                "} else {\n  r.val = 3\n}\nx.val = 5")
        self.assertEqual(run(code)["r.val"], 2)
        self.assertEqual(run(code, {"a.val": 1})["r.val"], 3)
        self.assertEqual(run(code)["x.val"], 5)
        # An else on its own line, after the "}".
        separate = code.replace("} else if", "}\nelse if")
        self.assertEqual(compile_lines(separate), compile_lines(code))

    def test_while_recomputes_its_condition(self):
        self.assertEqual(run("x.val = 0\nwhile (x.val * 2 < 9) {\n  x.val++\n}")["x.val"], 5)

    def test_for(self):
        code = "r.val = 0\nfor (x.val = 0; x.val < a.val - 2; x.val++) {\n  r.val += 2\n}"
        self.assertEqual(run(code)["r.val"], 10)
        self.assertEqual(compile_lines("for (x.val = 0; x.val < 3; x.val++) {\n}"),
                         ["for(x.val=0;x.val<3;x.val++)", "{", "}"])

    def test_text_comparison(self):
        self.assertEqual(run('if (t1.txt == "a" + "b") {\n  r.val = 1\n}')["r.val"], 1)


class ConstantAndLocalTest(unittest.TestCase):

    def test_command_keeps_picture_references(self):
        compiled = compile_page("p", COMPONENTS, ProgramNames(), [("p.nx", _numbered("const mono = 3"))],
                                {KEY: ("p.nx", _numbered("pic 0,0,@pic(mono)"))})
        self.assertEqual(compiled.events[KEY], [(1, "pic 0,0,@pic(mono)")])

    def test_constants(self):
        program = read_program_names(_numbered('const LIMIT = 40\nconst WORD = "hi"\nint g=0'))
        code = "x.val = LIMIT + LOW\nt0.txt = WORD\ncovx LIMIT,t0.txt,0,0"
        self.assertEqual(compile_lines(code, program=program, preamble="const LOW = -2"),
                         ["x.val=40+-2", 't0.txt="hi"', "covx 40,t0.txt,0,0"])

    def test_constant_refusals(self):
        with self.assertRaisesRegex(NxwrightError, "line 1: unknown name LIMIT"):
            compile_lines("x.val = LIMIT")
        with self.assertRaisesRegex(NxwrightError, "line 2: TWO is already a constant"):
            compile_lines("x.val = TWO", preamble="const TWO = 2\nconst TWO = 3")
        with self.assertRaisesRegex(NxwrightError, "line 1: a constant cannot be assigned"):
            compile_lines("TWO = 3", preamble="const TWO = 2")
        with self.assertRaisesRegex(NxwrightError, "constants go at the top"):
            compile_lines("const TWO = 2")
        with self.assertRaisesRegex(NxwrightError, "has the name of a component"):
            compile_lines("x.val = 1", preamble="const a = 2")

    def test_int_variables_of_program(self):
        program = read_program_names(_numbered("int sys0=0,count=0, total=1"))
        self.assertEqual(program.variables, frozenset({"sys0", "count", "total"}))
        self.assertEqual(compile_lines("count = total * 2", program=program), ["count=total*2"])

    def test_locals(self):
        code = "var n = a.val * 2\nvar s = \"v\" + n\nt0.txt = s\nx.val = n + 1\ncovx n,t1.txt,0,0"
        values = run(code)
        self.assertEqual((values["t0.txt"], values["x.val"], values["t1.txt"]), ("v14", 15, "14"))
        compiled = compile_page("p", COMPONENTS, ProgramNames(), [],
                                {("p", "down"): ("p.nx", _numbered("var n = 1")),
                                 ("p", "up"): ("p.nx", _numbered("var n = \"t\"\nx.val = a.val - b.val * c.val"))})
        # Numbers are program.s globals; only text needs a component.
        self.assertEqual([(variable.name, variable.kind) for variable in compiled.generated],
                         [("__v0", "text")])
        self.assertEqual(compiled.globals, ["__g0_0", "__g0_1"])

    def test_local_refusals(self):
        with self.assertRaisesRegex(NxwrightError, "line 2: local n is declared twice"):
            compile_lines("var n = 1\nvar n = 2")
        with self.assertRaisesRegex(NxwrightError, "line 1: local dim has the name of a component"):
            compile_lines("var dim = 1")
        with self.assertRaisesRegex(NxwrightError, "line 1: local __n may not start with"):
            compile_lines("var __n = 1")
        with self.assertRaisesRegex(NxwrightError, "line 1: unknown name n"):
            compile_lines("var n = n")

    def test_the_editors_system_variables(self):
        # Its own list, which a probe of its refused names gave in full.
        self.assertEqual(compile_lines("eq0 = 3\nx.val = usize + appid"),
                         ["eq0=3", "x.val=usize+appid"])
        with self.assertRaisesRegex(NxwrightError, "line 1: unknown name eqlb"):
            compile_lines("x.val = eqlb")

    def test_program_code(self):
        program = read_program_names(_numbered("const START = 2\nint g=0"))
        lines = compile_program(_numbered("const START = 2\nint g=0\ng = START * 3 + 1"), program)
        self.assertEqual(preprocess(lines, NO_NAMES), ["int g=0", "g=2*3+1"])
        with self.assertRaisesRegex(NxwrightError, "line 1: this needs a temporary"):
            compile_program(_numbered("g = 1 - 2 * 3"), program)


class RefusalTest(unittest.TestCase):

    def test_syntax_errors_name_the_line(self):
        for code, message in [("x.val = 1\nx.val = (a.val + ", "line 2:"),
                              ("if (a.val == 1 {\n}", "line 1:"),
                              ("x.val = a.val == 1", "line 1: a comparison can only be a condition"),
                              ('x.val = "a"', "line 1: text cannot be put in a number"),
                              ("if (a.val == 1) {\n  x.val = 1", "a block is not closed"),
                              ("x.val = !a.val", "line 1: ! can only be in a condition")]:
            with self.subTest(code=code), self.assertRaisesRegex(NxwrightError, message):
                compile_lines(code)

    def test_generated_prefix_is_refused_for_components(self):
        with self.assertRaisesRegex(NxwrightError, "component __x starts with"):
            compile_lines("x.val = 1", components=COMPONENTS + ["__x"])


class AttributeKindTest(unittest.TestCase):
    """A name's kind by its component's type, where nxlang is given the pages'
    types: a scrolling text's `dir` and `vvs2` are numbers, and a file
    browser's `dir` and a data record's `format` texts. Page q holds g1, a
    scrolling text."""
    TYPES = {"p": {"p": "page", "g0": "scrolling-text", "fb0": "file-browser",
                   "d": "data-record", "x": "number"},
             "q": {"q": "page", "g1": "scrolling-text"}}

    def compiled(self, code: str) -> list:
        return compile_lines(code, components=COMPONENTS + ["g0", "fb0"], object_types=self.TYPES)

    def test_a_scrolling_texts_numbers(self):
        self.assertEqual(self.compiled("g0.dir = 2"), ["g0.dir=2"])
        self.assertEqual(self.compiled("x.val = g0.vvs2"), ["x.val=g0.vvs2"])
        self.assertEqual(self.compiled("p.g0.dir = 2"), ["p.g0.dir=2"])
        self.assertEqual(self.compiled("q.g1.dir = 2"), ["q.g1.dir=2"])

    def test_texts_of_a_file_browser_and_a_data_record(self):
        self.assertEqual(self.compiled('fb0.dir = "sd0/"'), ['fb0.dir="sd0/"'])
        self.assertEqual(self.compiled('d.format = "a"'), ['d.format="a"'])

    def test_a_type_nxlang_cannot_tell(self):
        # Through b[], or on a page whose types nxlang is not given, a name
        # keeps the kind nxlang gave it by name: dir a text.
        self.assertEqual(self.compiled("b[3].dir = 2"), ["covx 2,b[3].dir,0,0"])
        self.assertEqual(compile_lines("g0.dir = 2", components=COMPONENTS + ["g0"]),
                         ["covx 2,g0.dir,0,0"])


class DataRecordCallTest(unittest.TestCase):
    """A data record's calls, whose arguments the Editor takes as one text or
    number each: an argument of more than one operand is computed first.
    Here `d` is the page's data record."""

    def compiled(self, code: str) -> list:
        return compile_lines(code, object_types={"p": {"d": "data-record"}})

    def test_an_argument_computed_first(self):
        self.assertEqual(self.compiled('d.insert("Total: " + t0.txt)'),
                         ['__s0.txt="Total: "+t0.txt', "d.insert(__s0.txt)"])
        self.assertEqual(self.compiled("d.delete(x.val + 1, 2)"),
                         ["__g0_0=x.val+1", "d.delete(__g0_0,2)"])
        self.assertEqual(self.compiled("d.up(t0.txt, x.val * 2)"),
                         ["__g0_0=x.val*2", "d.up(t0.txt,__g0_0)"])

    def test_one_operand_as_written(self):
        self.assertEqual(self.compiled("d.insert(t0.txt)"), ["d.insert(t0.txt)"])
        self.assertEqual(self.compiled("d.clear()"), ["d.clear()"])
        # Another component's call of the same name is left as today.
        self.assertEqual(self.compiled('x.insert("a" + t0.txt)'), ['x.insert("a"+t0.txt)'])

    def test_a_number_for_text_becomes_its_digits(self):
        self.assertEqual(self.compiled("d.insert(x.val)"),
                         ["covx x.val,__s0.txt,0,0", "d.insert(__s0.txt)"])

    def test_refusals(self):
        for code, pattern in (
                ("d.delete(t0.txt, 1)", "argument 1 of d.delete is a number, not a text"),
                ("d.delete(1)", "d.delete takes 2 arguments, as the Nextion Editor compiles it"),
                ("d.clear(1)", "d.clear takes no arguments, as the Nextion Editor compiles it")):
            with self.subTest(code=code), self.assertRaisesRegex(NxwrightError,
                                                                  "line 1: " + pattern):
                self.compiled(code)


class CommandArgumentTest(unittest.TestCase):
    """get, print, prints, and covx, whose first argument the Editor takes as
    one text or number: one of more operands is computed first. Their other
    numbers, which the Editor takes as arithmetic, are written as such."""

    def test_a_first_argument_computed_first(self):
        self.assertEqual(compile_lines("print x.val + 1"), ["__g0_0=x.val+1", "print __g0_0"])
        self.assertEqual(compile_lines('get "a" + t0.txt'),
                         ['__s0.txt="a"+t0.txt', "get __s0.txt"])
        self.assertEqual(compile_lines("prints x.val * 2, 0"),
                         ["__g0_0=x.val*2", "prints __g0_0,0"])
        self.assertEqual(compile_lines("covx x.val - 1, t0.txt, 0, 0"),
                         ["__g0_0=x.val-1", "covx __g0_0,t0.txt,0,0"])

    def test_the_other_numbers_as_arithmetic(self):
        self.assertEqual(compile_lines("covx 1234, t0.txt, x.val - 3, x.val - 4"),
                         ["covx 1234,t0.txt,x.val-3,x.val-4"])
        self.assertEqual(compile_lines("prints t0.txt, x.val + 1"), ["prints t0.txt,x.val+1"])

    def test_one_operand_as_written(self):
        self.assertEqual(compile_lines("get x.val"), ["get x.val"])
        self.assertEqual(compile_lines('print "a, b"'), ['print "a, b"'])


class EditorMeaningTest(unittest.TestCase):
    """Editor code rewritten so that nxlang reads it as the Editor does: the Editor
    computes strictly from left to right (see editor_code.py)."""

    def test_parentheses_keep_left_to_right(self):
        lines = _numbered("x.val=a.val+b.val*c.val\n  y.val=a.val*b.val+c.val // kept\n"
                          "x.val=(1<<2)+1\ncovx a.val,t0.txt,0,0")
        self.assertEqual([text for _, text in keep_editor_meaning(lines)],
                         ["x.val=(a.val+b.val)*c.val", "  y.val=a.val*b.val+c.val // kept",
                          "x.val=(1<<2)+1", "covx a.val,t0.txt,0,0"])

    def test_compound_assignment(self):
        lines = keep_editor_meaning(_numbered("x.val-=a.val+b.val\nx.val+=a.val-b.val\nt0.txt+=t1.txt+\"a\""))
        self.assertEqual([text for _, text in lines],
                         ["x.val=x.val-a.val+b.val", "x.val+=a.val-b.val", 't0.txt+=t1.txt+"a"'])
        self.assertEqual(editor_equivalent(["  x.val-=a.val+b.val", "x.val+=a.val"]),
                         ["  x.val=x.val-a.val+b.val", "x.val+=a.val"])

    def test_compiles_back_to_the_editor_code(self):
        editor = ["x.val=a.val+b.val*c.val", "x.val-=a.val*b.val", "if(a.val==1&&b.val!=2)", "{",
                  "  t0.txt=t1.txt+\"a\"", "}else", "{", "  x.val=0-a.val*2", "}"]
        nxlang_lines = keep_editor_meaning(list(enumerate(editor, start=1)))
        self.assertEqual(compile_lines("\n".join(text for _, text in nxlang_lines)),
                         editor_equivalent(editor))

    def test_hex_written_0X(self):
        # The Editor reads 0X10 as 0x10, and nxlang writes hex as 0x alone.
        # A quoted text and a comment keep theirs, and so does a name holding
        # it.
        editor = ["x.val=0X10+a.val*2", "if(a.val==0X0A)", "{", '  t0.txt="0X10"', "}",
                  "covx 0X10,t0.txt,0,0", "x.val=x.val&0XFF"]
        nxlang_lines = keep_editor_meaning(list(enumerate(editor, start=1)))
        self.assertEqual([text for _, text in nxlang_lines],
                         ["x.val=(0x10+a.val)*2", "if(a.val==0x0A)", "{", '  t0.txt="0X10"', "}",
                          "covx 0x10,t0.txt,0,0", "x.val=x.val&0xFF"])
        self.assertEqual(keep_editor_meaning([(1, "x.val=0X01 // 0X02")]),
                         [(1, "x.val=0x01 // 0X02")])
        self.assertEqual(editor_equivalent(["x.val-=a0X1.val+0X02 // 0X03"]),
                         ["x.val=x.val-a0X1.val+0x02 // 0X03"])
        self.assertEqual(compile_lines("\n".join(text for _, text in nxlang_lines)),
                         editor_equivalent(editor))


class NxlangFolderTestCase(SourceFolderTestCase):
    """The small project's first page, given the variables a and x and a down event in
    Editor code, `x.val=a.val+a.val*2`. Most tests switch the folder to nxlang."""

    PAGE = ("\n[[component]]\nname = \"a\"\ntype = \"variable\"\n"
            "\n[[component]]\nname = \"x\"\ntype = \"variable\"\n")
    EVENTS = ("const TWO = 2\n\non first.down:\n  x.val = a.val - TWO * a.val\n\n"
              "on first.up:\n  x.val = 1\n")
    # Code joining a number to a text, which needs a text temporary. x then
    # holds a text (write_text_join), as a variable of a number has no `txt`.
    TEXT_JOIN = 'on first.down:\n  x.txt = "n" + a.val\n'

    def write_text_join(self):
        """Writes TEXT_JOIN as page first's code, x made a variable of a text."""
        edit_text(self.source / "pages" / "first.page.toml",
                  'name = "x"\ntype = "variable"\n', 'name = "x"\ntype = "variable"\nsta = 1\n')
        (self.source / "pages" / "first.nx").write_text(self.TEXT_JOIN, encoding="utf-8",
                                                         newline="\n")

    def setUp(self):
        super().setUp()
        self.set_events("first", ["down", "up"])
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8", newline="\n") as file:
            file.write(self.PAGE)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  x.val=a.val+a.val*2\n",
                                                         encoding="utf-8", newline="\n")
        self.plain_build = self.folder / "plain.HMI"
        build(self.source, self.plain_build)

    def set_events(self, page: str, events: list):
        """Sets the events a page's table lists, as data (edited_page_file)."""
        path = self.source / "pages" / (page + ".page.toml")
        path.write_text(edited_page_file(path.read_text(encoding="utf-8"),
                                         lambda tables: tables[0].update(events=events)),
                        encoding="utf-8", newline="\n")

    def build_and_dump(self, name: str) -> Path:
        built = self.folder / (name + ".HMI")
        build(self.source, built)
        dump = self.folder / (name + "-dump")
        ProjectDumper(built, dump).dump()
        return dump


class NxlangSourceFolderTest(NxlangFolderTestCase):
    """A source folder switched to nxlang."""

    def test_switch_keeps_the_meaning_and_the_project(self):
        before = self.folder / "before"
        export_dump(self.source, before)
        switch_to_nxlang(self.source)
        self.assertIn('language = "nxlang"', (self.source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         "on first.down:\n  x.val=(a.val+a.val)*2\n")
        export_dump(self.source, self.folder / "after")
        assert_same_dump_files(self, before, self.folder / "after")
        with self.assertRaisesRegex(NxwrightError, "already uses nxlang"):
            switch_to_nxlang(self.source)

    def test_switch_writes_hex_0X_as_0x(self):
        # nxlang writes hex as 0x alone, and the Editor read 0X10 as 0x10.
        (self.source / "pages" / "first.nx").write_text(
            "on first.down:\n  x.val=0X10\n  if(a.val==0X01)\n  {\n    x.val=a.val*0X02\n  }\n",
            encoding="utf-8", newline="\n")
        program = self.source / "program.nx"
        edit_text(program, "page 0", "sys0=0X10\npage 0")
        switch_to_nxlang(self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         "on first.down:\n  x.val=0x10\n  if(a.val==0x01)\n  {\n"
                         "    x.val=a.val*0x02\n  }\n")
        self.assertIn("sys0=0x10\npage 0", program.read_text(encoding="utf-8"))

    def test_build_adds_generated_variables_and_import_keeps_the_source(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        dump = self.build_and_dump("nxlang")
        page = (dump / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("| __g0_0=2*a.val", page)
        self.assertTrue((dump / "program.s").read_bytes().startswith(b"int __g0_0=0\r\n"))
        program = (self.source / "program.nx").read_text(encoding="utf-8")
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         self.EVENTS)
        # The declaration line is the build's; import leaves it out.
        self.assertEqual((self.source / "program.nx").read_text(encoding="utf-8"), program)
        self.assertIn('language = "nxlang"', (self.source / "app.toml").read_text(encoding="utf-8"))

    def test_another_pages_scrolling_text_keeps_its_direction(self):
        # Switching and importing compile each page with every page's types,
        # as the build does: second's g1 is a scrolling text, whose dir is a
        # number, set as written.
        with open(self.source / "pages" / "second.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "g1"\ntype = "scrolling-text"\nvscope = 1\n'
                       'x = 0\ny = 40\nw = 100\nh = 30\n')
        code = "on first.down:\n  second.g1.dir=2\n"
        (self.source / "pages" / "first.nx").write_text(code, encoding="utf-8", newline="\n")
        switch_to_nxlang(self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"), code)
        dump = self.build_and_dump("nxlang")
        self.assertIn("| second.g1.dir=2\n",
                      (dump / "pages" / "00-first.txt").read_text(encoding="utf-8"))
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"), code)

    def test_import_replaces_an_event_the_editor_changed(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        dump = self.build_and_dump("nxlang")
        edit_text(dump / "pages" / "00-first.txt", "x.val=1", "x.val=a.val+a.val*3")
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         self.EVENTS.replace("x.val = 1", "x.val=(a.val+a.val)*3"))

    def test_import_stops_when_the_editor_changed_compiled_code(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        dump = self.build_and_dump("nxlang")
        edit_text(dump / "pages" / "00-first.txt", "__g0_0=2*a.val", "__g0_0=3*a.val")
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        with self.assertRaisesRegex(NxwrightError, "first.nx: the Nextion Editor changed "
                                                   "first.down"):
            import_dump(dump, self.source)
        self.assertEqual({path: path.read_bytes() for path in self.source.rglob("*")
                          if path.is_file()}, before)

    def test_import_after_a_component_added_in_the_editor(self):
        switch_to_nxlang(self.source)
        # TEXT_JOIN needs a text temporary, __s0: a generated component.
        self.write_text_join()
        dump = self.build_and_dump("nxlang")
        page = dump / "pages" / "00-first.txt"
        # The Editor puts a new component after the generated variables.
        text = page.read_text(encoding="utf-8")
        start = text.index("object 2 x")
        block = text[start:text.index("\n\nobject", start)]
        added = block.replace("object 2 x", "object 4 y").replace(
            'objname = "x"', 'objname = "y"').replace("id = 2", "id = 4")
        page.write_text(text.rstrip("\n") + "\n\n" + added, encoding="utf-8", newline="\n")
        import_dump(dump, self.source)
        toml = (self.source / "pages" / "first.page.toml").read_text(encoding="utf-8")
        self.assertIn('name = "y"', toml)
        self.assertNotIn("__s0", toml)
        self.assertNotIn("id = ", toml)
        export_dump(self.source, self.folder / "again")
        rebuilt = (self.folder / "again" / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("object 3 y", rebuilt)
        self.assertIn("object 4 __s0", rebuilt)

    def test_import_refuses_a_component_with_the_generated_prefix(self):
        switch_to_nxlang(self.source)
        dump = self.build_and_dump("nxlang")
        edit_text(dump / "pages" / "00-first.txt", 'object 1 a\n', 'object 1 __a\n')
        edit_text(dump / "pages" / "00-first.txt", 'objname = "a"', 'objname = "__a"')
        with self.assertRaisesRegex(NxwrightError, "component __a starts with"):
            import_dump(dump, self.source)

    def test_build_refuses_a_page_past_id_255(self):
        switch_to_nxlang(self.source)
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8", newline="\n") as file:
            for number in range(253):
                file.write('\n[[component]]\nname = "v%d"\ntype = "variable"\n' % number)
        self.write_text_join()
        # The page, its 255 components, and the text temporary.
        self.assert_export_refused("first: with the variables nxlang adds, the page "
                                   "has 257 objects; at most 256 fit")

    def test_globals_of_two_pages_and_an_import_after_reordering(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        (self.source / "pages" / "second.nx").write_text(
            "on second.down:\n  sys0 = sys1 - sys2 * 2\n", encoding="utf-8", newline="\n")
        self.set_events("second", ["down"])
        dump = self.build_and_dump("two")
        self.assertIn("| __g1_0=sys2*2",
                      (dump / "pages" / "01-second.txt").read_text(encoding="utf-8"))
        self.assertTrue((dump / "program.s").read_bytes().startswith(b"int __g0_0=0,__g1_0=0\r\n"))
        # Pages reordered in the Editor: the globals keep the names they were built with.
        (dump / "pages" / "00-first.txt").rename(dump / "pages" / "tmp.txt")
        (dump / "pages" / "01-second.txt").rename(dump / "pages" / "00-second.txt")
        (dump / "pages" / "tmp.txt").rename(dump / "pages" / "01-first.txt")
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "second.nx").read_text(encoding="utf-8"),
                         "on second.down:\n  sys0 = sys1 - sys2 * 2\n")

    def test_build_refuses_too_many_globals(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.EVENTS, encoding="utf-8", newline="\n")
        limit = source_folder.MOST_GLOBALS
        source_folder.MOST_GLOBALS = 0
        try:
            self.assert_export_refused("needs 1 program.s globals; at most 0")
        finally:
            source_folder.MOST_GLOBALS = limit

    def test_unknown_language_is_refused(self):
        edit_text(self.source / "app.toml", 'language = "nextion"', 'language = "fancy"')
        self.assert_export_refused("app.toml: language must be 'nextion' or 'nxlang'")


FUNCTIONS = """function twice(n: number) -> number:
  return n * 2

function add(first: number, second: number) -> number:
  var sum = first + second
  return sum

function label(n: number) -> text:
  return "n=" + n

function quad(n: number) -> number:
  return twice(twice(n))

function bump() -> number:
  c.val++
  return 1

function greet(who: text):
  t0.txt = "hi " + who

"""


class ConditionalTest(unittest.TestCase):
    """`condition ? a : b`, as in C. a.val is 7, b.val -3."""

    def test_it_chooses_as_in_c(self):
        for code, expected in (("x.val = a.val > 1 ? 2 : 3", 2), ("x.val = a.val > 10 ? 2 : 3", 3),
                               # Looser than ||, grouping from the right.
                               ("x.val = a.val > 10 || b.val < 0 ? 5 : 6", 5),
                               ("x.val = a.val > 10 ? 1 : b.val < 0 ? 2 : 3", 2),
                               ("x.val = a.val > 1 ? b.val < 0 ? 1 : 2 : 3", 1),
                               ("x.val = (a.val > 1 ? 2 : 3) * 10", 20),
                               ("x.val = !(a.val > 1) ? 2 : 3", 3), ("x.val = b.val ? 4 : 5", 4)):
            with self.subTest(code=code):
                self.assertEqual(run(code)["x.val"], expected)

    def test_texts(self):
        self.assertEqual(run('t0.txt = a.val > 1 ? "big" : "small"')["t0.txt"], "big")
        self.assertEqual(run('t0.txt = "is " + (a.val > 10 ? "big" : "small")')["t0.txt"],
                         "is small")

    def test_in_a_condition_an_argument_and_a_return(self):
        self.assertEqual(run("if ((a.val > 1 ? 1 : 0) == 1) {\n  x.val = 9\n}")["x.val"], 9)
        page = FUNCTIONS + ("function pick(n: number) -> number:\n  return n > 1 ? n : 0\n\n"
                            "on p.down:\n  x.val = twice(a.val > 1 ? 3 : 4)\n  r.val = pick(5)\n")
        values = run_page(page).values
        self.assertEqual((values["x.val"], values["r.val"]), (6, 5))
        self.assertEqual(run("print a.val > 1 ? 4 : 5")["sent"], run("print 4")["sent"])
        self.assertEqual(run("covx a.val > 1 ? 4 : 5,t0.txt,0,0")["t0.txt"], "4")

    def test_in_a_data_record_call(self):
        lines = compile_lines('d.insert(a.val > 1 ? "big" : "small")',
                              object_types={"p": {"d": "data-record"}})
        self.assertEqual(lines, ["if(a.val>1)", "{", '  __s0.txt="big"', "}else", "{",
                                 '  __s0.txt="small"', "}", "d.insert(__s0.txt)"])

    def test_only_the_chosen_branch_runs(self):
        # bump() adds 1 to c.val, which starts at 5.
        for code, expected in (("x.val = a.val > 1 ? 1 : bump()", 5),
                               ("x.val = a.val < 1 ? 1 : bump()", 6)):
            with self.subTest(code=code):
                self.assertEqual(run_page(FUNCTIONS + "on p.down:\n  %s\n" % code).values["c.val"],
                                 expected)

    def test_refusals(self):
        for code, message in (('x.val = a.val > 1 ? 1 : "one"', r"both sides of \? : must be "
                                                               r"numbers, or both texts"),
                              ("vis b,a.val > 1 ? 1 : 0", r"nxlang passes this line on as "
                                                          r"written, .*put the value in a local "
                                                          r"first")):
            with self.subTest(code=code):
                with self.assertRaisesRegex(NxwrightError, r"line 1: " + message):
                    compile_lines(code)
        with self.assertRaisesRegex(NxwrightError, r"a case holds a number, a text, or a constant"):
            compile_lines("switch (a.val) {\n  case a.val > 1 ? 1 : 2:\n    x.val = 1\n}")
        with self.assertRaisesRegex(NxwrightError, r"a constant's value must be a number or a "
                                                   r"text"):
            compile_lines("x.val = LIMIT", preamble="const LIMIT = 1 ? 2 : 3")
        lines = [(1, "int counter=0, other=0"), (2, "counter = other > 1 ? 1 : 2")]
        with self.assertRaisesRegex(NxwrightError, r"program\.nx cannot have"):
            compile_program(lines, read_program_names(lines))


# b0.down holds g's result in a temporary while f runs. f calls the macro
# tap, which clicks b1, whose event computes b.val * a.val in a temporary.
MACRO_CALLER = """\
function g() -> number:
  return 5

function f() -> number:
  call tap
  return 1

on b0.down:
  x.val = g() + f()

on b1.down:
  c.val = a.val - b.val * a.val
"""


class MacroCallTest(unittest.TestCase):
    """What may run during a macro that nxlang code calls."""

    def test_a_click_counts_the_unnamed_among_the_ids(self):
        # The page's object 2 is being named, as while its page file is
        # typed, so b1 is object 4. b1.down then runs during f, and takes
        # temporaries of its own.
        program = ProgramNames(macros={"tap": Macro("macros.nx", 1, ((2, "click 4,1"),))})
        names = ["p", "b0", None, "x", "b1", "a", "b", "c"]
        compiled = compile_nxlang_page(MACRO_CALLER, "p", names, program)
        temporaries = {key: set(re.findall(r"__g\d+_\d+", "\n".join(text for _, text in lines)))
                       for key, lines in compiled.events.items()}
        self.assertTrue(temporaries[("b1", "down")])
        self.assertFalse(temporaries[("b1", "down")] & temporaries[("b0", "down")])


class FunctionTest(unittest.TestCase):

    def test_locals_and_parameters_may_share_a_components_name(self):
        # Bare, the name is the local or parameter; with a field, it is the
        # component. That holds in expressions and in command arguments.
        files = {"pages/lib/f.nx": (
            "function f(a: number) -> number:\n"
            "  var x = a * 2\n"
            "  return x + a.val\n"
            "\n"
            "function size(t0: text) -> number:\n"
            "  var n = 0\n"
            "  strlen t0,n\n"
            "  return n\n")}
        values = call_function(files, "lib/f.nx", 'x.val = f(1)\nr.val = size("abcd")')
        self.assertEqual((values["x.val"], values["r.val"], values["t0.txt"]), (9, 4, ""))
        # In an event too.
        values = run("var a = 3\na += 1\na++\nx.val = a + a.val")
        self.assertEqual((values["x.val"], values["a.val"]), (12, 7))
        # Program variables, system variables, constants, and functions stay refused.
        program = read_program_names(_numbered("int count=0"))
        for code, message in [("var count = 1", "local count has the name of a component"),
                              ("var dim = 1", "local dim has the name of a component")]:
            with self.subTest(code=code):
                with self.assertRaisesRegex(NxwrightError, message):
                    compile_lines(code, program=program)
        for page, message in [
                ("const K = 1\n\non p.down:\n  var K = 2\n", "line 4: K is already a constant"),
                ("function g():\n  x.val = 1\n\nfunction f(g: number):\n  x.val = g\n",
                 "line 4: g is already a function")]:
            with self.subTest(page=page):
                with self.assertRaisesRegex(NxwrightError, message):
                    run_page(page)

    def run_code(self, code: str, values: dict = None) -> EditorMachine:
        lines = "\n".join("  " + line for line in code.split("\n"))
        return run_page(FUNCTIONS + "on p.down:\n" + lines + "\n", values)

    def test_calls(self):
        self.assertEqual(self.run_code("x.val = twice(a.val) + 1").values["x.val"], 15)
        self.assertEqual(self.run_code("x.val = twice(a.val) + twice(b.val)").values["x.val"], 8)
        self.assertEqual(self.run_code("x.val = add(a.val, add(b.val, c.val))").values["x.val"], 9)
        self.assertEqual(self.run_code("x.val = quad(d.val)").values["x.val"], 8)
        self.assertEqual(self.run_code("t0.txt = label(a.val - 1)").values["t0.txt"], "n=6")
        self.assertEqual(self.run_code("greet(\"you\")").values["t0.txt"], "hi you")
        self.assertEqual(self.run_code("greet(a.val)").values["t0.txt"], "hi 7")
        self.assertEqual(self.run_code("bump()").values["c.val"], 6)
        self.assertEqual(self.run_code("if (twice(a.val) == 14) {\n  r.val = 1\n}").values["r.val"], 1)
        code = "x.val = 0\nwhile (twice(x.val) < 9) {\n  x.val++\n}"
        self.assertEqual(self.run_code(code).values["x.val"], 5)

    def test_short_circuit(self):
        code = "if (a.val == 0 && bump() == 1) {\n  r.val = 1\n}"
        machine = self.run_code(code)
        self.assertEqual((machine.values["c.val"], machine.values["r.val"]), (5, 0))
        code = "if (a.val == 7 || bump() == 1) {\n  r.val = 1\n}"
        machine = self.run_code(code)
        self.assertEqual((machine.values["c.val"], machine.values["r.val"]), (5, 1))
        code = "if (a.val == 7 && bump() == 1) {\n  r.val = 1\n}"
        machine = self.run_code(code)
        self.assertEqual((machine.values["c.val"], machine.values["r.val"]), (6, 1))
        # The division would fail; it is never reached.
        code = "if (b.val != -3 && a.val / (b.val + 3) > 1) {\n  r.val = 1\n}"
        self.assertEqual(self.run_code(code).values["r.val"], 0)
        code = ("x.val = 0\nwhile (x.val < 3 && bump() == 1) {\n  x.val++\n}")
        machine = self.run_code(code)
        self.assertEqual((machine.values["x.val"], machine.values["c.val"]), (3, 8))

    def test_generated_parts(self):
        compiled = compile_nxlang_page(FUNCTIONS + "on p.down:\n  x.val = twice(1)\n", "p",
                                       COMPONENTS, ProgramNames())
        # Only twice is called: it is at depth 1, alone on the first hotspot.
        twice = compiled.functions["twice"]
        parameter, result, which = twice.parameter_variables[0], twice.result_variable, twice.which
        self.assertEqual((twice.hotspot, twice.depth, twice.index), ("__f0", 1, 0))
        self.assertEqual([text for _, text in compiled.events[("__f0", "down")]],
                         ["// function twice(n: number) -> number", "if(%s==0)" % which, "{",
                          "  %s=%s*2" % (result, parameter), "}"])
        self.assertEqual([text for _, text in compiled.events[("p", "load")]], ["tsw __f0,0"])
        self.assertEqual(preprocess(compiled.events[KEY], NO_NAMES),
                         ["%s=1" % parameter, "%s=0" % which, "click __f0,1", "x.val=%s" % result])
        # The uncalled functions generate nothing: no text variables, no hotspots.
        self.assertEqual(list(compiled.functions), ["twice"])
        self.assertEqual([variable.name for variable in compiled.generated], ["__f0"])
        self.assertEqual(compiled.globals, [parameter, result, which])

    def test_refusals(self):
        for code, message in [
                ("x.val = nothing(1)", ": unknown function nothing"),
                ("x.val = twice(1, 2)", ": twice takes 1 arguments, not 2"),
                ("x.val = greet(\"a\")", ": function greet has no result"),
                ("x.val = twice(\"a\")", ": twice takes a number, not text"),
                ("return 1", ": return can only be in a function"),
                # A call as a statement, half typed: a line that starts with a
                # name and "(" is a call, never an Editor command.
                ("bump(", ": the line ends too early"),
                ("greet(\"a\"", ": expected '\\)'"),
                ("bump() 1", ": unexpected '1'"),
                ("bump(#)", ": cannot read '#\\)'")]:
            with self.subTest(code=code), self.assertRaisesRegex(NxwrightError, message):
                self.run_code(code)
        for text, message in [
                ("function f() -> number:\n  return f()\n", "function f calls itself \\(f -> f\\)"),
                ("function f() -> number:\n  return g()\n\nfunction g() -> number:\n  return f()\n",
                 "function f calls itself \\(f -> g -> f\\)"),
                # An event run again while it runs, by a click, or a click in a call.
                ("on t0.down:\n  click t0,1\n",
                 "line 2: the calls and clicks t0.down -> t0.down come back to t0.down, which "
                 "has one set of variables"),
                ("function f():\n  click t0,1\n\non t0.down:\n  f()\n",
                 "line 5: the calls and clicks t0.down -> f -> t0.down come back to t0.down"),
                ("function f() -> number:\n  return 1\n  x.val = 2\n", "line 2: return must be the last"),
                ("function f() -> number:\n  if (a.val == 1) {\n    return 1\n  }\n",
                 "line 3: return must be the last"),
                ("function f() -> number:\n  x.val = 1\n", "line 1: function f must end with return"),
                ("function f():\n  return 1\n", "line 2: function f has no result to return"),
                ("function a():\n  x.val = 1\n", "line 1: function a has the name of a component"),
                ("const K = 1\nfunction K():\n  x.val = 1\n", "line 2: K is already a constant"),
                ("function f():\n  x.val = 1\n\nfunction f():\n  x.val = 2\n",
                 "line 4: function f appears twice"),
                ("function f(n: number, n: text):\n  x.val = 1\n", "line 1: parameter n appears twice"),
                ("function f(n: list):\n  x.val = 1\n", "line 1: a parameter is written"),
                ("function f(g: number):\n  x.val = 1\n\nfunction g():\n  x.val = 2\n",
                 "line 1: g is already a function"),
                ("function f():\n  var f = 1\n", "line 2: f is already a function")]:
            with self.subTest(text=text), self.assertRaisesRegex(NxwrightError, message):
                run_page(text + "\non p.down:\n  x.val = 1\n")

    def test_import_does_not_blame_the_editor_for_a_removed_picture(self):
        # The function names a picture the app no longer lists, so its old body
        # cannot be compared; that is no sign the Editor changed it.
        old = "function f():\n  x.val = @pic(gone)\n\non p.down:\n  f()\n"
        fresh = "on p.down:\n  __g0_0=0\n  click __f0,1\n"
        generated = {("__f0", "down"): ["// function f()", "if(__g0_0==0)", "{", "  x.val=3", "}"]}
        page_files = read_page_files("pages/p.nx", old, None)
        changes = nxlang_import_changes(fresh, "p", page_files, NO_NAMES, COMPONENTS,
                                        ProgramNames(), generated, 0)
        self.assertEqual((changes.changes, changes.editor), ({}, {}))

    def test_program_cannot_call(self):
        with self.assertRaisesRegex(NxwrightError, "line 1: program.nx cannot call functions"):
            compile_program(_numbered("dim = twice(2)"), ProgramNames())

    def test_goto_and_labels_in_functions(self):
        # The functions of one depth compile into one event, their hotspot's:
        # each function's labels are named apart, so each goto lands in its
        # own function.
        text = ("function f():\n  x.val = 1\n  goto done\n  x.val = 2\n  done:\n  x.val += 10\n\n"
                "function g():\n  r.val = 1\n  goto done\n  r.val = 2\n  done:\n  r.val += 10\n\n"
                "on p.down:\n  f()\n  g()\n")
        machine = run_page(text)
        self.assertEqual((machine.values["x.val"], machine.values["r.val"]), (11, 11))
        compiled = compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
        self.assertEqual([line.strip() for _, line in compiled.bodies["f"]
                          if "__l" in line], ["goto __l0", "__l0:"])
        self.assertEqual([line.strip() for _, line in compiled.bodies["g"]
                          if "__l" in line], ["goto __l1", "__l1:"])

    def test_a_goto_to_a_label_beyond_its_function(self):
        for text in ("function f():\n  goto done\n\nfunction g():\n  done:\n  x.val = 1\n\n"
                     "on p.down:\n  f()\n  g()\n",
                     "function f():\n  goto again\n\non p.down:\n  again:\n  f()\n"):
            with self.subTest(text=text), self.assertRaisesRegex(
                    NxwrightError, "line 2: function f has no label"):
                run_page(text)

    def test_a_label_twice_in_a_function(self):
        with self.assertRaisesRegex(NxwrightError, "line 3: done: function f holds this label twice"):
            run_page("function f():\n  done:\n  done:\n\non p.down:\n  f()\n")

    def test_a_label_named_as_a_local_or_a_constant(self):
        # A goto names a label, never a value.
        code = "var done = 1\nagain:\ndone:\ngoto again\ngoto done"
        self.assertEqual([line for line in compile_lines(code, preamble="const again = 5")
                          if line.startswith("goto")], ["goto again", "goto done"])
        run_page("const again = 5\n\nfunction f():\n  var done = 1\n  goto done\n"
                 "  done:\n  goto again\n  again:\n\non p.down:\n  f()\n")

    def test_labels_in_events_as_written(self):
        self.assertEqual(compile_lines("again:\nx.val = 1\ngoto again"),
                         ["again:", "x.val=1", "goto again"])


class FunctionSourceFolderTest(NxlangFolderTestCase):
    """Functions through build and import."""

    WITH_FUNCTION = ("function twice(n: number) -> number:\n  return n * 2\n\n"
                     "on first.down:\n  x.val = twice(a.val)\n\non first.up:\n  x.val = 1\n")

    def setUp(self):
        super().setUp()
        switch_to_nxlang(self.source)
        self.set_events("first", ["load", "down", "up"])
        (self.source / "pages" / "first.nx").write_text(self.WITH_FUNCTION, encoding="utf-8",
                                                         newline="\n")

    def test_build_refuses_functions_without_a_load_event(self):
        self.set_events("first", ["down", "up"])
        self.assert_export_refused("first.page.toml: functions need the page's load event")

    def test_build_and_import_keep_the_function(self):
        dump = self.build_and_dump("functions")
        page = (dump / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("object 3 __f0", page)
        self.assertIn("| tsw __f0,0", page)
        self.assertIn("| click __f0,1", page)
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"),
                         self.WITH_FUNCTION)
        self.assertNotIn("__f0",
                         (self.source / "pages" / "first.page.toml").read_text(encoding="utf-8"))

    def test_import_stops_when_the_editor_changed_a_function(self):
        dump = self.build_and_dump("functions")
        edit_text(dump / "pages" / "00-first.txt", "=__g0_0*2", "=__g0_0*3")
        with self.assertRaisesRegex(NxwrightError, "first.nx: the Nextion Editor changed function "
                                                   "twice"):
            import_dump(dump, self.source)

    def test_import_keeps_an_editor_change_to_the_page_preinitialize_event(self):
        dump = self.build_and_dump("functions")
        edit_text(dump / "pages" / "00-first.txt", "| tsw __f0,0", "| tsw __f0,0\n    | x.val=5")
        import_dump(dump, self.source)
        text = (self.source / "pages" / "first.nx").read_text(encoding="utf-8")
        self.assertIn("on first.load:\n  x.val=5\n", text)
        self.assertNotIn("tsw", text)
        export_dump(self.source, self.folder / "again")
        self.assertIn("| tsw __f0,0\n    | x.val=5",
                      (self.folder / "again" / "pages" / "00-first.txt").read_text(encoding="utf-8"))

    def test_build_refuses_a_page_past_id_255_through_functions(self):
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8", newline="\n") as file:
            for number in range(253):
                file.write('\n[[component]]\nname = "v%d"\ntype = "variable"\n' % number)
        # The page, its 255 components, and the function's hotspot.
        self.assert_export_refused("the page has 257 objects; at most 256 fit")


class EventCommentTest(NxlangFolderTestCase):
    """A comment right above an event's heading in a .nx file. The build puts it at
    the start of the event, each line marked `// ###`, and import puts it back above
    the heading."""

    PLAIN = "// Doubles a.\n//\n//  Twice.\non first.down:\n  x.val=a.val+a.val*2\n"

    def write_events(self, text: str):
        (self.source / "pages" / "first.nx").write_text(text, encoding="utf-8", newline="\n")

    def events(self) -> str:
        return (self.source / "pages" / "first.nx").read_text(encoding="utf-8")

    def test_plain_build_and_import(self):
        self.write_events(self.PLAIN)
        dump = self.build_and_dump("plain-comments")
        page = (dump / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("| // ### Doubles a.\n    | // ###\n    | // ###  Twice.\n"
                      "    | x.val=a.val+a.val*2", page)
        import_dump(dump, self.source)
        self.assertEqual(self.events(), self.PLAIN)

    def test_plain_import_of_comments_the_editor_changed(self):
        self.write_events(self.PLAIN)
        dump = self.build_and_dump("plain-comments")
        edit_text(dump / "pages" / "00-first.txt", "| // ### Doubles a.", "| // ### Doubles a, twice.")
        # A marked line after the code is an ordinary comment.
        edit_text(dump / "pages" / "00-first.txt", "| x.val=a.val+a.val*2",
                  "| x.val=a.val+a.val*2\n    | // ### later")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), self.PLAIN.replace("Doubles a.", "Doubles a, twice.")
                         + "  // ### later\n")

    def test_plain_import_keeps_the_code_when_only_the_comment_changed(self):
        text = "// Doubles a.\non first.down:\n  x.val=a.val\n\n  x.val+=a.val\n"
        self.write_events(text)
        dump = self.build_and_dump("plain-comments")
        edit_text(dump / "pages" / "00-first.txt", "| // ### Doubles a.", "| // ### Twice a.")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), text.replace("Doubles a.", "Twice a."))

    def test_nxlang_build_and_import(self):
        switch_to_nxlang(self.source)
        self.set_events("first", ["load", "down", "up"])
        text = ("// The page's functions.\n\n"
                "// Twice its argument.\nfunction twice(n: number) -> number:\n  return n * 2\n\n"
                "// Runs first.\non first.load:\n  x.val = 0\n\n"
                "// Doubles a.\non first.down:\n  x.val = twice(a.val)\n\n"
                "on first.up:\n  x.val = 1\n")
        self.write_events(text)
        dump = self.build_and_dump("nxlang-comments")
        page = (dump / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("| // ### Runs first.\n    | tsw __f0,0\n    | x.val=0", page)
        self.assertIn("| // ### Doubles a.\n", page)
        # The comments above a function and at the top stay in the .nx file only.
        self.assertNotIn("Twice its argument", page)
        self.assertNotIn("functions.", page)
        import_dump(dump, self.source)
        self.assertEqual(self.events(), text)
        edit_text(dump / "pages" / "00-first.txt", "| // ### Runs first.", "| // ### Runs at once.")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), text.replace("Runs first.", "Runs at once."))

    # Comments above no heading: before the first event, between two, and
    # after the last. A blank line parts each from what follows.
    STRAY = ("// The page's events.\n\non first.down:\n  x.val=1\n\n// --- Releases ---\n\n"
             "// More of the section.\n\non first.up:\n  x.val=2\n\n// The end.\n")

    def test_a_comment_above_no_heading_is_left_out_of_the_project(self):
        self.set_events("first", ["down", "up"])
        self.write_events(self.STRAY)
        page = (self.build_and_dump("stray-comments") / "pages" / "00-first.txt").read_text(
            encoding="utf-8")
        for comment in ("events.", "Releases", "More of", "The end"):
            self.assertNotIn(comment, page)
        self.assertEqual(check_folder(folder_reader(self.source),
                                      lambda path: (self.source / path).is_file()).findings(), [])
        # A comment right after an event's code, at the file's end, alike.
        self.write_events("on first.down:\n  x.val=1\n// The end.\n")
        self.build_and_dump("comment-at-the-end")

    def test_import_keeps_a_comment_above_no_heading(self):
        # Where the project changed the code of the event after it, too.
        self.set_events("first", ["down", "up"])
        self.write_events(self.STRAY)
        dump = self.build_and_dump("stray-comments")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), self.STRAY)
        edit_text(dump / "pages" / "00-first.txt", "| x.val=2", "| x.val=3")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), self.STRAY.replace("x.val=2", "x.val=3"))

    def test_nxlang_import_keeps_a_comment_above_no_heading(self):
        switch_to_nxlang(self.source)
        self.set_events("first", ["down", "up"])
        text = ("on first.down:\n  x.val = 1\n\n// --- Releases ---\n\non first.up:\n"
                "  x.val = 2\n\n// The end.\n")
        self.write_events(text)
        dump = self.build_and_dump("nxlang-stray-comments")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), text)
        edit_text(dump / "pages" / "00-first.txt", "| x.val=2", "| x.val=3")
        import_dump(dump, self.source)
        self.assertEqual(self.events(), text.replace("x.val = 2", "x.val=3"))

    def test_switching_to_nxlang_keeps_a_comment_above_no_heading(self):
        # nxlang reads the line otherwise, so the switch writes the file again.
        self.write_events("// The page's events.\n\non first.down:\n  x.val=a.val+a.val*2\n\n"
                          "// The end.\n")
        switch_to_nxlang(self.source)
        events = self.events()
        self.assertNotIn("x.val=a.val+a.val*2", events)
        self.assertTrue(events.startswith("// The page's events.\n\non first.down:\n"), events)
        self.assertTrue(events.endswith("\n\n// The end.\n"), events)

    def test_a_comment_inside_an_events_code_is_refused(self):
        # At the start of its line, it may have been meant as code.
        for text in ["on first.down:\n  x.val=1\n// inside\n  x.val=2\n",
                     "on first.down:\n  x.val=1\n// inside\n\n  x.val=2\n"]:
            with self.subTest(text=text):
                self.write_events(text)
                self.assert_export_refused("a comment at the start of a line, inside the code "
                                           "of first.down: indent it as its code, or move it "
                                           "right above a heading")


def block(code: str) -> str:
    """Returns `code` indented as an event's body in a .nx file."""
    return "\n".join("  " + line if line else "" for line in code.split("\n"))


class JumpTest(unittest.TestCase):
    """break, continue, and switch."""

    def run_code(self, code: str, values: dict = None, preamble: str = "") -> EditorMachine:
        return run_page(preamble + FUNCTIONS + "on p.down:\n" + block(code) + "\n", values)

    def test_while(self):
        code = """x.val = 0
r.val = 0
while (x.val < 10) {
  x.val++
  if (x.val == 3) {
    continue
  }
  if (x.val == 6) {
    break
  }
  r.val += x.val
}"""
        values = self.run_code(code).values
        self.assertEqual((values["x.val"], values["r.val"]), (6, 1 + 2 + 4 + 5))

    def test_for_runs_its_step_after_continue_not_after_break(self):
        code = """r.val = 0
for (x.val = 0; x.val < 10; x.val++) {
  if (x.val == 2) {
    continue
  }
  if (x.val == 4) {
    break
  }
  r.val += x.val
}"""
        values = self.run_code(code).values
        self.assertEqual((values["x.val"], values["r.val"]), (4, 0 + 1 + 3))

    def test_code_after_break_does_not_run(self):
        code = """x.val = 0
while (x.val < 5) {
  x.val++
  if (x.val == 2) {
    break
    r.val = 99
  }
  r.val += 1
}"""
        values = self.run_code(code).values
        self.assertEqual((values["x.val"], values["r.val"]), (2, 1))

    def test_break_leaves_only_the_inner_loop(self):
        code = """r.val = 0
for (x.val = 0; x.val < 3; x.val++) {
  d.val = 0
  while (d.val < 100) {
    d.val++
    if (d.val == 2) {
      break
    }
  }
  r.val += d.val
}"""
        self.assertEqual(self.run_code(code).values["r.val"], 6)

    def test_loop_condition_with_or(self):
        code = """x.val = 0
while (x.val < 3 || a.val == 0) {
  x.val++
  if (x.val == 5) {
    break
  }
}"""
        self.assertEqual(self.run_code(code).values["x.val"], 3)

    def test_no_call_after_break(self):
        code = """r.val = 0
while (bump() == 1) {
  r.val++
  if (r.val == 2) {
    break
  }
}"""
        # c.val starts at 5, and bump adds 1 on each of the two passes only.
        self.assertEqual(self.run_code(code).values["c.val"], 7)

    def test_switch(self):
        code = """switch (a.val) {
  case 1:
    t0.txt = "one"
    break
  case 7:
  case 8:
    t0.txt = "seven or eight"
    break
  default:
    t0.txt = "other"
}"""
        # A negative case value.
        code = code.replace("case 1:", "case -1:")
        for value, expected in ((7, "seven or eight"), (8, "seven or eight"), (-1, "one"),
                                (2, "other")):
            with self.subTest(value=value):
                self.assertEqual(self.run_code(code, {"a.val": value}).values["t0.txt"], expected)

    def test_switch_on_text_with_constants(self):
        code = """switch (t1.txt) {
  case "x":
    r.val = 1
    break
  case AB:
    r.val = 2
}"""
        values = self.run_code(code, preamble='const AB = "ab"\n\n').values
        self.assertEqual(values["r.val"], 2)

    def test_falling_through(self):
        code = """r.val = 0
switch (a.val) {
  case 7:
    r.val += 1
  case 8:
    r.val += 10
    break
  case 9:
    r.val += 100
}"""
        self.assertEqual(self.run_code(code).values["r.val"], 11)
        self.assertEqual(self.run_code(code, {"a.val": 9}).values["r.val"], 100)
        self.assertEqual(self.run_code(code, {"a.val": 0}).values["r.val"], 0)

    def test_default_first_falls_through(self):
        code = """r.val = 0
switch (a.val) {
  default:
    r.val += 1
  case 1:
    r.val += 10
}"""
        self.assertEqual(self.run_code(code).values["r.val"], 11)
        self.assertEqual(self.run_code(code, {"a.val": 1}).values["r.val"], 10)

    def test_switch_in_a_loop(self):
        loop = """r.val = 0
for (x.val = 0; x.val < 3; x.val++) {
  switch (x.val) {
    case 1:
      %s
    default:
      r.val += 1
  }
  r.val += 10
}"""
        # break leaves the switch only; continue skips the rest of the pass.
        self.assertEqual(self.run_code(loop % "break").values["r.val"], 32)
        self.assertEqual(self.run_code(loop % "continue").values["r.val"], 22)

    def test_an_event_run_twice(self):
        code = """x.val = 0
while (x.val < 5) {
  x.val++
  if (x.val == 2) {
    break
  }
}
switch (a.val) {
  case 7:
    r.val += 1
    break
  default:
    r.val += 100
}"""
        machine = self.run_code(code)
        # The generated variables the first run left set must not change the second.
        machine.run(machine.events[KEY])
        self.assertEqual((machine.values["x.val"], machine.values["r.val"]), (2, 2))

    def test_in_a_function(self):
        functions = """function firstOver(limit: number) -> number:
  var n = 0
  while (n < 100) {
    n++
    if (n > limit) {
      break
    }
  }
  switch (n) {
    case 4:
      n = 40
      break
    default:
      n = 0
  }
  return n

"""
        self.assertEqual(self.run_code("x.val = firstOver(3)", preamble=functions).values["x.val"], 40)

    def test_refusals(self):
        for code, message in [
                # Line 1 is the event's heading.
                ("break", "line 2: break can only be in a loop or a switch"),
                ("switch (a.val) {\n  case 1:\n    continue\n}", "line 4: continue can only be in a loop"),
                ("case 1:", "line 2: case and default can only be in a switch"),
                ("switch (a.val) {\n  x.val = 1\n  case 1:\n}", "line 3: code before the first case"),
                ("switch (a.val) {\n  case 1:\n  case 1:\n}", "line 4: case 1 appears twice"),
                ("switch (a.val) {\n  case 1:\n  case 0x1:\n}", "line 4: case 0x1 appears twice"),
                # In 32 bits, as C compares them.
                ("switch (a.val) {\n  case -1:\n  case 0xFFFFFFFF:\n}",
                 "line 4: case 0xFFFFFFFF appears twice"),
                ("switch (a.val) {\n  case 7:\n  case 007:\n}", "line 4: case 007 appears twice"),
                ("switch (a.val) {\n  default:\n  default:\n}", "line 4: a switch has one default"),
                ("switch (a.val) {\n  case b.val:\n}", "line 3: a case holds a number, a text"),
                ("switch (a.val) {\n  case \"x\":\n}", "line 3: the case's value is not of the switch's kind")]:
            with self.subTest(code=code), self.assertRaisesRegex(NxwrightError, message):
                run_page("on p.down:\n" + block(code) + "\n")

    def test_break_in_an_if_chain_before_a_nested_chain(self):
        code = """x.val = 0
r.val = 0
while (x.val < 5) {
  x.val++
  if (x.val == 3) {
    break
  } else {
    if (x.val == 1) {
      r.val += 100
    }
  }
  r.val += 1
}"""
        values = self.run_code(code).values
        self.assertEqual((values["x.val"], values["r.val"]), (3, 102))

    def test_program_cannot_jump(self):
        program = ProgramNames()
        for code, message in [
                ("while (sys0 < 3) {\n  break\n}", "line 1: program.nx cannot use break or continue"),
                ("switch (sys0) {\n  case 1:\n}", "line 1: program.nx cannot use switch")]:
            with self.subTest(code=code), self.assertRaisesRegex(NxwrightError, message):
                compile_program(_numbered(code), program)

    def test_names_of_keywords(self):
        with self.assertRaisesRegex(NxwrightError, "local case has the name of a component, "
                                                   "variable, or keyword"):
            run_page("on p.down:\n  var case = 1\n")
        # A component may keep such a name.
        compiled = compile_nxlang_page("on p.down:\n  case.val = 1\n", "p", COMPONENTS + ["case"],
                                       ProgramNames())
        self.assertEqual(preprocess(compiled.events[KEY], NO_NAMES), ["case.val=1"])


class JumpSourceFolderTest(NxlangFolderTestCase):

    LOOP = ("on first.down:\n  x.val = 0\n  while (x.val < 9) {\n    x.val++\n"
            "    if (x.val == a.val) {\n      break\n    }\n  }\n")

    def setUp(self):
        super().setUp()
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text(self.LOOP, encoding="utf-8", newline="\n")

    def test_import_keeps_the_loop_and_stops_on_an_editor_change(self):
        dump = self.build_and_dump("jumps")
        # __g0_0 is the loop's control variable, which the break sets to 2.
        self.assertIn("__g0_0=2", (dump / "pages" / "00-first.txt").read_text(encoding="utf-8"))
        import_dump(dump, self.source)
        self.assertEqual((self.source / "pages" / "first.nx").read_text(encoding="utf-8"), self.LOOP)
        edit_text(dump / "pages" / "00-first.txt", "__g0_0=2", "__g0_0=1")
        with self.assertRaisesRegex(NxwrightError, "it uses the generated variable __g0_0"):
            import_dump(dump, self.source)


class FewerObjectsTest(unittest.TestCase):
    """How the compiler keeps a page's objects few: generated numbers are program.s
    globals, events share temporaries, and the functions of one call depth share a
    hotspot."""

    def test_globals_are_named_after_the_page(self):
        compiled = compile_nxlang_page("on p.down:\n  x.val = a.val - b.val * c.val\n", "p",
                                       COMPONENTS, ProgramNames(), page_id=3)
        self.assertEqual(compiled.globals, ["__g3_0"])
        self.assertEqual(compiled.generated, [])

    def test_declarations_hold_50_names_a_line(self):
        names = ["__g0_%d" % number for number in range(120)]
        lines = global_declarations(names)
        self.assertEqual([line.count("=0") for line in lines], [50, 50, 20])
        self.assertTrue(lines[0].startswith("int __g0_0=0,__g0_1=0,"))
        self.assertEqual(without_global_declarations(lines + ["page 0"]), ["page 0"])

    def test_events_share_temporaries(self):
        text = ("on p.down:\n  x.val = a.val - b.val * c.val\n\n"
                "on p.up:\n  r.val = a.val - b.val * d.val\n")
        compiled = compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
        self.assertEqual(compiled.globals, ["__g0_0"])

    def test_program_int_names_may_not_start_with_the_prefix(self):
        with self.assertRaisesRegex(NxwrightError, "line 2: int __x may not start with"):
            read_program_names(_numbered("int a=0\nint __x=0"))

    def test_caller_temporaries_survive_a_call(self):
        functions = "function poly(n: number) -> number:\n  return n - n * n\n\n"
        code = "x.val = a.val - b.val * c.val + poly(d.val)"
        machine = run_page(functions + "on p.down:\n  " + code + "\n")
        self.assertEqual(machine.values["x.val"], 7 + 15 + (2 - 4))

    def test_depths(self):
        functions = ("function h(n: number) -> number:\n  return n + 1\n\n"
                     "function g(n: number) -> number:\n  return h(n) * 2\n\n"
                     "function f(n: number) -> number:\n  return g(n) + h(n)\n\n")
        text = functions + "on p.down:\n  x.val = f(1)\n  r.val = h(5)\n"
        compiled = compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
        self.assertEqual([(name, function.depth, function.hotspot)
                          for name, function in compiled.functions.items()],
                         [("h", 3, "__f2"), ("g", 2, "__f1"), ("f", 1, "__f0")])
        values = run_page(text).values
        self.assertEqual((values["x.val"], values["r.val"]), (2 * 2 + 2, 6))

    def test_functions_sharing_a_hotspot(self):
        # add and bump share the depth 1 hotspot. Calling bump, for add's argument,
        # selects bump's body, so add's call must select add's body again.
        machine = FunctionTest.run_code(FunctionTest(), "x.val = add(bump(), 1)")
        self.assertEqual((machine.values["x.val"], machine.values["c.val"]), (2, 6))

    def test_call_depth_limit(self):
        names = ["f%d" % number for number in range(9)]
        functions = "".join("function %s() -> number:\n  return %s\n\n"
                            % (name, "%s() + 1" % following if following else "1")
                            for name, following in zip(names, names[1:] + [None]))
        # f0 calls f1, and so on to f8. Cut after f6, the calls nest 7 deep;
        # cut after f7, 8 deep.
        run_page(functions.replace("f7() + 1", "1") + "on p.down:\n  x.val = f0()\n")
        with self.assertRaisesRegex(NxwrightError, "the calls f0 -> f1 -> f2 -> f3 -> f4 -> f5 "
                                                   "-> f6 -> f7 nest 8 deep; at most 7"):
            run_page(functions.replace("f8() + 1", "1") + "on p.down:\n  x.val = f0()\n")


def text_variables(text: str) -> list:
    """Returns the names of the long-lived text variables, __v0 and on, that compiling
    `text` as page p generates."""
    compiled = compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
    return [variable.name for variable in compiled.generated if variable.name.startswith("__v")]


class SharedVariablesTest(unittest.TestCase):
    """Long-lived text variables, which events and functions share when they can
    never run at once. Calls, and `click` commands in the code, decide which can."""

    def test_a_click_in_a_function_leaves_the_callers_temporaries(self):
        # first's result waits in a temporary while second runs; second clicks
        # t0, whose event uses temporaries too.
        text = ('function first(s: text) -> text:\n  return s + "1"\n\n'
                'function second(s: text) -> text:\n  click t0,1\n  return s + "2"\n\n'
                'on t0.down:\n  t1.txt = "z" + t1.txt\n\n'
                'on p.down:\n  x.txt = first("p") + second("q")\n')
        values = run_page(text, {"x.txt": "", "t1.txt": "ab"}).values
        self.assertEqual((values["x.txt"], values["t1.txt"]), ("p1q2", "zab"))

    def test_a_click_in_a_function_runs_another_function_once(self):
        # f and g would share a hotspot: g, called from the event f clicks,
        # must not run a second time when f's body ends.
        text = ("function f() -> number:\n  click t0,1\n  return 1\n\n"
                "function g() -> number:\n  c.val += 1\n  return 2\n\n"
                "on t0.down:\n  r.val = g()\n\n"
                "on p.down:\n  x.val = f()\n")
        values = run_page(text, {"c.val": 0}).values
        self.assertEqual((values["x.val"], values["r.val"], values["c.val"]), (1, 2, 1))

    def test_separate_chains_share(self):
        text = ('function f() -> text:\n  var s = "f"\n  return s + "1"\n\n'
                'function g() -> text:\n  var s = "g"\n  var u = "2"\n  return s + u\n\n'
                'on p.down:\n  x.txt = f()\n  r.txt = g()\n')
        # g's three (its result and two locals) cover f's two.
        self.assertEqual(text_variables(text), ["__v0", "__v1", "__v2"])
        values = run_page(text, {"x.txt": "", "r.txt": ""}).values
        self.assertEqual((values["x.txt"], values["r.txt"]), ("f1", "g2"))

    def test_a_caller_and_its_callee_never_share(self):
        text = ('function g(s: text) -> text:\n  var u = s + "g"\n  return u\n\n'
                'function f(s: text) -> text:\n  var kept = s + "f"\n  var got = g("x")\n'
                '  return kept + got\n\n'
                'on p.down:\n  var mine = "e"\n  x.txt = f("a")\n  r.txt = mine\n')
        values = run_page(text, {"x.txt": "", "r.txt": ""}).values
        self.assertEqual((values["x.txt"], values["r.txt"]), ("afxg", "e"))
        # The heaviest chain: the event's local, f's parameter, result, and two
        # locals, g's parameter, result, and local.
        self.assertEqual(len(text_variables(text)), 1 + 4 + 3)

    def test_a_clicking_event_and_the_event_it_clicks_never_share(self):
        # click t0,1 runs t0's Touch Press event; click t0,0 its Touch Release.
        for event, which in (("down", 1), ("up", 0)):
            with self.subTest(event=event):
                text = ('on t0.%s:\n  var other = "b"\n  t1.txt = other\n\n'
                        'on p.down:\n  var mine = "a"\n  click t0,%d\n  x.txt = mine + t1.txt\n'
                        % (event, which))
                values = run_page(text, {"x.txt": ""}).values
                self.assertEqual(values["x.txt"], "ab")
                self.assertEqual(len(text_variables(text)), 2)

    def test_events_that_never_run_at_once_share(self):
        text = ('on t0.down:\n  var other = "b"\n  t1.txt = other\n\n'
                'on p.down:\n  var mine = "a"\n  x.txt = mine\n')
        self.assertEqual(text_variables(text), ["__v0"])

    def test_calls_in_arguments_with_shared_variables(self):
        functions = ('function f(s: text, u: text) -> text:\n  return s + "-" + u\n\n'
                     'function g(s: text) -> text:\n  return "<" + s + ">"\n\n')
        for code, expected in (('x.txt = f(g("a"), "b")', "<a>-b"),
                               ('x.txt = f("a", g("b"))', "a-<b>"),
                               ('x.txt = f("a", "b") + g("c")', "a-b<c>"),
                               ('x.txt = g(f("a", g("b")))', "<a-<b>>")):
            with self.subTest(code=code):
                values = run_page(functions + "on p.down:\n  " + code + "\n", {"x.txt": ""}).values
                self.assertEqual(values["x.txt"], expected)

    def test_a_text_switch_value_is_shared_too(self):
        text = ('function f(s: text) -> number:\n  var n = 0\n  switch (s) {\n    case "a":\n      n = 1\n'
                '  }\n  return n\n\n'
                'on p.down:\n  x.val = f("a")\n')
        compiled = compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
        # The hotspot, then the parameter and the switch's value.
        self.assertEqual([variable.name for variable in compiled.generated],
                         ["__f0", "__v0", "__v1"])
        self.assertEqual(run_page(text).values["x.val"], 1)

    def test_call_and_click_nesting_limit(self):
        # Each call and each click runs one more event inside the current one, and at
        # most 7 may nest. Here p.down calls f0, on to f5, and f5 clicks t0: 7 deep.
        names = ["f%d" % number for number in range(6)]
        functions = "".join("function %s() -> number:\n  %s\n  return 1\n\n"
                            % (name, "c.val = %s()" % following if following else "click t0,1")
                            for name, following in zip(names, names[1:] + [None]))
        run_page(functions + "on t0.down:\n  c.val += 1\n\non p.down:\n  x.val = f0()\n")
        deeper = "on t0.down:\n  click t1,1\n\non t1.down:\n  c.val += 1\n\non p.down:\n  x.val = f0()\n"
        with self.assertRaisesRegex(NxwrightError, "the calls and clicks p.down -> f0 -> f1 -> f2 -> f3 "
                                                   "-> f4 -> f5 -> t0.down -> t1.down nest 8 deep; "
                                                   "at most 7"):
            run_page(functions + deeper)

    def test_a_cycle_through_clicks_is_refused(self):
        text = "on t0.down:\n  click p,1\n\non p.down:\n  click t0,1\n"
        with self.assertRaisesRegex(NxwrightError, "t0.down -> p.down -> t0.down"):
            compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())
        text = "function f():\n  click p,1\n\non p.down:\n  f()\n"
        with self.assertRaisesRegex(NxwrightError, "p.down -> f -> p.down"):
            compile_nxlang_page(text, "p", COMPONENTS, ProgramNames())

    def test_a_click_must_name_its_component_and_event(self):
        for click in ("click b[3],1", "click t0,c.val", "click t0", "click 3,1"):
            with self.subTest(click=click):
                with self.assertRaisesRegex(NxwrightError, "line 2: .*click"):
                    compile_nxlang_page("on p.down:\n  %s\n" % click, "p", COMPONENTS,
                                        ProgramNames())
        # A constant stands for its value: the click names no component.
        with self.assertRaisesRegex(NxwrightError, "line 3: .*click"):
            compile_nxlang_page("const B = 3\non p.down:\n  click B,1\n", "p", COMPONENTS,
                                ProgramNames())


FIXED = """const SCALE = 1000

function toFixed(whole: number) -> number:
  return whole * SCALE

function toWhole(fixed: number) -> number:
  return fixed / SCALE
"""
UNITS = """include "fixed.nx"
const MM_PER_INCH = 25

function inchesToMm(inches: number) -> number:
  return toWhole(toFixed(inches) * MM_PER_INCH)

function unused() -> number:
  return toFixed(1) + 1
"""


class IncludeTest(unittest.TestCase):

    def test_library_including_a_library(self):
        files = {"pages/lib/fixed.nx": FIXED, "pages/lib/units.nx": UNITS}
        page = 'include "lib/units.nx"\ninclude "lib/fixed.nx"\n\non p.down:\n  x.val = inchesToMm(a.val) + SCALE\n'
        self.assertEqual(run_page(page, files=files).values["x.val"], 7 * 25 + 1000)

    def test_only_called_functions_generate_anything(self):
        files = {"pages/lib/fixed.nx": FIXED, "pages/lib/units.nx": UNITS}
        page = 'include "lib/units.nx"\n\non p.down:\n  x.val = inchesToMm(a.val)\n'
        compiled = compile_nxlang_page(page, "p", COMPONENTS, ProgramNames(), read=reader(files))
        self.assertEqual({name: function.depth for name, function in compiled.functions.items()},
                         {"toFixed": 2, "toWhole": 2, "inchesToMm": 1})
        # inchesToMm has the depth 1 hotspot, and toFixed and toWhole share the depth 2
        # one. unused, never called, adds nothing.
        self.assertEqual([variable.name for variable in compiled.generated], ["__f0", "__f1"])
        self.assertEqual(compiled.functions["toFixed"].hotspot, compiled.functions["toWhole"].hotspot)

    def test_an_uncalled_function_may_name_other_pages_components(self):
        # One theme file holds a function per page; each names its own page's components.
        files = {"pages/theme.nx": "function themeOther():\n  missing.pic=pic_x\n\n"
                                   "function themeP():\n  x.pco=pic_x\n"}
        page = 'include "theme.nx"\n\non p.load:\n  themeP()\n'
        program = ProgramNames(variables=frozenset({"pic_x"}))
        compiled = compile_nxlang_page(page, "p", COMPONENTS, program, read=reader(files))
        self.assertEqual(list(compiled.functions), ["themeP"])

    def test_a_page_split_into_two_files(self):
        files = {"pages/p/keys.nx": "on b.down:\n  r.val = 2\n"}
        page = 'include "p/keys.nx"\n\non p.down:\n  r.val = 1\n'
        compiled = compile_nxlang_page(page, "p", COMPONENTS + ["b"], ProgramNames(),
                                       read=reader(files))
        self.assertEqual(preprocess(compiled.events[("b", "down")], NO_NAMES), ["r.val=2"])
        self.assertEqual(compiled.sources[("b", "down")], "pages/p/keys.nx")

    def test_errors_name_the_file(self):
        broken = FIXED.replace("return fixed / SCALE", "return fixed / ")
        files = {"pages/lib/fixed.nx": broken}
        page = 'include "lib/fixed.nx"\n\non p.down:\n  x.val = toFixed(1)\n'
        # toWhole is not called, and still checked.
        with self.assertRaisesRegex(NxwrightError, "pages/lib/fixed.nx line 7:"):
            run_page(page, files=files)

    def test_call_chain_across_files(self):
        library = "".join("function f%d() -> number:\n  return %s\n\n" % (number, "f%d() + 1" % (number + 1)
                                                                           if number < 7 else "1")
                          for number in range(1, 8))
        page = 'include "deep.nx"\n\nfunction f0() -> number:\n  return f1()\n\non p.down:\n  x.val = f0()\n'
        # The error names f7, the eighth deep, at its heading: line 19 of deep.nx.
        with self.assertRaisesRegex(NxwrightError, "pages/deep.nx line 19: the calls f0 -> f1 .* -> f7 nest 8 deep"):
            run_page(page, files={"pages/deep.nx": library})

    def test_refusals(self):
        files = {"pages/lib/fixed.nx": FIXED, "pages/a.nx": "on p.down:\n  r.val = 1\n",
                 "pages/c.nx": "const SCALE = 2\n", "pages/bad.txt": ""}
        for page, message in [
                ('include "lib/none.nx"\non p.up:\n  r.val = 1\n',
                 "pages/p.nx line 1: pages/lib/none.nx is missing"),
                ('include "../../outside.nx"\non p.up:\n  r.val = 1\n', "leaves the source folder"),
                ('include "bad.txt"\non p.up:\n  r.val = 1\n', "bad.txt does not end in .nx"),
                ('include "a.nx"\n\non p.down:\n  r.val = 2\n',
                 "pages/p.nx line 3: p.down is also defined in pages/a.nx"),
                ('include "lib/fixed.nx"\ninclude "c.nx"\non p.up:\n  r.val = 1\n',
                 "pages/c.nx line 1: SCALE is already a constant"),
                ('include "lib/fixed.nx"\n\nfunction toFixed() -> number:\n  return 1\n',
                 "function toFixed is also defined in pages/lib/fixed.nx"),
                ('on p.up:\n  r.val = 1\ninclude "lib/fixed.nx"\n', "pages/p.nx line 3: expected")]:
            with self.subTest(page=page), self.assertRaisesRegex(NxwrightError, message):
                compile_nxlang_page(page, "p", COMPONENTS, ProgramNames(), read=reader(files))


class IncludeSourceFolderTest(NxlangFolderTestCase):
    """Includes through build and import, with two pages sharing a file."""

    SHARED = "const STEP = 3\n\non h.down:\n  x.val = STEP * 2\n"

    def setUp(self):
        super().setUp()
        switch_to_nxlang(self.source)
        for page in ("first", "second"):
            toml = self.source / "pages" / (page + ".page.toml")
            with open(toml, "a", encoding="utf-8", newline="\n") as file:
                file.write('\n[[component]]\nname = "h"\ntype = "hotspot"\nx = 0\ny = 0\nw = 50\nh = 50\n')
                if page == "second":
                    file.write('\n[[component]]\nname = "x"\ntype = "variable"\n')
            (self.source / "pages" / (page + ".nx")).write_text(
                'include "shared.nx"\n\non %s.up:\n  x.val = STEP + 1\n' % page,
                encoding="utf-8", newline="\n")
        self.set_events("first", ["up"])
        self.set_events("second", ["up"])
        (self.source / "pages" / "shared.nx").write_text(self.SHARED, encoding="utf-8", newline="\n")
        (self.source / "program.nx").write_text(
            'include "lib/constants.nx"\nint sys0=0\nsys0 = LIMIT\n', encoding="utf-8",
            newline="\n")
        (self.source / "lib").mkdir()
        (self.source / "lib" / "constants.nx").write_text("const LIMIT = 9\n", encoding="utf-8",
                                                          newline="\n")
        self.dump = self.build_and_dump("shared")

    def page_text(self, page: str) -> Path:
        return self.dump / "pages" / ("%02d-%s.txt" % (["first", "second"].index(page), page))

    def sources(self) -> dict:
        return {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}

    def test_build_and_import_keep_every_file(self):
        self.assertIn("| x.val=3*2", self.page_text("second").read_text(encoding="utf-8"))
        self.assertIn(b"sys0=9", (self.dump / "program.s").read_bytes())
        before = self.sources()
        import_dump(self.dump, self.source)
        self.assertEqual(self.sources(), before)

    def test_a_changed_event_is_written_where_it_is_defined(self):
        for page in ("first", "second"):
            edit_text(self.page_text(page), "x.val=3*2", "x.val=7")
        # Page first also gets a down event, which goes to first.nx.
        edit_text(self.page_text("first"), "x.val=3+1", "x.val=4\n  event down\n    | x.val=1")
        import_dump(self.dump, self.source)
        self.assertEqual((self.source / "pages" / "shared.nx").read_text(encoding="utf-8"),
                         "const STEP = 3\n\non h.down:\n  x.val=7\n")
        first = (self.source / "pages" / "first.nx").read_text(encoding="utf-8")
        self.assertEqual(first, 'include "shared.nx"\n\non first.up:\n  x.val=4\n\n'
                                'on first.down:\n  x.val=1\n')

    def test_an_emptied_event_is_removed_from_its_file(self):
        for page in ("first", "second"):
            edit_text(self.page_text(page), "    | x.val=3*2\n", "")
        import_dump(self.dump, self.source)
        self.assertEqual((self.source / "pages" / "shared.nx").read_text(encoding="utf-8"),
                         "const STEP = 3\n")

    def test_pages_disagreeing_about_a_shared_event_stop_the_import(self):
        before = self.sources()
        edit_text(self.page_text("first"), "x.val=3*2", "x.val=7")
        with self.assertRaisesRegex(NxwrightError, "pages/shared.nx: the Nextion Editor left "
                                                   "h.down different between pages first and "
                                                   "second"):
            import_dump(self.dump, self.source)
        edit_text(self.page_text("second"), "x.val=3*2", "x.val=8")
        with self.assertRaisesRegex(NxwrightError, "different between pages first and second"):
            import_dump(self.dump, self.source)
        self.assertEqual(self.sources(), before)

    def test_program_includes_constants_only(self):
        (self.source / "lib" / "constants.nx").write_text("const LIMIT = 9\n\non x.down:\n  r.val = 1\n",
                                                          encoding="utf-8", newline="\n")
        self.assert_export_refused("program.nx line 1: program.nx can include constants only")
        (self.source / "lib" / "constants.nx").write_text(
            "const LIMIT = 9\n\nfunction f() -> number:\n  return 1\n", encoding="utf-8", newline="\n")
        self.assert_export_refused("program.nx line 1: program.nx can include constants only")


class AnnotationTest(unittest.TestCase):

    def test_every_annotation_names_something_that_exists(self):
        # Python 3.14 reads annotations only when asked; 3.11 to 3.13 read
        # them on import, where a stale name stops the module loading.
        import inspect
        import typing
        from nxwright.language import editor_code, nxlang
        from nxwright.source import nx_files, page_source
        for module in (page_source, nxlang, editor_code, nx_files, source_folder):
            for name, member in inspect.getmembers(module, inspect.isfunction):
                if member.__module__ == module.__name__:
                    with self.subTest(function="%s.%s" % (module.__name__, name)):
                        typing.get_type_hints(member)


class TestBenchTest(unittest.TestCase):
    """The interpreter's string commands, and running a library function."""

    def run_lines(self, lines: list, values: dict = None) -> dict:
        return EditorMachine(dict({"s.txt": "", "n.val": 0, "sys0": 0}, **(values or {}))).run(lines)

    def test_commands_as_the_simulator_showed(self):
        number_to_text = [(5, 3, "005"), (1234, 3, "123"), (-5, 3, "-005"), (-1234, 0, "-1234")]
        for value, length, expected in number_to_text:
            with self.subTest(value=value, length=length):
                values = self.run_lines(["sys0=%d" % value, "covx sys0,s.txt,%d,0" % length])
                self.assertEqual(values["s.txt"], expected)
        for text, expected in [("007", 7), ("-12", -12), ("", 0), ("12abc", 12), ("1.5", 1)]:
            with self.subTest(text=text):
                values = self.run_lines(['s.txt="%s"' % text, "covx s.txt,sys0,0,0"])
                self.assertEqual(values["sys0"], expected)
        for start_text, command, expected in [
                ("hello", "substr s.txt,s.txt,1,3", "ell"), ("hi", "substr s.txt,s.txt,1,5", "i"),
                ("hello", "substr s.txt,s.txt,5,2", ""), ("a|b|c", 'spstr s.txt,s.txt,"|",1', "b"),
                ("a|b|c", 'spstr s.txt,s.txt,"|",5', ""), ("abc", 'spstr s.txt,s.txt,".",0', "abc"),
                ("abc", 'spstr s.txt,s.txt,".",1', ""), ("-", "substr s.txt,s.txt,0,1", "-")]:
            with self.subTest(command=command, text=start_text):
                self.assertEqual(self.run_lines(['s.txt="%s"' % start_text, command])["s.txt"], expected)
        self.assertEqual(self.run_lines(['s.txt=""', "strlen s.txt,sys0"])["sys0"], 0)
        self.assertEqual(self.run_lines(['s.txt="ab"', "btlen s.txt,sys0"])["sys0"], 2)

    def test_covx_with_commas_and_in_hex(self):
        # Seen in the Editor's simulator: format 1 separates thousands with
        # commas, and format 2 writes hex in whole bytes. Given a length, each
        # keeps its first characters, or pads with zeros.
        cases = [(0, 0, 1, "0"), (999, 0, 1, "999"), (1000, 0, 1, "1,000"),
                 (1234567, 0, 1, "1,234,567"), (-1234567, 0, 1, "-1,234,567"),
                 (1234567, 4, 1, "1,23"), (5, 4, 1, "0005"),
                 (0, 0, 2, "00"), (5, 0, 2, "05"), (255, 0, 2, "FF"), (4660, 0, 2, "1234"),
                 (-1, 0, 2, "FFFFFFFF"), (255, 2, 2, "FF"), (255, 4, 2, "00FF"),
                 (255, 6, 2, "0000FF"), (255, 8, 2, "000000FF"), (4660, 2, 2, "12"),
                 (-1, 4, 2, "FFFF")]
        for value, length, form, expected in cases:
            with self.subTest(value=value, length=length, form=form):
                values = self.run_lines(["sys0=%d" % value,
                                         "covx sys0,s.txt,%d,%d" % (length, form)])
                self.assertEqual(values["s.txt"], expected)
        # An odd number of hex digits: the screen leaves the text as it was.
        values = self.run_lines(['s.txt="kept"', "sys0=65535", "covx sys0,s.txt,3,2"])
        self.assertEqual(values["s.txt"], "kept")

    def test_calling_a_library_function(self):
        files = {"pages/lib/twice.nx": "function twice(n: number) -> number:\n  return n * 2\n"}
        self.assertEqual(call_function(files, "lib/twice.nx", "x.val = twice(a.val)")["x.val"], 14)


if __name__ == "__main__":
    unittest.main()
