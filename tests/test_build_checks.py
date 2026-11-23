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
from nxwright.language.code_checks import ObjectNames, check_line, misread_byte_by_byte
from nxwright.language.code_lines import first_word
from nxwright.project.editor_language import (EDITOR_COMMANDS, EDITOR_PROGRAM_DECLARATION,
                                              SERIES_LACKED_COMMANDS)
from nxwright.project import editor_limits
from nxwright.project.editor_limits import LONGEST_LINES
from nxwright.project.device_settings import TextCodec
from nxwright.project.dumper import ProjectDumper
from nxwright.project.project_writer import ProjectWriter
from nxwright.source.device_keys import DEVICE_KEYS
from nxwright.source.folder_check import check_folder
from nxwright.source.project_files import build
from nxwright.source.source_folder import (app_text, export_dump, folder_reader,
                                           switch_to_nxlang)
from nxwright.testing import SourceFolderRunner
from tests.test_project_writer import edit_text
from tests.test_source_folder import SourceFolderTestCase


def add_component(page_file: Path, name: str, text: str = None, limit: int = None,
                  scope: int = None):
    """Adds a text component to a page file. Its `vscope` is `scope` when
    given (0 for local, 1 for global), and otherwise its type's default."""
    lines = '\n[[component]]\nname = "%s"\ntype = "text"\nx = 0\ny = 0\nw = 100\nh = 30\n' % name
    if text is not None:
        lines += 'txt = "%s"\n' % text
    if limit is not None:
        lines += "txt_maxl = %d\n" % limit
    if scope is not None:
        lines += "vscope = %d\n" % scope
    with open(page_file, "a", encoding="utf-8", newline="\n") as file:
        file.write(lines)


class MalformedPageFileTest(SourceFolderTestCase):
    """The build reads every page file's names before it builds any page, so a
    malformed page file must still stop it with the page file's own error."""

    def test_a_page_that_is_not_a_table(self):
        (self.source / "pages" / "second.page.toml").write_text('page = "x"\n', encoding="utf-8")
        self.assert_export_refused(r"pages/second\.page\.toml: the \[page\] table is missing")

    def test_components_that_are_not_tables(self):
        edit_text(self.source / "pages" / "second.page.toml", "[page]", "component = 5\n\n[page]")
        self.assert_export_refused(r"pages/second\.page\.toml: only \[page\] and "
                                   r"\[\[component\]\] tables are allowed")


class SourceFolderLimitTest(SourceFolderTestCase):

    def add_text_component(self, name: str, text: str, limit: int = None):
        add_component(self.source / "pages" / "first.page.toml", name, text, limit)

    def test_a_name_longer_than_the_editor_keeps(self):
        self.add_text_component("abcdefghijklmno", "x")
        self.assert_export_refused(r"pages/first\.page\.toml:9: the name of component `abcdefghijklmno` "
                                   r"has 15 bytes, and the limit is 14")

    def test_names_the_editor_refuses(self):
        # The Editor says "Illegal name" as it opens such a project, whatever
        # the component's type: its system variables and its colours.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for name in ("audio0", "dim", "eq9", "scache", "bcpu", "aph", "BLACK"):
            with self.subTest(name=name):
                self.add_text_component(name, "x")
                self.assert_export_refused(r"pages/first\.page\.toml:9: component `%s` has a reserved "
                                           r"name" % name)
                page_file.write_bytes(page)

    def test_a_name_that_starts_with_a_digit(self):
        # The Nextion Editor refused a project with such a component, or such
        # a page, as it opened it, each probed alone.
        self.add_text_component("1t", "x")
        self.assert_export_refused(r"pages/first\.page\.toml:9: the name of component `1t` cannot start "
                                   r"with a digit")

    def test_a_page_name_that_starts_with_a_digit(self):
        pages = self.source / "pages"
        (pages / "second.page.toml").rename(pages / "2nd.page.toml")
        (pages / "second.nx").rename(pages / "2nd.nx")
        for path in (self.source / "app.toml", pages / "2nd.page.toml"):
            path.write_text(path.read_text(encoding="utf-8").replace('"second"', '"2nd"'),
                            encoding="utf-8")
        self.assert_export_refused(r"pages/2nd\.page\.toml:1: the name of page `2nd` cannot start with a "
                                   r"digit")

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
        self.assert_export_refused(r"pages/dim\.page\.toml:1: page `dim` has a reserved name")

    def test_a_name_of_14_bytes(self):
        self.add_text_component("abcdefghijklmn", "x")
        export_dump(self.source, self.folder / "again")

    def test_a_text_longer_than_its_field(self):
        # A text component's field holds 10 bytes unless txt_maxl says otherwise.
        self.add_text_component("t0", "abcdefghijk")
        self.assert_export_refused(r"pages/first\.page\.toml:9: attribute `txt` of component `t0` has 11 "
                                   r"bytes, and its limit, `txt_maxl`, is 10")

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
        self.assert_export_refused(r"pages/first\.page\.toml:9: attribute `path` of component `xp0` has "
                                   r"17 bytes, and its limit, `path_m`, is 8")
        edit_text(self.source / "pages" / "first.page.toml", "path_m = 8", "path_m = 17")
        export_dump(self.source, self.folder / "again")

    def test_bounds_the_editor_does_not_check(self):
        # The Editor compiled a video's or a sound's path past its path_m
        # while its from was 0, an internal file, and refused it with from 1,
        # a file on an SD card.
        page_file = self.source / "pages" / "first.page.toml"
        with open(page_file, "a", encoding="utf-8", newline="\n") as file:
            file.write('\n[[component]]\nname = "vd0"\ntype = "video"\nx = 0\ny = 100\nw = 50\n'
                       'h = 50\npath = "sd0/abcdefghij.video"\npath_m = 8\n'
                       '\n[[component]]\nname = "au0"\ntype = "audio"\n'
                       'path = "sd0/abcdefghij.wav"\npath_m = 8\n')
        export_dump(self.source, self.folder / "built")
        page = page_file.read_bytes()
        for name, kind, length in (("vd0", "video", 20), ("au0", "audio", 18)):
            with self.subTest(kind=kind):
                edit_text(page_file, 'type = "%s"\n' % kind, 'type = "%s"\nfrom = 1\n' % kind)
                self.assert_export_refused(
                    r"pages/first\.page\.toml:\d+: attribute `path` of component `%s` has %d bytes, and "
                    r"its limit, `path_m`, is 8" % (name, length))
                page_file.write_bytes(page)

    def test_a_data_records_texts_longer_than_their_bound(self):
        # The Editor's compile took a data record's format or dir up to 3
        # bytes longer than its bound. The build refuses any byte past the
        # bound, because that extra room is not documented.
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
            with self.subTest(attribute=attribute):
                with_record(attribute, 8, 8)
                export_dump(self.source, self.folder / attribute)
                with_record(attribute, 9, 8)
                self.assert_export_refused(
                    r"pages/first\.page\.toml:9: attribute `%s` of component `d0` has 9 bytes, and its "
                    r"limit, `%s_m`, is 8" % (attribute, attribute))

    def test_a_text_of_a_buttons_style(self):
        # The Editor refuses a text of style 4, 3D auto, which only a button
        # has: "styles.text4.style Out of range". A text's go from 0 to 3.
        self.add_text_component("t0", "x")
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write("style = 4\n")
        self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: style must be from 0 to 3")
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
        self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: style must be from 0 to 1")
        edit_text(page_file, "style = 2", "style = 1")
        export_dump(self.source, self.folder / "again")

    def test_a_component_narrower_or_lower_than_2(self):
        # The Editor says "Width can not be less than 2", then "Height can not
        # be less than 2", as it opens such a project. It then sets the side
        # back to its type's default, as it did for every type with a place,
        # which the build would not match.
        self.add_text_component("t0", "x")
        edit_text(self.source / "pages" / "first.page.toml", 'h = 30\ntxt = "x"', 'h = 1\ntxt = "x"')
        self.assert_export_refused(r"pages/first\.page\.toml:9: component `t0` is 100 by 1\. It must be "
                                   r"at least 2 by 2\.")
        edit_text(self.source / "pages" / "first.page.toml", 'h = 1\ntxt = "x"', 'h = 2\ntxt = "x"')
        export_dump(self.source, self.folder / "again")

    def test_a_component_too_small_in_a_table_of_every_attribute(self):
        # A table marked defaults = false lists every attribute; the check holds alike.
        defaults = tomllib.loads((self.source / "defaults.toml").read_text(encoding="utf-8"))
        values = dict(defaults["hotspot"]["attributes"], x=0, y=0, w=0, h=0)
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "zone"\ntype = "hotspot"\ndefaults = false\n'
                       + tomli_w.dumps(values))
        self.assert_export_refused(r"pages/first\.page\.toml:9: component `zone` is 0 by 0\. It must be "
                                   r"at least 2 by 2\.")

    def test_a_gauge_past_360_degrees(self):
        # The Editor refuses a gauge whose val is past 360: "page0.g14.valOut
        # of range".
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8") as file:
            file.write('\n[[component]]\nname = "dial"\ntype = "gauge"\nx = 0\ny = 0\nw = 100\n'
                       'h = 100\nval = 361\n')
        self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: val must be from 0 to 360")
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
                self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: %s must be from 0 to %d"
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
        self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: left must be from 0 to 1024")
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
                    self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: %s must be from "
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
        self.assert_export_refused(r"pages/first\.page\.toml:1: object 0: aph must be from 0 to 127")
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
                self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: tim must be from 80 "
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
        self.assert_export_refused(r"pages/first\.page\.toml:9: object 1: a keyboard is bound \(key 2\), "
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
            r"^pages/first\.page\.toml:49: the page has 6 waveforms, and the limit is 5$")
        # The page's whole count.
        self.add("waveform", 2)
        self.assert_export_refused(r"the page has 8 waveforms, and the limit is 5")

    def test_timers_and_scrolling_texts_together(self):
        self.add("timer", 12)
        export_dump(self.source, self.folder / "twelve")
        self.add("scrolling-text", 1)
        self.assert_export_refused(
            r"^pages/first\.page\.toml:57: the page has 13 timers and scrolling texts, and the limit is "
            r"12$")

    def test_a_mix_of_timers_and_scrolling_texts(self):
        self.add("timer", 6)
        self.add("scrolling-text", 7)
        self.assert_export_refused(r"the page has 13 timers and scrolling texts, and the limit "
                                   r"is 12")

    def test_animations_and_videos_together(self):
        self.add("gmov", 15)
        self.add("video", 2)
        self.assert_export_refused(
            r"^pages/first\.page\.toml:137: the page has 17 animations and videos, and the limit is 16$")

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
        with self.assertRaisesRegex(NxwrightError, r"pages[/\\]00-first\.txt: the page has 6 "
                                                   r"waveforms, and the limit is 5"):
            ProjectWriter(self.project, dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())


def add_pages_up_to(folder: Path, count: int):
    """Adds pages to a source folder until its app.toml lists `count`, each a
    copy of its first page, named more2, more3, and so on, with no code."""
    app_path = folder / "app.toml"
    app = tomllib.loads(app_path.read_text(encoding="utf-8"))
    first = app["pages"][0]
    text = (folder / "pages" / ("%s.page.toml" % first)).read_text(encoding="utf-8")
    for number in range(len(app["pages"]), count):
        name = "more%d" % number
        (folder / "pages" / ("%s.page.toml" % name)).write_text(
            text.replace('name = "%s"' % first, 'name = "%s"' % name, 1), encoding="utf-8")
        (folder / "pages" / ("%s.nx" % name)).write_text("", encoding="utf-8")
        app["pages"].append(name)
    app_path.write_text(app_text(app, written=None), encoding="utf-8", newline="\n")


class ComponentCountTest(SourceFolderTestCase):
    """The Nextion Editor's compile refuses a page of more than 250
    components, "Too many components", on every series, whatever their type
    or scope (Nextion Editor 1.68.2). The build refuses one too, at the
    first component past 250."""

    REFUSED = (r"^pages/first\.page\.toml:1009: the page has %d components, and the limit is 250\. "
               r"Remove %s, or move %s to another page\.$")

    def setUp(self):
        super().setUp()
        self.added = 0

    def add(self, count: int):
        """Adds `count` variables to the page first, named v0, v1, and so on."""
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            for _ in range(count):
                file.write('\n[[component]]\nname = "v%d"\ntype = "variable"\n' % self.added)
                self.added += 1

    def test_250_build_and_251_are_refused(self):
        self.add(250)
        export_dump(self.source, self.folder / "most")
        self.add(1)
        self.assert_export_refused(self.REFUSED % (251, "1 component", "it"))

    def test_the_message_gives_how_many_to_remove(self):
        self.add(253)
        self.assert_export_refused(self.REFUSED % (253, "3 components", "them"))

    def test_in_nxlang(self):
        switch_to_nxlang(self.source)
        self.add(251)
        self.assert_export_refused(self.REFUSED % (251, "1 component", "it"))

    def test_check_gives_the_component_s_line(self):
        self.add(251)
        page_file = self.source / "pages" / "first.page.toml"
        found = check_folder(folder_reader(self.source), lambda path: (self.source / path).is_file())
        errors = [finding for finding in found.errors()
                  if "the page has 251 components" in finding.message]
        self.assertEqual(len(errors), 1)
        lines = page_file.read_text(encoding="utf-8").split("\n")
        self.assertEqual((lines[errors[0].line - 1], lines[errors[0].line]),
                         ("[[component]]", 'name = "v250"'))

    def test_nxlang_s_components_count(self):
        # The page first, 249 components of its file, and 2 nxlang adds.
        names = ["first"] + ["v%d" % number for number in range(249)] + ["__s0", "__f0"]
        with self.assertRaises(NxwrightError) as raised:
            editor_limits.check_component_count(names, 2, "first.page.toml")
        self.assertEqual(str(raised.exception),
                         "first.page.toml: the page has 251 components, and the limit is 250. "
                         "nxlang adds 2 of them to run the page's code. Remove 1 component, or "
                         "move it to another page.")
        self.assertEqual(raised.exception.table, 0)
        editor_limits.check_component_count(names[:-1], 1, "first.page.toml")

    def test_the_build_of_a_dump(self):
        # A dump past the limit, as one of a project the Nextion Editor saved
        # but cannot compile: a 251st component, copied from the 250th.
        self.add(250)
        dump = self.folder / "most"
        export_dump(self.source, dump)
        page = dump / "pages" / "00-first.txt"
        text = page.read_text(encoding="utf-8")
        last = text[text.index("object 250 v249"):]
        more = re.sub(r"\bv249\b", "v250", last.replace("object 250 v249", "object 251 v250", 1))
        more = re.sub(r"(?m)^  id = 250$", "  id = 251", more)
        page.write_text(text.rstrip("\n") + "\n\n" + more, encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"pages[/\\]00-first\.txt: the page has 251 "
                                                   r"components, and the limit is 250"):
            ProjectWriter(self.project, dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())


