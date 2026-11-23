"""Tests of a method call as a value, and of a method alone on a line, in
the match check and in the statement encoder (tft/statements.py). For each
line that the Nextion Editor 1.68.2 compiled, the encoder must write the
same bytes, and the match check must cover the line. The match check must
not cover the lines that the Nextion Editor rejected.

Each line was alone in page0's Touch Release event, in a project on the P
base folder. The page also had a text t0, numbers n0 and n1, a timer tm0,
a waveform s0, a file stream fs0, a data record d0, and a file browser fb0
(ResearchNotes/tft/method-calls-in-code.md).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_code, encode_line
from tools.tft.probing.command_operand_probes import COMPONENTS
from tools.tft.probing.data_record_probes import data_record_component
from tools.tft.probing.file_browser_probes import file_browser_component
from tools.tft.probing import p_probes
from tools.tft.probing.file_stream_probes import file_stream_component
from tests.tft.t_components import CodePieces
from tests.tft.unit_inputs import page, project_of

# The operands of the page's objects, as the Nextion Editor numbered their
# entries: sys0, t0's txt, n0's val, and each method.
_SYS0, _TXT, _VAL = "05 00 00 00 00", "01 3d 00 00 00", "01 65 00 00 00"
_OPEN, _READ, _WRITE, _CLOSE, _FIND = ("01 %02x 00 00 00" % entry
                                       for entry in (0xDA, 0xDB, 0xDC, 0xDD, 0xDE))
_INSERT, _DELETE, _UP, _CLEAR = ("01 %02x 01 00 00" % entry for entry in (0x1A, 0x1B, 0x1C, 0x1D))
_BROWSER_UP = "01 5f 01 00 00"
_PATH = "22 73 64 30 2f 61 2e 74 78 74 22"

# Each line the Nextion Editor compiled, and the bytes it wrote.
COMPILED = {
    "sys0=fs0.open(t0.txt)": "%s 3d %s 28 %s 29" % (_SYS0, _OPEN, _TXT),
    'sys0=fs0.open("sd0/a.txt")': "%s 3d %s 28 %s 29" % (_SYS0, _OPEN, _PATH),
    'sys0=fs0.find("sd0/a.txt")': "%s 3d %s 28 %s 29" % (_SYS0, _FIND, _PATH),
    "sys0=fs0.read(t0.txt,0,3)": "%s 3d %s 28 %s 2c 30 2c 33 29" % (_SYS0, _READ, _TXT),
    "sys0=fs0.write(t0.txt,0,3)": "%s 3d %s 28 %s 2c 30 2c 33 29" % (_SYS0, _WRITE, _TXT),
    "sys0=fs0.close()": "%s 3d %s 28 29" % (_SYS0, _CLOSE),
    "sys0=fs0.open(5)": "%s 3d %s 28 35 29" % (_SYS0, _OPEN),
    "n0.val=fs0.open(t0.txt)": "%s 3d %s 28 %s 29" % (_VAL, _OPEN, _TXT),
    "sys0+=fs0.open(t0.txt)": "%s 2b 3d %s 28 %s 29" % (_SYS0, _OPEN, _TXT),
    "sys0=fs0.open(t0.txt)+1": "%s 3d %s 28 %s 29 2b 31" % (_SYS0, _OPEN, _TXT),
    "sys0=1+fs0.close()": "%s 3d 31 2b %s 28 29" % (_SYS0, _CLOSE),
    "sys0=fs0.open(t0.txt)+fs0.find(t0.txt)":
        "%s 3d %s 28 %s 29 2b %s 28 %s 29" % (_SYS0, _OPEN, _TXT, _FIND, _TXT),
    "sys0=page0.fs0.open(t0.txt)": "%s 3d %s 28 %s 29" % (_SYS0, _OPEN, _TXT),
    "sys0=d0.clear()": "%s 3d %s 28 29" % (_SYS0, _CLEAR),
    'sys0=d0.insert("a^b")': "%s 3d %s 28 22 61 5e 62 22 29" % (_SYS0, _INSERT),
    "sys0=d0.delete(0,1)": "%s 3d %s 28 30 2c 31 29" % (_SYS0, _DELETE),
    'sys0=d0.up("a^b",0)': "%s 3d %s 28 22 61 5e 62 22 2c 30 29" % (_SYS0, _UP),
    "sys0=fb0.up()": "%s 3d %s 28 29" % (_SYS0, _BROWSER_UP),
    # A method alone on its line is its operand alone.
    "fs0.close": _CLOSE, "fs0.open": _OPEN, "fs0.read": _READ, "fs0.write": _WRITE,
    "fs0.find": _FIND, "page0.fs0.close": _CLOSE, "d0.clear": _CLEAR, "d0.insert": _INSERT,
    "d0.up": _UP, "fb0.up": _BROWSER_UP,
}
# The lines the Nextion Editor rejected: a call of a name that is not a
# method, a call with the wrong number of arguments, a call whose result is
# put in a text, an attribute alone that is not a method, and a call among
# another call's arguments.
REJECTED = ["sys0=n0.val()", "sys0=n0.val(5)", "sys0=n0.val(1)+1", "sys0=fs0.val(5)",
           "sys0=page0.up()", "sys0=fs0.close(1)", "sys0=fs0.open()", "sys0=fs0.read(5)",
           "sys0=d0.clear(1)", "sys0=fb0.up(1)", "t0.txt=fs0.open(t0.txt)",
           "t0.txt+=fs0.open(t0.txt)", "n0.val", "t0.txt", "fs0.val", "page0.up",
           "fs0.open(fs0.find(t0.txt))", "cls n0.val()", "cls fs0.close(1)", "n0.val(5)"]
# The lines the Nextion Editor rejected on T, K, and F, which have no type
# with a method.
REJECTED_WITHOUT_METHODS = ["sys0=n0.val()", "sys0=n0.val(5)", "sys0=n0.val(1)+1",
                           "sys0=page0.up()", "n0.val", "page0.up"]


def _project(series: str, *components: str):
    """Returns a Project of facts on `series`. Its page0 has the components
    that the lines of this module use, then `components`."""
    return project_of(page(*COMPONENTS, *components, series=series,
                           code="on page0.up:\n  sys0=1\n", strict=True),
                      series=series, strict=True, fonts=0)


def _context(project) -> dict:
    """Returns the context of a line in page0's Touch Release event."""
    return next(need.context for need in project_needs(project)
                if need.kind == "code" and need.subject == "event")


