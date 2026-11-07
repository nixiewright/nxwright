"""The variable component (tft/component_types/variable.py): its drawing,
memory, and entries, what its list matched, which of its attributes code
may use, the blocks the encoder gives them, and its memory and entries on
P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/variable_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P. What the frame writes across
objects, such as a variable's record, the head of its memory on P, and its
txt there, is left to the frame's tests, and compared until then by the
sample of whole files (tests/tft/test_whole_files.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import variable
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, variable_probes
from tools.tft.probing.statement_probes import touch_release_code
from tools.tft.probing.variable_probes import text_variable_component, variable_component
from nxwright.tft.statements import CodePlace, StatementError, attribute_kind, encode_line
from tests.tft.line_context import line_context
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, page_of, probe_project, project_of


def value(number: int, size: int = 4) -> bytes:
    return number.to_bytes(size, "little", signed=True)


def _probe(name: str):
    return next(probe for probe in variable_probes.PROBES + p_probes.PROBES
                if probe.name == name)


class MemoryTest(unittest.TestCase):
    """A variable's starting memory: its val, 4 bytes, signed, in one of a
    number; 4 zeros, then its txt, in one of a text. It reads no project."""

    def test_its_val(self):
        for val in (0, 123, -5, -2 ** 31, 2 ** 31 - 1):
            of_a_number = page(variable_component(val=val)).objects[1]
            with self.subTest(val=val):
                self.assertEqual(variable.variant(of_a_number).memory(of_a_number, None),
                                 value(val))

    def test_its_txt(self):
        # Its txt, then zeros, to txt_maxl + 1 bytes, the whole rounded up
        # to 4.
        for txt, maxl, memory in (("Hi", 10, bytes(4) + b"Hi" + bytes(10)),
                                  ("", 1, bytes(8)), ("A", 1, bytes(4) + b"A" + bytes(3))):
            of_a_text = page(text_variable_component(txt=txt, txt_maxl=maxl)).objects[1]
            with self.subTest(txt=txt, maxl=maxl):
                self.assertEqual(variable.variant(of_a_text).memory(of_a_text, None), memory)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each variable of each probe that keeps its whole user code, at its
    type's functions, and each probe of code, at the statement encoder,
    against the probe's pieces (tests/tft/t_components.py): two of a number on a
    page; one among a text, a number, and a button; one on a second page,
    numbered on from the first's; and one of a text beside one of a number
    and another of a text. A variable is not drawn: its drawing is a 0 word
    alone. Its entries give its type, ID, vscope, and sta, and where its val
    or its txt lies, each with 0xFFFF in place of its ID and its page's. Its
    probes of code take its val in code and in conditions, its txt in code,
    and a variable in the screen's commands."""

    TYPE = "variable"
    PROBES = variable_probes.PROBES
    COUNT = 7
    CODE_COUNT = 4


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each variable of each of its probes on P that keeps its whole user
    code, at its type's functions on P, and each probe of code, against the
    probe's pieces (tests/tft/p_components.py). Its values follow the 4 bytes of
    its record's head its memory starts with (P_HEAD_SIZE): of a number, its
    sta at 4 and its val at 12; of a text, its sta at 4, its txt_maxl at 6,
    and its txt's place at 8, which its probe's table gives (text_places).
    Every entry's owner is 0xFFFF; its val's entry, its 9th, gives its val's
    place, or its txt's its txt's. One of a text keeps its txt after its
    page's components' memory."""

    TYPE = "variable"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-variable-")]
    COUNT = 7
    CODE_COUNT = 4


class MatchedTest(unittest.TestCase):
    """The needs variable.MATCHED covers (matching.py)."""

    # The other attributes of a variable of a number, and of one of a text.
    OF_A_NUMBER = {"sta": value(0, 1), "txt_maxl": value(10, 2)}
    OF_A_TEXT = {"sta": value(1, 1), "txt_maxl": value(10, 2)}

    def need(self, attribute: str, raw: bytes, context: dict) -> Need:
        return Need("attribute", "variable." + attribute, raw, context=context)

    def test_what_it_covers(self):
        covered = [Need("type", "variable"), Need("attribute", "variable.objname", b"va0"),
                   self.need("val", value(-2 ** 31), self.OF_A_NUMBER),
                   self.need("val", value(2 ** 31 - 1), self.OF_A_NUMBER),
                   self.need("sta", value(0, 1), self.OF_A_NUMBER),
                   self.need("sta", value(1, 1), self.OF_A_TEXT),
                   self.need("txt", b"", self.OF_A_TEXT), self.need("txt", b"Go12", self.OF_A_TEXT),
                   self.need("txt_maxl", value(1, 2), self.OF_A_TEXT),
                   self.need("txt_maxl", value(200, 2), self.OF_A_TEXT),
                   # The attributes the other sta writes, which this one does
                   # not write.
                   self.need("val", value(5), self.OF_A_TEXT),
                   self.need("txt", b"Yo", self.OF_A_NUMBER),
                   # Longer than its txt_maxl of 10, which the Nextion Editor
                   # compiled in a variable of a number.
                   self.need("txt", b"0123456789AB", self.OF_A_NUMBER),
                   self.need("txt_maxl", value(20, 2), self.OF_A_NUMBER)]
        self.assertEqual(unmatched(covered, variable.MATCHED), [])

    def test_a_txt_maxl_its_txt_does_not_fit(self):
        # A txt of 6 characters, as the default "newtxt", and a txt_maxl of 5:
        # the Nextion Editor refuses it.
        need = self.need("txt_maxl", value(5, 2), dict(self.OF_A_TEXT))
        need.context["txt"] = b"newtxt"
        self.assertEqual(unmatched([need], variable.MATCHED), [need])

    def test_what_it_leaves_out(self):
        left = [self.need("sta", value(2, 1), self.OF_A_TEXT)]
        self.assertEqual(unmatched(left, variable.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may use a variable's val, and no other attribute of it. The
    encoder reads the page's components and program.s's variables."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page_of(_probe("variable-one")))

    def test_its_val(self):
        # va0 is page0's first component: its first entry is 33, so its val's
        # is 41.
        self.assertEqual(encode_line("va0.val=5", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x01\x29\x00\x00\x00=5")

    def test_its_txt_is_refused(self):
        with self.assertRaisesRegex(StatementError, "va0's txt is not encoded"):
            encode_line('va0.txt="Yo"', CodePlace(0, "page0", "up"), CompileContext(self.project))

    def test_the_txt_of_a_variable_of_a_text(self):
        project = project_of(page(text_variable_component(), strict=True), strict=True)
        place = CodePlace(0, "page0", "up")
        # Its txt has the entry its val would have: 41 for page0's first component.
        self.assertEqual(encode_line('va0.txt="Yo"', place, CompileContext(project)),
                         b'\x01\x29\x00\x00\x00="Yo"')
        with self.assertRaisesRegex(StatementError, "va0's val is not encoded"):
            encode_line("va0.val=5", place, CompileContext(project))

    def test_the_kind_of_each_attribute_by_its_sta(self):
        # va0 of a number, va1 of a text, on one page.
        context = line_context(variable_component(), text_variable_component("va1"))
        need = Need("code", "event", "sys0=1", context=context)
        for attribute, kind in (("va0.val", "number"), ("va0.txt", None),
                                ("va1.val", None), ("va1.txt", "text")):
            with self.subTest(attribute=attribute):
                self.assertEqual(attribute_kind(need, attribute), kind)

    def test_the_check_lets_its_val_through(self):
        made = page(variable_component(), strict=True, code=touch_release_code(
            ["va0.val=5", "sys0=va0.val", "if(va0.val==1)", "{", "}", "get va0.val"]))
        self.assertEqual(unmatched(project_needs(project_of(made, strict=True, fonts=0)),
                                   matched_rules()), [])

    def test_the_check_takes_every_probe(self):
        # Each probe's page matched the Nextion Editor's, so the check,
        # through the variable's rules and those of the statements and the
        # commands, lets it through.
        for probe in variable_probes.PROBES:
            with self.subTest(probe=probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)),
                                           matched_rules()), [])

    def test_the_check_lists_its_txt(self):
        # nxwright's build refuses a variable of a number's txt in code, so
        # the line is put in after it, as a project file nxwright did not
        # write may hold it.
        from nxwright.project.page_block import Event
        made = page_of(_probe("variable-one"))
        event = next(item for item in made.objects[0].items
                     if isinstance(item, Event) and item.name == "up")
        event.lines = [b'va0.txt="Yo"']
        left = unmatched(project_needs(project_of(made, fonts=0)), matched_rules())
        self.assertEqual([need.value for need in left], ['va0.txt="Yo"'])


if __name__ == "__main__":
    unittest.main()
