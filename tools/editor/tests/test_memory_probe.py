"""Tests of the memory probe's rounds (memory_probe.py, and the modules of
its rounds: memory_series.py, memory_type_rounds.py, memory_global_rounds.py,
and memory_need_rounds.py), against a stand-in
for the Editor whose compile counts as a known table does, and refuses as
the Editor 1.68.2 was seen to on a basic screen. The probe must find that
table again. They need neither the Editor nor pywinauto."""
from dataclasses import replace
import unittest

from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_block import Attribute, PageBlock, PageObject
from nxwright.project.memory_table import Part, SeriesCosts, Steps, TypeCosts
from nxwright.project.page_memory import Unmeasured, global_memory, page_memory
from tools.editor.memory_cases import TYPES, defaults
from tools.editor.memory_fit import read_compile
from tools.editor.memory_probe import BASE_INTS, check_series, measure_series
from tools.editor.memory_series import ProbeStopped, SeriesProbe

MEMORY = 3584
# What the stand-in counts: the basic screen's rules as measured, a few
# types refused, and a timer reserving global memory, as a type may, which
# the probe must find too.
REFUSED = {"switch", "file-browser", "data-record", "combo-box", "select", "sliding-text",
           "external-picture", "touch-capture", "file-stream", "gmov", "video", "audio"}
# A QR code's temporary need by its txt_maxl, as hand probes found it on the
# basic screen, its steps' edges chosen where they were not found, and a
# last step past what a page of it can hold.
QR_NEED = Steps("txt_maxl", ((0, 0), (12, 586), (32, 851), (47, 1182), (75, 1565), (100, 1997),
                             (131, 2383), (152, 2823), (190, 3382), (65535, 3900)))
TRUTH = SeriesCosts(16, Part("", 1, 1, 0, 4), 4, 4, 4, {
    **{kind: TypeCosts(20) for kind in TYPES if kind not in REFUSED},
    "text": TypeCosts(8, (Part("txt_maxl", 1, 1, 2, 4),)),
    "hotspot": TypeCosts(0),
    # It reserves global memory by its molloc, 0 by default, as a buffer held there may.
    "waveform": TypeCosts(36, (Part("ch", 16), Part("w", 13, 10, 0, 4, "ch")),
                          reserve_parts=(Part("molloc", 1),)),
    "timer": TypeCosts(24, reserve=8),
    # Its txt_maxl counts only once its `sta` makes it hold text.
    "variable": TypeCosts(4, (Part("txt_maxl", 1, 1, 2, 4, "sta"),)),
    "qr-code": TypeCosts(20, (Part("txt_maxl", 1, 1, 2, 4),), temporary=QR_NEED)},
    frozenset(REFUSED))
# The values the stand-in refuses: a gauge's default `sta`, as the basic
# screen did, and an `aph` past 127.
REFUSED_VALUES = {("gauge", "sta", 3), ("gauge", "aph", 128), ("text", "aph", 128)}


