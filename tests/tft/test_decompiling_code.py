"""Decoding a run of code's blocks back into lines (tft/decompiling/code.py):
statements and commands.

Each probe that keeps the blocks of page0's Touch Release event, or of
program.s's lines, is a test: its piece is decoded into lines, and the
encoder (statements.encode_code) gives the same blocks from those lines, in
a Project of the probe's facts (tests/tft/unit_inputs.py). The decoded file
the decoder reads is made from the same facts, as small as the decoder
needs (unit_inputs.decoded_file_of).

The forms the decoder chooses where several give the same bytes are
checked on single blocks.
"""
from dataclasses import replace
import importlib
import pkgutil
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft import probing
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.code import decoded_lines
from nxwright.tft.decompiling.decoded_file import (CodeRun, DecodedFile, DecodedPage, IntVariable,
                                            Macro, Name)
from nxwright.tft.label_numbers import resolved
from tools.tft.probing import other_page_probes, statement_probes
from nxwright.tft.statements import CodePlace, encode_code
from nxwright.tft.tft_file import split_blocks
from tests.tft.unit_inputs import decoded_file_of, decoded_object_named, piece, probe_project

# The pieces of code a probe keeps: page0's Touch Release event's blocks, and
# program.s's (tools/tft/probing/statement_probes.py).
_EVENT, _PROGRAM = "event", "program-s"
_EVENT_PLACE = CodePlace(0, "page0", "up")


def _probes() -> list:
    """Returns every probe of the T, K, F, and P series that keeps, as its
    fixture, the encoder's blocks of page0's Touch Release event or of
    program.s's lines (statement_probes.kept_blocks), with the name of that
    piece."""
    found = []
    for module_info in pkgutil.iter_modules(probing.__path__):
        module = importlib.import_module("tools.tft.probing." + module_info.name)
        for probe in getattr(module, "PROBES", []):
            kept = probe.kept or probe.ours
            if (probe.fixtures and probe.base in ("T", "K", "F", "P")
                    and kept in (statement_probes.ours_in_event, statement_probes.ours_in_program)):
                found.append((probe, _PROGRAM if kept is statement_probes.ours_in_program
                              else _EVENT))
    return found


class ProbesTest(unittest.TestCase):
    """Every probe that keeps a run of code, decoded and encoded again."""

    def test_each_probe_s_blocks_come_back(self):
        checked = 0
        for probe, name in _probes():
            blocks = split_blocks(piece(probe, name))
            with self.subTest(probe=probe.name, piece=name):
                project = probe_project(probe)
                decoded, attribute_of_entry = decoded_file_of(project)
                page_id, place = (0, _EVENT_PLACE) if name == _EVENT else (None, CodePlace())
                lines = decoded_lines(CodeRun(0, blocks), page_id, decoded, attribute_of_entry)
                self.assertEqual(encode_code(lines, place, CompileContext(project)), blocks)
                checked += 1
        # The 191 runs of T, K, and F, 64 of them with control statements,
        # and the 53 of P. P writes code as T does. Only its numbers for
        # commands, system variables, and colours differ.
        self.assertEqual(checked, 244)