class PageCountTest(SourceFolderTestCase):
    """The Nextion Editor's compile refuses a project of more than 251 pages,
    "Too many pages", on every series (Nextion Editor 1.68.2). The build
    refuses one too, at the line of app.toml that gives the 252nd page."""

    REFUSED = r"the project has 252 pages, and the limit is 251\. Remove 1 page\."

    def test_251_build_and_252_are_refused(self):
        add_pages_up_to(self.source, 251)
        export_dump(self.source, self.folder / "most")
        add_pages_up_to(self.source, 252)
        line = self.page_line("more251")
        self.assert_export_refused(r"^app\.toml:%d: %s$" % (line, self.REFUSED))

    def test_check_gives_the_line(self):
        add_pages_up_to(self.source, 252)
        found = check_folder(folder_reader(self.source), lambda path: (self.source / path).is_file())
        errors = [finding for finding in found.errors()
                  if "the project has 252 pages" in finding.message]
        self.assertEqual([(finding.file, finding.line) for finding in errors],
                         [("app.toml", self.page_line("more251"))])

    def test_the_build_of_a_dump(self):
        add_pages_up_to(self.source, 251)
        dump = self.folder / "most"
        export_dump(self.source, dump)
        pages = dump / "pages"
        (pages / "251-more251.txt").write_bytes((pages / "250-more250.txt").read_bytes())
        with self.assertRaisesRegex(NxwrightError, r"^the dump has 252 pages, and the limit is "
                                                   r"251\. Remove 1 page\.$"):
            ProjectWriter(self.project, dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())

    def page_line(self, page: str) -> int:
        """Returns the line, from 1, of app.toml giving the page `page`."""
        lines = (self.source / "app.toml").read_text(encoding="utf-8").split("\n")
        return lines.index('    "%s",' % page) + 1


class WriterLimitTest(SourceFolderTestCase):

    def test_nxwright_write_refuses_a_text_longer_than_its_field(self):
        edit_text(self.dump / "pages" / "00-first.txt", '  txt = "hello"\n',
                  '  txt = "hello"\n  txt_maxl = 3\n')
        with self.assertRaisesRegex(NxwrightError, r"pages[/\\]00-first\.txt: attribute `txt` of "
                                                   r"page `first` has 5 bytes, and its limit, "
                                                   r"`txt_maxl`, is 3"):
            ProjectWriter(self.project, self.dump, self.folder / "out.HMI").write()
        self.assertFalse((self.folder / "out.HMI").exists())


class ReferenceTest(SourceFolderTestCase):
    """Code in strict Nextion syntax in first.down, checked against the names
    of the small test project. setUp adds the down event, t0 on page first, and two texts on
    page second: t1, of local scope, and t2, of global scope."""

    def setUp(self):
        super().setUp()
        edit_text(self.source / "pages" / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(self.source / "pages" / "first.page.toml", "t0")
        add_component(self.source / "pages" / "second.page.toml", "t1", scope=0)
        add_component(self.source / "pages" / "second.page.toml", "t2", scope=1)

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def test_names_that_exist(self):
        # The build accepts each of these:
        # - the page's own components, with or without the page's name;
        # - the page itself;
        # - another page's components of global scope, after that page's name;
        # - a command's component;
        # - the array forms, on this page and on another, which pick their
        #   component when the code runs.
        # The checks skip strings and comments.
        self.write_code('t0.txt="a.b"', 'first.t0.txt="c"', "first.bco=0",
                        "second.t2.txt=t0.txt", "sys0=second.t2.txt_maxl", "vis t0,1",
                        "tsw 255,0", "b[1].txt=p[0].b[2].txt", "t0.txt=second.b[1].txt",
                        "sys0=first.bco // nothing.here")
        export_dump(self.source, self.folder / "again")

    def test_another_pages_component_of_local_scope(self):
        # On the T and K series, the Nextion Editor rejected page code that
        # read or assigned another page's component of local scope ("Invalid
        # Variables"). It compiled the same lines with a component of global
        # scope.
        for line in ("second.t1.txt=t0.txt", "t0.txt=second.t1.txt", "sys0=second.t1.txt_maxl"):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_export_refused(
                    r"first\.nx:2: `second\.t1`: `t1` has local scope, so it cannot be used "
                    r"in another page\. Give `t1` global scope \(`vscope = 1`\)\.")

    def test_another_pages_own_attribute(self):
        # The Nextion Editor rejected page code that read or assigned another
        # page's own attribute, whatever that page's vscope ("Invalid
        # Variables"). On page0 itself, it compiled `sys0=page0.bco`.
        for line in ("sys0=second.bco", "second.bco=0"):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_export_refused(
                    r"first\.nx:2: `second\.bco`: the attributes of a page can only be "
                    r"used in that page")

    def test_another_pages_component_of_local_scope_in_nxlang(self):
        switch_to_nxlang(self.source)
        self.write_code("second.t1.txt = t0.txt")
        self.assert_export_refused(r"first\.nx:2: `second\.t1`: `t1` has local scope")
        self.write_code("second.t2.txt = t0.txt")
        export_dump(self.source, self.folder / "nxlang")

    def test_an_unknown_component(self):
        self.write_code('t0.txt=""', 't9.txt=""')
        self.assert_export_refused(r"first\.nx:3: `t9` is neither a page nor a component "
                                   r"of this page")

    def test_an_unknown_page(self):
        self.write_code("t0.txt=third.t1.txt")
        self.assert_export_refused(r"first\.nx:2: `third` is neither a page nor a "
                                   r"component of this page")

    def test_an_unknown_component_of_another_page(self):
        self.write_code("t0.txt=second.t9.txt")
        self.assert_export_refused(r"first\.nx:2: page `second` has no component `t9`")

    def test_another_pages_component_without_its_page(self):
        self.write_code('t1.txt=""')
        self.assert_export_refused(r"first\.nx:2: `t1` is neither a page nor a component "
                                   r"of this page")

    def test_an_unknown_component_in_a_command(self):
        self.write_code("vis t9,1")
        self.assert_export_refused(r"first\.nx:2: `vis t9,1`: `t9` is neither a variable "
                                   r"nor a component of this page")

    def test_the_runner_refuses_what_the_build_refuses(self):
        for line, said in (('t9.txt=""', r"`t9` is neither a page nor a component of this page"),
                           ("second.t1.txt=t0.txt", r"`second\.t1`: `t1` has local scope"),
                           ("sys0=second.bco", r"`second\.bco`: the attributes of a page")):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r":2: " + said):
                    SourceFolderRunner(self.source).run("first", [("first", "down")])
        switch_to_nxlang(self.source)
        self.write_code("second.t1.txt = t0.txt")
        with self.assertRaisesRegex(NxwrightError,
                                    r":2: `second\.t1`: `t1` has local scope"):
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
        cases = [("d0.delete(0)", r"`d0\.delete` takes 2 arguments"),
                 ("d0.clear(1)", r"`d0\.clear` takes no arguments"),
                 ("d0.insert()", r"`d0\.insert` takes 1 argument"),
                 ('d0.up("x","1")', r"argument 2 of `d0\.up` must be a number, not text"),
                 ("d0.delete(t0.txt,1)", r"argument 1 of `d0\.delete` must be a number, not text"),
                 ('d0.insert(t0.txt+"^")', r"argument 1 of `d0\.insert` must be a single value")]
        for number, (line, message) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: " + message):
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
        cases = [("fs0.open()", "`fs0.open` takes 1 argument"),
                 ('fs0.open("sd0/a.txt","b")', "`fs0.open` takes 1 argument"),
                 ("fs0.read(t0.txt,0)", "`fs0.read` takes 3 arguments"),
                 ("fs0.read(t0.txt,0,1,2)", "`fs0.read` takes 3 arguments"),
                 ("fs0.write(t0.txt)", "`fs0.write` takes 3 arguments"),
                 ("fs0.write(t0.txt,0,1,2)", "`fs0.write` takes 3 arguments"),
                 ("fs0.close(1)", "`fs0.close` takes no arguments"),
                 ("fs0.find()", "`fs0.find` takes 1 argument"),
                 ('fs0.find("sd0/a.txt",n0.val)', "`fs0.find` takes 1 argument")]
        for number, (line, message) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError,
                                            r"first\.nx:2: %s$" % re.escape(message)):
                    export_dump(self.source, self.folder / ("refused%d" % number))

    def test_in_nxlang(self):
        # nxlang passes a file stream's calls through as written.
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  fs0.read(t0.txt, 0)\n",
                                                         encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `fs0\.read` takes 3 "
                                                   r"arguments"):
            export_dump(self.source, self.folder / "refused")


class MethodCallAsValueTest(_CodeOnFirstTestCase):
    """The lines with a method call in a value, or with a method alone,
    that the Nextion Editor 1.68.2 compiled, and the ones it rejected. The
    page `first` has a data record (d0), a file stream (fs0), a file browser
    (fb0), and an audio that plays a file (wav0)."""

    def setUp(self):
        super().setUp()
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "fs0"\ntype = "file-stream"\n'
                       '\n[[component]]\nname = "fb0"\ntype = "file-browser"\nx = 0\ny = 150\n'
                       'w = 200\nh = 100\n'
                       '\n[[component]]\nname = "wav0"\ntype = "audio"\nfrom = 1\n'
                       'path = "sd0/a.wav"\n')

    def rejected(self, cases: list):
        """Checks that the build rejects each line of `cases`. Each case is
        (line, message), where the message is the error's text after the file
        and the line number."""
        for number, (line, message) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError,
                                            r"first\.nx:2: %s$" % re.escape(message)):
                    export_dump(self.source, self.folder / ("rejected%d" % number))

    def test_the_calls_the_nextion_editor_compiles(self):
        self.write_code(
            "n0.val=fs0.open(t0.txt)", 'n0.val=fs0.open("sd0/a.txt")',
            'n0.val=fs0.find("sd0/a.txt")', "n0.val=fs0.read(t0.txt,0,3)",
            "n0.val=fs0.write(t0.txt,0,3)", "n0.val=fs0.close()", "n0.val+=fs0.open(t0.txt)",
            "n0.val=fs0.open(t0.txt)+1", "n0.val=1+fs0.close()",
            "n0.val=fs0.open(t0.txt)+fs0.find(t0.txt)", 'n0.val=d0.insert("a^b")',
            "n0.val=d0.delete(0,1)", 'n0.val=d0.up("a^b",0)', "n0.val=d0.clear()",
            "n0.val=fb0.up()", "n0.val=first.fs0.open(t0.txt)")
        export_dump(self.source, self.folder / "again")

    def test_a_call_of_what_is_no_method_is_rejected(self):
        self.rejected([
            ("n0.val=n0.val()", "`n0.val=n0.val()`: `n0.val` is not a method, it cannot be called"),
            ("n0.val=n0.val(5)+1",
             "`n0.val=n0.val(5)+1`: `n0.val` is not a method, it cannot be called"),
            ("n0.val=fs0.val(5)",
             "`n0.val=fs0.val(5)`: `fs0.val` is not a method, it cannot be called"),
            # `up` is a method of a data record and of a file browser, not
            # of a page.
            ("n0.val=first.up()",
             "`n0.val=first.up()`: `first.up` is not a method, it cannot be called")])

    def test_another_number_of_arguments_is_rejected(self):
        self.rejected([("n0.val=fs0.close(1)", "`fs0.close` takes no arguments"),
                      ("n0.val=fs0.open()", "`fs0.open` takes 1 argument"),
                      ("n0.val=fs0.read(5)", "`fs0.read` takes 3 arguments"),
                      ("n0.val=1+fs0.find()", "`fs0.find` takes 1 argument"),
                      ("n0.val=d0.clear(1)", "`d0.clear` takes no arguments"),
                      ("n0.val=d0.delete(t0.txt,1)",
                       "argument 1 of `d0.delete` must be a number, not text"),
                      ("n0.val=fb0.up(1)", "`fb0.up` takes no arguments"),
                      ("fb0.up(1)", "`fb0.up` takes no arguments"),
                      ("first.fs0.close(1)", "`first.fs0.close` takes no arguments")])

    def test_a_call_among_a_command_s_arguments(self):
        # The Nextion Editor compiled a method call there, and rejected the
        # same calls as in a value.
        self.write_code("cls fs0.close()", "vis t0,fs0.close()")
        export_dump(self.source, self.folder / "again")
        self.rejected([
            ("cls fs0.close(1)", "`fs0.close` takes no arguments"),
            ("cls n0.val()", "`cls n0.val()`: `n0.val` is not a method, it cannot be called"),
            ("n0.val(5)", "`n0.val(5)`: `n0.val` is not a method, it cannot be called")])

    def test_a_call_put_in_a_text_is_rejected(self):
        self.rejected([
            ("t0.txt=fs0.open(t0.txt)",
             "`t0.txt=fs0.open(t0.txt)`: the result of a call cannot be put in text"),
            ("t0.txt+=fs0.open(t0.txt)",
             "`t0.txt+=fs0.open(t0.txt)`: the result of a call cannot be put in text"),
            # A text other than a txt: an audio's path.
            ("wav0.path=fs0.open(t0.txt)",
             "`wav0.path=fs0.open(t0.txt)`: the result of a call cannot be put in text")])
        self.write_code("wav0.path=t0.txt")
        export_dump(self.source, self.folder / "again")

    def test_a_call_among_a_call_s_arguments_is_rejected(self):
        self.rejected([
            ("fs0.open(fs0.find(t0.txt))",
             "`fs0.open(fs0.find(t0.txt))`: an argument of `fs0.open` cannot be a call. "
             "Put the call's result in a variable first."),
            ("fs0.read(t0.txt,fs0.find(t0.txt),3)",
             "`fs0.read(t0.txt,fs0.find(t0.txt),3)`: an argument of `fs0.read` cannot be a "
             "call. Put the call's result in a variable first.")])

    def test_a_call_in_the_step_of_a_for_is_rejected(self):
        # The Nextion Editor rejected it ("Invalid Variables"). It compiled a
        # call in a for's start, and in the condition of an if and of a while.
        self.write_code("for(n0.val=fs0.close();n0.val<fs0.find(t0.txt);n0.val++)", "{", "}")
        export_dump(self.source, self.folder / "again")
        self.write_code("for(n0.val=0;n0.val<1;n0.val+=fs0.close())", "{", "}")
        with self.assertRaisesRegex(NxwrightError, re.escape(
                "first.nx:2: `for(n0.val=0;n0.val<1;n0.val+=fs0.close())`: the step of a `for` "
                "cannot contain a call. Use a `while` loop.")):
            export_dump(self.source, self.folder / "rejected")

    def test_a_folder_s_test_runs_a_call_as_a_value(self):
        # An `open` of a missing file gives 0, and a `close` gives 1, so
        # `n0.val` ends at 6. The last line, a method without its
        # parentheses, does nothing.
        self.write_code('n0.val=fs0.open("sd0/none.txt")+5', "n0.val+=fs0.close()", "fs0.close")
        values = SourceFolderRunner(self.source).run("first", [("first", "down")])
        self.assertEqual(values["n0.val"], 6)

    def test_a_method_alone_on_a_line(self):
        self.write_code("fs0.close", "fs0.open", "fs0.read", "d0.clear", "d0.up", "fb0.up",
                        "first.fs0.close")
        export_dump(self.source, self.folder / "again")

    def test_another_attribute_alone_on_a_line_is_rejected(self):
        self.rejected([(line, "`%s` is not a method, so it cannot be alone on a line" % line)
                      for line in ("n0.val", "t0.txt", "fs0.val", "first.up", "first.n0.val")])

    def test_on_a_page_without_a_type_that_has_methods(self):
        # T, K, and F have no type with a method, so every call on those series
        # is a call of a name that is not a method.
        objects = ObjectNames(frozenset({"page0", "n0"}), {"page0": {"page0": "page",
                                                                    "n0": "number"}}, "page0")
        with self.assertRaisesRegex(NxwrightError, "`n0.val` is not a method"):
            check_line("n0.val=n0.val()", objects, frozenset(), frozenset(), None, 1)


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
                        NxwrightError, r"first\.nx:2: `%s`: the first argument of `%s` must "
                                       r"be a single value\. Put the expression in a variable "
                                       r"first\.$" % (re.escape(line), line.split()[0])):
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
                        NxwrightError, r"first\.nx:2: `%s`: the text of `xstr` must be a "
                                       r"single value" % re.escape(head + text)):
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


