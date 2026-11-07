"""A component's attribute reached through the screen's arrays, `b[i].name`,
`p[i].b[j].name`, and `page1.b[i].name` (tft/statements.py's INDIRECT): the blocks the
probes of indirect_probes.py kept once they matched the Nextion Editor's
file, the bytes of each form as the Nextion Editor wrote them, what the
encoder refuses, and what the check covers.

The probes' blocks are compared on each probe's page and program.s made in
memory (tests/tft/unit_inputs.py). One probe is compared whole, as the family's
sample, in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.project.device_settings import TextCodec
from tools.tft.probing import indirect_probes
from nxwright.tft.instructions import for_statement, if_statement
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import MATCHED, StatementError, _block
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project

_VARIABLES = ["sys0", "sys1", "sys2", "a"]
_CODEC = TextCodec("iso-8859-1")


def block(line: str) -> str:
    """Returns the block of `line` in an event, n0.val's entry being 0x65."""
    return _block(line, "T", _VARIABLES, lambda attribute: 0x65, None, None, _CODEC).hex(" ")


class PiecesTest(unittest.TestCase):
    """The blocks the encoder gives each probe's lines, on its page and
    program.s made in memory, in strict Nextion syntax, against the probe's
    pieces: page0's Touch Release event's, or program.s's for a probe that
    keeps those (statement_probes.kept_blocks). Each form in assignments,
    as indexes, across pages, in conditions, in commands, on K in its EEPROM
    commands, as components, and in program.s."""

    PROBES = indirect_probes.PROBES

    def test_each_probe(self):
        self.assertEqual(len(self.PROBES), 10)
        for probe in self.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class EncodingTest(unittest.TestCase):
    """The reference's text, compacted, but for its first index, written as an
    assignment's value, as the Nextion Editor wrote each."""

    def test_its_text(self):
        self.assertEqual(block('b[1].txt="Yo"'), "62 5b 31 5d 2e 74 78 74 3d 22 59 6f 22")
        self.assertEqual(block("b[ 1 ].foo=5"), "62 5b 31 5d 2e 66 6f 6f 3d 35")

    def test_its_first_index_as_a_value(self):
        # sys0's operand, then +1; a long number as 03 and its value; a val.
        self.assertEqual(block('b[sys0+1].txt="a"'),
                         "62 5b 05 00 00 00 00 2b 31 5d 2e 74 78 74 3d 22 61 22")
        self.assertEqual(block("b[1000].val=5"), "62 5b 03 e8 03 00 00 5d 2e 76 61 6c 3d 35")
        self.assertEqual(block("sys0=b[n0.val].val"),
                         "05 00 00 00 00 3d 62 5b 01 65 00 00 00 5d 2e 76 61 6c")

    def test_the_second_index_as_written(self):
        # In p[i].b[j], sys0 becomes its operand, and sys1 stays text.
        self.assertEqual(block('p[sys0].b[ sys1 ].txt="a"'),
                         "70 5b 05 00 00 00 00 5d 2e 62 5b 73 79 73 31 5d 2e 74 78 74 3d 22 61 22")

    def test_what_it_refuses(self):
        # As the Nextion Editor refuses them: an empty index, a text, another
        # reference as an index, and a component alone as a value.
        for line in ('b[].txt="a"', 'b["a"].txt="a"', 'b[b[2].val].txt="a"', "b[1]=5"):
            with self.subTest(line), self.assertRaises(StatementError):
                block(line)


