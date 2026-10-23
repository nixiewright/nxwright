"""Tests of a page's memory as the Editor's compile counts it
(nxwright/project/page_memory.py), on a table holding what the compile
showed on a basic NX4832T035."""
from dataclasses import replace
import unittest

from nxwright import NxwrightError
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_block import Attribute, PageBlock, PageObject
from nxwright.project.memory_table import Part, memory_table, read_memory_table
from nxwright.project.page_memory import (Unmeasured, global_memory, measure_page, page_memory,
                                          project_memory)
from nxwright.project.screen_models import MODELS, model_named
from nxwright.project.component_defaults import nxwright_defaults

TABLE = """
editor = "3.1.73"

[memory]
NX4832T035 = 3584

[series.T]
page = 16
objects = {bytes = 1, round = 4}
global = 4
int = 4
global_component = 4
refused = ["switch"]
refused_values = {gauge = {sta = [3]}}

[series.T.types]
text = {cost = 8, parts = [{attribute = "txt_maxl", bytes = 1, add = 2, round = 4}], unmeasured = {key = 255}}
hotspot = {cost = 0}
waveform = {cost = 36, parts = [{attribute = "ch", bytes = 16}, {attribute = "w", bytes = 13, units = 10, round = 4, times = "ch"}]}
data-record = {cost = 4, reserve = 10000, reserve_parts = [{attribute = "molloc", bytes = 1}]}
qr-code = {cost = 16, parts = [{attribute = "txt_maxl", bytes = 1, add = 1, round = 4}], temporary = {attribute = "txt_maxl", steps = [[0, 0], [12, 586], [32, 851], [192, 3382]]}}
checkbox = {cost = 20, temporary = {attribute = "", steps = []}}
"""


def component(kind: str, name: str, **values) -> PageObject:
    attributes = [Attribute("type", TYPES_BY_NAME[kind].to_bytes(1, "little")),
                  Attribute("objname", name.encode("latin-1"))]
    attributes += [Attribute(attribute, value.to_bytes(4, "little"))
                   for attribute, value in values.items()]
    return PageObject(attributes)


def page(*components, name: str = "page0") -> PageBlock:
    return PageBlock(name, 0, b"", b"", [component("page", name)] + list(components))


class PageMemoryTest(unittest.TestCase):

    def setUp(self):
        self.costs = read_memory_table(TABLE, "test").series["T"]

    def own(self, *components) -> int:
        return page_memory(self.costs, page(*components)).own

    def test_an_empty_page(self):
        self.assertEqual(self.own(), 20)

    def test_the_overflow_seen(self):
        # Four texts of txt_maxl 1000: "Memory overflow:16+4072=4088" of 3584.
        texts = [component("text", "t%d" % n, vscope=0, txt_maxl=1000, key=255)
                 for n in range(4)]
        self.assertEqual(self.own(*texts), 4072)

    def test_a_byte_for_each_object_rounded(self):
        for count, own in [(1, 20), (3, 20), (4, 24), (7, 24), (8, 28)]:
            with self.subTest(count=count):
                self.assertEqual(self.own(*[component("hotspot", "m%d" % n)
                                            for n in range(count)]), own)

    def test_channels_multiply_the_width(self):
        self.assertEqual(self.own(component("waveform", "s0", w=100, ch=3)), 20 + 480)

    def test_a_global_component(self):
        memory = page_memory(self.costs, page(component("text", "t0", vscope=1, txt_maxl=10)))
        self.assertEqual((memory.own, memory.global_part), (20 + 4, 16))

    def test_global_memory(self):
        pages = [page(component("text", "t0", vscope=1, txt_maxl=10)),
                 page(component("data-record", "data0", vscope=0, molloc=500))]
        self.assertEqual(global_memory(self.costs, pages, 3), 4 + 12 + 16 + 10500)

    def test_a_temporary_need_by_its_steps(self):
        need = lambda *components: page_memory(self.costs, page(*components)).temporary
        self.assertEqual(need(component("qr-code", "q0", txt_maxl=0)), 0)
        self.assertEqual(need(component("qr-code", "q0", txt_maxl=12)), 586)
        self.assertEqual(need(component("qr-code", "q0", txt_maxl=13)), 851)
        # Two need the larger of theirs, unless the table says they add up.
        self.assertEqual(need(component("qr-code", "q0", txt_maxl=12),
                              component("qr-code", "q1", txt_maxl=30)), 851)
        self.assertEqual(need(component("hotspot", "m0")), 0)
        with self.assertRaisesRegex(Unmeasured, "page0.q0: the temporary memory needed at a "
                                    "txt_maxl of 193 was not measured"):
            need(component("qr-code", "q0", txt_maxl=193))
        # A need with no steps is one the probe found but could not measure.
        with self.assertRaisesRegex(Unmeasured, "page0.c0: the temporary memory a checkbox "
                                    "needs was not measured"):
            need(component("checkbox", "c0"))

    def test_what_was_not_measured(self):
        with self.assertRaisesRegex(Unmeasured, "page0.sw0: the memory of a switch was not "
                                    "measured"):
            self.own(component("switch", "sw0"))
        with self.assertRaisesRegex(Unmeasured, "page0.t0: the memory of a text whose key is "
                                    "not 255 was not measured"):
            self.own(component("text", "t0", txt_maxl=10, key=3))