class CommandComponentTest(_CodeOnFirstTestCase):
    """A command's component: the argument saying which component it acts
    on, as vis's first. The Nextion Editor refused each line refused here as
    it compiled ("Invalid Component ID"), and compiled each that builds."""

    def setUp(self):
        super().setUp()
        self.program = self.source / "program.nx"
        self.read_program()

    def read_program(self):
        """Keeps program.nx's lines, which write_program_line writes after."""
        text = self.program.read_text(encoding="utf-8")
        self.program_text = text + ("" if text.endswith("\n") else "\n")

    def switch_to_nxlang(self):
        """Switches the folder to nxlang, which compiles its event's code
        first, and so after `n0.val=0` alone."""
        self.write_code("n0.val=0")
        self.program.write_text(self.program_text, encoding="utf-8", newline="\n")
        switch_to_nxlang(self.source)
        self.read_program()

    def write_program_line(self, line: str) -> int:
        """Writes program.nx with `line` after its own lines, and returns the
        line's number."""
        self.program.write_text(self.program_text + line + "\n", encoding="utf-8",
                                newline="\n")
        return len(self.program_text.split("\n"))

    def assert_refused(self, where: str, line: str, words: str, built: str):
        with self.assertRaisesRegex(NxwrightError, r"%s: `%s`: .*%s"
                                    % (where, re.escape(line), re.escape(words))):
            export_dump(self.source, self.folder / built)

    def test_a_txt_as_a_component(self):
        for number, line in enumerate(("vis t0.txt,0", "tsw t0.txt,0", "click t0.txt,0",
                                       "ref t0.txt", "cfgpio 1,1,t0.txt",
                                       "move t0.txt,0,0,10,10,0,100", "setlayer t0.txt,n0",
                                       "setlayer n0,t0.txt")):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(r"first\.nx:2", line,
                                    "must be called with a component, not text",
                                    "refused%d" % number)
        self.switch_to_nxlang()
        self.write_code("vis t0.txt, 0")
        self.assert_refused(r"first\.nx:2", "vis t0.txt,0",
                            "`vis` must be called with a component, not text", "nxlang")

    def test_a_variable_as_a_component_in_an_event(self):
        self.write_code("vis sys0,0", "tsw sys1,1", "click sys2,0", "ref dim", "vis RED,0",
                        "cfgpio 1,1,sys0", "vis n0,0")
        export_dump(self.source, self.folder / "built")
        # nxlang's way to give one a computed component: a local, which it
        # writes as an int of program.s.
        self.switch_to_nxlang()
        self.write_code("var x = 1", "vis x, 0")
        export_dump(self.source, self.folder / "nxlang")
        # sys0 too, but only once program.nx declares it, as anywhere.
        self.assertIn("int sys0=0,sys1=0,sys2=0", self.program_text)
        self.program.write_text(self.program_text.replace("int sys0=0,sys1=0,sys2=0",
                                                          "int sys1=0,sys2=0"),
                                encoding="utf-8", newline="\n")
        self.write_code("vis sys0, 0")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: .*sys0"):
            export_dump(self.source, self.folder / "undeclared")

    def test_a_name_that_is_no_component_and_no_variable(self):
        for number, line in enumerate(("vis zz,0", "tsw zz,1", "click zz,0", "ref zz",
                                       "cfgpio 1,1,zz", "move zz,0,0,10,10,0,100",
                                       "setlayer zz,n0")):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(r"first\.nx:2", line, "`zz` is neither a variable nor "
                                    "a component of this page", "event%d" % number)
        self.write_code("n0.val=0")
        for number, line in enumerate(("vis zz,0", "tsw zz,1", "click zz,0", "ref zz",
                                       "cfgpio 1,1,zz", "move zz,0,0,10,10,0,100",
                                       "move t0,0,0,10,10,0,100", "setlayer zz,n0")):
            with self.subTest(line=line):
                line_number = self.write_program_line(line)
                self.assert_refused(r"program\.nx:%d" % line_number, line,
                                    "must be called with a component's ID or a variable",
                                    "program%d" % number)
        self.write_program_line("vis dim,0")
        export_dump(self.source, self.folder / "built")
        # nxlang refuses a name it does not know, as anywhere.
        self.switch_to_nxlang()
        self.write_code("vis zz, 0")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: unknown name `zz`"):
            export_dump(self.source, self.folder / "nxlang")
        self.write_code("n0.val = 0")
        line_number = self.write_program_line("vis zz, 0")
        with self.assertRaisesRegex(NxwrightError,
                                    r"program\.nx:%d: unknown name `zz`" % line_number):
            export_dump(self.source, self.folder / "nxlang-program")

    def test_the_screen_s_arrays_in_program_nx(self):
        for number, line in enumerate(("vis b[1],0", "vis b[sys0],1", "vis p[0].b[1],0",
                                       "tsw b[1],1", "click b[1],0", "ref b[1]",
                                       "move b[1],0,0,10,10,0,100", "cfgpio 1,1,b[1]",
                                       "setlayer b[1],n0")):
            with self.subTest(line=line):
                line_number = self.write_program_line(line)
                self.assert_refused(r"program\.nx:%d" % line_number, line,
                                    "cannot be used in program.nx. Use the component's ID or a "
                                    "variable.", "refused%d" % number)
        # In program.nx, nxlang turns `vis b[1], 0` into `vis 1,0`. The
        # Nextion Editor refuses `b[1]` in program.s, but takes `1`. Both
        # mean the component with ID 1 on the page that is showing: in the
        # simulator, each hid it. `p[0].b[1]` stays refused, as page 0 may
        # not be the page showing.
        self.switch_to_nxlang()
        self.write_program_line("vis b[1], 0")
        export_dump(self.source, self.folder / "nxlang")
        self.assertIn(b"vis 1,0", (self.folder / "nxlang" / "program.s").read_bytes())
        # A component given by arithmetic over the arrays is not one `b[i]`,
        # and is written as it is.
        self.write_program_line("vis b[1]+b[2], 0")
        export_dump(self.source, self.folder / "nxlang-sum")
        self.assertIn(b"vis b[1]+b[2],0",
                      (self.folder / "nxlang-sum" / "program.s").read_bytes())
        # An index other than a number or a name, which no probe tried as a
        # component, is not written as the component: the build refuses
        # `b[...]` there.
        line_number = self.write_program_line("vis b[sys0+1], 0")
        self.assert_refused(r"program\.nx:%d" % line_number, "vis b[sys0+1],0",
                            "`b[sys0+1]` cannot be used in program.nx", "nxlang-index")
        # The name written in place of `b[i]` is checked as any other.
        line_number = self.write_program_line("vis b[zz], 0")
        with self.assertRaisesRegex(NxwrightError,
                                    r"program\.nx:%d: unknown name `zz`" % line_number):
            export_dump(self.source, self.folder / "nxlang-unknown")
        line_number = self.write_program_line("vis p[0].b[1], 0")
        self.assert_refused(r"program\.nx:%d" % line_number, "vis p[0].b[1],0",
                            "`p[0].b[1]` cannot be used in program.nx", "nxlang-refused")

    def test_page_given_a_text(self):
        self.write_code('page "first"')
        self.assert_refused(r"first\.nx:2", 'page "first"',
                            "`page` must be called with a page's name without quotes, or its ID",
                            "refused")
        self.switch_to_nxlang()
        self.write_code('page "first"')
        self.assert_refused(r"first\.nx:2", 'page "first"',
                            "`page` must be called with a page's name without quotes, or its ID",
                            "nxlang")

    def test_page_given_a_name_that_is_no_page(self):
        # The Nextion Editor refused each of these when it compiled, and its
        # error gave the name. They are a name that is not defined, a
        # component's name, and a page's name in an expression or in another
        # letter case.
        whole_argument = "`second` is a page's name, which must be the whole argument of `page`"
        taken = ("page second", "page first", "page sys0", "page sys0+1", "page RED", "page dim",
                 "page 5", "page n0.val", "page appid&0x000000FF")
        # Each language's message lists what the name could have been, in a
        # page's file and in program.nx. In nxlang, program.nx cannot have
        # locals, so its list leaves them out.
        strict = "an int variable, a system variable, or a constant"
        for language, values, program_values in (
                ("nextion", strict, strict),
                ("nxlang", "a constant, a local, an int variable, or a system variable",
                 "a constant, an int variable, or a system variable")):
            if language == "nxlang":
                self.switch_to_nxlang()
            not_a_page = "`%s` is not a page, " + values
            refused = (("page zz", not_a_page % "zz"), ("page t0", not_a_page % "t0"),
                       ("page second+1", whole_argument), ("page 1+second", whole_argument),
                       ("page Second", "unknown page `Second`. Did you mean `second`?"),
                       # In an expression, a page's name would not work either.
                       ("page sys0+zz", "unknown name `zz`: not " + values))
            for number, (line, words) in enumerate(refused):
                with self.subTest(language=language, line=line):
                    self.write_code(line)
                    self.assert_refused(r"first\.nx:2", line, words,
                                        "%s-refused%d" % (language, number))
            for number, line in enumerate(taken):
                with self.subTest(language=language, line=line):
                    self.write_code(line)
                    export_dump(self.source, self.folder / ("%s-taken%d" % (language, number)))
            # An int variable of program.nx that is none of sys0 to sys2.
            lines = self.program_text.split("\n")
            declaration = next(place for place, text in enumerate(lines)
                               if text.startswith("int "))
            lines[declaration] += ",total=0"
            self.program.write_text("\n".join(lines), encoding="utf-8", newline="\n")
            self.write_code("page total")
            export_dump(self.source, self.folder / ("%s-int" % language))
            self.program.write_text(self.program_text, encoding="utf-8", newline="\n")
            self.write_code("n0.val=0")
            line_number = self.write_program_line("page zz")
            self.assert_refused(r"program\.nx:%d" % line_number, "page zz",
                                "`zz` is not a page, " + program_values,
                                "%s-program" % language)
            self.write_program_line("page second")
            export_dump(self.source, self.folder / ("%s-program-taken" % language))
            self.program.write_text(self.program_text, encoding="utf-8", newline="\n")
        # nxlang also takes a constant and a local.
        (self.source / "pages" / "first.nx").write_text(
            "const HOME = 1\n\non first.down:\n  var where = 1\n  page HOME\n  page where\n",
            encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "nxlang-constant-and-local")