class AnotherPageTest(unittest.TestCase):
    """A component of another page reached through the screen's array by
    that page's name, as `page1.b[1].val`. The Nextion Editor wrote the whole
    reference as its text, compacted, its index included, in an event, a
    macro, and program.s (ResearchNotes/tft/statements.md)."""

    @classmethod
    def setUpClass(cls):
        cls.context = line_context(text_component("t0"), number_component("n0", y=60))

    def need(self, line: str, subject: str = "event") -> Need:
        return Need("code", subject, line, context=self.context if subject == "event" else {},
                    series="T")

    def test_its_text(self):
        # Each index as written, as the Nextion Editor kept it.
        for line in ("page1.b[1].val=5", "page1.b[sys0].val=5", "page1.b[a].val=5",
                     "page1.b[sys0+1].val=5", "page1.b[n0.val].val=5", "page1.b[1000].val=5",
                     'page1.b[2].txt="a"'):
            with self.subTest(line):
                self.assertEqual(block(line), line.encode("ascii").hex(" "))

    def test_its_spaces_dropped(self):
        self.assertEqual(block("page1.b[ 1 ].val=5"), b"page1.b[1].val=5".hex(" "))

    def test_as_a_value(self):
        # After the target's operand: sys0's, or t0.txt's entry.
        self.assertEqual(block("sys0=page1.b[1].val"),
                         "05 00 00 00 00 3d " + b"page1.b[1].val".hex(" "))
        self.assertEqual(block("t0.txt=page1.b[2].txt"),
                         "01 65 00 00 00 3d " + b"page1.b[2].txt".hex(" "))

    def test_what_the_check_covers(self):
        rules = matched_rules()
        lines = {"event": ["page1.b[1].val=5", "sys0=page1.b[sys0].val",
                           "t0.txt=page1.b[2].txt", "page1.b[1].val+=1",
                           "if(page1.b[1].val==1)", "cls page1.b[2].val"],
                 "macro": ["page1.b[1].val=5", "sys0=page1.b[sys0].val", "page1.b[a].val=1"],
                 "program.s": ["page1.b[1].val=5", "sys0=page1.b[sys0].val"]}
        for subject, each in lines.items():
            for line in each:
                with self.subTest(subject=subject, line=line):
                    self.assertEqual(unmatched([self.need(line, subject)], rules), [])

    def test_an_index_s_attributes_are_checked(self):
        # As the indexes of `b[i]` and `p[i].b[j]` are: each attribute an
        # index names must be one encoded as a number.
        rules = matched_rules()
        for line in ("page1.b[t0.txt].val=5", "page1.b[zz.val].val=5"):
            with self.subTest(line):
                need = self.need(line)
                self.assertEqual(unmatched([need], rules), [need])

    def test_the_line_s_own_page_is_left_out(self):
        # nxwright's build refuses it first, so no probe reached the Nextion
        # Editor with it.
        need = self.need('page0.b[1].txt="a"')
        self.assertEqual(unmatched([need], matched_rules()), [need])


class CommandTest(unittest.TestCase):
    """References as commands' operands, and `b[i]` as a command's
    component, as the Nextion Editor wrote them, and what the encoder and
    the check take."""

    _COMPONENTS = ("page0", "t0", "n0", "n1")

    def block(self, line: str, components: tuple = _COMPONENTS, series: str = "T") -> str:
        return _block(line, series, _VARIABLES, lambda attribute: 0x65, components, None,
                      _CODEC).hex(" ")

    def test_as_operands(self):
        self.assertEqual(self.block("cls b[2].val"), "09 06 04 62 5b 32 5d 2e 76 61 6c")
        self.assertEqual(self.block("strlen b[1].txt,b[2].val"),
                         "09 0c 08 62 5b 31 5d 2e 74 78 74 2c 62 5b 32 5d 2e 76 61 6c")

    def test_as_a_component(self):
        # Its index written as a reference's first index.
        self.assertEqual(self.block("vis b[sys0],0"), "09 05 04 62 5b 05 00 00 00 00 5d 2c 30")
        self.assertEqual(self.block("ref b[1]"), "09 03 04 62 5b 31 5d")
        # The Nextion Editor refused a space in it, `p[i].b[j]` there, and
        # `b[i]` in program.s ("Invalid Component ID").
        for line, components in (("vis b[ 1 ],0", self._COMPONENTS),
                                 ("vis p[0].b[1],0", self._COMPONENTS), ("vis b[1],0", ())):
            with self.subTest(line), self.assertRaises(StatementError):
                self.block(line, components)

    def test_as_page_s_value(self):
        # As any value's operand.
        self.assertEqual(self.block("page b[sys0].val+1"),
                         "09 0b 04 62 5b 05 00 00 00 00 5d 2e 76 61 6c 2b 31")
        self.assertEqual(self.block("page p[0].b[2].val", ()),
                         "09 0b 04 70 5b 30 5d 2e 62 5b 32 5d 2e 76 61 6c")

    def test_as_cfgpio_s_component(self):
        # On K, as vis's component, and refused where vis's is.
        self.assertEqual(self.block("cfgpio 2,1,b[sys0]", series="K"),
                         "09 0d 08 32 2c 31 2c 62 5b 05 00 00 00 00 5d")
        for line, components in (("cfgpio 2,1,b[ 1 ]", self._COMPONENTS),
                                 ("cfgpio 2,1,p[0].b[1]", self._COMPONENTS),
                                 ("cfgpio 2,1,b[1]", ())):
            with self.subTest(line), self.assertRaises(StatementError):
                self.block(line, components, "K")

    def test_what_the_check_takes(self):
        context = line_context(text_component("t0"), number_component("n0", y=60))
        rules = matched_rules()

        def need(line: str, subject: str = "event", series: str = "T") -> Need:
            return Need("code", subject, line,
                        context=context if subject == "event" else {}, series=series)
        for line in ("cls b[2].val+1", "prints b[1].txt,0", "pa_q b[1].txt,b[2].val",
                     "vis b[n0.val],1", "click b[1],1", "page 1+b[2].val",
                     "page b[n0.val].val*2", "page b[1].txt"):
            with self.subTest(line):
                self.assertEqual(unmatched([need(line)], rules), [])
        for line in ("cfgpio 2,1,b[n0.val+1]", "cfgpio b[2].val,b[3].val,n0"):
            with self.subTest(line):
                self.assertEqual(unmatched([need(line, series="K")], rules), [])
        for line, series in (("cls p[0].b[2].val", "T"), ("page p[0].b[2].val", "T"),
                             ("cfgpio p[0].b[2].val,1,0", "K")):
            with self.subTest(line):
                self.assertEqual(unmatched([need(line, "program.s", series)], rules), [])
        # A txt where a command takes a number, as in `cls b[1].txt`;
        # `p[i].b[j]` as a component; `b[i]` in program.s, which the Nextion
        # Editor refused as an operand and as a component; and a space in
        # `page`'s reference, which it refused ("Invalid Page ID").
        left = [need("cls b[1].txt"), need("vis p[0].b[1],0"),
                need("vis b[1],0", "program.s"), need("cls b[2].val", "program.s"),
                need("get b[2].val", "program.s"), need("print b[1].txt", "program.s"),
                need("crcputs b[1].txt,0", "program.s"), need("page b[2].val", "program.s"),
                need("cfgpio 2,1,b[1]", "program.s", "K"), need("page b[ 2 ].val")]
        self.assertEqual(unmatched(left, rules), left)