class FormsTest(unittest.TestCase):
    """The forms the decoder writes, on single blocks of a page of a text t0
    and of a page page1 with a text t1, and the int variables sys0 to sys2."""

    def setUp(self):
        pages = [DecodedPage(page_id, [decoded_object_named(page), decoded_object_named(text, 1)],
                             0, b"", CodeRun(0, []))
                 for page_id, (page, text) in enumerate((("page0", "t0"), ("page1", "t1")))]
        ints = [IntVariable(Name(name, 0, True), 0) for name in ("sys0", "sys1", "sys2")]
        self.decoded = DecodedFile("T", "", 0, "iso-8859-1", ints, b"", CodeRun(0, []), [],
                                   pages)
        # Entry 7 is t0's txt, and entry 40 t1's.
        self.entries = {7: (0, 1, "txt"), 40: (1, 1, "txt")}

    def attribute_of_entry(self, decoded_file: DecodedFile, number: int) -> tuple:
        page_id, object_id, attribute = self.entries[number]
        page = decoded_file.pages[page_id]
        return page, page.objects[object_id], attribute

    def lines(self, *blocks, page_id=0, encoding=None) -> list:
        if encoding:
            self.decoded.encoding = encoding
        return decoded_lines(CodeRun(0, list(blocks)), page_id, self.decoded,
                             self.attribute_of_entry)

    def test_a_long_number_in_decimal(self):
        # 03, then 4 bytes: 1000 as it is, and a shorter value, which came
        # from a hexadecimal or from zeros before it, with zeros up to 4.
        self.assertEqual(self.lines(b"\x05\x00\x00\x00\x00=\x03\xe8\x03\x00\x00",
                                    b"\x05\x00\x00\x00\x00=\x03\x12\x00\x00\x00",
                                    b"\x05\x00\x00\x00\x00=\x03\xfb\xff\xff\xff",
                                    b"\x05\x00\x00\x00\x00=\x03\x00\x00\x00\x80"),
                         ["sys0=1000", "sys0=0018", "sys0=-005", "sys0=-2147483648"])

    def test_variables_and_colours(self):
        self.assertEqual(self.lines(b"\x05\x08\x00\x00\x00=\x04\x04\x0e\x00\x00+\x04\x04\x01"
                                    b"\x00\x00"),
                         ["sys2=baud+RED"])

    def test_attributes_of_its_page_and_another(self):
        self.assertEqual(self.lines(b'\x01\x07\x00\x00\x00="a"', b'\x01\x28\x00\x00\x00="b"'),
                         ['t0.txt="a"', 'page1.t1.txt="b"'])
        # program.s has no page, so each is named after its page.
        self.assertEqual(self.lines(b'\x01\x07\x00\x00\x00="a"', page_id=None),
                         ['page0.t0.txt="a"'])

    def test_texts_in_the_project_s_encoding(self):
        # Escapes are kept, and so is a byte of a character of two bytes that
        # is a backslash's: 表 in shift-jis is 95 5c.
        self.assertEqual(self.lines(b'\x01\x07\x00\x00\x00="a\\"b\\\\"'),
                         [r't0.txt="a\"b\\"'])
        self.assertEqual(self.lines(b'\x01\x07\x00\x00\x00="\x95\x5c"', encoding="shift-jis"),
                         ['t0.txt="表"'])

    def test_a_return(self):
        # A return is a 0 word, an empty block, inside its run.
        self.assertEqual(self.lines(b"\x09\x21\x08", b"", b"\x09\x21\x08"),
                         ["doevents", "return", "doevents"])

    def test_commands(self):
        self.assertEqual(self.lines(b"\x09\x21\x08", b"\x09\x05\x04t0,0", b"\x09\x0b\x08"
                                    b"0d 0a", b"\x09\x0b\x04page1"),
                         ["doevents", "vis t0,0", "printh 0d 0a", "page page1"])