class StandInEditor:
    """Compiles a probe project as the table TRUTH counts it. A page whose
    total leaves less than its temporary need, as `need(page)` gives it, is
    refused as the Editor refused a QR code's: the shortfall, then an error
    of the compile's own, and no last line."""

    def __init__(self, need=None, refuses=lambda kind, attribute, value: (kind, attribute, value)
                 in REFUSED_VALUES, truth: SeriesCosts = TRUTH, memory: int = MEMORY,
                 bound_bytes: int = 0):
        self.projects = []
        self.truth = truth
        self.memory = memory
        self.need = need or (lambda page: page_memory(truth, page).temporary)
        self.refuses = refuses
        # What a component bound to a keyboard adds to global memory.
        self.bound_bytes = bound_bytes

    def compile(self, project) -> tuple:
        self.projects.append(project)
        pages, refusal = [], None
        for name, case in zip(project.page_names(), ((None,) + project.cases)):
            objects = [PageObject([Attribute("type", TYPES_BY_NAME["page"].to_bytes(1,
                                                                                   "little")),
                                   Attribute("objname", name.encode())])]
            for index, component in enumerate(case.components if case else ()):
                values = {**defaults(component.kind), **project.values_of(component)}
                if len(str(values.get("txt", ""))) > values.get("txt_maxl", 65535):
                    # nxwright's build refuses it, as the Editor cuts it.
                    raise ProbeStopped("nxwright did not build %s: its txt is past its "
                                       "txt_maxl" % name)
                if component.kind in self.truth.refused and refusal is None:
                    refusal = "Error:Unsupported component was found for this series " \
                              "device:%s.c%d" % (name, index)
                for attribute, value in values.items():
                    if self.refuses(component.kind, attribute, value) and refusal is None:
                        refusal = "Error:%s.c%d.%sOut of range" % (name, index, attribute)
                objects.append(_page_object(component.kind, "c%d" % index, values))
            pages.append(PageBlock(name, 0, b"", b"", objects))
        if refusal:
            return read_compile(refusal + "\nError:Compile failed! 1 Errors"), pages
        ints = BASE_INTS + project.ints
        lines = ["Available Memory:%d" % self.memory,
                 "Global Memory:%d" % _global(self.truth, pages, ints, self.bound_bytes)]
        for page in pages:
            own = page_memory(self.truth, page).own
            total = _global(self.truth, pages, ints, self.bound_bytes) + own
            if total > self.memory:
                lines.append("Error:Page:%s Error! Memory overflow:%d+%d=%d"
                             % (page.name, total - own, own, total))
                return read_compile("\n".join(lines + ["Error:Compile failed!"])), pages
            if self.need(page) > self.memory - total:
                lines += ["Error:Page:%s The remaining memory is not enough to run the temporary "
                          "use of QR code(-%d),please decrease the value of txt_maxl to reduce "
                          "the comsuption of the memory." % (page.name,
                                                             self.need(page) - self.memory + total),
                          "Destination array was not long enough."]
                return read_compile("\n".join(lines)), pages
            lines.append("Page:%s Memory Occupied:%d+%d=%d" % (page.name, total - own, own,
                                                              total))
        return read_compile("\n".join(lines + ["Compile Successful! 0 Errors"])), pages


def _global(truth: SeriesCosts, pages: list, ints: int, bound_bytes: int) -> int:
    """Global memory as `truth` counts it, but that a slider of global scope
    takes 8 bytes more there, and a component bound to a keyboard
    `bound_bytes` more, which no rule of the table can say: the probe must
    find them so."""
    sliders = sum(1 for page in pages for page_object in page.objects[1:]
                  if page_object.attribute("type")[0] == TYPES_BY_NAME["slider"]
                  and page_object.attribute("vscope")[0] == 1)
    bound = sum(1 for page in pages for page_object in page.objects[1:]
                if (page_object.attribute("key") or b"\xff")[0] != 255)
    return global_memory(truth, pages, ints) + 8 * sliders + bound_bytes * bound


def _page_object(kind: str, name: str, values: dict) -> PageObject:
    attributes = [Attribute("type", TYPES_BY_NAME[kind].to_bytes(1, "little")),
                  Attribute("objname", name.encode())]
    for attribute, value in values.items():
        stored = value.encode("latin-1") if isinstance(value, str) else \
            (value % 2 ** 32).to_bytes(4, "little")
        attributes.append(Attribute(attribute, stored))
    return PageObject(attributes)


class MeasureSeriesTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.editor = StandInEditor()
        cls.probe = SeriesProbe(cls.editor, "NX4832T035")
        cls.result = measure_series(cls.probe)

    def test_the_series_costs_found_again(self):
        costs = self.result.costs
        self.assertEqual((costs.page, costs.objects, costs.global_memory, costs.int_bytes,
                          costs.global_component, costs.refused),
                         (TRUTH.page, TRUTH.objects, TRUTH.global_memory, TRUTH.int_bytes,
                          TRUTH.global_component, TRUTH.refused))
        self.assertEqual(set(costs.types), set(TRUTH.types))
        for kind, truth in TRUTH.types.items():
            with self.subTest(kind=kind):
                found = costs.types[kind]
                self.assertEqual((found.cost, set(found.parts), found.reserve,
                                  set(found.reserve_parts)),
                                 (truth.cost, set(truth.parts), truth.reserve,
                                  set(truth.reserve_parts)))

    def test_a_global_scope_that_costs_otherwise_is_unmeasured(self):
        # The stand-in's global slider takes 8 bytes more than the rule says:
        # it alone is found, so the rest keep their global scope measured.
        unscoped = {kind for kind, costs in self.result.costs.types.items()
                    if costs.unmeasured.get("vscope") == 0}
        self.assertEqual(unscoped, {"slider"})

    def test_every_page_compiled_agrees(self):
        self.assertEqual(check_series(self.probe, self.result.costs), [])

    def test_a_refused_default_measured_at_another_value(self):
        self.assertEqual(self.probe.replaced, {("gauge", "sta"): (3, 0)})
        self.assertIn("the compile refused a gauge's sta 3, nxwright's default; measured at 0",
                      self.result.notes)

    def test_the_refused_values_kept(self):
        # Those the probe tried and the compile refused: each one the stand-in
        # refuses, a gauge's default sta among them.
        found = {(kind, attribute, value)
                 for kind, attributes in self.result.costs.refused_values.items()
                 for attribute, values in attributes.items() for value in values}
        self.assertLessEqual(found, REFUSED_VALUES)
        self.assertIn(("gauge", "sta", 3), found)

    def test_what_could_not_be_varied_is_unmeasured(self):
        # A text's keyboard is varied in its own round, with the keypad, so
        # it is measured; so is a waveform's `dir`, a byte kept as text,
        # varied over its choices. A text's scope away from both is not.
        for kind in ("text", "number", "xfloat", "scrolling-text"):
            with self.subTest(kind=kind):
                self.assertNotIn("key", self.result.costs.types[kind].unmeasured)
        self.assertNotIn("dir", self.result.costs.types["waveform"].unmeasured)
        page = PageBlock("p", 0, b"", b"", [
            _page_object("page", "p", {}),
            _page_object("text", "t0", {**defaults("text"), "vscope": 1, "key": 3})])
        self.assertEqual(page_memory(self.result.costs, page).own, 16 + 4 + 4)
        self.assertTrue(any(project.keyboards == ("keypad",) for project in self.editor.projects))

    def test_projects_hold_at_most_250_pages(self):
        self.assertTrue(all(len(project.cases) < 250 for project in self.editor.projects))

    def test_the_temporary_need_found_again(self):
        # Measured up to the largest txt_maxl the probe gave it, its base and
        # 200, where its last step ends; the larger of two counts. No other
        # type needs any.
        found = self.result.costs.types["qr-code"].temporary
        last = defaults("qr-code")["txt_maxl"] + 200
        self.assertEqual(found, Steps("txt_maxl", QR_NEED.steps[:-1] + ((last, 3900),)))
        self.assertEqual({kind for kind, costs in self.result.costs.types.items()
                          if costs.temporary}, {"qr-code"})
        self.assertNotIn("txt_maxl", self.result.costs.types["qr-code"].unmeasured)

    def test_a_value_whose_need_its_page_cannot_hold(self):
        # A QR code of txt_maxl base + 200 needs more than its page leaves of
        # the screen's memory: its cost is fitted from the other values.
        last = defaults("qr-code")["txt_maxl"] + 200
        self.assertIn("a qr-code's txt_maxl %d needs more temporary memory than its page "
                      "leaves: its cost is not measured there" % last, self.result.notes)

    def test_a_value_past_the_last_step_is_unmeasured(self):
        last = defaults("qr-code")["txt_maxl"] + 200
        for txt_maxl, measured in ((last, True), (last + 1, False)):
            with self.subTest(txt_maxl=txt_maxl):
                page = PageBlock("p", 0, b"", b"", [
                    _page_object("page", "p", {}),
                    _page_object("qr-code", "q0", {**defaults("qr-code"), "txt_maxl": txt_maxl})])
                if measured:
                    self.assertEqual(page_memory(self.result.costs, page).temporary, 3900)
                else:
                    with self.assertRaises(Unmeasured):
                        page_memory(self.result.costs, page)


