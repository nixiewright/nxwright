"""The statement encoder (tft/statements.py): its blocks, against the
fixtures its probes kept (tools/tft/probing/statement_probes.py), and what it refuses.

Each test gives the encoder its own input: lines, where they lie, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py).
"""
import re
import struct
import types
import unittest
from unittest import mock

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import statements
from tools.tft.probing import number_probes, p_probes, statement_probes, text_probes
from nxwright.tft.component_types import code_entry
from nxwright.tft.instructions import for_statement
from nxwright.tft.matching import Need
from nxwright.tft.statements import (MATCHED, CodePlace, Command, StatementError, encodable,
                              encode_line, operand, program_variables)
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import page, piece, piece_names, probe_project, project_of


def texts_project():
    """Returns the Project of facts of the page of the texts t0 and t1, as
    the text's probe text-setting-second-txt adds them."""
    return probe_project(next(probe for probe in text_probes.PROBES
                              if probe.name == "text-setting-second-txt"))


class FixturesTest(unittest.TestCase):
    """Each probe's blocks, as the encoder gives them now on its page and
    program.s made in memory, are the pieces the probe kept once they
    matched the Nextion Editor's."""

    def test_each_probe(self):
        # On T, and on P, which keeps the blocks of the same lines.
        probes = [probe for probe in statement_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-statements-")]
        self.assertEqual(len(probes), 16)
        for probe in probes:
            with self.subTest(probe=probe.name):
                self.assertEqual(statement_probes.kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class LineTest(unittest.TestCase):
    """Lines that give no block, and those the encoder refuses."""

    @classmethod
    def setUpClass(cls):
        # The base folder's page0, in strict Nextion syntax, and program.s
        # declaring the ints a and b.
        declared = {"strict": True, "declarations": ("int a=1,b=2",)}
        cls.project = project_of(page(**declared), **declared)

    def test_lines_that_give_no_block(self):
        for line in ("int sys0=0,sys1=0,sys2=0", "// a comment", "  ", ""):
            with self.subTest(line=line):
                self.assertIsNone(encode_line(line, CodePlace(), CompileContext(self.project)))

    def test_an_int_declaration_in_an_event(self):
        with self.assertRaises(StatementError):
            encode_line("int a=1", CodePlace(0, "page0", "up"), CompileContext(self.project))

    def test_a_negative_number_after_an_operator(self):
        # The Nextion Editor writes its minus as the number's sign, as
        # written: sys0's operand, `=`, then 2*-16; and sys0's, then --1.
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=2*-16", place, CompileContext(self.project)),
                         bytes.fromhex("05 00 00 00 00 3d") + b"2*-16")
        self.assertEqual(encode_line("sys2=sys0--1", place, CompileContext(self.project)),
                         bytes.fromhex("05 08 00 00 00 3d 05 00 00 00 00") + b"--1")

    def test_a_colour_s_name_set(self):
        # Written as any assignment: the colour's operand, then the rest.
        self.assertEqual(encode_line("RED=5", CodePlace(), CompileContext(self.project)),
                         b"\x04\x04\x01\x00\x00=5")

    def test_spaces_are_dropped(self):
        self.assertEqual(encode_line("dim = 50", CodePlace(), CompileContext(self.project)),
                         encode_line("dim=50", CodePlace(), CompileContext(self.project)))

    def test_a_line_of_any_length(self):
        # nxwright's build refuses a line longer than its series takes, so
        # the encoder writes a line of any length: 767 bytes is the most T
        # takes, and 4095 the most P takes.
        for size in (767, 768, 4095):
            last = "11" if size % 2 else "1"
            line = "sys0=" + "1+" * ((size - 5 - len(last)) // 2) + last
            with self.subTest(size=size):
                self.assertEqual(len(line), size)
                self.assertEqual(encode_line(line, CodePlace(), CompileContext(self.project)),
                                 b"\x05\x00\x00\x00\x00" + line[len("sys0"):].encode("ascii"))
                self.assertTrue(encodable(line))

    def test_refused(self):
        for line in ('t0.txt="a"', "made_up t0,0", "sys0=-sys1",
                     "sys0=", "sys0=nothing", "page nosuch", "page 1,2",
                     "sys0=(1)", "{", "}"):
            with self.subTest(line=line), self.assertRaises(StatementError):
                encode_line(line, CodePlace(), CompileContext(self.project))

    def test_compound_assignments(self):
        # Each arithmetic operator's own assigning operator, written as its
        # text, as the Nextion Editor wrote it, and a minus after any
        # assigning operator starting a number.
        for line, written in (("sys0*=10", "05 00 00 00 00 2a 3d 31 30"),
                              ("sys0/=-2", "05 00 00 00 00 2f 3d 2d 32"),
                              ("sys0%=3", "05 00 00 00 00 25 3d 33"),
                              ("sys0&=1", "05 00 00 00 00 26 3d 31"),
                              ("sys0|=2", "05 00 00 00 00 7c 3d 32"),
                              ("sys0^=3", "05 00 00 00 00 5e 3d 33"),
                              ("sys0<<=1", "05 00 00 00 00 3c 3c 3d 31"),
                              ("sys0>>=1", "05 00 00 00 00 3e 3e 3d 31"),
                              ("sys0+=-1", "05 00 00 00 00 2b 3d 2d 31"),
                              ("sys0*=-1000", "05 00 00 00 00 2a 3d 03 18 fc ff ff")):
            with self.subTest(line=line):
                self.assertEqual(encode_line(line, CodePlace(),
                                             CompileContext(self.project)).hex(" "), written)

    def test_printh_of_any_count_of_bytes(self):
        # Its bytes as written, as the Nextion Editor wrote 17, 64, and 253
        # of them, the most a line of 767 characters holds on T. A longer
        # line is taken too, as nxwright's build holds a line to its series'
        # limit.
        for count in (17, 64, 253, 254):
            line = "printh " + " ".join("%02x" % (number % 256) for number in range(count))
            with self.subTest(count=count):
                self.assertEqual(encode_line(line, CodePlace(), CompileContext(self.project)),
                                 b"\x09\x0b\x08" + line[len("printh "):].encode("ascii"))

    def test_f_s_own_numbers(self):
        # F numbers baud 0x1a, where T numbers it 0x0e, as F's probes showed.
        on_t = encode_line("sys0=baud", CodePlace(), CompileContext(self.project))
        on_f = encode_line("sys0=baud", CodePlace(), CompileContext(project_of(series="F")))
        self.assertEqual(on_f, on_t.replace(b"\x04\x0e", b"\x04\x1a"))
        self.assertNotEqual(on_f, on_t)

    def test_a_command_of_instructions(self):
        # As a family of commands' module gives it: arguments as operands,
        # their commas kept, as `randset 0,100` was seen.
        family = types.ModuleType("nxwright.tft.instructions.family")
        family.COMMANDS = {"T": {"randset": Command(0x16, 8)}}
        statements.series_commands.cache_clear()
        self.addCleanup(statements.series_commands.cache_clear)
        with mock.patch.object(statements, "_instruction_modules", lambda: [family]):
            self.assertEqual(encode_line("randset 0,1000", CodePlace(),
                                         CompileContext(self.project)),
                             b"\x09\x16\x080," + bytes([3, 0xe8, 3, 0, 0]))

    def test_digits_of_other_scripts(self):
        with self.assertRaises(StatementError):
            encode_line("sys0=\u0663", CodePlace(), CompileContext(self.project))

    def test_program_variables_in_the_order_declared(self):
        self.assertEqual(program_variables(self.project), ["sys0", "sys1", "sys2", "a", "b"])

    def test_program_variables_without_a_comment_after_them(self):
        # A comment after a declaration names no variable, even with commas
        # in it, as in a new project's first line; and a tab may follow int.
        program = ("int sys0=0,sys1=0,sys2=0     //At present, a comment, with commas\r\n"
                   "int\ta=1 // b, c\r\n").encode("ascii")
        project = types.SimpleNamespace(program=program,
                                        settings=types.SimpleNamespace(encoding="iso-8859-1"))
        self.assertEqual(program_variables(project), ["sys0", "sys1", "sys2", "a"])


class OperandTest(unittest.TestCase):
    """One operand alone, as a control statement's module encodes it."""

    @classmethod
    def setUpClass(cls):
        cls.project = texts_project()

    def test_each_kind(self):
        # t1's entries follow the page's 33 and t0's 41; txt is its 29th.
        for text, expected in (("5", b"5"), ("-1000", b"\x03" + struct.pack("<i", -1000)),
                               ("sys1", b"\x05\x04\x00\x00\x00"),
                               ("RED", b"\x04\x04\x01\x00\x00"),
                               ("t1.txt", b"\x01" + struct.pack("<I", 33 + 41 + 28))):
            with self.subTest(text=text):
                self.assertEqual(operand(text, CodePlace(0, "t0", "up"),
                                         CompileContext(self.project)), expected)

    def test_past_32_bits(self):
        # A number keeps its low 32 bits, as `page 2147483648` gave
        # 03 00 00 00 80 (ResearchNotes/tft/statements.md). A hexadecimal number
        # may have leading zeros, or an odd count of digits, and is 03 and its
        # value, as any other.
        for text, expected in (("2147483648", b"\x03\x00\x00\x00\x80"),
                               ("-2147483649", b"\x03\xff\xff\xff\x7f"),
                               ("0x0000000001", b"\x03\x01\x00\x00\x00"),
                               ("0x1", b"\x03\x01\x00\x00\x00"),
                               ("0xF8000", b"\x03\x00\x80\x0f\x00")):
            with self.subTest(text=text):
                self.assertEqual(operand(text, CodePlace(0, "t0", "up"),
                                         CompileContext(self.project)), expected)

    def test_refused(self):
        for text, place, said in (("sys0+1", CodePlace(0, "t0", "up"), "not one operand"),
                                  ('"a"', CodePlace(0, "t0", "up"), "not one operand"),
                                  ("", CodePlace(0, "t0", "up"), "not one operand"),
                                  ("t1.txt", CodePlace(), "attribute in program.s")):
            with self.subTest(text=text), self.assertRaisesRegex(StatementError, said):
                operand(text, place, CompileContext(self.project))


class CommandTest(unittest.TestCase):
    """A command alone on its line, and one whose first argument is a
    component, as a family of commands' module gives them."""

    @classmethod
    def setUpClass(cls):
        # The texts t0 and t1 on page0.
        cls.project = texts_project()

    def setUp(self):
        family = types.ModuleType("nxwright.tft.instructions.family")
        family.COMMANDS = {"T": {"doevents": Command(0x21, 8, ""),
                                 "vis": Command(0x05, 4, r"\w+, ?\w+", component=True)}}
        statements.series_commands.cache_clear()
        self.addCleanup(statements.series_commands.cache_clear)
        patch = mock.patch.object(statements, "_instruction_modules", lambda: [family])
        patch.start()
        self.addCleanup(patch.stop)

    def test_alone(self):
        self.assertEqual(encode_line("doevents", CodePlace(),
                                     CompileContext(self.project)), b"\x09\x21\x08")
        with self.assertRaises(StatementError):
            encode_line("doevents 1", CodePlace(), CompileContext(self.project))

    def test_a_component(self):
        event = CodePlace(0, "t0", "up")
        # By name, kept as written, then an operand.
        self.assertEqual(encode_line("vis t1, sys1", event, CompileContext(self.project)),
                         b"\x09\x05\x04t1," + b"\x05\x04\x00\x00\x00")
        # By ID, in program.s too.
        self.assertEqual(encode_line("vis 2,0", CodePlace(),
                                     CompileContext(self.project)), b"\x09\x05\x042,0")
        # A name not on the line's page, and a component's name in program.s,
        # neither of them a variable's.
        for line, place in (("vis t9,0", event), ("vis t0,0", CodePlace())):
            with self.subTest(line=line), self.assertRaisesRegex(
                    StatementError, "is neither a component of .* nor a variable"):
                encode_line(line, place, CompileContext(self.project))

    def test_left_to_its_own_rule(self):
        rule, = MATCHED
        self.assertTrue(encodable("doevents"))
        self.assertFalse(rule.matches(Need("code", "event", "doevents")))

    def test_the_patterns(self):
        pattern = statements.operands("x", 3)
        for text, matches in (("x,x,x", True), ("x, x, x", True), ("x,x", False),
                              ("x,  x,x", False)):
            with self.subTest(text=text):
                self.assertEqual(re.fullmatch(pattern, text) is not None, matches)
        for line, name in (("  vis t0,0", "vis"), ("doevents", "doevents"), ("sys0=1", "sys0=1")):
            with self.subTest(line=line):
                self.assertEqual(statements.command_name(line), name)


class MatchedTest(unittest.TestCase):
    """What the check (matching.py) lets through: the lines the encoder
    encodes, any name taken for a declared int variable."""

    def test_encodable(self):
        for line in ("sys0=5", "count+=1", "dim=sys0/2", "page 0", "printh 00 ff", "// note",
                     't0.txt="a"', "sys0*=2", "sys0<<=n0.val"):
            with self.subTest(line=line):
                self.assertTrue(encodable(line))
        for line in ("made_up t0,0", 'made_up "a"'):
            with self.subTest(line=line):
                self.assertFalse(encodable(line))

    def test_compound_assignments(self):
        # On numbers, in an event and in program.s, as a for's step, and
        # through the screen's arrays. Not on a txt, which nxwright's build
        # refuses, nor through the arrays on one, nor a txt cut by a negative
        # number, which the Nextion Editor compiles but makes no sense.
        context = line_context(text_probes.text_component(),
                               number_probes.number_component(y=60))
        rules = MATCHED + for_statement.MATCHED
        for line in ("n0.val*=-1", "sys0/=n0.val+1", "b[2].val<<=n0.val", "sys0*=b[2].val",
                     "for(sys0=1;sys0<100;sys0*=2)"):
            with self.subTest(line=line):
                self.assertTrue(any(rule.matches(Need("code", "event", line, context=context))
                                    for rule in rules))
        self.assertTrue(MATCHED[0].matches(Need("code", "program.s", "sys0%=3")))
        # The Nextion Editor compiles these, and nxwright writes them as any
        # assignment.
        for line in ('b[1].txt*="a"', "b[1].txt-=-1"):
            with self.subTest(line=line):
                self.assertTrue(any(rule.matches(Need("code", "event", line, context=context))
                                    for rule in rules))

    def test_the_rule(self):
        rule, = MATCHED
        self.assertTrue(rule.matches(Need("code", "event", "sys0=sys1+1")))
        # The frame's list covers the declarations it reads.
        self.assertFalse(rule.matches(Need("code", "program.s", "int a=1")))
        self.assertFalse(rule.matches(Need("code", "event", "int a=1")))
        self.assertFalse(rule.matches(Need("code", "program.s", "made_up t0,0")))
        # A comment gives no block, whatever it holds.
        for line in ("// e.g. note", '// say "hi"'):
            with self.subTest(line=line):
                self.assertTrue(rule.matches(Need("code", "event", line)))
        # A text's txt set as the probes showed, in an event whose page has
        # the text t0 and the number n0.
        context = line_context(text_probes.text_component(),
                               number_probes.number_component(y=60))
        for value in ("Yo", "", "a" * 20, "a b", "Hi!", "a" * 21):
            with self.subTest(value=value):
                self.assertTrue(rule.matches(Need("code", "event", 't0.txt="%s"' % value,
                                                  context=context)))
        # The escapes the screen reads are kept as written; any other is
        # refused.
        for line in ('t0.txt="a\\"b"', 't0.txt="a\\\\b"', 't0.txt+="\\r"'):
            with self.subTest(line=line):
                self.assertTrue(rule.matches(Need("code", "event", line, context=context)))
        for line in ("t0.val=5", 't0.txt="a\\nb"', 't0.txt="a\\"', 'sys0="a"', "t0.txt=n0.val",
                     't0.txt+="a"+n0.val', "t0.txt-=t0.txt"):
            with self.subTest(line=line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=context)))
        # printh keeps its argument as written, so nothing in it is read as a
        # text, an attribute, or a name, on any series.
        for series in ("T", "K", "F", "P", "E"):
            for line in ("printh 3G", 'printh "a"', "printh n0.val", "printh b[0]"):
                with self.subTest(series=series, line=line):
                    self.assertTrue(rule.matches(Need("code", "event", line, series=series)))
        # Without a page's components, as in program.s, no attribute is known.
        for subject in ("program.s", "event"):
            with self.subTest(subject=subject):
                self.assertFalse(rule.matches(Need("code", subject, 't0.txt="Yo"')))
        self.assertFalse(rule.matches(Need("type", "text")))

    def test_a_command_of_instructions_is_left_to_its_own_rule(self):
        # The encoder encodes it, but only its module's MATCHED says what of
        # it was probed.
        family = types.ModuleType("nxwright.tft.instructions.family")
        family.COMMANDS = {"T": {"randset": Command(0x16, 8)}}
        statements.series_commands.cache_clear()
        self.addCleanup(statements.series_commands.cache_clear)
        rule, = MATCHED
        with mock.patch.object(statements, "_instruction_modules", lambda: [family]):
            self.assertTrue(encodable("randset 0,100"))
            self.assertFalse(rule.matches(Need("code", "event", "randset 0,100")))
            self.assertTrue(rule.matches(Need("code", "event", "page 0")))


