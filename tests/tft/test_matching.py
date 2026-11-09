"""The check that a compile writes only what nxwright has matched
(tft/matching.py), on a Project of the facts of a page made in memory on
the T base folder (tests/tft/unit_inputs.py).
"""
from dataclasses import replace
import importlib
import re
from types import SimpleNamespace
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec

from nxwright.tft import matching, reasons
from nxwright.tft.component_types import type_module
from nxwright.tft.matching import Need, Rule, firmware_needs, project_needs, refuse_unmatched, unmatched
from tools.tft.probing.macro_probes import macros_text
from tools.tft.probing.text_probes import text_component
from nxwright.tft.series_differences import DIFFERENCES
from tests.tft.unit_inputs import page, project_of, with_font_blocks

TEXT = '\n[[component]]\nname = "t0"\ntype = "text"\nx = 10\ny = 10\nw = 100\nh = 30\ntxt = "Yo"\n'


def facts(components: str, code: str = ""):
    """Returns a Project of the facts of page0 of the T base folder, made in
    memory, given `components`, in a page file's form, and `code` in its
    events, in strict Nextion syntax. It holds the base folder's font, whose
    block is its file, as a whole build holds it, so that the check reads
    the font's need."""
    return with_font_blocks(project_of(page(components, code=code, strict=True), strict=True),
                            "T")


def component(name: str, type_name: str, place: tuple = None) -> str:
    """Returns a component in a page file's form, at its type's defaults
    but for its `place`, an x, a y, a width, and a height, when given."""
    lines = '\n[[component]]\nname = "%s"\ntype = "%s"\n' % (name, type_name)
    if place is not None:
        lines += "x = %d\ny = %d\nw = %d\nh = %d\n" % place
    return lines


# Pieces matched on a leader and left off one of its followers on purpose,
# {(module, follower): why}, such as one the Nextion Editor refuses on the
# follower. None now.
_LEADER_ONLY = {}


def _missing_followers() -> list:
    """Returns (module, follower) for each piece module whose SERIES gives a
    leader of series_differences.DIFFERENCES without one of its followers,
    but those of _LEADER_ONLY."""
    return [(module.__name__, follower) for module in matching.piece_modules()
            for follower, differences in DIFFERENCES.items()
            if differences["leader"] in module.SERIES and follower not in module.SERIES
            and (module.__name__, follower) not in _LEADER_ONLY]


class MatchingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # A text, with a line in its Touch Release event.
        cls.project = facts(TEXT, 'on t0.up:\n  t0.txt="Hi"\n')

    def needs(self) -> dict:
        return {need.described(): need for need in project_needs(self.project)}

    def test_the_project_s_needs(self):
        needs = self.needs()
        for described in ("series T", "model NX4832T035", "rotation 0", "encoding iso-8859-1",
                          "type page", "type text", "attribute text.txt = 'Yo'",
                          "attribute text.x = 10", "attribute page.w = 320",
                          "code event = 't0.txt=\"Hi\"'",
                          "code program.s = 'baud=9600'", "resource font"):
            self.assertIn(described, needs)
        self.assertEqual(needs["attribute text.txt = 'Yo'"].where, "page0: t0")
        self.assertEqual(needs["attribute text.txt = 'Yo'"].context["txt_maxl"],
                         b"\x0a\x00")
        self.assertEqual(needs["code event = 't0.txt=\"Hi\"'"].where, "page0: t0, up, line 1")
        # An attribute at its default is no need.
        self.assertNotIn("attribute text.pco = 0", needs)

    def test_an_event_s_lines_give_their_page_s_name(self):
        # The screen's commands may name the line's own page, as a component
        # (instructions/screen_commands.py).
        self.assertEqual(self.needs()["code event = 't0.txt=\"Hi\"'"].context["page"], "page0")

    def test_code_is_split_at_line_ends_alone(self):
        # Byte 0x85 is U+0085 in iso-8859-1, which str.splitlines splits at.
        project = SimpleNamespace(codec=TextCodec("iso-8859-1"))
        code = b'a="x\x85y"\r\nb=1\n\n  \t\r\nc=2'
        self.assertEqual(matching.code_lines(project, code), ['a="x\x85y"', "b=1", "c=2"])

    def test_code_lines_without_their_indentation_and_comments(self):
        # The Nextion Editor writes a line as its code alone, without its
        # indentation or a comment after it. A comment alone stays a line,
        # and a "//" inside a text is no comment.
        project = facts(TEXT)
        code = b'  sys0=1 // note\r\n\tint a=0\t// b\r\n// alone\r\nt0.txt="http://x" // c'
        self.assertEqual(matching.code_lines(project, code),
                         ["sys0=1", "int a=0", "// alone", 't0.txt="http://x"'])

    def test_a_rule_covers_its_kind_subject_and_value(self):
        text = self.needs()["attribute text.txt = 'Yo'"]
        self.assertEqual(unmatched([text], [Rule("attribute", "text.txt", "any text")]), [])
        self.assertEqual(unmatched([text], [Rule("attribute", None, "any attribute")]), [])
        self.assertEqual(unmatched([text], [Rule("attribute", "text.pco", "any colour")]), [text])
        short = Rule("attribute", "text.txt", "a text of one byte",
                     covers=lambda need: len(need.value) == 1)
        self.assertEqual(unmatched([text], [short]), [text])

    def test_refused_listing_each_need_once(self):
        with self.assertRaises(NxwrightError) as raised:
            refuse_unmatched(firmware_needs((1, 68, 2)) + project_needs(self.project), [])
        message = str(raised.exception)
        self.assertIn("- firmware 1.68.2 (the firmware)", message)
        self.assertIn("- attribute text.txt = 'Yo' (page0: t0)", message)
        self.assertEqual(message.count("- series T"), 1)

    def test_a_refusal_gives_its_rule_s_reason(self):
        short = Rule("attribute", "text.txt", "a text of one byte",
                     covers=lambda need: len(need.value) == 1,
                     refuses_because=reasons.DOES_NOT_FIT)
        with self.assertRaises(NxwrightError) as raised:
            refuse_unmatched(project_needs(self.project), [short])
        self.assertIn("- attribute text.txt = 'Yo' (page0: t0): the value is outside the range "
                      "that can be encoded",
                      str(raised.exception))

    def test_a_refused_line_of_code_is_an_unsupported_statement(self):
        # A rule of code gives no reason, so the line it refuses is listed
        # as an unsupported statement.
        any_line = Rule("code", None, "no line", covers=lambda need: False)
        with self.assertRaises(NxwrightError) as raised:
            refuse_unmatched(project_needs(self.project), [any_line])
        self.assertIn("- code event = 't0.txt=\"Hi\"' (page0: t0, up, line 1): unsupported "
                      "statement, please file a bug",
                      str(raised.exception))
        # So is a line whose characters past ASCII no rule takes.
        past_ascii = Need("text in code", "iso-8859-1", 't0.txt="中"')
        self.assertEqual(matching.refusal_reasons(past_ascii, []),
                         [reasons.UNSUPPORTED_STATEMENT])
        # A need of any other kind gets only the reasons that its rules give.
        self.assertEqual(matching.refusal_reasons(Need("attribute", "text.txt", b"Yo"), []), [])

    def test_a_rule_refuses_only_for_one_of_the_reasons(self):
        with self.assertRaises(ValueError):
            Rule("attribute", "text.txt", "a text of one byte",
                 refuses_because="no probe tried it")

    def test_a_refusal_gives_the_reasons_of_its_series_rules(self):
        # A rule of some series alone neither takes nor refuses on another.
        on_t = Rule("attribute", "text.vscope", "0 or 1", lambda need: need.value[0] <= 1,
                    reasons.NOT_SUPPORTED_YET, series=("T",))
        on_p = Rule("attribute", "text.vscope", "0 or 1", lambda need: need.value[0] <= 1,
                    reasons.INVALID_VALUE, series=("P",))
        need = Need("attribute", "text.vscope", b"\x02", series="T")
        self.assertEqual(matching.refusal_reasons(need, [on_t, on_p]),
                         [reasons.NOT_SUPPORTED_YET])
        self.assertEqual(unmatched([Need("attribute", "text.vscope", b"\x00", series="P")],
                                   [on_t]), [Need("attribute", "text.vscope", b"\x00",
                                                  series="P")])

    def test_a_refusal_s_reasons_are_found_once_for_each_need_described(self):
        # The same need in 50 places is listed once, so its reasons are
        # found once, from the rules of its kind and subject.
        rule = Rule("attribute", "text.vscope", "0 or 1", lambda need: need.value[0] <= 1,
                    reasons.NOT_SUPPORTED_YET)
        other = Rule("attribute", "text.x", "any", lambda need: False, reasons.INVALID_VALUE)
        needs = [Need("attribute", "text.vscope", b"\x02", "page0, t%d" % number)
                 for number in range(50)]
        with mock.patch.object(matching, "refusal_reasons",
                               wraps=matching.refusal_reasons) as found:
            with self.assertRaisesRegex(NxwrightError, re.escape(
                    "and 49 more): " + reasons.NOT_SUPPORTED_YET)):
                refuse_unmatched(needs, [other, rule])
        self.assertEqual(found.call_count, 1)
        self.assertEqual(found.call_args.args[1], [rule])

    def test_nothing_is_refused_once_rules_cover_it(self):
        rules = [Rule(kind, None, "anything") for kind in (
            "firmware", "series", "model", "rotation", "encoding", "type", "attribute", "code",
            "resource")]
        refuse_unmatched(firmware_needs((1, 68, 2)) + project_needs(self.project), rules)

    def test_the_pieces_lists_are_gathered(self):
        from nxwright.tft import packaging
        said = {(rule.kind, rule.subject, rule.says) for rule in matching.matched_rules()}
        self.assertTrue(all((rule.kind, rule.subject, rule.says) in said
                            for rule in packaging.MATCHED))
        # The page's type is no need packaging covers, so a project is
        # refused with packaging's rules alone.
        with self.assertRaisesRegex(NxwrightError, "- type page"):
            refuse_unmatched(project_needs(self.project), packaging.MATCHED)

    def test_a_piece_without_its_list_is_refused(self):
        module = importlib.import_module("nxwright.tft.frame")
        kept = module.MATCHED
        del module.MATCHED
        try:
            with self.assertRaisesRegex(NxwrightError, "nxwright.tft.frame keeps no MATCHED list"):
                matching.matched_rules()
        finally:
            module.MATCHED = kept

    def test_a_piece_without_its_series_is_refused(self):
        module = importlib.import_module("nxwright.tft.frame")
        kept = module.SERIES
        del module.SERIES
        try:
            with self.assertRaisesRegex(NxwrightError, "nxwright.tft.frame gives no SERIES"):
                matching.matched_rules()
        finally:
            module.SERIES = kept

    def test_every_need_gives_the_project_s_series(self):
        self.assertEqual({need.series for need in project_needs(self.project)}, {"T"})

    def test_a_piece_matches_only_on_its_series(self):
        # A text matched on T alone: its rules cover a text of T, and one of
        # a need with no series, as the firmware's, but not one of K.
        module = importlib.import_module("nxwright.tft.component_types.text")
        kept = module.SERIES
        module.SERIES = ("T",)
        try:
            rules = matching.matched_rules()
            for series, covered in (("T", True), (None, True), ("K", False)):
                with self.subTest(series=series):
                    need = matching.Need("type", "text", series=series)
                    self.assertEqual(unmatched([need], rules) == [], covered)
        finally:
            module.SERIES = kept

    def test_every_type_takes_any_name(self):
        # nxwright's build decides which names a project may hold, and the
        # frame writes any name as the CRC of its bytes. So a component's
        # name is never refused by nxwright: not one past ASCII, nor one starting
        # with a digit, which nxwright's build refuses before.
        rules = matching.matched_rules()
        subjects = sorted({rule.subject for rule in rules
                           if rule.kind == "attribute" and str(rule.subject).endswith(".objname")})
        self.assertIn("text.objname", subjects)
        for subject in subjects:
            for name in (b"t\xe9", b"1t", b"t-0", b"a_name_of_14ch"):
                with self.subTest(subject, name=name):
                    need = Need("attribute", subject, name)
                    self.assertEqual(unmatched([need], rules), [])

    def test_each_piece_of_a_leader_is_on_its_followers(self):
        # A piece matched on T must be matched on K and F too, and one on P
        # on E, as each follower writes as its leader does.
        self.assertEqual(_missing_followers(), [])

    def test_a_piece_missing_a_follower_is_found(self):
        module = importlib.import_module("nxwright.tft.component_types.text")
        kept = module.SERIES
        module.SERIES = tuple(series for series in kept if series != "K")
        try:
            self.assertEqual(_missing_followers(), [("nxwright.tft.component_types.text", "K")])
        finally:
            module.SERIES = kept


