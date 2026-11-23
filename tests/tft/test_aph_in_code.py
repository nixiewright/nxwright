"""A component's aph in code, in the match check and in the statement
encoder (component_types.code_entry).

Code refers to a component's aph by the component's entry 6, on every
series. The Nextion Editor 1.68.2 wrote that entry for code that reads the
aph of each drawn type on T, K, and F, and for code that reads and sets a
hotspot's aph on P and E
(ResearchNotes/tft/attributes-in-code.md). The probes that read and set
every attribute keep the Nextion Editor's blocks for those lines as their
fixtures (tests/tft/test_other_attributes.py).

Each page here has a text t0, a hotspot m0, a timer tm0, and a touch capture
tc0. The page has 33 entries and the text has 41, so the text's first entry
is 33 and the hotspot's is 74. Their aphs are therefore entries 39 and 80,
the 0x27 and 0x50 in _TEXT_APH and _HOTSPOT_APH.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tests.tft.unit_inputs import page, project_of

_SYS0 = "05 00 00 00 00"
_TEXT_APH, _HOTSPOT_APH = "01 27 00 00 00", "01 50 00 00 00"
_PLACE = CodePlace(0, "page0", "up")


class AphInCodeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rules = matched_rules()
        cls.projects = {
            series: project_of(page(
                text_component(), hotspot_component(x=150, y=120), timer_component(),
                touch_capture_component(), series=series, code="on page0.up:\n  sys0=1\n",
                strict=True), series=series, strict=True, fonts=0)
            for series in ("T", "K", "F", "P", "E")}

    def covered(self, line: str, series: str) -> bool:
        context = next(need.context for need in project_needs(self.projects[series])
                       if need.kind == "code" and need.subject == "event")
        need = Need("code", "event", line, context=context, series=series)
        return unmatched([need], self.rules) == []

    def encoded(self, line: str, series: str) -> str:
        return encode_line(line, _PLACE, CompileContext(self.projects[series])).hex(" ")

    def test_a_read_is_entry_6_on_every_series(self):
        for series in self.projects:
            for line, operand in (("sys0=t0.aph", _TEXT_APH), ("sys0=m0.aph", _HOTSPOT_APH)):
                with self.subTest(line, series=series):
                    self.assertTrue(self.covered(line, series))
                    self.assertEqual(self.encoded(line, series), "%s 3d %s" % (_SYS0, operand))

    def test_a_set_is_entry_6_on_p_and_e(self):
        for series in ("P", "E"):
            for line, written in (("m0.aph=50", "%s 3d 35 30" % _HOTSPOT_APH),
                                  ("m0.aph=sys0", "%s 3d %s" % (_HOTSPOT_APH, _SYS0)),
                                  ("t0.aph=sys0", "%s 3d %s" % (_TEXT_APH, _SYS0))):
                with self.subTest(line, series=series):
                    self.assertTrue(self.covered(line, series))
                    self.assertEqual(self.encoded(line, series), written)

    def test_a_set_is_not_covered_on_t_k_and_f(self):
        # Code cannot change an aph on T, K, or F. nxwright's build rejects a
        # line that sets one, and the match check does not cover it.
        for series in ("T", "K", "F"):
            for line in ("m0.aph=50", "t0.aph=sys0"):
                with self.subTest(line, series=series):
                    self.assertFalse(self.covered(line, series))

    def test_a_type_without_an_aph_has_no_entry_of_it(self):
        # A timer and a touch capture have no aph.
        for series in self.projects:
            for line in ("sys0=tm0.aph", "sys0=tc0.aph"):
                with self.subTest(line, series=series):
                    self.assertFalse(self.covered(line, series))
                    with self.assertRaisesRegex(StatementError, "aph is not encoded"):
                        self.encoded(line, series)


if __name__ == "__main__":
    unittest.main()
