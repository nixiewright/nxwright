"""The pinyin commands, pa_q and pa_txt (tft/instructions/
pinyin_commands.py): the blocks the probes of pinyin_probes.py kept once
they matched the Nextion Editor's file, each command's bytes on T and K as
the Nextion Editor wrote them, what the encoder refuses, and what the check
covers.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.project.device_settings import TextCodec
from tools.tft.probing import p_probes, pinyin_probes
from nxwright.tft.instructions import pinyin_commands
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import StatementError, _block
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project

# The entries of t0's txt and n0's val beside them, as in the probes.
_ENTRIES = {"t0.txt": 0x3D, "n0.val": 0x65}


def block(line: str, series: str = "T") -> str:
    return _block(line, series, ["sys0", "sys1", "sys2"], _ENTRIES.__getitem__, None, None,
                  TextCodec("iso-8859-1")).hex(" ")


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in pinyin_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-pinyin-")]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class EncodingTest(unittest.TestCase):
    """Each command's number and table, then its operands, as the Nextion
    Editor wrote them: pa_q is 09 0e 04 on T and 09 10 04 on K, and pa_txt
    09 10 08 on T and 09 11 08 on K."""

    def test_on_each_series(self):
        self.assertEqual(block("pa_q t0.txt,n0.val"),
                         "09 0e 04 01 3d 00 00 00 2c 01 65 00 00 00")
        self.assertEqual(block("pa_q t0.txt,n0.val", "K"),
                         "09 10 04 01 3d 00 00 00 2c 01 65 00 00 00")
        self.assertEqual(block("pa_txt t0.txt,t0.txt,n0.val,1"),
                         "09 10 08 01 3d 00 00 00 2c 01 3d 00 00 00 2c 01 65 00 00 00 2c 31")
        self.assertEqual(block("pa_txt t0.txt,t0.txt,n0.val,1", "K"),
                         "09 11 08 01 3d 00 00 00 2c 01 3d 00 00 00 2c 01 65 00 00 00 2c 31")

    def test_its_operands(self):
        # A text, a variable, and a long number, as any line writes them.
        self.assertEqual(block('pa_q "ni",sys0'), "09 0e 04 22 6e 69 22 2c 05 00 00 00 00")
        self.assertEqual(block("pa_txt t0.txt,t0.txt,n0.val,1000"),
                         "09 10 08 01 3d 00 00 00 2c 01 3d 00 00 00 2c 01 65 00 00 00 2c 03 e8 03 "
                         "00 00")

    def test_any_kind_where_one_operand_goes(self):
        # The syllable, and where the count or the characters go: the
        # Nextion Editor compiled a number in each, written as any operand:
        # `pa_q 5,sys0` gave 09 0e 04 35 2c, then sys0's operand.
        self.assertEqual(block("pa_q 5,sys0"), "09 0e 04 35 2c 05 00 00 00 00")

    def test_what_it_refuses(self):
        # An expression where one operand goes, which the Nextion Editor
        # refused ("Invalid Variables"); and a text or a txt where a number
        # goes, which it refused ("Invalid variable operation").
        for line in ("pa_q t0.txt,n0.val+1", "pa_q sys0+1,sys1", 'pa_txt "a",sys0+1,0,1',
                     'pa_txt "a",t0.txt,t0.txt,1', 'pa_txt "a",t0.txt,0,"1"'):
            with self.subTest(line), self.assertRaises(StatementError):
                block(line)


class CoveredTest(unittest.TestCase):
    """What the check covers, beside the text t0 and the number n0."""

    @classmethod
    def setUpClass(cls):
        cls.context = line_context(text_component(), number_component("n0", y=60))

    def covered(self, line: str, subject: str = "event", series: str = "T") -> bool:
        need = Need("code", subject, line, context=self.context if subject == "event" else {},
                    series=series)
        return any(rule.covers(need) for rule in pinyin_commands.MATCHED)

    def test_what_it_covers(self):
        # One operand of any kind where one goes, as the Nextion Editor
        # compiled each of these.
        for line in ("pa_q t0.txt,n0.val", "pa_txt t0.txt,t0.txt,n0.val,1",
                     'pa_txt "mei",t0.txt,0x00,0x06', 'pa_q "a",5', 'pa_q "a",0x05',
                     'pa_q "a",-5', 'pa_q "a",b[1].txt', "pa_q b[1].val,n0.val",
                     'pa_txt "a",b[1].val,0,1', "pa_q n0.val,sys0", "pa_q 5,sys0",
                     'pa_txt "a",n0.val,0,1', 'pa_txt "a",sys0,0,1'):
            with self.subTest(line):
                self.assertTrue(self.covered(line))
        self.assertTrue(self.covered('pa_q "ni",sys0', "program.s"))

    def test_what_it_leaves_out(self):
        # A component the page has not, an expression, and a txt in program.s,
        # which has no page.
        for line in ("pa_q t9.txt,n0.val", "pa_q t0.txt,n0.val+1"):
            with self.subTest(line):
                self.assertFalse(self.covered(line))
        self.assertFalse(self.covered("pa_q t0.txt,sys0", "program.s"))

    def test_on_p(self):
        # P numbers them its own way, as P's probes showed (p_probes.py).
        need = Need("code", "event", "pa_q t0.txt,n0.val", context=self.context, series="P")
        self.assertEqual(unmatched([need], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