class RangeEndTest(unittest.TestCase):
    """A stand-in that refuses a QR code's txt_maxl past 192, out of range,
    as the Editor refused 230 on the basic screen: the probe finds the
    largest value the series takes, and the steps end there."""

    def test_the_steps_end_at_the_largest_value_taken(self):
        def refuses(kind, attribute, value):
            return (kind, attribute, value) in REFUSED_VALUES or \
                (kind, attribute) == ("qr-code", "txt_maxl") and value > 192
        result = measure_series(SeriesProbe(StandInEditor(refuses=refuses), "NX4832T035"))
        steps = result.costs.types["qr-code"].temporary.steps
        self.assertEqual(steps[-2:], ((190, 3382), (192, 3900)))
        self.assertIn(230, result.costs.refused_values["qr-code"]["txt_maxl"])


class LargeScreenTest(unittest.TestCase):
    """A stand-in of 300,000 bytes, more than one text can fill, that refuses
    a text's txt_maxl past 20,000, out of range: the pages measuring needs
    are filled with several texts, of a size the series takes, and the QR
    code's need is found again."""

    def test_needs_measured_on_pages_of_several_fillers(self):
        def refuses(kind, attribute, value):
            return (kind, attribute, value) in REFUSED_VALUES or \
                (kind, attribute) == ("text", "txt_maxl") and value > 20000
        probe = SeriesProbe(StandInEditor(refuses=refuses, memory=300000), "NX4832T035")
        result = measure_series(probe)
        self.assertEqual(result.costs.types["qr-code"].temporary.steps[:3], QR_NEED.steps[:3])
        self.assertEqual(check_series(probe, result.costs), [])


class LocalOnlyTest(unittest.TestCase):
    """A stand-in that refuses a timer of global scope, as the Intelligent
    NX8048P050 refused a file stream so: "p015.c0.vscopeOut of range". The
    probe leaves its global scope unmeasured, and measures the others'."""

    def test_its_global_scope_unmeasured(self):
        def refuses(kind, attribute, value):
            return (kind, attribute, value) in REFUSED_VALUES or \
                (kind, attribute, value) == ("timer", "vscope", 1)
        probe = SeriesProbe(StandInEditor(refuses=refuses), "NX4832T035")
        result = measure_series(probe)
        types = result.costs.types
        self.assertEqual(types["timer"].unmeasured.get("vscope"), 0)
        self.assertNotIn("vscope", types["text"].unmeasured)
        self.assertIn("the compile refused a timer of global scope: measured at local scope "
                      "alone", result.notes)
        self.assertEqual(check_series(probe, result.costs), [])


class GlobalOnlyTest(unittest.TestCase):
    """A stand-in that takes data records of global scope alone, as the
    Intelligent NX8048P050 refused one of local scope: "p006.c0.vscopeOut of
    range". The probe measures its type at global scope: its cost, the part
    on its page and that in global memory together, and its buffer's part.
    Its `filter_m` counts here, where its `molloc` of 10,752, as the Editor
    counted it, would not fit a basic screen's memory."""

    @classmethod
    def setUpClass(cls):
        record = TypeCosts(20, (Part("filter_m", 1, 1, 0, 4),))
        truth = replace(TRUTH, types={**TRUTH.types, "data-record": record},
                        refused=TRUTH.refused - {"data-record"})

        def refuses(kind, attribute, value):
            return (kind, attribute, value) in REFUSED_VALUES or \
                (kind, attribute, value) == ("data-record", "vscope", 0)
        cls.probe = SeriesProbe(StandInEditor(refuses=refuses, truth=truth), "NX4832T035")
        cls.result = measure_series(cls.probe)

    def test_measured_at_global_scope(self):
        found = self.result.costs.types["data-record"]
        self.assertEqual((found.cost, found.parts, found.reserve, found.reserve_parts),
                         (20, (Part("filter_m", 1, 1, 0, 4),), 0, ()))
        # Its local scope, which the series refuses, is not measured.
        self.assertEqual(found.unmeasured.get("vscope"), 1)
        self.assertIn("the compile refused a data-record of local scope: measured at global "
                      "scope", self.result.notes)

    def test_every_page_compiled_agrees(self):
        self.assertEqual(check_series(self.probe, self.result.costs), [])