class _Renumbered:
    """A type whose entries on P are numbered unlike T's: its a is 19 on
    both, its b 20 on T and 22 on P, and its c 21 on T, with no entry on P.
    Its d has an entry on P that attribute_place refuses, and its e an
    entry code names on P alone, 34 (P_CODE_ENTRIES)."""
    P_ENTRIES = {19: ("a", 56, 1, 0, 0x121), 22: ("b", 57, 1, 0, 0x121),
                 23: ("d", 58, 1, 0, 0x121)}
    P_CODE_ENTRIES = {"e": 34}

    @staticmethod
    def attribute_place(name: str) -> int:
        return {"a": 19, "b": 20, "c": 21, "e": 34}[name]


class CodeEntryTest(unittest.TestCase):
    """The entry code names for an attribute (component_types.code_entry):
    attribute_place's on T and K, and its type's P_ENTRIES' on P and E."""

    @classmethod
    def setUpClass(cls):
        cls.plain, cls.with_an_effect = (
            page(text_probes.text_component(**attributes), series="P").objects[1]
            for attributes in ({}, {"effect": 2}))

    def test_on_t_it_is_attribute_place_s(self):
        self.assertEqual([code_entry(_Renumbered, self.plain, name, "T") for name in "abc"],
                         [19, 20, 21])

    def test_on_p_and_e_it_is_the_p_table_s(self):
        # The b renumbered, the c refused, as its number on T would name
        # another entry there; the d refused, as attribute_place refuses it;
        # and the e from P_CODE_ENTRIES.
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual([code_entry(_Renumbered, self.plain, name, series)
                                  for name in "abe"], [19, 22, 34])
                for name in "cd":
                    with self.assertRaises(KeyError):
                        code_entry(_Renumbered, self.plain, name, series)

    def test_an_effect_moves_them_two_on(self):
        self.assertEqual([code_entry(_Renumbered, self.with_an_effect, name, "P")
                          for name in "abe"], [21, 24, 36])

    def test_no_type_gives_an_entry_both_ways(self):
        # P_CODE_ENTRIES give entries a type's data does not give. One that
        # shared a number with its P_ENTRIES would hide that entry's own
        # name from code_entry.
        import pkgutil
        from nxwright.tft import component_types
        for found in pkgutil.iter_modules(component_types.__path__):
            module = component_types.type_module(found.name)
            code_entries = set(getattr(module, "P_CODE_ENTRIES", {}).values())
            with self.subTest(found.name):
                self.assertFalse(code_entries & set(getattr(module, "P_ENTRIES", {})))

    def test_a_type_that_keeps_t_s_numbers(self):
        # A text's txt is its entry 28 on T and on P.
        from nxwright.tft.component_types import object_module
        text = object_module(self.plain)
        self.assertEqual(code_entry(text, self.plain, "txt", "P"), text.attribute_place("txt"))


if __name__ == "__main__":
    unittest.main()
