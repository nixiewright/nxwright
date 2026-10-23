"""The catalog of the Editor's attributes (tools/editor/catalog.py): hints'
choices, catalogs merged and compared with nxwright's defaults, and the
variants' values. Made-up catalogs stand in for the Editor's."""
import unittest

from tools.editor.catalog import (Seen, choices_of, compare, copied_hints, known_rows, merge,
                                  most_choices, report_markdown, variant_settings, with_values)

# Types by the number the `type` attribute stores: a text, and a scrolling text.
TEXT, SCROLLING = 116, 55


def _row(name, value, hint, green):
    return {"name": name, "value": value, "hint": hint, "code_can_change": green}


STA_HINT = "Background fill:0-crop image;1-solid color;2-image;3-transparency"
DEFAULTS_CATALOG = {"variant": "defaults", "objects": [
    {"page": "page0", "component": "t0", "type": TEXT, "attributes": [
        _row("type", "116", "Component type:Text", False),
        _row("sta", "solid color", STA_HINT, True),
        _row("w", "100", "Width", False),
        _row("pco", "0", "Font color", True)]},
    {"page": "page0", "component": "g0", "type": SCROLLING, "attributes": [
        _row("sta", "solid color", "Scrolling background:0-crop image;1-solid color", True),
        _row("tim", "150", "Scrolling period", True)]}]}
# Variant 2, read with --known: the rows met before have no hint of their own.
VARIANT = {"variant": "choice 2", "objects": [
    {"page": "page0", "component": "t0", "type": TEXT, "attributes": [
        _row("sta", "image", None, False),
        _row("pic", "65535", "Background image", True)]}]}
DEFAULTS = {"text": {"attributes": {"sta": 1, "w": 100, "pco": 63488, "pic": 65535, "aph": 127}},
            "scrolling-text": {"attributes": {"sta": 1, "tim": 150}},
            "timer": {"attributes": {"tim": 400}}}


class ChoicesTest(unittest.TestCase):

    def test_a_list_of_choices(self):
        self.assertEqual(choices_of(STA_HINT),
                         {0: "crop image", 1: "solid color", 2: "image", 3: "transparency"})
        self.assertEqual(choices_of("Variable scope(local-visible in current page, global-visible "
                                    " in all pages):0-local;1-global"), {0: "local", 1: "global"})

    def test_no_choices(self):
        self.assertEqual(choices_of("Opaqueness(0-127)"), {})
        self.assertEqual(choices_of("Component type:Scrolling text"), {})
        self.assertEqual(choices_of(None), {})


class MergeTest(unittest.TestCase):

    def test_rows_are_known_by_type_and_name(self):
        merged = merge([DEFAULTS_CATALOG, VARIANT])
        # The same name on two types keeps the hint of each.
        self.assertEqual(merged["text"]["sta"].hint, STA_HINT)
        self.assertTrue(merged["scrolling-text"]["sta"].hint.startswith("Scrolling background"))
        # A row read with --known keeps the hint first found, and adds its colour and value.
        self.assertEqual(merged["text"]["sta"].green, ["defaults"])
        self.assertEqual(merged["text"]["sta"].black, ["choice 2"])
        self.assertEqual(merged["text"]["sta"].values, ["solid color", "image"])
        self.assertNotIn("type", merged["text"])
        self.assertIn(("text", "pic"), known_rows(VARIANT))
        self.assertNotIn(("text", "sta"), known_rows(VARIANT))