class NeedsTest(unittest.TestCase):
    """What the check reads from a project (project_needs), on Projects of
    facts of pages made in memory, by each kind of need not given above:
    the device's settings, which every need carries too; a page's own
    type; a macro and its lines; a global component, in every line's
    context; and a font's block. MatchingTest gives a text's needs, its
    attributes, its code, and program.s's; OverlapTest those of components
    that overlap; and tests/tft/test_encodings.py those of code past ASCII. The
    needs are typed here, as no fixture keeps one."""

    def test_the_device_s_settings(self):
        # On K, at 90 degrees, in utf-8: the first four needs, and the
        # settings every need carries.
        project = project_of(page(series="K", rotation=90, encoding="utf-8"), series="K",
                             rotation=90, encoding="utf-8", fonts=0)
        needs = project_needs(project)
        self.assertEqual([(need.kind, need.subject, need.where) for need in needs[:4]], [
            ("series", "K", "the screen model"), ("model", "NX4832K035", "the screen model"),
            ("rotation", "90", "the device settings"),
            ("encoding", "utf-8", "the device settings")])
        self.assertEqual({(need.series, need.model, need.rotation, need.encoding)
                          for need in needs}, {("K", "NX4832K035", 90, "utf-8")})

    def test_every_device_setting_is_taken(self):
        # packaging.py writes each of the other device settings, so none
        # away from its default leaves a need that no rule takes.
        project = project_of(page(), fonts=0)
        for name, value in (("memory_file_storage_size", 1), ("ignore_library_resources", True),
                            ("ignore_image_resources", True),
                            ("password_hash", bytes(range(1, 5))), ("one_time_update", True)):
            with self.subTest(name):
                changed = replace(project, settings=replace(project.settings, **{name: value}))
                self.assertEqual(unmatched(project_needs(changed), matching.matched_rules()), [])

    def test_each_page_s_type(self):
        needs = [need for need in project_needs(project_of(page(), page(name="page1"), fonts=0))
                 if need.kind == "type"]
        self.assertEqual([(need.subject, need.where) for need in needs],
                         [("page", "page0: page0"), ("page", "page1: page1")])

    def test_a_macro_and_its_lines(self):
        # The macro itself, then each line, as program.s's lines.
        project = project_of(page(strict=True), page(strict=True, name="page1"), strict=True,
                             fonts=0, macros=macros_text([("m0", ["sys0=1", "return"])]))
        needs = [need for need in project_needs(project)
                 if need.kind == "macro" or need.subject == "macro"]
        self.assertEqual([(need.kind, need.subject, need.value, need.where) for need in needs], [
            ("macro", "m0", None, "the macro m0"), ("code", "macro", "sys0=1", "macro m0, line 1"),
            ("code", "macro", "return", "macro m0, line 2")])

    def test_a_global_component_in_every_line_s_context(self):
        # A global text of page1, which code on page0 and in program.s may
        # name by its page's name, as page1.t9.
        project = project_of(page(text_component(), code='on t0.up:\n  t0.txt="a"\n'),
                             page(text_component("t9", vscope=1), name="page1"), fonts=0)
        lines = [need for need in project_needs(project) if need.kind == "code"]
        self.assertEqual({need.subject for need in lines}, {"event", "program.s"})
        self.assertEqual({tuple(need.context["globals"]) for need in lines},
                         {(("page1", "t9"),)})

    def test_a_font_s_block(self):
        # A font's need gives its block, which the font's rules read. A
        # picture's block is made only by a whole build, so its need is read
        # by the check of nxwright's example project, which has pictures
        # (tests/tft/test_example_project.py).
        project = with_font_blocks(project_of(page()), "T")
        needs = [need for need in project_needs(project) if need.kind == "resource"]
        self.assertEqual([(need.subject, need.where) for need in needs],
                         [("font", "the font 0.zi")])
        self.assertEqual(needs[0].context["block"], project.blocks["0.zi"])

    def test_derived_attributes_give_none(self):
        # A component's type, ID, and right and bottom edges, which its page
        # object holds, are the build's, and give no need.
        made = page(text_component())
        derived = ("type", "id", "endx", "endy")
        self.assertTrue(all(made.objects[1].attribute(name) is not None for name in derived))
        subjects = {need.subject for need in project_needs(project_of(made, fonts=0))}
        self.assertFalse({"text." + name for name in derived} & subjects)