def built(kind: str, name: str, **values) -> PageObject:
    """A component as the build makes it: every attribute of its type's
    defaults, then `values`, numbers or texts."""
    number = TYPES_BY_NAME[kind]
    attributes = [Attribute("type", number.to_bytes(1, "little")),
                  Attribute("objname", name.encode("latin-1"))]
    for attribute, value in nxwright_defaults()[number].attributes:
        if attribute in values:
            given = values[attribute]
            value = given.encode("latin-1") if isinstance(given, str) else \
                given.to_bytes(len(value), "little")
        attributes.append(Attribute(attribute, value))
    return PageObject(attributes)


class ShippedTableTest(unittest.TestCase):
    """The table nxwright ships holds what the Editor 3.1.73's compile
    showed."""

    def own(self, series: str, *components) -> int:
        return page_memory(memory_table().series[series], page(*components)).own

    def test_every_series_and_model(self):
        table = memory_table()
        self.assertEqual(set(table.series), {"T", "K", "P", "E", "F"})
        self.assertEqual(set(table.memory), {model.name for model in MODELS})
        for letter, costs in table.series.items():
            with self.subTest(series=letter):
                self.assertIn("text", costs.types)
                self.assertGreater(costs.page, 0)
                self.assertGreater(costs.global_memory, 0)

    def test_the_screens_memory(self):
        self.assertEqual(memory_table().memory["NX8048P050"], 524288)
        self.assertEqual(memory_table().memory["NX4832T035"], 3584)

    def test_an_empty_page(self):
        self.assertEqual(self.own("P"), 76)
        self.assertEqual(self.own("T"), 20)

    def test_a_text(self):
        self.assertEqual(self.own("P", built("text", "t0")), 76 + 100)
        self.assertEqual(self.own("T", built("text", "t0", txt_maxl=1000)), 20 + 1012)

    def test_the_overflow_seen(self):
        texts = [built("text", "t%d" % n, txt_maxl=1000) for n in range(4)]
        self.assertEqual(self.own("T", *texts), 4072)

    def test_a_global_text(self):
        memory = page_memory(memory_table().series["P"], page(built("text", "t0", vscope=1)))
        self.assertEqual((memory.own, memory.global_part), (76 + 4, 96))

    def test_the_page_part_for_each_object(self):
        self.assertEqual(self.own("T", *[built("hotspot", "m%d" % n) for n in range(4)]), 24)

    def test_a_waveform(self):
        self.assertEqual(self.own("T", built("waveform", "s0", w=100, ch=3)), 20 + 480)

    def test_a_qr_codes_temporary_need(self):
        def need(series: str, txt_maxl: int) -> int:
            return page_memory(memory_table().series[series], page(
                built("qr-code", "q0", txt="", txt_maxl=txt_maxl))).temporary
        self.assertEqual([need("T", value) for value in (0, 17, 18, 192)], [0, 586, 851, 3382])
        self.assertEqual(need("P", 192), 0)

    def test_a_sliding_texts_lines(self):
        # As the Editor's compile counted a sliding text of local scope alone
        # on its page:
        # the room for its lines is its path_m, or its txt_maxl while path_m
        # is 0.
        for series in ("P", "E"):
            for values, own in (({}, 716), ({"path_m": 1}, 460), ({"path_m": 4}, 464),
                                ({"path_m": 200}, 660), ({"txt_maxl": 356}, 916),
                                ({"txt_maxl": 356, "path_m": 100}, 660),
                                ({"txt_maxl": 456}, 1116)):
                with self.subTest(series=series, values=values):
                    self.assertEqual(self.own(series, built("sliding-text", "st0", vscope=0,
                                                            **values)), own)
            # Its global scope and keyboard measured too: only its path, whose
            # use is not known, stays unmeasured.
            self.assertEqual(memory_table().series[series].types["sliding-text"].unmeasured,
                             {"path": ""})


