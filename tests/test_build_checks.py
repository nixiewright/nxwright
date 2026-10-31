"""The build refuses what the Editor would refuse: names longer than the Editor
keeps, texts longer than their field, code that names components or pages
that do not exist, a goto without its label, and an assignment to an
attribute code cannot change."""
from pathlib import Path
import re
import tomllib
import unittest

import tomli_w

from nxwright import NxwrightError
from nxwright.language.code_lines import first_word
from nxwright.project.editor_language import EDITOR_COMMANDS, SERIES_LACKED_COMMANDS
from nxwright.project.project_writer import ProjectWriter
from nxwright.source.device_keys import DEVICE_KEYS
from nxwright.source.source_folder import export_dump, switch_to_nxlang
from nxwright.testing import SourceFolderRunner
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase


def add_component(page_file: Path, name: str, text: str = None, limit: int = None):
    """Adds a text component to a page file."""
    lines = '\n[[component]]\nname = "%s"\ntype = "text"\nx = 0\ny = 0\nw = 100\nh = 30\n' % name
    if text is not None:
        lines += 'txt = "%s"\n' % text
    if limit is not None:
        lines += "txt_maxl = %d\n" % limit
    with open(page_file, "a", encoding="utf-8", newline="\n") as file:
        file.write(lines)


class MalformedPageFileTest(SourceFolderTestCase):
    """The build reads every page file's names before it builds any page, so a
    malformed page file must still stop it with the page file's own error."""

    def test_a_page_that_is_not_a_table(self):
        (self.source / "pages" / "second.page.toml").write_text('page = "x"\n', encoding="utf-8")
        self.assert_export_refused(r"second\.page\.toml has no \[page\] table")

    def test_components_that_are_not_tables(self):
        edit_text(self.source / "pages" / "second.page.toml", "[page]", "component = 5\n\n[page]")
        self.assert_export_refused(r"second\.page\.toml holds only \[page\] and \[\[component\]\] tables")


class SourceFolderLimitTest(SourceFolderTestCase):

    def add_text_component(self, name: str, text: str, limit: int = None):
        add_component(self.source / "pages" / "first.page.toml", name, text, limit)

    def test_a_name_longer_than_the_editor_keeps(self):
        self.add_text_component("abcdefghijklmno", "x")
        self.assert_export_refused(r"first\.page\.toml: component abcdefghijklmno: its name has 15 bytes; "
                                   r"the Nextion Editor keeps 14")

    def test_names_the_editor_refuses(self):
        # The Editor says "Illegal name" as it opens such a project, whatever
        # the component's type: its system variables and its colours.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for name in ("audio0", "dim", "eq9", "scache", "bcpu", "aph", "BLACK"):
            with self.subTest(name=name):
                self.add_text_component(name, "x")
                self.assert_export_refused(r"first\.page\.toml: component %s: the Nextion Editor "
                                           r"refuses this name, saying \"Illegal name\"" % name)
                page_file.write_bytes(page)

    def test_a_name_that_starts_with_a_digit(self):
        # The Nextion Editor refused a project with such a component, or such
        # a page, as it opened it, each probed alone.
        self.add_text_component("1t", "x")
        self.assert_export_refused(r"first\.page\.toml: component 1t: the Nextion Editor refuses "
                                   r"a name that starts with a digit, saying \"First character "
                                   r"of a Name can not be number\"")

    def test_a_page_name_that_starts_with_a_digit(self):
        pages = self.source / "pages"
        (pages / "second.page.toml").rename(pages / "2nd.page.toml")
        (pages / "second.nx").rename(pages / "2nd.nx")
        for path in (self.source / "app.toml", pages / "2nd.page.toml"):
            path.write_text(path.read_text(encoding="utf-8").replace('"second"', '"2nd"'),
                            encoding="utf-8")
        self.assert_export_refused(r"2nd\.page\.toml: page 2nd: the Nextion Editor refuses a "
                                   r"name that starts with a digit")

    def test_names_like_them_that_the_editor_takes(self):
        # Matched exactly, case included; and the commands and the keywords
        # are not among them. sys0 to sys2 are not either, but program.nx
        # declares them, and a component of the same name conflicts with its
        # int (EditorCommandTest).
        for name in ("DIM", "black", "dim1", "rtc7", "eqlb", "page", "if"):
            self.add_text_component(name, "x")
        export_dump(self.source, self.folder / "again")

    def test_a_page_name_the_editor_refuses(self):
        pages = self.source / "pages"
        (pages / "second.page.toml").rename(pages / "dim.page.toml")
        (pages / "second.nx").rename(pages / "dim.nx")
        for path in (self.source / "app.toml", pages / "dim.page.toml"):
            path.write_text(path.read_text(encoding="utf-8").replace('"second"', '"dim"'),
                            encoding="utf-8")
        self.assert_export_refused(r"dim\.page\.toml: page dim: the Nextion Editor refuses this "
                                   r"name, saying \"Illegal name\"")

    def test_a_name_of_14_bytes(self):
        self.add_text_component("abcdefghijklmn", "x")
        export_dump(self.source, self.folder / "again")

    def test_a_text_longer_than_its_field(self):
        # A text component's field holds 10 bytes unless txt_maxl says otherwise.
        self.add_text_component("t0", "abcdefghijk")
        self.assert_export_refused(r"first\.page\.toml: component t0: its txt has 11 bytes; "
                                   r"its txt_maxl is 10")

    def test_a_text_that_fits_its_field(self):
        self.add_text_component("t0", "abcdefghijk", 11)
        export_dump(self.source, self.folder / "again")

    def test_an_attribute_longer_than_its_m(self):
        # An attribute `X_m` holds the most bytes `X` takes, as txt_maxl does a
        # txt's: the Editor refused to compile an external picture's path past
        # its path_m, saying "The length exceeds the maximum value".
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "xp0"\ntype = "external-picture"\nx = 0\ny = 0\n'
                       'w = 50\nh = 50\npath = "sd0/abcdefghij.xi"\npath_m = 8\n')
        self.assert_export_refused(r"first\.page\.toml: component xp0: its path has 17 bytes; "
                                   r"its path_m is 8")
        edit_text(self.source / "pages" / "first.page.toml", "path_m = 8", "path_m = 17")
        export_dump(self.source, self.folder / "again")

    def test_bounds_the_editor_does_not_check(self):
        # The Editor compiled a data record's format and dir past their _m,
        # up to a limit (test_a_data_records_texts_past_what_their_bound_holds),
        # and the screen kept all of each. It compiled a video's or a sound's
        # path past its path_m while its from was 0, an internal file, and
        # refused it with from 1, a file on an SD card.
        page_file = self.source / "pages" / "first.page.toml"
        with open(page_file, "a", encoding="utf-8", newline="\n") as file:
            file.write('\n[[component]]\nname = "d0"\ntype = "data-record"\nx = 0\ny = 0\n'
                       'w = 200\nh = 100\nformat = "100^100^100"\nformat_m = 8\n'
                       'dir = "aa^bb^cc^dd"\ndir_m = 8\n'
                       '\n[[component]]\nname = "vd0"\ntype = "video"\nx = 0\ny = 100\nw = 50\n'
                       'h = 50\npath = "sd0/abcdefghij.video"\npath_m = 8\n'
                       '\n[[component]]\nname = "au0"\ntype = "audio"\n'
                       'path = "sd0/abcdefghij.wav"\npath_m = 8\n')
        export_dump(self.source, self.folder / "built")
        page = page_file.read_bytes()
        for name, kind, length in (("vd0", "video", 20), ("au0", "audio", 18)):
            with self.subTest(kind=kind):
                edit_text(page_file, 'type = "%s"\n' % kind, 'type = "%s"\nfrom = 1\n' % kind)
                self.assert_export_refused(r"first\.page\.toml: component %s: its path has %d "
                                           r"bytes; its path_m is 8" % (name, length))
                page_file.write_bytes(page)

    def test_a_data_records_texts_past_what_their_bound_holds(self):
        # The Editor's compile took a data record's format or dir up to its
        # bound plus 1, rounded up to a multiple of 4, less 1. It refused one
        # byte more, saying "The length exceeds the maximum value".
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()

        def with_record(attribute: str, length: int, bound: int):
            """The page as it was, with a data record d0 of a text `length`
            bytes long for `attribute`, bounded by `bound`."""
            page_file.write_bytes(page)
            with open(page_file, "a", encoding="utf-8", newline="\n") as file:
                file.write('\n[[component]]\nname = "d0"\ntype = "data-record"\nx = 0\ny = 0\n'
                           'w = 200\nh = 100\n%s = "%s"\n%s_m = %d\n'
                           % (attribute, "a" * length, attribute, bound))
        for attribute in ("format", "dir"):
            for bound, most in ((8, 11), (12, 15)):
                with self.subTest(attribute=attribute, bound=bound):
                    with_record(attribute, most, bound)
                    export_dump(self.source, self.folder / ("%s-%d" % (attribute, bound)))
                    with_record(attribute, most + 1, bound)
                    self.assert_export_refused(
                        r"first\.page\.toml: component d0: its %s has %d bytes; its %s_m of %d "
                        r"holds %d at most, and the Nextion Editor refuses more \(\"The length "
                        r"exceeds the maximum value\"\)" % (attribute, most + 1, attribute, bound,
                                                           most))

    def test_a_text_of_a_buttons_style(self):
        # The Editor refuses a text of style 4, 3D auto, which only a button
        # has: "styles.text4.style Out of range". A text's go from 0 to 3.
        self.add_text_component("t0", "x")
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write("style = 4\n")
        self.assert_export_refused(r"first\.page\.toml, object 1: style must be from 0 to 3")
        edit_text(self.source / "pages" / "first.page.toml", "style = 4", "style = 3")
        export_dump(self.source, self.folder / "again")

    def test_a_selects_sunken_style(self):
        # The Editor refused a select's style of 2, sunken, on the Edge and
        # the Intelligent alike ("Out of range"). The other series have no
        # select.
        page_file = self.source / "pages" / "first.page.toml"
        with open(page_file, "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "s0"\ntype = "select"\nx = 0\ny = 0\n'
                       'w = 120\nh = 120\nstyle = 2\n')
        self.assert_export_refused(r"first\.page\.toml, object 1: style must be from 0 to 1")
        edit_text(page_file, "style = 2", "style = 1")
        export_dump(self.source, self.folder / "again")

    def test_a_component_narrower_or_lower_than_2(self):
        # The Editor says "Width can not be less than 2", then "Height can not
        # be less than 2", as it opens such a project. It then sets the side
        # back to its type's default, as it did for every type with a place,
        # which the build would not match.
        self.add_text_component("t0", "x")
        edit_text(self.source / "pages" / "first.page.toml", 'h = 30\ntxt = "x"', 'h = 1\ntxt = "x"')
        self.assert_export_refused(r"first\.page\.toml, object 1: component t0 is 100 by 1; "
                                   r"the Nextion Editor says \"Height can not be less than 2\" as "
                                   r"it opens the project, and sets the height back to 30, its "
                                   r"type's default; make it at least 2 by 2")
        edit_text(self.source / "pages" / "first.page.toml", 'h = 1\ntxt = "x"', 'h = 2\ntxt = "x"')
        export_dump(self.source, self.folder / "again")

    def test_a_component_too_small_in_a_table_of_every_attribute(self):
        # A table marked defaults = false lists every attribute; the check holds alike.
        defaults = tomllib.loads((self.source / "defaults.toml").read_text(encoding="utf-8"))
        values = dict(defaults["hotspot"]["attributes"], x=0, y=0, w=0, h=0)
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "zone"\ntype = "hotspot"\ndefaults = false\n'
                       + tomli_w.dumps(values))
        self.assert_export_refused(r"first\.page\.toml, object 1: component zone is 0 by 0; "
                                   r"the Nextion Editor says \"Width can not be less than 2\" and "
                                   r"\"Height can not be less than 2\" as it opens the project, "
                                   r"and sets them back to 60 by 60, its type's default; make it "
                                   r"at least 2 by 2")

    def test_a_gauge_past_360_degrees(self):
        # The Editor refuses a gauge whose val is past 360: "page0.g14.valOut
        # of range".
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "dial"\ntype = "gauge"\nx = 0\ny = 0\nw = 100\n'
                       'h = 100\nval = 361\n')
        self.assert_export_refused(r"first\.page\.toml, object 1: val must be from 0 to 360")
        edit_text(self.source / "pages" / "first.page.toml", "val = 361", "val = 360")
        export_dump(self.source, self.folder / "again")

    def test_digits_a_waveforms_way_and_aph_past_what_the_editor_takes(self):
        # The Nextion Editor 1.68.2 refused each of these, "Out of range": an
        # xfloat's vvs1 past 8 and vvs0 past 10, a waveform's dir past 2, and
        # an aph past 127, on a text, a button, a number, and a picture alike.
        # It took each at the bound.
        page_file = self.source / "pages" / "first.page.toml"
        original = page_file.read_text(encoding="utf-8")
        place = "x = 0\ny = 0\nw = 100\nh = 30\n"
        cases = (("xfloat", "vvs1 = %d\n", 9, 8), ("xfloat", "vvs0 = %d\n", 11, 10),
                 ("waveform", 'dir = "\\u%04x"\n', 3, 2), ("text", "aph = %d\n", 128, 127),
                 ("button", "aph = %d\n", 128, 127), ("number", "aph = %d\n", 128, 127))
        for kind, line, past, bound in cases:
            with self.subTest(kind=kind, line=line % past):
                page_file.write_text(original + '\n[[component]]\nname = "c0"\ntype = "%s"\n'
                                     % kind + place + line % past, encoding="utf-8")
                attribute = line.split(" ")[0]
                self.assert_export_refused(r"first\.page\.toml, object 1: %s must be from 0 to %d"
                                           % (attribute, bound))
        page_file.write_text(original + "".join(
            '\n[[component]]\nname = "c%d"\ntype = "%s"\n' % (number, kind) + place + line % bound
            for number, (kind, line, _, bound) in enumerate(cases)), encoding="utf-8")
        export_dump(self.source, self.folder / "again")

    def test_a_gauge_needle_wider_than_1024(self):
        # The Editor refuses a gauge whose left is past 1024, on gauges 36,
        # 140, and 300 pixels across alike: "page0.g140_1025.leftOut of range".
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "dial"\ntype = "gauge"\nx = 0\ny = 0\nw = 140\n'
                       'h = 140\nleft = 1025\n')
        self.assert_export_refused(r"first\.page\.toml, object 1: left must be from 0 to 1024")
        edit_text(self.source / "pages" / "first.page.toml", "left = 1025", "left = 1024")
        export_dump(self.source, self.folder / "again")

    def test_ranges_of_attributes_the_panel_never_shows(self):
        # The Editor refused each value past its range, "page0.c0.val Out of
        # range" for one; a gauge's wid alike whatever its size. A hotspot's
        # drag, effect, and aph it refused past 1, 8, and 127.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for number, (kind, w, h, attribute, low, high) in enumerate((
                ("button", 100, 50, "val", 0, 1), ("file-browser", 250, 150, "xcen", 0, 2),
                ("combo-box", 150, 40, "drastate", 0, 1), ("gauge", 100, 100, "wid", 1, 20),
                ("hotspot", 100, 50, "drag", 0, 1), ("hotspot", 100, 50, "effect", 0, 8),
                ("hotspot", 100, 50, "aph", 0, 127))):
            for value in (low - 1, high + 1) if low else (high + 1,):
                with self.subTest(kind=kind, value=value):
                    with open(page_file, "a", encoding="utf-8") as file:
                        file.write('\n[[component]]\nname = "c0"\ntype = "%s"\nx = 0\ny = 0\n'
                                   'w = %d\nh = %d\n%s = %d\n' % (kind, w, h, attribute, value))
                    self.assert_export_refused(r"first\.page\.toml, object 1: %s must be from "
                                               r"%d to %d" % (attribute, low, high))
                    edit_text(page_file, "%s = %d" % (attribute, value),
                              "%s = %d" % (attribute, high))
                    export_dump(self.source, self.folder / ("taken%d_%d" % (number, value)))
                    page_file.write_bytes(page)

    def test_a_pages_opacity(self):
        # The Editor refused a page's aph of 128 on every series, the memory
        # probe found (memory_costs.toml); it stores 127.
        page_file = self.source / "pages" / "first.page.toml"
        edit_text(page_file, "vscope = 0", "vscope = 0\naph = 128")
        self.assert_export_refused(r"first\.page\.toml, object 0: aph must be from 0 to 127")
        edit_text(page_file, "aph = 128", "aph = 127")
        export_dump(self.source, self.folder / "taken")

    def test_a_scrolling_texts_period(self):
        # The Editor refuses 79 and 65535 alike: "page0.st0.tim Out of range".
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "st0"\ntype = "scrolling-text"\n'
                       'x = 0\ny = 0\nw = 240\nh = 30\ntim = 79\n')
        for refused, allowed in ((79, 80), (65535, 65534)):
            with self.subTest(tim=refused):
                edit_text(self.source / "pages" / "first.page.toml", "tim = 79", "tim = %d" % refused)
                self.assert_export_refused(r"first\.page\.toml, object 1: tim must be from 80 "
                                           r"to 65534")
                edit_text(self.source / "pages" / "first.page.toml", "tim = %d" % refused,
                          "tim = %d" % allowed)
                export_dump(self.source, self.folder / ("again%d" % allowed))
                edit_text(self.source / "pages" / "first.page.toml", "tim = %d" % allowed,
                          "tim = 79")

    def test_a_keyboard_bound_to_a_component_of_local_scope(self):
        # The Editor refuses both to bind a keyboard to a component of local
        # scope ("Please set vscope to global before binding the on-screen
        # keyboard.") and to make a bound one local.
        self.add_text_component("t0", "x")
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write("key = 2\n")
        self.assert_export_refused(r"first\.page\.toml, object 1: a keyboard is bound \(key 2\), "
                                   r"so vscope must be 1, global, as the Nextion Editor requires")
        edit_text(self.source / "pages" / "first.page.toml", "key = 2\n", "key = 2\nvscope = 1\n")
        export_dump(self.source, self.folder / "again")