class NumberArgumentTest(_CodeOnFirstTestCase):
    """A command's argument where it takes a number. The Nextion Editor
    refused each line refused here as it compiled, and compiled each that
    builds."""

    def assert_refused(self, line: str, words: str, built: str):
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `%s`: %s$"
                                    % (re.escape(line), re.escape(words))):
            export_dump(self.source, self.folder / built)

    def test_a_text_or_a_txt(self):
        for number, line in enumerate((
                "cls t0.txt", 'cls "1"', "add t0.txt,0,1", 'add 1,"a",1', "addt 1,0,t0.txt",
                'cle "a",0', "prints n0.val,t0.txt", 'prints n0.val,"x"',
                'pa_txt "a",t0.txt,t0.txt,1', 'pa_txt "a",t0.txt,0,"1"',
                'newfile "sd0/a.txt",t0.txt',
                'newfile "sd0/a.txt","1"', 'rdfile "sd0/a.txt",t0.txt,10,0',
                'rdfile "sd0/a.txt","0",10,0')):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, "`%s` must be called with a number, not text"
                                    % line.split()[0], "refused%d" % number)
        # pa_txt's second argument is a text, which takes either.
        self.write_code('pa_txt "a","1",0,1', 'pa_txt "a",t0.txt,0,1', "cls 1", "add 1,0,n0.val",
                        "prints t0.txt,n0.val")
        export_dump(self.source, self.folder / "built")

    def test_an_operand_the_nextion_editor_does_not_read(self):
        lines = [(line % form, form) for form in ("RED+*1", "5a", "1_000", "-sys0")
                 for line in ("cls %s", "add 1,0,%s", 'newfile "sd0/a.txt",%s',
                              'rdfile "sd0/a.txt",%s,10,0', "prints n0.val,%s")]
        for number, (line, form) in enumerate(lines):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, "`%s` is not a valid value" % form,
                                    "refused%d" % number)
        self.write_code("cls -5", "add 1,0,sys0+1", "cls 0x0001")
        export_dump(self.source, self.folder / "built")

    def test_nxlang_computes_a_minus_before_a_name_first(self):
        self.write_code("n0.val=0")
        switch_to_nxlang(self.source)
        self.write_code("cls -n0.val")
        export_dump(self.source, self.folder / "built")
        page = next((self.folder / "built" / "pages").glob("*-first.txt"))
        self.assertRegex(page.read_text(encoding="utf-8"),
                         r"\| (__g\w+)=0-n0\.val\n\s*\| cls \1\n")
        # Any value nxlang reads and the Nextion Editor does not, as a minus
        # before a name inside arithmetic, in each place of the line.
        self.write_code("add 1,-n0.val,2*-n0.val // two", "cls -n0.val+1")
        export_dump(self.source, self.folder / "more")
        page = next((self.folder / "more" / "pages").glob("*-first.txt"))
        written = page.read_text(encoding="utf-8")
        self.assertRegex(written, r"\| add 1,__g\w+,__g\w+ // two\n")
        self.assertRegex(written, r"\| cls __g\w+\n")
        # What nxlang does not read either is refused as in strict syntax.
        not_text = "`cls` must be called with a number, not text"
        for number, (line, words) in enumerate((("cls t0.txt", not_text), ('cls "1"', not_text),
                                                ("cls 5a", "`5a` is not a valid value"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, words, "nxlang%d" % number)
        # program.nx has no temporaries, so the line stays refused there.
        self.write_code("n0.val = 0")
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        text += "" if text.endswith("\n") else "\n"
        program.write_text(text + "cls -sys0\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"program\.nx:%d: `cls -sys0`: `-sys0` is "
                                    r"not a valid value" % len(text.split("\n"))):
            export_dump(self.source, self.folder / "program")


class OneOperandArgumentTest(_CodeOnFirstTestCase):
    """An expression where a command takes one operand. The Nextion Editor
    refused each line refused here as it compiled ("Invalid Variables"), on
    the series given, and compiled each that builds."""

    # Each series' model, with the lines refused on it.
    REFUSED = {
        "NX4832T035": [
            "pa_q t0.txt,n0.val+1", "pa_q sys0+1,sys1", 'pa_txt "a",sys0+1,0,1',
            "crcputs 0x01+1,4", "getv sys0+1", "fstr sys0+1,0,0", "strsize 0,0,sys0+1",
            "ucopy sys0+1,0,2,0", "i sys0+1,0,0,0", "i 0,sys0+1,0,0", "nstr sys0+1,0x01,1000",
            "zstr 0,0,0,0,sys0+1", "qrcode 0,0,0,0,0,0,0,sys0+1",
            "cov n0.val,sys0+1,0", "strlen t0.txt,sys0+1", "covx n0.val,n0.val+1,0,0",
            "strlen sys0+1,sys1", "substr sys0+1,t0.txt,0,1", 'spstr sys0+1,t0.txt,"a",0',
            "btlen sys0+1,sys1", 'spstr t0.txt,t0.txt,"a"+"b",0', 'getv t0.txt+"a"',
            'strlen t0.txt+"a",sys1'],
        "NX8048P050": [
            "delfile sys0+1", 'findfile "sd0/a.txt",sys0+1', "gets n0.val,sys0+1",
            "sets sys0+1,0", "sets 0,sys0+1", 'delfile t0.txt+"a"', 'sets 0,t0.txt+"a"'],
        "NX4832K035": ["wepo sys0+1,0", "repo sys0+1,0", 'wepo t0.txt+"a",0'],
        "NX4832F035": ["piccolor 0,0,0,sys0+1", 'piccolor 0,0,0,t0.txt+"a"'],
    }
    # Each series' model, with the lines of a minus before a name refused on it.
    MINUS_REFUSED = {
        "NX4832T035": [
            "pa_q t0.txt,-sys0", "pa_q -sys0,sys1", 'pa_txt "a",-sys0,0,1', "crcputs -sys0,0",
            "getv -sys0", "getv -n0.val", "getv -RED", "fstr -sys0,0,0", "strsize 0,0,-sys0",
            "ucopy -sys0,0,2,0", "i -sys0,t0.txt,1,2", "i t0.txt,-sys0,1,2",
            "nstr -sys0,0x01,1000", "zstr 0,0,0,0,-sys0", "qrcode 0,0,0,0,0,0,0,-sys0",
            "cov n0.val,-sys0,0", "strlen t0.txt,-sys0", "covx n0.val,-sys0,0,0",
            "strlen -sys0,sys1", "substr -sys0,t0.txt,0,1", 'spstr -sys0,t0.txt,"a",0',
            "spstr t0.txt,t0.txt,-sys0,0", "btlen -sys0,sys1", "get -sys0", "print -sys0",
            "print -RED", "prints -sys0,0", "covx -sys0,t0.txt,0,0",
            "xstr 0,0,100,30,0,RED,BLACK,0,0,1,-sys0", "getv 1+-sys0", "strlen 1*-sys0,sys1"],
        "NX8048P050": ["delfile -sys0", 'findfile "sd0/a.txt",-sys0', "gets n0.val,-sys0",
                       "sets -sys0,0", "sets 0,-sys0"],
        "NX4832K035": ["wepo -sys0,0", "repo -sys0,0"],
        "NX4832F035": ["piccolor 0,0,0,-sys0"],
    }

    def setUp(self):
        super().setUp()
        # A data record is of the Intelligent series alone.
        edit_text(self.source / "pages" / "first.page.toml",
                  '\n[[component]]\nname = "d0"\ntype = "data-record"\nx = 0\ny = 40\n'
                  'w = 200\nh = 100\n', "")

    def use_screen(self, model: str):
        app = self.source / "app.toml"
        data = tomllib.loads(app.read_text(encoding="utf-8"))
        data["screen"] = model
        app.write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")

    def assert_refused(self, line: str, built: str, file: str = r"first\.nx", place: int = 2):
        # A command of ONE_OPERAND_FIRST says "the first argument of `get`
        # must be a single value", the others "`getv` must be called with a
        # single value".
        with self.assertRaisesRegex(NxwrightError, r"%s:%d: `%s`: .*`%s` must be (called "
                                    r"with )?a single value"
                                    % (file, place, re.escape(line), line.split()[0])):
            export_dump(self.source, self.folder / built)

    def test_an_expression(self):
        number = 0
        for model, lines in self.REFUSED.items():
            self.use_screen(model)
            for line in lines:
                with self.subTest(line=line):
                    self.write_code(line)
                    number += 1
                    self.assert_refused(line, "refused%d" % number)
        # One operand in each place builds.
        self.use_screen("NX4832T035")
        self.write_code("ucopy -1,0,2,0", 'strlen "a",n0.val', "cov n0.val,t0.txt,0",
                        'spstr t0.txt,t0.txt,"a",0', "crcputs t0.txt,0", "getv b[1].txt")
        export_dump(self.source, self.folder / "built")

    def test_a_minus_before_a_name(self):
        number = 0
        for model, lines in self.MINUS_REFUSED.items():
            self.use_screen(model)
            for line in lines:
                with self.subTest(line=line):
                    self.write_code(line)
                    number += 1
                    self.assert_refused(line, "refused%d" % number)
        # xstr has a message of its own.
        self.use_screen("NX4832T035")
        self.write_code("xstr 0,0,100,30,0,RED,BLACK,0,0,1,-sys0")
        with self.assertRaisesRegex(NxwrightError, "the text of `xstr` must be a single value"):
            export_dump(self.source, self.folder / "xstr")
        # A minus before a number, and a colour's name alone, build.
        self.write_code("getv -5", "print -5", "getv RED")
        export_dump(self.source, self.folder / "built")

    def test_the_advice_fits_the_place(self):
        self.use_screen("NX4832T035")
        # A place the command reads, a place it writes, and a place of an
        # undocumented command, which gets no advice.
        for number, (line, advice) in enumerate((
                ('strlen t0.txt+"a",n0.val', ". Put the expression in a variable first."),
                ("strlen -sys0,n0.val", ". Put the expression in a variable first."),
                ("cov n0.val,sys0+1,0", ". Use the variable that will take the result."),
                ("getv sys0+1", ""))):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, re.escape(
                        "must be called with a single value" + advice) + "$"):
                    export_dump(self.source, self.folder / ("advice%d" % number))

    def written_code(self, built: str) -> str:
        export_dump(self.source, self.folder / built)
        page = next((self.folder / built / "pages").glob("*-first.txt"))
        return page.read_text(encoding="utf-8")

    def test_nxlang_computes_an_expression_a_command_only_reads_first(self):
        # The NX8048P050 has each of these commands.
        self.use_screen("NX8048P050")
        self.write_code("n0.val=0")
        switch_to_nxlang(self.source)
        self.write_code('strlen t0.txt + "a", n0.val', 'spstr t0.txt, t0.txt, "a" + "b", 0',
                        "crcputs n0.val + 1, 0 // sum", "wepo n0.val * 2, 0",
                        'delfile "sd0/" + t0.txt', 'substr t0.txt + "b", t0.txt, 0, 1',
                        'btlen t0.txt + "c", n0.val')
        written = self.written_code("built")
        self.assertRegex(written, r'\| (__s\w+)\.txt=t0\.txt\+"a"\n\s*\| strlen \1\.txt,n0\.val\n')
        self.assertRegex(written, r'\| (__s\w+)\.txt="a"\+"b"\n\s*\| spstr t0\.txt,t0\.txt,'
                                  r'\1\.txt,0\n')
        self.assertRegex(written, r"\| (__g\w+)=n0\.val\+1\n\s*\| crcputs \1,0 // sum\n")
        self.assertRegex(written, r"\| (__g\w+)=n0\.val\*2\n\s*\| wepo \1,0\n")
        self.assertRegex(written, r'\| (__s\w+)\.txt="sd0/"\+t0\.txt\n\s*\| delfile \1\.txt\n')
        self.assertRegex(written, r'\| (__s\w+)\.txt=t0\.txt\+"b"\n\s*\| substr \1\.txt,t0\.txt,'
                                  r'0,1\n')
        self.assertRegex(written, r'\| (__s\w+)\.txt=t0\.txt\+"c"\n\s*\| btlen \1\.txt,n0\.val\n')
        # Two places of one line take a temporary each.
        self.write_code('spstr t0.txt + "a", t0.txt, "a" + "b", 0')
        self.assertRegex(self.written_code("two"),
                         r"\| spstr (__s\w+)\.txt,t0\.txt,(?!\1)__s\w+\.txt,0\n")
        # A place the command writes, a place of an undocumented command, and
        # wepo's text, whose temporary would write 256 bytes, stay refused.
        # The build's message quotes the line without its spaces.
        for number, line in enumerate(("cov n0.val,n0.val+1,0", "getv n0.val+1",
                                       'wepo t0.txt+"a",0')):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, "nxlang%d" % number)
        # program.nx has no temporaries, so each line stays refused there.
        self.write_code("n0.val = 0")
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        text += "" if text.endswith("\n") else "\n"
        for number, line in enumerate((
                "wepo sys0+1,0", "crcputs sys0+1,0", "delfile sys0+1", "strlen sys0+1,sys1",
                "substr sys0+1,sys1,0,1", 'spstr sys0+1,sys1,"a",0', 'spstr "a",sys1,"a"+"b",0',
                "btlen sys0+1,sys1")):
            with self.subTest(line=line):
                program.write_text(text + line + "\n", encoding="utf-8", newline="\n")
                self.assert_refused(line, "program%d" % number, r"program\.nx",
                                    len(text.split("\n")))

    def test_nxlang_computes_a_minus_before_a_name_a_command_only_reads_first(self):
        # The NX8048P050 has each of these commands.
        self.use_screen("NX8048P050")
        self.write_code("n0.val=0")
        switch_to_nxlang(self.source)
        self.write_code("strlen -n0.val, n0.val", "spstr t0.txt, t0.txt, -n0.val, 0",
                        "crcputs -n0.val, 0", "wepo -n0.val, 0", "delfile -n0.val",
                        "substr -n0.val, t0.txt, 0, 1", "btlen -n0.val, n0.val",
                        "xstr 0, 0, 100, 30, 0, RED, BLACK, 0, 0, 1, -n0.val")
        written = self.written_code("built")
        for line in ("strlen %s,n0.val", "spstr t0.txt,t0.txt,%s,0", "crcputs %s,0",
                     "wepo %s,0", "delfile %s", "substr %s,t0.txt,0,1", "btlen %s,n0.val",
                     "xstr 0,0,100,30,0,RED,BLACK,0,0,1,%s"):
            with self.subTest(line=line):
                self.assertRegex(written, r"\| (__g\w+)=0-n0\.val\n\s*\| %s\n"
                                 % re.escape(line).replace("%s", r"\1"))
        # A place the command writes and a place of an undocumented command
        # stay refused. The build's message quotes the line without its spaces.
        for number, line in enumerate(("cov n0.val,-n0.val,0", "getv -n0.val")):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, "nxlang%d" % number)
        # program.nx has no temporaries, so each line stays refused there.
        self.write_code("n0.val = 0")
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        text += "" if text.endswith("\n") else "\n"
        for number, line in enumerate((
                "wepo -sys0,0", "crcputs -sys0,0", "delfile -sys0", "strlen -sys0,sys1",
                "substr -sys0,sys1,0,1", 'spstr -sys0,sys1,"a",0', 'spstr "a",sys1,-sys0,0',
                "btlen -sys0,sys1")):
            with self.subTest(line=line):
                program.write_text(text + line + "\n", encoding="utf-8", newline="\n")
                self.assert_refused(line, "program%d" % number, r"program\.nx",
                                    len(text.split("\n")))
        # nxlang refuses xstr's text itself, as it computes that text before
        # the build checks the line.
        program.write_text(text + "xstr 0,0,100,30,0,RED,BLACK,0,0,1,-sys0\n", encoding="utf-8",
                           newline="\n")
        with self.assertRaisesRegex(NxwrightError, r"program\.nx:%d: this line requires a temporary "
                                    r"variable, which program\.nx cannot have"
                                    % len(text.split("\n"))):
            export_dump(self.source, self.folder / "program-xstr")


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
        self.assert_export_refused(r"first\.nx:2: `extra\.val=5`: text `extra` has no "
                                   r"attribute `val`")


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

    # The lines the build stops at, by the words of its message.
    REFUSED = {
        "text cannot be put in a number": [
            "n0.val=t0.txt", 'n0.val="a"', 't0.pco="a"', "t0.pco=t0.txt", 't0.font="a"',
            'sys0="a"', "n0.val+=t0.txt", "n0.val-=t0.txt", "n0.val=n0.val+t0.txt",
            "n0.val=t0.txt+t0.txt"],
        "a number cannot be put in text": [
            "t0.txt=5", "t0.txt=n0.val", "va0.txt=5", "t0.txt=0X10"],
        "the operator `*` cannot be used on text": ["t0.txt*=2"],
        "text and a number cannot be joined with `+`": ["t0.txt+=5", "t0.txt=t0.txt+5"],
        "is not a valid escape": [
            r't0.txt="a\q"', r't0.txt="a\nb"', r't0.txt="a\tb"', r'print "a\qb"',
            r'newfile "sd0\a.txt",10'],
        "`va0.val` cannot be used while `va0` contains text": ['va0.val="a"', "n0.val=va0.val"],
        "`va1.txt` cannot be used while `va1` contains a number": [
            'va1.txt="a"', "t0.txt=va1.txt"],
        "plays an internal file (its `from` is 0)": ['vd0.path="sd0/a.video"', "t0.txt=au0.path"],
        "`gm1.vid` cannot be used while `gm1.from` is 1": ["gm1.vid=0", "sys0=gm1.vid"],
        "`vd1.vid` cannot be used while `vd1` plays a file of an SD card (its `from` is 1)": [
            "sys0=vd1.vid"],
    }

    def test_the_lines_the_editor_refuses(self):
        number = 0
        for words, lines in self.REFUSED.items():
            for line in lines:
                with self.subTest(line=line):
                    self.write_code(line)
                    number += 1
                    with self.assertRaisesRegex(
                            NxwrightError, r"first\.nx:2: `%s`: .*%s$"
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
        for number, (line, words) in enumerate((
                ("n0.val=second.vs.val", "`vs.val` cannot be used while `vs` contains text"),
                ('vd.txt="a"', "`vd.txt` cannot be used while `vd` contains a number"))):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: .*%s$"
                                            % re.escape(words)):
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
                                       "cfguart 1,2,3", "cuts 1,2", "xnum 1,2",
                                       "doevents 1", "ref_stop 1", "ref_star 1",
                                       "com_stop 1", "com_star 1", "page 1,2", "page")):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx:2: `%s`: `%s` takes (no|\d+) arguments?, "
                        r"not \d+$" % (re.escape(line), line.split()[0])):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # Its own number, a quoted comma within one, a command the table
        # lacks, which takes any number, and commands that take none.
        self.write_code("cls 1", 'print "a,b"', "crcputh 0A 0B", "crcrest 1,0xffff",
                        'rdfile "sd0/a.txt",0,1,0', 'twfile "sd0/a.txt",5', "rest", "touch_j",
                        "code_c", "i 1,2,3,4", "beepset 1,2", "meup 1,2", "gets 1,2",
                        "cfguart 1,2,3,4", "cuts 1,2,3,4,5,6,7", "xnum 1,2,3,4,5,6,7,8,9,10",
                        "doevents", "ref_stop", "ref_star", "com_stop", "com_star", "page 0")
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
        # As the Nextion Editor's compile refused each.
        value = ("the value is not valid. A value is made of numbers, texts, names, and "
                 "method calls, joined by operators. Parentheses are only valid around a "
                 "call's arguments.")
        end, semicolon = "this line must end with `)`", ("text in a `for` header cannot contain "
                                                         "a semicolon. Use a `while` loop.")
        cases = [("n0.val==2", value), ("n0.val=2+", value), ("n0.val=+2", value),
                 ("n0.val=2++3", value), ("n0.val=-n0.val", value), ("n0.val=(1+2)", value),
                 ("n0.val=1.5", value), ("n0.val=2*-n0.val", value),
                 ("n0.val=", "the assignment has no value"),
                 ("if(n0.val==1", end), ("while(n0.val<3", end),
                 ("for(n0.val=0;n0.val<3;n0.val++", end),
                 # A text holding a semicolon, in each part of a for's head.
                 ('for(n0.val=0;t0.txt!="a;b";n0.val++)', semicolon),
                 ('for(t0.txt="a;b";n0.val<1;n0.val++)', semicolon),
                 ('for(n0.val=0;n0.val<1;t0.txt="a;b")', semicolon)]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                block = [line, "{", "}"] if "(" in line and not line.startswith("n0") else [line]
                self.write_code(*block)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `%s`: %s$"
                                            % (re.escape(line), re.escape(words))):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # An else if's head too, refused alike.
        self.write_code("if(n0.val==1)", "{", "}else if(n0.val==2", "{", "}")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:4: `\}else if\(n0\.val==2`: "
                                    r"this line must end with `\)`$"):
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
        unknown = "unknown name `%s`: not an int variable, a system variable, or a constant"
        cases = [(line, unknown % "abc") for line in (
            "n0.val=abc+1", "n0.val=abc", "n0.val=n0.val+abc", "n0.val+=abc", "t0.txt=abc",
            "n0.val=b[abc].val", "b[abc].val=1", "if(abc==1)", "while(abc<1)",
            "for(sys0=0;sys0<abc;sys0++)", "get abc", "print abc", "prints abc,0",
            "covx abc,t0.txt,0,0")]
        cases += [("n0.val=val", unknown % "val"),
                  ("n0.val=n0+1", "`n0` is a component. Use one of its attributes."),
                  ("n0.val=first+1", "`first` is a page. Use one of its attributes."),
                  ("n0.val=red", "unknown name `red`. Did you mean `RED`?")]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                block = [line, "{", "}"] if line[:2] in ("if", "wh", "fo") else [line]
                self.write_code(*block)
                with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `%s`: %s$"
                                            % (re.escape(line), re.escape(words))):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code("if(sys0==1)", "{", "}else if(abc==1)", "{", "}")
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:4: `\}else if\(abc==1\)`: "
                                                   r"unknown name `abc`"):
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
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: .*`\\q` is not a valid "
                                                   r"escape"):
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
                        NxwrightError, r"first\.nx:%d: .*in a condition, text cannot end "
                                       r"with an escaped backslash" % (lines.index(refused) + 2)):
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
        cases = [("sys0=t0.pic", "`t0.pic` cannot be used while `t0.sta` is 1"),
                 ("sys0=t1.bco", "`t1.bco` cannot be used while `t1.sta` is 3"),
                 ("t1.picc=0", "`t1.picc` cannot be used while `t1.sta` is 3"),
                 ("sys0=t0.borderw", "`t0.borderw` cannot be used while `t0.style` is 0"),
                 ("sys0=t0.first", "`t0.first` cannot be used while `t0.effect` is 0"),
                 ("sys0=first.pic", "`first.pic` cannot be used while `first.sta` is 1"),
                 ("sys0=s2.pco2", "`s2.pco2` cannot be used while `s2.ch` is 2"),
                 ("sys0=au1.vid", "`au1.vid` cannot be used while `au1` plays a file of an SD "
                                  "card (its `from` is 1)"),
                 ("sys0=vd0.path_m", "`vd0.path_m` cannot be used while `vd0` plays an internal "
                                     "file (its `from` is 0)"),
                 ("sys0=va1.txt_maxl", "`va1.txt_maxl` cannot be used while `va1` contains a "
                                       "number")]
        for number, (line, why) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                with self.assertRaisesRegex(
                        NxwrightError, r"first\.nx:2: `%s`: %s$"
                                       % (re.escape(line), re.escape(why))):
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
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `%s`: %s$"
                                    % (re.escape(line), pattern)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_a_name_the_type_does_not_have(self):
        # Read or assigned. Names differ by their letters' case. A timer has
        # no place, so no endx.
        cases = [("sys0=n0.vall", "number `n0` has no attribute `vall`"),
                 ('n0.txt="a"', "number `n0` has no attribute `txt`"),
                 ("t0.txt=n0.txt", "number `n0` has no attribute `txt`"),
                 ("sys0=n0.Val", "number `n0` has no attribute `Val`"),
                 ("sys0=t0.objWid", "text `t0` has no attribute `objWid`"),
                 ("sys0=tm0.endx", "timer `tm0` has no attribute `endx`"),
                 ("sys0=first.vall", "page `first` has no attribute `vall`"),
                 ("sys0=second.n9.vall", "number `second.n9` has no attribute `vall`")]
        for number, (line, words) in enumerate(cases):
            with self.subTest(line=line):
                self.assert_refused(line, re.escape(words), number)

    def test_assignments_the_editor_refuses(self):
        # endx and endy, as id, type, and objname; and each method, which
        # code calls, as d0.insert("a^b").
        for number, attribute in enumerate(("endx", "endy")):
            with self.subTest(attribute=attribute):
                self.assert_refused("n0.%s=3" % attribute,
                                    "attribute `%s` cannot be changed in code" % attribute,
                                    number)
        methods = [("d0", "data-record", name) for name in ("insert", "delete", "up", "clear")]
        methods += [("fb0", "file-browser", "up")]
        methods += [("fs0", "file-stream", name)
                    for name in ("open", "read", "write", "close", "find")]
        for number, (name, kind, method) in enumerate(methods, 2):
            with self.subTest(method="%s.%s" % (name, method)):
                self.assert_refused("%s.%s=1" % (name, method),
                                    "`%s` is a method, it cannot be assigned" % method, number)

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
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `sys0=n0\.vall`: number "
                                                   r"`n0` has no attribute `vall`"):
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
                            file: str = r"first\.nx:2"):
        with self.assertRaisesRegex(NxwrightError, r"%s: `%s`: %s" % (file, re.escape(line),
                                                                      problem)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_a_first_word_the_editor_lacks(self):
        for number, (line, problem) in enumerate((
                ("zork b0,1", r"unknown command `zork`$"),
                ("sys0", r"unknown command `sys0`$"),
                ('dir "sd0/"', r"unknown command `dir`$"),
                ("CLS BLUE", r"unknown command `CLS`\. Did you mean `cls`\?$"),
                ("Zork 1", r"unknown command `Zork`$"),
                ("movelayer t0,n0", r"unknown command `movelayer`$"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_line_refused(line, problem, number)

    def test_a_word_nxlang_adds_in_a_strict_folder(self):
        # The error shows the line without a "{" at its end.
        for number, (line, shown, word) in enumerate((
                ("var total = 1", "var total = 1", "var"),
                ("const LIMIT = 3", "const LIMIT = 3", "const"),
                ("function twice():", "function twice():", "function"),
                ("switch (sys0) {", "switch (sys0)", "switch"),
                ("switch(sys0) {", "switch(sys0)", "switch"),
                ("case 1:", "case 1:", "case"),
                ("break", "break", "break"),
                ("continue", "continue", "continue"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_line_refused(
                    shown, r"`%s` can only be used with nxlang but this project uses strict "
                           r"Nextion syntax$" % word, number)

    def test_a_word_nxlang_adds_in_a_macro(self):
        # Macros are always in strict Nextion syntax, even in a folder in nxlang,
        # so switching would not help.
        (self.source / "macros.nx").write_text("macro probe:\n  var total = 1\n",
                                               encoding="utf-8", newline="\n")
        self.assert_line_refused("var total = 1", r"unknown command `var`$", 0,
                                 r"macros\.nx:2")

    def test_every_command_of_the_editor_builds(self):
        self.assertEqual({first_word(line) for line in self.EVERY_COMMAND} - {None},
                         EDITOR_COMMANDS - SERIES_LACKED_COMMANDS["P"])
        self.write_code(*self.EVERY_COMMAND)
        export_dump(self.source, self.folder / "built")

    def test_a_command_written_alone(self):
        # As the Editor refused each command that takes arguments, written
        # alone.
        for number, line in enumerate(("lcd_dev", "cls", "cuts", "add")):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_line_refused(line, r"`%s` takes \d+ arguments?, not 0$" % line,
                                         number)
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
        # The int goes before program.nx's other code, as the Nextion Editor
        # takes declarations only before other code.
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8").replace(
            EDITOR_PROGRAM_DECLARATION, EDITOR_PROGRAM_DECLARATION + "\nint display_mode=1", 1)
        program.write_text(text + ("" if text.endswith("\n") else "\n")
                           + "if(display_mode==1)\n{\n"
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
                        NxwrightError, r"program\.nx:%d: `%s`: in program\.nx, `%s` must be "
                        r"called with a component's ID or a variable$"
                        % (line_number, re.escape(line), line.split()[0])):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        program.write_text(written + "vis 1,0\nvis sys0,0\n", encoding="utf-8", newline="\n")
        export_dump(self.source, self.folder / "built")

    def test_a_components_attribute_in_program_nx(self):
        # program.s belongs to no page, so a component's attribute there
        # needs its page's name, and the component must be of global scope.
        # On the T series, the Nextion Editor refused an attribute named
        # without its page: "Invalid Variables" in an assignment, "Invalid
        # Page ID" given to page, and "Invalid Component ID" given to vis
        # and tsw. It refused one of local scope with its page's name too,
        # "Invalid Variables". Here n0 is of local scope, n2 is of global
        # scope, and t1 is on page second.
        add_component(self.source / "pages" / "second.page.toml", "t1")
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as page:
            page.write('\n[[component]]\nname = "n2"\ntype = "number"\nx = 0\ny = 160\n'
                       'w = 200\nh = 100\nvscope = 1\n')
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        written = text + ("" if text.endswith("\n") else "\n")
        line_number = len(written.split("\n"))
        its_page = "`%s`: in program.nx, a component must include its page, as in `<page>.%s`"
        for number, (line, said) in enumerate((
                ("sys0=n0.val", its_page % ("n0.val", "n0.val")),
                ("sys0=n2.val", its_page % ("n2.val", "n2.val")),
                ("sys0=1+t1.txt_maxl", its_page % ("t1.txt_maxl", "t1.txt_maxl")),
                ("page n0.val", its_page % ("n0.val", "n0.val")),
                ("vis n0.val,0", its_page % ("n0.val", "n0.val")),
                ("tsw n2.val,1", its_page % ("n2.val", "n2.val")),
                ("sys0=first.n0.val", "`first.n0.val`: `n0` has local scope, so it cannot be "
                                      "used in program.nx. Give `n0` global scope "
                                      "(`vscope = 1`)."))):
            with self.subTest(line=line):
                program.write_text(written + line + "\n", encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(
                        NxwrightError, r"program\.nx:%d: %s$"
                        % (line_number, re.escape(said))):
                    export_dump(self.source, self.folder / ("refused%d" % number))
        # A component of global scope with its page's name builds, as the
        # Nextion Editor compiled `sys0=page0.n2.val`. A quoted text that
        # contains such a name is not a name, and builds too.
        program.write_text(written + 'sys0=first.n2.val\nprint "n0.val"\n', encoding="utf-8",
                           newline="\n")
        export_dump(self.source, self.folder / "built")

    def test_a_component_without_its_page_in_program_nx_is_not_searched_for(self):
        # The message is the same whether several pages have the component,
        # as n0 here, or none does, as zz: no page is searched for it.
        pages, globals_ = {"first": {"n0": "number"}, "second": {"n0": "number"}}, \
            {"first": frozenset(), "second": frozenset({"n0"})}
        for line, name in (("sys0=n0.val", "n0.val"), ("print n0.val", "n0.val"),
                           ("sys0=zz.val", "zz.val")):
            with self.subTest(line=line):
                with self.assertRaisesRegex(
                        NxwrightError, r"line 1: `%s`: in program\.nx, a component must include "
                        r"its page, as in `<page>\.%s`$" % (re.escape(name), re.escape(name))):
                    check_line(line, None, None, None, None, 1, pages, None, globals_)
        # With its page's name, a component of local scope is still refused.
        with self.assertRaisesRegex(NxwrightError, r"`first\.n0\.val`: `n0` has local scope, so "
                                                   r"it cannot be used in program\.nx"):
            check_line("page first.n0.val", None, None, None, None, 1, pages, None, globals_)
        # The array of a page's components picks its component when the code
        # runs, so it is not checked, whether or not the folder has the page.
        for line in ("sys0=second.b[1].val", "sys0=page9.b[1].val"):
            with self.subTest(line=line):
                check_line(line, None, None, None, None, 1, pages, None, globals_)

    def test_an_int_of_program_nx_named_as_the_editor_refuses(self):
        # The Editor refused an int named as one of its commands, even one
        # the series lacks; as a system variable; as a page; and as a
        # component of any page. It compiled other names. nxlang writes
        # program.nx's ints as they are, so it refuses them too.
        # Each declaration goes right after sys0 to sys2's, before program.nx's
        # other code, as the Nextion Editor takes declarations only before it.
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        line_number = text.split("\n").index(EDITOR_PROGRAM_DECLARATION) + 2

        def written(line: str) -> str:
            return text.replace(EDITOR_PROGRAM_DECLARATION,
                                EDITOR_PROGRAM_DECLARATION + "\n" + line, 1)
        cases = [("int sets=0", "`sets` already exists as a command"),
                 ("int vis=0", "`vis` already exists as a command"),
                 ("int fstr=0", "`fstr` already exists as a command"),
                 ("int dim=0", "`dim` already exists as a system variable"),
                 ("int abc=0,first=1", "`first` already exists as a page"),
                 ("int t0=1", "`t0` already exists as a component of page `first`")]
        for language in ("strict", "nxlang"):
            if language == "nxlang":
                switch_to_nxlang(self.source)
            for number, (line, words) in enumerate(cases):
                with self.subTest(language=language, line=line):
                    program.write_text(written(line), encoding="utf-8", newline="\n")
                    with self.assertRaisesRegex(
                            NxwrightError, r"program\.nx:%d: `%s`: %s, it cannot be "
                            r"redefined$" % (line_number, re.escape(line), re.escape(words))):
                        export_dump(self.source, self.folder / ("%s%d" % (language, number)))
            program.write_text(written("int abc=0,t1=2"), encoding="utf-8", newline="\n")
            export_dump(self.source, self.folder / ("%s-built" % language))

    def test_a_component_named_as_an_int_of_program_nx(self):
        # The Editor refused a text named sys0 beside program.s's own
        # declaration of sys0 to sys2, on the int's line.
        add_component(self.source / "pages" / "first.page.toml", "sys0")
        program = self.source / "program.nx"
        line_number = program.read_text(encoding="utf-8").split("\n").index(
            "int sys0=0,sys1=0,sys2=0") + 1
        with self.assertRaisesRegex(
                NxwrightError, r"program\.nx:%d: `int sys0=0,sys1=0,sys2=0`: `sys0` already "
                r"exists as a component of page `first`, it cannot be redefined$"
                % line_number):
            export_dump(self.source, self.folder / "refused")

    def test_program_nx_macros_and_nxlang(self):
        program = self.source / "program.nx"
        text = program.read_text(encoding="utf-8")
        written = text + ("" if text.endswith("\n") else "\n")
        program.write_text(written + "zork 1\n", encoding="utf-8", newline="\n")
        self.assert_line_refused("zork 1", r"unknown command `zork`$", 0,
                                 r"program\.nx:%d" % len(written.split("\n")))
        program.write_text(text, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  CLS 1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_line_refused("CLS 1", r"unknown command `CLS`\. Did you mean `cls`\?", 1,
                                 r"macros\.nx:2")
        (self.source / "macros.nx").unlink()
        switch_to_nxlang(self.source)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  zork 1\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_line_refused("zork 1", r"unknown command `zork`$", 2)


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
        cases = [(("sys0 = 1", "goto end"), r"first\.nx:3: `goto end`: this event has no "
                                            r"label `end`"),
                 (("end:", "sys0 = 1", "end:"), r"first\.nx:4: label `end` is already "
                                                r"defined in this event"),
                 (("1abc:", "goto 1abc"), r"first\.nx:2: `1abc:`: a label cannot start "
                                          r"with a digit")]
        for lines, message in cases:
            with self.subTest(lines=lines):
                self.write_code(*lines)
                self.assert_export_refused(message)


class ReadOnlyAttributeTest(SourceFolderTestCase):
    """Assignments in first.down to attributes that code cannot change. The
    Nextion Editor rejected them when it compiled ("Assignment operation
    failed"). setUp adds the down event, and a text on each page: t0 on
    first, and t1, of global scope, on second."""

    def setUp(self):
        super().setUp()
        pages = self.source / "pages"
        edit_text(pages / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(pages / "first.page.toml", "t0")
        add_component(pages / "second.page.toml", "t1", scope=1)

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def assert_refused(self, line: str, attribute: str, number: int,
                       file: str = r"first\.nx:2"):
        with self.assertRaisesRegex(NxwrightError, r"%s: `%s`: attribute `%s` cannot be "
                                                   r"changed in code$"
                                    % (file, re.escape(line), attribute)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_the_assignments_the_editor_refuses(self):
        # The Nextion Editor rejected each of these assignments when it
        # compiled. They cover every form of assignment, the page's own
        # attributes, another page's component, and id, type, and objname,
        # which are missing from the attribute descriptions. Another page's
        # own attributes never reach this check, because the reference check
        # rejects them first (ReferenceTest).
        cases = [("t0.w=10", "w"), ("t0.w+=1", "w"),
                 ("t0.h++", "h"), ("t0.h|=1", "h"),
                 ("t0.id=3", "id"), ("t0.type=1", "type"),
                 ('t0.objname="a"', "objname"),
                 ("first.x=10", "x"),
                 ("second.t1.w=10", "w")]
        for number, (line, attribute) in enumerate(cases):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, attribute, number)

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
        self.assert_refused("gm0.from=1", "from", 0)
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
                self.assert_refused(line, attribute, number)
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
        for number, (line, attribute) in enumerate((
                ("b0.movex=5", "movex"),
                ("b0.movey=5", "movey"),
                ("s0.txt_maxl=5", "txt_maxl"),
                ("sw0.txt_maxl=5", "txt_maxl"),
                ("cb0.drastate=1", "drastate"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, attribute, number)
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
        for number, (line, attribute) in enumerate((
                ("first.drag=1", "drag"),
                ("first.aph=50", "aph"),
                ("slt0.leftshow=1", "leftshow"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, attribute, number)
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
        for number, (line, attribute) in enumerate((
                ("d0.init=1", "init"),
                ("d0.autoleft=1", "autoleft"),
                ("fb0.autoleft=1", "autoleft"),
                ("fb0.buff=1", "buff"))):
            with self.subTest(line=line):
                self.write_code(line)
                self.assert_refused(line, attribute, number)
        self.write_code("sys0=d0.init", "sys1=d0.autoleft", "sys2=fb0.buff", "sys0=fb0.autoleft",
                        "t9.txt=d0.filter", 'd0.filter="a"', "g0.vvs2=5", "g0.vvs3=5")
        export_dump(self.source, self.folder / "taken")

    def test_the_runner_refuses_it_too(self):
        # Tests and the simulator build the page as the build does.
        self.write_code("t0.w=10")
        with self.assertRaisesRegex(NxwrightError, r":2: `t0\.w=10`: attribute `w` cannot "
                                                   r"be changed in code"):
            SourceFolderRunner(self.source).run("first", [("first", "down")])

    def test_in_nxlang_and_in_a_file_two_pages_include(self):
        # The included line is checked for each page that uses it.
        switch_to_nxlang(self.source)
        pages = self.source / "pages"
        (pages / "first.nx").write_text("on first.down:\n  t0.w = 10\n", encoding="utf-8",
                                        newline="\n")
        self.assert_refused("t0.w=10", "w", 0)
        edit_text(pages / "second.page.toml", "events = []", 'events = ["down"]')
        (pages / "lib").mkdir()
        (pages / "lib" / "shared.nx").write_text("function widen():\n  t1.h = 5\n",
                                                 encoding="utf-8", newline="\n")
        (pages / "first.nx").write_text("on first.down:\n  sys0 = 1\n", encoding="utf-8",
                                        newline="\n")
        (pages / "second.nx").write_text('include "lib/shared.nx"\n\non second.down:\n'
                                         "  widen()\n", encoding="utf-8", newline="\n")
        self.assert_refused("t1.h=5", "h", 1, r"pages/lib/shared\.nx:2")


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
            r"^pages/first\.page\.toml:9: component `c0` reaches past the screen, which is %s at this "
            r"rotation$" % size)

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
        self.assert_export_refused(r"component `c1` reaches past the screen, which is 480 by 320 "
                                   r"at this rotation")

    def test_the_intelligent_and_edge_series_take_it(self):
        self.place("c0", 1000, 0, 100, 30)
        for model in ("NX8048P050", "NX4848E040"):
            with self.subTest(model=model):
                self.use_screen(model)
                export_dump(self.source, self.folder / model)


class FirstDownTestCase(SourceFolderTestCase):
    """The small project, its screen and code changed by its tests. setUp
    adds the down event to page first, and a text t0 on it. The small
    project's screen, an NX1060P101, is of the Intelligent series."""

    def setUp(self):
        super().setUp()
        pages = self.source / "pages"
        edit_text(pages / "first.page.toml", "events = []", 'events = ["down"]')
        add_component(pages / "first.page.toml", "t0")

    def use_screen(self, model: str, **app_values):
        """Sets the folder's screen to `model`, and its app.toml's other
        values to `app_values`, such as its encoding."""
        app = self.source / "app.toml"
        data = tomllib.loads(app.read_text(encoding="utf-8"))
        data.update(screen=model, **app_values)
        app.write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")

    def write_code(self, *lines: str):
        """Writes the code of first.down; its lines start at line 2 of first.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "first.nx").write_text("on first.down:\n" + code,
                                                         encoding="utf-8", newline="\n")


class SeriesTest(FirstDownTestCase):
    """Lines using a command or a system variable the folder's screen series
    lacks, which the Editor 1.68.2 refused as it compiled."""

    def assert_refused(self, line: str, model: str, word: str, number: int,
                       file: str = r"first\.nx:2"):
        with self.assertRaisesRegex(
                NxwrightError, r"%s: `%s`: `%s` is not available on the %s$"
                               % (file, re.escape(line), word, model)):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def assert_assignment_refused(self, line: str, model: str, attribute: str, number: int):
        """Asserts the build refuses `line`, the code of first.down, on the
        screen `model`, as an assignment to `attribute`, which code cannot
        change on its series."""
        self.use_screen(model)
        self.write_code(line)
        with self.assertRaisesRegex(
                NxwrightError, r"first\.nx:2: `%s`: on the %s, attribute `%s` cannot be "
                               r"changed in code$" % (re.escape(line), model, attribute)):
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
                            NxwrightError, r"first\.nx:2: `%s`: `%s\.%s` cannot be used on "
                                           r"the %s$" % (re.escape(line), name, attribute, model)):
                        export_dump(self.source, self.folder / ("refused%d" % number))
        self.write_code(*(line for line, _, _ in cases))
        for model in ("NX4848E040", "NX8048P050"):
            with self.subTest(model=model):
                self.use_screen(model)
                export_dump(self.source, self.folder / model)

    def assert_component_refused(self, refusal: str):
        """Asserts that the build refuses page first, its message going on
        after its place, such as "pages/first.page.toml:17: ", as the pattern
        `refusal` says."""
        with self.assertRaisesRegex(NxwrightError,
                                    r"^pages/first\.page\.toml:\d+: " + refusal + "$"):
            export_dump(self.source, self.folder / "refused")

    def test_a_type_the_series_refuses(self):
        # As the Editor 1.68.2 refused an animation on the Discovery series:
        # "Unsupported component was found for this series device".
        self.add("gm0", "gmov")
        self.use_screen("NX4832F035")
        self.assert_component_refused(r"component `gm0` is of type `gmov`, which is not "
                                      r"available on the NX4832F035")
        self.use_screen("NX8048P050")
        export_dump(self.source, self.folder / "taken")

    def test_a_choice_the_series_refuses(self):
        # A gauge's sta 3, nxwright's default, on the basic series; a data
        # record of local scope on the Intelligent: "Out of range".
        self.use_screen("NX4832T035")
        self.add("g0", "gauge")
        self.assert_component_refused(r"attribute `sta` of component `g0` cannot be 3 on the "
                                      r"NX4832T035")
        edit_text(self.source / "pages" / "first.page.toml", 'type = "gauge"\n',
                  'type = "gauge"\nsta = 0\n')
        export_dump(self.source, self.folder / "sta0")
        self.use_screen("NX8048P050")
        self.add("d0", "data-record", vscope=0)
        self.assert_component_refused(r"attribute `vscope` of component `d0` cannot be 0 on the "
                                      r"NX8048P050")
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
                self.assert_component_refused(r"attribute `%s` of component `x0` cannot be %d on "
                                              r"the %s" % (attribute, value, model))
                self.use_screen("NX8048P050")
                export_dump(self.source, self.folder / ("taken-" + kind))
                page_file.write_bytes(page)

    def test_a_value_past_the_highest_of_its_series(self):
        # As the Editor 1.68.2 refused it on the Intelligent series, "Out of
        # range": a slider's ch past 100, where the Basic series takes up to
        # 255. The Edge series has the Intelligent's limit.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for model, ch in (("NX8048P050", 101), ("NX8048P050", 255), ("NX4848E040", 101)):
            with self.subTest(model=model, ch=ch):
                self.use_screen(model)
                self.add("h0", "slider", ch=ch)
                self.assert_component_refused(r"attribute `ch` of component `h0` must be between "
                                              r"0 and 100 on the %s" % model)
                page_file.write_bytes(page)
        self.add("h0", "slider", ch=100)
        export_dump(self.source, self.folder / "highest")
        page_file.write_bytes(page)
        # Seen with a colour behind the track alone: with a crop there, the
        # ch has no entry, and no probe tried a larger one.
        self.add("h0", "slider", sta=0, ch=255)
        export_dump(self.source, self.folder / "crop")
        page_file.write_bytes(page)
        self.use_screen("NX4832T035")
        self.add("h0", "slider", ch=255)
        export_dump(self.source, self.folder / "basic")

    def add_unplaced(self, name: str, kind: str, **values):
        """Adds a component of type `kind` that has no place, such as a
        timer, to page first, with `values`."""
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "%s"\ntype = "%s"\n' % (name, kind)
                       + "".join("%s = %d\n" % item for item in values.items()))

    def refused_with(self, number: int, pattern: str):
        """Asserts that the build refuses page first as the pattern `pattern`
        says, its message going on after the file and the line of its place,
        such as "pages/first.page.toml:17", into a folder of its own,
        `number`."""
        with self.assertRaisesRegex(NxwrightError, r"pages/first\.page\.toml:\d+" + pattern):
            export_dump(self.source, self.folder / ("refused-%d" % number))

    def test_values_past_their_entry_on_every_series(self):
        # As the Editor 1.68.2 refused them on every series ("Out of range",
        # or an error of its own for vscope), one past the range the
        # attribute's entry gives, at either end. A QR code and a scrolling
        # text refused a vscope of 2 on every series.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for number, (model, kind, values, refusal) in enumerate((
                ("NX4832T035", "text", {"xcen": 3}, "xcen must be from 0 to 2"),
                ("NX8048P050", "text", {"txt_maxl": 65535}, "txt_maxl must be from 0 to 65534"),
                ("NX4832T035", "timer", {"tim": 49}, "tim must be from 50 to 65534"),
                ("NX4832K035", "number", {"lenth": 16}, "lenth must be from 0 to 15"),
                ("NX4832T035", "qr-code", {"vscope": 2}, "vscope must be from 0 to 1"),
                ("NX4832F035", "scrolling-text", {"vscope": 2}, "vscope must be from 0 to 1"))):
            with self.subTest(model=model, values=values):
                self.use_screen(model)
                (self.add_unplaced if kind == "timer" else self.add)("c0", kind, **values)
                try:
                    self.refused_with(number, ": object 2: " + refusal)
                finally:
                    page_file.write_bytes(page)
        # The ends of the ranges are built.
        self.use_screen("NX8048P050")
        self.add("c0", "text", xcen=2, txt_maxl=65534)
        self.add_unplaced("c1", "timer", tim=50)
        export_dump(self.source, self.folder / "ends")

    def test_values_past_their_entry_on_a_series(self):
        # As the Editor 1.68.2 refused them on some series alone ("Out of
        # range"): a component's x past 6000 on the Intelligent series, and a
        # QR code's txt_maxl past its series' highest. A vscope of 2, which
        # the Intelligent and Edge series refused too, is outside its choices,
        # which the build refuses first (test_values_outside_their_choices).
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for number, (model, name, kind, attribute, value, lowest, highest) in enumerate((
                ("NX8048P050", "c0", "text", "x", 6001, -6000, 6000),
                ("NX4832K035", "qr0", "qr-code", "txt_maxl", 193, 0, 192),
                ("NX8048P050", "qr0", "qr-code", "txt_maxl", 631, 0, 630))):
            with self.subTest(model=model, kind=kind, attribute=attribute):
                self.use_screen(model)
                if attribute == "x":
                    # add gives each component an x of its own.
                    self.add(name, kind)
                    edit_text(page_file, 'name = "%s"\ntype = "%s"\nx = 0' % (name, kind),
                              'name = "%s"\ntype = "%s"\nx = %d' % (name, kind, value))
                else:
                    self.add(name, kind, **{attribute: value})
                try:
                    self.refused_with(
                        number, r": attribute `%s` of component `%s` must be between %d and %d "
                                r"on the %s$" % (attribute, name, lowest, highest, model))
                finally:
                    page_file.write_bytes(page)
        # The Intelligent series compiled a QR code's txt_maxl of 630.
        self.use_screen("NX8048P050")
        self.add("qr0", "qr-code", txt_maxl=630)
        export_dump(self.source, self.folder / "intelligent")

    def test_values_outside_their_choices(self):
        # A value outside an attribute's choices has no meaning, and the
        # Nextion Editor's panel cannot set it. So the build refuses it on
        # every series, though the Basic series compiled some of them, for
        # example a vscope of 2 on a text.
        page_file = self.source / "pages" / "first.page.toml"
        page = page_file.read_bytes()
        for number, (model, values, refusal) in enumerate((
                ("NX4832T035", {"vscope": 2}, r"vscope must be 0 \(local\) or 1 \(global\)$"),
                ("NX4848E040", {"vscope": 2}, r"vscope must be 0 \(local\) or 1 \(global\)$"),
                ("NX4832T035", {"drag": 2}, r"drag must be 0 \(no\) or 1 \(yes\)$"),
                ("NX4832K035", {"effect": 9}, r"effect must be 0 \(at once\), 1 \(from the "
                                              r"top\), "),
                ("NX4832F035", {"sendkey": 4}, r"sendkey must be 0 \(none\), 1 \(release\), 2 "
                                               r"\(press\), or 3 \(both\)$"),
                ("NX8048P050", {"sendkey": 4}, r"sendkey must be 0 \(none\), "))):
            with self.subTest(model=model, values=values):
                self.use_screen(model)
                self.add("c0", "text", **values)
                try:
                    self.refused_with(number, ": object 2: " + refusal)
                finally:
                    page_file.write_bytes(page)
        # Values among the choices are built: a page's effect of 10, which a
        # page's choices give, and on the Intelligent series a sta of 3.
        self.use_screen("NX8048P050")
        edit_text(page_file, 'events = ["down"]', 'events = ["down"]\neffect = 10')
        self.add("c0", "text", vscope=1, drag=1, effect=8, sendkey=3, sta=3)
        export_dump(self.source, self.folder / "chosen")

    def test_assignments_the_series_refuses(self):
        # As the Editor 1.68.2 refused them on the Basic, Enhanced, and
        # Discovery series, on every type that has them and the page:
        # "Assignment operation failed"; and x and y, on a text and a slider.
        # The Edge and the Intelligent took them.
        for number, (model, line, owner) in enumerate((
                ("NX4832T035", "t0.aph=50", "aph"),
                ("NX4832K035", "t0.drag=1", "drag"),
                ("NX4832F035", "first.effect=1", "effect"),
                ("NX4832T035", "t0.x=5", "x"),
                ("NX4832K035", "t0.y=5", "y"),
                ("NX4832F035", "t0.x=5", "x"))):
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
                ("NX4832T035", "b0.first=0", "first"),
                ("NX4832K035", "b0.time=300", "time"),
                ("NX4832F035", "first.first=0", "first"),
                ("NX4832T035", "t0.spax=1", "spax"),
                ("NX4832K035", "bt0.spay=1", "spay"),
                ("NX4832F035", "t1.borderc=0", "borderc"),
                ("NX4832T035", "t1.borderw=2", "borderw"),
                ("NX4832K035", "q0.vvs0=1", "vvs0"),
                ("NX4832F035", "q0.vvs1=1", "vvs1"))):
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
        for number, (model, line, word, _, taking) in enumerate(cases):
            with self.subTest(line=line, model=model):
                self.use_screen(model)
                self.write_code(line)
                self.assert_refused(line, model, word, number)
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
                        NxwrightError, r"first\.nx:2: `%s`: `piccolor` takes 4 arguments, "
                        r"not \d$" % re.escape(line)):
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
                self.assert_refused(line, "NX4832T035", word, number)

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
        self.assert_refused("wepo 1,0", "NX4832T035", "wepo", 0,
                            r"program\.nx:%d" % line)
        program.write_text(text, encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro probe:\n  sys1=rtc1\n", encoding="utf-8",
                                               newline="\n")
        self.assert_refused("sys1=rtc1", "NX4832T035", "rtc1", 1,
                            r"macros\.nx:2")

    def test_in_nxlang(self):
        switch_to_nxlang(self.source)
        self.use_screen("NX4832K035")
        (self.source / "pages" / "first.nx").write_text("on first.down:\n  sys0 = volume\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_refused("sys0=volume", "NX4832K035", "volume", 0)

    def test_the_series_before_the_number_of_arguments(self):
        # The Basic series lacks beep; the Intelligent takes one argument.
        self.use_screen("NX4832T035")
        self.write_code("beep 100,2")
        self.assert_refused("beep 100,2", "NX4832T035", "beep", 0)
        self.use_screen("NX8048P050")
        with self.assertRaisesRegex(NxwrightError, r"`beep` takes 1 argument, not 2$"):
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
        self.assert_export_refused(r"pages/lib/both\.nx:2: `t9` is neither a page nor a "
                                   r"component of this page")


def _text_line(size: int, character: str = "a", width: int = 1) -> str:
    """Returns `t0.txt="..."` of `size` bytes, its text of `character`, each
    `width` bytes in the folder's encoding."""
    return 't0.txt="%s"' % (character * ((size - len('t0.txt=""')) // width))


def _sum_line(size: int) -> str:
    """Returns `sys0=1+1+...`, or `sys0=11+1+...`, of `size` bytes."""
    start = "sys0=1" if size % 2 == 0 else "sys0=11"
    return start + "+1" * ((size - len(start)) // 2)


class LongLineTest(FirstDownTestCase):
    """A line of code longer than the Editor 1.68.2 compiled on the folder's
    series (editor_limits.LONGEST_LINES), counted in bytes of the folder's
    encoding, without the spaces the Editor drops: "The instructions are too
    long"."""

    def assert_line_refused(self, size: int, number: int, where: str = r"first\.nx:2",
                            what: str = "this line", encoding: str = "iso-8859-1"):
        with self.assertRaisesRegex(
                NxwrightError, r"%s: %s is too long: %d bytes in %s, not counting spaces, and "
                               r"the limit for this series is %d$"
                               % (where, what, size, encoding, LONGEST_LINES[self.series])):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def use_series(self, model: str, **app_values):
        self.use_screen(model, **app_values)
        self.series = model[6]

    def test_on_each_series(self):
        # 767 bytes on T, K, and F, and more on P and E.
        for number, model in enumerate(("NX4832T035", "NX4832K035", "NX4832F035", "NX4848E040",
                                        "NX8048P050")):
            with self.subTest(model=model):
                self.use_series(model)
                longest = LONGEST_LINES[self.series]
                self.write_code(_text_line(longest))
                export_dump(self.source, self.folder / model)
                self.write_code(_text_line(longest + 1))
                self.assert_line_refused(longest + 1, number)

    def test_counted_in_bytes_of_the_encoding_without_spaces(self):
        # 380 characters of 2 bytes in gb2312, 769 bytes in all. Spaces
        # outside the text are not counted, but those inside it are.
        self.use_series("NX4832T035", encoding="gb2312")
        self.write_code(_text_line(769, "中", 2))
        self.assert_line_refused(769, 0, encoding="gb2312")
        self.use_series("NX4832T035", encoding="iso-8859-1")
        self.write_code(_text_line(767).replace("=", "   =   "))
        export_dump(self.source, self.folder / "spaced")
        self.write_code(_text_line(767).replace('="a', '=" '))
        export_dump(self.source, self.folder / "spaced-text")
        self.write_code(_text_line(767).replace('="', '=" '))
        self.assert_line_refused(768, 1)

    def test_heads_and_declarations(self):
        # The Editor compiled heads of an if, an else if, and a while of
        # more than 1000 characters, and an int declaration of 1500. A for's
        # start and step are limited like lines. Its condition is limited
        # comparison by comparison (LongComparisonTest).
        self.use_series("NX4832T035")
        comparisons = "&&".join(["sys0==1"] * 120)
        self.write_code("if(%s)" % comparisons, "{", "}else if(%s)" % comparisons, "{", "}",
                        "while(%s)" % comparisons, "{", "}",
                        "for(%s;%s;%s)" % (_sum_line(767), comparisons, _sum_line(767)),
                        "{", "}")
        export_dump(self.source, self.folder / "heads")
        self.write_code("for(%s;sys0<1;sys0++)" % _sum_line(768), "{", "}")
        self.assert_line_refused(768, 0, what="the start of this `for` header")
        self.write_code("for(sys0=0;sys0<1;%s)" % _sum_line(768), "{", "}")
        self.assert_line_refused(768, 1, what="the step of this `for` header")
        program = self.source / "program.nx"
        program.write_text("int sys0=0,sys1=0,sys2=0,%s\npage 0\n"
                           % ",".join("v%d=0" % index for index in range(300)),
                           encoding="utf-8", newline="\n")
        self.write_code("sys0=1")
        export_dump(self.source, self.folder / "declaration")

    def test_the_runner_refuses_it_as_the_build_does(self):
        self.use_series("NX4832T035")
        self.write_code(_text_line(768))
        with self.assertRaisesRegex(NxwrightError, r":2: this line is too long: 768 bytes"):
            SourceFolderRunner(self.source).run("first", [("first", "down")])

    def test_in_program_nx_and_in_a_macro(self):
        self.use_series("NX4832T035")
        program = self.source / "program.nx"
        program.write_text("int sys0=0,sys1=0,sys2=0\n%s\npage 0\n" % _sum_line(768),
                           encoding="utf-8", newline="\n")
        self.assert_line_refused(768, 0, r"program\.nx:2")
        program.write_text("int sys0=0,sys1=0,sys2=0\npage 0\n", encoding="utf-8", newline="\n")
        (self.source / "macros.nx").write_text("macro long:\n  %s\n" % _sum_line(768),
                                               encoding="utf-8", newline="\n")
        self.assert_line_refused(768, 1, r"macros\.nx:2")

    def test_nxlang_writes_a_long_print_and_number_assignment_in_lines_that_fit(self):
        # A long prints stays refused, as only print is split.
        self.use_series("NX4832T035")
        switch_to_nxlang(self.source)
        long_sum = " + ".join(["sys0"] * 200)
        self.write_code('print "%s"' % ("a" * 2000), "sys1 = " + long_sum, "sys1 -= " + long_sum)
        export_dump(self.source, self.folder / "nxlang")
        self.write_code('prints "%s", 0' % ("a" * 800))
        self.assert_line_refused(len('prints "",0') + 800, 0)

    def test_nxlang_cuts_a_long_text_where_shift_jis_reads_it_right(self):
        # nxlang counts a line in utf-8, where ｱ and 日 take 3 bytes each. So
        # without its rule, the first part of each would end with ｱ日, which
        # the Nextion Editor reads in pairs of bytes past the closing quote.
        self.use_series("NX4832K035", encoding="shift-jis")
        switch_to_nxlang(self.source)
        longest = min(LONGEST_LINES.values())
        tail = "ｱ日"
        print_text = "a" * (longest - len('print ""') - 6) + tail + "b" * 100
        assigned = "a" * (longest - len('t0.txt+=""') - 6) + tail + "b" * 100
        self.write_code('print "%s"' % print_text, 't0.txt = "%s"' % assigned)
        export_dump(self.source, self.folder / "shift-jis")


def _text_comparison(size: int, text: str = "a", width: int = 1) -> str:
    """Returns `t0.txt=="..."`, whose compiled line `i t0.txt,"...",1,0` has
    `size` bytes. The text repeats `text`, which takes `width` bytes in the
    folder's encoding."""
    return 't0.txt=="%s"' % (text * ((size - len('i t0.txt,"",1,0')) // width))


class LongComparisonTest(FirstDownTestCase):
    """A comparison in a condition. The Editor 1.68.2 compiled each one into
    a line of its own, `i <left>,<right>,<number>,0`, with the same limit as
    any line on the series (editor_limits.LONGEST_LINES). When the line was
    longer, the Editor said "The instructions are too long", then "Index
    was outside the bounds of the array", and wrote no file."""

    def use_series(self, model: str, **app_values):
        self.use_screen(model, **app_values)
        self.series = model[6]

    def assert_comparison_refused(self, start: str, size: int, number: int,
                                  where: str = r"first\.nx:2",
                                  encoding: str = "iso-8859-1"):
        with self.assertRaisesRegex(
                NxwrightError, r"%s: the comparison `%s…` is too long: it takes %d bytes in %s, "
                               r"and the limit for this series is %d\. Compare a shorter text\.$"
                               % (where, re.escape(start), size, encoding,
                                  LONGEST_LINES[self.series])):
            export_dump(self.source, self.folder / ("refused%d" % number))

    def test_on_each_series(self):
        # 767 bytes on T, K, and F, and 4095 on P and E.
        for number, model in enumerate(("NX4832T035", "NX4832K035", "NX4832F035", "NX4848E040",
                                        "NX8048P050")):
            with self.subTest(model=model):
                self.use_series(model)
                longest = LONGEST_LINES[self.series]
                self.write_code("if(%s)" % _text_comparison(longest), "{", "}")
                export_dump(self.source, self.folder / model)
                self.write_code("if(%s)" % _text_comparison(longest + 1), "{", "}")
                self.assert_comparison_refused('t0.txt=="' + "a" * 31, longest + 1, number)

    def test_in_each_condition(self):
        # The head of an if, an else if, and a while, and a for's condition.
        self.use_series("NX4832T035")
        long = _text_comparison(768)
        for number, lines in enumerate((
                ["if(sys0==1)", "{", "}else if(%s)" % long, "{", "}"],
                ["while(%s)" % long, "{", "}"],
                ["for(sys0=0;%s;sys0++)" % long, "{", "}"])):
            with self.subTest(lines=lines[0][:12]):
                self.write_code(*lines)
                self.assert_comparison_refused('t0.txt=="' + "a" * 31, 768, number,
                                               r"first\.nx:%d" % (4 if number == 0 else 2))

    def test_each_comparison_on_its_own(self):
        # A head longer than 767 builds when each comparison is shorter. Two
        # texts are too long together though neither is near 753.
        self.use_series("NX4832T035")
        self.write_code("if(sys0==1&&%s)" % _text_comparison(767), "{", "}",
                        "while(sys0==1||%s||sys1==2)" % _text_comparison(767), "{", "}",
                        'if("%s"=="%s")' % ("a" * 378, "b" * 378), "{", "}")
        export_dump(self.source, self.folder / "built")
        self.write_code('if(sys0==1&&"%s"=="%s")' % ("a" * 378, "b" * 379), "{", "}")
        self.assert_comparison_refused('"' + "a" * 39, 768, 0)

    def test_joins_and_comparisons_inside_a_text(self):
        # A text that contains && or == stays one side of one comparison.
        self.use_series("NX4832T035")
        text = ("a&&b==c<" * 95)[:753]
        self.write_code('if(t0.txt=="%s")' % text, "{", "}")
        self.assert_comparison_refused('t0.txt=="' + text[:31], 768, 0)

    def test_counted_in_bytes_of_the_encoding_without_spaces(self):
        # 376 characters of 2 bytes in gb2312 make a line of 767 bytes.
        self.use_series("NX4832T035", encoding="gb2312")
        self.write_code("if ( %s )" % _text_comparison(767, "中", 2).replace("==", " == "),
                        "{", "}")
        export_dump(self.source, self.folder / "built")
        self.write_code("if(%s)" % _text_comparison(769, "中", 2), "{", "}")
        self.assert_comparison_refused('t0.txt=="' + "中" * 31, 769, 0, encoding="gb2312")

    def test_in_nxlang(self):
        # In an event, nxlang puts the long text into a text temporary with
        # room for it, so the comparison fits, and the page builds.
        switch_to_nxlang(self.source)
        self.use_series("NX4832T035")
        self.write_code('if (t0.txt == "%s") {' % ("a" * 753), "}")
        dump = self.folder / "built"
        export_dump(self.source, dump)
        page = next((dump / "pages").glob("*-first.txt")).read_text(encoding="utf-8")
        self.assertIn("if(t0.txt==__s0.txt)", page)
        self.assertRegex(page, r'objname = "__s0"\n(?:  .*\n)*?  txt_maxl = 753\n')
        # program.nx has no temporaries, so the build refuses it there.
        program = self.source / "program.nx"
        program.write_text('int sys0=0,sys1=0,sys2=0\nif ("%s" == "a") {\n  sys0 = 1\n}\npage 0\n'
                           % ("a" * 758), encoding="utf-8", newline="\n")
        self.write_code("sys0 = 1")
        with self.assertRaisesRegex(NxwrightError, r"program\.nx:2: .*770 bytes"):
            export_dump(self.source, self.folder / "program")



class TextRoomTest(FirstDownTestCase):
    """The room nxlang gives a text variable it adds, built as its txt_maxl."""

    def test_a_local_given_a_long_text(self):
        switch_to_nxlang(self.source)
        self.use_screen("NX8048P050")
        self.write_code('var s = "%s"' % ("a" * 400), "t0.txt = s")
        dump = self.folder / "built"
        export_dump(self.source, dump)
        page = next((dump / "pages").glob("*-first.txt")).read_text(encoding="utf-8")
        self.assertRegex(page, r'objname = "__v0"\n(?:  .*\n)*?  txt_maxl = 400\n')


class TextBytesTest(FirstDownTestCase):
    """Texts in code that the Nextion Editor 1.68.2 reads by their bytes, and
    refused as it compiled. In gb2312, big5, and shift-jis, it reads every
    text in pairs of bytes, so a shift-jis half-width katakana, one byte,
    takes the byte after it. In a condition, and before a comma among the
    arguments of prints, spstr, strlen, btlen, and crcputs, it reads a text
    again byte by byte, so a 0x5C byte, as the second byte of 表, escapes
    the closing quote."""

    def setUp(self):
        super().setUp()
        self.use_screen("NX4832K035", encoding="shift-jis")
        self.built = 0

    def next_folder(self, kind: str) -> Path:
        """Returns a folder no earlier build of the test wrote, as one that
        failed leaves its folder behind."""
        self.built += 1
        return self.folder / ("%s%d" % (kind, self.built))

    def assert_refused(self, lines: list, words: str):
        refused = lines[0]
        self.write_code(*lines)
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:2: `%s`: %s"
                                    % (re.escape(refused), words)):
            export_dump(self.source, self.next_folder("refused"))

    def assert_taken(self, *lines: str):
        self.write_code(*lines)
        export_dump(self.source, self.next_folder("taken"))

    def test_a_half_width_katakana_that_takes_the_closing_quote(self):
        words = (r"the half-width katakana `ｱ` is read together with the byte after it, so "
                 r"the closing quote is not found\. Put another character after `ｱ`\.$")
        for line in ('t0.txt="aｱ"', 't0.txt="ｱ"', 't0.txt="日ｱ"', 't0.txt="ｱｱｱ"',
                     't0.txt="ｱ日"', 't0.txt="ｱ表"', 't0.txt="ｱ\\""', 'prints "ｱ",0',
                     'print "aｱ"'):
            with self.subTest(line=line):
                self.assert_refused([line], words)
        self.assert_taken('t0.txt="ｱa"', 't0.txt="ｱｱ"', 't0.txt="ｱ日a"', 't0.txt="表"')

    def test_the_katakana_that_takes_the_closing_quote_is_given(self):
        # ｱ and ｲ read as a pair, and 日 as one character, so ｳ is the
        # katakana that takes the quote.
        self.assert_refused(['t0.txt="ｱｲ日ｳ"'], r"the half-width katakana `ｳ` is read together")

    def test_a_half_width_katakana_in_another_encoding(self):
        self.use_screen("NX4832K035", encoding="utf-8")
        self.assert_taken('t0.txt="aｱ"')

    def test_a_data_record_call_is_left_to_the_nextion_editor(self):
        with open(self.source / "pages" / "first.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "d0"\ntype = "data-record"\nx = 0\ny = 40\n'
                       'w = 200\nh = 100\n')
        self.use_screen("NX8048P050", encoding="shift-jis")
        self.assert_taken('d0.insert("ｱ")')

    def test_a_byte_0x5c_that_escapes_the_closing_quote(self):
        words = (r"the last byte of `表` is read as a backslash before the closing quote, so "
                 r"the text does not end\. Put the text in a variable first\.$")
        body = ["{", "sys1=1", "}"]
        for lines in (['if(t0.txt=="表")'] + body, ['while(t0.txt!="表")'] + body,
                      ['for(sys0=0;t0.txt!="表";sys0++)'] + body,
                      ['if(t0.txt=="日表"&&sys0==1)'] + body,
                      ['prints "日表",0'], ['spstr "表",t0.txt,"a",0'],
                      ['spstr t0.txt,t0.txt,"表",0'], ['strlen "表",sys0'], ['btlen "表",sys0'],
                      ['crcputs "表",0']):
            with self.subTest(line=lines[0]):
                self.assert_refused(lines, words)
        self.write_code("if(sys0==1)", *body, 'else if(t0.txt=="表")', *body)
        with self.assertRaisesRegex(NxwrightError, r"first\.nx:6: .*%s" % words):
            export_dump(self.source, self.folder / "else-if")
        # Taken: the text ending a line or joined in an assignment, a 0x5C
        # that escapes a letter, and a for's first and last parts.
        self.assert_taken('t0.txt="日表"', 't0.txt="日表"+t0.txt', 'print "日表"',
                          'prints "表a",0', 'if(t0.txt=="表a")', *body,
                          'for(t0.txt="表";sys0<1;sys0++)', *body,
                          'for(sys0=0;sys0<1;t0.txt="表")', *body)

    def test_a_byte_0x5c_inside_an_escape(self):
        # 表's 0x5C escapes the first backslash, and the second the quote.
        self.assert_refused(['prints "a表' + "\\\\" + '",0'],
                            r"the last byte of `表` is read as a backslash")

    def test_a_byte_0x5c_in_another_encoding(self):
        # In utf-8, no character but the backslash has a byte 0x5C.
        self.use_screen("NX4832K035", encoding="utf-8")
        self.assert_taken('if(t0.txt=="表")', "{", "sys1=1", "}", 'prints "日表",0')

    def test_in_big5_and_gb2312(self):
        for encoding, character in (("big5", "許"), ("gb2312", "乗")):
            with self.subTest(encoding=encoding):
                self.use_screen("NX4832K035", encoding=encoding)
                self.assert_refused(['prints "%s",0' % character],
                                    r"the last byte of `%s` is read as a backslash" % character)

    def test_an_escaped_backslash_before_a_comma(self):
        # A 0x5C that is a backslash's escape escapes the second, not the quote.
        self.use_screen("NX4832T035", encoding="iso-8859-1")
        self.assert_taken(r'prints "a\\",0', r'spstr "a\\",t0.txt,"b",0', r'prints "a\\b",0')

    def test_only_a_quoted_text_is_misread(self):
        # nxlang asks about any argument, a name or an expression too.
        codec = TextCodec("shift-jis")
        self.assertTrue(misread_byte_by_byte('"表"', codec))
        for argument in ("t0.txt", "x.val", '"表"+t0.txt', '"a"'):
            with self.subTest(argument=argument):
                self.assertFalse(misread_byte_by_byte(argument, codec))
        self.assertFalse(misread_byte_by_byte('"表"', None))

    def test_in_nxlang(self):
        # nxlang puts a text whose 0x5C escapes its quote into a text
        # temporary first, so the build takes the line.
        switch_to_nxlang(self.source)
        code = ('on first.down:\n  if (t0.txt == "表") {\n    sys1 = 1\n  }\n'
                '  prints "日表", 0\n')
        nx_file = self.source / "pages" / "first.nx"
        nx_file.write_text(code, encoding="utf-8", newline="\n")
        built = self.next_folder("nxlang").with_suffix(".HMI")
        build(self.source, built)
        dump = self.next_folder("dump")
        ProjectDumper(built, dump).dump()
        page = (dump / "pages" / "00-first.txt").read_text(encoding="utf-8")
        self.assertIn("| if(t0.txt==__s0.txt)", page)
        self.assertIn("| prints __s0.txt,0", page)
        # The runtime reads a half-width katakana with the character after
        # it, so no character added to the text can be taken off again. Its
        # text stays refused.
        self.assert_refused(['t0.txt="aｱ"'], r"the half-width katakana `ｱ` is read together")

    def test_in_program_nx(self):
        # program.nx has no temporaries, so the text stays refused.
        switch_to_nxlang(self.source)
        edit_text(self.source / "program.nx", "page 0", 'prints "表",0\npage 0')
        with self.assertRaisesRegex(NxwrightError, r"program\.nx:\d+: `prints \"表\",0`: "
                                                   r"the last byte of `表` is read as a backslash"):
            export_dump(self.source, self.next_folder("program"))


if __name__ == "__main__":
    unittest.main()
