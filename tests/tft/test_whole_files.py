"""The sample of whole files: probes built whole, from their source folder to
a project file, whose user code nxwright writes and compares with the probe's
fixtures, part by part. They show that nxwright's pieces fit together into a
whole file. Every other test gives a piece's function its own input
(tests/tft/unit_inputs.py).

The fixtures are the frame's output through frame_probes.stand_in_code,
which the probe runner wrote once each probe matched the Nextion Editor's
file.
"""
from dataclasses import replace
from pathlib import Path
import re
import struct
import tempfile
import unittest

from nxwright import NxwrightError
from nxwright.project.page_text import page_to_text
from nxwright.project.zi_font import turned_font
from nxwright.tft import frame, packaging
from nxwright.tft.packaging import Firmware, package
from nxwright.tft.commands.compile import compile_project
from nxwright.tft.firmware import firmware_from_tft
from nxwright.tft.component_types import button, dual_state_button, number, text, xfloat
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing import (attribute_probes, button_probes, checkbox_probes, code_form_probes,
                           command_operand_probes, compile_probes, condition_probes,
                           crc_command_probes, crop_probes, device_and_buffer_command_probes,
                           drawing_probes, dual_state_button_probes, e_probes,
                           eeprom_and_gpio_probes, encoding_probes, entry_limit_probes, f_probes,
                           file_stream_probes, for_probes, frame_probes, gauge_probes, goto_probes,
                           hex_number_probes, hotspot_probes, if_probes, indirect_probes, k_probes,
                           key_probes, macro_probes, media_probes, model_probes, number_probes,
                           other_attribute_probes, other_page_probes, overlap_probes, p_probes,
                           packaging_probes, page_command_probes, page_place_probes, page_probes,
                           picture_probes, pinyin_probes, progress_bar_probes, qr_code_probes,
                           radio_probes, resampled_sound_probes, rotation_probes,
                           screen_command_probes, scrolling_text_probes, serial_command_probes,
                           shared_attribute_probes, slider_probes, statement_probes,
                           text_assignment_probes, text_character_probes, text_command_probes,
                           text_condition_probes, text_probes, text_room_probes, timer_probes,
                           touch_capture_probes, undocumented_command_probes, variable_probes,
                           waveform_command_probes, waveform_probes, while_probes, xfloat_probes)
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.component_probes import with_components
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.gmov_probes import gmov_component
from tools.tft.probing.frame_probes import stand_in_code
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import BASE_MODELS, BASES, FIXTURES, Probe, _built
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tools.tft.probing.variable_probes import variable_component
from tools.tft.probing.video_probes import video_component
from tools.tft.probing.waveform_probes import waveform_component
from tools.tft.probing.xfloat_probes import xfloat_component
from nxwright.tft.project import Project
from nxwright.tft.series_differences import DIFFERENCES
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.line_context import line_context
from tests.tft.series_comparison import compare_user_code
from tests.tft.series_probe_pairs import paired_probes
from tests.tft.made_tft import made_tft, made_user_code, zeros_of_the_table
from tests.tft.p_components import SEVERAL_TYPES, TXTS_PAST_ASCII
from tests.tft.t_components import made_in_memory
from tests.tft.whole_builds import built_project
from tests.tft.unit_inputs import laid_out_pieces, page_of, probe_facts, probe_project


def _named(module, *names: str) -> list:
    """Returns the probes of the probe module `module` named `names`, in that
    order."""
    by_name = {probe.name: probe for probe in module.PROBES}
    return [by_name[name] for name in names]


# The types whose tests on P take their probes on P, by their probes' names,
# but the text commands' family's, which a text's tests do not take; the
# statement encoder's own probes, which tests/tft/test_statements.py takes; and
# P's own probes of every attribute of a text, a number, and a button, read
# and set, which tests/tft/test_other_attributes.py takes.
_TYPES_TESTED_ON_P = re.compile(
    r"p-(progress-bar|text|number|button|radio|checkbox|dual-state-button|select|gmov"
    r"|sliding-text|combo-box|switch|external-picture|video|audio|hotspot|slider|variable"
    r"|timer|xfloat|qr-code|gauge|waveform|picture|crop|touch-capture|scrolling-text"
    r"|file-stream|data-record|file-browser|statements|attributes)-(?!commands-).*")
# The sample on P of the types sampled here, in _P_SAMPLES; the others' is in
# test_eight_types_of_p_at_their_defaults, test_hotspots, test_sliders,
# test_variables, test_timers, test_xfloats, test_qr_codes, test_gauges,
# test_waveforms, test_scrolling_texts, test_file_streams, and
# test_a_data_record_and_a_file_browser.
_P_SAMPLES = ("p-progress-bar-among-the-types-matched", "p-text-two", "p-number-beside-a-text",
              "p-button-beside-a-text-and-a-number", "p-radio-among-the-types-matched",
              "p-checkbox-among-the-types-matched", "p-dual-state-button-among-the-types-matched",
              "p-picture-among-the-types-matched", "p-crop-among-the-types-matched",
              "p-touch-capture-among-the-types-matched", "p-statements-system-variables",
              "p-attributes-read", "p-globals-waveform",
              # The samples of P's probes of several types
              # (p_components.SEVERAL_TYPES): the page's, the overlaps', and
              # the attributes every object has.
              "p-page-of-pictures", "p-overlap-types-under-a-picture",
              "p-shared-attributes-effects-and-a-second-page",
              # A text's room after a longer text on the page before, after
              # a global's memory, and on the page after: each page's texts
              # on P, which only a whole build compares
              # (test_the_frame_and_a_page).
              "p-text-rooms-after-a-long-page", "p-globals-under-a-wide-room",
              "p-text-rooms-across-pages",
              # Code on P naming another page's globals, which only a whole
              # build compares on P (tests/tft/test_other_page.py takes T's).
              "p-globals-on-two-pages",
              # The sample of P's probes of txts past ASCII letters and digits
              # (p_components.TXTS_PAST_ASCII).
              "p-text-characters-txt-of-latin-1")
# The P probes of a global component of each type, whose components
# tests/tft/test_shared_attributes.py takes at their types' functions; their
# sample, p-globals-waveform, a buffer's word among the int area's, is in
# _P_SAMPLES.
_GLOBALS_TESTED_ON_P = frozenset("p-globals-" + name for name in p_probes.GLOBAL_TYPES)
# The other P probes whose pieces the unit tests take: P's probes of several
# types, whose components test_p_series.SeveralTypesTest takes; the commands
# P has, whose family's probes test_p_series.CommandsPHasTest takes, its
# sample p-commands-p-has-each; the three families whose samples on P
# test_command_families compares; and P's probes of txts past ASCII
# letters and digits, whose components test_text_characters.TxtOnPTest
# takes. tests/tft/test_frame.py takes the frame's pieces of every probe of P
# that keeps its user code.
_OTHERS_TESTED_ON_P = frozenset(SEVERAL_TYPES + (
    "p-commands-p-has-operands", "p-commands-p-has-components-of-other-forms",
    "p-commands-p-has-files-of-any-kind",
    "p-crc-commands-each", "p-drawing-each-command",
    "p-waveform-commands-each") + tuple(probe.name for probe in p_probes.PROBES
                                        if probe.name.startswith(TXTS_PAST_ASCII)))