class PiecesTest(CodePieces, unittest.TestCase):
    """Compares the statement encoder's blocks with the blocks the Nextion
    Editor wrote, for four probes on P. Three are the probes of calls as
    values and of methods alone on a line: the file stream's, the data
    record's, and the file browser's. The fourth is the probe of a file
    stream's calls in a for's start. Each probe's page is made in memory,
    and the Nextion Editor's blocks are the ones the probe keeps."""

    PROBES = [probe for probe in p_probes.PROBES
              if probe.name.endswith(("-calls-as-values", "-calls-in-a-for-s-start"))]
    CODE_COUNT = 4


class PageOnPTestCase(unittest.TestCase):
    """The base of the tests on P. Its page has the components that this
    module's docstring lists. `covered` returns whether the match check
    covers a line of code in the page's Touch Release event."""

    @classmethod
    def setUpClass(cls):
        cls.project = _project("P", file_stream_component(),
                                data_record_component("d0", x=300, y=10, w=200, h=120),
                                file_browser_component("fb0", x=300, y=150, w=200, h=120))
        cls.context, cls.rules = _context(cls.project), matched_rules()

    def covered(self, line: str, series: str) -> bool:
        need = Need("code", "event", line, context=self.context, series=series)
        return unmatched([need], self.rules) == []


class OnPTest(PageOnPTestCase):

    def test_what_the_nextion_editor_compiled(self):
        place = CodePlace(0, "page0", "up")
        for line, written in COMPILED.items():
            for series in ("P", "E"):
                with self.subTest(line, series=series):
                    self.assertTrue(self.covered(line, series))
            with self.subTest(line):
                self.assertEqual(
                    encode_line(line, place, CompileContext(self.project)).hex(" "), written)

    def test_what_the_nextion_editor_rejected(self):
        for line in REJECTED:
            for series in ("P", "E"):
                with self.subTest(line, series=series):
                    self.assertFalse(self.covered(line, series))

    def test_the_encoder_rejects_an_attribute_alone_that_is_no_method(self):
        place = CodePlace(0, "page0", "up")
        for line in ("n0.val", "t0.txt", "fs0.val", "page0.up", "page0.n0.val"):
            with self.subTest(line):
                with self.assertRaisesRegex(StatementError,
                                            "is not a method, so it cannot be alone on a line"):
                    encode_line(line, place, CompileContext(self.project))