class ControlFormsTest(unittest.TestCase):
    """The control statements, labels, gotos, and calls, as the decoder
    writes them: each run is encoded by the compile, in program.s of a
    probe's project of facts, its labels numbered from 5, its gotos and
    calls given their places (label_numbers.resolved), and decoded."""

    def setUp(self):
        probe = next(probe for probe in statement_probes.PROBES
                     if probe.name == "statements-numbers")
        self.project = probe_project(probe)
        decoded, self.attribute_of_entry = decoded_file_of(self.project)
        # The macro m0, whose run starts at 0x80.
        self.decoded = replace(decoded, macros=[Macro(Name("m0", 0, True), 4,
                                                      CodeRun(0x80, []))])

    def decoded_again(self, lines: list) -> list:
        blocks = resolved(encode_code(lines, CodePlace(), CompileContext(self.project)), 5, 0x200,
                          {"m0": 0x80})
        return decoded_lines(CodeRun(0x200, blocks), None, self.decoded,
                             self.attribute_of_entry)

    def assert_written_as(self, lines: list, written: list):
        self.assertEqual(self.decoded_again(lines), written)

    def test_an_if_with_its_branches(self):
        lines = ["if(sys0==1)", "{", "  sys1=1", "}else if(sys0>2&&sys1<=3)", "{", "  sys1=2",
                 "}else", "{", "  sys1=3", "}"]
        self.assert_written_as(lines, lines)

    def test_a_while_and_an_or(self):
        lines = ["while(sys0<3||sys1!=0)", "{", "  sys0+=1", "  if(sys1==5)", "  {",
                 "    sys1=0", "  }", "}"]
        self.assert_written_as(lines, lines)

    def test_forms_that_give_the_same_blocks(self):
        # A for is its start, then a while whose body ends with its step.
        self.assert_written_as(["for(sys0=0;sys0<3;sys0++)", "{", "  sys1+=1", "}"],
                               ["sys0=0", "while(sys0<3)", "{", "  sys1+=1", "  sys0++", "}"])
        # An if that is a body's whole is joined to the if around it.
        self.assert_written_as(["if(sys0==1)", "{", "  if(sys1==2)", "  {", "    sys2=1", "  }",
                                "}"],
                               ["if(sys0==1&&sys1==2)", "{", "  sys2=1", "}"])
        # An else that holds one if alone is an else if.
        self.assert_written_as(["if(sys0==1)", "{", "  sys2=1", "}else", "{", "  if(sys1==2)",
                                "  {", "    sys2=2", "  }", "}"],
                               ["if(sys0==1)", "{", "  sys2=1", "}else if(sys1==2)", "{",
                                "  sys2=2", "}"])

    def test_labels_gotos_and_calls(self):
        lines = ["label5:", "sys0+=1", "if(sys0<3)", "{", "  goto label5", "}", "call m0"]
        self.assert_written_as(lines, lines)

    def test_a_comparison_that_starts_no_statement(self):
        # The command i writes a comparison's block, which jumps nowhere a
        # statement ends.
        self.assert_written_as(["i sys0,1,1,100000"], ["i sys0,1,1,100000"])


class PageAttributeTest(unittest.TestCase):
    """A page's own attribute, which code names by the page itself, as
    `page1.bco`, comes back as the encoder takes it: from another page or
    from program.s after its page's name too, as `page1.page1.bco`, since
    the encoder would look for an object page1 on the line's own page."""

    def test_named_from_each_place(self):
        probe = next(probe for probe in other_page_probes.PROBES if probe.fixtures)
        project = probe_project(probe)
        decoded, attribute_of_entry = decoded_file_of(project)
        for place, page_id, written in ((CodePlace(), None, "sys0=page1.page1.bco"),
                                        (CodePlace(0, "page0", "up"), 0, "sys0=page1.page1.bco"),
                                        (CodePlace(1, "page1", "up"), 1, "sys0=page1.bco")):
            with self.subTest(place=place):
                blocks = encode_code([written], place, CompileContext(project))
                self.assertEqual(decoded_lines(CodeRun(0, blocks), page_id, decoded,
                                               attribute_of_entry), [written])


class RefusedTest(unittest.TestCase):
    """What the decoder cannot read raises DecodeError, with where it lies."""

    def setUp(self):
        self.decoded = DecodedFile("T", "", 0, "iso-8859-1", [], b"", CodeRun(0, []), [], [])

    def refused(self, block: bytes) -> DecodeError:
        with self.assertRaises(DecodeError) as raised:
            decoded_lines(CodeRun(0x40, [block]), 0, self.decoded, lambda *_: None)
        self.assertEqual(raised.exception.place, 0x40)
        return raised.exception

    def test_what_it_cannot_read(self):
        for block in (b"\x09\x7f\x04", b"\x05\x00\x00\x00\x00=1", b"\x04\x04\xff\x00\x00=1",
                      b'\x05\x00\x00\x00\x00="a', b"\x05\x00\x00\x00\x00=\x02"):
            with self.subTest(block=block):
                self.refused(block)

    def test_jumps_out_of_place(self):
        # A jump block outside a statement, a goto to no label of its run,
        # and a call of no macro.
        for block, words in ((b"T \x03\x10\x00\x00\x00", "outside a control statement"),
                             (b"G \x03\x00\x01\x00\x00", "no label"),
                             (b"J \x03\x00\x01\x00\x00", "no macro")):
            with self.subTest(block=block):
                self.assertIn(words, str(self.refused(block)))


if __name__ == "__main__":
    unittest.main()