class PageCapTest(SourceFolderTestCase):
    """The Editor's compile refuses a page holding more components of some
    kinds than it takes on a page, as "Waveform components exceed maximum in
    page:5" (Editor 1.68.2, on every series that takes the kinds). The build
    refuses it too, naming the first component past the cap."""

    def setUp(self):
        super().setUp()
        self.added = 0

    def add(self, kind: str, count: int):
        """Adds `count` components of type `kind` to the page first, named
        c0, c1, and so on, in the order they are added."""
        placed = "" if kind == "timer" else "x = 0\ny = 0\nw = 100\nh = 30\n"
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for _ in range(count):
                file.write('\n[[component]]\nname = "c%d"\ntype = "%s"\n%s'
                           % (self.added, kind, placed))
                self.added += 1

    def test_waveforms(self):
        self.add("waveform", 5)
        export_dump(self.source, self.folder / "five")
        self.add("waveform", 1)
        self.assert_export_refused(
            r"first\.page\.toml: component c5: the page holds 6 waveforms; the Nextion Editor's "
            r"compile takes 5 on a page, saying \"Waveform components exceed maximum in page:5\"")
        # The page's whole count, still at the first component past the cap.
        self.add("waveform", 2)
        self.assert_export_refused(r"component c5: the page holds 8 waveforms")

    def test_timers_and_scrolling_texts_together(self):
        self.add("timer", 12)
        export_dump(self.source, self.folder / "twelve")
        self.add("scrolling-text", 1)
        self.assert_export_refused(
            r"first\.page\.toml: component c12: the page holds 13 timers and scrolling texts; the "
            r"Nextion Editor's compile takes 12 on a page, saying \"Timer events exceed maximum "
            r"in page:12\"")

    def test_a_mix_of_timers_and_scrolling_texts(self):
        self.add("timer", 6)
        self.add("scrolling-text", 7)
        self.assert_export_refused(r"component c12: the page holds 13 timers and scrolling texts")

    def test_animations_and_videos_together(self):
        self.add("gmov", 15)
        self.add("video", 2)
        self.assert_export_refused(
            r"first\.page\.toml: component c16: the page holds 17 animations and videos; the "
            r"Nextion Editor's compile takes 16 on a page, saying \"Gmov and video components "
            r"exceed maximum in page:16\"")

    def test_the_build_of_a_dump(self):
        # A dump past a cap, as one of a project the Editor saved but cannot
        # compile: a sixth waveform, copied from the fifth.
        self.add("waveform", 5)
        dump = self.folder / "five"
        export_dump(self.source, dump)
        page = dump / "pages" / "00-first.txt"
        text = page.read_text(encoding="utf-8")
        fifth = text[text.index("object 5 c4"):]
        sixth = re.sub(r"\bc4\b", "c5", fifth.replace("object 5 c4", "object 6 c5", 1))
        sixth = re.sub(r"(?m)^  id = 5$", "  id = 6", sixth)
        page.write_text(text.rstrip("\n") + "\n\n" + sixth, encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"pages[/\\]00-first\.txt: component c5: the "
                                                   r"page holds 6 waveforms"):
            ProjectWriter(self.project, dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())


class WriterLimitTest(SourceFolderTestCase):

    def test_nxwright_write_refuses_a_text_longer_than_its_field(self):
        edit_text(self.dump / "pages" / "00-first.txt", '  txt = "hello"\n',
                  '  txt = "hello"\n  txt_maxl = 3\n')
        with self.assertRaisesRegex(NxwrightError, r"pages[/\\]00-first\.txt: page first: its txt "
                                                   r"has 5 bytes; its txt_maxl is 3"):
            ProjectWriter(self.project, self.dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())