class FallbackTest(unittest.TestCase):
    """A stand-in that takes sliding texts, whose `path_m`, the room for
    their lines, takes their `txt_maxl` while it is 0, as the Intelligent
    and Edge series counted it. The probe finds both parts again, and with
    them the type's global scope."""

    @classmethod
    def setUpClass(cls):
        sliding = TypeCosts(120, (Part("txt_maxl", 1, 1, 1, 4),
                                  Part("path_m", 1, 1, 1, 4, fallback="txt_maxl")))
        truth = replace(TRUTH, types={**TRUTH.types, "sliding-text": sliding},
                        refused=TRUTH.refused - {"sliding-text"})
        cls.probe = SeriesProbe(StandInEditor(truth=truth), "NX4832T035")
        cls.result = measure_series(cls.probe)

    def test_both_parts_found_again(self):
        found = self.result.costs.types["sliding-text"]
        self.assertEqual((found.cost, set(found.parts)),
                         (120, {Part("txt_maxl", 1, 1, 1, 4),
                                Part("path_m", 1, 1, 1, 4, fallback="txt_maxl")}))
        self.assertNotIn("path_m", found.unmeasured)
        self.assertNotIn("vscope", found.unmeasured)

    def test_every_page_compiled_agrees(self):
        self.assertEqual(check_series(self.probe, self.result.costs), [])


class BufferAtItsLimitTest(unittest.TestCase):
    """A stand-in that takes data records, refusing their `path_m` past its
    default of 255, as the Intelligent NX8048P050 did, and their `dir_m` at
    any value but its default. The probe measures the first below its
    default, and leaves the second unmeasured, rather than costing nothing."""

    @classmethod
    def setUpClass(cls):
        record = TypeCosts(20, (Part("path_m", 1, 1, 1, 4),))
        truth = replace(TRUTH, types={**TRUTH.types, "data-record": record},
                        refused=TRUTH.refused - {"data-record"})

        def refuses(kind, attribute, value):
            return (kind, attribute, value) in REFUSED_VALUES or \
                (kind, attribute) == ("data-record", "path_m") and value > 255 or \
                (kind, attribute) == ("data-record", "dir_m") and value != 255
        cls.probe = SeriesProbe(StandInEditor(refuses=refuses, truth=truth), "NX4832T035")
        cls.result = measure_series(cls.probe)

    def test_measured_below_its_default(self):
        found = self.result.costs.types["data-record"]
        self.assertEqual((found.cost, found.parts), (20, (Part("path_m", 1, 1, 1, 4),)))

    def test_unmeasured_where_it_takes_no_other_value(self):
        self.assertEqual(self.result.costs.types["data-record"].unmeasured.get("dir_m"), 255)
        self.assertIn("a data-record's dir_m was measured at 255 alone: not measured away from it",
                      self.result.notes)

    def test_every_page_compiled_agrees(self):
        self.assertEqual(check_series(self.probe, self.result.costs), [])


class KeyboardCostTest(unittest.TestCase):
    """A stand-in whose components bound to a keyboard take 8 bytes more
    of global memory, which no rule of the table can say: the probe leaves
    `key` unmeasured away from 255, saying so."""

    def test_its_key_unmeasured(self):
        result = measure_series(SeriesProbe(StandInEditor(bound_bytes=8), "NX4832T035"))
        self.assertEqual(result.costs.types["text"].unmeasured.get("key"), 255)
        self.assertIn("a component bound to the keypad changes what the compile counts on "
                      "NX4832T035: key is not measured away from 255", result.notes)


class NeedMovingOtherwiseTest(unittest.TestCase):
    """A stand-in whose QR code needs 4 bytes more when its `dis` is not its
    default: the probe finds its steps at that default, and leaves its
    `dis` unmeasured away from it."""

    def test_its_dis_is_unmeasured(self):
        dis = defaults("qr-code")["dis"]

        def need(page):
            moved = sum(4 for page_object in page.objects[1:]
                        if page_object.attribute("type")[0] == TYPES_BY_NAME["qr-code"]
                        and int.from_bytes(page_object.attribute("dis"), "little") != dis)
            return page_memory(TRUTH, page).temporary + moved
        result = measure_series(SeriesProbe(StandInEditor(need), "NX4832T035"))
        costs = result.costs.types["qr-code"]
        self.assertEqual(costs.unmeasured.get("dis"), dis)
        self.assertEqual(costs.temporary.steps[:3], QR_NEED.steps[:3])
        self.assertIn("a qr-code's temporary need changes with its dis: not measured away "
                      "from %d" % dis, result.notes)


if __name__ == "__main__":
    unittest.main()