class CompareTest(unittest.TestCase):

    def setUp(self):
        self.merged = merge([DEFAULTS_CATALOG, VARIANT])
        self.comparison = compare(self.merged, DEFAULTS_CATALOG, DEFAULTS)

    def test_attributes_never_shown_and_not_listed(self):
        self.assertEqual(self.comparison.never_shown["text"], ["aph"])
        # A type with no catalogued component showed none of its attributes.
        self.assertEqual(self.comparison.never_shown["timer"], ["tim"])
        self.assertNotIn("scrolling-text", self.comparison.not_in_defaults)

    def test_an_attribute_shown_in_both_colours(self):
        self.assertEqual(list(self.comparison.both_colours["text"]), ["sta"])

    def test_defaults_that_differ(self):
        # sta shows "solid color", choice 1, as stored; w is placement, left out.
        self.assertEqual(self.comparison.different_defaults, {"text": [("pco", "0", 63488)]})

    def test_the_panels_ways_of_showing_values(self):
        catalog = {"variant": "defaults", "objects": [
            {"page": "page0", "component": "g0", "type": SCROLLING, "attributes": [
                _row("pic", "(null)", "Background image", True),
                _row("txt", "(null)", "Text", True),
                _row("key", "None", "Keyboard", False),
                _row("val", "-1", "Value", True),
                _row("dir", "Right to Left", "Direction:0-Left to Right;1-Right to Left", True),
                _row("tim", "(null)", "Scrolling period", True)]}]}
        defaults = {"scrolling-text": {"attributes": {
            "pic": 65535, "txt": "", "key": 255, "val": 4294967295, "dir": "\x01", "tim": 150}}}
        found = compare(merge([catalog]), catalog, defaults).different_defaults
        # Each is the stored value shown the panel's way, but a period of 150 is no "(null)".
        self.assertEqual(found, {"scrolling-text": [("tim", "(null)", 150)]})

    def test_the_report_names_each_finding(self):
        report = report_markdown(self.merged, self.comparison)
        self.assertIn("- text: `aph`", report)
        self.assertIn("- text `sta`: green under defaults; black under choice 2", report)
        self.assertIn("- text `pco`: the Editor shows '0', nxwright stores 63488", report)


class CopiedHintTest(unittest.TestCase):

    def test_a_description_equal_to_a_hint_is_flagged(self):
        merged = merge([DEFAULTS_CATALOG])
        written = {("text", "sta"): "background FILL", ("text", "pco"): "Font color.",
                   ("text", "w"): "How wide the text is, in pixels."}

        def describe(name, attribute):
            text = written.get((name, attribute))
            return None if text is None else _Described(text)
        # The first equals sta's hint without its choices; the second, pco's hint.
        self.assertEqual(sorted(copied_hints(merged, describe)), [("text", "pco"), ("text", "sta")])


class _Described:
    """Stands for an AttributeDescription: only its description is used."""
    def __init__(self, description):
        self.description = description


class VariantTest(unittest.TestCase):

    def test_settings_of_a_choice(self):
        merged = merge([DEFAULTS_CATALOG])
        self.assertEqual(variant_settings(merged, DEFAULTS_CATALOG, 2), {"t0": {"sta": 2}})
        self.assertEqual(variant_settings(merged, DEFAULTS_CATALOG, 0),
                         {"t0": {"sta": 0}, "g0": {"sta": 0}})
        self.assertEqual(most_choices(merged), 3)
        self.assertEqual(most_choices({"text": {"w": Seen(hint="Width")}}), -1)

    def test_values_set_in_a_dump_as_they_are_stored(self):
        # A one-byte string takes the choice's byte; a longer string, or a
        # text, is no choice; a width suffix stays.
        page = ('object 3 g0\n  dir = "\\x01"\n  txt = "newtxt"\n  tim:u16 = 150\n'
                'object 4 data0\n  dir = "head0^head1"\n')
        settings = {"g0": {"dir": 2, "txt": 2, "tim": 2}, "data0": {"dir": 2}}
        self.assertEqual(with_values(page, settings),
                         'object 3 g0\n  dir = "\\x02"\n  txt = "newtxt"\n  tim:u16 = 2\n'
                         'object 4 data0\n  dir = "head0^head1"\n')

    def test_values_set_in_a_dump(self):
        page = ("page page0\n\nobject 1 t0\n  type = 116\n  sta = 1\n  txt = \"sta = 1\"\n"
                "\nobject 2 g0\n  sta = 1\n")
        self.assertEqual(with_values(page, {"t0": {"sta": 2, "pic": 0}}),
                         page.replace("t0\n  type = 116\n  sta = 1", "t0\n  type = 116\n  sta = 2"))


if __name__ == "__main__":
    unittest.main()