class ProjectMemoryTest(unittest.TestCase):
    """A project's memory over its pages, as the Editor's compile counts it,
    on the table nxwright ships."""

    BASIC = model_named("NX4832T035")

    def memory(self, model, *pages, ints: int = 3):
        """The memory of a project of `pages`, each a list of components,
        named p0, p1, and so on."""
        return project_memory(model, {"p%d" % number: measure_page(model, page(
            *components, name="p%d" % number)) for number, components in enumerate(pages)},
                              ints)

    def test_within_the_screens_memory(self):
        memory = self.memory(self.BASIC, [built("text", "t0")], [])
        self.assertEqual((memory.model, memory.memory, memory.global_memory, memory.totals,
                          memory.refusals, memory.unmeasured),
                         ("NX4832T035", 3584, 16, {"p0": 16 + 40, "p1": 16 + 20}, (), None))

    def test_the_overflow_seen(self):
        # Four texts of txt_maxl 1,000: "Memory overflow:16+4072=4088".
        texts = [built("text", "t%d" % n, txt_maxl=1000) for n in range(4)]
        memory = self.memory(self.BASIC, [], texts, texts)
        self.assertEqual(memory.refusals, tuple(
            (name, "its memory, 16 + 4072 = 4088 bytes, passes the NX4832T035's 3584, and the "
                   "Nextion Editor's compile refuses it (\"Memory overflow\")")
            for name in ("p1", "p2")))

    def test_ints_and_global_components_count_in_every_page(self):
        memory = self.memory(model_named("NX8048P050"), [built("text", "t0", vscope=1)], [],
                             ints=5)
        self.assertEqual((memory.global_memory, memory.totals),
                         (4 + 4 * 5 + 96, {"p0": 120 + 80, "p1": 120 + 76}))

    def test_a_temporary_need_past_what_the_page_leaves(self):
        # The Editor's compile said "temporary use of QR code(-46)" for such a page.
        memory = self.memory(self.BASIC, [built("qr-code", "q0", txt_maxl=192)])
        self.assertEqual(memory.refusals, (("p0", "q0 needs 3382 bytes of temporary memory, where "
                                                  "the page leaves 3336 of the NX4832T035's 3584: "
                                                  "46 missing, and the Nextion Editor's compile "
                                                  "refuses it (\"The remaining memory is not "
                                                  "enough\")"),))
        # With 1 byte to spare, and then 3 missing.
        qr = built("qr-code", "q0", txt_maxl=154)
        self.assertEqual(self.memory(self.BASIC, [qr, built("text", "t0", txt_maxl=542)])
                         .refusals, ())
        self.assertIn("3 missing", self.memory(self.BASIC, [
            qr, built("text", "t0", txt_maxl=546)]).refusals[0][1])

    def test_a_page_holding_what_the_table_lacks(self):
        # The basic screen refuses a sliding text, so the table has no cost of
        # it. It counts as nothing but its place among the page's objects, a
        # lower bound, and the other pages are still checked.
        memory = self.memory(self.BASIC, [], [built("sliding-text", "st0")],
                             [built("text", "t%d" % n, txt_maxl=1000) for n in range(4)])
        self.assertEqual((memory.unmeasured[0], str(memory.unmeasured[1])),
                         ("p1", "p1.st0: the memory of a sliding-text was not measured"))
        self.assertEqual(memory.warning, "memory counted without p1.st0, as the memory of a "
                                         "sliding-text was not measured")
        self.assertEqual(memory.totals, {"p0": 16 + 20, "p1": 16 + 20, "p2": 16 + 4072})
        self.assertEqual(memory.refusals, (("p2", "its memory, at least 16 + 4072 = 4088 bytes, "
                                                  "passes the NX4832T035's 3584, and the Nextion "
                                                  "Editor's compile refuses it (\"Memory "
                                                  "overflow\")"),))

    def test_refused_with_what_the_table_lacks_on_its_page(self):
        texts = [built("text", "t%d" % n, txt_maxl=1000) for n in range(4)]
        memory = self.memory(self.BASIC, [built("sliding-text", "st0")] + texts)
        self.assertEqual([name for name, _ in memory.refusals], ["p0"])
        self.assertIn("at least 16 + 4072", memory.refusals[0][1])

    def test_a_temporary_need_past_what_the_page_leaves_around_what_was_left_out(self):
        # The page leaves at most 3336, and the QR code needs at least 3382.
        memory = self.memory(self.BASIC, [built("qr-code", "q0", txt_maxl=192),
                                          built("sliding-text", "st0")])
        self.assertEqual(memory.refusals, (("p0", "q0 needs at least 3382 bytes of temporary "
                                                  "memory, where the page leaves at most 3336 of "
                                                  "the NX4832T035's 3584: at least 46 missing, and "
                                                  "the Nextion Editor's compile refuses it (\"The "
                                                  "remaining memory is not enough\")"),))

    def test_a_temporary_need_the_table_lacks(self):
        # A QR code's need past the table's last step: the component counts as
        # nothing, its temporary need too.
        memory = self.memory(self.BASIC, [built("qr-code", "q0", txt_maxl=193)])
        self.assertEqual((str(memory.unmeasured[1]), memory.totals, memory.refusals),
                         ("p0.q0: the temporary memory needed at a txt_maxl of 193 was not "
                          "measured", {"p0": 16 + 20}, ()))

    def test_the_exact_counts_still_refuse_what_the_table_lacks(self):
        # The memory probe compares them with the Editor's compile.
        costs = memory_table().series["T"]
        lacking = page(built("sliding-text", "st0"))
        with self.assertRaisesRegex(Unmeasured, "page0.st0: the memory of a sliding-text was "
                                                "not measured"):
            page_memory(costs, lacking)
        with self.assertRaises(Unmeasured):
            global_memory(costs, [lacking], 3)

    def test_a_value_longer_than_its_bound(self):
        # Counted as its bound, as the Editor's compile counted each value the
        # build lets past its bound. A data record is of global scope alone
        # on this series.
        model = model_named("NX8048P050")
        for kind, values, attribute in (("data-record", {"vscope": 1, "format_m": 8}, "format"),
                                        ("variable", {"sta": 0, "txt_maxl": 8}, "txt"),
                                        ("video", {"from": 0, "path_m": 8}, "path")):
            with self.subTest(kind=kind):
                within, past = (measure_page(model, page(built(kind, "c0", **values,
                                                               **{attribute: text})))
                                for text in ("abcdefgh", "abcdefghijk"))
                self.assertEqual((within.unmeasured, past), ((), within))

    def test_a_model_the_table_lacks(self):
        # Said of no page: of the folder's screen. Nothing is counted.
        model = replace(self.BASIC, name="NX0000T000")
        memory = self.memory(model, [])
        self.assertEqual((memory.unmeasured[0], str(memory.unmeasured[1]), memory.totals),
                         (None, "the memory of an NX0000T000 was not measured", {}))
        self.assertEqual(memory.warning, "memory not checked: the memory of an NX0000T000 was "
                                         "not measured")
        self.assertIsNone(self.memory(self.BASIC, []).warning)