class WholeFileTest(unittest.TestCase):

    def assert_each_part(self, probes: list):
        """Checks that each of `probes` keeps as its fixtures the parts of
        its user code that nxwright writes from its whole build."""
        self.assertTrue(probes)
        for probe in probes:
            folder = FIXTURES / probe.fixtures / probe.name
            with tempfile.TemporaryDirectory() as work:
                ours = (probe.kept or probe.ours)(_built(probe, Path(work)))
            self.assertEqual(sorted(file.stem for file in folder.glob("*.bin")), sorted(ours),
                             probe.name)
            for piece, data in ours.items():
                with self.subTest(probe=probe.name, piece=piece):
                    self.assertEqual(data, (folder / (piece + ".bin")).read_bytes())

    def assert_whole_compile(self, probe, pieces=compile_probes.fixture_pieces):
        """Checks that `probe`, a probe of the whole compile, keeps as its
        fixtures the pieces of the file nxwright compiles from its whole build,
        made on zeros for the firmware, of the sizes their own table
        gives. With packaging_probes.fixture_pieces as `pieces`, it checks a
        probe of packaging the same way."""
        folder = FIXTURES / probe.fixtures / probe.name
        kept = {file.stem: file.read_bytes() for file in folder.glob("*.bin")}
        firmware = zeros_of_the_table(kept["table"], probe.base)
        self.assertEqual(pieces(built_project(probe.base, probe.change), firmware), kept)

    def test_a_probe_s_page_in_memory_is_its_page(self):
        # unit_inputs.page_of makes the page a probe's components go on, as
        # its whole build does: on page0 and on a page it adds, with code,
        # and with pictures, which the page names (PicturesChange).
        for name in ("p-text-on-second-page", "progress-bar-event-code",
                     "p-progress-bar-of-pictures"):
            probe = next(probe for module in (p_probes, progress_bar_probes)
                         for probe in module.PROBES if probe.name == name)
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as work:
                    pages = Project.from_file(_built(probe, Path(work))).pages
                number = 0 if probe.change.page == "page0" else len(pages) - 1
                self.assertEqual(page_to_text(page_of(probe)), page_to_text(pages[number]))

    def test_a_probe_s_added_pages_in_memory_are_its_pages(self):
        # unit_inputs.probe_project gives each page a probe adds the place
        # after those added before it, as its whole build does: ten empty
        # pages after page0.
        probe = next(probe for probe in page_command_probes.PROBES if probe.name == "page-of-ten")
        with tempfile.TemporaryDirectory() as work:
            built = Project.from_file(_built(probe, Path(work))).pages
        self.assertEqual([page_to_text(made) for made in probe_project(probe).pages],
                         [page_to_text(made) for made in built])

    def test_a_probe_s_program_in_memory_is_its_program(self):
        # unit_inputs.probe_project gives a probe of statement_probes'
        # ProgramChange its program.s and its page0, as its whole build
        # does: one with lines and declarations in program.s, and one with
        # code in page0's event beside a text and two numbers.
        for probe in (next(probe for probe in module.PROBES if probe.name == name)
                      for module, name in ((code_form_probes, "code-forms-declarations"),
                                           (crc_command_probes, "crc-commands-each"))):
            with self.subTest(probe.name):
                with tempfile.TemporaryDirectory() as work:
                    built = Project.from_file(_built(probe, Path(work)))
                facts = probe_project(probe)
                self.assertEqual(facts.program, built.program)
                self.assertEqual(page_to_text(facts.pages[0]), page_to_text(built.pages[0]))

    def test_a_probe_s_macros_in_memory_are_its_macros(self):
        # unit_inputs.probe_facts gives a probe of macro_probes' MacrosChange
        # the macros' block and program.s its whole build does: one with
        # calls from program.s, an event, and a macro, and one with comments
        # and indentation in a macro.
        for probe in (next(probe for probe in module.PROBES if probe.name == name)
                      for module, name in ((macro_probes, "macros-called"),
                                           (code_form_probes, "code-forms-in-a-macro"))):
            with self.subTest(probe.name):
                with tempfile.TemporaryDirectory() as work:
                    built = Project.from_file(_built(probe, Path(work)))
                facts = probe_facts(probe)
                self.assertEqual(facts.blocks["comcode.sn"], built.blocks["comcode.sn"])
                self.assertEqual(facts.program, built.program)

    def test_a_probe_s_pages_in_memory_with_attributes_ints_and_encoding(self):
        # unit_inputs.probe_facts gives a probe the pages and program.s its
        # whole build does: one of pages with their own attributes, one of
        # two more ints in program.s, and one in gb2312.
        for probe in (next(probe for probe in module.PROBES if probe.name == name)
                      for module, name in (
                          (shared_attribute_probes, "shared-attributes-effects-of-each-type"),
                          (shared_attribute_probes, "shared-attributes-globals-on-two-pages"),
                          (encoding_probes, "encoding-gb2312"))):
            with self.subTest(probe.name):
                with tempfile.TemporaryDirectory() as work:
                    built = Project.from_file(_built(probe, Path(work)))
                facts = probe_facts(probe)
                self.assertEqual(facts.settings, built.settings)
                self.assertEqual(facts.program, built.program)
                self.assertEqual([page_to_text(made) for made in facts.pages],
                                 [page_to_text(made) for made in built.pages])

    def test_macros_and_code_forms(self):
        # The sample of whole files of the macros, on T: calls from an event,
        # from program.s, and from a macro, and a return in a macro; and of
        # the forms of code the Nextion Editor writes as plainer ones:
        # comments after code. Their pieces are compared on their projects in
        # memory in tests/tft/test_macros.py and tests/tft/test_code_form_probes.py.
        self.assert_each_part(_named(macro_probes, "macros-called")
                              + _named(code_form_probes, "code-forms-comments-after-code"))

    def test_header_1_s_fields_of_the_macros(self):
        # 0x58 gives the macros' table's place, and 0x6E the number of
        # macros; without macros, 0x58 gives the page index's place, and 0x6E
        # holds 0. The packaging writes header 1, so the check stays here
        # until its tests take it.
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(_named(macro_probes, "macros-sorted-by-crc")[0],
                                               Path(work)))
        firmware = firmware_from_tft(made_tft("T"), "made.tft", "T")
        for each, part, count in ((project, "macros", 4), (built_project("T"), "page index", 0)):
            with self.subTest(part):
                tft = read_tft(compile_project(each, firmware), "nxwright's file")
                self.assertEqual(tft.header_1_value(0x58), tft.user_code.places()[part][0])
                self.assertEqual(struct.unpack_from("<H", tft.data, 0x6E)[0], count)

    def test_a_probe_of_code_s_page_in_memory_is_its_page(self):
        # unit_inputs.page_of makes the page of a probe of
        # attribute_probes.with_attributes as its whole build does. Its
        # change makes its code strict Nextion syntax, so page_of does too.
        for probe in (next(probe for probe in module.PROBES if probe.name == name)
                      for module, name in ((hotspot_probes, "hotspot-in-commands"),
                                           (variable_probes, "variable-txt-in-code"))):
            with self.subTest(probe.name):
                with tempfile.TemporaryDirectory() as work:
                    built = Project.from_file(_built(probe, Path(work))).pages[0]
                self.assertEqual(page_to_text(page_of(probe)), page_to_text(built))

    def test_a_probe_s_needs_in_memory_are_a_whole_build_s(self):
        # unit_inputs.probe_project gives the match check a probe's pages,
        # on page0 and on a page it adds; a whole build gives the same
        # needs, but for its resources', which a Project of facts has not.
        for name in ("p-text-on-second-page", "progress-bar-event-code"):
            probe = next(probe for module in (p_probes, progress_bar_probes)
                         for probe in module.PROBES if probe.name == name)
            with self.subTest(name):
                with tempfile.TemporaryDirectory() as work:
                    built = project_needs(Project.from_file(_built(probe, Path(work))))
                self.assertEqual(project_needs(probe_project(probe)),
                                 [need for need in built if need.kind != "resource"])

    def test_a_line_s_context_in_memory_is_a_whole_build_s(self):
        # tests/tft/line_context.py makes its page in memory. A whole build of
        # the same page, as attribute_probes.with_attributes makes it, gives
        # the same context, for components of each kind the tests give it.
        for components in ((text_component(), number_component(y=60)),
                           (crop_component(picc=None),), (waveform_component(),),
                           (touch_capture_component(),), (variable_component(),),
                           (timer_component(), xfloat_component(y=60))):
            probe = Probe("context", "T", with_attributes(["sys0=1"], list(components)),
                          None, None)
            with self.subTest(components):
                with tempfile.TemporaryDirectory() as work:
                    project = Project.from_file(_built(probe, Path(work)))
                built = next(need.context for need in project_needs(project)
                             if need.kind == "code" and need.subject == "event")
                self.assertEqual(line_context(*components), built)

    def test_the_p_probes(self):
        # The samples of whole files on P: each P probe that keeps fixtures
        # but those whose pieces the unit tests take, of a type, of a global
        # of each type, or of several types or a family of commands, which
        # keep one each, their sample on P. The rest are whole compiles, the
        # samples of the families of commands, and those whose pages a unit
        # test cannot make in memory. A probe that no unit test takes counts
        # here, so that the list does not grow unseen.
        probes = [probe for probe in p_probes.PROBES if probe.fixtures
                  and not ((_TYPES_TESTED_ON_P.fullmatch(probe.name)
                            or probe.name in _GLOBALS_TESTED_ON_P
                            or probe.name in _OTHERS_TESTED_ON_P)
                           and made_in_memory(probe) and probe.name not in _P_SAMPLES)]
        self.assertEqual(len(probes), 36)
        for probe in probes:
            if probe.kept is compile_probes._kept:
                with self.subTest(probe.name):
                    self.assert_whole_compile(probe)
        self.assert_each_part([probe for probe in probes
                               if probe.kept is not compile_probes._kept])

    def test_the_k_series(self):
        # K's sample of whole files: the whole compile of a blank project.
        # K's other probes keep no fixtures but its own system variables',
        # whose blocks are compared at the statement encoder in
        # tests/tft/test_k_series.py.
        self.assert_whole_compile(next(probe for probe in k_probes.PROBES
                                       if probe.name == "k-compile-T-blank"))

    def compiled_pair(self, series: str, leader_name: str) -> tuple:
        """Returns (the leader's user code, the follower's, the leader's
        rotation) of the pair of `series` whose leader is `leader_name`, each
        compiled whole on zeros for the firmware, which packaging alone
        reads."""
        def compiled(probe):
            with tempfile.TemporaryDirectory() as work:
                project = Project.from_file(_built(probe, Path(work)))
            firmware = Firmware((1, 68, 2), {name: bytes(16)
                                             for name in firmware_names(probe.base)})
            return read_tft(compile_project(project, firmware), probe.name).user_code, \
                project.settings.rotation
        leader, follower = next(pair for pair in paired_probes(series)
                                if pair[0].name == leader_name)
        (leader_code, rotation), (follower_code, follower_rotation) = (compiled(leader),
                                                                       compiled(follower))
        self.assertEqual(rotation, follower_rotation)
        return leader_code, follower_code, rotation

    def test_the_followers(self):
        # Each follower's sample of whole files: a project of three pages,
        # ints, and code, its whole user code beside its leader's, which may
        # differ only as its table of differences says. A page's size, in the
        # page's record and memory, is the frame's, so the samples check it
        # until the frame's tests take it. Each follower's pieces are
        # compared on its pages in memory in tests/tft/test_series_followers.py.
        for series, leader in (("F", "compile-T-pages-ints-code"),
                               ("K", "compile-T-pages-ints-code"),
                               ("E", "p-compile-T-pages-ints-code")):
            with self.subTest(series):
                leader_code, follower_code, rotation = self.compiled_pair(series, leader)
                used = compare_user_code(leader_code, follower_code, series, rotation)
                if DIFFERENCES[series]["page_size"] is not None:
                    self.assertIn(("page_size", DIFFERENCES[series]["page_size"]), used)

    def test_the_whole_comparison_refuses_what_its_table_does_not_give(self):
        # A row missing from K's table, an instruction changed, and an entry
        # changed, each named by its part and block, in K's blank project
        # beside T's.
        leader, follower, _ = self.compiled_pair("K", "compile-T-blank")
        differences = {**DIFFERENCES["K"], "operands": tuple(
            row for row in DIFFERENCES["K"]["operands"] if row[0] != "baud")}
        with self.assertRaisesRegex(AssertionError, r"program\.s block 1, byte 2"):
            compare_user_code(leader, follower, "K", differences=differences)
        blocks = list(follower.blocks)
        blocks[1] = blocks[1][:-1] + bytes([blocks[1][-1] ^ 1])
        with self.assertRaisesRegex(AssertionError, r"program\.s block 1"):
            compare_user_code(leader, replace(follower, blocks=blocks), "K")
        data = bytes([follower.data[0] ^ 1]) + follower.data[1:]
        with self.assertRaisesRegex(AssertionError, "data, byte 0"):
            compare_user_code(leader, replace(follower, data=data), "K")

    def test_packaging(self):
        # The sample of whole files of packaging, on T: a project of two
        # pictures and two fonts, which only a whole build gives their
        # blocks. Its layout on each series is checked on a Project of facts
        # in tests/tft/test_packaging.py.
        self.assert_whole_compile(_named(packaging_probes, "packaging-T-two-each")[0],
                                  packaging_probes.fixture_pieces)

    def test_each_series_fonts_in_its_section(self):
        # Each base folder's fonts lie in the section's part 8, as the
        # project holds their blocks.
        for series in BASE_MODELS:
            with self.subTest(series):
                project = built_project(series)
                firmware = Firmware((1, 68, 2), {name: bytes(16)
                                                 for name in firmware_names(series)})
                tft = read_tft(package(project, made_user_code(), firmware), series)
                fonts = b"".join(project.blocks[name] for kind, name in project.resources
                                 if kind == "font")
                self.assertEqual(tft.table_part(tft.table[8]), fonts)

    def test_a_picture_in_its_section(self):
        project = built_project("T", packaging_probes._add_picture)
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        tft = read_tft(package(project, made_user_code(), firmware), "picture")
        pictures = [project.blocks[name] for kind, name in project.resources if kind == "picture"]
        self.assertEqual(len(pictures), 1)
        self.assertEqual(tft.table_part(tft.table[7]), pictures[0])
        self.assertEqual(tft.header_2_value(0x104), 1)

    def test_two_pictures_and_two_fonts_in_their_section(self):
        # The pictures' headers come first, each giving the picture's ID and
        # where its data lies in the pictures' part; then their data.
        project = built_project("T", packaging_probes._add_two_of_each)
        self.assertEqual((project.resource_count("picture"), project.resource_count("font")),
                         (2, 2))
        firmware = Firmware((1, 68, 2), {name: bytes(16) for name in firmware_names("T")})
        tft = read_tft(package(project, made_user_code(), firmware), "two pictures")
        blocks = [project.blocks[name] for kind, name in project.resources if kind == "picture"]
        part = tft.table_part(tft.table[7])
        self.assertEqual(len(part), sum(len(block) for block in blocks))
        self.assertEqual([struct.unpack_from("<II", part, 24 * number + 4)
                          for number in range(2)],
                         [(0, 48), (1, 48 + len(blocks[0]) - 24)])
        self.assertEqual(part[48:], blocks[0][24:] + blocks[1][24:])
        self.assertEqual(part[16:24], blocks[0][16:24])
        # The fonts alike, with 44-byte headers, the u32 at 24 of each giving
        # where its description starts in the fonts' part, and no ID.
        fonts = [project.blocks[name] for kind, name in project.resources if kind == "font"]
        part = tft.table_part(tft.table[8])
        self.assertEqual([struct.unpack_from("<I", part, 44 * number + 24)[0]
                          for number in range(2)], [88, 88 + len(fonts[0]) - 44])
        self.assertEqual(part[:24] + part[28:44], fonts[0][:24] + fonts[0][28:44])
        self.assertEqual(part[88:], fonts[0][44:] + fonts[1][44:])

    def test_overlaps(self):
        # The sample of whole files of the refs of components that overlap,
        # on T: a component of each of five types and a variable and a timer,
        # under a picture. Each drawn component's background fill and refs,
        # in each probe that keeps fixtures, are compared at their functions
        # in tests/tft/test_overlap.py.
        self.assert_each_part(_named(overlap_probes, "overlap-types-under-a-picture"))

    def test_the_e_series(self):
        # E's sample of whole files: the whole compiles of a blank project
        # and of three pages with int variables and code, whose fixtures are
        # E's two that keep any. Each compile runs the match check on E.
        for name in ("e-compile-T-blank", "e-compile-T-pages-ints-code"):
            with self.subTest(name):
                self.assert_whole_compile(_named(e_probes, name)[0])

    def test_the_f_series(self):
        # F's sample of whole files: the packaging of a project of two of
        # each resource, and the whole compile of a blank project. F's other
        # probes that keep fixtures, of its own system variables and of the
        # commands it has, are compared at the statement encoder in
        # tests/tft/test_f_series.py.
        self.assert_whole_compile(_named(f_probes, "f-packaging-T-two-each")[0],
                                  packaging_probes.fixture_pieces)
        self.assert_whole_compile(_named(f_probes, "f-compile-T-blank")[0])

    @staticmethod
    def font_of(probe) -> tuple:
        """Returns the font of `probe`'s whole build, as its folder keeps it,
        and the font the packaging writes for it (packaging._fonts)."""
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        kept = project.blocks[next(name for kind, name in project.resources if kind == "font")]
        return kept, packaging._fonts(project)[0]

    def test_an_f_project_s_font_is_written_at_0_degrees(self):
        # On F, the Nextion Editor writes each font at 0 degrees, whatever
        # the project's rotation. nxwright's device command keeps the base
        # folder's font at 0 degrees, orientation byte 0x0a, as it turns the
        # folder to 90, so the font is written as it is.
        kept, written = self.font_of(_named(f_probes, "f-at-90-compile-T-blank")[0])
        self.assertEqual((kept[3], written[3]), (0x0A, 0x0A))
        self.assertEqual(written, (BASES / "F" / "fonts" / "NotoSans24.zi").read_bytes())

    def test_a_t_project_s_font_is_written_at_its_rotation(self):
        # On T, the TFT file keeps a font at the project's rotation. The
        # folder, turned to 90 degrees by nxwright's device command, keeps
        # the base folder's font at 0, so the packaging turns it to 90,
        # orientation byte 0x0b.
        kept, written = self.font_of(_named(rotation_probes, "rotation-90")[0])
        self.assertEqual((kept[3], written[3]), (0x0A, 0x0B))
        self.assertEqual(written, turned_font(kept, 90))

    def test_progress_bars(self):
        # The progress bar's sample on T: two bars among the other types
        # matched. Each bar of every probe is compared at its type's
        # functions (tests/tft/test_progress_bar.py).
        self.assert_each_part([probe for probe in progress_bar_probes.PROBES
                               if probe.name == "progress-bar-among-the-types-matched"])

    def test_checkboxes(self):
        # The checkbox's sample on T: a checkbox among the other types
        # matched. Each checkbox of every probe is compared at its type's
        # functions (tests/tft/test_checkbox.py).
        self.assert_each_part(_named(checkbox_probes, "checkbox-among-the-types-matched"))

    def test_dual_state_buttons(self):
        # The dual-state button's sample on T: one among the other types
        # matched. Each one of every probe is compared at its type's
        # functions (tests/tft/test_dual_state_button.py).
        self.assert_each_part(_named(dual_state_button_probes,
                                     "dual-state-button-among-the-types-matched"))

    def test_a_dual_state_button_s_font_is_its_id_among_the_project_s(self):
        # A dual-state button's memory starts with its font's ID among the
        # project's fonts, from a second font added to the folder, as for a
        # text.
        probe = _named(dual_state_button_probes, "dual-state-button-in-a-second-font")[0]
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        bt0, bt1 = project.pages[0].objects[1:]
        self.assertEqual([dual_state_button.variant(one).memory(one, project)[0]
                          for one in (bt0, bt1)], [1, 0])

    def test_pictures_crops_and_touch_captures(self):
        # The sample on T of the picture, the crop, and the touch capture:
        # each one among the other types matched. Each one of every probe is
        # compared at its type's functions (tests/tft/test_picture.py,
        # tests/tft/test_crop.py, tests/tft/test_touch_capture.py).
        self.assert_each_part(_named(picture_probes, "picture-among-the-types-matched")
                              + _named(crop_probes, "crop-among-the-types-matched")
                              + _named(touch_capture_probes,
                                       "touch-capture-among-the-types-matched"))

    def test_a_touch_capture_s_record(self):
        # The frame's record of a touch capture, as a timer's: not drawn, a
        # place and size of 0, 0, 1, 1, its type 5, and 0x27, as it has
        # events but is not drawn. Until the tests of what the frame writes
        # across objects take it.
        probe = _named(touch_capture_probes, "touch-capture-two")[0]
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        record = frame.user_code(project, stand_in_code).records[232:464]
        self.assertEqual(record[:4], b"\x05\x01\x00\x27")
        self.assertEqual(struct.unpack_from("<I", record, 4)[0], 0xFFFFFFFF)
        self.assertEqual(struct.unpack_from("<6H", record, 40), (0, 0, 1, 1, 0, 0))

    def test_radios(self):
        # The radio's sample on T: a radio among the other types matched.
        # Each radio of every probe is compared at its type's functions
        # (tests/tft/test_radio.py).
        self.assert_each_part(_named(radio_probes, "radio-among-the-types-matched"))

    def test_texts(self):
        # The text's sample on T: two texts on a page. Each text of every
        # probe is compared at its type's functions (tests/tft/test_text.py).
        self.assert_each_part([probe for probe in text_probes.PROBES
                               if probe.name == "text-two"])

    def test_txt_rooms_over_earlier_pages(self):
        # On T, a txt's room keeps what earlier pages left in the scratch
        # image, where the Nextion Editor writes nothing. The frame writes
        # the scratch image, so only a whole build compares it: each type
        # that keeps a txt, over a page, past a shorter page, and over the
        # int area.
        self.assert_each_part(text_room_probes.PROBES)

    def test_buttons(self):
        # The button's sample on T: a button beside a text and a number.
        # Each button of every probe is compared at its type's functions
        # (tests/tft/test_button.py).
        self.assert_each_part([probe for probe in button_probes.PROBES
                               if probe.name == "button-beside-a-text-and-a-number"])

    def test_a_button_s_font_is_its_id_among_the_project_s(self):
        # A button's memory starts with its font's ID among the project's
        # fonts, from a second font added to the folder, as for a text.
        probe = next(probe for probe in button_probes.PROBES
                     if probe.name == "button-in-a-second-font")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        b0, b1 = project.pages[0].objects[1:]
        self.assertEqual([button.variant(one).memory(one, project)[0] for one in (b0, b1)],
                         [1, 0])

    def test_numbers(self):
        # The number's sample on T: a number beside a text. Each number of
        # every probe is compared at its type's functions
        # (tests/tft/test_number.py).
        self.assert_each_part([probe for probe in number_probes.PROBES
                               if probe.name == "number-beside-a-text"])

    def test_a_number_s_font_is_its_id_among_the_project_s(self):
        # A number's memory holds its font's ID among the project's fonts at
        # its sixth byte, from a second font added to the folder, as for a
        # text.
        probe = next(probe for probe in number_probes.PROBES
                     if probe.name == "number-in-a-second-font")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        n0, n1 = project.pages[0].objects[1:]
        self.assertEqual([number.variant(one).memory(one, project)[5] for one in (n0, n1)],
                         [1, 0])

    def test_a_text_s_font_is_its_id_among_the_project_s(self):
        # A text's memory starts with its font's ID among the project's
        # fonts. The probe's second font is added to the folder, which a page
        # made in memory, of the base folder's fonts alone, cannot hold.
        probe = next(probe for probe in text_probes.PROBES
                     if probe.name == "text-in-a-second-font")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        t0, t1 = project.pages[0].objects[1:]
        self.assertEqual([text.variant(one).memory(one, project)[0] for one in (t0, t1)],
                         [1, 0])

    def test_hotspots(self):
        # The sample of whole files of a hotspot, on T and on P: one among
        # the types matched. Its own pieces of every probe are compared in
        # tests/tft/test_hotspot.py.
        self.assert_each_part(_named(hotspot_probes, "hotspot-among-the-types-matched")
                              + _named(p_probes, "p-hotspot-among-the-types-matched"))

    def test_sliders(self):
        # The sample of whole files of a slider, on T and on P: one among the
        # types matched. Its own pieces of every probe are compared in
        # tests/tft/test_slider.py.
        self.assert_each_part(_named(slider_probes, "slider-among-the-types-matched")
                              + _named(p_probes, "p-slider-among-the-types-matched"))

    def test_a_slider_s_slide_event_takes_its_record_s_fourth_place(self):
        # With code in its slide event alone, a slider's record gives no
        # place for down and up, and its slide code's place as the fourth,
        # a timer's timer event's. The frame writes the record, so the check
        # stays here until the tests of records take it.
        probe = next(probe for probe in slider_probes.PROBES
                     if probe.name == "slider-slide-code-alone")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        # h0's record follows the page's, of 232 bytes.
        down, up, slide = struct.unpack_from("<3I", frame.user_code(
            project, stand_in_code).records, 232 + 12)
        self.assertEqual((down, up), (0xFFFFFFFF, 0xFFFFFFFF))
        self.assertNotEqual(slide, 0xFFFFFFFF)

    def test_a_hotspot_s_memory_on_p_with_the_attributes_every_component_has(self):
        # As the Nextion Editor wrote it (p-hotspot-shared-attributes), which
        # keeps no fixtures: its drag of 1 as 0 at 32, as it keeps its aph's
        # 0 at 34; its sendkey, movex, and movey, its first, and its time,
        # as a drawn component's; and its effect as 0 at 52. The frame
        # writes its head, so the check stays here until the tests of heads
        # take it.
        code = frame.user_code(built_project("P", with_components(hotspot_component(
            aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
            effect=2, first=10, time=500))))
        # Its memory starts at 72 in the page's memory block, after the
        # places of the page and the hotspot, 4 bytes each, and the page's
        # 64 bytes.
        memory = next(block for block, part in zip(code.blocks, code.block_parts())
                      if part == "page 0" and len(block) > 80)
        self.assertEqual(memory[72 + 28:72 + 56].hex(" "),
                         "58 00 00 00 00 03 00 00 05 00 06 00 0a 00 0a 00 64 00 32 00 6d 00 3b 00 "
                         "00 0a f4 01")

    def test_timers(self):
        # The sample of whole files of a timer, on T and on P: one among a
        # text, a number, a button, and a variable. Its own pieces of every
        # probe are compared in tests/tft/test_timer.py.
        self.assert_each_part(
            _named(timer_probes, "timer-among-a-text-a-number-a-button-and-a-variable")
            + _named(p_probes, "p-timer-among-a-text-a-number-a-button-and-a-variable"))

    def test_xfloats(self):
        # The sample of whole files of an xfloat, on T and on P: one among
        # the types matched. Its own pieces of every probe are compared in
        # tests/tft/test_xfloat.py.
        self.assert_each_part(_named(xfloat_probes, "xfloat-among-the-types-matched")
                              + _named(p_probes, "p-xfloat-among-the-types-matched"))

    def test_an_xfloat_s_font_is_its_id_among_the_project_s(self):
        # An xfloat's memory holds its font's ID among the project's fonts at
        # its sixth byte, as a number's, from a second font added to the
        # folder, which a page made in memory, of the base folder's fonts
        # alone, cannot hold.
        probe = next(probe for probe in xfloat_probes.PROBES
                     if probe.name == "xfloat-in-a-second-font")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        self.assertEqual([xfloat.variant(one).memory(one, project)[5]
                          for one in project.pages[0].objects[1:]], [1, 0])

    def test_qr_codes(self):
        # The sample of whole files of a QR code, on T and on P: one among
        # the types matched. Its own pieces of every probe are compared in
        # tests/tft/test_qr_code.py.
        self.assert_each_part(_named(qr_code_probes, "qr-code-among-the-types-matched")
                              + _named(p_probes, "p-qr-code-among-the-types-matched"))

    def test_gauges(self):
        # The sample of whole files of a gauge, on T and on P: two on a page.
        # Its own pieces of every probe are compared in tests/tft/test_gauge.py.
        self.assert_each_part(_named(gauge_probes, "gauge-two") + _named(p_probes, "p-gauge-two"))

    def test_waveforms(self):
        # The sample of whole files of a waveform, on T and on P: two on a
        # page, with their buffers. Its own pieces of every probe are
        # compared in tests/tft/test_waveform.py.
        self.assert_each_part(_named(waveform_probes, "waveform-two")
                              + _named(p_probes, "p-waveform-two"))

    def test_file_streams(self):
        # The sample of whole files of a file stream, on P: one at its
        # defaults. Its own pieces of every probe are compared in
        # tests/tft/test_file_stream.py.
        self.assert_each_part(_named(p_probes, "p-file-stream-at-its-defaults"))

    def test_a_file_stream_under_a_later_page_s_rooms(self):
        # A later page's txt's room over a file stream keeps its val and its
        # qty from the scratch image; its kind, filled in late, is 0. The
        # frame writes the scratch image, so the check stays here until the
        # tests of memory take it.
        probe = next(probe for probe in file_stream_probes.PROBES
                     if probe.name == "file-stream-under-later-rooms")
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        code = frame.user_code(project)
        memory = next(block for block, part in zip(code.blocks, code.block_parts())
                      if part == "page 1" and len(block) > 100)
        self.assertEqual(memory[248:260].hex(" "), "48 69 00 00 05 00 00 00 07 00 00 00")

    def test_a_file_stream_s_init_and_close(self):
        # Each file stream adds `init` and its ID to the load section, and a
        # call of its close to the end of the page's unload event, in the
        # page's order, after the page's own code. The frame writes the
        # page's events, so the check stays here until its tests take it.
        code = frame.user_code(built_project("P", with_components(
            file_stream_probes.file_stream_component(), text_component(),
            file_stream_probes.file_stream_component("fs1"),
            code="on page0.unload:\n  sys0=1\n")))
        blocks = [block for block, part in zip(code.blocks, code.block_parts())
                  if part == "page 0"]
        unload = blocks.index(b"unload")
        self.assertEqual(blocks[unload + 1:unload + 5], [
            b"\x05\x00\x00\x00\x00=1", b"\x01" + (33 + 13).to_bytes(4, "little") + b"()",
            b"\x01" + (33 + 19 + 41 + 13).to_bytes(4, "little") + b"()", b""])
        self.assertIn(b"\x09\x1f\x041", blocks)
        self.assertIn(b"\x09\x1f\x043", blocks)

    def test_the_total_of_two_file_streams_buffers(self):
        # The last word of the page's memory gives the size of its file
        # streams' buffers together, 10752 each. The frame writes that word,
        # so the check stays here until the tests of memory take it.
        code = frame.user_code(built_project("P", with_components(
            file_stream_probes.file_stream_component(), text_component(),
            file_stream_probes.file_stream_component("fs1"))))
        memory = next(block for block, part in zip(code.blocks, code.block_parts())
                      if part == "page 0" and len(block) > 100)
        self.assertEqual(memory[-4:], struct.pack("<I", 2 * 10752))

    def test_scrolling_texts(self):
        # The sample of whole files of a scrolling text, on T and on P: one
        # among the types matched. Its own pieces of every probe are compared
        # in tests/tft/test_scrolling_text.py.
        self.assert_each_part(
            _named(scrolling_text_probes, "scrolling-text-among-the-types-matched")
            + _named(p_probes, "p-scrolling-text-among-the-types-matched"))

    def test_a_scrolling_text_in_a_second_font_is_matched(self):
        # Its probe adds a second font to the folder, which a page made in
        # memory, of the base folder's fonts alone, cannot hold.
        probe = _named(scrolling_text_probes, "scrolling-text-in-a-second-font")[0]
        with tempfile.TemporaryDirectory() as work:
            project = Project.from_file(_built(probe, Path(work)))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_variables(self):
        # The sample of whole files of a variable, on T and on P: one beside
        # a text, a number, and a button. Its own pieces of every probe are
        # compared in tests/tft/test_variable.py.
        self.assert_each_part(
            _named(variable_probes, "variable-among-a-text-a-number-and-a-button")
            + _named(p_probes, "p-variable-among-a-text-a-number-and-a-button"))

    def test_command_families(self):
        # The sample of whole files of each family of commands, on T, and on
        # P for the families with a probe there, built whole, whose
        # encoder's blocks are compared on its pages in memory in its
        # family's tests:
        # tests/tft/test_command_operands.py, test_crc_commands.py,
        # test_drawing_commands.py, test_waveform_commands.py,
        # test_device_and_buffer_commands.py, test_eeprom_and_gpio_commands.py,
        # test_page_command.py, test_pinyin_commands.py,
        # test_screen_commands.py, test_serial_commands.py, and
        # test_undocumented_commands.py. The samples on P of the last seven,
        # each one's probe on P that keeps fixtures, are compared whole with
        # the other P probes (test_the_p_probes).
        self.assert_each_part([next(probe for probe in module.PROBES if probe.name == name)
                               for module, name in (
                                   (command_operand_probes,
                                    "command-operands-expressions-in-drawing-commands"),
                                   (crc_command_probes, "crc-commands-each"),
                                   (drawing_probes, "drawing-each-command"),
                                   (waveform_command_probes, "waveform-commands-each"),
                                   (device_and_buffer_command_probes,
                                    "device-and-buffer-commands-each"),
                                   (eeprom_and_gpio_probes, "eeprom-and-gpio-each"),
                                   (page_command_probes, "page-by-name"),
                                   (pinyin_probes, "pinyin-in-an-event"),
                                   (screen_command_probes, "screen-commands-each"),
                                   (serial_command_probes, "serial-commands-each"),
                                   (undocumented_command_probes, "undocumented-commands-each"))]
                              + _named(p_probes, "p-crc-commands-each", "p-drawing-each-command",
                                       "p-waveform-commands-each"))

    def test_statement_families(self):
        # The sample of whole files of each family of statements, on T: if,
        # while, for, long and joined conditions, and labels and goto. Their
        # blocks are compared on their pages in memory in their families'
        # tests: tests/tft/test_if_statement.py,
        # test_while_statement.py, test_for_statement.py, test_conditions.py,
        # and test_goto_statement.py. The goto's sample on P,
        # p-goto-across-program-and-events, is compared whole with the other
        # P probes (test_the_p_probes). The other families have no probe on
        # P that keeps fixtures.
        self.assert_each_part(_named(if_probes, "if-event") + _named(while_probes, "while-event")
                              + _named(for_probes, "for-event")
                              + _named(condition_probes, "conditions-texts-holding-joins")
                              + _named(goto_probes, "goto-across-program-and-events"))

    def test_statements_and_texts_in_code(self):
        # The sample of whole files of the statement encoder's own probes and
        # of each family of texts in code, on T: texts set, txts of other
        # characters, the text commands, and conditions of texts. Their
        # blocks, and the components of the probes of txts, are compared on
        # their pages in memory in their families' tests:
        # tests/tft/test_statements.py, test_text_assignments.py,
        # test_text_characters.py, test_text_commands.py, and
        # test_text_conditions.py. Their samples on P,
        # p-statements-system-variables and p-text-commands-each, are
        # compared whole with the other P probes (test_the_p_probes).
        self.assert_each_part(_named(statement_probes, "statements-event")
                              + _named(text_assignment_probes, "text-joined")
                              + _named(text_character_probes, "text-characters-txt-of-latin-1")
                              + _named(text_command_probes, "text-commands-each")
                              + _named(text_condition_probes, "text-conditions-in-if"))

    def test_attributes_hex_numbers_and_references(self):
        # The sample of whole files of each family of components' attributes
        # in code, of hexadecimal numbers, and of references through the
        # screen's arrays, on T: attributes in lines, every attribute of each
        # type read, hexadecimal numbers in assignments, and references in
        # assignments. Their blocks are compared on their pages in memory in
        # their families' tests: tests/tft/test_attributes_in_code.py,
        # test_other_attributes.py, test_hex_numbers.py, and test_indirect.py.
        # The sample on P, p-attributes-read, is compared whole with the other
        # P probes (test_the_p_probes).
        self.assert_each_part(_named(attribute_probes, "attributes-lines")
                              + _named(other_attribute_probes, "other-attributes-read")
                              + _named(hex_number_probes, "hex-numbers-in-assignments")
                              + _named(indirect_probes, "indirect-assignments"))

    def test_models_rotations_page_places_and_other_pages(self):
        # The sample of whole files of a project on another screen model, at
        # another rotation, of a page at another place and size, on T and on
        # P, and of code that names another page's globals. Their components
        # are compared at their types' functions, and the code's blocks at
        # the statement encoder, on their pages made in memory, in
        # tests/tft/test_models.py, test_rotations.py, test_page_place.py, and
        # test_other_page.py.
        self.assert_each_part(
            _named(model_probes, "model-NX3224T024")
            + _named(rotation_probes, "rotation-90-every-type-on-a-picture")
            + _named(page_place_probes, "t-page-of-another-size", "p-page-of-another-size")
            + _named(other_page_probes, "other-page-in-an-event"))

    def test_entry_limits(self):
        # The sample of whole files of the attributes at their entries'
        # limits, on T and on P: a page's effects of 9 and 10, on each of two
        # pages. The frame writes a page's effect in its record and the head
        # of its memory, so the sample checks it until the frame's tests take
        # it. Each component's pieces of every probe are compared in
        # tests/tft/test_entry_limits.py.
        self.assert_each_part(_named(entry_limit_probes, "t-page-effects-9-and-10",
                                     "p-page-effects-9-and-10"))

    def test_media_s_section_and_header_2(self):
        # A gmov playing the second of two animations, of 3 and 2 frames, and
        # two sounds, mono and stereo, on P. The packaging writes the
        # section's rows of the media, its part of sounds, and header 2's
        # counts, so the check stays here until its tests take it.
        def change(folder):
            media_probes.add_animation(folder, "anim", 3)
            media_probes.add_animation(folder, "anim2", 2, duration=200)
            media_probes.add_sound(folder, "beep")
            media_probes.add_sound(folder, "beep2", 2)
            with_components(gmov_component(vid=1))(folder)
        project = built_project("P", change)
        kept = (FIXTURES / "p" / "p-media-of-each" / "table.bin").read_bytes()
        tft = read_tft(compile_project(project, zeros_of_the_table(kept, "P")), "nxwright's file",
                       check=False)
        # Rows 9, 10, and 11 hold the animations, the videos, and the
        # sounds, one after the other: with no video, row 10 is empty, where
        # row 11 starts.
        animations, videos, sounds = tft.table[9:12]
        names = {kind: [name for resource, name in project.resources if resource == kind]
                 for kind in ("animation", "sound")}
        self.assertEqual(animations.size,
                         sum(len(project.blocks[name]) for name in names["animation"]))
        self.assertEqual((videos.place, videos.size), (animations.place + animations.size, 0))
        self.assertEqual(sounds.place, videos.place)
        # A header of 16 bytes for each sound first, giving where its file
        # lies and its length, then the files as they are.
        part = tft.table_part(tft.table[11])
        files = [project.blocks[name] for name in names["sound"]]
        self.assertEqual(struct.unpack_from("<4I", part), (32, len(files[0]), 0, 0))
        self.assertEqual(struct.unpack_from("<4I", part, 16),
                         (32 + len(files[0]), len(files[1]), 0, 0))
        self.assertEqual(part[32:], b"".join(files))
        # The pictures and then the animations, 2 bytes each, at 0x104; the
        # videos and then the sounds at 0x108.
        self.assertEqual(tft.header_2_value(0x104), 2 << 16)
        self.assertEqual(tft.header_2_value(0x108), 2 << 16)

    def test_a_compile_without_ffmpeg_stops_at_a_sound_to_resample(self):
        # It says how to give ffmpeg. The compile gives the packaging no
        # ffmpeg unless named, so the check stays here until the
        # packaging's tests take it.
        project = built_project("P", resampled_sound_probes.with_a_sound(8000, 1, 1))
        kept = (FIXTURES / "p" / "p-media-of-each" / "table.bin").read_bytes()
        with self.assertRaisesRegex(NxwrightError, "the sound tone has 8000 samples a second of "
                                    "8 bits each.*install it, or name it with --ffmpeg"):
            compile_project(project, zeros_of_the_table(kept, "P"))

    def test_keys(self):
        # The sample of whole files of a component's key, on T: a keyed text
        # beside nxwright's keypad. Its components, the keypad's among them,
        # are compared at their types' functions, and the key's lines at the
        # statement encoder, on its pages made in memory, in
        # tests/tft/test_keys.py.
        self.assert_each_part(_named(key_probes, "key-text-on-the-keypad"))

    def test_the_frame_and_a_page(self):
        # The sample of whole files of the frame's own probes and of the
        # page's, on T: code in each of a page's events, and three pages of
        # pictures beside components. The frame's parts are compared at their
        # functions, and the components at their types', in
        # tests/tft/test_frame.py. What no part names, the events' code, each
        # page's texts, the blocks the frame appends to program.s, and the
        # padding, this compares. The page's sample on P, p-page-of-pictures,
        # is compared whole with the other P samples (test_the_p_probes).
        self.assert_each_part(_named(frame_probes, "frame-page-events")
                              + _named(page_probes, "page-of-pictures"))

    def test_eight_types_of_p_at_their_defaults(self):
        # The sample of whole files of the select, the gmov, the sliding
        # text, the combo-box, the switch, the external picture, the video,
        # and the audio on P: each one's probe at its defaults. Their pieces
        # are compared at their types' functions in their own modules.
        self.assert_each_part(_p_probes(*("p-%s-at-its-defaults" % name for name in (
            "select", "gmov", "sliding-text", "combo-box", "switch", "external-picture",
            "video", "audio"))))

    def test_a_data_record_and_a_file_browser(self):
        # The sample of whole files of the data record and the file browser
        # on P: each one's probe at its defaults, the data record's memory in
        # the first block's int area. Their pieces are compared at their
        # types' functions in their own modules.
        self.assert_each_part(_p_probes("p-data-record-at-its-defaults",
                                        "p-file-browser-at-its-defaults"))

    def test_a_gmov_s_playend_place(self):
        # A gmov's record gives where its playend event's code starts, in
        # the place a page's record gives its unload event's, before its
        # base; 0xFFFFFFFF without code there.
        for name, has_code in (("p-gmov-at-its-defaults", False), ("p-gmov-in-code", True)):
            with self.subTest(name), tempfile.TemporaryDirectory() as work:
                project = Project.from_file(_built(_p_probes(name)[0], Path(work)))
                record = laid_out_pieces(project)["page0-1-record"]
                self.assertEqual(struct.unpack_from("<I", record, 24)[0] != 0xFFFFFFFF, has_code)

    def test_a_video_from_a_file_s_room_and_buffer(self):
        # From a file, at its default path_m of 255: its from, 1, at 80, its
        # path_m at 82, the place of its path, right after the components'
        # memory, at 84, and its buffer after its path's room, 256 bytes, at
        # 92. The frame places its room and its buffer, so the check stays
        # here until the tests of the frame's memory take it.
        pieces = laid_out_pieces(built_project("P", with_components(
            video_component(**{"from": 1}))))
        memory = pieces["page0-1-head"] + pieces["page0-1-memory"]
        self.assertEqual(memory[80:96].hex(" "),
                         "01 00 ff 00 c4 00 00 00 00 fa 00 00 c4 01 00 00")

    def test_an_audio_s_record(self):
        # An audio's record gives 50 by 50, left of the screen, and its
        # playend event's code's place as its fifth place: 0xFFFFFFFF
        # without code there. In the probe of code, the audio follows a
        # text.
        for name, object_id, has_code in (("p-audio-at-its-defaults", 1, False),
                                          ("p-audio-in-code", 2, True)):
            with self.subTest(name), tempfile.TemporaryDirectory() as work:
                project = Project.from_file(_built(_p_probes(name)[0], Path(work)))
                record = laid_out_pieces(project)["page0-%d-record" % object_id]
                self.assertEqual(record[:4], bytes([4, object_id, 0, 0x27]))
                self.assertEqual(struct.unpack_from("<6h", record, 40), (-50, 0, 50, 50, -1, 49))
                self.assertEqual(struct.unpack_from("<I", record, 24)[0] != 0xFFFFFFFF, has_code)

    def test_the_attributes_every_component_has(self):
        # The sample on T of the attributes every component has: a component
        # of each type on page0, every other one global, and two globals on
        # page1, beside two more ints. Each component of its probes is
        # compared at its type's functions in tests/tft/test_shared_attributes.py.
        self.assert_each_part(_named(shared_attribute_probes,
                                     "shared-attributes-globals-on-two-pages"))

    def test_encodings(self):
        # The sample on T of a project's encoding: a text of gb2312's
        # characters, and code after a comment of them. Each probe's text
        # and blocks of code are compared at their functions in
        # tests/tft/test_encodings.py.
        self.assert_each_part(_named(encoding_probes, "encoding-gb2312"))


def _p_probes(*names: str) -> list:
    """Returns the probes of p_probes.py named `names`, in that order."""
    by_name = {probe.name: probe for probe in p_probes.PROBES}
    return [by_name[name] for name in names]


if __name__ == "__main__":
    unittest.main()