class CoveredTest(unittest.TestCase):
    """What the check covers, in an event beside a text t0 and a number n0,
    and in program.s."""

    @classmethod
    def setUpClass(cls):
        cls.context = line_context(text_component("t0"), number_component("n0", y=60))

    def need(self, line: str, subject: str = "event", series: str = "T") -> Need:
        return Need("code", subject, line, context=self.context if subject == "event" else {},
                    series=series)

    def covered(self, need: Need) -> bool:
        rules = MATCHED + if_statement.MATCHED + for_statement.MATCHED
        return any(rule.covers(need) for rule in rules)

    def test_what_it_covers(self):
        lines = ['b[1].txt="Yo"', 'b[1].txt=t0.txt+n0.val', "b[2].val++", "sys0=b[2].val",
                 'n0.val=b[1].txt', 't0.txt="a"+b[1].txt', "t0.txt-=b[2].val",
                 'p[n0.val].b[n0.val].txt="a"', "if(b[1].txt==1)", "if(n0.val!=p[0].b[2].val)",
                 "for(b[2].val=0;b[2].val<3;b[2].val++)"]
        for line in lines:
            with self.subTest(line):
                self.assertTrue(self.covered(self.need(line)))
        for line in ('p[0].b[1].txt="a"', "sys0=p[0].b[1].val", "if(p[0].b[2].val==1)"):
            with self.subTest(line):
                self.assertTrue(self.covered(self.need(line, "program.s")))
        for series in ("K", "P"):
            with self.subTest(series=series):
                self.assertTrue(self.covered(self.need('b[1].txt="Yo"', series=series)))
                self.assertTrue(self.covered(self.need('p[0].b[1].txt="a"', "program.s",
                                                       series)))

    def test_what_it_leaves_out(self):
        # A text in a number's value, which nxwright's build refuses; a number
        # in a txt's value, which no probe gave beside a txt's texts; a txt as
        # an index; a command; and b[i] in program.s, which the Nextion Editor
        # refuses.
        for line in ("sys0=b[2].val+t0.txt", 't0.txt="a"+b[1].txt+5', "b[t0.txt].val=1",
                     "cov b[2].val,t0.txt,0"):
            with self.subTest(line):
                self.assertFalse(self.covered(self.need(line)))
        for line in ('b[1].txt="a"', "sys0=b[1].val", "if(b[2].val==1)",
                     "for(b[2].val=0;b[2].val<3;b[2].val++)"):
            for series in ("T", "P"):
                with self.subTest(line, series=series):
                    self.assertFalse(self.covered(self.need(line, "program.s", series)))


if __name__ == "__main__":
    unittest.main()