class PartTest(unittest.TestCase):
    """A part's bytes for a component's values, read from its attribute, or
    from its fallback while the attribute is 0, as a sliding text's
    `path_m`, the room for its lines, takes its `txt_maxl` at 0."""

    def test_a_fallback_read_while_the_attribute_is_0(self):
        lines = Part("path_m", 1, 1, 1, 4, fallback="txt_maxl")
        self.assertEqual(lines.cost_in({"path_m": 0, "txt_maxl": 356}), 360)
        self.assertEqual(lines.cost_in({"path_m": 100, "txt_maxl": 356}), 104)

    def test_without_a_fallback_0_is_read(self):
        self.assertEqual(Part("txt_maxl", 1, 1, 2, 4).cost_in({"txt_maxl": 0}), 4)

    def test_times_another_attribute(self):
        width = Part("w", 13, 10, 0, 4, "ch")
        self.assertEqual(width.cost_in({"w": 100, "ch": 3}), 3 * 132)

    def test_read_from_a_table(self):
        table = read_memory_table(TABLE.replace(
            'checkbox = {cost = 20, temporary = {attribute = "", steps = []}}',
            'checkbox = {cost = 20, parts = [{attribute = "path_m", bytes = 1, add = 1, '
            'round = 4, fallback = "txt_maxl"}]}'), "test")
        self.assertEqual(table.series["T"].types["checkbox"].parts,
                         (Part("path_m", 1, 1, 1, 4, fallback="txt_maxl"),))


class ReadMemoryTableTest(unittest.TestCase):

    def test_a_table(self):
        table = read_memory_table(TABLE, "test")
        self.assertEqual((table.editor, table.memory), ("3.1.73", {"NX4832T035": 3584}))
        self.assertEqual(table.series["T"].refused, frozenset({"switch"}))
        self.assertEqual(table.series["T"].refused_values, {"gauge": {"sta": (3,)}})

    def test_not_a_table(self):
        with self.assertRaisesRegex(NxwrightError, "test is not a memory table"):
            read_memory_table('editor = "3.1.73"\n', "test")


if __name__ == "__main__":
    unittest.main()