class InAForTest(PageOnPTestCase):
    """A call in a for's start. The Nextion Editor wrote the start only up
    to the first call's parentheses: `sys0=fs0.close` for `sys0=fs0.close()`,
    and `sys0=fs0.open` for `sys0=fs0.open(t0.txt)+1`. Each for was
    `for(<start>;sys0<1;sys0++)`, with `sys1=1` as its body. The for whose
    start sets `n0.val` had `n0.val` in its condition and its step."""

    # Each start, and the bytes that the Nextion Editor wrote for it.
    STARTS = {
        "sys0=fs0.close()": "%s 3d %s" % (_SYS0, _CLOSE),
        "sys0=fs0.open(t0.txt)": "%s 3d %s" % (_SYS0, _OPEN),
        'sys0=fs0.open("sd0/a.txt")': "%s 3d %s" % (_SYS0, _OPEN),
        "sys0=fs0.read(t0.txt,0,3)+1": "%s 3d %s" % (_SYS0, _READ),
        "sys0=fs0.open(t0.txt)+1": "%s 3d %s" % (_SYS0, _OPEN),
        "sys0=fs0.open(t0.txt)+fs0.find(t0.txt)": "%s 3d %s" % (_SYS0, _OPEN),
        "sys0=fs0.close()+fs0.open(t0.txt)": "%s 3d %s" % (_SYS0, _CLOSE),
        "sys0=1+fs0.close()": "%s 3d 31 2b %s" % (_SYS0, _CLOSE),
        "sys0=1+fs0.close()+2": "%s 3d 31 2b %s" % (_SYS0, _CLOSE),
        "sys0+=fs0.close()": "%s 2b 3d %s" % (_SYS0, _CLOSE),
        "sys0=page0.fs0.close()": "%s 3d %s" % (_SYS0, _CLOSE),
        "sys0=d0.clear()": "%s 3d %s" % (_SYS0, _CLEAR),
        "sys0=d0.delete(0,1)": "%s 3d %s" % (_SYS0, _DELETE),
        "sys0=fb0.up()": "%s 3d %s" % (_SYS0, _BROWSER_UP),
        # A method written without its parentheses.
        "sys0=fs0.close": "%s 3d %s" % (_SYS0, _CLOSE),
    }
    # The blocks after the start's: the condition, the body, the step, and
    # the jump back to the condition.
    REST = ["09 00 04 %s 2c 31 2c 32 2c 03 21 00 00 00" % _SYS0, "05 04 00 00 00 3d 31",
            "%s 2b 2b" % _SYS0, "54 20 03 c9 ff ff ff"]

    def test_the_start_is_written_up_to_its_first_call_s_parentheses(self):
        place = CodePlace(0, "page0", "up")
        for start, written in self.STARTS.items():
            head = "for(%s;sys0<1;sys0++)" % start
            for series in ("P", "E"):
                with self.subTest(head, series=series):
                    self.assertTrue(self.covered(head, series))
            with self.subTest(head):
                blocks = encode_code([head, "{", "sys1=1", "}"], place,
                                     CompileContext(self.project))
                self.assertEqual([block.hex(" ") for block in blocks], [written, *self.REST])

    def test_a_start_that_puts_its_call_in_a_number_s_val(self):
        blocks = encode_code(["for(n0.val=fs0.close();n0.val<1;n0.val++)", "{", "sys1=1", "}"],
                             CodePlace(0, "page0", "up"), CompileContext(self.project))
        self.assertEqual(blocks[0].hex(" "), "%s 3d %s" % (_VAL, _CLOSE))

    def test_what_the_rule_does_not_cover(self):
        # Each of these keeps the rule from covering a for:
        # - a call in the step. The Nextion Editor rejected it ("Invalid
        #   Variables").
        # - a start with a call that the Nextion Editor rejects when the call
        #   is on a line of its own, such as `sys0=fs0.close(1)`. nxwright's
        #   build rejects that call in a for too.
        # - a step that the rule does not cover, such as `cls RED`, after a
        #   start with a call.
        for head in ("for(sys0=0;sys0<1;sys0+=fs0.close())",
                     "for(sys0=fs0.close(1);sys0<1;sys0++)", "for(sys0=n0.val();sys0<1;sys0++)",
                     "for(t0.txt=fs0.open(t0.txt);sys0<1;sys0++)",
                     "for(sys0=fs0.open(fs0.find(t0.txt));sys0<1;sys0++)",
                     "for(sys0=fs0.close();sys0<1;cls RED)",
                     "for(sys0=fs0.close();sys0<1;sys0=t0.txt)"):
            for series in ("P", "E"):
                with self.subTest(head, series=series):
                    self.assertFalse(self.covered(head, series))


class WithoutMethodsTest(unittest.TestCase):

    def test_what_the_nextion_editor_rejected(self):
        rules = matched_rules()
        for series in ("T", "K", "F"):
            context = _context(_project(series))
            for line in REJECTED_WITHOUT_METHODS:
                with self.subTest(line, series=series):
                    need = Need("code", "event", line, context=context, series=series)
                    self.assertEqual(unmatched([need], rules), [need])


if __name__ == "__main__":
    unittest.main()