class ReferenceTest(SourceFolderTestCase):
    """Editor code in first.down, checked against the names of the small test
    project. setUp adds the down event, t0 on page first, and t1 on page second."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(self.source / "pages" / "first.page.toml", "t0")
        add_component(self.source / "pages" / "second.page.toml", "t1")

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def test_names_that_exist(self):
        # The page's own components, the page itself, another page's
        # components after its name, a command's component, and the forms
        # whose component is chosen at run time. Strings and comments are not read.
        self.write_code('t0.txt="a.b"', "first.bco=0", "second.t1.txt=t0.txt", "vis t0,1",
                        "tsw 255,0", "b[1].txt=p[0].b[2].txt", "sys0=second.bco // nothing.here")
        export_dump(self.source, self.folder / "again")

    def test_an_unknown_component(self):
        self.write_code('t0.txt=""', 't9.txt=""')
        self.assert_export_refused(r"first\.nx line 3: t9 is neither on this page nor a page")

    def test_an_unknown_page(self):
        self.write_code("t0.txt=third.t1.txt")
        self.assert_export_refused(r"first\.nx line 2: third is neither on this page nor a page")

    def test_an_unknown_component_of_another_page(self):
        self.write_code("t0.txt=second.t9.txt")
        self.assert_export_refused(r"first\.nx line 2: page second has no component t9")

    def test_another_pages_component_without_its_page(self):
        self.write_code('t1.txt=""')
        self.assert_export_refused(r"first\.nx line 2: t1 is neither on this page nor a page")

    def test_an_unknown_component_in_a_command(self):
        self.write_code("vis t9,1")
        self.assert_export_refused(r"first\.nx line 2: vis names t9, which is not on this page")

    def test_the_runner_refuses_what_the_build_refuses(self):
        self.write_code('t9.txt=""')
        with self.assertRaisesRegex(NxwrightError, r"line 2: t9 is neither on this page nor a page"):
            SourceFolderRunner(self.source).run("first", [("first", "down")])

    def test_the_runner_does_not_check_code_given_as_text(self):
        # Such as an older version of the page, naming components it no longer has.
        values = SourceFolderRunner(self.source).run("first", [("first", "down")],
                                                     text='on first.down:\n  t9.txt="old"\n')
        self.assertEqual(values["t9.txt"], "old")


class _CodeOnFirstTestCase(SourceFolderTestCase):
    """Code in first.down. setUp adds the down event, and d0, a data record,
    n0, a number, and t0, a text, on page first."""

    def setUp(self):
        super().setUp()
        page = self.source / "pages" / "first.page.toml"
        edit_text(page, "events = []", 'events = ["down"]')
        add_component(page, "t0")
        with open(page, "a", encoding="utf-8", newline="\n") as file:
            for name, kind in (("d0", "data-record"), ("n0", "number")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 40\n'
                           'w = 200\nh = 100\n' % (name, kind))

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")


class DataRecordCallTest(_CodeOnFirstTestCase):
    """A data record's calls. The build refuses those the Editor refused as
    it compiled."""

    def test_the_forms_the_editor_compiles(self):
        # A number where a text goes among them: the screen then adds nothing.
        self.write_code("d0.insert(t0.txt)", 'd0.insert("a^b")', "d0.insert(n0.val)",
                        "d0.insert(5)", "d0.up(t0.txt,n0.val)", "d0.up(5,0)",
                        "d0.delete(n0.val,1)", "d0.delete(n0.val+1,1)", "d0.clear()")
        export_dump(self.source, self.folder / "again")

    def test_the_forms_the_editor_refuses(self):
        cases = [("d0.delete(0)", r"d0\.delete takes 2 arguments"),
                 ("d0.clear(1)", r"d0\.clear takes no arguments"),
                 ("d0.insert()", r"d0\.insert takes 1 argument"),
                 ('d0.up("x","1")', r"argument 2 of d0\.up is a number, not a text"),
                 ("d0.delete(t0.txt,1)", r"argument 1 of d0\.delete is a number, not a text"),
                 ('d0.insert(t0.txt+"^")', r"argument 1 of d0\.insert is one text or number")]
        for number, (line, message) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: " + message):
                    export_dump(self.source, self.folder / ("refused%d" % number))


class FileStreamCallTest(_CodeOnFirstTestCase):
    """A file stream's calls, refused given another number of arguments than
    each method takes. The Nextion Editor 1.68.2 refused them as it compiled
    ("Invalid number of arguments"). Page first holds fs0, a file stream."""

    def setUp(self):
        super().setUp()
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "fs0"\ntype = "file-stream"\n')

    def test_the_forms_the_nextion_editor_compiles(self):
        self.write_code('fs0.open("sd0/a.txt")', "fs0.open(t0.txt)", "fs0.read(t0.txt,0,3)",
                        "fs0.read(t0.txt,n0.val+1,2)", "fs0.write(t0.txt,0,3)", "fs0.close()",
                        'fs0.find("sd0/a.txt")')
        export_dump(self.source, self.folder / "again")

    def test_another_number_of_arguments_is_refused(self):
        cases = [("fs0.open()", "fs0.open takes 1 argument"),
                 ('fs0.open("sd0/a.txt","b")', "fs0.open takes 1 argument"),
                 ("fs0.read(t0.txt,0)", "fs0.read takes 3 arguments"),
                 ("fs0.read(t0.txt,0,1,2)", "fs0.read takes 3 arguments"),
                 ("fs0.write(t0.txt)", "fs0.write takes 3 arguments"),
                 ("fs0.write(t0.txt,0,1,2)", "fs0.write takes 3 arguments"),
                 ("fs0.close(1)", "fs0.close takes no arguments"),
                 ("fs0.find()", "fs0.find takes 1 argument"),
                 ('fs0.find("sd0/a.txt",n0.val)', "fs0.find takes 1 argument")]
        for number, (line, message) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: %s, as the "
                                            r"Nextion Editor compiles it" % re.escape(message)):
                    export_dump(self.source, self.folder / ("refused%d" % number))

    def test_in_nxlang(self):
        # nxlang passes a file stream's calls through as written.
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  fs0.read(t0.txt, 0)\n",
                                                         encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: fs0\.read takes 3 "
                                                   r"arguments"):
            export_dump(self.source, self.folder / "refused")


class CommandArgumentTest(_CodeOnFirstTestCase):
    """The commands whose first argument the Editor takes as one operand
    alone, refusing arithmetic there as it compiles ("Invalid Variables"),
    where it takes arithmetic in their other numbers."""

    def test_the_forms_the_editor_compiles(self):
        # A space by a comma goes before the check, as the build drops it.
        self.write_code("get n0.val", 'print "a"', "prints t0.txt ,n0.val+1",
                        "covx 1234,t0.txt,n0.val-3,n0.val-4", 'newfile "sd0/a.txt",n0.val+1')
        export_dump(self.source, self.folder / "again")

    def test_arithmetic_in_the_first_argument_is_refused(self):
        for number, line in enumerate(("get n0.val+1", "print n0.val+1", "prints n0.val+1,0",
                                       "covx n0.val+1,t0.txt,0,0", 'print "a"+t0.txt')):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line 2: %s: the Nextion Editor takes one text "
                                       r"or number as the first argument of %s, not arithmetic or "
                                       r"texts joined"
                        % (re.escape(line), line.split()[0])):
                    export_dump(self.source, self.folder / ("refused%d" % number))

    def test_texts_joined_as_xstr_s_text_are_refused(self):
        # The Editor's compile refused each ("Invalid Variables"), and
        # compiled a txt or a text alone there.
        head = "xstr 0,0,100,30,0,RED,WHITE,0,0,1,"
        for number, text in enumerate(('"a"+"b"', 't0.txt+"b"', '"a"+t0.txt+"c"', "sys0+1",
                                       "n0.val*2")):
            with self.subTest(text=text):
                self.write_code(head + text)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line 2: %s: .*\(\"Invalid Variables\"\)"
                        % re.escape(head + text)):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code(head + "t0.txt", head + '"a+b"')
        export_dump(self.source, self.folder / "built")

    def test_nxlang_computes_xstr_s_text_first(self):
        switch_to_nxlang(self.source)
        self.write_code('xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a"+"b"')
        export_dump(self.source, self.folder / "built")
        page = next((self.folder / "built" / "pages").glob("*-first.txt"))
        self.assertRegex(page.read_text(encoding="utf-8"),
                         r'\| (__s\w+\.txt)="a"\+"b"\n\s*\| xstr 0,0,100,30,0,RED,WHITE,0,0,1,\1\n')

    def test_nxlang_computes_it_first(self):
        switch_to_nxlang(self.source)
        self.write_code("get n0.val+1")
        export_dump(self.source, self.folder / "built")
        page = next((self.folder / "built" / "pages").glob("*-first.txt"))
        self.assertRegex(page.read_text(encoding="utf-8"),
                         r"\| (__g\w+)=n0\.val\+1\n\s*\| get \1\n")


class FullyListedComponentTest(_CodeOnFirstTestCase):
    """Code naming a component whose page file lists every attribute, as the
    Nextion Editor compiled it: by the component's type. It makes such a
    component its type's as it opens the project, filling in what the table
    leaves out and dropping what its type lacks."""

    def test_its_code_is_checked_by_its_type(self):
        defaults = tomllib.loads((self.source / "defaults.toml").read_text(encoding="utf-8"))
        values = dict(defaults["text"]["attributes"], x=0, y=150, w=100, h=30)
        lacking = {key: value for key, value in values.items() if key != "pco"}
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for name, table in (("lack", lacking), ("extra", dict(values, val=0))):
                file.write('\n[[component]]\nname = "%s"\ntype = "text"\ndefaults = false\n'
                           % name + tomli_w.dumps(table))
        # An attribute its type has, which its table leaves out.
        self.write_code("lack.pco=63488", "sys0=lack.pco")
        export_dump(self.source, self.folder / "taken")
        # One its type lacks, which its table lists.
        self.write_code("extra.val=5")
        self.assert_export_refused(r"first\.nx line 2: extra\.val=5: extra is a text, which "
                                   r"has no val")


class CompileRefusalTest(_CodeOnFirstTestCase):
    """Lines the Editor 1.68.2's compile refused, each alone in an event,
    with its words; and lines like them it compiled. Besides t0, n0, and d0,
    page first holds va0, a variable of a text (`sta` 1), va1, one of a
    number, st0, a scrolling text, vd0 and au0, a video and a sound playing
    an internal file (`from` 0), vd1, a video playing a file of an SD card
    (`from` 1), and gm0 and gm1, animations of `from` 0 and 1."""

    def setUp(self):
        super().setUp()
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "va0"\ntype = "variable"\nsta = 1\n'
                       '\n[[component]]\nname = "va1"\ntype = "variable"\nsta = 0\n'
                       '\n[[component]]\nname = "st0"\ntype = "scrolling-text"\nx = 0\n'
                       'y = 150\nw = 200\nh = 30\n'
                       '\n[[component]]\nname = "vd0"\ntype = "video"\nx = 0\ny = 200\nw = 50\n'
                       'h = 50\n\n[[component]]\nname = "au0"\ntype = "audio"\n'
                       '\n[[component]]\nname = "vd1"\ntype = "video"\nx = 60\ny = 200\nw = 50\n'
                       'h = 50\nfrom = 1\n'
                       '\n[[component]]\nname = "gm0"\ntype = "gmov"\nx = 120\ny = 200\nw = 50\n'
                       'h = 50\n\n[[component]]\nname = "gm1"\ntype = "gmov"\nx = 180\ny = 200\n'
                       'w = 50\nh = 50\nfrom = 1\n')

    REFUSED = {
        "Assignment operation failed": [
            "n0.val=t0.txt", 'n0.val="a"', "t0.txt=5", 't0.pco="a"', "t0.pco=t0.txt",
            't0.font="a"', "t0.txt=n0.val", 'sys0="a"', "va0.txt=5", "t0.txt=0X10"],
        "Invalid variable operation": [
            "t0.txt*=2", "n0.val+=t0.txt", "t0.txt+=5", "n0.val-=t0.txt", "t0.txt=t0.txt+5",
            "n0.val=n0.val+t0.txt", "n0.val=t0.txt+t0.txt"],
        "Improper use of escape characters": [
            r't0.txt="a\q"', r't0.txt="a\nb"', r't0.txt="a\tb"', r'print "a\qb"',
            r'newfile "sd0\a.txt",10'],
        "Invalid Variables": ['va0.val="a"', "n0.val=va0.val", 'va1.txt="a"',
                              "t0.txt=va1.txt", 'vd0.path="sd0/a.video"', "t0.txt=au0.path",
                              "gm1.vid=0", "sys0=gm1.vid", "sys0=vd1.vid"],
    }

    def test_the_lines_the_editor_refuses(self):
        number = 0
        for words, lines in self.REFUSED.items():
            for line in lines:
                with self.subTest(line=line):
                    self.write_code(line)
                    number += 1
                    with self.assertRaisesRegex(
                            NxwrightError, r"first\.nx line 2: %s: .*\(\"%s\"\)"
                            % (re.escape(line), re.escape(words))):
                        export_dump(self.source, self.folder / ("refused%d" % number))

    def test_another_pages_variable_and_a_types_default(self):
        # A variable of page second, named through its page; and one whose
        # page file leaves its `sta` out, its type's default, 0: a number.
        with open(self.source / "pages" / "second.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "vs"\ntype = "variable"\nvscope = 1\nsta = 1\n')
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "vd"\ntype = "variable"\n')
        for number, line in enumerate(("n0.val=second.vs.val", 'vd.txt="a"')):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: .*\(\"Invalid "
                                                           r"Variables\"\)"):
                    export_dump(self.source, self.folder / ("refused%d" % number))

    def test_a_text_taken_from_a_text_is_left_to_the_editor(self):
        # No probe tried it: the build takes it.
        self.write_code("t0.txt=t0.txt-t0.txt")
        export_dump(self.source, self.folder / "built")

    def test_a_command_given_another_number_of_arguments(self):
        # Each of these the Editor's compile refused; its numbers are the
        # vendor's (COMMAND_PARAMETERS).
        for number, line in enumerate(("cls 1,2", "fill 0,0,10", "prints t0.txt", "print t0.txt,0",
                                       "get 1,2", "click t0", "xstr 0,0,50,20,0,0,63488,0,0,1",
                                       "lcd_dev fffb,0002,0000,0020", "setbrush 1,2",
                                       "draw_h 1,2", 'rdfile "sd0/a.txt",0,1',
                                       'rdfile "sd0/a.txt",0,1,0,1', "twfile",
                                       'twfile "sd0/a.txt"', 'twfile "sd0/a.txt",5,6',
                                       "crcrest", "crcrest 1", "crcputs t0.txt,0,1",
                                       "crcputu 0", "rest 1", "touch_j 1", "code_c 1",
                                       "i 1,2", "beepset 1", "meup 1,2,3", "gets 1",
                                       "cfguart 1,2,3", "cuts 1,2", "xnum 1,2")):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line 2: %s: .*\(\"Invalid number of "
                        r"arguments\"\)" % re.escape(line)):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # Its own number, a quoted comma within one, a command the table
        # lacks, which takes any number, and commands that take none.
        self.write_code("cls 1", 'print "a,b"', "crcputh 0A 0B", "crcrest 1,0xffff",
                        'rdfile "sd0/a.txt",0,1,0', 'twfile "sd0/a.txt",5', "rest", "touch_j",
                        "code_c", "i 1,2,3,4", "beepset 1,2", "meup 1,2", "gets 1,2",
                        "cfguart 1,2,3,4", "cuts 1,2,3,4,5,6,7", "xnum 1,2,3,4,5,6,7,8,9,10")
        export_dump(self.source, self.folder / "built")

    def test_nxlang_writes_such_texts_another_way(self):
        # A condition's text that ends in an escaped backslash goes into a
        # text temporary first, and a for whose head holds a text with a
        # semicolon becomes its start and a while.
        switch_to_nxlang(self.source)
        self.write_code(r'if (t0.txt == "a\\") {', "  n0.val = 1", "}",
                        'for (n0.val = 0; t0.txt != "a;b"; n0.val++) {', '  t0.txt = "a;b"', "}")
        export_dump(self.source, self.folder / "built")
        page = next((self.folder / "built" / "pages").glob("*-first.txt")).read_text(
            encoding="utf-8")
        self.assertRegex(page, r'\| (__s\w+\.txt)="a\\\\"\n\s*\| if\(t0\.txt==\1\)\n')
        self.assertIn('| while(t0.txt!="a;b")', page)
        self.assertNotIn("| for(", page)

    def test_a_text_holding_a_semicolon_outside_a_for_s_head(self):
        # The Nextion Editor compiled each: the text in a while's and an
        # if's condition, and outside a head.
        self.write_code('while(t0.txt!="a;b")', "{", "}", 'if(t0.txt=="a;b")', "{", "}",
                        't0.txt="a;b"')
        export_dump(self.source, self.folder / "built")

    def test_a_value_or_a_head_the_editor_refuses(self):
        # As the Nextion Editor's compile refused each, in its words.
        cases = [("n0.val==2", "Invalid Variables"), ("n0.val=2+", "Invalid Variables"),
                 ("n0.val=+2", "Invalid Variables"), ("n0.val=2++3", "Invalid Variables"),
                 ("n0.val=-n0.val", "Invalid Variables"), ("n0.val=(1+2)", "Invalid Variables"),
                 ("n0.val=1.5", "Invalid Variables"), ("n0.val=2*-n0.val", "Invalid Variables"),
                 ("n0.val=", "Invalid command"),
                 ("if(n0.val==1", 'SYNTAX ERROR:must end with ")"'),
                 ("while(n0.val<3", 'SYNTAX ERROR:must end with ")"'),
                 ("for(n0.val=0;n0.val<3;n0.val++", "SYNTAX ERROR:for"),
                 # A text holding a semicolon, in each part of a for's head.
                 ('for(n0.val=0;t0.txt!="a;b";n0.val++)', "SYNTAX ERROR:for"),
                 ('for(t0.txt="a;b";n0.val<1;n0.val++)', "SYNTAX ERROR:for"),
                 ('for(n0.val=0;n0.val<1;t0.txt="a;b")', "SYNTAX ERROR:for")]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                block = [line, "{", "}"] if "(" in line and not line.startswith("n0") else [line]
                self.write_code(*block)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: %s: .*\(\"%s\"\)$"
                                            % (re.escape(line), re.escape(words))):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # An else if's head too, refused alike.
        self.write_code("if(n0.val==1)", "{", "}else if(n0.val==2", "{", "}")
        with self.assertRaisesRegex(NxwrightError, r'first\.nx line 4: \}else if\(n0\.val==2: .*'
                                    r'\("SYNTAX ERROR:must end with "\)""\)$'):
            export_dump(self.source, self.folder / "refused-else")
        # What the Nextion Editor compiled, a hexadecimal number written 0X too.
        self.write_code("n0.val=-2", "n0.val=2*-16", "n0.val=5--16", "n0.val=n0.val+-2",
                        "n0.val=0X10",
                        't0.txt=t0.txt+"a"', "if(n0.val==1&&n0.val!=2)", "{", "}",
                        "while(n0.val<3)", "{", "n0.val++", "}",
                        "for(n0.val=0;n0.val<3;n0.val++)", "{", "}")
        export_dump(self.source, self.folder / "built")

    def test_a_name_alone_the_editor_does_not_know(self):
        # As the Nextion Editor's compile refused each, saying "Invalid
        # Variables:" and the name: a name alone in a value, a condition, an
        # index, or the first argument of get, print, prints, or covx, that is
        # no int of program.nx, no system variable, and no colour. A
        # component's and a page's names alone are refused too, and so is a
        # colour in small letters.
        cases = [("n0.val=abc+1", "the Nextion Editor knows no abc"),
                 ("n0.val=abc", "knows no abc"), ("n0.val=n0.val+abc", "knows no abc"),
                 ("n0.val+=abc", "knows no abc"), ("t0.txt=abc", "knows no abc"),
                 ("n0.val=b[abc].val", "knows no abc"), ("b[abc].val=1", "knows no abc"),
                 ("if(abc==1)", "knows no abc"), ("while(abc<1)", "knows no abc"),
                 ("for(sys0=0;sys0<abc;sys0++)", "knows no abc"), ("get abc", "knows no abc"),
                 ("print abc", "knows no abc"), ("prints abc,0", "knows no abc"),
                 ("covx abc,t0.txt,0,0", "knows no abc"), ("n0.val=val", "knows no val"),
                 ("n0.val=n0+1", "n0 names a component, which the Nextion Editor refuses "
                                 "alone: name one of its attributes"),
                 ("n0.val=first+1", "first names a page, which"),
                 ("n0.val=red", "knows no red, though it knows RED")]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                block = [line, "{", "}"] if line[:2] in ("if", "wh", "fo") else [line]
                self.write_code(*block)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: %s: .*%s.*"
                                            r"\(\"Invalid Variables\"\)$"
                                            % (re.escape(line), re.escape(words))):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code("if(sys0==1)", "{", "}else if(abc==1)", "{", "}")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx line 4: \}else if\(abc==1\): "
                                                   r"the Nextion Editor knows no abc"):
            export_dump(self.source, self.folder / "refused-else")
        # What the Nextion Editor compiled: system variables, an int of
        # program.nx, colours in capitals, and a system variable as an index.
        edit_text(self.source / "program.nx", "int sys0=0,sys1=0,sys2=0",
                  "int sys0=0,sys1=0,sys2=0\nint myint=0")
        self.write_code("n0.val=sys0+dim", "n0.val=myint+1", "n0.val=RED+1",
                        "n0.val=GRAY+WHITE", "n0.val=b[sys0].val", "covx sys0,t0.txt,0,0",
                        "if(myint==1)", "{", "}", 't0.txt="abc"')
        export_dump(self.source, self.folder / "built")

    def test_an_escape_in_a_condition(self):
        self.write_code(r'if(t0.txt=="a\qb")', "{", "n0.val=1", "}")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: .*Improper use of "
                                                   r"escape characters"):
            export_dump(self.source, self.folder / "refused")

    def test_a_text_ending_in_an_escaped_backslash_in_a_condition(self):
        # Each the Editor's compile refused ("SYNTAX ERROR"): in the head of
        # an if, an else if, or a while, and in a for's condition, the text
        # first or second, two escaped backslashes, and one before `&&`.
        body = ["{", "n0.val=1", "}"]
        cases = [[r'if(t0.txt=="\\")'] + body, [r'if(t0.txt=="a\\")'] + body,
                 [r'while(t0.txt!="\\")'] + body, [r'if("\\"==t0.txt)'] + body,
                 [r'if(t0.txt=="\\\\")'] + body, [r'if(t0.txt=="\\"&&n0.val==1)'] + body,
                 [r'for(n0.val=0;t0.txt!="\\";n0.val++)'] + body,
                 ["if(n0.val==1)"] + body + [r'else if(t0.txt=="\\")'] + body]
        for number, lines in enumerate(cases):
            refused = next(line for line in lines if "\\" in line)
            with self.subTest(line=refused):
                self.write_code(*lines)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line %d: .*\(\"SYNTAX ERROR\"\)"
                        % (lines.index(refused) + 2)):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # Each it compiled: the text in a for's first and last parts, other
        # escapes ending a condition's text, and the text outside a condition.
        self.write_code(r'for(t0.txt="\\";n0.val<1;n0.val++)', *body,
                        r'for(n0.val=0;n0.val<1;t0.txt="\\")', *body,
                        r'if(t0.txt=="a\\b")', *body, r'while(t0.txt!="\"")', *body,
                        r'if("a\"b"!=t0.txt)', *body, r't0.txt="\\"')
        export_dump(self.source, self.folder / "built")

    def test_the_lines_the_editor_compiles(self):
        # A text loses characters by `-`; an array's attribute is of no known
        # kind; a condition compares texts; escapes are read in pairs from
        # the left; a comment is not compiled.
        self.write_code(r't0.txt="a\rb"', "st0.dir=2", "t0.txt-=3", "t0.txt=t0.txt-3",
                        'b[1].val="a"', 'if(t0.txt=="a")', "{", "n0.val=1", "}",
                        r't0.txt="a\\nb"', r't0.txt="say \"hi\""',
                        r't0.txt="a" // see "sd0\data"', 'va0.txt="a"', "va1.val=2",
                        "n0.val=n0.val+1", 't0.txt=t0.txt+"a"', 'vd1.path="sd0/a.video"',
                        "sys0=gm0.vid", "sys0=vd0.vid")
        export_dump(self.source, self.folder / "built")


class LackedAttributeTest(_CodeOnFirstTestCase):
    """An attribute a component lacks under its page file's choices, which the
    Editor 1.68.2's compile refused even read ("Invalid Variables"), each
    value of each choice tried apart on every series; and the same names under
    a value that keeps them, which it compiled. Besides t0, a text of `sta` 1,
    a colour, n0, and d0, page first holds texts of `sta` 3, nothing behind
    them, and 0, a crop of a picture, and of `effect` 1; waveforms of `ch` 2
    and 3; sounds and videos of `from` 0 and 1; and variables of a text and of
    a number."""

    def setUp(self):
        super().setUp()
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for name, kind, values in (
                    ("t1", "text", "sta = 3\n"), ("t2", "text", "sta = 0\n"),
                    ("t3", "text", "effect = 1\n"), ("s2", "waveform", "ch = 2\n"),
                    ("s3", "waveform", "ch = 3\n"), ("vd0", "video", ""),
                    ("vd1", "video", "from = 1\n")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 150\n'
                           'w = 100\nh = 60\n%s' % (name, kind, values))
            for name, kind, values in (("au0", "audio", ""), ("au1", "audio", "from = 1\n"),
                                       ("va0", "variable", "sta = 1\n"),
                                       ("va1", "variable", "")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\n%s' % (name, kind, values))

    def test_what_a_choice_leaves_out(self):
        cases = [("sys0=t0.pic", "t0 has its sta at 1, so it has no pic"),
                 ("sys0=t1.bco", "t1 has its sta at 3, so it has no bco"),
                 ("t1.picc=0", "t1 has its sta at 3, so it has no picc"),
                 ("sys0=t0.borderw", "t0 has its style at 0, so it has no borderw"),
                 ("sys0=t0.first", "t0 has its effect at 0, so it has no first"),
                 ("sys0=first.pic", "first has its sta at 1, so it has no pic"),
                 ("sys0=s2.pco2", "s2 has its ch at 2, so it has no pco2"),
                 ("sys0=au1.vid", "au1 plays a file of an SD card \\(its from is 1\\), so it has "
                                  "no vid"),
                 ("sys0=vd0.path_m", "vd0 plays an internal file \\(its from is 0\\), so it has "
                                     "no path_m"),
                 ("sys0=va1.txt_maxl", "va1 holds a number, so it has no txt_maxl")]
        for number, (line, why) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line 2: %s: %s, and the Nextion Editor refuses "
                                       r"to compile it \(\"Invalid Variables\"\)"
                                       % (re.escape(line), why)):
                    export_dump(self.source, self.folder / ("refused%d" % number))

    def test_the_same_names_under_a_value_that_keeps_them(self):
        self.write_code("sys0=t0.bco", "sys0=t2.picc", "sys0=t3.first", "sys0=t3.time",
                        "sys0=s3.pco2", "sys0=au0.vid", "sys0=vd1.path_m", "sys0=va0.txt_maxl",
                        "sys0=first.bco")
        export_dump(self.source, self.folder / "built")


class TypeNameTest(_CodeOnFirstTestCase):
    """Names code gives after a component, as the Editor 1.68.2 compiled them,
    every name it knows read on every type, on each series. A type has the
    attributes its defaults list, methods included, `id`, `type`, and
    `objname`, and `endx` and `endy` when it has a place; the Editor refused
    any other name ("Invalid Variables"). Besides t0, n0, and d0, page first
    holds tm0, a timer, fb0, a file browser, and fs0, a file stream; page
    second holds n9, a number."""

    def setUp(self):
        super().setUp()
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "tm0"\ntype = "timer"\n'
                       '\n[[component]]\nname = "fb0"\ntype = "file-browser"\nx = 0\ny = 150\n'
                       'w = 200\nh = 100\n\n[[component]]\nname = "fs0"\ntype = "file-stream"\n')
        with open(self.source / "pages" / "second.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "n9"\ntype = "number"\nvscope = 1\nx = 0\n'
                       'y = 40\nw = 100\nh = 40\n')

    def assert_refused(self, line: str, pattern: str, number: int):
        self.write_code(line)
        with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: %s: %s"
                                    % (re.escape(line), pattern)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_a_name_the_type_does_not_have(self):
        # Read or assigned. Names differ by their letters' case. A timer has
        # no place, so no endx.
        cases = [("sys0=n0.vall", "n0 is a number, which has no vall"),
                 ('n0.txt="a"', "n0 is a number, which has no txt"),
                 ("t0.txt=n0.txt", "n0 is a number, which has no txt"),
                 ("sys0=n0.Val", "n0 is a number, which has no Val"),
                 ("sys0=t0.objWid", "t0 is a text, which has no objWid"),
                 ("sys0=tm0.endx", "tm0 is a timer, which has no endx"),
                 ("sys0=first.vall", "first is a page, which has no vall"),
                 ("sys0=second.n9.vall", "second's n9 is a number, which has no vall")]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                self.assert_refused(line, words + r", and the Nextion Editor refuses to compile "
                                                  r"it \(\"Invalid Variables\"\)", number)

    def test_assignments_the_editor_refuses(self):
        # endx and endy, as id, type, and objname; and each method, which
        # code calls, as d0.insert("a^b").
        for number, attribute in enumerate(("endx", "endy")):
            with self.subTest(attribute=attribute):
                self.assert_refused("n0.%s=3" % attribute,
                                    "the Nextion Editor refuses to assign to %s of first's number "
                                    "n0, which code cannot change" % attribute, number)
        methods = [("d0", "data-record", name) for name in ("insert", "delete", "up", "clear")]
        methods += [("fb0", "file-browser", "up")]
        methods += [("fs0", "file-stream", name)
                    for name in ("open", "read", "write", "close", "find")]
        for number, (name, kind, method) in enumerate(methods, 2):
            with self.subTest(method="%s.%s" % (name, method)):
                self.assert_refused("%s.%s=1" % (name, method),
                                    r"%s is a method of first's %s %s, which code calls, and the "
                                    r"Nextion Editor refuses to compile an assignment to it "
                                    r"\(\"Invalid Variables\"\)" % (method, kind, name), number)

    def test_the_names_the_editor_compiles(self):
        # A page's `up` is the page a swipe opens, no method. A component
        # reached through the screen's arrays is left to the Editor.
        self.write_code("sys0=n0.id", "sys0=n0.type", "t0.txt=n0.objname", "sys0=n0.endx",
                        "sys0=n0.endy", "sys0=tm0.id", "sys0=tm0.type", "t0.txt=tm0.objname",
                        "sys0=first.id", "sys0=first.endy", "sys0=second.n9.val",
                        "sys0=d0.insert", "sys0=fb0.up", "sys0=fs0.find", 'd0.insert("a^b")',
                        "first.up=1", "b[1].vall=1")
        export_dump(self.source, self.folder / "built")

    def test_in_nxlang(self):
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0 = n0.vall\n",
                                                         encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx line 2: sys0=n0\.vall: n0 is a "
                                                   r"number, which has no vall"):
            export_dump(self.source, self.folder / "refused")


class EditorCommandTest(_CodeOnFirstTestCase):
    """A line whose first word is no command of the Editor's, which the
    Editor 1.68.2 refused as it compiled; and the lines it compiled. The small
    project's screen is of the Intelligent series, which lacks two of the
    Editor's commands, fstr and piccolor."""

    # A line of each of the Editor's commands, in the vendor's form, with
    # the components page first holds; call names a macro setUp adds, and
    # goto a label of the same event.
    EVERY_COMMAND = (
        "page 0", "ref t0", "click t0,1", "ref_stop", "ref_star", "get t0.txt", "sendme",
        "covx n0.val,t0.txt,0,0", "cov n0.val,t0.txt,0", "touch_j", "substr t0.txt,t0.txt,0,5",
        "vis t0,0", "tsw t0,0", "com_stop", "com_star", "randset 1,100", "code_c",
        "prints t0.txt,0", "print t0.txt", "printh 0d 0a", "add 1,0,30", "addt 1,0,20",
        "cle 1,0", "rest", "doevents", "strlen t0.txt,n0.val", "btlen t0.txt,n0.val",
        "wepo t0.txt,10", "repo t0.txt,10", "wept 30,20", "rept 30,20", "cfgpio 0,0,0",
        "ucopy n0.val,0,2,0", "move t0,-30,-30,100,150,95,120", "play 1,3,0",
        'twfile "ram/0.jpg",1120', 'delfile "ram/0.jpg"', 'refile "ram/0.jpg","ram/1.jpg"',
        'findfile "ram/0.jpg",n0.val', 'rdfile "ram/0.jpg",0,10,0', "setlayer t0,n0",
        'newdir "sd0/data/"', 'deldir "sd0/data/"', 'redir "sd0/data/","sd0/data2/"',
        'finddir "sd0/data/",n0.val', "udelete 24", "crcrest 1,0xFFFF", "crcputs n0.val,0",
        "lcd_dev fffb 0002 0000 0020",
        "crcputh 0A", "crcputu 0,10", 'spstr "ab3cd3ef3ghi",t0.txt,"3",0',
        'newfile "ram/0.bin",512', "call probe", "goto done", "cls BLUE", "pic 10,20,0",
        "picq 20,50,30,20,0", "xpic 20,50,30,20,15,15,0",
        "xstr 10,10,100,30,0,WHITE,GREEN,1,1,1,t0.txt", "fill 20,20,150,50,1024",
        "line 20,30,170,200,BLUE", "draw 10,10,70,70,GREEN", "cir 100,100,30,RED",
        "cirs 100,100,30,RED", "beep 100",
        # Those the vendor does not document, with the number of arguments
        # each compiled with.
        "getpassw", "lcd_refx", "lhmi_cle", "showqq", "getv 1", "init 1", "setbaudz 1",
        "pa_q 1,2", "whmi_cle 1,2", "nstr 1,2,3", "rfpt 1,2,3", "strsize 1,2,3", "wfpt 1,2,3",
        "pa_txt 1,2,3,4", "timerset 1,2,3,4", "zstr 1,2,3,4,5", "comok 1,2,3,4,5,6,7",
        "draw3d 1,2,3,4,5,6,7", "qrcode 1,2,3,4,5,6,7,8",
        "draw_h 1,2,3,4,5,6,7,8,9,10,11,12,13",
        "setbrush 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15", "sets", "sets 1,2,3", "i 1,2,3,4",
        "cfguart 1,2,3,4", "cuts 1,2,3,4,5,6,7", "gets 1,2", "meup 1,2",
        "xnum 1,2,3,4,5,6,7,8,9,10", "beepset 1,2",
        "done:", "return")

    def setUp(self):
        super().setUp()
        (self.source / "macros.nx").write_text("macro probe:\n  sys1=1\n", encoding="utf-8",
                                               newline="\n")

    def assert_line_refused(self, line: str, problem: str, number: int,
                            file: str = r"first\.nx line 2"):
        with self.assertRaisesRegex(NxwrightError, r"%s: %s: %s" % (file, re.escape(line),
                                                                    problem)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_a_first_word_the_editor_lacks(self):
        for number, (line, problem) in enumerate((
                ("zork b0,1", r"the Nextion Editor knows no command zork, and refuses it "
                              r"\(\"Invalid command\"\)"),
                ("sys0", r"the Nextion Editor knows no command sys0, and refuses it "
                         r"\(\"Invalid command\"\)"),
                ('dir "sd0/"', r"the Nextion Editor knows no command dir, and refuses it "
                               r"\(\"Invalid command\"\)"),
                ("CLS BLUE", r"the Nextion Editor's commands are written in small letters, as "
                             r"cls, and it refuses CLS \(\"Invalid Variables\"\)"),
                ("Zork 1", r"the Nextion Editor knows no command Zork, and refuses it "
                           r"\(\"Invalid Variables\"\)"),
                ("movelayer t0,n0", r"the Nextion Editor knows no command movelayer, and refuses "
                                    r"it \(\"Invalid Variables\"\)"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_line_refused(line, problem, number)

    def test_every_command_of_the_editor_builds(self):
        self.assertEqual({first_word(line) for line in self.EVERY_COMMAND} - {None},
                         EDITOR_COMMANDS - SERIES_LACKED_COMMANDS["P"])
        self.write_code(*self.EVERY_COMMAND)
        export_dump(self.source, self.folder / "built")

    def test_a_command_written_alone(self):
        # As the Editor refused each command that takes arguments, written
        # alone: for its number of arguments, but add for no command.
        for number, (line, words) in enumerate((("lcd_dev", "Invalid number of arguments"),
                                                ("cls", "Invalid number of arguments"),
                                                ("cuts", "Invalid number of arguments"),
                                                ("add", "Invalid command"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_line_refused(line, r".*\(\"%s\"\)" % words, number)
        self.write_code("doevents", "getpassw")
        export_dump(self.source, self.folder / "built")

    def test_lines_without_a_first_word_build(self):
        # A condition and its else alone on its line, a label, braces alone,
        # and methods called on a data record and a file stream.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "fs0"\ntype = "file-stream"\n')
        self.write_code("if(n0.val==1)", "{", "n0.val=2", "}", "else", "{", "n0.val=3", "}",
                        "start:", 'd0.insert("a^b")', "d0.clear()", "fs0.close()")
        export_dump(self.source, self.folder / "built")

    def test_lcd_dev_in_program_nx(self):
        # As a user's program.nx held it, which the Editor compiled: a fix of
        # the touch's offsets, for one version of a screen. Its four hex
        # values, spaced as printh's, are one argument; spaced by commas, they
        # are four, which the Editor refused.
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        program.write_text(text + ("" if text.endswith("\n") else "\n")
                           + "int display_mode=1\nif(display_mode==1)\n{\n"
                           "  lcd_dev fffb 0002 0000 0020// Fix touch offset for EU Version\n}\n",
                           encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "built")

    def test_a_page_or_component_named_in_program_nx(self):
        # program.s belongs to no page. The Editor refused a page's or a
        # component's name given to vis, tsw, ref, or click there, with its
        # page's name or not ("Invalid Component ID"). It compiled a
        # component's number, and a variable holding one.
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        written = text + ("" if text.endswith("\n") else "\n")
        line_number = len(written.split("\n"))
        for number, line in enumerate(("vis first,0", "ref first", "vis t0,0", "tsw t0,1",
                                       "click t0,1", "vis first.t0,0")):
            with self.subTest(line=line):
                program.write_text(written + line + "\n", encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(
                        NxwrightError, r"program\.nx line %d: %s: .*\(\"Invalid Component "
                        r"ID\"\)" % (line_number, line)):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        program.write_text(written + "vis 1,0\nvis sys0,0\n", encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "built")

    def test_an_int_of_program_nx_named_as_the_editor_refuses(self):
        # The Editor refused an int named as one of its commands, even one
        # the series lacks; as a system variable; as a page; and as a
        # component of any page. It compiled other names. nxlang writes
        # program.nx's ints as they are, so it refuses them too.
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        written = text + ("" if text.endswith("\n") else "\n")
        line_number = len(written.split("\n"))
        cases = [("int sets=0", "Conflict with instructions name"),
                 ("int vis=0", "Conflict with instructions name"),
                 ("int fstr=0", "Conflict with instructions name"),
                 ("int dim=0", "Illegal name"),
                 ("int abc=0,first=1", "Conflict with page name"),
                 ("int t0=1", "Conflict with Component name")]
        for language in ("strict", "nxlang"):
            if language == "nxlang":
                switch_to_nxlang(self.source)
            for number, (line, words) in enumerate(cases):
                with self.subTest(language=language, line=line):
                    program.write_text(written + line + "\n", encoding="utf-8", newline="\n")
                    with self.assertRaisesRegex(
                            NxwrightError, r"program\.nx line %d: %s: .*\(\"%s\"\)"
                            % (line_number, re.escape(line), words)):
                        export_dump(self.source, self.folder / ("%s%d" % (language, number)))
            program.write_text(written + "int abc=0,t1=2\n", encoding="utf-8", newline="\n")
            export_dump(self.source, self.folder / ("%s-built" % language))

    def test_a_component_named_as_an_int_of_program_nx(self):
        # The Editor refused a text named sys0 beside program.s's own
        # declaration of sys0 to sys2, on the int's line.
        add_component(self.source / "pages" / "first.page.toml", "sys0")
        program = self.source / "program.nx"
        line_number = program.read_text(encoding="utf-8").split("\n").index(
            "int sys0=0,sys1=0,sys2=0") + 1
        with self.assertRaisesRegex(
                NxwrightError, r"program\.nx line %d: int sys0=0,sys1=0,sys2=0: sys0 is a "
                r"component of page first, .*\(\"Conflict with Component name\"\)"
                % line_number):
            export_dump(self.source, self.folder / "refused")

    def test_program_nx_macros_and_nxlang(self):
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        written = text + ("" if text.endswith("\n") else "\n")
        program.write_text(written + "zork 1\n", encoding="utf-8", newline="\n")
        self.assert_line_refused("zork 1", r"the Nextion Editor knows no command zork", 0,
                                 r"program\.nx line %d" % len(written.split("\n")))
        program.write_text(text, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  CLS 1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_line_refused("CLS 1", r"the Nextion Editor's commands are written in small "
                                          r"letters, as cls", 1, r"macros\.nx line 2")
        (self.source / "macros.nx").unlink()
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  zork 1\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_line_refused("zork 1", r"the Nextion Editor knows no command zork", 2)


class LabelTest(SourceFolderTestCase):
    """Labels and goto in first.down, kept, or refused where the Editor
    refused them as it compiled. setUp adds the down event on page first."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def test_label_lines_are_kept(self):
        self.write_code("up:  // again", "sys0 += 1", "if (sys0 < 3) {", "  goto up", "}",
                        "return")
        export_dump(self.source, self.folder / "again")
        self.assertIn("  event down\n    | up:  // again\n    | sys0+=1\n    | if(sys0<3)\n"
                      "    | {\n    |   goto up\n    | }\n    | return\n",
                      (self.folder / "again" / "pages" / "00-first.txt").read_text(encoding="utf-8"))

    def test_the_editor_refuses_a_missing_or_repeated_label(self):
        cases = [(("sys0 = 1", "goto end"), r"first\.nx line 3: goto end: the Nextion Editor "
                                            r"finds no label end in this event"),
                 (("end:", "sys0 = 1", "end:"), r"first\.nx line 4: end: the Nextion Editor "
                                                r"refuses a label twice in one event"),
                 (("1abc:", "goto 1abc"), r"first\.nx line 2: 1abc: the Nextion Editor "
                                          r"refuses this label")]
        for lines, message in cases:
            with self.subTest(lines=lines):
                self.write_code(*lines)
                self.assert_export_refused(message)


class ReadOnlyAttributeTest(SourceFolderTestCase):
    """Assignments in first.down to attributes code cannot change, which the
    Editor refused as it compiled ("Assignment operation failed").
    setUp adds the down event, and a text on each page: t0 on first, and t1
    on second."""

    def setUp(self):
        super().setUp()
        pages = self.source / "pages"
        edit_text(pages / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(pages / "first.page.toml", "t0")
        add_component(pages / "second.page.toml", "t1")

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def assert_refused(self, line: str, what: str, number: int, file: str = r"first\.nx line 2"):
        with self.assertRaisesRegex(NxwrightError, r"%s: %s: the Nextion Editor refuses "
                                                   "to assign to %s, which code cannot change"
                                    % (file, re.escape(line), what)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_the_assignments_the_editor_refuses(self):
        # As the Editor compiled them: every form of assignment, a page's own
        # attributes, another page's component, and id, type, and objname,
        # which the attribute descriptions hold none of.
        cases = [("t0.w=10", "w of first's text t0"), ("t0.w+=1", "w of first's text t0"),
                 ("t0.h++", "h of first's text t0"), ("t0.h|=1", "h of first's text t0"),
                 ("t0.id=3", "id of first's text t0"), ("t0.type=1", "type of first's text t0"),
                 ('t0.objname="a"', "objname of first's text t0"),
                 ("first.x=10", "x of the page first"), ("second.w=10", "w of the page second"),
                 ("second.t1.w=10", "w of second's text t1")]
        for number, (line, what) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, what, number)

    def test_what_the_editor_compiles(self):
        # A text's x and txt are green in the Editor's panel, and reading w
        # changes nothing. A component named by its ID is left to the
        # Editor, as no read-only attribute can be told there.
        self.write_code("t0.x=10", 't0.txt="a"', "sys0=t0.w", "b[1].w=1")
        export_dump(self.source, self.folder / "again")

    def test_an_animations_source(self):
        # As the Editor compiled them: it refused `from`, and took `path`,
        # though its panel shows neither for an animation.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "gm0"\ntype = "gmov"\nx = 0\ny = 50\nw = 80\n'
                       'h = 60\n')
        self.write_code("gm0.from=1")
        self.assert_refused("gm0.from=1", "from of first's gmov gm0", 0)
        self.write_code('gm0.path="sd0/a.gmov"')
        export_dump(self.source, self.folder / "path")

    def test_a_waveforms_hidden_attributes(self):
        # As the Editor compiled them: it refused setting objWid, objHig, or
        # inittrue, and took code reading them, though its panel shows none of
        # them.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "s0"\ntype = "waveform"\nx = 0\ny = 50\n'
                       'w = 200\nh = 100\n')
        for number, attribute in enumerate(("objWid", "objHig", "inittrue")):
            with self.subTest(attribute=attribute):
                line = "s0.%s=5" % attribute
                self.write_code(line)
                self.assert_refused(line, "%s of first's waveform s0" % attribute, number)
        self.write_code("sys0=s0.objWid", "sys1=s0.objHig", "sys2=s0.inittrue")
        export_dump(self.source, self.folder / "read")

    def test_more_attributes_the_panel_never_shows(self):
        # As the Editor compiled them: it refused setting movex and movey, on
        # every type tried, a select's or a switch's txt_maxl, and a combo
        # box's drastate, and took code reading them; it took code setting a
        # button's val, a file browser's xcen, and a gauge's wid.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for name, kind in (("b0", "button"), ("s0", "select"), ("sw0", "switch"),
                               ("cb0", "combo-box"), ("fb0", "file-browser"), ("z0", "gauge")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 50\n'
                           'w = 100\nh = 50\n' % (name, kind))
        for number, (line, owner) in enumerate((
                ("b0.movex=5", "movex of first's button b0"),
                ("b0.movey=5", "movey of first's button b0"),
                ("s0.txt_maxl=5", "txt_maxl of first's select s0"),
                ("sw0.txt_maxl=5", "txt_maxl of first's switch sw0"),
                ("cb0.drastate=1", "drastate of first's combo-box cb0"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, owner, number)
        self.write_code("sys0=b0.movex", "sys1=cb0.drastate", "sys2=sw0.txt_maxl", "b0.val=1",
                        "fb0.xcen=0", "z0.wid=3")
        export_dump(self.source, self.folder / "taken")

    def test_a_pages_hotspots_crops_and_sliding_texts_hidden_attributes(self):
        # As the Editor compiled them: it refused setting a page's drag or
        # aph, or a sliding text's leftshow, and took code reading them; it
        # took code setting a hotspot's drag, aph, and effect, a crop's vvs0
        # and vvs1, and a sliding text's path to a text.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for name, kind in (("m0", "hotspot"), ("q0", "crop"), ("slt0", "sliding-text")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 50\n'
                           'w = 100\nh = 50\n' % (name, kind))
        for number, (line, owner) in enumerate((
                ("first.drag=1", "drag of the page first"),
                ("first.aph=50", "aph of the page first"),
                ("slt0.leftshow=1", "leftshow of first's sliding-text slt0"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, owner, number)
        self.write_code("sys0=first.drag", "sys1=first.aph", "sys2=slt0.leftshow", "m0.drag=1",
                        "m0.aph=50", "m0.effect=1", "q0.vvs0=10", "q0.vvs1=10", 'slt0.path="a"')
        export_dump(self.source, self.folder / "taken")

    def test_a_data_records_file_browsers_and_scrolling_texts_hidden_attributes(self):
        # As the Editor compiled them: it refused setting a data record's init
        # or autoleft, or a file browser's autoleft or buff, and took code
        # reading them; it took code setting a data record's filter, and a
        # scrolling text's vvs2 and vvs3.
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for name, kind in (("d0", "data-record"), ("fb0", "file-browser"),
                               ("g0", "scrolling-text"), ("t9", "text")):
                file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 50\n'
                           'w = 100\nh = 50\n' % (name, kind))
        for number, (line, owner) in enumerate((
                ("d0.init=1", "init of first's data-record d0"),
                ("d0.autoleft=1", "autoleft of first's data-record d0"),
                ("fb0.autoleft=1", "autoleft of first's file-browser fb0"),
                ("fb0.buff=1", "buff of first's file-browser fb0"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, owner, number)
        self.write_code("sys0=d0.init", "sys1=d0.autoleft", "sys2=fb0.buff", "sys0=fb0.autoleft",
                        "t9.txt=d0.filter", 'd0.filter="a"', "g0.vvs2=5", "g0.vvs3=5")
        export_dump(self.source, self.folder / "taken")

    def test_the_runner_refuses_it_too(self):
        # Tests and the simulator build the page as the build does.
        self.write_code("t0.w=10")
        with self.assertRaisesRegex(NxwrightError, r"line 2: t0\.w=10: the Nextion Editor refuses "
                                                   r"to assign to w of first's text t0"):
            SourceFolderRunner(self.source).run("first", [("first", "down")])

    def test_in_nxlang_and_in_a_file_two_pages_include(self):
        # The included line is checked for each page that uses it, and the
        # message names the page, as a line may be refused for one page alone.
        switch_to_nxlang(self.source)
        pages = self.source / "pages"
        (pages / "first.nx").write_text("on first.down:\n  t0.w = 10\n", encoding="utf-8",
                                        newline="\n")
        self.assert_refused("t0.w=10", "w of first's text t0", 0)
        edit_text(pages / "second.page.toml", "events = []", 'events = ["down"]')
        (pages / "lib").mkdir()
        (pages / "lib" / "shared.nx").write_text("function widen():\n  t1.h = 5\n",
                                                 encoding="utf-8", newline="\n")
        (pages / "first.nx").write_text("on first.down:\n  sys0 = 1\n", encoding="utf-8",
                                        newline="\n")
        (pages / "second.nx").write_text('include "lib/shared.nx"\n\non second.down:\n'
                                         "  widen()\n", encoding="utf-8", newline="\n")
        self.assert_refused("t1.h=5", "h of second's text t1", 1, r"pages/lib/shared\.nx line 2")


class ScreenEdgeTest(SourceFolderTestCase):
    """A component reaching past the screen, which the Editor 1.68.2's compile
    refused on the Basic, Enhanced, and Discovery series, "Position Invalid":
    past its right or bottom edge, at the screen's rotation, or starting past
    it. One ending at an edge compiled, and the Intelligent and Edge series
    took any."""

    def use_screen(self, model: str, rotation: int = 0):
        app = self.source / "app.toml"
        data = tomllib.loads(app.read_text(encoding="utf-8"))
        data["screen"], data["rotation"] = model, rotation
        app.write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")

    def place(self, name: str, x: int, y: int, w: int, h: int, kind: str = "text"):
        """Adds a component `name` of type `kind` to page first, at (x, y),
        w by h."""
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = %d\ny = %d\nw = %d\n'
                       'h = %d\n' % (name, kind, x, y, w, h))

    def assert_past(self, model: str, size: str):
        self.assert_export_refused(
            r"first\.page\.toml: component c0: it reaches past the screen, %s at its rotation, "
            r"and the Nextion Editor refuses to compile it on the %s \(\"Position Invalid\"\)"
            % (size, model))

    def test_past_the_right_or_the_bottom_edge(self):
        # An NX4832T035 is 320 pixels wide and 480 high.
        self.use_screen("NX4832T035")
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for x, y, w, h, kind in ((280, 0, 100, 30, "text"), (0, 460, 100, 30, "text"),
                                 (340, 0, 50, 30, "text"), (280, 40, 100, 30, "hotspot")):
            with self.subTest(x=x, y=y, kind=kind):
                self.place("c0", x, y, w, h, kind)
                self.assert_past("NX4832T035", "320 by 480")
                page_file.write_bytes(page)
        self.place("c0", 220, 450, 100, 30)
        export_dump(self.source, self.folder / "at the edges")

    def test_on_a_turned_screen(self):
        # Turned 90 degrees, an NX4832T035 is 480 wide and 320 high.
        self.use_screen("NX4832T035", 90)
        self.place("c0", 350, 0, 100, 30)
        export_dump(self.source, self.folder / "wide")
        self.place("c1", 0, 300, 100, 50)
        self.assert_export_refused(r"component c1: it reaches past the screen, 480 by 320")

    def test_the_intelligent_and_edge_series_take_it(self):
        self.place("c0", 1000, 0, 100, 30)
        for model in ("NX8048P050", "NX4848E040"):
            with self.subTest(model=model):
                self.use_screen(model)
                export_dump(self.source, self.folder / model)


class SeriesTest(SourceFolderTestCase):
    """Lines using a command or a system variable the folder's screen series
    lacks, which the Editor 1.68.2 refused as it compiled. setUp adds the down
    event to page first, and a text t0 on it. The small project's screen, an
    NX1060P101, is of the Intelligent series."""

    def setUp(self):
        super().setUp()
        pages = self.source / "pages"
        edit_text(pages / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(pages / "first.page.toml", "t0")

    def use_screen(self, model: str):
        app = self.source / "app.toml"
        data = tomllib.loads(app.read_text(encoding="utf-8"))
        data["screen"] = model
        app.write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def assert_refused(self, line: str, model: str, word: str, kind: str, number: int,
                       file: str = r"first\.nx line 2"):
        with self.assertRaisesRegex(
                NxwrightError, r"%s: %s: the %s lacks %s, and the Nextion Editor refuses to "
                               r"compile it for its series \(\"Do not support such %s for this "
                               r"series device\"\)" % (file, re.escape(line), model, word, kind)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def assert_assignment_refused(self, line: str, model: str, owner: str, number: int):
        """Asserts the build refuses `line`, the code of first.down, on the
        screen `model`, as an assignment to `owner`'s attribute that code
        cannot change on its series."""
        self.use_screen(model)
        self.write_code(line)
        with self.assertRaisesRegex(
                NxwrightError, r"first\.nx line 2: %s: on the %s, the Nextion Editor refuses to "
                               r"assign to %s, which code cannot change on its series "
                               r"\(\"Assignment operation failed\"\)"
                               % (re.escape(line), model, owner)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def add(self, name: str, kind: str, **values):
        """Adds a component of type `kind` to page first, with `values`."""
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 100\nw = 80\n'
                       'h = 60\n' % (name, kind)
                       + "".join("%s = %d\n" % item for item in values.items()))

    def test_attributes_a_series_lacks(self):
        # As the Editor 1.68.2 compiled them: the Basic, Enhanced, and
        # Discovery series refused code naming these, even read ("Invalid
        # Variables"), and the Edge and Intelligent took it.
        self.add("s0", "waveform")
        cases = [("sys0=t0.movex", "t0", "movex"), ("t0.txt=t0.objname", "t0", "objname"),
                 ("t0.txt=first.objname", "first", "objname"), ("sys0=s0.objWid", "s0", "objWid")]
        number = 0
        for model in ("NX4832T035", "NX4832K035", "NX4832F035"):
            self.use_screen(model)
            for line, name, attribute in cases:
                with self.subTest(model=model, line=line):
                    self.write_code(line)
                    number += 1
                    with self.assertRaisesRegex(
                            NxwrightError, r"first\.nx line 2: %s: %s is on an %s, so it has "
                                           r"no %s, and the Nextion Editor refuses to compile it "
                                           r"\(\"Invalid Variables\"\)"
                                           % (re.escape(line), name, model, attribute)):
                        export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code(*(line for line, _, _ in cases))
        for model in ("NX4848E040", "NX8048P050"):
            with self.subTest(model=model):
                self.use_screen(model)
                export_dump(self.source, self.folder / model)

    def assert_component_refused(self, refusal: str):
        """Asserts that the build refuses page first, its message going on
        after "component " as the pattern `refusal` says."""
        with self.assertRaisesRegex(NxwrightError, r"first\.page\.toml: component " + refusal):
            export_dump(self.source, self.folder / "refused")

    def test_a_type_the_series_refuses(self):
        # As the Editor 1.68.2 refused an animation on the Discovery series:
        # "Unsupported component was found for this series device".
        self.add("gm0", "gmov")
        self.use_screen("NX4832F035")
        self.assert_component_refused(r"gm0: the NX4832F035 lacks the type gmov, and the "
                                      r"Nextion Editor refuses to compile it \(\"Unsupported "
                                      r"component was found for this series device\"\)")
        self.use_screen("NX8048P050")
        export_dump(self.source, self.folder / "taken")

    def test_a_choice_the_series_refuses(self):
        # A gauge's sta 3, nxwright's default, on the basic series; a data
        # record of local scope on the Intelligent: "Out of range".
        self.use_screen("NX4832T035")
        self.add("g0", "gauge")
        self.assert_component_refused(r"g0: its sta of 3 is refused on the NX4832T035, as the "
                                      r"Nextion Editor's compile refuses it \(\"Out of range\"\)")
        edit_text(self.source / "pages" / "first.page.toml", 'type = "gauge"\n',
                  'type = "gauge"\nsta = 0\n')
        export_dump(self.source, self.folder / "sta0")
        self.use_screen("NX8048P050")
        self.add("d0", "data-record", vscope=0)
        self.assert_component_refused(r"d0: its vscope of 0 is refused on the NX8048P050, as the "
                                      r"Nextion Editor's compile refuses it \(\"Out of range\"\)")
        edit_text(self.source / "pages" / "first.page.toml", "vscope = 0\n", "vscope = 1\n")
        export_dump(self.source, self.folder / "global")

    def test_choices_the_editor_refused_beside_the_table(self):
        # As the Editor 1.68.2 refused them, "Out of range": a sta of 3 on the
        # Basic, Enhanced, and Discovery series, on a text, a button, and
        # others, and a slider's psta of 2. The Edge and the Intelligent took
        # them.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for model, kind, attribute, value in (("NX4832T035", "text", "sta", 3),
                                              ("NX4832K035", "button", "sta", 3),
                                              ("NX4832F035", "slider", "psta", 2)):
            with self.subTest(model=model, kind=kind):
                self.use_screen(model)
                self.add("x0", kind, **{attribute: value})
                self.assert_component_refused(r"x0: its %s of %d is refused on the %s, as the "
                                              r"Nextion Editor's compile refuses it \(\"Out of "
                                              r"range\"\)"
                                              % (attribute, value, model))
                self.use_screen("NX8048P050")
                export_dump(self.source, self.folder / ("taken-" + kind))
                page_file.write_bytes(page)

    def test_assignments_the_series_refuses(self):
        # As the Editor 1.68.2 refused them on the Basic, Enhanced, and
        # Discovery series, on every type that has them and the page:
        # "Assignment operation failed"; and x and y, on a text and a slider.
        # The Edge and the Intelligent took them.
        for number, (model, line, owner) in enumerate((
                ("NX4832T035", "t0.aph=50", "aph of first's text t0"),
                ("NX4832K035", "t0.drag=1", "drag of first's text t0"),
                ("NX4832F035", "first.effect=1", "effect of the page first"),
                ("NX4832T035", "t0.x=5", "x of first's text t0"),
                ("NX4832K035", "t0.y=5", "y of first's text t0"),
                ("NX4832F035", "t0.x=5", "x of first's text t0"))):
            with self.subTest(line=line):
                self.assert_assignment_refused(line, model, owner, number)
        self.use_screen("NX4832T035")
        self.write_code("sys0=t0.x", "sys1=t0.y")
        export_dump(self.source, self.folder / "read")
        self.use_screen("NX4848E040")
        self.write_code("t0.aph=50", "t0.drag=1", "t0.effect=1", "first.effect=1", "sys0=t0.aph",
                        "t0.x=5", "t0.y=5")
        export_dump(self.source, self.folder / "taken")

    def test_assignments_the_series_refuses_on_some_types(self):
        # As the Editor 1.68.2 refused them on the Basic, Enhanced, and
        # Discovery series ("Assignment operation failed"), and took them on
        # the Edge and Intelligent. first and time were refused on every type,
        # each with an effect, and on the Basic's page. A button's, a
        # dual-state button's, and a text's border and spacing were refused,
        # and a crop's vvs0 and vvs1. A number took its border and spacing.
        # The Basic took code reading each.
        edit_text(self.source / "pages" / "first.page.toml", "[page]\n", "[page]\neffect = 1\n")
        self.add("b0", "button", effect=1)
        self.add("bt0", "dual-state-button")
        self.add("t1", "text", style=1)
        self.add("q0", "crop")
        self.add("n0", "number", style=1)
        for number, (model, line, owner) in enumerate((
                ("NX4832T035", "b0.first=0", "first of first's button b0"),
                ("NX4832K035", "b0.time=300", "time of first's button b0"),
                ("NX4832F035", "first.first=0", "first of the page first"),
                ("NX4832T035", "t0.spax=1", "spax of first's text t0"),
                ("NX4832K035", "bt0.spay=1", "spay of first's dual-state-button bt0"),
                ("NX4832F035", "t1.borderc=0", "borderc of first's text t1"),
                ("NX4832T035", "t1.borderw=2", "borderw of first's text t1"),
                ("NX4832K035", "q0.vvs0=1", "vvs0 of first's crop q0"),
                ("NX4832F035", "q0.vvs1=1", "vvs1 of first's crop q0"))):
            with self.subTest(line=line):
                self.assert_assignment_refused(line, model, owner, number)
        self.use_screen("NX4832T035")
        self.write_code("sys0=b0.first", "sys0=first.time", "sys0=t0.spax", "sys0=t1.borderc",
                        "sys0=q0.vvs0", "n0.spax=1", "n0.borderc=0")
        export_dump(self.source, self.folder / "read")
        self.use_screen("NX4848E040")
        self.write_code("b0.first=0", "first.time=300", "t0.spax=1", "bt0.spay=1",
                        "t1.borderw=2", "q0.vvs1=1")
        export_dump(self.source, self.folder / "taken")

    def test_the_memory_probe_builds_what_the_series_refuses(self):
        # The Editor tool's memory probe builds components a series refuses,
        # to see the Editor refuse them, and asks the build to leave out
        # the checks that read its table.
        self.add("gm0", "gmov")
        self.add("t1", "text", sta=3)
        self.use_screen("NX4832F035")
        export_dump(self.source, self.folder / "probe", refuse_by_table=False)

    def test_a_value_of_an_attribute_without_choices(self):
        # The table lists aph 128 as refused, a sample past aph's range, which
        # the build refuses on every type, as the Nextion Editor refused it
        # on a button too.
        self.add("b0", "button", aph=128)
        with self.assertRaisesRegex(NxwrightError, "aph must be from 0 to 127"):
            export_dump(self.source, self.folder / "built")

    def test_a_folder_without_screen_settings(self):
        app = self.source / "app.toml"
        data = tomllib.loads(app.read_text(encoding="utf-8"))
        for key in DEVICE_KEYS:
            data.pop(key, None)
        app.write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")
        self.add("gm0", "gmov")
        export_dump(self.source, self.folder / "built")

    def test_what_each_series_lacks(self):
        # Each line on a screen whose series refused it, then on one whose
        # series took it.
        cases = [("NX4832T035", "wepo 1,0", "wepo", "instruction", "NX4832K035"),
                 ("NX4832T035", "sys0=rtc0", "rtc0", "variable", "NX4832K035"),
                 ("NX4832K035", 'newfile "sd0/a.txt",10', "newfile", "instruction",
                  "NX8048P050"),
                 ("NX4832K035", "sys0=volume", "volume", "variable", "NX8048P050"),
                 ("NX4832F035", "rept 0,10", "rept", "instruction", "NX4832K035"),
                 ("NX4832F035", "sys0=rtc1", "rtc1", "variable", "NX4832K035"),
                 ("NX8048P050", "sys0=lowpower", "lowpower", "variable", "NX4832F035"),
                 ("NX4832K035", "sys0=scache", "scache", "variable", "NX4848E040"),
                 ("NX4832K035", "sys0=tprc", "tprc", "variable", "NX4848E040"),
                 ("NX8048P050", "fstr 1,2,3", "fstr", "instruction", "NX4832T035"),
                 ("NX4832T035", "piccolor 1,2,3,4", "piccolor", "instruction", "NX4832F035"),
                 ("NX4848E040", "sys0=lowpower", "lowpower", "variable", "NX4832F035")]
        for number, (model, line, word, kind, taking) in enumerate(cases):
            with self.subTest(line=line, model=model):
                self.use_screen(model)
                self.write_code(line)
                self.assert_refused(line, model, word, kind, number)
                self.use_screen(taking)
                export_dump(self.source, self.folder / ("taken%d" % number))

    def test_piccolor_on_the_discovery_series(self):
        # The Editor compiled piccolor with four arguments on the Discovery
        # series, the one series that has it, and refused three and five
        # ("Invalid number of arguments").
        self.use_screen("NX4832F035")
        for number, line in enumerate(("piccolor 1,2,3", "piccolor 1,2,3,4,5")):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx line 2: %s: piccolor takes 4, .*\(\"Invalid "
                        r"number of arguments\"\)" % re.escape(line)):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code("piccolor 1,2,3,4")
        export_dump(self.source, self.folder / "built")

    def test_a_variable_anywhere_in_a_line(self):
        # In a condition, as an assignment's target, in arithmetic, and as
        # an argument.
        self.use_screen("NX4832T035")
        for number, line in enumerate(("if(rtc0>0)", "rtc0=5", "sys0=t0.w+pio0",
                                       "covx rtc3,t0.txt,0,0")):
            with self.subTest(line=line):
                self.write_code(*([line, "{", "}"] if line.startswith("if") else [line]))
                word = re.search(r"rtc\d|pio\d", line)[0]
                self.assert_refused(line, "NX4832T035", word, "variable", number)

    def test_names_in_a_quoted_text(self):
        self.use_screen("NX4832T035")
        self.write_code('t0.txt="rtc0 wepo"')
        export_dump(self.source, self.folder / "built")

    def test_program_nx_and_macros(self):
        self.use_screen("NX4832T035")
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        program.write_text(text + ("" if text.endswith("\n") else "\n") + "wepo 1,0\n",
                           encoding="utf-8", newline="\n")
        line = len((text + ("" if text.endswith("\n") else "\n")).split("\n"))
        self.assert_refused("wepo 1,0", "NX4832T035", "wepo", "instruction", 0,
                            r"program\.nx line %d" % line)
        program.write_text(text, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  sys1=rtc1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_refused("sys1=rtc1", "NX4832T035", "rtc1", "variable", 1,
                            r"macros\.nx line 2")

    def test_in_nxlang(self):
        switch_to_nxlang(self.source)
        self.use_screen("NX4832K035")
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0 = volume\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_refused("sys0=volume", "NX4832K035", "volume", "variable", 0)

    def test_the_series_before_the_number_of_arguments(self):
        # The Basic series lacks beep; the Intelligent takes one argument.
        self.use_screen("NX4832T035")
        self.write_code("beep 100,2")
        self.assert_refused("beep 100,2", "NX4832T035", "beep", "instruction", 0)
        self.use_screen("NX8048P050")
        with self.assertRaisesRegex(NxwrightError, r"beep takes 1, .*\(\"Invalid number of "
                                                   r"arguments\"\)"):
            export_dump(self.source, self.folder / "two")
        self.write_code("beep 100")
        export_dump(self.source, self.folder / "one")


class SharedFileReferenceTest(SourceFolderTestCase):
    """A shared file holding a function for each of two pages, each naming its
    own page's component: a page checks only the functions it uses."""

    def setUp(self):
        super().setUp()
        switch_to_nxlang(self.source)
        pages = self.source / "pages"
        for page, component, function in (("first", "t0", "showFirst"),
                                          ("second", "t1", "showSecond")):
            edit_text(pages / (page + ".page.toml"), "events = []", 'events = ["load", "down"]')
            add_component(pages / (page + ".page.toml"), component)
            (pages / (page + ".nx")).write_text(
                'include "lib/both.nx"\n\non %s.down:\n  %s()\n' % (page, function),
                encoding="utf-8", newline="\n")
        (pages / "lib").mkdir()

    def write_library(self, first_component: str):
        """Writes lib/both.nx, whose showFirst sets the txt of `first_component`."""
        (self.source / "pages" / "lib" / "both.nx").write_text(
            'function showFirst():\n  %s.txt = "first"\n\n'
            'function showSecond():\n  t1.txt = "second"\n' % first_component,
            encoding="utf-8", newline="\n")

    def test_each_page_checks_the_functions_it_uses(self):
        self.write_library("t0")
        export_dump(self.source, self.folder / "again")

    def test_an_unknown_component_is_reported_in_the_shared_file(self):
        self.write_library("t9")
        self.assert_export_refused(r"pages/lib/both\.nx line 2: t9 is neither on this page nor a page")


if __name__ == "__main__":
    unittest.main()
