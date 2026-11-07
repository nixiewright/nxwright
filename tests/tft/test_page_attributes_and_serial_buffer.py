"""A page's own attributes in its own code, the serial buffer u[], and an int
declared in an event: what the check takes, and where a page's attributes
lie among its entries on each series. The blocks the encoder gives them are
compared with their probes' fixtures in tests/tft/test_attributes_in_code.py
(attribute_probes.py's attributes-of-the-page and attributes-serial-buffer).

Each test gives the function it checks its own input: the T base folder's
page0, with the case's lines, made in memory (unit_inputs.probe_project), or
a page object (unit_inputs.page)."""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing import attribute_probes
from tools.tft.probing.probe_runner import Probe
from nxwright.tft.statements import CodePlace, StatementError, encode_line, page_code_entry
from tests.tft.unit_inputs import page, probe_project


def _project(lines: list):
    """Returns a Project of page0 with `lines` in its Touch Release event."""
    return probe_project(Probe("test", "T", attribute_probes.with_attributes(lines), None, None))


def _page(series: str = "T", **attributes):
    """Returns page0's own object, on `series`, with `attributes` in its own
    table."""
    lines = "".join("%s = %s\n" % (name, value) for name, value in attributes.items())
    return page(series=series, attributes=lines).objects[0]


class SerialBufferIndexTest(unittest.TestCase):
    """u[i]'s index is written as an assignment's value, a text or a sum
    among them; an empty one gives no value to write."""

    def test_an_index_of_any_value(self):
        lines = ['sys0=u["a"]', "sys0=u[sys0+1]", 'u["a"]=5', 'u["a"]++', 'if(u["a"]==1)',
                 "{", "}"]
        self.assertEqual(unmatched(project_needs(_project(lines)), matched_rules()), [])

    def test_an_empty_index(self):
        with self.assertRaisesRegex(StatementError, "no value"):
            encode_line("sys0=u[]", CodePlace(0, "page0", "up"),
                        CompileContext(_project(["sys0=1"])))


class PageEntryTest(unittest.TestCase):
    """A page's own attribute lies at the entry the frame writes it at."""

    def test_on_t(self):
        for name, entry in (("type", 0), ("id", 1), ("vscope", 3), ("x", 9), ("h", 12),
                            ("endy", 14), ("sta", 23), ("bco", 24)):
            with self.subTest(name):
                self.assertEqual(page_code_entry(_page(), name, "T"), entry)

    def test_its_background_by_its_sta(self):
        # A page of a picture has a pic and no bco, and one of a colour the
        # other way round.
        pictured = _page(sta=2)
        self.assertEqual(page_code_entry(pictured, "pic", "T"), 24)
        with self.assertRaises(KeyError):
            page_code_entry(pictured, "bco", "T")

    def test_an_effect_moves_its_sta_and_its_background(self):
        moved = _page(effect=1)
        self.assertEqual(page_code_entry(moved, "x", "T"), 9)
        self.assertEqual(page_code_entry(moved, "sta", "T"), 25)
        self.assertEqual(page_code_entry(moved, "bco", "T"), 26)

    def test_one_the_page_has_no_entry_of(self):
        with self.assertRaises(KeyError):
            page_code_entry(_page(), "txt", "T")

    def test_its_effect_and_swipe_targets_on_t_k_and_f(self):
        # Code names them by the entries P gives them, though the frame
        # writes no entry of them on these series: its effect, first, and
        # time from 15, its swipe targets from 19, and those two on beside an
        # effect, as the Nextion Editor's files showed.
        for series in ("T", "K", "F"):
            for page_object, entries in (
                    (_page(series), {"effect": 15, "up": 19, "down": 20, "left": 21,
                                     "right": 22}),
                    (_page(series, effect=1), {"effect": 15, "first": 16, "time": 17,
                                               "up": 21, "down": 22, "left": 23, "right": 24,
                                               "sta": 25})):
                for name, entry in entries.items():
                    with self.subTest(series, name=name, effect=page_object.attribute("effect")):
                        self.assertEqual(page_code_entry(page_object, name, series), entry)

    def test_its_effect_and_swipe_targets_are_taken(self):
        lines = ["sys0=page0.effect", "sys0=page0.up", "page0.down=2", "page0.left+=1",
                 "sys0=page0.right"]
        self.assertEqual(unmatched(project_needs(_project(lines)), matched_rules()), [])

    def test_an_effect_on_p(self):
        # P writes its first and its time after its effect, and each later entry
        # two on (component_types.with_p_effect).
        moved = _page("P", effect=1)
        for name, entry in (("effect", 15), ("first", 16), ("time", 17), ("up", 21),
                            ("sta", 25), ("bco", 26)):
            with self.subTest(name):
                self.assertEqual(page_code_entry(moved, name, "P"), entry)

    def test_on_p(self):
        # P's page has its own entries of its effect and its swipe targets.
        p_page = _page("P")
        for name, entry in (("x", 9), ("effect", 15), ("up", 19), ("right", 22), ("sta", 23),
                            ("bco", 24)):
            with self.subTest(name):
                self.assertEqual(page_code_entry(p_page, name, "P"), entry)


class IntInAnEventTest(unittest.TestCase):

    def test_refused(self):
        # The Nextion Editor refuses one: "Error:Global variable definitions
        # must precede all code in the program.c". nxwright's build lets it
        # through.
        project = _project(["sys0=1"])
        with self.assertRaisesRegex(StatementError, "must precede all code"):
            encode_line("int i=5", CodePlace(0, "page0", "up"), CompileContext(project))


if __name__ == "__main__":
    unittest.main()