class OverlapTest(unittest.TestCase):
    """The needs of two components of a page that share a pixel."""

    def overlaps(self, *components) -> list:
        needs = project_needs(facts("".join(components)))
        return [(need.subject, need.where) for need in needs if need.kind == "overlap"]

    def test_two_components_sharing_a_pixel(self):
        # t1's top left pixel is t0's bottom right one.
        self.assertEqual(self.overlaps(component("t0", "text", (10, 10, 100, 30)),
                                       component("t1", "text", (109, 39, 100, 30))),
                         [("text and text", "page0: t0 and t1")])

    def test_components_that_touch_share_none(self):
        # As the probe text-touching showed: four texts in a grid, sharing
        # sides and corners.
        self.assertEqual(self.overlaps(*[component("t%d" % number, "text",
                                                   (10 + 100 * (number % 2),
                                                    10 + 30 * (number // 2), 100, 30))
                                         for number in range(4)]), [])

    def test_a_component_without_a_place_shares_none(self):
        self.assertEqual(self.overlaps(component("t0", "text", (0, 0, 320, 480)),
                                       component("va0", "variable"),
                                       component("tm0", "timer")), [])

    def test_each_two_once_the_earlier_first(self):
        # A text over the whole screen, then a number and a button apart.
        self.assertEqual(self.overlaps(component("t0", "text", (0, 0, 320, 480)),
                                       component("n0", "number", (10, 10, 100, 30)),
                                       component("b0", "button", (10, 100, 100, 50))),
                         [("text and number", "page0: t0 and n0"),
                          ("text and button", "page0: t0 and b0")])

    def test_its_context_gives_the_two_types(self):
        needs = project_needs(facts(component("t0", "text", (10, 10, 100, 30))
                                    + component("n0", "number", (50, 20, 100, 30))))
        self.assertEqual([need.context for need in needs if need.kind == "overlap"],
                         [{"types": ("text", "number")}])

    def test_an_overlap_no_rule_covers_is_refused(self):
        # overlaps.py's rule covers the types its probes matched, every type
        # T draws. So the overlap here is of a type of another series, a
        # combo box, as the check gives a page's overlap.
        need = Need("overlap", "text and combo-box", where="page0: t0 and cb0",
                    context={"types": ("text", "combo-box")})
        with self.assertRaisesRegex(NxwrightError,
                                    r"- overlap text and combo-box \(page0: t0 and cb0\)"):
            refuse_unmatched([need])


class TypeModuleTest(unittest.TestCase):

    def test_a_type_with_no_module(self):
        for name in ("no-such-type", "../frame", ""):
            with self.subTest(name):
                self.assertIsNone(type_module(name))

    def test_a_type_s_module(self):
        from nxwright.tft.component_types import text
        self.assertIs(type_module("text"), text)

    def test_a_type_s_module_is_found_once(self):
        # A type's module does not change while nxwright runs, so it is found
        # the first time it is needed, and not looked for again. A compile
        # needs one for each object, again and again.
        type_module("number")
        type_module("no-such-type")
        with mock.patch("importlib.util.find_spec") as find_spec, \
                mock.patch("importlib.import_module") as import_module:
            for _ in range(100):
                type_module("number")
                type_module("no-such-type")
        self.assertEqual((find_spec.call_count, import_module.call_count), (0, 0))


if __name__ == "__main__":
    unittest.main()
